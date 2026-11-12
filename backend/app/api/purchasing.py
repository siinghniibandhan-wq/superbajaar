"""Supplier, purchase order and goods receipt API.
Requires the baseline purchasing, catalogue and inventory schema.
"""
from datetime import date
from decimal import Decimal
import hashlib
import json
import uuid

import psycopg
from fastapi import APIRouter, HTTPException, Query, Request
from psycopg.rows import dict_row
from pydantic import BaseModel, Field, field_validator

from app.core.config import settings
from app.api.organisation_policies import load_active_policy
from app.services.organisation_policy import evaluate_purchase_policy

router = APIRouter(prefix="/purchasing", tags=["purchasing"])


def _connect():
    if not settings.database_url:
        raise HTTPException(503, "Purchasing database is not configured")
    try:
        return psycopg.connect(settings.database_url, row_factory=dict_row, connect_timeout=3)
    except psycopg.Error as exc:
        raise HTTPException(503, "Purchasing database is unavailable") from exc


def _db_error(exc):
    if getattr(exc, "sqlstate", None) == "23503":
        return HTTPException(422, "Referenced supplier, location or variant does not exist")
    if getattr(exc, "sqlstate", None) == "23505":
        return HTTPException(409, "Supplier or purchase reference already exists")
    if getattr(exc, "sqlstate", None) == "23514":
        return HTTPException(422, "Purchase quantity or value violates a database constraint")
    return HTTPException(503, "Purchasing storage unavailable; verify the purchasing, catalogue and inventory schema")


class SupplierCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    contact_name: str | None = Field(default=None, max_length=200)
    phone: str | None = Field(default=None, max_length=30)
    email: str | None = Field(default=None, max_length=254)
    gstin: str | None = Field(default=None, min_length=15, max_length=15)
    address: str | None = Field(default=None, max_length=1000)

    @field_validator("name")
    @classmethod
    def valid_name(cls, value):
        if not value.strip():
            raise ValueError("Supplier name cannot be blank")
        return value.strip()

    @field_validator("gstin")
    @classmethod
    def valid_gstin_shape(cls, value):
        if value:
            value = value.strip().upper()
            if len(value) != 15 or not value[:2].isdigit() or not value[2:7].isalpha() or not value[7:11].isdigit() or not value[11].isalpha() or not value[12].isdigit() or not value[13].isalnum() or value[14] not in "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ":
                raise ValueError("Enter a GSTIN in the expected 15-character format")
            return value
        return value


class PurchaseLine(BaseModel):
    variant_id: int = Field(gt=0)
    quantity: Decimal = Field(gt=0, max_digits=14, decimal_places=3)
    unit_cost: Decimal = Field(ge=0, max_digits=12, decimal_places=2)


class PurchaseCreate(BaseModel):
    supplier_id: int = Field(gt=0)
    location_id: int = Field(gt=0)
    notes: str | None = Field(default=None, max_length=2000)
    lines: list[PurchaseLine] = Field(min_length=1, max_length=200)

    @field_validator("lines")
    @classmethod
    def unique_variants(cls, lines):
        ids = [line.variant_id for line in lines]
        if len(ids) != len(set(ids)):
            raise ValueError("Each variant must appear once per purchase order")
        return lines


class ReceiveLine(BaseModel):
    line_id: int = Field(gt=0)
    quantity: Decimal = Field(gt=0, max_digits=14, decimal_places=3)
    batch_code: str | None = Field(default=None, max_length=120)
    manufacture_date: date | None = None
    expiry_date: date | None = None


class GoodsReceipt(BaseModel):
    idempotency_key: uuid.UUID | None = None
    lines: list[ReceiveLine] = Field(min_length=1, max_length=200)
    note: str | None = Field(default=None, max_length=500)


