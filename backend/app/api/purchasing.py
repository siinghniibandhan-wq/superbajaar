"""Supplier, purchase order and goods receipt API.
Requires database/migrations/006_purchasing.sql and the catalogue/inventory schema.
"""
from decimal import Decimal
import uuid

import psycopg
from fastapi import APIRouter, HTTPException, Query
from psycopg.rows import dict_row
from pydantic import BaseModel, Field, field_validator

from app.core.config import settings

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
    return HTTPException(503, "Purchasing storage unavailable; verify migration 006")


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


class GoodsReceipt(BaseModel):
    lines: list[ReceiveLine] = Field(min_length=1, max_length=200)
    note: str | None = Field(default=None, max_length=500)


@router.get("/suppliers")
def list_suppliers(search: str | None = Query(default=None, max_length=200), limit: int = Query(default=100, ge=1, le=500), offset: int = Query(default=0, ge=0)):
    clauses = ["is_active=TRUE"]
    params = []
    if search and search.strip():
        term = "%" + search.strip() + "%"
        clauses.append("(name ILIKE %s OR COALESCE(phone,'') ILIKE %s OR COALESCE(gstin,'') ILIKE %s)")
        params.extend([term, term, term])
    where = " WHERE " + " AND ".join(clauses)
    try:
        with _connect() as conn:
            items = conn.execute("SELECT id,name,contact_name,phone,email,gstin,address,is_active,created_at FROM suppliers" + where + " ORDER BY name LIMIT %s OFFSET %s", (*params, limit, offset)).fetchall()
            total = conn.execute("SELECT count(*) AS total FROM suppliers" + where, params).fetchone()["total"]
        return {"items": items, "total": total, "limit": limit, "offset": offset}
    except psycopg.Error as exc:
        raise _db_error(exc) from exc


@router.post("/suppliers", status_code=201)
def create_supplier(payload: SupplierCreate):
    try:
        with _connect() as conn:
            row = conn.execute(
                "INSERT INTO suppliers(name,contact_name,phone,email,gstin,address) VALUES(%s,%s,%s,%s,%s,%s) RETURNING id,name,contact_name,phone,email,gstin,address,is_active,created_at",
                (payload.name, payload.contact_name.strip() if payload.contact_name else None, payload.phone.strip() if payload.phone else None, payload.email.strip().lower() if payload.email else None, payload.gstin, payload.address.strip() if payload.address else None),
            ).fetchone()
        return row
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


@router.post("/orders", status_code=201)
def create_purchase_order(payload: PurchaseCreate):
    try:
        with _connect() as conn:
            with conn.transaction():
                supplier = conn.execute("SELECT id FROM suppliers WHERE id=%s AND is_active=TRUE FOR SHARE", (payload.supplier_id,)).fetchone()
                location = conn.execute("SELECT id FROM stock_locations WHERE id=%s AND is_active=TRUE FOR SHARE", (payload.location_id,)).fetchone()
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
                po = conn.execute("INSERT INTO purchase_orders(purchase_number,supplier_id,location_id,status,subtotal,notes) VALUES(%s,%s,%s,'ordered',%s,%s) RETURNING id,purchase_number,supplier_id,location_id,status,subtotal,notes,created_at", (number,payload.supplier_id,payload.location_id,subtotal,payload.notes)).fetchone()
                for line in payload.lines:
                    conn.execute("INSERT INTO purchase_order_lines(purchase_order_id,variant_id,quantity_ordered,unit_cost) VALUES(%s,%s,%s,%s)", (po["id"],line.variant_id,line.quantity,line.unit_cost))
        return po
    except HTTPException:
        raise
    except psycopg.Error as exc:
        raise _db_error(exc) from exc


@router.post("/orders/{purchase_id}/receive")
def receive_goods(purchase_id: int, payload: GoodsReceipt):
    try:
        with _connect() as conn:
            with conn.transaction():
                po = conn.execute("SELECT id,location_id,status FROM purchase_orders WHERE id=%s FOR UPDATE", (purchase_id,)).fetchone()
                if not po:
                    raise HTTPException(404, "Purchase order not found")
                if po["status"] in {"draft", "cancelled", "received"}:
                    raise HTTPException(409, "Purchase order cannot receive goods in its current status")
                ids = [line.line_id for line in payload.lines]
                if len(ids) != len(set(ids)):
                    raise HTTPException(422, "Each purchase line can be received once per receipt")
                rows = conn.execute("SELECT id,variant_id,quantity_ordered,quantity_received,unit_cost FROM purchase_order_lines WHERE purchase_order_id=%s AND id=ANY(%s) FOR UPDATE", (purchase_id, ids)).fetchall()
                by_id = {int(row["id"]): row for row in rows}
                if len(by_id) != len(ids):
                    raise HTTPException(422, "A receipt line does not belong to this purchase order")
                for line in payload.lines:
                    row = by_id[line.line_id]
                    if line.quantity > row["quantity_ordered"] - row["quantity_received"]:
                        raise HTTPException(409, "Receipt quantity exceeds the outstanding purchase quantity")
                for line in payload.lines:
                    row = by_id[line.line_id]
                    conn.execute("UPDATE purchase_order_lines SET quantity_received=quantity_received+%s WHERE id=%s", (line.quantity,line.line_id))
                    conn.execute("INSERT INTO inventory_balances(variant_id,location_id,on_hand,reserved) VALUES(%s,%s,%s,0) ON CONFLICT(variant_id,location_id) DO UPDATE SET on_hand=inventory_balances.on_hand+EXCLUDED.on_hand,updated_at=now()", (row["variant_id"],po["location_id"],line.quantity))
                    conn.execute("INSERT INTO inventory_movements(variant_id,location_id,movement_type,quantity,reference_type,reference_id,note) VALUES(%s,%s,'receipt',%s,'purchase_order',%s,%s)", (row["variant_id"],po["location_id"],line.quantity,str(purchase_id),payload.note))
                remaining = conn.execute("SELECT count(*) AS open_lines FROM purchase_order_lines WHERE purchase_order_id=%s AND quantity_received<quantity_ordered", (purchase_id,)).fetchone()["open_lines"]
                status = "received" if remaining == 0 else "partially_received"
                conn.execute("UPDATE purchase_orders SET status=%s,updated_at=now() WHERE id=%s", (status,purchase_id))
        return {"purchase_order_id": purchase_id, "status": status, "received_line_count": len(payload.lines)}
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
