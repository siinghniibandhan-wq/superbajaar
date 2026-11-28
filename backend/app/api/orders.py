"""Order management API foundation. Requires database/migrations/002_orders.sql to be applied."""
from decimal import Decimal
from datetime import datetime
import json
import secrets
import re
import hashlib
import uuid

import psycopg
from fastapi import APIRouter, HTTPException, Query, Request
from psycopg.rows import dict_row
from pydantic import BaseModel, EmailStr, Field, field_validator

from app.core.config import settings
from app.services.order_inventory import ensure_order_can_be_cancelled, order_has_reservation, release_order_stock, reserve_order_stock
from app.services.loyalty_redemption import COIN_VALIDITY_DAYS, redeem_for_order, restore_order_redemption
from app.services.loyalty_accounting import post_earning_accrual
from app.services.pos_tender import checkout_payload_for_hash, validate_pos_tender
from app.services.serviceability import blocked_product_ids, eligible_locations, lookup_pin
from app.services.indian_gst import calculate_indian_gst_inclusive
from app.services.promotions import calculate_promotion_discount

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


def _lock_checkout_idempotency_key(conn, key: str) -> None:
    """Serialize concurrent requests that carry the same checkout key.

    The transaction-scoped advisory lock avoids the read-then-insert race where
    two retries both observe no prior order and one loses at the unique index.
    """
    conn.execute(
        "SELECT pg_advisory_xact_lock(hashtextextended(%s, 0))",
        (key,),
    )


def _enforce_regional_availability(conn, delivery_pin: str, variant_ids: list[int], delivery_type: str) -> None:
    """Website checkout guard: the region must be served, products must be sold there, express must be offered."""
    info = lookup_pin(conn, delivery_pin)
    standard = eligible_locations(conn, delivery_pin, False, info)
    if not standard:
        raise HTTPException(status_code=409, detail="Sorry, Super Bajaar isn't available in your region yet.")
    products = conn.execute(
        "SELECT DISTINCT p.id, p.name, p.delivery_options FROM product_variants v "
        "JOIN products p ON p.id=v.product_id WHERE v.id = ANY(%s)", (variant_ids,),
    ).fetchall()
    blocked = blocked_product_ids(conn, delivery_pin, info, standard, "website", [int(row["id"]) for row in products])
    if blocked:
        names = ", ".join(sorted(str(row["name"]) for row in products if int(row["id"]) in blocked))
        raise HTTPException(status_code=422, detail="Not available in your area: " + names + ". Please remove these items to continue.")
    if delivery_type == "express":
        no_express = [str(row["name"]) for row in products if "express" not in (row["delivery_options"] or [])]
        if no_express:
            raise HTTPException(status_code=422, detail="Express delivery is not offered for: " + ", ".join(sorted(no_express)))
        if not eligible_locations(conn, delivery_pin, True, info):
            raise HTTPException(status_code=422, detail="Express delivery is not available in your area yet. Please choose standard delivery.")




GST_STATE_CODES = {
    "JAMMU AND KASHMIR":"01","HIMACHAL PRADESH":"02","PUNJAB":"03","CHANDIGARH":"04",
    "UTTARAKHAND":"05","HARYANA":"06","DELHI":"07","RAJASTHAN":"08","UTTAR PRADESH":"09",
    "BIHAR":"10","SIKKIM":"11","ARUNACHAL PRADESH":"12","NAGALAND":"13","MANIPUR":"14",
    "MIZORAM":"15","TRIPURA":"16","MEGHALAYA":"17","ASSAM":"18","WEST BENGAL":"19",
    "JHARKHAND":"20","ODISHA":"21","CHHATTISGARH":"22","MADHYA PRADESH":"23","GUJARAT":"24",
    "DAMAN AND DIU":"25","DADRA AND NAGAR HAVELI AND DAMAN AND DIU":"26","MAHARASHTRA":"27",
    "ANDHRA PRADESH":"37","KARNATAKA":"29","GOA":"30","LAKSHADWEEP":"31","KERALA":"32",
    "TAMIL NADU":"33","PUDUCHERRY":"34","ANDAMAN AND NICOBAR ISLANDS":"35","TELANGANA":"36",
    "LADAKH":"38","OTHER TERRITORY":"97"
}


