"""Commerce APIs for checkout, customer order history, and persisted storefront settings.

These tables are isolated from the catalogue and are initialized lazily. No Odoo
sync, product import, or payment-provider simulation is performed here.
"""
import json
import secrets
from decimal import Decimal
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


class SettingUpdate(BaseModel):
    value: dict[str, Any]


class OrderStatusUpdate(BaseModel):
    status: str


def _order_detail(conn: Any, order_id: int) -> dict[str, Any]:
    order = conn.execute(
        """SELECT id,order_number,user_id,status,payment_method,payment_status,currency,
                  subtotal,shipping_fee,total,shipping_address,customer_note,created_at,updated_at
           FROM store_orders WHERE id=%s""", (order_id,)
    ).fetchone()
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
    order["items"] = conn.execute(
        """SELECT variant_id,product_id,sku,product_name,quantity,unit_price,line_total
           FROM store_order_items WHERE order_id=%s ORDER BY id""", (order_id,)
    ).fetchall()
    return order


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
            # Shipping is deliberately zero until an admin configures a verified shipping rule.
            shipping_fee = Decimal("0.00")
            total = subtotal + shipping_fee
            order_number = "SB-" + secrets.token_hex(5).upper()
            row = conn.execute(
                """INSERT INTO store_orders
                   (order_number,user_id,status,payment_method,payment_status,subtotal,shipping_fee,total,shipping_address,customer_note)
                   VALUES (%s,%s,'placed','cash_on_delivery','pending',%s,%s,%s,%s::jsonb,%s)
                   RETURNING id""",
                (order_number, user["id"], subtotal, shipping_fee, total,
                 json.dumps(body.shipping_address.model_dump()), body.customer_note.strip())
            ).fetchone()
            for product in products:
                conn.execute(
                    """INSERT INTO store_order_items
                       (order_id,variant_id,product_id,sku,product_name,quantity,unit_price,line_total)
                       VALUES (%s,%s,%s,%s,%s,%s,%s,%s)""",
                    (row["id"], product["variant_id"], product["product_id"], product["sku"],
                     product["name"], product["quantity"], product["unit_price"], product["line_total"])
                )
            return {"order": _order_detail(conn, row["id"]),
                    "message": "Order placed. Payment is due on delivery."}
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
                          subtotal,shipping_fee,total,shipping_address,created_at,updated_at
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
            row = conn.execute(
                """UPDATE store_orders SET status=%s,updated_at=now()
                   WHERE id=%s AND status NOT IN ('cancelled','delivered') RETURNING id""",
                (body.status, order_id)
            ).fetchone()
            if not row:
                raise HTTPException(status_code=404, detail="Order not found or already closed.")
            return {"order": _order_detail(conn, row["id"]), "updated_by": actor["id"]}
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
    encoded = json.dumps(body.value, separators=(",", ":"))
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