@router.get("/suppliers")
def list_suppliers(search: str | None = Query(default=None, max_length=200), limit: int = Query(default=100, ge=1, le=500), offset: int = Query(default=0, ge=0)):
    clauses = ["s.is_active=TRUE"]
    count_clauses = ["is_active=TRUE"]
    params = []
    if search and search.strip():
        term = "%" + search.strip() + "%"
        clauses.append("(s.name ILIKE %s OR COALESCE(s.phone,'') ILIKE %s OR COALESCE(s.gstin,'') ILIKE %s)")
        count_clauses.append("(name ILIKE %s OR COALESCE(phone,'') ILIKE %s OR COALESCE(gstin,'') ILIKE %s)")
        params.extend([term, term, term])
    where = " WHERE " + " AND ".join(clauses)
    count_where = " WHERE " + " AND ".join(count_clauses)
    try:
        with _connect() as conn:
            items = conn.execute(
                "SELECT s.id,s.name,s.contact_name,s.phone,s.email,s.gstin,s.address,s.is_active,s.created_at,iparty.sbid "
                "FROM suppliers s LEFT JOIN identity_profiles ip ON ip.supplier_id=s.id "
                "AND ip.profile_type='vendor_organisation' AND ip.status='active' "
                "LEFT JOIN identity_parties iparty ON iparty.id=ip.party_id"
                + where + " ORDER BY s.name LIMIT %s OFFSET %s",
                (*params, limit, offset),
            ).fetchall()
            total = conn.execute("SELECT count(*) AS total FROM suppliers" + count_where, params).fetchone()["total"]
        return {"items": items, "total": total, "limit": limit, "offset": offset}
    except psycopg.Error as exc:
        raise _db_error(exc) from exc


@router.post("/suppliers", status_code=201)
def create_supplier(payload: SupplierCreate):
    try:
        with _connect() as conn:
            with conn.transaction():
                row = conn.execute(
                    "INSERT INTO suppliers(name,contact_name,phone,email,gstin,address) VALUES(%s,%s,%s,%s,%s,%s) RETURNING id,name,contact_name,phone,email,gstin,address,is_active,created_at",
                    (payload.name, payload.contact_name.strip() if payload.contact_name else None, payload.phone.strip() if payload.phone else None, payload.email.strip().lower() if payload.email else None, payload.gstin, payload.address.strip() if payload.address else None),
                ).fetchone()
                # Give every supplier organisation a permanent SBID immediately;
                # vendor portal activation later adds the representative relationship.
                from app.services.identity import IdentityService
                identity = IdentityService(conn)
                party = identity.create_party(
                    party_type="organisation", display_name=row["name"],
                    reason="Supplier master created",
                )
                identity.link_profile(
                    party_id=party["id"], profile_type="vendor_organisation",
                    source_id=row["id"], link_method="admin_verified",
                    reason="Supplier master created",
                )
                if row["email"]:
                    try:
                        identity.add_contact(party_id=party["id"], contact_type="email",
                                             value=row["email"], source="supplier_master")
                    except ValueError:
                        pass
                if row["phone"]:
                    try:
                        identity.add_contact(party_id=party["id"], contact_type="phone",
                                             value=row["phone"], source="supplier_master")
                    except ValueError:
                        pass
                # The supplier is now linked to its canonical organisation identity.
                # Return the SBID immediately so the admin UI can display and retain it.
                row = {**row, "sbid": party["sbid"]}
        return row
    except psycopg.Error as exc:
        raise _db_error(exc) from exc




