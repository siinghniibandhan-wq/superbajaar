"""Super Bajaar API foundation. No credentials or product data are hardcoded."""
from contextlib import asynccontextmanager
from decimal import Decimal
import base64
import hashlib
import hmac
import json
import re
import time
import logging
import os
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator, model_validator
from fastapi import FastAPI, Header, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from psycopg_pool import ConnectionPool
from psycopg.errors import UniqueViolation
from psycopg.rows import dict_row

logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"))
logger = logging.getLogger("superbajaar.api")

DATABASE_URL = os.getenv("DATABASE_URL", "").strip()
CORS_ORIGINS = [origin.strip() for origin in os.getenv("CORS_ALLOWED_ORIGINS", "").split(",") if origin.strip()]
pool: ConnectionPool | None = None
ADMIN_USERNAME = os.getenv("ADMIN_USERNAME", "admin").strip()
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "")
ADMIN_TOKEN_SECRET = os.getenv("ADMIN_TOKEN_SECRET", "")


class AdminLogin(BaseModel):
    username: str = Field(min_length=1, max_length=100)
    password: str = Field(min_length=1, max_length=200)


class AdminCategoryInput(BaseModel):
    name: str = Field(min_length=1, max_length=100)

    @field_validator("name")
    @classmethod
    def strip_category_name(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Category name cannot be blank")
        return value


class AdminProductInput(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    product_code: str = Field(min_length=1, max_length=80)
    sku: str = Field(min_length=1, max_length=100)
    description: str = Field(default="", max_length=5000)
    image_url: str = Field(default="", max_length=2048)
    brand: str = Field(default="", max_length=150)
    category: str = Field(default="General", min_length=1, max_length=100)
    selling_price: Decimal = Field(ge=0)
    mrp: Decimal | None = Field(default=None, ge=0)
    currency: Literal["INR", "USD"] = "INR"
    active: bool = True
    variant_attributes: dict[str, Any] = Field(default_factory=dict)

    @field_validator("image_url")
    @classmethod
    def image_url_must_be_http(cls, value: str) -> str:
        value = value.strip()
        if value and not value.startswith(("https://", "http://")):
            raise ValueError("Product image URL must start with https:// or http://")
        return value

    @field_validator("selling_price", "mrp")
    @classmethod
    def validate_money_precision(cls, value: Decimal | None) -> Decimal | None:
        if value is not None and max(0, -value.as_tuple().exponent) > 2:
            raise ValueError("Prices must have no more than two decimal places")
        return value

    @model_validator(mode="after")
    def validate_mrp_not_below_selling_price(self):
        if self.mrp is not None and self.mrp < self.selling_price:
            raise ValueError("MRP must be greater than or equal to the selling price")
        return self


def _b64(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).decode().rstrip("=")


def _admin_token(username: str, expires: int) -> str:
    payload = _b64(json.dumps({"sub": username, "exp": expires}, separators=(",", ":")).encode())
    signature = _b64(hmac.new(ADMIN_TOKEN_SECRET.encode(), payload.encode(), hashlib.sha256).digest())
    return payload + "." + signature


def require_admin(authorization: str | None) -> str:
    if not ADMIN_PASSWORD or len(ADMIN_TOKEN_SECRET) < 32:
        raise HTTPException(status_code=503, detail="Admin login is not configured securely; set ADMIN_PASSWORD and an ADMIN_TOKEN_SECRET of at least 32 characters")
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Admin login required")
    try:
        payload, signature = authorization[7:].split(".", 1)
        expected = _b64(hmac.new(ADMIN_TOKEN_SECRET.encode(), payload.encode(), hashlib.sha256).digest())
        if not hmac.compare_digest(signature, expected):
            raise ValueError("invalid signature")
        claims = json.loads(base64.urlsafe_b64decode(payload + "=" * (-len(payload) % 4)))
        if claims.get("sub") != ADMIN_USERNAME or int(claims.get("exp", 0)) < int(time.time()):
            raise ValueError("expired or invalid token")
        return claims["sub"]
    except Exception:
        raise HTTPException(status_code=401, detail="Admin session expired; sign in again")


@asynccontextmanager
async def lifespan(app: FastAPI):
    global pool
    if DATABASE_URL:
        pool = ConnectionPool(
            conninfo=DATABASE_URL,
            min_size=1,
            max_size=int(os.getenv("DB_POOL_MAX", "5")),
            kwargs={"row_factory": dict_row, "connect_timeout": 5},
            open=True,
        )
        logger.info("Database connection pool initialized")
        # Safe, additive, idempotent migration: product images are optional until populated.
        # Run only when the product variant table exists; do not block older/incomplete schemas.
        try:
            with pool.connection() as conn:
                with conn.transaction():
                    variants_table_exists = conn.execute(
                        "SELECT to_regclass('public.product_variants') AS table_name"
                    ).fetchone()["table_name"] is not None
                    if variants_table_exists:
                        conn.execute(
                            "ALTER TABLE public.product_variants ADD COLUMN IF NOT EXISTS image_url TEXT"
                        )
                        logger.info("Product image schema migration verified")
                    else:
                        logger.warning("product_variants table is not present; skipped product image migration")
        except Exception:
            logger.exception("Product image schema migration failed; API will start, but image URL writes may be unavailable")
    else:
        logger.warning("DATABASE_URL is not configured; database endpoints will return 503")
    yield
    if pool is not None:
        pool.close()
        pool = None


app = FastAPI(
    title="Super Bajaar API",
    version="0.1.0",
    description="Backend API for the Super Bajaar storefront and commerce platform.",
    lifespan=lifespan,
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_credentials=False,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", "X-Request-ID"],
)


def get_pool() -> ConnectionPool:
    if pool is None:
        raise HTTPException(status_code=503, detail="Database is not configured")
    return pool


def json_safe(value: Any) -> Any:
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, dict):
        return {key: json_safe(item) for key, item in value.items()}
    if isinstance(value, list):
        return [json_safe(item) for item in value]
    return value


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "service": "superbajaar-api"}


