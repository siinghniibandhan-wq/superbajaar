"""Supplier-scoped vendor portal APIs. Every query derives supplier identity from the session."""
from datetime import date
from decimal import Decimal
import os
import re
import uuid
from urllib.parse import urlsplit

from botocore.exceptions import BotoCoreError, ClientError

import boto3

import psycopg
from fastapi import APIRouter, File, HTTPException, Request, UploadFile
from psycopg.rows import dict_row
from pydantic import BaseModel, Field, field_validator, model_validator

from app.core.config import settings
from app.api.purchasing_lifecycle import SupplierInvoiceCreate, SupplierInvoiceLineInput, create_supplier_invoice

router = APIRouter(prefix="/vendor-portal", tags=["vendor portal"])


def _s3_client():
    """Use the EC2 instance role/default AWS credential chain for private S3 access."""
    region = (
        os.getenv("SB_S3_REGION", "").strip()
        or os.getenv("AWS_REGION", "").strip()
        or settings.aws_region
    )
    return boto3.client("s3", region_name=region)


def _connect():
    if not settings.database_url:
        raise HTTPException(503, "Vendor portal database is not configured")
    try:
        return psycopg.connect(settings.database_url, row_factory=dict_row, connect_timeout=3)
    except psycopg.Error as exc:
        raise HTTPException(503, "Vendor portal database is unavailable") from exc


def _vendor_user(conn, request: Request):
    user_id = getattr(request.state, "user_id", None)
    if not user_id:
        raise HTTPException(401, "Sign in to the Vendor Portal")
    row = conn.execute(
        "SELECT vpu.supplier_id,s.name AS supplier_name,s.email,s.phone,s.gstin,s.address,party.sbid "
        "FROM vendor_portal_users vpu JOIN suppliers s ON s.id=vpu.supplier_id "
        "LEFT JOIN identity_profiles ip ON ip.supplier_id=s.id AND ip.profile_type='vendor_organisation' AND ip.status='active' "
        "LEFT JOIN identity_parties party ON party.id=ip.party_id "
        "JOIN app_users u ON u.id=vpu.user_id "
        "WHERE vpu.user_id=%s AND vpu.is_active=TRUE AND u.is_active=TRUE AND s.is_active=TRUE "
        "ORDER BY vpu.id LIMIT 1",
        (user_id,),
    ).fetchone()
    if not row:
        raise HTTPException(403, "This account is not linked to an active supplier")
    return row


class PurchaseOrderResponse(BaseModel):
    response: str = Field(pattern="^(accepted|rejected)$")
    note: str | None = Field(default=None, max_length=1000)


class DispatchNoticeInput(BaseModel):
    purchase_order_id: int = Field(gt=0)
    supplier_dispatch_reference: str | None = Field(default=None, max_length=100)
    dispatched_at: date | None = None
    expected_arrival_at: date | None = None
    carrier_name: str | None = Field(default=None, max_length=160)
    tracking_reference: str | None = Field(default=None, max_length=160)
    notes: str | None = Field(default=None, max_length=1000)


def _matches_document_signature(content_type: str, content: bytes) -> bool:
    signatures = {
        "application/pdf": content.startswith(b"%PDF-"),
        "image/jpeg": content.startswith(bytes((0xFF, 0xD8, 0xFF))),
        "image/png": content.startswith(bytes((0x89, 0x50, 0x4E, 0x47, 0x0D, 0x0A, 0x1A, 0x0A))),
    }
    return signatures.get(content_type, False)