@router.put("/suppliers/{supplier_id}")
def update_supplier(supplier_id: int, payload: SupplierCreate):
    """Update supplier master data without deleting or replacing the supplier record."""
    try:
        with _connect() as conn:
            with conn.transaction():
                row = conn.execute(
                    "UPDATE suppliers SET name=%s,contact_name=%s,phone=%s,email=%s,gstin=%s,address=%s,updated_at=now() "
                    "WHERE id=%s AND is_active=TRUE "
                    "RETURNING id,name,contact_name,phone,email,gstin,address,is_active,created_at,updated_at",
                    (payload.name, payload.contact_name.strip() if payload.contact_name else None,
                     payload.phone.strip() if payload.phone else None,
                     payload.email.strip().lower() if payload.email else None,
                     payload.gstin, payload.address.strip() if payload.address else None, supplier_id),
                ).fetchone()
                if not row:
                    raise HTTPException(404, "Active supplier not found")
                party = conn.execute(
                    "SELECT iparty.id,iparty.sbid FROM identity_profiles ip "
                    "JOIN identity_parties iparty ON iparty.id=ip.party_id "
                    "WHERE ip.supplier_id=%s AND ip.profile_type='vendor_organisation' "
                    "AND ip.status='active' FOR UPDATE OF iparty",
                    (supplier_id,),
                ).fetchone()
                identity = IdentityService(conn)
                if party:
                    conn.execute(
                        "UPDATE identity_parties SET display_name=%s,updated_at=now() WHERE id=%s",
                        (row["name"], party["id"]),
                    )
                    party_id, sbid = party["id"], party["sbid"]
                else:
                    created = identity.create_party(
                        party_type="organisation", display_name=row["name"],
                        reason="Legacy supplier assigned an identity during an explicit admin edit",
                    )
                    party_id, sbid = created["id"], created["sbid"]
                    identity.link_profile(
                        party_id=party_id, profile_type="vendor_organisation",
                        source_id=supplier_id, link_method="admin_verified",
                        reason="Legacy supplier assigned an identity during an explicit admin edit",
                    )
                for contact_type, value in (("email", row["email"]), ("phone", row["phone"])):
                    if value:
                        try:
                            identity.add_contact(party_id=party_id,contact_type=contact_type,value=value,source="supplier_update")
                        except ValueError:
                            pass
                return {**row, "sbid": sbid}
    except HTTPException:
        raise
    except psycopg.Error as exc:
        raise _db_error(exc) from exc


@router.get("/orders")
def list_purchase_orders(status: str | None = None, limit: int = Query(default=100, ge=1, le=500), offset: int = Query(default=0, ge=0)):
    allowed = {"draft", "ordered", "partially_received", "received", "cancelled"}
    if status and status not in allowed:
        raise HTTPException(422, "Unsupported purchase order status")
    where = " WHERE po.status=%s" if status else ""
    params = [status] if status else []
    try:
        with _connect() as conn:
            rows = conn.execute(
                "SELECT po.id,po.purchase_number,po.supplier_id,s.name AS supplier_name,po.location_id,sl.name AS location_name,po.status,po.subtotal,po.notes,po.created_at,po.updated_at,(SELECT count(*) FROM purchase_order_lines l WHERE l.purchase_order_id=po.id) AS line_count FROM purchase_orders po JOIN suppliers s ON s.id=po.supplier_id JOIN stock_locations sl ON sl.id=po.location_id"
                + where + " ORDER BY po.created_at DESC LIMIT %s OFFSET %s", (*params, limit, offset)
            ).fetchall()
        return {"items": rows, "limit": limit, "offset": offset}
    except psycopg.Error as exc:
        raise _db_error(exc) from exc


@router.get("/orders/{purchase_id}")
def get_purchase_order(purchase_id: int):
    try:
        with _connect() as conn:
            po = conn.execute("SELECT po.id,po.purchase_number,po.supplier_id,s.name AS supplier_name,po.location_id,sl.name AS location_name,po.status,po.subtotal,po.notes,po.created_at,po.updated_at FROM purchase_orders po JOIN suppliers s ON s.id=po.supplier_id JOIN stock_locations sl ON sl.id=po.location_id WHERE po.id=%s", (purchase_id,)).fetchone()
            if not po:
                raise HTTPException(404, "Purchase order not found")
            lines = conn.execute("SELECT l.id AS line_id,l.variant_id,v.sku,p.name AS product_name,l.quantity_ordered,l.quantity_received,l.unit_cost,(l.quantity_ordered-l.quantity_received) AS quantity_open FROM purchase_order_lines l JOIN product_variants v ON v.id=l.variant_id JOIN products p ON p.id=v.product_id WHERE l.purchase_order_id=%s ORDER BY l.id", (purchase_id,)).fetchall()
        return {**po, "lines": lines}
    except HTTPException:
        raise
    except psycopg.Error as exc:
        raise _db_error(exc) from exc


