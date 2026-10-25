import os
import logging
import hmac
from typing import Any

from pydantic import BaseModel, Field

import psycopg
from fastapi import FastAPI, Header, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from psycopg.rows import dict_row

logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"))
logger = logging.getLogger("superbajaar.api")
app = FastAPI(title="Super Bajaar API", version="1.0.0")


configured_origins = [item.strip() for item in os.getenv("CORS_ALLOWED_ORIGINS", "http://localhost:5173").split(",") if item.strip()]
# Keep the configured origins and explicitly allow the production storefront plus Codespaces previews.
origins = list(dict.fromkeys(configured_origins + [
    "https://bw7rptzexc5.amplifyapp.com",
    "https://main.d33bw7rptzexc5.amplifyapp.com",
]))
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_origin_regex=r"https://.*\.app\.github\.dev",
    allow_credentials=False,
    allow_methods=["GET", "POST", "PUT", "PATCH", "OPTIONS"],
    allow_headers=["Accept", "Content-Type", "Authorization", "X-Review-Moderation-Token"],
)


def database_url() -> str:
    # Prefer the deployment environment, then AWS SSM Parameter Store on EC2.
    # The instance role must be allowed to read /superbajaar/DATABASE_URL.
    value = os.getenv("DATABASE_URL", "").strip()
    if not value:
        try:
            from .auth import _setting
            value = _setting("DATABASE_URL")
        except Exception:
            value = ""
    if not value:
        raise HTTPException(status_code=503, detail="Database connection is not configured in the backend environment or AWS Parameter Store")
    return value


def get_columns(conn: psycopg.Connection, table: str) -> set[str]:
    rows = conn.execute("SELECT column_name FROM information_schema.columns WHERE table_schema = current_schema() AND table_name = %s", (table,)).fetchall()
    return {row["column_name"] for row in rows}


