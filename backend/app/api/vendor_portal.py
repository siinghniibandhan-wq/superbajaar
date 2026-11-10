"""Supplier-scoped vendor portal APIs. Every query derives supplier identity from the session."""
from datetime import date
from decimal import Decimal
import os
import uuid

import boto3

import psycopg
from fastapi import APIRouter, File, HTTPException, Request, UploadFile
from psycopg.rows import dict_row
from pydantic import BaseModel, Field, model_validator

from app.core.config import settings

router = APIRouter(prefix="/vendor-portal", tags=["vendor portal"])


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
        "SELECT vpu.supplier_id,s.name AS supplier_name,s.email,s.phone,s.gstin,s.address "
        "FROM vendor_portal_users vpu JOIN suppliers s ON s.id=vpu.supplier_id "
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
    source_document_uri: str | None = Field(default=None, max_length=1000)

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


@router.post("/documents", status_code=201)
async def upload_vendor_document(request: Request, file: UploadFile = File(...)):
    """Upload an invoice attachment to a private, server-side-encrypted S3 bucket."""
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
        extension = {"application/pdf": "pdf", "image/jpeg": "jpg", "image/png": "png"}[file.content_type]
        key = f"vendor-invoices/{vendor['supplier_id']}/{uuid.uuid4().hex}.{extension}"
        client = boto3.client("s3", region_name=os.getenv("AWS_REGION") or None)
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
        client = boto3.client("s3", region_name=os.getenv("AWS_REGION") or None)
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
            response = conn.execute(
                "SELECT response,note,responded_at FROM vendor_purchase_order_responses WHERE purchase_order_id=%s",
                (purchase_order_id,),
            ).fetchone()
        return {**order, "lines": lines, "vendor_response": response}
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
    email = getattr(request.state, "user_email", None)
    if not user_id or not email:
        raise HTTPException(401, "Sign in to continue")
    try:
        with _connect() as conn:
            with conn.transaction():
                vendor = _vendor_user(conn, request)
                order = conn.execute(
                    "SELECT id,status FROM purchase_orders WHERE id=%s AND supplier_id=%s FOR SHARE",
                    (payload.purchase_order_id, vendor["supplier_id"]),
                ).fetchone()
                if not order:
                    raise HTTPException(404, "Purchase order not found")
                if order["status"] not in {"ordered", "partially_received", "received"}:
                    raise HTTPException(409, "Invoices can be submitted only against an issued purchase order")
                row = conn.execute(
                    "INSERT INTO supplier_invoices(supplier_id,purchase_order_id,supplier_gstin,invoice_number,invoice_date,due_date,"
                    "taxable_value,cgst_amount,sgst_amount,igst_amount,cess_amount,freight_amount,discount_amount,invoice_total,"
                    "source_document_uri,match_status,created_by_user_id,created_by_email) "
                    "VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,'pending',%s,%s) "
                    "RETURNING id,purchase_order_id,invoice_number,invoice_date,invoice_total,match_status,created_at",
                    (vendor["supplier_id"],payload.purchase_order_id,payload.supplier_gstin,payload.invoice_number.strip(),
                     payload.invoice_date,payload.due_date,payload.taxable_value,payload.cgst_amount,payload.sgst_amount,
                     payload.igst_amount,payload.cess_amount,payload.freight_amount,payload.discount_amount,payload.invoice_total,
                     payload.source_document_uri,user_id,email),
                ).fetchone()
        return row
    except HTTPException:
        raise
    except psycopg.errors.UniqueViolation as exc:
        raise HTTPException(409, "This invoice number has already been submitted for your supplier account") from exc
    except psycopg.Error as exc:
        raise HTTPException(503, "Unable to submit supplier invoice") from exc