def _apply_order_gst(conn, order_id: int, *, delivery_pin: str | None, discount_total: Decimal):
    """Persist GST-inclusive tax snapshots; prices remain the customer-payable gross prices."""
    gstin = str(settings.company_gstin or "").strip().upper()
    if not gstin:
        return Decimal("0.00"), None
    if len(gstin) != 15 or not gstin[:2].isdigit() or not gstin.isalnum():
        raise HTTPException(status_code=503, detail="COMPANY_GSTIN must be a valid 15-character GST registration")
    origin_state_code = gstin[:2]
    destination_state_code = origin_state_code
    destination_state = None
    if delivery_pin:
        pin_info = lookup_pin(conn, delivery_pin)
        if not pin_info or not pin_info.get("state"):
            raise HTTPException(status_code=422, detail="Unable to determine destination state for GST; verify the delivery PIN")
        destination_state = str(pin_info["state"]).strip()
        destination_state_code = GST_STATE_CODES.get(destination_state.upper(), "")
        if not destination_state_code:
            raise HTTPException(status_code=422, detail="Destination state is not mapped for GST; contact support")
    supply_type = "intra_state" if destination_state_code == origin_state_code else "inter_state"
    lines = conn.execute(
        """SELECT ol.id,ol.quantity,ol.line_total,p.id AS product_id,p.category_id,
                  p.tax_code,p.tax_rate,p.name,
                  rule.hsn_code AS rule_hsn_code,rule.gst_rate AS rule_gst_rate
           FROM order_lines ol
           JOIN product_variants v ON v.id=ol.variant_id
           JOIN products p ON p.id=v.product_id
           LEFT JOIN LATERAL (
               SELECT h.hsn_code,h.gst_rate FROM hsn_rules h
               WHERE h.is_active=TRUE AND h.category_id=p.category_id AND h.conditions='{}'::jsonb
               ORDER BY h.updated_at DESC,h.id DESC LIMIT 1
           ) rule ON TRUE
           WHERE ol.order_id=%s ORDER BY ol.id FOR UPDATE OF ol""",
        (order_id,),
    ).fetchall()
    gross_total = sum((Decimal(str(line["line_total"])) for line in lines), Decimal("0.00"))
    remaining_discount = Decimal(str(discount_total or 0)).quantize(Decimal("0.01"))
    tax_total = Decimal("0.00")
    for index, line in enumerate(lines):
        gross = Decimal(str(line["line_total"]))
        if index == len(lines) - 1:
            line_discount = remaining_discount
        elif gross_total > 0:
            line_discount = (Decimal(str(discount_total or 0)) * gross / gross_total).quantize(Decimal("0.01"))
        else:
            line_discount = Decimal("0.00")
        line_discount = min(max(line_discount, Decimal("0.00")), gross)
        remaining_discount -= line_discount
        discounted_gross = gross - line_discount
        hsn_code = line["tax_code"] or line["rule_hsn_code"]
        rate_value = line["tax_rate"] if line["tax_rate"] is not None else line["rule_gst_rate"]
        if rate_value is None or not hsn_code:
            raise HTTPException(status_code=422, detail=f"GST/HSN mapping is missing for {line['name']}; configure its product tax code or category HSN rule")
        try:
            tax = calculate_indian_gst_inclusive(
                gross_value=discounted_gross, gst_rate=rate_value,
                supply_type=supply_type, hsn_code=str(hsn_code),
            )
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=f"Invalid GST/HSN mapping for {line['name']}: {exc}") from exc
        conn.execute(
            """UPDATE order_lines SET hsn_code=%s,gst_rate=%s,taxable_value=%s,
                      cgst_rate=%s,sgst_rate=%s,igst_rate=%s,cgst_amount=%s,
                      sgst_amount=%s,igst_amount=%s,tax_total=%s
               WHERE id=%s""",
            (tax["hsn_code"],tax["gst_rate"],tax["taxable_value"],
             tax["cgst_rate"],tax["sgst_rate"],tax["igst_rate"],
             tax["cgst_amount"],tax["sgst_amount"],tax["igst_amount"],
             tax["total_tax"],line["id"]),
        )
        tax_total += tax["total_tax"]
    tax_total = tax_total.quantize(Decimal("0.01"))
    conn.execute(
        "UPDATE orders SET tax_total=%s,place_of_supply_state=%s WHERE id=%s",
        (tax_total,destination_state or origin_state_code,order_id),
    )
    return tax_total, destination_state or origin_state_code

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
    delivery_type: str | None = Field(default=None, pattern=r"^(standard|express)$")
    notes: str | None = Field(default=None, max_length=2000)
    redeem_coins: int = Field(default=0, ge=0, le=10000000)
    checkout_idempotency_key: str = Field(min_length=16, max_length=100)
    pos_payment_method: str | None = None
    pos_register_id: int | None = Field(default=None, gt=0)
    coupon_code: str | None = Field(default=None, max_length=40)
    lines: list[OrderLineCreate] = Field(min_length=1, max_length=100)

    @field_validator("coupon_code")
    @classmethod
    def normalize_coupon_code(cls, value):
        if value is None:
            return None
        code = value.strip().upper()
        if not code or not re.fullmatch(r"[A-Z0-9][A-Z0-9_-]{1,39}", code):
            raise ValueError("Coupon code must contain 2-40 letters, numbers, hyphens or underscores")
        return code

    @field_validator("checkout_idempotency_key")
    @classmethod
    def valid_checkout_idempotency_key(cls, value):
        if not re.fullmatch(r"[A-Za-z0-9._:-]{16,100}", value or ""):
            raise ValueError("A valid checkout_idempotency_key is required for every order")
        return value

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