@app.get("/ready")
def readiness() -> dict[str, str]:
    db = get_pool()
    try:
        with db.connection() as conn:
            conn.execute("SELECT 1")
    except Exception:
        logger.exception("Readiness database check failed")
        raise HTTPException(status_code=503, detail="Database unavailable")
    return {"status": "ready"}



@app.post("/api/admin/login")
def admin_login(credentials: AdminLogin) -> dict[str, Any]:
    if not ADMIN_PASSWORD or len(ADMIN_TOKEN_SECRET) < 32:
        raise HTTPException(status_code=503, detail="Admin login is not configured securely. Set ADMIN_PASSWORD and an ADMIN_TOKEN_SECRET of at least 32 characters.")
    valid_user = hmac.compare_digest(credentials.username, ADMIN_USERNAME)
    valid_password = hmac.compare_digest(credentials.password, ADMIN_PASSWORD)
    if not (valid_user and valid_password):
        raise HTTPException(status_code=401, detail="Invalid admin ID or password")
    expires = int(time.time()) + 8 * 60 * 60
    return {"access_token": _admin_token(ADMIN_USERNAME, expires), "token_type": "bearer", "expires_in": 28800, "username": ADMIN_USERNAME}


@app.get("/api/admin/products")
def admin_list_products(authorization: str | None = Header(default=None)) -> dict[str, Any]:
    require_admin(authorization)
    db = get_pool()
    try:
        with db.connection() as conn:
            image_column_exists = conn.execute(
                "SELECT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_schema = 'public' AND table_name = 'product_variants' AND column_name = 'image_url') AS present"
            ).fetchone()["present"]
            image_select = "v.image_url" if image_column_exists else "NULL::text AS image_url"
            rows = conn.execute(
                f"""SELECT p.id AS product_id, p.product_code, p.name, p.description, p.brand,
                          p.status AS product_status, p.website_published, c.name AS category,
                          v.id AS variant_id, v.sku, v.barcode, v.variant_attributes,
                          {image_select}, v.mrp, v.selling_price, v.currency, v.status AS variant_status
                   FROM products p JOIN product_variants v ON v.product_id = p.id
                   LEFT JOIN product_categories c ON c.id = p.category_id
                   ORDER BY p.created_at DESC, p.name, v.sku LIMIT 500"""
            ).fetchall()
    except Exception:
        logger.exception("Admin product-list query failed")
        raise HTTPException(status_code=503, detail="Product catalogue is temporarily unavailable") from None
    return {"items": json_safe(rows)}