class InvoiceInput(BaseModel):
    purchase_order_id: int = Field(gt=0)
    supplier_gstin: str | None = Field(default=None, min_length=15, max_length=15)
    invoice_number: str = Field(min_length=1, max_length=100)
    invoice_date: date
    due_date: date | None = None
    taxable_value: Decimal = Field(ge=0, max_digits=16, decimal_places=2)
    cgst_amount: Decimal = Field(default=Decimal("0"), ge=0, max_digits=16, decimal_places=2)
    sgst_amount: Decimal = Field(default=Decimal("0"), ge=0, max_digits=16, decimal_places=2)
    igst_amount: Decimal = Field(default=Decimal("0"), ge=0, max_digits=16, decimal_places=2)
    cess_amount: Decimal = Field(default=Decimal("0"), ge=0, max_digits=16, decimal_places=2)
    freight_amount: Decimal = Field(default=Decimal("0"), ge=0, max_digits=16, decimal_places=2)
    discount_amount: Decimal = Field(default=Decimal("0"), ge=0, max_digits=16, decimal_places=2)
    invoice_total: Decimal = Field(gt=0, max_digits=16, decimal_places=2)
    source_document_uri: str = Field(min_length=1, max_length=1000)
    lines: list[SupplierInvoiceLineInput] = Field(min_length=1, max_length=200)

    @field_validator("supplier_gstin")
    @classmethod
    def valid_supplier_gstin(cls, value):
        if value:
            value = value.strip().upper()
            if len(value) != 15 or not value[:2].isdigit() or not value[2:7].isalpha() or not value[7:11].isdigit() or not value[11].isalpha() or not value[12].isdigit() or not value[13].isalnum() or value[14] not in "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ":
                raise ValueError("Enter a GSTIN in the expected 15-character format")
        return value

    @model_validator(mode="after")
    def invoice_total_matches_components(self):
        expected = (
            self.taxable_value + self.cgst_amount + self.sgst_amount
            + self.igst_amount + self.cess_amount + self.freight_amount
            - self.discount_amount
        )
        if abs(expected - self.invoice_total) > Decimal("0.01"):
            raise ValueError("Invoice total must equal taxable value, taxes, freight and discount")
        if self.due_date and self.due_date < self.invoice_date:
            raise ValueError("Invoice due date cannot precede invoice date")
        return self


def _verify_vendor_document_object(client, bucket: str, document_uri: str, supplier_id: int) -> str:
    """Verify an uploaded invoice object is real and belongs to this supplier."""
    parsed = urlsplit(document_uri)
    prefix = f"vendor-invoices/{supplier_id}/"
    if (
        parsed.scheme != "s3"
        or parsed.netloc != bucket
        or parsed.query
        or parsed.fragment
        or not parsed.path.startswith("/")
    ):
        raise HTTPException(422, "Invoice document must reference this supplier's private S3 upload")

    key = parsed.path[1:]
    name = key[len(prefix):] if key.startswith(prefix) else ""
    if not name or "/" in name or not re.fullmatch(r"[0-9a-f]{32}\.(pdf|jpg|png)", name):
        raise HTTPException(422, "Invoice document must reference a valid supplier upload")

    try:
        head = client.head_object(Bucket=bucket, Key=key)
    except ClientError as exc:
        status = exc.response.get("ResponseMetadata", {}).get("HTTPStatusCode")
        error_code = exc.response.get("Error", {}).get("Code")
        if status == 404 or error_code in {"404", "NoSuchKey", "NotFound"}:
            raise HTTPException(422, "Uploaded invoice document was not found in private storage") from exc
        raise HTTPException(503, "Unable to verify invoice document in private storage") from exc
    except BotoCoreError as exc:
        raise HTTPException(503, "Unable to verify invoice document in private storage") from exc

    metadata = head.get("Metadata") or {}
    if metadata.get("supplier-id") != str(supplier_id):
        raise HTTPException(403, "Invoice document does not belong to this supplier")
    if head.get("ServerSideEncryption") != "AES256":
        raise HTTPException(422, "Invoice document does not meet private-storage encryption requirements")
    if head.get("ContentLength", 0) < 1 or head.get("ContentLength", 0) > 10 * 1024 * 1024:
        raise HTTPException(422, "Invoice document size is invalid")
    expected_type = {"pdf": "application/pdf", "jpg": "image/jpeg", "png": "image/png"}[name.rsplit(".", 1)[1]]
    if head.get("ContentType") != expected_type:
        raise HTTPException(422, "Invoice document content type does not match its file extension")
    return key