class PromotionCreate(BaseModel):
    code: str = Field(min_length=2, max_length=40)
    name: str = Field(min_length=2, max_length=160)
    discount_type: str = Field(pattern=r"^(percent|fixed)$")
    discount_value: Decimal = Field(gt=0, max_digits=14, decimal_places=2)
    minimum_subtotal: Decimal = Field(default=0, ge=0, max_digits=14, decimal_places=2)
    maximum_discount: Decimal | None = Field(default=None, gt=0, max_digits=14, decimal_places=2)
    usage_limit: int | None = Field(default=None, gt=0)
    per_customer_limit: int | None = Field(default=None, gt=0)
    starts_at: datetime | None = None
    ends_at: datetime | None = None
    is_active: bool = True

    @field_validator("code")
    @classmethod
    def clean_code(cls, value):
        code = value.strip().upper()
        if not re.fullmatch(r"[A-Z0-9][A-Z0-9_-]{1,39}", code):
            raise ValueError("Promotion code must be 2-40 letters, numbers, hyphens or underscores")
        return code

    @field_validator("name")
    @classmethod
    def clean_name(cls, value):
        if not value.strip():
            raise ValueError("Promotion name cannot be blank")
        return value.strip()

    @field_validator("discount_value")
    @classmethod
    def validate_value(cls, value, info):
        if info.data.get("discount_type") == "percent" and value > 100:
            raise ValueError("Percentage discount cannot exceed 100")
        return value

    @field_validator("maximum_discount")
    @classmethod
    def max_discount_only_for_percentage(cls, value, info):
        if value is not None and info.data.get("discount_type") != "percent":
            raise ValueError("Maximum discount cap is only valid for percentage promotions")
        return value

    @field_validator("ends_at")
    @classmethod
    def valid_window(cls, value, info):
        starts = info.data.get("starts_at")
        if starts is not None and value is not None and value <= starts:
            raise ValueError("Promotion end must be after start")
        return value


class PromotionUpdate(PromotionCreate):
    pass


def _require_promotion_admin(request: Request):
    if getattr(request.state, "role", "") not in {"super_admin", "admin"}:
        raise HTTPException(status_code=403, detail="Administrator access required")