@app.get("/api/admin/categories")
def admin_list_categories(authorization: str | None = Header(default=None)) -> dict[str, Any]:
    require_admin(authorization)
    try:
        with get_pool().connection() as conn:
            rows = conn.execute(
                """SELECT id, category_code, name, parent_id, status
                   FROM product_categories
                   ORDER BY name"""
            ).fetchall()
        return {"items": json_safe(rows)}
    except Exception:
        logger.exception("Admin category-list query failed")
        raise HTTPException(status_code=503, detail="Categories are temporarily unavailable") from None


@app.post("/api/admin/categories", status_code=201)
def admin_create_category(category: AdminCategoryInput, authorization: str | None = Header(default=None)) -> dict[str, Any]:
    require_admin(authorization)
    slug = re.sub(r"[^a-z0-9]+", "-", category.name.lower()).strip("-") or "category"
    try:
        with get_pool().connection() as conn:
            with conn.transaction():
                row = conn.execute(
                    """INSERT INTO product_categories (category_code, name, status)
                       VALUES (%s, %s, 'active')
                       ON CONFLICT (category_code) DO UPDATE
                         SET name = EXCLUDED.name
                       RETURNING id, category_code, name, parent_id, status""",
                    [slug[:80], category.name],
                ).fetchone()
        return {"item": json_safe(row), "message": "Category saved"}
    except Exception:
        logger.exception("Admin category creation failed")
        raise HTTPException(status_code=503, detail="Category could not be saved") from None


@app.post("/api/admin/products", status_code=201)
def admin_create_product(product: AdminProductInput, authorization: str | None = Header(default=None)) -> dict[str, Any]:
    require_admin(authorization)
    if not product.name.strip() or not product.product_code.strip() or not product.sku.strip() or not product.category.strip():
        raise HTTPException(status_code=422, detail="Product name, product code, SKU, and category cannot be blank")
    db = get_pool()
    slug = re.sub(r"[^a-z0-9]+", "-", product.category.strip().lower()).strip("-") or "general"
    status = "active" if product.active else "inactive"
    try:
        with db.connection() as conn:
            with conn.transaction():
                category = conn.execute(
                    """INSERT INTO product_categories (category_code, name, status)
                       VALUES (%s, %s, 'active')
                       ON CONFLICT (category_code) DO UPDATE SET name = product_categories.name
                       RETURNING id""",
                    [slug[:80], product.category.strip()],
                ).fetchone()
                created = conn.execute(
                    """INSERT INTO products
                       (product_code, name, description, brand, category_id, website_published, status)
                       VALUES (%s, %s, %s, %s, %s, %s, %s) RETURNING id""",
                    [product.product_code.strip(), product.name.strip(), product.description.strip(),
                     product.brand.strip() or None, category["id"], product.active, status],
                ).fetchone()
                image_column_exists = conn.execute(
                    "SELECT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_schema = 'public' AND table_name = 'product_variants' AND column_name = 'image_url') AS present"
                ).fetchone()["present"]
                if product.image_url and not image_column_exists:
                    raise HTTPException(status_code=503, detail="Product image storage is not migrated yet; apply backend/schema/005_product_images.sql")
                if image_column_exists:
                    variant = conn.execute(
                        """INSERT INTO product_variants
                           (product_id, sku, variant_attributes, image_url, mrp, selling_price, currency, status)
                           VALUES (%s, %s, %s, %s, %s, %s, %s, %s) RETURNING id""",
                        [created["id"], product.sku.strip(), json.dumps(product.variant_attributes),
                         product.image_url or None, product.mrp, product.selling_price, product.currency.upper(), status],
                    ).fetchone()
                else:
                    variant = conn.execute(
                        """INSERT INTO product_variants
                           (product_id, sku, variant_attributes, mrp, selling_price, currency, status)
                           VALUES (%s, %s, %s, %s, %s, %s, %s) RETURNING id""",
                        [created["id"], product.sku.strip(), json.dumps(product.variant_attributes),
                         product.mrp, product.selling_price, product.currency.upper(), status],
                    ).fetchone()
    except UniqueViolation as exc:
        constraint = getattr(getattr(exc, "diag", None), "constraint_name", "")
        field = "SKU" if "sku" in constraint else "product code" if "product" in constraint else "category"
        raise HTTPException(status_code=409, detail=f"A record with this {field} already exists") from exc
    except Exception:
        logger.exception("Admin product creation failed")
        raise HTTPException(status_code=503, detail="Product could not be saved; check database availability and schema") from None
    return {"product_id": created["id"], "variant_id": variant["id"], "message": "Product saved to the catalogue database"}