@router.post("/documents", status_code=201)
async def upload_vendor_document(request: Request, file: UploadFile = File(...)):
    """Upload an invoice attachment to the configured private AWS S3 bucket."""
    if file.content_type not in {"application/pdf", "image/jpeg", "image/png"}:
        raise HTTPException(415, "Upload a PDF, JPEG or PNG document")
    bucket = os.getenv("SB_PRIVATE_DOCUMENT_BUCKET", "").strip()
    if not bucket:
        raise HTTPException(503, "Private document storage is not configured")
    try:
        with _connect() as conn:
            vendor = _vendor_user(conn, request)
        content = await file.read(10 * 1024 * 1024 + 1)
        if not content or len(content) > 10 * 1024 * 1024:
            raise HTTPException(413, "Document must be between 1 byte and 10 MB")
        if not _matches_document_signature(file.content_type, content):
            raise HTTPException(415, "The uploaded file content does not match its declared document type")
        extension = {"application/pdf": "pdf", "image/jpeg": "jpg", "image/png": "png"}[file.content_type]
        key = f"vendor-invoices/{vendor['supplier_id']}/{uuid.uuid4().hex}.{extension}"
        client = _s3_client()
        client.put_object(
            Bucket=bucket, Key=key, Body=content, ContentType=file.content_type,
            ServerSideEncryption="AES256",
            Metadata={"supplier-id": str(vendor["supplier_id"])},
        )
        return {"document_uri": f"s3://{bucket}/{key}", "file_name": file.filename, "content_type": file.content_type}
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(503, "Private document upload failed; verify storage configuration and permissions") from exc
    finally:
        await file.close()


@router.get("/invoices/{invoice_id}/document")
def vendor_invoice_document(invoice_id: int, request: Request):
    bucket = os.getenv("SB_PRIVATE_DOCUMENT_BUCKET", "").strip()
    if not bucket:
        raise HTTPException(503, "Private document storage is not configured")
    try:
        with _connect() as conn:
            vendor = _vendor_user(conn, request)
            row = conn.execute(
                "SELECT source_document_uri FROM supplier_invoices WHERE id=%s AND supplier_id=%s",
                (invoice_id, vendor["supplier_id"]),
            ).fetchone()
            if not row or not row["source_document_uri"]:
                raise HTTPException(404, "Invoice document not found")
            prefix = f"s3://{bucket}/vendor-invoices/{vendor['supplier_id']}/"
            if not row["source_document_uri"].startswith(prefix):
                raise HTTPException(403, "Invoice document is outside this supplier account")
            key = row["source_document_uri"][len(f"s3://{bucket}/"):]
        client = _s3_client()
        url = client.generate_presigned_url(
            "get_object", Params={"Bucket": bucket, "Key": key}, ExpiresIn=300
        )
        return {"download_url": url, "expires_in": 300}
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(503, "Unable to create a secure invoice document link") from exc


@router.get("/me")
def vendor_me(request: Request):
    try:
        with _connect() as conn:
            vendor = _vendor_user(conn, request)
        return {"portal": "vendor", "supplier": vendor}
    except HTTPException:
        raise
    except psycopg.Error as exc:
        raise HTTPException(503, "Unable to load vendor profile") from exc


