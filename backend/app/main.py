"""Super Bajaar API foundation. No credentials or product data are hardcoded."""
from contextlib import asynccontextmanager
from decimal import Decimal
import logging
import os
from typing import Any
from pydantic import BaseModel, Field

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from psycopg_pool import ConnectionPool
from psycopg.rows import dict_row

logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"))
logger = logging.getLogger("superbajaar.api")

DATABASE_URL = os.getenv("DATABASE_URL", "").strip()
CORS_ORIGINS = [origin.strip() for origin in os.getenv("CORS_ALLOWED_ORIGINS", "").split(",") if origin.strip()]
pool: ConnectionPool | None = None


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


@app.get("/api/products")
def list_products(
    search: str = Query(default="", max_length=120),
    pincode: str = Query(default="", pattern=r"^$|^\d{6}$"),
    category: str = Query(default="", max_length=80),
    limit: int = Query(default=24, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
) -> dict[str, Any]:
    """Return published products with current prices and stock-backed serviceability."""
    db = get_pool()
    conditions = ["p.status = 'active'", "v.status = 'active'"]
    params: list[Any] = []
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
    query = f"""
        SELECT p.id AS product_id, p.product_code, p.name, p.description, p.brand,
               c.name AS category, v.id AS variant_id, v.sku, v.barcode,
               v.variant_attributes, v.mrp, v.selling_price, v.currency,
               {history_select}
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