@router.get("/orders/{purchase_id}/receipts")
def list_purchase_receipts(purchase_id: int):
    """Return posted receipt movements grouped by the client receipt identity.

    This is a movement-backed history for the current receipt endpoint, not a
    substitute for a full GRN document with QC and batch provenance.
    """
    try:
        with _connect() as conn:
            po = conn.execute(
                "SELECT id FROM purchase_orders WHERE id=%s",
                (purchase_id,),
            ).fetchone()
            if not po:
                raise HTTPException(404, "Purchase order not found")
            rows = conn.execute(
                "SELECT im.id AS movement_id,im.reference_id,im.variant_id,v.sku,p.name AS product_name,"
                "im.quantity,im.note,im.created_at "
                "FROM inventory_movements im "
                "JOIN purchase_order_lines pol ON pol.purchase_order_id=%s AND pol.variant_id=im.variant_id "
                "JOIN product_variants v ON v.id=im.variant_id "
                "JOIN products p ON p.id=v.product_id "
                "WHERE im.movement_type='receipt' AND im.reference_type='purchase_receipt' "
                "AND im.reference_id LIKE %s "
                "ORDER BY im.created_at DESC,im.id DESC",
                (purchase_id, f"{purchase_id}:%"),
            ).fetchall()
        receipts = {}
        for row in rows:
            key = row["reference_id"]
            receipt = receipts.setdefault(key, {
                "idempotency_key": key.split(":", 1)[1],
                "received_at": row["created_at"],
                "note": row["note"],
                "lines": [],
            })
            receipt["lines"].append({
                "movement_id": row["movement_id"],
                "variant_id": row["variant_id"],
                "sku": row["sku"],
                "product_name": row["product_name"],
                "quantity": row["quantity"],
            })
        return {"purchase_order_id": purchase_id, "items": list(receipts.values())}
    except HTTPException:
        raise
    except psycopg.Error as exc:
        raise _db_error(exc) from exc


@router.post("/orders", status_code=201)
def create_purchase_order(payload: PurchaseCreate, request: Request):
    actor_id = getattr(request.state, "user_id", None)
    if not actor_id or not getattr(request.state, "user_email", None) or not getattr(request.state, "role", None):
        raise HTTPException(401, "A valid staff session is required")
    try:
        with _connect() as conn:
            with conn.transaction():
                supplier = conn.execute("SELECT id FROM suppliers WHERE id=%s AND is_active=TRUE FOR SHARE", (payload.supplier_id,)).fetchone()
                location = conn.execute("SELECT id,establishment_id FROM stock_locations WHERE id=%s AND is_active=TRUE FOR SHARE", (payload.location_id,)).fetchone()
                if not supplier:
                    raise HTTPException(404, "Active supplier not found")
                if not location:
                    raise HTTPException(404, "Active stock location not found")
                ids = [line.variant_id for line in payload.lines]
                found = conn.execute("SELECT id FROM product_variants WHERE id=ANY(%s) AND is_active=TRUE FOR SHARE", (ids,)).fetchall()
                if len(found) != len(ids):
                    raise HTTPException(422, "One or more variants are missing or inactive")
                subtotal = sum((line.quantity * line.unit_cost for line in payload.lines), Decimal("0"))
                number = "PO-" + uuid.uuid4().hex[:12].upper()
                policy_id = None
                if location["establishment_id"] is not None:
                    active = conn.execute(
                        "SELECT id FROM organisation_policy_versions WHERE establishment_id=%s AND domain='purchase' "
                        "AND status='active' AND effective_from<=CURRENT_DATE AND (effective_to IS NULL OR effective_to>=CURRENT_DATE)",
                        (location["establishment_id"],),
                    ).fetchall()
                    if len(active) > 1:
                        raise HTTPException(409, "Multiple active Purchase policies apply; resolve organisation policy configuration")
                    if active:
                        policy_id = active[0]["id"]
                po = conn.execute(
                    "INSERT INTO purchase_orders(purchase_number,supplier_id,location_id,status,subtotal,notes,created_by_user_id,policy_version_id) "
                    "VALUES(%s,%s,%s,'draft',%s,%s,%s,%s) "
                    "RETURNING id,purchase_number,supplier_id,location_id,status,subtotal,notes,created_at,created_by_user_id,policy_version_id",
                    (number,payload.supplier_id,payload.location_id,subtotal,payload.notes,actor_id,policy_id),
                ).fetchone()
                for line in payload.lines:
                    conn.execute("INSERT INTO purchase_order_lines(purchase_order_id,variant_id,quantity_ordered,unit_cost) VALUES(%s,%s,%s,%s)", (po["id"],line.variant_id,line.quantity,line.unit_cost))
        return po
    except HTTPException:
        raise
    except psycopg.Error as exc:
        raise _db_error(exc) from exc