@router.get("/dashboard")
def vendor_dashboard(request: Request):
    try:
        with _connect() as conn:
            vendor = _vendor_user(conn, request)
            supplier_id = vendor["supplier_id"]
            orders = conn.execute(
                "SELECT count(*) AS total, count(*) FILTER (WHERE po.status IN ('ordered','partially_received')) AS open "
                "FROM purchase_orders po WHERE po.supplier_id=%s", (supplier_id,)
            ).fetchone()
            invoices = conn.execute(
                "SELECT count(*) AS total, count(*) FILTER (WHERE si.match_status IN ('pending','variance','blocked')) AS awaiting_review, "
                "COALESCE(sum(si.invoice_total),0) AS submitted_value "
                "FROM supplier_invoices si WHERE si.supplier_id=%s", (supplier_id,)
            ).fetchone()
            return {"supplier": vendor, "orders": orders, "invoices": invoices}
    except HTTPException:
        raise
    except psycopg.Error as exc:
        raise HTTPException(503, "Unable to load vendor dashboard") from exc


@router.get("/orders")
def vendor_orders(request: Request, limit: int = 100, offset: int = 0):
    if limit < 1 or limit > 200 or offset < 0:
        raise HTTPException(422, "Invalid pagination")
    try:
        with _connect() as conn:
            vendor = _vendor_user(conn, request)
            rows = conn.execute(
                "SELECT po.id,po.purchase_number,po.status,po.subtotal,po.notes,po.created_at,po.updated_at,"
                "(SELECT count(*) FROM purchase_order_lines pol WHERE pol.purchase_order_id=po.id) AS line_count,"
                "vpr.response AS vendor_response,vpr.responded_at "
                "FROM purchase_orders po LEFT JOIN vendor_purchase_order_responses vpr ON vpr.purchase_order_id=po.id "
                "WHERE po.supplier_id=%s ORDER BY po.created_at DESC LIMIT %s OFFSET %s",
                (vendor["supplier_id"], limit, offset),
            ).fetchall()
        return {"items": rows, "limit": limit, "offset": offset}
    except HTTPException:
        raise
    except psycopg.Error as exc:
        raise HTTPException(503, "Unable to load purchase orders") from exc


@router.get("/orders/{purchase_order_id}")
def vendor_order_detail(purchase_order_id: int, request: Request):
    try:
        with _connect() as conn:
            vendor = _vendor_user(conn, request)
            order = conn.execute(
                "SELECT po.id,po.purchase_number,po.status,po.subtotal,po.notes,po.created_at,po.updated_at "
                "FROM purchase_orders po WHERE po.id=%s AND po.supplier_id=%s",
                (purchase_order_id, vendor["supplier_id"]),
            ).fetchone()
            if not order:
                raise HTTPException(404, "Purchase order not found")
            lines = conn.execute(
                "SELECT pol.id AS line_id,pol.variant_id,v.sku,p.name AS product_name,"
                "pol.quantity_ordered,pol.quantity_received,pol.unit_cost "
                "FROM purchase_order_lines pol JOIN product_variants v ON v.id=pol.variant_id "
                "JOIN products p ON p.id=v.product_id WHERE pol.purchase_order_id=%s ORDER BY pol.id",
                (purchase_order_id,),
            ).fetchall()
            invoiceable_lines = conn.execute(
                "SELECT grl.id AS goods_receipt_line_id,grl.purchase_order_line_id,grl.variant_id,v.sku,"
                "p.name AS product_name,grl.accepted_quantity,pol.unit_cost,"
                "COALESCE(sum(il.quantity) FILTER (WHERE si.id IS NOT NULL),0) AS invoiced_quantity,"
                "(grl.accepted_quantity-COALESCE(sum(il.quantity) FILTER (WHERE si.id IS NOT NULL),0)) AS available_quantity "
                "FROM goods_receipt_lines grl JOIN goods_receipts gr ON gr.id=grl.goods_receipt_id "
                "JOIN purchase_order_lines pol ON pol.id=grl.purchase_order_line_id "
                "JOIN product_variants v ON v.id=grl.variant_id JOIN products p ON p.id=v.product_id "
                "LEFT JOIN supplier_invoice_lines il ON il.goods_receipt_line_id=grl.id "
                "LEFT JOIN supplier_invoices si ON si.id=il.supplier_invoice_id AND si.match_status<>'rejected' "
                "WHERE gr.purchase_order_id=%s AND gr.supplier_id=%s AND gr.status='accepted' "
                "GROUP BY grl.id,grl.purchase_order_line_id,grl.variant_id,v.sku,p.name,grl.accepted_quantity,pol.unit_cost "
                "HAVING grl.accepted_quantity-COALESCE(sum(il.quantity) FILTER (WHERE si.id IS NOT NULL),0)>0 "
                "ORDER BY grl.id",
                (purchase_order_id,vendor["supplier_id"]),
            ).fetchall()
            response = conn.execute(
                "SELECT response,note,responded_at FROM vendor_purchase_order_responses WHERE purchase_order_id=%s",
                (purchase_order_id,),
            ).fetchone()
        return {**order, "lines": lines, "invoiceable_lines": invoiceable_lines, "vendor_response": response}
    except HTTPException:
        raise
    except psycopg.Error as exc:
        raise HTTPException(503, "Unable to load purchase order") from exc


