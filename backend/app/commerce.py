"""Commerce APIs for checkout, customer order history, and persisted storefront settings.

These tables are isolated from the catalogue and are initialized lazily. No Odoo
sync, product import, or payment-provider simulation is performed here.
"""
import json
import re
import secrets
from datetime import date
from decimal import Decimal, ROUND_DOWN
from typing import Any

import psycopg
from fastapi import APIRouter, Header, HTTPException, Query
from pydantic import BaseModel, Field
from psycopg.rows import dict_row

from .auth import _current, _require, _db

router = APIRouter(prefix="/api", tags=["commerce"])


def _ensure_commerce_schema(conn: Any) -> None:
    conn.execute("""
        CREATE TABLE IF NOT EXISTS store_settings (
            setting_key TEXT PRIMARY KEY,
            setting_value JSONB NOT NULL,
            updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_by BIGINT
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS store_orders (
            id BIGSERIAL PRIMARY KEY,
            order_number TEXT NOT NULL UNIQUE,
            user_id BIGINT NOT NULL REFERENCES app_users(id),
            status TEXT NOT NULL DEFAULT 'placed'
                CHECK (status IN ('placed','confirmed','processing','packed','shipped','delivered','cancelled')),
            payment_method TEXT NOT NULL CHECK (payment_method IN ('cash_on_delivery')),
            payment_status TEXT NOT NULL DEFAULT 'pending'
                CHECK (payment_status IN ('pending','paid','failed','refunded')),
            currency TEXT NOT NULL DEFAULT 'INR',
            subtotal NUMERIC(12,2) NOT NULL CHECK (subtotal >= 0),
            shipping_fee NUMERIC(12,2) NOT NULL DEFAULT 0 CHECK (shipping_fee >= 0),
            total NUMERIC(12,2) NOT NULL CHECK (total >= 0),
            shipping_address JSONB NOT NULL,
            customer_note TEXT NOT NULL DEFAULT '',
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS store_orders_user_created_idx ON store_orders(user_id, created_at DESC)")
    conn.execute("CREATE INDEX IF NOT EXISTS store_orders_status_created_idx ON store_orders(status, created_at DESC)")
    conn.execute("ALTER TABLE store_orders ADD COLUMN IF NOT EXISTS loyalty_discount NUMERIC(12,2) NOT NULL DEFAULT 0")
    conn.execute("ALTER TABLE store_orders ADD COLUMN IF NOT EXISTS loyalty_coins_redeemed BIGINT NOT NULL DEFAULT 0")
    conn.execute("""
        CREATE TABLE IF NOT EXISTS store_order_items (
            id BIGSERIAL PRIMARY KEY,
            order_id BIGINT NOT NULL REFERENCES store_orders(id) ON DELETE CASCADE,
            variant_id BIGINT NOT NULL,
            product_id BIGINT NOT NULL,
            sku TEXT,
            product_name TEXT NOT NULL,
            quantity INTEGER NOT NULL CHECK (quantity BETWEEN 1 AND 50),
            unit_price NUMERIC(12,2) NOT NULL CHECK (unit_price >= 0),
            line_total NUMERIC(12,2) NOT NULL CHECK (line_total >= 0)
        )
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS store_order_items_order_idx ON store_order_items(order_id)")


class CheckoutItem(BaseModel):
    variant_id: int = Field(gt=0)
    quantity: int = Field(ge=1, le=50)


class ShippingAddress(BaseModel):
    full_name: str = Field(min_length=2, max_length=120)
    phone: str = Field(min_length=10, max_length=20)
    address_line1: str = Field(min_length=3, max_length=240)
    address_line2: str = Field(default="", max_length=240)
    city: str = Field(min_length=2, max_length=100)
    state: str = Field(min_length=2, max_length=100)
    pincode: str = Field(pattern=r"^[0-9]{6}$")
    landmark: str = Field(default="", max_length=120)


class CheckoutInput(BaseModel):
    items: list[CheckoutItem] = Field(min_length=1, max_length=100)
    shipping_address: ShippingAddress
    payment_method: str = "cash_on_delivery"
    customer_note: str = Field(default="", max_length=500)
    super_coins_to_redeem: int = Field(default=0, ge=0, le=10000000)


class SettingUpdate(BaseModel):
    value: dict[str, Any]


class OrderStatusUpdate(BaseModel):
    status: str


def _validated_delivery_setting(value: dict[str, Any]) -> dict[str, Any]:
    """Validate the explicit delivery contract stored in the existing settings table."""
    if not value:
        return {}
    allowed = {"enabled", "serviceable_pincodes", "shipping_fee", "free_shipping_threshold", "message"}
    unknown = set(value) - allowed
    if unknown:
        raise HTTPException(status_code=422, detail="Unsupported delivery setting fields: " + ", ".join(sorted(unknown)))
    if not isinstance(value.get("enabled"), bool):
        raise HTTPException(status_code=422, detail="Delivery settings require an enabled boolean.")
    pins = value.get("serviceable_pincodes", [])
    if not isinstance(pins, list) or any(not isinstance(pin, str) or not re.fullmatch(r"[0-9]{6}", pin.strip()) for pin in pins):
        raise HTTPException(status_code=422, detail="Serviceable pincodes must be a list of six-digit strings.")
    pins = list(dict.fromkeys(pin.strip() for pin in pins))
    if value["enabled"] and not pins:
        raise HTTPException(status_code=422, detail="Add verified serviceable pincodes before enabling delivery.")
    if value["enabled"] and "shipping_fee" not in value:
        raise HTTPException(status_code=422, detail="Set an explicit shipping_fee before enabling delivery.")

    def amount(field: str, default: Any = None) -> float | None:
        raw = value.get(field, default)
        if raw is None:
            return None
        if isinstance(raw, bool) or not isinstance(raw, (int, float)):
            raise HTTPException(status_code=422, detail=f"{field} must be a non-negative number.")
        try:
            number = Decimal(str(raw))
        except Exception as exc:
            raise HTTPException(status_code=422, detail=f"{field} must be a valid amount.") from exc
        if not number.is_finite() or number < 0 or number > Decimal("9999999999.99"):
            raise HTTPException(status_code=422, detail=f"{field} must be a valid non-negative amount.")
        try:
            rounded = number.quantize(Decimal("0.01"))
        except Exception as exc:
            raise HTTPException(status_code=422, detail=f"{field} is outside the supported amount range.") from exc
        if rounded != number:
            raise HTTPException(status_code=422, detail=f"{field} must have at most two decimal places.")
        return float(number)

    fee = amount("shipping_fee", 0)
    threshold = amount("free_shipping_threshold")
    message = value.get("message", "")
    if not isinstance(message, str) or len(message) > 240:
        raise HTTPException(status_code=422, detail="Delivery message must be text up to 240 characters.")
    return {
        "enabled": value["enabled"],
        "serviceable_pincodes": pins,
        "shipping_fee": fee,
        "free_shipping_threshold": threshold,
        "message": message.strip(),
    }


def _delivery_quote(config: Any, pincode: str | None, subtotal: Decimal) -> dict[str, Any]:
    if not isinstance(config, dict) or config.get("enabled") is not True:
        return {"configured": False, "serviceable": None, "shipping_fee": None,
                "message": "Delivery coverage and charges have not been configured by the store."}
    pins = config.get("serviceable_pincodes")
    if not isinstance(pins, list) or not pins or any(not isinstance(pin, str) or not re.fullmatch(r"[0-9]{6}", pin) for pin in pins):
        return {"configured": False, "serviceable": None, "shipping_fee": None,
                "message": "Delivery settings need valid serviceable pincodes."}
    if "shipping_fee" not in config:
        return {"configured": False, "serviceable": None, "shipping_fee": None,
                "message": "Delivery settings need an explicit shipping fee."}
    try:
        fee = Decimal(str(config["shipping_fee"]))
        threshold_value = config.get("free_shipping_threshold")
        threshold = Decimal(str(threshold_value)) if threshold_value is not None else None
        if not fee.is_finite() or fee < 0 or fee > Decimal("9999999999.99"):
            raise ValueError("invalid fee")
        if threshold is not None and (not threshold.is_finite() or threshold < 0 or threshold > Decimal("9999999999.99")):
            raise ValueError("invalid free-shipping threshold")
        if fee.quantize(Decimal("0.01")) != fee or (threshold is not None and threshold.quantize(Decimal("0.01")) != threshold):
            raise ValueError("invalid decimal precision")
    except Exception:
        return {"configured": False, "serviceable": None, "shipping_fee": None,
                "message": "Delivery settings contain an invalid fee or threshold."}
    message = config.get("message", "")
    if not isinstance(message, str):
        message = ""
    if not pincode:
        return {"configured": True, "serviceable": None, "shipping_fee": None,
                "message": message or "Enter a delivery pincode to check serviceability."}
    if pincode not in pins:
        return {"configured": True, "serviceable": False, "shipping_fee": None,
                "message": "Delivery is not available for this pincode."}
    if threshold is not None and subtotal >= threshold:
        fee = Decimal("0.00")
    return {"configured": True, "serviceable": True, "shipping_fee": f"{fee:.2f}",
            "message": message or ("Free delivery applied." if fee == 0 else "Delivery is available.")}


def _order_detail(conn: Any, order_id: int) -> dict[str, Any]:
    order = conn.execute(
        """SELECT id,order_number,user_id,status,payment_method,payment_status,currency,
                  subtotal,shipping_fee,loyalty_discount,loyalty_coins_redeemed,total,shipping_address,customer_note,created_at,updated_at
           FROM store_orders WHERE id=%s""", (order_id,)
    ).fetchone()
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
    order["items"] = conn.execute(
        """SELECT variant_id,product_id,sku,product_name,quantity,unit_price,line_total
           FROM store_order_items WHERE order_id=%s ORDER BY id""", (order_id,)
    ).fetchall()
    return order


@router.get("/admin/operations/readiness")
def operations_readiness(authorization: str | None = Header(default=None)) -> dict[str, Any]:
    _require(authorization, {"super_admin", "admin", "staff"})
    try:
        with psycopg.connect(_db(), row_factory=dict_row, connect_timeout=8) as conn:
            _ensure_commerce_schema(conn)
            table_rows = conn.execute(
                """SELECT table_name FROM information_schema.tables
                   WHERE table_schema=current_schema() AND table_type='BASE TABLE'"""
            ).fetchall()
            tables = {row["table_name"] for row in table_rows}
            column_rows = conn.execute(
                """SELECT table_name,column_name,data_type FROM information_schema.columns
                   WHERE table_schema=current_schema()"""
            ).fetchall()
            columns: dict[str, set[str]] = {}
            for row in column_rows:
                columns.setdefault(row["table_name"], set()).add(row["column_name"])

            def module_status(required_tables: set[str]) -> dict[str, Any]:
                found = sorted(tables.intersection(required_tables))
                return {
                    "status": "schema_detected_review_required" if found else "blocked_missing_schema",
                    "tables_detected": found,
                    "integrated": False,
                }

            catalogue_ok = (
                {"products", "product_variants", "product_categories"}.issubset(tables)
                and {"id", "name"}.issubset(columns.get("products", set()))
                and {"id", "product_id", "selling_price"}.issubset(columns.get("product_variants", set()))
            )
            from .operations import _ensure as ensure_operations
            ensure_operations(conn)
            address=body.shipping_address.model_dump()
            customer_email=(address.get("email") or user.get("email") or "").strip().lower()
            customer_name=(address.get("full_name") or user.get("full_name") or "Website customer").strip()
            customer_phone=(address.get("phone") or "").strip()
            if customer_email:
                conn.execute("""INSERT INTO sb_customers(name,phone,email) VALUES(%s,%s,%s)
                    ON CONFLICT (lower(email)) WHERE email IS NOT NULL AND email<>'' DO UPDATE
                    SET name=EXCLUDED.name,phone=COALESCE(EXCLUDED.phone,sb_customers.phone)""",
                    (customer_name,customer_phone or None,customer_email))
            delivery_row = conn.execute(
                "SELECT setting_value FROM store_settings WHERE setting_key='delivery'"
            ).fetchone()
            delivery = _delivery_quote(delivery_row["setting_value"] if delivery_row else None, None, Decimal("0"))
            stock_columns = sorted(
                columns.get("product_variants", set()).intersection(
                    {"stock_quantity", "stock_qty", "available_quantity", "quantity_in_stock", "inventory_quantity"}
                )
            )
            return {
                "catalogue": {"status": "connected" if catalogue_ok else "blocked_schema_mismatch", "integrated": catalogue_ok},
                "inventory": {
                    "status": "schema_detected_review_required" if stock_columns else "blocked_missing_schema",
                    "integrated": False,
                    "stock_columns_detected": stock_columns,
                    "message": "No stock mutation or reservation is enabled until an explicit stock schema and concurrency rules are verified.",
                },
                "delivery": {
                    "status": "configured" if delivery["configured"] else "needs_configuration",
                    "integrated": delivery["configured"],
                    "message": delivery["message"],
                },
                "payments": {
                    "status": "cod_only",
                    "cash_on_delivery": True,
                    "online_payment": False,
                    "provider_configured": False,
                    "message": "Online payments remain deferred; no gateway credentials or payment flow are enabled.",
                },
                "purchasing": module_status({"suppliers", "purchase_orders", "goods_receipts"}),
                "accounting": module_status({"chart_of_accounts", "journal_entries", "ledger_entries", "supplier_bills"}),
                "logistics": module_status({"shipments", "delivery_jobs", "routes", "drivers", "hubs"}),
                "people": module_status({"employees", "attendance", "payroll_runs", "shifts"}),
            }
    except HTTPException:
        raise
    except psycopg.Error as exc:
        raise HTTPException(status_code=503, detail="Operational readiness could not be read.") from exc


@router.get("/checkout-options")
def checkout_options(
    pincode: str | None = Query(default=None, pattern=r"^[0-9]{6}$"),
    subtotal: Decimal = Query(default=Decimal("0"), ge=0, le=Decimal("9999999999.99")),
) -> dict[str, Any]:
    try:
        with psycopg.connect(_db(), row_factory=dict_row, connect_timeout=8) as conn:
            _ensure_commerce_schema(conn)
            row = conn.execute("SELECT setting_value FROM store_settings WHERE setting_key='delivery'").fetchone()
            delivery = _delivery_quote(row["setting_value"] if row else None, pincode, subtotal)
            return {
                "payment_methods": [{"id": "cash_on_delivery", "enabled": True}],
                "online_payment": {"enabled": False, "provider_configured": False,
                                   "message": "Online payments are deferred until a provider is explicitly configured."},
                "delivery": delivery,
            }
    except HTTPException:
        raise
    except psycopg.Error as exc:
        raise HTTPException(status_code=503, detail="Checkout options are temporarily unavailable.") from exc


@router.post("/checkout", status_code=201)
def create_order(body: CheckoutInput, authorization: str | None = Header(default=None)) -> dict[str, Any]:
    user = _current(authorization)
    if body.payment_method != "cash_on_delivery":
        raise HTTPException(status_code=422, detail="Online payment is not enabled until a payment provider is configured.")
    quantities: dict[int, int] = {}
    for item in body.items:
        quantities[item.variant_id] = quantities.get(item.variant_id, 0) + item.quantity
    if any(q > 50 for q in quantities.values()):
        raise HTTPException(status_code=422, detail="Maximum quantity per product variant is 50.")
    try:
        with psycopg.connect(_db(), row_factory=dict_row, connect_timeout=8) as conn:
            _ensure_commerce_schema(conn)
            from .operations import _ensure as ensure_operations
            from .loyalty import _ensure as ensure_loyalty, _program as loyalty_program, _wallet as loyalty_wallet, _post as post_loyalty, _expire_due as expire_loyalty
            ensure_operations(conn)
            ensure_loyalty(conn)
            products: list[dict[str, Any]] = []
            subtotal = Decimal("0")
            for variant_id, quantity in quantities.items():
                product_columns = {r["column_name"] for r in conn.execute(
                    "SELECT column_name FROM information_schema.columns WHERE table_schema=current_schema() AND table_name='products'"
                ).fetchall()}
                variant_columns = {r["column_name"] for r in conn.execute(
                    "SELECT column_name FROM information_schema.columns WHERE table_schema=current_schema() AND table_name='product_variants'"
                ).fetchall()}
                if not {"id", "name"}.issubset(product_columns) or not {"id", "product_id", "selling_price"}.issubset(variant_columns):
                    raise HTTPException(status_code=503, detail="The existing catalogue schema does not support checkout.")
                active_product = " AND p.status='active'" if "status" in product_columns else ""
                active_variant = " AND v.status='active'" if "status" in variant_columns else ""
                sku_select = "v.sku" if "sku" in variant_columns else "NULL::text"
                product = conn.execute(
                    f"""SELECT p.id AS product_id,p.name,v.id AS variant_id,
                               v.selling_price,{sku_select} AS sku
                        FROM products p JOIN product_variants v ON v.product_id=p.id
                        WHERE v.id=%s{active_product}{active_variant}
                        FOR SHARE OF p,v""", (variant_id,)
                ).fetchone()
                if not product:
                    raise HTTPException(status_code=409, detail=f"Product variant {variant_id} is no longer available.")
                price = Decimal(str(product["selling_price"] or 0))
                if price <= 0:
                    raise HTTPException(status_code=409, detail=f"Price is not configured for {product['name']}.")
                line_total = (price * quantity).quantize(Decimal("0.01"))
                subtotal += line_total
                products.append({**product, "quantity": quantity, "unit_price": price, "line_total": line_total})
            delivery_row = conn.execute(
                "SELECT setting_value FROM store_settings WHERE setting_key='delivery'"
            ).fetchone()
            delivery_quote = _delivery_quote(
                delivery_row["setting_value"] if delivery_row else None,
                body.shipping_address.pincode,
                subtotal,
            )
            if not delivery_quote["configured"]:
                raise HTTPException(status_code=503, detail=delivery_quote["message"])
            if delivery_quote["serviceable"] is not True:
                raise HTTPException(status_code=422, detail=delivery_quote["message"])
            shipping_fee = Decimal(str(delivery_quote["shipping_fee"]))
            total_before_coins = subtotal + shipping_fee
            loyalty_discount = Decimal("0")
            coins_used = 0
            if body.super_coins_to_redeem:
                program = loyalty_program(conn)
                if not program["enabled"]:
                    raise HTTPException(status_code=409, detail="Super Coins are currently disabled")
                expire_loyalty(conn, int(user["id"]))
                wallet = loyalty_wallet(conn, int(user["id"]))
                if body.super_coins_to_redeem < int(program["min_redeem_coins"]):
                    raise HTTPException(status_code=422, detail=f"Minimum redemption is {program['min_redeem_coins']} Super Coins")
                if body.super_coins_to_redeem > int(wallet["balance"]):
                    raise HTTPException(status_code=422, detail="Not enough Super Coins in your wallet")
                maximum = (total_before_coins * Decimal(str(program["max_redemption_percent"])) / Decimal("100")).quantize(Decimal("0.01"))
                redemption_value = Decimal(str(program["redemption_value"]))
                max_discount = min(maximum, subtotal)
                coins_used = min(body.super_coins_to_redeem, int((max_discount / redemption_value).to_integral_value(rounding=ROUND_DOWN)))
                loyalty_discount = (Decimal(coins_used) * redemption_value).quantize(Decimal("0.01"))
                if coins_used <= 0 or loyalty_discount <= 0:
                    raise HTTPException(status_code=422, detail="Coin redemption is below the allowed amount")
            total = max(Decimal("0"), total_before_coins - loyalty_discount)
            order_number = "SB-" + secrets.token_hex(5).upper()
            row = conn.execute(
                """INSERT INTO store_orders
                   (order_number,user_id,status,payment_method,payment_status,subtotal,shipping_fee,total,loyalty_discount,loyalty_coins_redeemed,shipping_address,customer_note)
                   VALUES (%s,%s,'placed','cash_on_delivery','pending',%s,%s,%s,%s,%s,%s::jsonb,%s)
                   RETURNING id""",
                (order_number, user["id"], subtotal, shipping_fee, total, loyalty_discount, coins_used,
                 json.dumps(body.shipping_address.model_dump()), body.customer_note.strip())
            ).fetchone()
            if coins_used:
                post_loyalty(conn, int(user["id"]), "redeem", coins_used, f"DEBIT:Redeemed on order {order_number}",
                    order_id=int(row["id"]), key=f"order:{row['id']}:redeem")
            for product in products:
                conn.execute(
                    """INSERT INTO store_order_items
                       (order_id,variant_id,product_id,sku,product_name,quantity,unit_price,line_total)
                       VALUES (%s,%s,%s,%s,%s,%s,%s,%s)""",
                    (row["id"], product["variant_id"], product["product_id"], product["sku"],
                     product["name"], product["quantity"], product["unit_price"], product["line_total"])
                )
                stock=conn.execute("SELECT quantity FROM sb_stock WHERE variant_id=%s AND warehouse='Main' FOR UPDATE",(product["variant_id"],)).fetchone()
                # Enforce inventory only for variants explicitly tracked in the stock ledger.
                if stock:
                    available=Decimal(str(stock["quantity"]))
                    if available < product["quantity"]:
                        raise HTTPException(status_code=422,detail=f"Insufficient stock for {product['name']}; available {available}")
                    conn.execute("UPDATE sb_stock SET quantity=quantity-%s,updated_at=now() WHERE variant_id=%s AND warehouse='Main'",(product["quantity"],product["variant_id"]))
                    conn.execute("""INSERT INTO sb_stock_movements(variant_id,warehouse,movement_type,quantity,reference_type,reference_id)
                        VALUES(%s,'Main','website_sale',%s,'website_order',%s)""",(product["variant_id"],product["quantity"],row["id"]))
            return {"order": _order_detail(conn, row["id"]),
                    "message": "Order placed. Tracked inventory is deducted atomically; payment is due on delivery."}
    except HTTPException:
        raise
    except psycopg.Error as exc:
        import logging
        logging.getLogger("superbajaar.commerce").exception("Order creation failed")
        raise HTTPException(status_code=503, detail="Checkout is temporarily unavailable.") from exc


@router.get("/orders/me")
def list_my_orders(authorization: str | None = Header(default=None)) -> dict[str, Any]:
    user = _current(authorization)
    try:
        with psycopg.connect(_db(), row_factory=dict_row, connect_timeout=8) as conn:
            _ensure_commerce_schema(conn)
            rows = conn.execute(
                """SELECT id,order_number,status,payment_method,payment_status,currency,
                          subtotal,shipping_fee,loyalty_discount,loyalty_coins_redeemed,total,shipping_address,created_at,updated_at
                   FROM store_orders WHERE user_id=%s ORDER BY created_at DESC LIMIT 100""",
                (user["id"],)
            ).fetchall()
            for row in rows:
                row["items"] = conn.execute(
                    """SELECT variant_id,product_id,sku,product_name,quantity,unit_price,line_total
                       FROM store_order_items WHERE order_id=%s ORDER BY id""", (row["id"],)
                ).fetchall()
            return {"items": rows}
    except psycopg.Error as exc:
        raise HTTPException(status_code=503, detail="Order history is temporarily unavailable.") from exc


@router.get("/admin/orders")
def list_admin_orders(
    authorization: str | None = Header(default=None),
    search: str = Query(default="", max_length=100),
    status: str = Query(default="", pattern=r"^(|placed|confirmed|processing|packed|shipped|delivered|cancelled)$"),
) -> dict[str, Any]:
    _require(authorization, {"super_admin", "admin", "staff"})
    try:
        with psycopg.connect(_db(), row_factory=dict_row, connect_timeout=8) as conn:
            _ensure_commerce_schema(conn)
            where = ["(o.order_number ILIKE %s OR u.email ILIKE %s OR u.full_name ILIKE %s)"]
            pattern = f"%{search.strip()}%"
            params: list[Any] = [pattern, pattern, pattern]
            if status:
                where.append("o.status=%s")
                params.append(status)
            rows = conn.execute(
                """SELECT o.id,o.order_number,o.user_id,u.email,u.full_name,o.status,o.payment_method,
                          o.payment_status,o.subtotal,o.shipping_fee,o.total,o.shipping_address,o.created_at,o.updated_at
                   FROM store_orders o JOIN app_users u ON u.id=o.user_id
                   WHERE """ + " AND ".join(where) + " ORDER BY o.created_at DESC LIMIT 200",
                params
            ).fetchall()
            for row in rows:
                row["items"] = conn.execute(
                    """SELECT variant_id,product_id,sku,product_name,quantity,unit_price,line_total
                       FROM store_order_items WHERE order_id=%s ORDER BY id""", (row["id"],)
                ).fetchall()
            return {"items": rows}
    except psycopg.Error as exc:
        raise HTTPException(status_code=503, detail="Order management is temporarily unavailable.") from exc


@router.patch("/admin/orders/{order_id}")
def update_admin_order(
    order_id: int, body: OrderStatusUpdate,
    authorization: str | None = Header(default=None)
) -> dict[str, Any]:
    actor = _require(authorization, {"super_admin", "admin"})
    allowed = {"confirmed", "processing", "packed", "shipped", "delivered", "cancelled"}
    if body.status not in allowed:
        raise HTTPException(status_code=422, detail="Invalid order status transition.")
    try:
        with psycopg.connect(_db(), row_factory=dict_row, connect_timeout=8) as conn:
            _ensure_commerce_schema(conn)
            from .operations import _ensure as ensure_operations
            ensure_operations(conn)
            with conn.transaction():
                previous=conn.execute("SELECT * FROM store_orders WHERE id=%s FOR UPDATE",(order_id,)).fetchone()
                if not previous or previous["status"] in ("cancelled","delivered"):
                    raise HTTPException(status_code=404, detail="Order not found or already closed.")
                if body.status=="cancelled":
                    lines=conn.execute("SELECT variant_id,quantity FROM store_order_items WHERE order_id=%s",(order_id,)).fetchall()
                    for line in lines:
                        reserved=conn.execute("""SELECT id FROM sb_stock_movements WHERE variant_id=%s AND reference_type='website_order'
                            AND reference_id=%s AND movement_type='website_sale' LIMIT 1""",(line["variant_id"],order_id)).fetchone()
                        stock=conn.execute("SELECT quantity FROM sb_stock WHERE variant_id=%s AND warehouse='Main' FOR UPDATE",(line["variant_id"],)).fetchone()
                        if reserved and stock:
                            conn.execute("UPDATE sb_stock SET quantity=quantity+%s,updated_at=now() WHERE variant_id=%s AND warehouse='Main'",(line["quantity"],line["variant_id"]))
                            conn.execute("""INSERT INTO sb_stock_movements(variant_id,warehouse,movement_type,quantity,reference_type,reference_id,created_by)
                                VALUES(%s,'Main','return_in',%s,'website_order_cancel',%s,%s)""",(line["variant_id"],line["quantity"],order_id,actor["id"]))
                row=conn.execute("UPDATE store_orders SET status=%s,updated_at=now() WHERE id=%s RETURNING id",(body.status,order_id)).fetchone()
                if body.status in ("packed","shipped"):
                    shipment=conn.execute("SELECT id FROM sb_shipments WHERE order_type='website' AND order_id=%s AND status NOT IN ('cancelled','delivered') ORDER BY id DESC LIMIT 1",(order_id,)).fetchone()
                    shipment_status="packed" if body.status=="packed" else "in_transit"
                    if shipment:
                        conn.execute("UPDATE sb_shipments SET status=%s WHERE id=%s",(shipment_status,shipment["id"]))
                    else:
                        conn.execute("INSERT INTO sb_shipments(order_type,order_id,status) VALUES('website',%s,%s)",(order_id,shipment_status))
                journal_id=None
                if body.status=="delivered":
                    from .operations import _post_journal
                    subtotal=Decimal(str(previous["subtotal"]))
                    total=Decimal(str(previous["total"]))
                    shipping=Decimal(str(previous["shipping_fee"]))
                    discount=Decimal(str(previous.get("loyalty_discount") or 0))
                    lines=[("accounts_receivable",total,Decimal("0")),("sales",Decimal("0"),subtotal-discount)]
                    if shipping:
                        lines.append(("other_income",Decimal("0"),shipping))
                    cost_rows=conn.execute("""SELECT oi.variant_id,oi.quantity,
                            COALESCE(SUM(CASE WHEN po.id IS NOT NULL THEN pl.unit_cost*pl.received_qty ELSE 0 END)/NULLIF(SUM(CASE WHEN po.id IS NOT NULL THEN pl.received_qty ELSE 0 END),0),0) AS avg_cost
                        FROM store_order_items oi LEFT JOIN sb_purchase_lines pl ON pl.variant_id=oi.variant_id
                        LEFT JOIN sb_purchase_orders po ON po.id=pl.purchase_id AND po.status='received'
                        WHERE oi.order_id=%s GROUP BY oi.variant_id,oi.quantity""",(order_id,)).fetchall()
                    cogs=sum((Decimal(str(x["avg_cost"] or 0))*Decimal(str(x["quantity"])) for x in cost_rows),Decimal("0")).quantize(Decimal("0.01"))
                    if cogs:
                        lines.extend([("cost_of_goods_sold",cogs,Decimal("0")),("inventory",Decimal("0"),cogs)])
                    journal_id=_post_journal(conn,date.today(),previous["order_number"],"Website sale "+previous["order_number"],"website",order_id,lines,actor["id"])
                    from .loyalty import award_order_coins
                    award_order_coins(conn,int(previous["user_id"]),order_id,subtotal-discount,total)
                return {"order": _order_detail(conn, row["id"]), "updated_by": actor["id"], "journal_id":journal_id}
    except HTTPException:
        raise
    except psycopg.Error as exc:
        raise HTTPException(status_code=503, detail="Could not update order status.") from exc


@router.get("/admin/store-settings")
def get_store_settings(authorization: str | None = Header(default=None)) -> dict[str, Any]:
    _require(authorization, {"super_admin", "admin", "staff"})
    try:
        with psycopg.connect(_db(), row_factory=dict_row, connect_timeout=8) as conn:
            _ensure_commerce_schema(conn)
            rows = conn.execute("SELECT setting_key,setting_value,updated_at FROM store_settings ORDER BY setting_key").fetchall()
            return {"items": rows}
    except psycopg.Error as exc:
        raise HTTPException(status_code=503, detail="Store settings are temporarily unavailable.") from exc


@router.put("/admin/store-settings/{setting_key}")
def update_store_setting(
    setting_key: str, body: SettingUpdate,
    authorization: str | None = Header(default=None)
) -> dict[str, Any]:
    actor = _require(authorization, {"super_admin", "admin"})
    if setting_key not in {"brand", "catalogue", "checkout", "delivery", "policies"}:
        raise HTTPException(status_code=422, detail="Unsupported store setting key.")
    # Settings are JSON objects with strict size limits; no executable templates or secrets.
    value = _validated_delivery_setting(body.value) if setting_key == "delivery" else body.value
    encoded = json.dumps(value, separators=(",", ":"))
    if len(encoded) > 20000:
        raise HTTPException(status_code=413, detail="Setting payload is too large.")
    try:
        with psycopg.connect(_db(), row_factory=dict_row, connect_timeout=8) as conn:
            _ensure_commerce_schema(conn)
            row = conn.execute(
                """INSERT INTO store_settings(setting_key,setting_value,updated_by)
                   VALUES (%s,%s::jsonb,%s)
                   ON CONFLICT(setting_key) DO UPDATE
                     SET setting_value=EXCLUDED.setting_value,updated_at=now(),updated_by=EXCLUDED.updated_by
                   RETURNING setting_key,setting_value,updated_at""",
                (setting_key, encoded, actor["id"])
            ).fetchone()
            return {"item": row}
    except psycopg.Error as exc:
        raise HTTPException(status_code=503, detail="Could not save store settings.") from exc
