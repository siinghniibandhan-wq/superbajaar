"""Order management API foundation. Requires database/migrations/002_orders.sql to be applied."""
from decimal import Decimal
import json
import re

import psycopg
from fastapi import APIRouter, HTTPException, Query
from psycopg.rows import dict_row
from pydantic import BaseModel, Field, field_validator

from app.core.config import settings

router = APIRouter(prefix="/orders", tags=["orders"])
ORDER_STATUSES = {"draft", "placed", "confirmed", "processing", "ready_for_dispatch", "dispatched", "delivered", "cancelled"}
CHANNELS = {"website", "pos", "manual"}


def _connect():
    if not settings.database_url:
        raise HTTPException(status_code=503, detail="Orders database is not configured")
    try:
        return psycopg.connect(settings.database_url, row_factory=dict_row)
    except psycopg.Error as exc:
        raise HTTPException(status_code=503, detail="Orders database is unavailable") from exc


def _db_error(exc: psycopg.Error):
    if getattr(exc, "sqlstate", None) == "23505":
        return HTTPException(status_code=409, detail="Order reference already exists")
    if getattr(exc, "sqlstate", None) == "23503":
        return HTTPException(status_code=422, detail="Referenced customer, product or variant does not exist")
    return HTTPException(status_code=503, detail="Order storage is unavailable; verify the orders migration")


class OrderLineCreate(BaseModel):
    variant_id: int = Field(gt=0)
    quantity: int = Field(gt=0, le=100000)


class OrderCreate(BaseModel):
    channel: str = "manual"
    customer_name: str = Field(min_length=1, max_length=200)
    customer_phone: str | None = Field(default=None, max_length=20)
    delivery_pin: str | None = Field(default=None, pattern=r"^[0-9]{6}$")
    notes: str | None = Field(default=None, max_length=2000)
    lines: list[OrderLineCreate] = Field(min_length=1, max_length=100)

    @field_validator("channel")
    @classmethod
    def valid_channel(cls, value):
        if value not in CHANNELS:
            raise ValueError("Channel must be website, pos or manual")
        return value

    @field_validator("customer_name")
    @classmethod
    def name_not_blank(cls, value):
        if not value.strip():
            raise ValueError("Customer name cannot be blank")
        return value.strip()

    @field_validator("lines")
    @classmethod
    def variants_must_be_unique(cls, value):
        variant_ids = [line.variant_id for line in value]
        if len(variant_ids) != len(set(variant_ids)):
            raise ValueError("Each product variant can appear only once per order; combine quantities on its line")
        return value


class OrderStatusUpdate(BaseModel):
    status: str

    @field_validator("status")
    @classmethod
    def valid_status(cls, value):
        if value not in ORDER_STATUSES:
            raise ValueError("Unsupported order status")
        return value


@router.get("")
def list_orders(
    status: str | None = Query(default=None),
    channel: str | None = Query(default=None, pattern=r"^(website|pos|manual)$"),
    search: str | None = Query(default=None, max_length=200),
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
):
    if status and status not in ORDER_STATUSES:
        raise HTTPException(status_code=422, detail="Unsupported order status")
    clauses, params = [], []
    if status:
        clauses.append("o.status = %s"); params.append(status)
    if channel:
        clauses.append("o.channel = %s"); params.append(channel)
    if search and search.strip():
        term = "%" + search.strip() + "%"
        clauses.append("(o.order_number ILIKE %s OR o.customer_name ILIKE %s OR COALESCE(o.customer_phone, '') ILIKE %s OR COALESCE(o.delivery_pin, '') ILIKE %s)")
        params.extend([term, term, term, term])
    where = (" WHERE " + " AND ".join(clauses)) if clauses else ""
    try:
        with _connect() as conn:
            items = conn.execute(
                "SELECT o.id, o.order_number, o.channel, o.customer_name, o.customer_phone, o.delivery_pin, "
                "o.status, o.subtotal, o.total, o.notes, o.created_at, o.updated_at, "
                "(SELECT count(*) FROM order_lines l WHERE l.order_id=o.id) AS line_count "
                "FROM orders o" + where + " ORDER BY o.created_at DESC LIMIT %s OFFSET %s",
                (*params, limit, offset),
            ).fetchall()
            count = conn.execute("SELECT count(*) AS total FROM orders o" + where, params).fetchone()["total"]
        return {"items": items, "total": count, "limit": limit, "offset": offset}
    except psycopg.Error as exc:
        raise _db_error(exc) from exc