@router.post("/orders/{purchase_order_id}/respond")
def respond_to_order(purchase_order_id: int, payload: PurchaseOrderResponse, request: Request):
    user_id = getattr(request.state, "user_id", None)
    if not user_id:
        raise HTTPException(401, "Sign in to continue")
    try:
        with _connect() as conn:
            with conn.transaction():
                vendor = _vendor_user(conn, request)
                order = conn.execute(
                    "SELECT id,status FROM purchase_orders WHERE id=%s AND supplier_id=%s FOR UPDATE",
                    (purchase_order_id, vendor["supplier_id"]),
                ).fetchone()
                if not order:
                    raise HTTPException(404, "Purchase order not found")
                if order["status"] not in {"ordered", "partially_received"}:
                    raise HTTPException(409, "Only active purchase orders can be acknowledged")
                if conn.execute("SELECT id FROM vendor_purchase_order_responses WHERE purchase_order_id=%s", (purchase_order_id,)).fetchone():
                    raise HTTPException(409, "A response has already been recorded for this purchase order")
                row = conn.execute(
                    "INSERT INTO vendor_purchase_order_responses(purchase_order_id,supplier_id,response,note,responded_by_user_id) "
                    "VALUES(%s,%s,%s,%s,%s) RETURNING id,response,note,responded_at",
                    (purchase_order_id, vendor["supplier_id"], payload.response, payload.note, user_id),
                ).fetchone()
        return row
    except HTTPException:
        raise
    except psycopg.Error as exc:
        raise HTTPException(503, "Unable to record purchase order response") from exc


@router.get("/dispatches")
def vendor_dispatches(request: Request):
    try:
        with _connect() as conn:
            vendor = _vendor_user(conn, request)
            rows = conn.execute(
                "SELECT d.id,d.purchase_order_id,po.purchase_number,d.supplier_dispatch_reference,d.dispatched_at,"
                "d.expected_arrival_at,d.carrier_name,d.tracking_reference,d.notes,d.created_at "
                "FROM supplier_dispatch_notices d JOIN purchase_orders po ON po.id=d.purchase_order_id "
                "WHERE d.supplier_id=%s ORDER BY d.created_at DESC",
                (vendor["supplier_id"],),
            ).fetchall()
        return {"items": rows}
    except HTTPException:
        raise
    except psycopg.Error as exc:
        raise HTTPException(503, "Unable to load dispatches") from exc