@router.get("/promotions/quote")
def promotion_quote(code: str = Query(min_length=2, max_length=40), subtotal: Decimal = Query(gt=0)):
    """Non-reserving quote. Checkout recalculates and enforces all usage limits in its transaction."""
    normalized = code.strip().upper()
    try:
        with _connect() as conn:
            promo = conn.execute(
                "SELECT * FROM promotions WHERE upper(code)=upper(%s) AND is_active=TRUE",
                (normalized,),
            ).fetchone()
            if promo is None:
                raise HTTPException(status_code=404, detail="Coupon code is invalid or inactive")
            now = conn.execute("SELECT now() AS current_time").fetchone()["current_time"]
            if promo["starts_at"] and promo["starts_at"] > now:
                raise HTTPException(status_code=422, detail="Coupon is not active yet")
            if promo["ends_at"] and promo["ends_at"] <= now:
                raise HTTPException(status_code=422, detail="Coupon has expired")
            used = conn.execute("SELECT count(*) AS n FROM promotion_redemptions WHERE promotion_id=%s",(promo["id"],)).fetchone()["n"]
            if promo["usage_limit"] is not None and used >= promo["usage_limit"]:
                raise HTTPException(status_code=409, detail="Coupon redemption limit has been reached")
            try:
                amount = calculate_promotion_discount(
                    subtotal=subtotal, discount_type=promo["discount_type"], discount_value=promo["discount_value"],
                    minimum_subtotal=promo["minimum_subtotal"], maximum_discount=promo["maximum_discount"],
                )
            except ValueError as exc:
                raise HTTPException(status_code=422, detail=str(exc)) from exc
            return {"code":promo["code"],"name":promo["name"],"discount_amount":amount,"subtotal":subtotal,"payable":subtotal-amount}
    except HTTPException:
        raise
    except psycopg.Error as exc:
        raise _db_error(exc) from exc


@router.get("/promotions")
def list_promotions(request: Request, include_inactive: bool = False):
    _require_promotion_admin(request)
    try:
        with _connect() as conn:
            rows = conn.execute(
                "SELECT p.*, (SELECT count(*) FROM promotion_redemptions r WHERE r.promotion_id=p.id) AS redeemed_count "
                "FROM promotions p WHERE (%s OR p.is_active=TRUE) ORDER BY p.created_at DESC",
                (include_inactive,),
            ).fetchall()
        return {"items":rows}
    except psycopg.Error as exc:
        raise _db_error(exc) from exc


@router.post("/promotions", status_code=201)
def create_promotion(payload: PromotionCreate, request: Request):
    _require_promotion_admin(request)
    try:
        with _connect() as conn:
            row = conn.execute(
                "INSERT INTO promotions(code,name,discount_type,discount_value,minimum_subtotal,maximum_discount,usage_limit,per_customer_limit,starts_at,ends_at,is_active,created_by_user_id) "
                "VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING *",
                (payload.code,payload.name,payload.discount_type,payload.discount_value,payload.minimum_subtotal,payload.maximum_discount,
                 payload.usage_limit,payload.per_customer_limit,payload.starts_at,payload.ends_at,payload.is_active,getattr(request.state,"user_id",None)),
            ).fetchone()
        return row
    except psycopg.Error as exc:
        if getattr(exc,"sqlstate",None)=="23505":
            raise HTTPException(status_code=409,detail="Promotion code already exists") from exc
        raise _db_error(exc) from exc