@router.put("/orders/{purchase_id}")
def update_draft_purchase_order(purchase_id: int, payload: PurchaseCreate, request: Request):
    """Edit a draft PO only; each amendment starts a new approval revision."""
    actor_id = getattr(request.state, "user_id", None)
    if not actor_id or not getattr(request.state, "user_email", None) or not getattr(request.state, "role", None):
        raise HTTPException(401, "A valid staff session is required")
    try:
        with _connect() as conn:
            with conn.transaction():
                po = conn.execute(
                    "SELECT id,status FROM purchase_orders WHERE id=%s FOR UPDATE",
                    (purchase_id,),
                ).fetchone()
                if not po:
                    raise HTTPException(404, "Purchase order not found")
                if po["status"] != "draft":
                    raise HTTPException(409, "Only draft purchase orders can be edited")
                supplier = conn.execute(
                    "SELECT id FROM suppliers WHERE id=%s AND is_active=TRUE FOR SHARE",
                    (payload.supplier_id,),
                ).fetchone()
                location = conn.execute(
                    "SELECT id FROM stock_locations WHERE id=%s AND is_active=TRUE FOR SHARE",
                    (payload.location_id,),
                ).fetchone()
                if not supplier:
                    raise HTTPException(404, "Active supplier not found")
                if not location:
                    raise HTTPException(404, "Active stock location not found")
                ids = [line.variant_id for line in payload.lines]
                found = conn.execute(
                    "SELECT id FROM product_variants WHERE id=ANY(%s) AND is_active=TRUE FOR SHARE",
                    (ids,),
                ).fetchall()
                if len(found) != len(ids):
                    raise HTTPException(422, "One or more variants are missing or inactive")
                subtotal = sum((line.quantity * line.unit_cost for line in payload.lines), Decimal("0"))
                conn.execute(
                    "UPDATE purchase_orders SET supplier_id=%s,location_id=%s,subtotal=%s,notes=%s,"
                    "created_by_user_id=%s,approval_revision=approval_revision+1,policy_version_id=NULL,updated_at=now() WHERE id=%s",
                    (payload.supplier_id,payload.location_id,subtotal,payload.notes,actor_id,purchase_id),
                )
                # Draft orders cannot have receipts; replacing their lines is therefore safe.
                conn.execute("DELETE FROM purchase_order_lines WHERE purchase_order_id=%s", (purchase_id,))
                for line in payload.lines:
                    conn.execute(
                        "INSERT INTO purchase_order_lines(purchase_order_id,variant_id,quantity_ordered,unit_cost) VALUES(%s,%s,%s,%s)",
                        (purchase_id,line.variant_id,line.quantity,line.unit_cost),
                    )
                updated = conn.execute(
                    "SELECT id,purchase_number,supplier_id,location_id,status,subtotal,notes,updated_at FROM purchase_orders WHERE id=%s",
                    (purchase_id,),
                ).fetchone()
        return updated
    except HTTPException:
        raise
    except psycopg.Error as exc:
        raise _db_error(exc) from exc