@router.post("/dispatches", status_code=201)
def create_dispatch(payload: DispatchNoticeInput, request: Request):
    try:
        with _connect() as conn:
            with conn.transaction():
                vendor = _vendor_user(conn, request)
                order = conn.execute(
                    "SELECT id FROM purchase_orders WHERE id=%s AND supplier_id=%s AND status IN ('ordered','partially_received') FOR SHARE",
                    (payload.purchase_order_id, vendor["supplier_id"]),
                ).fetchone()
                if not order:
                    raise HTTPException(404, "Active purchase order not found")
                row = conn.execute(
                    "INSERT INTO supplier_dispatch_notices(purchase_order_id,supplier_id,supplier_dispatch_reference,dispatched_at,"
                    "expected_arrival_at,carrier_name,tracking_reference,notes) VALUES(%s,%s,%s,%s,%s,%s,%s,%s) "
                    "RETURNING id,purchase_order_id,supplier_dispatch_reference,dispatched_at,expected_arrival_at,carrier_name,tracking_reference,notes,created_at",
                    (payload.purchase_order_id,vendor["supplier_id"],payload.supplier_dispatch_reference,payload.dispatched_at,
                     payload.expected_arrival_at,payload.carrier_name,payload.tracking_reference,payload.notes),
                ).fetchone()
        return row
    except HTTPException:
        raise
    except psycopg.Error as exc:
        raise HTTPException(503, "Unable to submit dispatch notice") from exc


@router.get("/invoices")
def vendor_invoices(request: Request):
    try:
        with _connect() as conn:
            vendor = _vendor_user(conn, request)
            rows = conn.execute(
                "SELECT si.id,si.purchase_order_id,po.purchase_number,si.invoice_number,si.invoice_date,si.due_date,"
                "si.taxable_value,si.invoice_total,si.match_status,si.created_at,"
                "COALESCE((SELECT sum(spa.allocated_amount) FROM supplier_payment_allocations spa WHERE spa.supplier_invoice_id=si.id),0) AS paid_amount "
                "FROM supplier_invoices si JOIN purchase_orders po ON po.id=si.purchase_order_id "
                "WHERE si.supplier_id=%s ORDER BY si.created_at DESC",
                (vendor["supplier_id"],),
            ).fetchall()
            payments = conn.execute(
                "SELECT spa.supplier_invoice_id,spa.accounting_voucher_id,spa.allocated_amount,spa.allocated_at "
                "FROM supplier_payment_allocations spa JOIN supplier_invoices si ON si.id=spa.supplier_invoice_id "
                "WHERE si.supplier_id=%s ORDER BY spa.allocated_at DESC",
                (vendor["supplier_id"],),
            ).fetchall()
        return {"items": rows, "payments": payments}
    except HTTPException:
        raise
    except psycopg.Error as exc:
        raise HTTPException(503, "Unable to load invoices and payment allocations") from exc


@router.post("/invoices", status_code=201)
def submit_invoice(payload: InvoiceInput, request: Request):
    user_id = getattr(request.state, "user_id", None)
    if not user_id:
        raise HTTPException(401, "Sign in to continue")
    try:
        with _connect() as conn:
            vendor = _vendor_user(conn, request)
            order = conn.execute(
                "SELECT id FROM purchase_orders WHERE id=%s AND supplier_id=%s",
                (payload.purchase_order_id, vendor["supplier_id"]),
            ).fetchone()
            if not order:
                raise HTTPException(404, "Purchase order not found")
        bucket = os.getenv("SB_PRIVATE_DOCUMENT_BUCKET", "").strip()
        if not bucket:
            raise HTTPException(503, "Private document storage is not configured")
        _verify_vendor_document_object(
            _s3_client(), bucket, payload.source_document_uri, vendor["supplier_id"]
        )
        # Reuse the canonical Purchasing invoice workflow: policy checks, PO-line
        # matching, QC-accepted GRN validation, quantity limits and match status.
        canonical_payload = SupplierInvoiceCreate(**payload.model_dump())
        return create_supplier_invoice(canonical_payload, request)
    except HTTPException:
        raise
    except psycopg.errors.UniqueViolation as exc:
        raise HTTPException(409, "This invoice number has already been submitted for your supplier account") from exc
    except psycopg.Error as exc:
        raise HTTPException(503, "Unable to submit supplier invoice") from exc