@router.patch("/promotions/{promotion_id}")
def update_promotion(promotion_id: int, payload: PromotionUpdate, request: Request):
    _require_promotion_admin(request)
    try:
        with _connect() as conn:
            with conn.transaction():
                current = conn.execute("SELECT id FROM promotions WHERE id=%s FOR UPDATE",(promotion_id,)).fetchone()
                if current is None:
                    raise HTTPException(status_code=404,detail="Promotion not found")
                row = conn.execute(
                    "UPDATE promotions SET code=%s,name=%s,discount_type=%s,discount_value=%s,minimum_subtotal=%s,maximum_discount=%s,usage_limit=%s,per_customer_limit=%s,starts_at=%s,ends_at=%s,is_active=%s,updated_at=now() WHERE id=%s RETURNING *",
                    (payload.code,payload.name,payload.discount_type,payload.discount_value,payload.minimum_subtotal,payload.maximum_discount,
                     payload.usage_limit,payload.per_customer_limit,payload.starts_at,payload.ends_at,payload.is_active,promotion_id),
                ).fetchone()
        return row
    except HTTPException:
        raise
    except psycopg.Error as exc:
        if getattr(exc,"sqlstate",None)=="23505":
            raise HTTPException(status_code=409,detail="Promotion code already exists") from exc
        raise _db_error(exc) from exc


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
                "SELECT o.id, o.order_number, o.channel, o.customer_name, o.customer_phone, o.delivery_pin, o.delivery_type, "
                "o.status, o.subtotal, o.total, o.notes, o.created_at, o.updated_at, "
                "assigned_location.id AS inventory_location_id, assigned_location.name AS inventory_location_name, "
                "(SELECT count(*) FROM order_lines l WHERE l.order_id=o.id) AS line_count "
                "FROM orders o LEFT JOIN stock_locations assigned_location ON assigned_location.id=COALESCE("
                "(SELECT d.location_id FROM deliveries d WHERE d.order_id=o.id ORDER BY d.id DESC LIMIT 1),"
                "(SELECT im.location_id FROM inventory_movements im WHERE im.reference_id=o.id::text "
                "AND im.reference_type='order_reservation' AND im.movement_type='reservation' ORDER BY im.id DESC LIMIT 1))"
                + where + " ORDER BY o.created_at DESC LIMIT %s OFFSET %s",
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
                "SELECT o.id, o.order_number, o.channel, o.customer_name, o.customer_phone, o.delivery_pin, o.delivery_type, "
                "o.status, o.subtotal, o.total, o.notes, o.created_at, o.updated_at, "
                "assigned_location.id AS inventory_location_id, assigned_location.name AS inventory_location_name "
                "FROM orders o LEFT JOIN stock_locations assigned_location ON assigned_location.id=COALESCE("
                "(SELECT d.location_id FROM deliveries d WHERE d.order_id=o.id ORDER BY d.id DESC LIMIT 1),"
                "(SELECT im.location_id FROM inventory_movements im WHERE im.reference_id=o.id::text "
                "AND im.reference_type='order_reservation' AND im.movement_type='reservation' ORDER BY im.id DESC LIMIT 1)) "
                "WHERE o.id=%s",
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
    try:
        validate_pos_tender(
            channel=payload.channel, method=payload.pos_payment_method,
            checkout_idempotency_key=payload.checkout_idempotency_key,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    if payload.redeem_coins and payload.channel != "website":
        raise HTTPException(status_code=422, detail="Super Coins can only be redeemed during website checkout")
    if payload.redeem_coins and not getattr(request.state, "customer_checkout", False):
        raise HTTPException(status_code=403, detail="Super Coins redemption requires an authenticated customer checkout")
    if payload.redeem_coins and not payload.checkout_idempotency_key:
        raise HTTPException(status_code=422, detail="A checkout_idempotency_key is required when redeeming Super Coins")
    if payload.channel == "pos" and payload.location_id is None:
        raise HTTPException(status_code=422, detail="POS orders require the staff-selected stock location")
    if payload.channel == "pos" and payload.pos_register_id is None:
        raise HTTPException(status_code=422, detail="POS orders require an active register selection")
    if payload.channel != "pos" and payload.pos_register_id is not None:
        raise HTTPException(status_code=422, detail="A POS register can only be attached to POS orders")
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
                if payload.checkout_idempotency_key:
                    _lock_checkout_idempotency_key(conn, payload.checkout_idempotency_key)
                hash_payload = checkout_payload_for_hash(payload.model_dump(mode="json"))
                payload_hash = hashlib.sha256(
                    json.dumps(hash_payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
                ).hexdigest()
                if payload.checkout_idempotency_key:
                    prior = conn.execute(
                        "SELECT id,order_number,channel,customer_name,customer_phone,customer_email,delivery_pin,status,subtotal,total,discount_total,promotion_code,notes,checkout_payload_hash "
                        "FROM orders WHERE checkout_idempotency_key=%s FOR UPDATE",
                        (payload.checkout_idempotency_key,),
                    ).fetchone()
                    if prior:
                        if str(prior.get("customer_email") or "").lower() != str(payload.customer_email or "").lower() or prior.get("checkout_payload_hash") != payload_hash:
                            raise HTTPException(status_code=409, detail="Checkout idempotency key was already used with a different order payload")
                        existing_payment = None
                        if payload.pos_payment_method:
                            existing_payment = conn.execute(
                                "SELECT id,payment_reference,order_id,method,amount,status,provider_reference,note,created_at,updated_at "
                                "FROM payments WHERE order_id=%s ORDER BY created_at,id LIMIT 1",
                                (prior["id"],),
                            ).fetchone()
                            if existing_payment is None:
                                raise HTTPException(status_code=409, detail="POS order exists without its atomic tender record; reconcile before retrying")
                        return {**prior, "payment": existing_payment,
                                "inventory_location_id": None, "stock_reserved": order_has_reservation(conn, int(prior["id"])),
                                "idempotent_replay": True}
                variant_ids = list(dict.fromkeys(line.variant_id for line in payload.lines))
                variants = conn.execute(
                    "SELECT id, sku, selling_price FROM product_variants WHERE id = ANY(%s) AND is_active=TRUE FOR SHARE",
                    (variant_ids,),
                ).fetchall()
                by_id = {int(row["id"]): row for row in variants}
                missing = set(variant_ids) - set(by_id)
                if missing:
                    raise HTTPException(status_code=422, detail="One or more variants are missing or inactive")
                delivery_type = payload.delivery_type or "standard"
                if payload.channel == "website":
                    _enforce_regional_availability(conn, payload.delivery_pin, variant_ids, delivery_type)
                subtotal = sum((Decimal(str(by_id[line.variant_id]["selling_price"])) * line.quantity for line in payload.lines), Decimal("0"))
                promotion = None
                promotion_discount = Decimal("0.00")
                if payload.coupon_code:
                    promotion = conn.execute(
                        "SELECT * FROM promotions WHERE upper(code)=upper(%s) FOR UPDATE",
                        (payload.coupon_code,),
                    ).fetchone()
                    if promotion is None or not promotion["is_active"]:
                        raise HTTPException(status_code=422, detail="Coupon code is invalid or inactive")
                    if promotion["starts_at"] and promotion["starts_at"] > conn.execute("SELECT now() AS current_time").fetchone()["current_time"]:
                        raise HTTPException(status_code=422, detail="Coupon is not active yet")
                    if promotion["ends_at"] and promotion["ends_at"] <= conn.execute("SELECT now() AS current_time").fetchone()["current_time"]:
                        raise HTTPException(status_code=422, detail="Coupon has expired")
                    redeemed_count = conn.execute(
                        "SELECT count(*) AS n FROM promotion_redemptions WHERE promotion_id=%s",
                        (promotion["id"],),
                    ).fetchone()["n"]
                    if promotion["usage_limit"] is not None and redeemed_count >= promotion["usage_limit"]:
                        raise HTTPException(status_code=409, detail="Coupon redemption limit has been reached")
                    customer_identifier = str(payload.customer_email or "").strip().lower() or str(payload.customer_phone or "").strip()
                    if promotion["per_customer_limit"] is not None:
                        if not customer_identifier:
                            raise HTTPException(status_code=422, detail="This coupon requires customer details to enforce its per-customer limit")
                        customer_redemptions = conn.execute(
                            "SELECT count(*) AS n FROM promotion_redemptions WHERE promotion_id=%s "
                            "AND (lower(COALESCE(customer_email,''))=%s OR (COALESCE(customer_email,'')='' AND customer_phone=%s))",
                            (promotion["id"], customer_identifier if payload.customer_email else "", customer_identifier if payload.customer_phone and not payload.customer_email else ""),
                        ).fetchone()["n"]
                        if customer_redemptions >= promotion["per_customer_limit"]:
                            raise HTTPException(status_code=409, detail="This customer has already used the coupon the allowed number of times")
                    try:
                        promotion_discount = calculate_promotion_discount(
                            subtotal=subtotal, discount_type=promotion["discount_type"],
                            discount_value=promotion["discount_value"], minimum_subtotal=promotion["minimum_subtotal"],
                            maximum_discount=promotion["maximum_discount"],
                        )
                    except ValueError as exc:
                        raise HTTPException(status_code=422, detail=str(exc)) from exc
                pos_shift_id = None
                if payload.channel == "pos":
                    actor_id = getattr(request.state, "user_id", None)
                    if not actor_id:
                        raise HTTPException(status_code=403, detail="POS checkout requires an authenticated cashier account")
                    active_shift = conn.execute(
                        "SELECT s.id FROM pos_register_shifts s JOIN pos_registers r ON r.id=s.register_id "
                        "WHERE s.register_id=%s AND s.cashier_user_id=%s AND s.status='open' AND r.location_id=%s AND r.is_active=TRUE FOR UPDATE OF s",
                        (payload.pos_register_id, actor_id, payload.location_id),
                    ).fetchone()
                    if active_shift is None:
                        raise HTTPException(status_code=409, detail="Open a cashier shift on this register before creating a POS sale")
                    pos_shift_id = active_shift["id"]
                order_number = "SB-" + __import__("uuid").uuid4().hex[:12].upper()
                order = conn.execute(
                    "INSERT INTO orders (order_number, channel, customer_name, customer_phone, customer_email, delivery_pin, delivery_type, status, subtotal, total, discount_total, promotion_code, notes, checkout_idempotency_key, checkout_payload_hash, pos_register_shift_id) "
                    "VALUES (%s,%s,%s,%s,%s,%s,%s,'placed',%s,%s,%s,%s,%s,%s,%s,%s) "
                    "RETURNING id, order_number, channel, customer_name, customer_phone, customer_email, delivery_pin, delivery_type, status, subtotal, total, discount_total, promotion_code, notes, created_at, updated_at",
                    (order_number, payload.channel, payload.customer_name, payload.customer_phone, str(payload.customer_email).lower() if payload.customer_email else None, payload.delivery_pin, delivery_type, subtotal, subtotal-promotion_discount, promotion_discount, promotion["code"] if promotion else None, payload.notes, payload.checkout_idempotency_key, payload_hash, pos_shift_id),
                ).fetchone()
                for line in payload.lines:
                    unit_price = Decimal(str(by_id[line.variant_id]["selling_price"]))
                    conn.execute(
                        "INSERT INTO order_lines (order_id, variant_id, quantity, unit_price, line_total) VALUES (%s,%s,%s,%s,%s)",
                        (order["id"], line.variant_id, line.quantity, unit_price, unit_price * line.quantity),
                    )
                if promotion:
                    conn.execute(
                        "INSERT INTO promotion_redemptions (promotion_id,order_id,customer_email,customer_phone,subtotal,discount_amount,code_snapshot) "
                        "VALUES (%s,%s,%s,%s,%s,%s,%s)",
                        (promotion["id"], order["id"], str(payload.customer_email).lower() if payload.customer_email else None,
                         payload.customer_phone, subtotal, promotion_discount, promotion["code"]),
                    )
                loyalty_discount = Decimal("0.00")
                redeemed_coins = 0
                if payload.redeem_coins:
                    redemption = redeem_for_order(
                        conn,
                        customer_email=str(payload.customer_email).strip().lower(),
                        order_id=int(order["id"]),
                        order_reference=order["order_number"],
                        payable_amount=subtotal-promotion_discount,
                        requested_coins=payload.redeem_coins,
                    )
                    loyalty_discount = redemption["discount_amount"]
                    redeemed_coins = redemption["coins"]
                    order = conn.execute(
                        "UPDATE orders SET total=%s,discount_total=%s WHERE id=%s RETURNING id,order_number,channel,customer_name,customer_phone,customer_email,delivery_pin,status,subtotal,total,discount_total,promotion_code,notes,created_at,updated_at",
                        (subtotal - promotion_discount - loyalty_discount, promotion_discount + loyalty_discount, order["id"]),
                    ).fetchone()
                try:
                    inventory_location_id = reserve_order_stock(
                        conn, order["id"], payload.delivery_pin,
                        [(line.variant_id, line.quantity) for line in payload.lines],
                        location_id=payload.location_id,
                        profile_routing=payload.channel == "website",
                        express=delivery_type == "express",
                    )
                except ValueError as exc:
                    raise HTTPException(status_code=409, detail=str(exc)) from exc
                tax_total, place_of_supply_state = _apply_order_gst(
                    conn, int(order["id"]), delivery_pin=payload.delivery_pin,
                    discount_total=promotion_discount + loyalty_discount,
                )
                order["tax_total"] = tax_total
                order["place_of_supply_state"] = place_of_supply_state
                order["tax_lines"] = conn.execute(
                    """SELECT ol.id,ol.hsn_code,ol.gst_rate,ol.taxable_value,ol.cgst_rate,
                              ol.sgst_rate,ol.igst_rate,ol.cgst_amount,ol.sgst_amount,
                              ol.igst_amount,ol.tax_total
                       FROM order_lines ol WHERE ol.order_id=%s ORDER BY ol.id""",
                    (order["id"],),
                ).fetchall()
                payment = None
                if payload.pos_payment_method:
                    payment_reference = "PAY-" + uuid.uuid4().hex[:12].upper()
                    payment = conn.execute(
                        "INSERT INTO payments(payment_reference,order_id,method,amount,status,note) "
                        "VALUES(%s,%s,%s,%s,'pending',%s) "
                        "RETURNING id,payment_reference,order_id,method,amount,status,provider_reference,note,created_at,updated_at",
                        (payment_reference, order["id"], payload.pos_payment_method, order["total"],
                         "POS tender intent created atomically with order; awaiting cashier or provider confirmation"),
                    ).fetchone()
        return {**order, "payment": payment, "promotion_discount": promotion_discount, "loyalty_discount": loyalty_discount, "redeemed_coins": redeemed_coins,
                "inventory_location_id": inventory_location_id, "stock_reserved": inventory_location_id is not None}
    except HTTPException:
        raise
    except psycopg.Error as exc:
        raise _db_error(exc) from exc


@router.patch("/{order_id}/status")
def update_order_status(order_id: int, payload: OrderStatusUpdate, request: Request):
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
                current = conn.execute("SELECT status, customer_email, customer_name, order_number FROM orders WHERE id=%s FOR UPDATE", (order_id,)).fetchone()
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
                        restore_order_redemption(conn, order_id=order_id, reason="Restored after eligible pre-dispatch cancellation")
                    except ValueError as exc:
                        raise HTTPException(status_code=409, detail=str(exc)) from exc
                elif payload.status == "delivered":
                    shipment = conn.execute(
                        "SELECT status FROM deliveries WHERE order_id=%s "
                        "AND status NOT IN ('delivered','cancelled') ORDER BY id DESC LIMIT 1 FOR SHARE",
                        (order_id,),
                    ).fetchone()
                    if shipment:
                        raise HTTPException(
                            status_code=409,
                            detail="Complete or resolve the linked shipment in Delivery before marking this order delivered",
                        )
                    if order_has_reservation(conn, order_id):
                        raise HTTPException(status_code=409, detail="Cannot mark order delivered while stock reservations remain undispatched")
                elif payload.status == "dispatched":
                    raise HTTPException(
                        status_code=409,
                        detail="Physical stock dispatch is controlled by the linked Delivery shipment; dispatch it from the Fulfilment workspace",
                    )
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
                            earned = conn.execute(
                                "INSERT INTO loyalty_transactions (account_id, transaction_type, coins, order_reference, description, expires_at, idempotency_key) "
                                "VALUES (%s,'earn',%s,%s,%s,now() + make_interval(days => %s),%s) ON CONFLICT (idempotency_key) DO NOTHING RETURNING id",
                                (account["id"], coins, current["order_number"], "Delivered order reward", COIN_VALIDITY_DAYS, f"earn:order:{order_id}:line:{line['line_id']}"),
                            ).fetchone()
                            if earned:
                                post_earning_accrual(conn, int(earned["id"]))

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
                                earned = conn.execute(
                                    "INSERT INTO loyalty_transactions "
                                    "(account_id, transaction_type, coins, order_reference, description, expires_at, idempotency_key) "
                                    "VALUES (%s,'earn',100,%s,%s,now() + make_interval(days => %s),%s) "
                                    "ON CONFLICT (idempotency_key) DO NOTHING RETURNING id",
                                    (referral_account["id"], current["order_number"], description, COIN_VALIDITY_DAYS, reward_key),
                                ).fetchone()
                                if earned:
                                    post_earning_accrual(conn, int(earned["id"]))
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