@app.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/api/products")
def list_products(
    search: str = Query(default="", max_length=120),
    category: str = Query(default="", max_length=80),
    limit: int = Query(default=24, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
) -> dict[str, Any]:
    try:
        with psycopg.connect(database_url(), row_factory=dict_row, connect_timeout=8) as conn:
            product_columns = get_columns(conn, "products")
            variant_columns = get_columns(conn, "product_variants")
            category_columns = get_columns(conn, "product_categories")
            if not product_columns or not variant_columns or not category_columns:
                raise HTTPException(status_code=503, detail="The existing catalogue tables are not available")

            product_status = "p.status = 'active'" if "status" in product_columns else "TRUE"
            variant_status = "v.status = 'active'" if "status" in variant_columns else "TRUE"
            image_select = "v.image_url AS image_url" if "image_url" in variant_columns else "NULL::text AS image_url"
            brand_select = "p.brand AS brand" if "brand" in product_columns else "NULL::text AS brand"
            description_select = "p.description AS description" if "description" in product_columns else "NULL::text AS description"
            currency_select = "v.currency AS currency" if "currency" in variant_columns else "'INR'::text AS currency"
            category_join = "LEFT JOIN product_categories c ON c.id = p.category_id" if "category_id" in product_columns else "LEFT JOIN product_categories c ON FALSE"
            where = [product_status, variant_status]
            params: list[Any] = []
            if search.strip():
                where.append("(p.name ILIKE %s OR COALESCE(p.description, '') ILIKE %s OR COALESCE(p.brand, '') ILIKE %s)" if "brand" in product_columns and "description" in product_columns else "p.name ILIKE %s")
                if "brand" in product_columns and "description" in product_columns:
                    pattern = f"%{search.strip()}%"
                    params.extend([pattern, pattern, pattern])
                else:
                    params.append(f"%{search.strip()}%")
            if category.strip():
                where.append("c.name = %s")
                params.append(category.strip())
            params.extend([limit, offset])
            query = f"""SELECT p.id AS product_id, p.name, {description_select}, {brand_select},
                              c.name AS category, v.id AS variant_id,
                              {('v.sku' if 'sku' in variant_columns else 'NULL::text AS sku')},
                              {('v.mrp' if 'mrp' in variant_columns else 'NULL::numeric AS mrp')},
                              {('v.selling_price' if 'selling_price' in variant_columns else 'NULL::numeric AS selling_price')},
                              {currency_select}, {image_select}
                       FROM products p
                       JOIN product_variants v ON v.product_id = p.id
                       {category_join}
                       WHERE {' AND '.join(where)}
                       ORDER BY p.name, v.id
                       LIMIT %s OFFSET %s"""
            rows = conn.execute(query, params).fetchall()
            return {"items": rows, "limit": limit, "offset": offset}
    except HTTPException:
        raise
    except psycopg.Error as exc:
        logger.exception("Catalogue database query failed")
        raise HTTPException(status_code=503, detail="Catalogue is temporarily unavailable") from exc


@app.get("/api/products/by-variant/{variant_id}")
def get_product_by_variant(variant_id: int) -> dict[str, Any]:
    """Return one active catalogue variant for a direct product URL."""
    try:
        with psycopg.connect(database_url(), row_factory=dict_row, connect_timeout=8) as conn:
            product_columns = get_columns(conn, "products")
            variant_columns = get_columns(conn, "product_variants")
            category_columns = get_columns(conn, "product_categories")
            if not product_columns or not variant_columns or not category_columns:
                raise HTTPException(status_code=503, detail="The existing catalogue tables are not available")
            product_status = "p.status = 'active'" if "status" in product_columns else "TRUE"
            variant_status = "v.status = 'active'" if "status" in variant_columns else "TRUE"
            image_select = "v.image_url AS image_url" if "image_url" in variant_columns else "NULL::text AS image_url"
            brand_select = "p.brand AS brand" if "brand" in product_columns else "NULL::text AS brand"
            description_select = "p.description AS description" if "description" in product_columns else "NULL::text AS description"
            currency_select = "v.currency AS currency" if "currency" in variant_columns else "'INR'::text AS currency"
            category_join = "LEFT JOIN product_categories c ON c.id = p.category_id" if "category_id" in product_columns else "LEFT JOIN product_categories c ON FALSE"
            sku_select = "v.sku AS sku" if "sku" in variant_columns else "NULL::text AS sku"
            mrp_select = "v.mrp AS mrp" if "mrp" in variant_columns else "NULL::numeric AS mrp"
            price_select = "v.selling_price AS selling_price" if "selling_price" in variant_columns else "NULL::numeric AS selling_price"
            row = conn.execute(f"""SELECT p.id AS product_id, p.name, {description_select}, {brand_select},
                c.name AS category, v.id AS variant_id, {sku_select}, {mrp_select},
                {price_select}, {currency_select}, {image_select}
                FROM products p JOIN product_variants v ON v.product_id = p.id
                {category_join} WHERE v.id = %s AND {product_status} AND {variant_status}
                LIMIT 1""", (variant_id,)).fetchone()
            if not row:
                raise HTTPException(status_code=404, detail="Product not found")
            return row
    except HTTPException:
        raise
    except psycopg.Error as exc:
        logger.exception("Product detail query failed")
        raise HTTPException(status_code=503, detail="Product details are temporarily unavailable") from exc



DEFAULT_REVIEW_FLAG_WORDS = ("fuck", "shit", "bitch", "bastard", "asshole", "motherfucker", "cunt", "dickhead")


def review_needs_moderation(text: str) -> bool:
    """Flag obvious profanity for manual review; ordinary positive or negative opinions publish immediately."""
    configured = os.getenv("REVIEW_FLAG_WORDS", "").strip()
    words = tuple(word.strip().casefold() for word in configured.split(",") if word.strip()) if configured else DEFAULT_REVIEW_FLAG_WORDS
    lowered = text.casefold()
    import re
    return any(re.search(r"(?<!\w)" + re.escape(word) + r"(?!\w)", lowered) for word in words)


class ProductReviewInput(BaseModel):
    reviewer_name: str = Field(min_length=1, max_length=80)
    rating: int = Field(ge=1, le=5)
    review_text: str = Field(min_length=3, max_length=2000)

@app.get("/api/products/{product_id}/reviews")
def list_product_reviews(product_id: int) -> dict[str, Any]:
    """Return only approved reviews; safely report empty when migration is not applied."""
    try:
        with psycopg.connect(database_url(), row_factory=dict_row, connect_timeout=8) as conn:
            if not conn.execute("SELECT to_regclass('public.product_reviews') AS table_name").fetchone()["table_name"]:
                return {"items": [], "message": "Reviews are not configured yet"}
            rows = conn.execute(
                """SELECT id, reviewer_name, rating, review_text, created_at
                   FROM product_reviews
                   WHERE product_id = %s AND status = 'approved'
                   ORDER BY created_at DESC LIMIT 100""",
                (product_id,),
            ).fetchall()
            summary = conn.execute(
                """SELECT COUNT(*)::int AS review_count, COALESCE(AVG(rating), 0)::numeric(3,2) AS average_rating
                   FROM product_reviews WHERE product_id = %s AND status = 'approved'""",
                (product_id,),
            ).fetchone()
            return {"items": rows, **summary}
    except HTTPException:
        raise
    except psycopg.Error as exc:
        logger.exception("Could not load product reviews")
        raise HTTPException(status_code=503, detail="Reviews are temporarily unavailable") from exc


@app.post("/api/products/{product_id}/reviews", status_code=202)
def submit_product_review(product_id: int, review: ProductReviewInput) -> dict[str, str]:
    """Publish ordinary reviews immediately; hold reviews containing flagged profanity for moderation."""
    reviewer_name = review.reviewer_name.strip()
    review_text = review.review_text.strip()
    if not reviewer_name or not review_text:
        raise HTTPException(status_code=422, detail="Name and review cannot be blank")
    try:
        with psycopg.connect(database_url(), row_factory=dict_row, connect_timeout=8) as conn:
            if not conn.execute("SELECT to_regclass('public.product_reviews') AS table_name").fetchone()["table_name"]:
                raise HTTPException(status_code=503, detail="Review submission is not configured yet")
            product_columns = get_columns(conn, "products")
            if not product_columns:
                raise HTTPException(status_code=503, detail="Catalogue is not available")
            status_filter = " AND status = 'active'" if "status" in product_columns else ""
            product = conn.execute(
                f"SELECT id FROM products WHERE id = %s{status_filter} LIMIT 1",
                (product_id,),
            ).fetchone()
            if not product:
                raise HTTPException(status_code=404, detail="Product not found")
            flagged = review_needs_moderation(review_text)
            review_status = "pending" if flagged else "approved"
            conn.execute(
                """INSERT INTO product_reviews
                   (product_id, reviewer_name, rating, review_text, status)
                   VALUES (%s, %s, %s, %s, %s)""",
                (product_id, reviewer_name, review.rating, review_text, review_status),
            )
    except HTTPException:
        raise
    except psycopg.Error as exc:
        logger.exception("Could not save product review")
        raise HTTPException(status_code=503, detail="Review submission failed") from exc
    return {"message": "Your review is published. Thank you for sharing your feedback." if review_status == "approved" else "Your review was saved and is awaiting a quick content check."}



def require_review_moderator(token: str) -> None:
    expected = os.getenv("REVIEW_MODERATION_TOKEN", "").strip()
    if not expected:
        raise HTTPException(status_code=503, detail="Review moderation is not configured on the server")
    if not token or not hmac.compare_digest(token, expected):
        raise HTTPException(status_code=401, detail="Invalid review moderation token")


@app.get("/api/admin/reviews")
def list_reviews_for_moderation(
    x_review_moderation_token: str = Header(default="", alias="X-Review-Moderation-Token"),
) -> dict[str, Any]:
    """List pending reviews for the separately token-protected moderation workspace."""
    require_review_moderator(x_review_moderation_token)
    try:
        with psycopg.connect(database_url(), row_factory=dict_row, connect_timeout=8) as conn:
            table = conn.execute("SELECT to_regclass('public.product_reviews') AS table_name").fetchone()["table_name"]
            if not table:
                raise HTTPException(status_code=503, detail="Review schema migration has not been applied")
            rows = conn.execute(
                """SELECT r.id, r.product_id, p.name AS product_name, r.reviewer_name,
                          r.rating, r.review_text, r.created_at, r.status
                   FROM product_reviews r JOIN products p ON p.id = r.product_id
                   WHERE r.status = 'pending' ORDER BY r.created_at ASC LIMIT 200"""
            ).fetchall()
            return {"items": rows}
    except HTTPException:
        raise
    except psycopg.Error as exc:
        logger.exception("Could not load pending reviews")
        raise HTTPException(status_code=503, detail="Review moderation is temporarily unavailable") from exc


@app.patch("/api/admin/reviews/{review_id}")
def moderate_product_review(
    review_id: int,
    status: str = Query(..., pattern="^(approved|rejected)$"),
    x_review_moderation_token: str = Header(default="", alias="X-Review-Moderation-Token"),
) -> dict[str, str]:
    """Approve or reject one pending review using the server-side moderation token."""
    require_review_moderator(x_review_moderation_token)
    try:
        with psycopg.connect(database_url(), row_factory=dict_row, connect_timeout=8) as conn:
            table = conn.execute("SELECT to_regclass('public.product_reviews') AS table_name").fetchone()["table_name"]
            if not table:
                raise HTTPException(status_code=503, detail="Review schema migration has not been applied")
            row = conn.execute(
                """UPDATE product_reviews SET status = %s, moderated_at = now()
                   WHERE id = %s AND status = 'pending' RETURNING id""",
                (status, review_id),
            ).fetchone()
            if not row:
                raise HTTPException(status_code=404, detail="Pending review not found")
    except HTTPException:
        raise
    except psycopg.Error as exc:
        logger.exception("Could not moderate product review")
        raise HTTPException(status_code=503, detail="Review moderation failed") from exc
    return {"message": "Review " + status + ".", "status": status}


@app.get("/api/categories")
def list_categories() -> dict[str, Any]:
    try:
        with psycopg.connect(database_url(), row_factory=dict_row, connect_timeout=8) as conn:
            columns = get_columns(conn, "product_categories")
            if not columns:
                raise HTTPException(status_code=503, detail="The existing category table is not available")
            status_filter = "WHERE status = 'active'" if "status" in columns else ""
            rows = conn.execute(f"SELECT id, name FROM product_categories {status_filter} ORDER BY name").fetchall()
            return {"items": rows}
    except HTTPException:
        raise
    except psycopg.Error as exc:
        logger.exception("Category database query failed")
        raise HTTPException(status_code=503, detail="Categories are temporarily unavailable") from exc


@app.get("/api/products/variants/{variant_id}/price-history")
def get_variant_price_history(variant_id: int, days: int = Query(default=30, ge=1, le=90)) -> dict[str, Any]:
    """Return recorded selling-price snapshots for one variant; never fabricate missing history."""
    try:
        with psycopg.connect(database_url(), row_factory=dict_row, connect_timeout=8) as conn:
            table = conn.execute("SELECT to_regclass('public.product_variant_price_history') AS table_name").fetchone()["table_name"]
            if not table:
                return {"available": False, "items": [], "message": "Price history is building; historical snapshots are not available yet."}
            rows = conn.execute(
                """SELECT selling_price, recorded_at FROM product_variant_price_history
                   WHERE variant_id = %s AND recorded_at >= now() - (%s * interval '1 day')
                   ORDER BY recorded_at ASC LIMIT 1000""", (variant_id, days)
            ).fetchall()
            return {"available": len(rows) > 0, "days": days, "items": rows}
    except HTTPException:
        raise
    except psycopg.Error as exc:
        logger.exception("Could not load variant price history")
        raise HTTPException(status_code=503, detail="Price history is temporarily unavailable") from exc


# Register routers after module initialization. This avoids registering a partially
# initialized router if imports are ever refactored to introduce a dependency cycle.
from .auth import router as auth_router
from .commerce import router as commerce_router

app.include_router(auth_router)
app.include_router(commerce_router)
