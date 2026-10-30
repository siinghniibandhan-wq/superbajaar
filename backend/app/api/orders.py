"""Order management API foundation. Requires database/migrations/002_orders.sql to be applied."""
from decimal import Decimal
import json
import secrets
import re

import psycopg
from fastapi import APIRouter, HTTPException, Query, Request
from psycopg.rows import dict_row
from pydantic import BaseModel, EmailStr, Field, field_validator

from app.core.config import settings
from app.services.order_inventory import dispatch_order_stock, ensure_order_can_be_cancelled, order_fulfilment_started, release_order_stock, reserve_order_stock

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
    customer_email: EmailStr | None = None
    delivery_pin: str | None = Field(default=None, pattern=r"^[0-9]{6}$")
    location_id: int | None = Field(default=None, gt=0)
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
def create_order(payload: OrderCreate, request: Request):
    if payload.channel == "pos" and payload.location_id is None:
        raise HTTPException(status_code=422, detail="POS orders require the staff-selected stock location")
    if payload.channel in {"website", "manual"} and not payload.delivery_pin:
        raise HTTPException(status_code=422, detail="Website and manual orders require a verified six-digit delivery PIN before stock can be reserved")
    if payload.channel in {"website", "manual"} and payload.location_id is not None:
        raise HTTPException(status_code=422, detail="Website and manual orders must use the server-selected eligible stock location")
    if getattr(request.state, "customer_checkout", False):
        if payload.channel != "website":
            raise HTTPException(status_code=403, detail="Customer accounts can only create website orders")
        if not payload.customer_email or str(payload.customer_email).strip().lower() != str(request.state.customer_email).strip().lower():
            raise HTTPException(status_code=403, detail="Order email must match the signed-in customer account")
    elif getattr(request.state, "role", None) == "customer":
        raise HTTPException(status_code=403, detail="Customer sign-in is required to place a website order")
    if getattr(request.state, "role", None) == "staff" and payload.channel == "manual":
        raise HTTPException(status_code=403, detail="Staff cannot create manual orders")
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
                    "INSERT INTO orders (order_number, channel, customer_name, customer_phone, customer_email, delivery_pin, status, subtotal, total, notes) "
                    "VALUES (%s,%s,%s,%s,%s,%s,'placed',%s,%s,%s) "
                    "RETURNING id, order_number, channel, customer_name, customer_phone, customer_email, delivery_pin, status, subtotal, total, notes, created_at, updated_at",
                    (order_number, payload.channel, payload.customer_name, payload.customer_phone, str(payload.customer_email).lower() if payload.customer_email else None, payload.delivery_pin, subtotal, subtotal, payload.notes),
                ).fetchone()
                for line in payload.lines:
                    unit_price = Decimal(str(by_id[line.variant_id]["selling_price"]))
                    conn.execute(
                        "INSERT INTO order_lines (order_id, variant_id, quantity, unit_price, line_total) VALUES (%s,%s,%s,%s,%s)",
                        (order["id"], line.variant_id, line.quantity, unit_price, unit_price * line.quantity),
                    )
                try:
                    inventory_location_id = reserve_order_stock(
                        conn, order["id"], payload.delivery_pin,
                        [(line.variant_id, line.quantity) for line in payload.lines],
                        location_id=payload.location_id,
                    )
                except ValueError as exc:
                    raise HTTPException(status_code=409, detail=str(exc)) from exc
        return {**order, "inventory_location_id": inventory_location_id, "stock_reserved": inventory_location_id is not None}
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
                current = conn.execute("SELECT status, customer_email, order_number FROM orders WHERE id=%s FOR UPDATE", (order_id,)).fetchone()
                if current is None:
                    raise HTTPException(status_code=404, detail="Order not found")
                old = current["status"]
                if payload.status == old:
                    return {"id": order_id, "status": old}
                if payload.status not in allowed[old]:
                    raise HTTPException(status_code=409, detail=f"Cannot change order status from {old} to {payload.status}")
                if payload.status == "cancelled":
                    try:
                        ensure_order_can_be_cancelled(conn, order_id)
                        release_order_stock(conn, order_id)
                    except ValueError as exc:
                        raise HTTPException(status_code=409, detail=str(exc)) from exc
                elif payload.status == "dispatched":
                    try:
                        dispatched_lines = dispatch_order_stock(conn, order_id)
                        if dispatched_lines == 0 and not order_fulfilment_started(conn, order_id):
                            raise ValueError("No outstanding stock reservation exists for this order")
                    except ValueError as exc:
                        raise HTTPException(status_code=409, detail=str(exc)) from exc
                row = conn.execute(
                    "UPDATE orders SET status=%s, updated_at=now() WHERE id=%s RETURNING id, order_number, status, updated_at",
                    (payload.status, order_id),
                ).fetchone()
                conn.execute(
                    "INSERT INTO order_status_history (order_id, from_status, to_status) VALUES (%s,%s,%s)",
                    (order_id, old, payload.status),
                )
                # Credit coins only once, in the transaction that marks an order delivered.
                # Older orders without a customer email are skipped rather than guessing identity.
                if payload.status == "delivered" and current.get("customer_email"):
                    email = str(current["customer_email"]).strip().lower()
                    card_number = "SB-" + secrets.token_hex(5).upper()
                    conn.execute(
                        "INSERT INTO loyalty_accounts (customer_email, card_number) VALUES (%s,%s) "
                        "ON CONFLICT (customer_email) DO NOTHING",
                        (email, card_number),
                    )
                    account = conn.execute(
                        "SELECT id FROM loyalty_accounts WHERE customer_email=%s FOR UPDATE", (email,)
                    ).fetchone()
                    lines = conn.execute(
                        "SELECT ol.id AS line_id, ol.line_total, p.id AS product_id, p.category_id "
                        "FROM order_lines ol JOIN product_variants v ON v.id=ol.variant_id "
                        "JOIN products p ON p.id=v.product_id WHERE ol.order_id=%s ORDER BY ol.id",
                        (order_id,),
                    ).fetchall()
                    for line in lines:
                        rule = conn.execute(
                            "SELECT coins_per_100 FROM loyalty_rules WHERE scope_type='product' AND scope_id=%s AND is_active=TRUE",
                            (line["product_id"],),
                        ).fetchone()
                        if rule is None and line["category_id"] is not None:
                            rule = conn.execute(
                                "SELECT coins_per_100 FROM loyalty_rules WHERE scope_type='category' AND scope_id=%s AND is_active=TRUE",
                                (line["category_id"],),
                            ).fetchone()
                        if rule is None:
                            rule = conn.execute(
                                "SELECT coins_per_100 FROM loyalty_rules WHERE scope_type='default' AND scope_id IS NULL AND is_active=TRUE"
                            ).fetchone()
                        rate = Decimal(str(rule["coins_per_100"])) if rule else Decimal("1")
                        coins = int((Decimal(str(line["line_total"])) / Decimal("100") * rate).to_integral_value(rounding="ROUND_FLOOR"))
                        if coins > 0:
                            conn.execute(
                                "INSERT INTO loyalty_transactions (account_id, transaction_type, coins, order_reference, description, expires_at, idempotency_key) "
                                "VALUES (%s,'earn',%s,%s,%s,now() + interval '365 days',%s) ON CONFLICT (idempotency_key) DO NOTHING",
                                (account["id"], coins, current["order_number"], "Delivered order reward", f"earn:order:{order_id}:line:{line['line_id']}"),
                            )

                    # Referral rewards are issued only when the referred customer's
                    # first order reaches delivered. The status update and both coin
                    # credits share this transaction, so retries cannot double-credit.
                    referral = conn.execute(
                        "UPDATE customer_referrals r SET status='rewarded', reward_coins=100, "
                        "reward_trigger='first_order_delivered', updated_at=now() "
                        "FROM customer_accounts referred "
                        "WHERE r.referred_customer_id=referred.id AND lower(referred.email)=%s "
                        "AND r.status IN ('tracked','eligible') "
                        "RETURNING r.id, r.referrer_customer_id",
                        (email,),
                    ).fetchone()
                    if referral:
                        referrer = conn.execute(
                            "SELECT email FROM customer_accounts WHERE id=%s",
                            (referral["referrer_customer_id"],),
                        ).fetchone()
                        if referrer:
                            for beneficiary_email, reward_key, description in (
                                (email, f"referral:{referral['id']}:referred", "Super Bajaar referral reward"),
                                (str(referrer["email"]).strip().lower(), f"referral:{referral['id']}:referrer", "Super Bajaar referral reward"),
                            ):
                                referral_card = "SB-" + secrets.token_hex(5).upper()
                                conn.execute(
                                    "INSERT INTO loyalty_accounts (customer_email, card_number) VALUES (%s,%s) "
                                    "ON CONFLICT (customer_email) DO NOTHING",
                                    (beneficiary_email, referral_card),
                                )
                                referral_account = conn.execute(
                                    "SELECT id FROM loyalty_accounts WHERE customer_email=%s FOR UPDATE",
                                    (beneficiary_email,),
                                ).fetchone()
                                conn.execute(
                                    "INSERT INTO loyalty_transactions "
                                    "(account_id, transaction_type, coins, order_reference, description, expires_at, idempotency_key) "
                                    "VALUES (%s,'earn',100,%s,%s,now() + interval '365 days',%s) "
                                    "ON CONFLICT (idempotency_key) DO NOTHING",
                                    (referral_account["id"], current["order_number"], description, reward_key),
                                )
        return row
    except HTTPException:
        raise
    except psycopg.Error as exc:
        raise _db_error(exc) from exc



@router.get("/{order_id}/history")
def order_status_history(
    order_id: int,
    limit: int = Query(default=100, ge=1, le=500),
):
    """Return recorded status transitions for an order, newest first."""
    try:
        with _connect() as conn:
            order = conn.execute(
                "SELECT id, order_number FROM orders WHERE id = %s",
                (order_id,),
            ).fetchone()
            if order is None:
                raise HTTPException(status_code=404, detail="Order not found")
            rows = conn.execute(
                "SELECT id, from_status, to_status, changed_at "
                "FROM order_status_history WHERE order_id = %s "
                "ORDER BY changed_at DESC, id DESC LIMIT %s",
                (order_id, limit),
            ).fetchall()
        return {"order_id": order_id, "order_number": order["order_number"], "items": rows}
    except HTTPException:
        raise
    except psycopg.Error as exc:
        raise _db_error(exc) from exc