@app.put("/api/admin/products/{product_id}/variants/{variant_id}")
def admin_update_product(
    product_id: int,
    variant_id: int,
    product: AdminProductInput,
    authorization: str | None = Header(default=None),
) -> dict[str, Any]:
    require_admin(authorization)
    if product_id < 1 or variant_id < 1:
        raise HTTPException(status_code=422, detail="Product and variant IDs must be positive")
    if not product.name.strip() or not product.product_code.strip() or not product.sku.strip() or not product.category.strip():
        raise HTTPException(status_code=422, detail="Product name, product code, SKU, and category cannot be blank")
    db = get_pool()
    slug = re.sub(r"[^a-z0-9]+", "-", product.category.strip().lower()).strip("-") or "general"
    status = "active" if product.active else "inactive"
    try:
        with db.connection() as conn:
            with conn.transaction():
                existing = conn.execute(
                    "SELECT id FROM product_variants WHERE id = %s AND product_id = %s",
                    [variant_id, product_id],
                ).fetchone()
                if existing is None:
                    raise HTTPException(status_code=404, detail="Product variant not found")
                category = conn.execute(
                    """INSERT INTO product_categories (category_code, name, status)
                       VALUES (%s, %s, 'active')
                       ON CONFLICT (category_code) DO UPDATE SET name = product_categories.name
                       RETURNING id""",
                    [slug[:80], product.category.strip()],
                ).fetchone()
                conn.execute(
                    """UPDATE products
                       SET product_code = %s, name = %s, description = %s, brand = %s,
                           category_id = %s, website_published = %s, status = %s, updated_at = now()
                       WHERE id = %s""",
                    [product.product_code.strip(), product.name.strip(), product.description.strip(),
                     product.brand.strip() or None, category["id"], product.active, status, product_id],
                )
                image_column_exists = conn.execute(
                    "SELECT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_schema = 'public' AND table_name = 'product_variants' AND column_name = 'image_url') AS present"
                ).fetchone()["present"]
                if product.image_url and not image_column_exists:
                    raise HTTPException(status_code=503, detail="Product image storage is not migrated yet; apply backend/schema/005_product_images.sql")
                if image_column_exists:
                    conn.execute(
                        """UPDATE product_variants
                           SET sku = %s, variant_attributes = %s, image_url = %s, mrp = %s, selling_price = %s,
                               currency = %s, status = %s
                           WHERE id = %s AND product_id = %s""",
                        [product.sku.strip(), json.dumps(product.variant_attributes), product.image_url or None,
                         product.mrp, product.selling_price, product.currency, status, variant_id, product_id],
                    )
                else:
                    conn.execute(
                        """UPDATE product_variants
                           SET sku = %s, variant_attributes = %s, mrp = %s, selling_price = %s,
                               currency = %s, status = %s
                           WHERE id = %s AND product_id = %s""",
                        [product.sku.strip(), json.dumps(product.variant_attributes), product.mrp,
                         product.selling_price, product.currency, status, variant_id, product_id],
                    )
    except HTTPException:
        raise
    except UniqueViolation as exc:
        constraint = getattr(getattr(exc, "diag", None), "constraint_name", "")
        field = "SKU" if "sku" in constraint else "product code" if "product" in constraint else "category"
        raise HTTPException(status_code=409, detail=f"A record with this {field} already exists") from exc
    except Exception:
        logger.exception("Admin product update failed")
        raise HTTPException(status_code=503, detail="Product could not be updated; check database availability and schema") from None
    return {"product_id": product_id, "variant_id": variant_id, "message": "Product updated successfully"}