@router.post("/orders/{purchase_id}/receive")
def receive_goods(purchase_id: int, payload: GoodsReceipt, request: Request):
    """Legacy-compatible GRN entry point; receipt is quarantined pending QC.

    Physical receipt updates the PO received quantity but never saleable stock.
    Only the QC endpoint in purchasing_lifecycle.py may release accepted units.
    """
    if not settings.database_url:
        raise HTTPException(503, "Purchasing database is not configured")
    actor_id = getattr(request.state, "user_id", None)
    actor_email = getattr(request.state, "user_email", None)
    if not actor_id or not actor_email:
        raise HTTPException(401, "A valid staff session is required")
    receipt_key = payload.idempotency_key or uuid.uuid4()
    canonical = {
        "note": payload.note,
        "lines": [
            {"line_id": line.line_id, "quantity": str(line.quantity), "batch_code": line.batch_code,
             "manufacture_date": str(line.manufacture_date) if line.manufacture_date else None,
             "expiry_date": str(line.expiry_date) if line.expiry_date else None}
            for line in sorted(payload.lines, key=lambda item: item.line_id)
        ],
    }
    payload_hash = hashlib.sha256(json.dumps(canonical, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    try:
        with _connect() as conn:
            with conn.transaction():
                po = conn.execute(
                    "SELECT id,supplier_id,location_id,status FROM purchase_orders WHERE id=%s FOR UPDATE",
                    (purchase_id,),
                ).fetchone()
                if not po:
                    raise HTTPException(404, "Purchase order not found")
                existing = conn.execute(
                    "SELECT id,grn_number,payload_hash,status,received_at FROM goods_receipts "
                    "WHERE purchase_order_id=%s AND idempotency_key=%s",
                    (purchase_id, receipt_key),
                ).fetchone()
                if existing:
                    if existing["payload_hash"] != payload_hash:
                        raise HTTPException(409, "Receipt idempotency key was already used with a different payload")
                    return {"purchase_order_id": purchase_id, **existing, "replayed": True, "inventory_posted": False}
                if po["status"] not in {"ordered", "partially_received"}:
                    raise HTTPException(409, "Purchase order cannot receive goods in its current status")
                ids = [line.line_id for line in payload.lines]
                if len(ids) != len(set(ids)):
                    raise HTTPException(422, "Each purchase line can be received once per receipt")
                rows = conn.execute(
                    "SELECT id,variant_id,quantity_ordered,quantity_received,unit_cost "
                    "FROM purchase_order_lines WHERE purchase_order_id=%s AND id=ANY(%s) FOR UPDATE",
                    (purchase_id, ids),
                ).fetchall()
                by_id = {int(row["id"]): row for row in rows}
                if len(by_id) != len(ids):
                    raise HTTPException(422, "A receipt line does not belong to this purchase order")
                for line in payload.lines:
                    row = by_id[line.line_id]
                    if line.quantity > row["quantity_ordered"] - row["quantity_received"]:
                        raise HTTPException(409, "Receipt quantity exceeds the outstanding purchase quantity")
                    if line.manufacture_date and line.expiry_date and line.expiry_date < line.manufacture_date:
                        raise HTTPException(422, "Expiry date cannot precede manufacture date")
                    if line.batch_code is not None and not line.batch_code.strip():
                        raise HTTPException(422, "Batch code cannot be blank")
                grn_number = "GRN-" + uuid.uuid4().hex[:12].upper()
                grn = conn.execute(
                    "INSERT INTO goods_receipts(grn_number,purchase_order_id,supplier_id,location_id,idempotency_key,payload_hash,received_by_user_id,received_by_email,note,status) "
                    "VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,'qc_pending') "
                    "RETURNING id,grn_number,payload_hash,status,received_at",
                    (grn_number,purchase_id,po["supplier_id"],po["location_id"],receipt_key,payload_hash,
                     actor_id,actor_email,payload.note),
                ).fetchone()
                for line in payload.lines:
                    row = by_id[line.line_id]
                    conn.execute(
                        "INSERT INTO goods_receipt_lines(goods_receipt_id,purchase_order_line_id,variant_id,received_quantity,batch_code,manufacture_date,expiry_date,unit_cost) "
                        "VALUES(%s,%s,%s,%s,%s,%s,%s,%s)",
                        (grn["id"],line.line_id,row["variant_id"],line.quantity,line.batch_code,
                         line.manufacture_date,line.expiry_date,row["unit_cost"]),
                    )
                    conn.execute(
                        "UPDATE purchase_order_lines SET quantity_received=quantity_received+%s WHERE id=%s",
                        (line.quantity,line.line_id),
                    )
                open_lines = conn.execute(
                    "SELECT count(*) AS n FROM purchase_order_lines WHERE purchase_order_id=%s AND quantity_received<quantity_ordered",
                    (purchase_id,),
                ).fetchone()["n"]
                po_status = "received" if open_lines == 0 else "partially_received"
                conn.execute("UPDATE purchase_orders SET status=%s,updated_at=now() WHERE id=%s", (po_status,purchase_id))
        return {
            "purchase_order_id": purchase_id, **grn, "status": po_status,
            "grn_status": grn["status"], "purchase_order_status": po_status,
            "received_line_count": len(payload.lines), "replayed": False,
            "inventory_posted": False, "message": "GRN recorded; received stock is unavailable until QC acceptance.",
        }
    except HTTPException:
        raise
    except psycopg.Error as exc:
        raise _db_error(exc) from exc


@router.post("/orders/{purchase_id}/cancel")
def cancel_purchase_order(purchase_id: int):
    """Cancel the unreceived remainder of an order; already received stock is not reversed."""
    try:
        with _connect() as conn:
            with conn.transaction():
                po = conn.execute(
                    "SELECT id, status FROM purchase_orders WHERE id = %s FOR UPDATE",
                    (purchase_id,),
                ).fetchone()
                if po is None:
                    raise HTTPException(404, "Purchase order not found")
                if po["status"] not in {"ordered", "partially_received"}:
                    raise HTTPException(409, "Only ordered or partially received purchase orders can be cancelled")
                row = conn.execute(
                    "UPDATE purchase_orders SET status = 'cancelled', updated_at = now() "
                    "WHERE id = %s RETURNING id, purchase_number, status, updated_at",
                    (purchase_id,),
                ).fetchone()
        return {
            **row,
            "message": "Remaining quantities cancelled. Previously received inventory remains unchanged.",
        }
    except HTTPException:
        raise
    except psycopg.Error as exc:
        raise _db_error(exc) from exc



@router.post("/orders/{purchase_id}/approve")
def approve_purchase_order(purchase_id: int, request: Request):
    """Approve a draft PO and record the authenticated decision in the same transaction."""
    actor_id = getattr(request.state, "user_id", None)
    actor_email = getattr(request.state, "user_email", None)
    actor_role = getattr(request.state, "role", None)
    if not actor_id or not actor_email or not actor_role:
        raise HTTPException(401, "A valid staff session is required")
    try:
        with _connect() as conn:
            with conn.transaction():
                po = conn.execute(
                    "SELECT p.id,p.purchase_number,p.status,p.subtotal,p.created_by_user_id,p.approval_revision,"
                    "p.policy_version_id,l.establishment_id FROM purchase_orders p "
                    "JOIN stock_locations l ON l.id=p.location_id WHERE p.id=%s FOR UPDATE OF p",
                    (purchase_id,),
                ).fetchone()
                if po is None:
                    raise HTTPException(404, "Purchase order not found")
                if po["status"] != "draft":
                    raise HTTPException(409, "Only draft purchase orders can be approved")
                if po["created_by_user_id"] is None:
                    raise HTTPException(409, "This legacy purchase order has no recorded creator; amend the draft to establish its approval owner before approval")
                if int(po["created_by_user_id"]) == int(actor_id):
                    raise HTTPException(403, "The purchase-order creator cannot approve their own revision")
                if po["establishment_id"] is None:
                    raise HTTPException(409, "Assign this stock location to an active establishment before approving its purchase order")
                policy = None
                if po["policy_version_id"] is not None:
                    policy = conn.execute(
                        "SELECT * FROM organisation_policy_versions WHERE id=%s AND establishment_id=%s "
                        "AND domain='purchase' FOR SHARE",
                        (po["policy_version_id"],po["establishment_id"]),
                    ).fetchone()
                if policy is None:
                    policy = load_active_policy(conn,int(po["establishment_id"]),"purchase")
                evaluation = evaluate_purchase_policy(policy["policy_config"],Decimal(str(po["subtotal"])))
                completed = conn.execute(
                    "SELECT stage_sequence FROM organisation_policy_decisions WHERE domain='purchase' "
                    "AND document_type='purchase_order' AND document_id=%s AND document_revision=%s "
                    "AND decision='approved' ORDER BY stage_sequence",
                    (purchase_id,po["approval_revision"]),
                ).fetchall()
                completed_sequences = {int(item["stage_sequence"]) for item in completed}
                next_stage = next((stage for stage in evaluation["stages"] if int(stage["sequence"]) not in completed_sequences),None)
                if next_stage is None:
                    raise HTTPException(409, "This purchase-order revision already has all required approvals")
                if actor_role not in next_stage["approver_roles"]:
                    raise HTTPException(403, "Your role is not authorised for the next configured Purchase approval stage")
                conn.execute(
                    "INSERT INTO organisation_policy_decisions "
                    "(policy_version_id,establishment_id,domain,document_type,document_id,document_revision,"
                    "stage_sequence,decision,actor_user_id,actor_email,actor_role,reason,evaluation_snapshot) "
                    "VALUES(%s,%s,'purchase','purchase_order',%s,%s,%s,'approved',%s,%s,%s,%s,%s::jsonb)",
                    (policy["id"],po["establishment_id"],purchase_id,po["approval_revision"],next_stage["sequence"],
                     actor_id,actor_email,actor_role,"Purchase order approval",json.dumps(evaluation,default=str)),
                )
                conn.execute(
                    "INSERT INTO purchasing_approval_events "
                    "(document_type,document_id,action,actor_user_id,actor_email,actor_role,reason) "
                    "VALUES('purchase_order',%s,'approved',%s,%s,%s,%s)",
                    (purchase_id,actor_id,actor_email,actor_role,f"Purchase order approval stage {next_stage['sequence']}"),
                )
                conn.execute(
                    "UPDATE purchase_orders SET policy_version_id=%s,updated_at=now() WHERE id=%s",
                    (policy["id"],purchase_id),
                )
                all_sequences = {int(stage["sequence"]) for stage in evaluation["stages"]}
                if all_sequences.issubset(completed_sequences | {int(next_stage["sequence"])}):
                    row = conn.execute(
                        "UPDATE purchase_orders SET status='ordered',updated_at=now() "
                        "WHERE id=%s RETURNING id,purchase_number,status,updated_at",
                        (purchase_id,),
                    ).fetchone()
                    message = "All configured Purchase approval stages are complete; purchase order is released."
                else:
                    row = conn.execute(
                        "SELECT id,purchase_number,status,updated_at FROM purchase_orders WHERE id=%s",
                        (purchase_id,),
                    ).fetchone()
                    message = f"Approval stage {next_stage['sequence']} recorded; additional configured approval is required."
        return {**row,"message":message,"approved_stage":next_stage["sequence"],
                "required_stages":len(evaluation["stages"]),"policy_version_id":policy["id"]}
    except HTTPException:
        raise
    except psycopg.Error as exc:
        raise _db_error(exc) from exc