@router.get("/summary")
def order_summary():
    try:
        with _connect() as conn:
            rows = conn.execute(
                "SELECT status, count(*) AS order_count, COALESCE(sum(total), 0) AS order_value "
                "FROM orders GROUP BY status ORDER BY status"
            ).fetchall()
        return {"items": rows}
    except psycopg.Error as exc:
        raise _db_error(exc) from exc


@router.get("/{order_id}")
def get_order(order_id: int):
    try:
        with _connect() as conn:
            order = conn.execute(
                "SELECT id, order_number, channel, customer_name, customer_phone, delivery_pin, status, subtotal, total, notes, created_at, updated_at FROM orders WHERE id=%s",
                (order_id,),
            ).fetchone()
            if order is None:
                raise HTTPException(status_code=404, detail="Order not found")
            lines = conn.execute(
                "SELECT l.id, l.variant_id, v.sku, p.name AS product_name, l.quantity, l.unit_price, l.line_total "
                "FROM order_lines l JOIN product_variants v ON v.id=l.variant_id JOIN products p ON p.id=v.product_id "
                "WHERE l.order_id=%s ORDER BY l.id", (order_id,)
            ).fetchall()
        return {**order, "lines": lines}
    except HTTPException:
        raise
    except psycopg.Error as exc:
        raise _db_error(exc) from exc


@router.post("", status_code=201)
def create_order(payload: OrderCreate):
    try:
        with _connect() as conn:
            with conn.transaction():
                variant_ids = list(dict.fromkeys(line.variant_id for line in payload.lines))
                variants = conn.execute(
                    "SELECT id, sku, selling_price FROM product_variants WHERE id = ANY(%s) AND is_active=TRUE FOR SHARE",
                    (variant_ids,),
                ).fetchall()
                by_id = {int(row["id"]): row for row in variants}
                missing = set(variant_ids) - set(by_id)
                if missing:
                    raise HTTPException(status_code=422, detail="One or more variants are missing or inactive")
                subtotal = sum((Decimal(str(by_id[line.variant_id]["selling_price"])) * line.quantity for line in payload.lines), Decimal("0"))
                order_number = "SB-" + __import__("uuid").uuid4().hex[:12].upper()
                order = conn.execute(
                    "INSERT INTO orders (order_number, channel, customer_name, customer_phone, delivery_pin, status, subtotal, total, notes) "
                    "VALUES (%s,%s,%s,%s,%s,'placed',%s,%s,%s) "
                    "RETURNING id, order_number, channel, customer_name, customer_phone, delivery_pin, status, subtotal, total, notes, created_at, updated_at",
                    (order_number, payload.channel, payload.customer_name, payload.customer_phone, payload.delivery_pin, subtotal, subtotal, payload.notes),
                ).fetchone()
                for line in payload.lines:
                    unit_price = Decimal(str(by_id[line.variant_id]["selling_price"]))
                    conn.execute(
                        "INSERT INTO order_lines (order_id, variant_id, quantity, unit_price, line_total) VALUES (%s,%s,%s,%s,%s)",
                        (order["id"], line.variant_id, line.quantity, unit_price, unit_price * line.quantity),
                    )
        return order
    except HTTPException:
        raise
    except psycopg.Error as exc:
        raise _db_error(exc) from exc


@router.patch("/{order_id}/status")
def update_order_status(order_id: int, payload: OrderStatusUpdate):
    allowed = {
        "draft": {"placed", "cancelled"},
        "placed": {"confirmed", "cancelled"},
        "confirmed": {"processing", "cancelled"},
        "processing": {"ready_for_dispatch", "cancelled"},
        "ready_for_dispatch": {"dispatched", "cancelled"},
        "dispatched": {"delivered"},
        "delivered": set(),
        "cancelled": set(),
    }
    try:
        with _connect() as conn:
            with conn.transaction():
                current = conn.execute("SELECT status FROM orders WHERE id=%s FOR UPDATE", (order_id,)).fetchone()
                if current is None:
                    raise HTTPException(status_code=404, detail="Order not found")
                old = current["status"]
                if payload.status == old:
                    return {"id": order_id, "status": old}
                if payload.status not in allowed[old]:
                    raise HTTPException(status_code=409, detail=f"Cannot change order status from {old} to {payload.status}")
                row = conn.execute(
                    "UPDATE orders SET status=%s, updated_at=now() WHERE id=%s RETURNING id, order_number, status, updated_at",
                    (payload.status, order_id),
                ).fetchone()
                conn.execute(
                    "INSERT INTO order_status_history (order_id, from_status, to_status) VALUES (%s,%s,%s)",
                    (order_id, old, payload.status),
                )
        return row
    except HTTPException:
        raise
    except psycopg.Error as exc:
        raise _db_error(exc) from exc