@app.get("/api/products")
def list_products(
    search: str = Query(default="", max_length=120),
    pincode: str = Query(default="", pattern=r"^$|^\d{6}$"),
    category: str = Query(default="", max_length=80),
    limit: int = Query(default=24, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    product_id: int | None = Query(default=None, ge=1),
) -> dict[str, Any]:
    """Return active catalogue products with current prices, stock, and approved review summaries."""
    db = get_pool()
    conditions = ["p.status = 'active'", "v.status = 'active'"]
    params: list[Any] = []
    if product_id is not None:
        conditions.append("p.id = %s")
        params.append(product_id)
    if search.strip():
        conditions.append("(p.name ILIKE %s OR p.brand ILIKE %s OR v.sku ILIKE %s)")
        term = f"%{search.strip()}%"
        params.extend([term, term, term])
    if category.strip():
        conditions.append("c.category_code = %s")
        params.append(category.strip())
    # A serviceability filter is only applied when a matching coverage table is installed.
    # Until then, never claim a PIN code is serviceable based on a frontend-only guess.
    if pincode:
        try:
            with db.connection() as conn:
                coverage_exists = conn.execute(
                    "SELECT to_regclass('public.warehouse_serviceability') AS table_name"
                ).fetchone()["table_name"] is not None
        except Exception:
            logger.exception("Could not inspect serviceability schema")
            raise HTTPException(status_code=503, detail="Serviceability data unavailable")
        if not coverage_exists:
            raise HTTPException(status_code=503, detail="PIN-code serviceability is not configured yet")
        conditions.append("""EXISTS (
            SELECT 1
            FROM warehouse_serviceability ws
            JOIN inventory_balances ib ON ib.warehouse_id = ws.warehouse_id
            WHERE ws.pincode = %s AND ws.status = 'active'
              AND ws.valid_from <= now() AND (ws.valid_to IS NULL OR ws.valid_to > now())
              AND ib.product_variant_id = v.id
              AND (ib.quantity_on_hand - ib.quantity_reserved) > 0
        )""")
        params.append(pincode)
    where_sql = " AND ".join(conditions)
    history_select = "NULL::numeric AS lowest_selling_price_30d,"
    try:
        with db.connection() as conn:
            history_exists = conn.execute(
                "SELECT to_regclass('public.product_price_history') AS table_name"
            ).fetchone()["table_name"] is not None
        if history_exists:
            history_select = """(
                SELECT MIN(ph.price) FROM product_price_history ph
                WHERE ph.product_variant_id = v.id
                  AND ph.price_type = 'selling'
                  AND ph.valid_from >= now() - interval '30 days'
            ) AS lowest_selling_price_30d,"""
    except Exception:
        logger.exception("Could not inspect price history table; continuing without 30-day price")
    review_select = """0::numeric AS average_rating, 0::bigint AS review_count,"""
    try:
        with db.connection() as conn:
            reviews_exists = conn.execute(
                "SELECT to_regclass('public.product_reviews') AS table_name"
            ).fetchone()["table_name"] is not None
        if reviews_exists:
            review_select = """COALESCE((
                    SELECT ROUND(AVG(pr.rating)::numeric, 1)
                    FROM product_reviews pr
                    WHERE pr.product_id = p.id AND pr.status = 'approved'
                ), 0) AS average_rating,
                (
                    SELECT COUNT(*) FROM product_reviews pr
                    WHERE pr.product_id = p.id AND pr.status = 'approved'
                ) AS review_count,"""
    except Exception:
        logger.exception("Could not inspect product review schema; returning empty review summaries")

    image_column_exists = False
    try:
        with db.connection() as conn:
            image_column_exists = conn.execute(
                "SELECT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_schema = 'public' AND table_name = 'product_variants' AND column_name = 'image_url') AS present"
            ).fetchone()["present"]
    except Exception:
        logger.exception("Could not inspect product image column; returning empty image URLs")
    image_select = "v.image_url" if image_column_exists else "NULL::text AS image_url"
    query = f"""
        SELECT p.id AS product_id, p.product_code, p.name, p.description, p.brand,
               c.name AS category, v.id AS variant_id, v.sku, v.barcode,
               v.variant_attributes, {image_select}, v.mrp, v.selling_price, v.currency,
               {history_select}
               {review_select}
               COALESCE(SUM(ib.quantity_on_hand - ib.quantity_reserved), 0) AS available_quantity
        FROM products p
        JOIN product_variants v ON v.product_id = p.id
        LEFT JOIN product_categories c ON c.id = p.category_id
        LEFT JOIN inventory_balances ib ON ib.product_variant_id = v.id
        WHERE {where_sql}
        GROUP BY p.id, c.name, v.id
        ORDER BY p.name, v.sku
        LIMIT %s OFFSET %s
    """
    query = f"""
        SELECT p.id AS product_id, p.product_code, p.name, p.description, p.brand,
               c.name AS category, v.id AS variant_id, v.sku, v.barcode,
               v.variant_attributes, v.mrp, v.selling_price, v.currency,
               {history_select}
               {review_select}
               COALESCE(SUM(ib.quantity_on_hand - ib.quantity_reserved), 0) AS available_quantity
        FROM products p
        JOIN product_variants v ON v.product_id = p.id
        LEFT JOIN product_categories c ON c.id = p.category_id
        LEFT JOIN inventory_balances ib ON ib.product_variant_id = v.id
        WHERE {where_sql}
        GROUP BY p.id, c.name, v.id
        ORDER BY p.name, v.sku
        LIMIT %s OFFSET %s
    """
    params.extend([limit, offset])
    try:
        with db.connection() as conn:
            rows = conn.execute(query, params).fetchall()
    except Exception:
        logger.exception("Catalogue query failed")
        raise HTTPException(status_code=503, detail="Catalogue is not ready; check database migrations")
    return {"items": json_safe(rows), "limit": limit, "offset": offset}


class ProductReviewInput(BaseModel):
    reviewer_name: str = Field(min_length=1, max_length=80)
    rating: int = Field(ge=1, le=5)
    review_text: str = Field(min_length=3, max_length=2000)

    @field_validator("reviewer_name", "review_text")
    @classmethod
    def strip_review_text(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("This field cannot be blank")
        return value


class ProductReviewModeration(BaseModel):
    status: Literal["approved", "rejected"]


@app.get("/api/products/{product_id}/reviews")
def list_product_reviews(product_id: int) -> dict[str, Any]:
    db = get_pool()
    try:
        with db.connection() as conn:
            exists = conn.execute(
                "SELECT to_regclass('public.product_reviews') AS table_name"
            ).fetchone()["table_name"] is not None
            if not exists:
                return {"items": [], "message": "Reviews are not configured yet"}
            rows = conn.execute(
                """SELECT id, reviewer_name, rating, review_text, created_at
                   FROM product_reviews
                   WHERE product_id = %s AND status = 'approved'
                   ORDER BY created_at DESC LIMIT 100""",
                [product_id],
            ).fetchall()
    except Exception:
        logger.exception("Could not load product reviews")
        raise HTTPException(status_code=503, detail="Reviews are temporarily unavailable")
    return {"items": json_safe(rows)}


@app.post("/api/products/{product_id}/reviews", status_code=202)
def submit_product_review(product_id: int, review: ProductReviewInput) -> dict[str, str]:
    db = get_pool()
    try:
        with db.connection() as conn:
            exists = conn.execute(
                "SELECT to_regclass('public.product_reviews') AS table_name"
            ).fetchone()["table_name"] is not None
            if not exists:
                raise HTTPException(status_code=503, detail="Review submission is not configured yet")
            product = conn.execute(
                "SELECT id FROM products WHERE id = %s AND status = 'active'",
                [product_id],
            ).fetchone()
            if not product:
                raise HTTPException(status_code=404, detail="Product not found")
            conn.execute(
                """INSERT INTO product_reviews
                   (product_id, reviewer_name, rating, review_text, status)
                   VALUES (%s, %s, %s, %s, 'pending')""",
                [product_id, review.reviewer_name.strip(), review.rating, review.review_text.strip()],
            )
    except HTTPException:
        raise
    except Exception:
        logger.exception("Could not save product review")
        raise HTTPException(status_code=503, detail="Review submission failed")
    return {"message": "Thank you. Your review was submitted for moderation."}


@app.get("/api/admin/reviews")
def admin_list_reviews(authorization: str | None = Header(default=None)) -> dict[str, Any]:
    require_admin(authorization)
    db = get_pool()
    try:
        with db.connection() as conn:
            exists = conn.execute("SELECT to_regclass('public.product_reviews') AS table_name").fetchone()["table_name"] is not None
            if not exists:
                return {"items": [], "message": "Review schema is not installed yet"}
            rows = conn.execute(
                """SELECT pr.id, pr.product_id, p.name AS product_name, pr.reviewer_name,
                          pr.rating, pr.review_text, pr.status, pr.created_at
                   FROM product_reviews pr JOIN products p ON p.id = pr.product_id
                   ORDER BY CASE pr.status WHEN 'pending' THEN 0 ELSE 1 END, pr.created_at DESC
                   LIMIT 500"""
            ).fetchall()
    except Exception:
        logger.exception("Admin review list failed")
        raise HTTPException(status_code=503, detail="Reviews are temporarily unavailable")
    return {"items": json_safe(rows)}


@app.patch("/api/admin/reviews/{review_id}")
def admin_moderate_review(
    review_id: int,
    moderation: ProductReviewModeration,
    authorization: str | None = Header(default=None),
) -> dict[str, Any]:
    require_admin(authorization)
    db = get_pool()
    try:
        with db.connection() as conn:
            with conn.transaction():
                row = conn.execute(
                    "UPDATE product_reviews SET status = %s, moderated_at = now() WHERE id = %s RETURNING id, status",
                    [moderation.status, review_id],
                ).fetchone()
                if row is None:
                    raise HTTPException(status_code=404, detail="Review not found")
    except HTTPException:
        raise
    except Exception:
        logger.exception("Review moderation failed")
        raise HTTPException(status_code=503, detail="Could not update review status")
    return {"review_id": row["id"], "status": row["status"], "message": "Review status updated"}


@app.get("/api/serviceability")
def check_serviceability(pincode: str = Query(..., pattern=r"^\d{6}$")) -> dict[str, Any]:
    """Check active warehouse coverage and inventory; never infer from PIN format alone."""
    db = get_pool()
    try:
        with db.connection() as conn:
            table_exists = conn.execute(
                "SELECT to_regclass('public.warehouse_serviceability') AS table_name"
            ).fetchone()["table_name"] is not None
            if not table_exists:
                raise HTTPException(status_code=503, detail="PIN-code serviceability is not configured yet")
            rows = conn.execute(
                """SELECT DISTINCT ws.warehouse_id, w.name AS warehouse_name
                   FROM warehouse_serviceability ws
                   JOIN warehouses w ON w.id = ws.warehouse_id
                   WHERE ws.pincode = %s AND ws.status = 'active' AND w.status = 'active'
                     AND ws.valid_from <= now() AND (ws.valid_to IS NULL OR ws.valid_to > now())
                     AND EXISTS (
                       SELECT 1 FROM inventory_balances ib
                       WHERE ib.warehouse_id = ws.warehouse_id
                         AND (ib.quantity_on_hand - ib.quantity_reserved) > 0
                     )""",
                [pincode],
            ).fetchall()
    except HTTPException:
        raise
    except Exception:
        logger.exception("Serviceability query failed")
        raise HTTPException(status_code=503, detail="Could not verify serviceability")
    return {
        "pincode": pincode,
        "serviceable": bool(rows),
        "warehouse_count": len(rows),
        "message": "Delivery available" if rows else "Delivery is not currently available for this PIN code",
    }
