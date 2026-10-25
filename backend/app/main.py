import os
import logging
import re
import hmac
import uuid
from typing import Any

from pydantic import BaseModel, Field

import psycopg
from fastapi import FastAPI, Header, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi import Request
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"))
logger = logging.getLogger("superbajaar.api")
app = FastAPI(title="Super Bajaar API", version="1.0.0")

configured_origins = [item.strip() for item in os.getenv("CORS_ALLOWED_ORIGINS", "http://localhost:5173").split(",") if item.strip()]
# Keep the configured origins and explicitly allow the production storefront plus Codespaces previews.
origins = list(dict.fromkeys(configured_origins + [
    "https://bw7rptzexc5.amplifyapp.com",
    "https://main.d33bw7rptzexc5.amplifyapp.com",
]))
@app.middleware("http")
async def return_json_for_unhandled_errors(request: Request, call_next):
    # Registered BEFORE CORSMiddleware so CORS wraps it: a server error then reaches the browser
    # with CORS headers and a readable message, instead of a bare "Failed to fetch".
    try:
        return await call_next(request)
    except Exception:
        logger.exception("Unhandled error on %s %s", request.method, request.url.path)
        return JSONResponse(status_code=500, content={"detail": "Server error while processing this request. Check backend logs."})


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


def attach_catalogue_media_and_attributes(conn: psycopg.Connection, rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Attach the saved product/variant details and images to each catalogue row."""
    if not rows:
        return rows
    tables = {
        name: bool(conn.execute("SELECT to_regclass(%s) AS t", (f"public.{name}",)).fetchone()["t"])
        for name in ("variant_attribute_values", "catalog_attributes", "product_variant_images")
    }
    product_columns = get_columns(conn, "products")
    variant_columns = get_columns(conn, "product_variants")
    for row in rows:
        variant_id, product_id = row.get("variant_id"), row.get("product_id")
        if variant_id and tables["variant_attribute_values"] and tables["catalog_attributes"]:
            saved = conn.execute(
                """SELECT a.name AS attribute_name, v.value AS attribute_value, a.display_type
                   FROM variant_attribute_values v JOIN catalog_attributes a ON a.id=v.attribute_id
                   WHERE v.variant_id=%s ORDER BY a.name""", (variant_id,)
            ).fetchall()
            if saved:
                row["attributes"] = saved
        if variant_id and tables["product_variant_images"]:
            gallery = conn.execute(
                """SELECT id, image_url, alt_text, sort_order FROM product_variant_images
                   WHERE variant_id=%s ORDER BY sort_order, id""", (variant_id,)
            ).fetchall()
            if gallery:
                row["gallery_images"] = gallery
                row["image_url"] = next((im["image_url"] for im in gallery if im.get("image_url")), row.get("image_url"))
        # Prefer a saved variant image; if absent, use the product's saved cover image.
        if product_id and product_columns:
            candidates = [c for c in ("cover_image_url", "main_image_url", "image_url", "image", "image_1920") if c in product_columns]
            if candidates and not row.get("image_url"):
                select = ", ".join(f'"{c}"' for c in candidates)
                saved_product = conn.execute(f"SELECT {select} FROM products WHERE id=%s", (product_id,)).fetchone()
                if saved_product:
                    for col in candidates:
                        value = saved_product.get(col)
                        if value:
                            row["image_url"] = value
                            break
            # Keep each product detail in its own field, not merged into the description.
            for col in ("description", "specifications", "manufacturer_details", "seller_details"):
                if col in product_columns and not row.get(col):
                    detail = conn.execute(f'SELECT "{col}" FROM products WHERE id=%s', (product_id,)).fetchone()
                    if detail and detail.get(col) is not None:
                        row[col] = detail[col]
        # Convert legacy Odoo binary/base64 image fields to browser-loadable data URLs.
        import base64
        for key in ("image_url", "image", "image_1920"):
            value = row.get(key)
            if isinstance(value, memoryview):
                value = value.tobytes()
            if isinstance(value, (bytes, bytearray)) and value:
                decoded = bytes(value)
                encoded = base64.b64encode(decoded).decode("ascii")
                if decoded.startswith(b"\xff\xd8\xff"): mime = "image/jpeg"
                elif decoded.startswith(b"RIFF") and decoded[8:12] == b"WEBP": mime = "image/webp"
                elif decoded.startswith(b"GIF8"): mime = "image/gif"
                elif decoded.startswith(b"\x89PNG\r\n\x1a\n"): mime = "image/png"
                else: mime = ""
                if mime:
                    row["image_url"] = f"data:{mime};base64,{encoded}"
                if key != "image_url":
                    row.pop(key, None)
            elif isinstance(value, str) and value and not value.startswith(("http://", "https://", "data:", "/")):
                try:
                    decoded = base64.b64decode(value, validate=True)
                    if decoded:
                        if decoded.startswith(b"\xff\xd8\xff"): mime = "image/jpeg"
                        elif decoded.startswith(b"RIFF") and decoded[8:12] == b"WEBP": mime = "image/webp"
                        elif decoded.startswith(b"GIF8"): mime = "image/gif"
                        elif decoded.startswith(b"\x89PNG\r\n\x1a\n"): mime = "image/png"
                        else: mime = ""
                        if mime:
                            row["image_url"] = f"data:{mime};base64,{base64.b64encode(decoded).decode('ascii')}"
                except Exception:
                    pass
    return rows


@app.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/api/admin/operations/readiness")
def operational_readiness(authorization: str | None = Header(default=None)) -> dict[str, Any]:
    """Return authenticated, real schema readiness checks for the admin dashboard."""
    from .auth import _require
    _require(authorization, {"super_admin", "admin"})
    try:
        with psycopg.connect(database_url(), row_factory=dict_row, connect_timeout=8) as conn:
            existing = {
                name: bool(conn.execute("SELECT to_regclass(%s) AS table_name", (f"public.{name}",)).fetchone()["table_name"])
                for name in (
                    "products", "product_variants", "catalog_attributes", "variant_attribute_values",
                    "sb_stock", "sb_stock_movements", "sb_inventory_ledger", "sb_warehouses",
                    "sb_purchase_orders", "sb_procurements", "sb_pos_sales", "sb_invoices",
                    "sb_accounts", "sb_journal_entries", "sb_employees", "sb_attendance",
                    "sb_payroll_runs", "sb_shipments", "orders",
                )
            }
            def item(label: str, required: tuple[str, ...], message: str) -> dict[str, Any]:
                missing = [table for table in required if not existing.get(table, False)]
                return {
                    "status": "connected" if not missing else "needs_setup",
                    "integrated": not missing,
                    "tables_detected": [table for table in required if existing.get(table, False)],
                    "message": message if not missing else "Missing required database tables: " + ", ".join(missing),
                }
            return {
                "catalogue": item("Catalogue", ("products", "product_variants"), "Product and variant tables are available."),
                "inventory": item("Inventory", ("sb_stock", "sb_stock_movements"), "Inventory ledger tables are available."),
                "delivery": item("Delivery", ("sb_shipments",), "Shipment table is available."),
                "payments": item("Payments", ("sb_invoices",), "Invoice/payment foundation is available."),
                "purchasing": item("Purchasing", ("sb_purchase_orders",), "Purchase-order table is available."),
                "accounting": item("Accounting", ("sb_accounts", "sb_journal_entries"), "Accounting tables are available."),
                "logistics": item("Logistics", ("sb_shipments",), "Shipment table is available."),
                "people": item("People", ("sb_employees", "sb_attendance", "sb_payroll_runs"), "HR and payroll tables are available."),
            }
    except HTTPException:
        raise
    except psycopg.Error as exc:
        logger.exception("Operational readiness database check failed")
        raise HTTPException(status_code=503, detail="Operational readiness could not query the database schema.") from exc




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
            image_candidates = []
            if "image_url" in variant_columns:
                image_candidates.append("NULLIF(v.image_url, '')")
            for image_column in ("cover_image_url", "main_image_url", "image_url"):
                if image_column in product_columns:
                    image_candidates.append(f"NULLIF(p.{image_column}, '')")
            image_select = ("COALESCE(" + ", ".join(image_candidates) + ") AS image_url") if image_candidates else "NULL::text AS image_url"
            brand_select = "p.brand AS brand" if "brand" in product_columns else "NULL::text AS brand"
            description_select = "p.description AS description" if "description" in product_columns else "NULL::text AS description"
            specification_select = "p.specifications AS specifications" if "specifications" in product_columns else "'[]'::jsonb AS specifications"
            manufacturer_select = "p.manufacturer_details AS manufacturer_details" if "manufacturer_details" in product_columns else "'[]'::jsonb AS manufacturer_details"
            seller_select = "p.seller_details AS seller_details" if "seller_details" in product_columns else "'[]'::jsonb AS seller_details"
            currency_select = "v.currency AS currency" if "currency" in variant_columns else "'INR'::text AS currency"
            product_status_select = "p.status AS status" if "status" in product_columns else "'active'::text AS status"
            variant_status_select = "v.status AS variant_status" if "status" in variant_columns else "'active'::text AS variant_status"
            # Preserve available human-readable variant attributes without assuming a fixed schema.
            attribute_columns = ("variant_type_name", "variant_type", "variant_value", "variant_type_value", "variant_short",
                                 "attribute_name", "attribute_value", "attributes", "attribute_values",
                                 "variant_attributes", "variant_label", "variant_name", "variant_description",
                                 "attribute_value_ids", "variant_attribute_values", "attribute_values_ids",
                                 "product_template_attribute_value_ids", "product_template_variant_value_ids",
                                 "quantity_label", "weight", "pack_size", "unit", "volume", "size")
            attribute_select = ", ".join(f"v.{column} AS {column}" for column in attribute_columns if column in variant_columns)
            attribute_select = (", " + attribute_select) if attribute_select else ""
            category_id_select = "p.category_id AS category_id" if "category_id" in product_columns else "NULL::bigint AS category_id"
            category_join = "LEFT JOIN product_categories c ON c.id = p.category_id" if "category_id" in product_columns else "LEFT JOIN product_categories c ON FALSE"
            category_parent_join = "LEFT JOIN product_categories cp ON cp.id = c.parent_id" if "parent_id" in category_columns else ""
            category_path_select = "COALESCE(cp.name || ' › ' || c.name, c.name) AS category_path" if "parent_id" in category_columns else "c.name AS category_path"
            reviews_table = conn.execute("SELECT to_regclass('public.product_reviews') AS table_name").fetchone()["table_name"]
            review_select = ("""COALESCE((SELECT AVG(r.rating)::numeric(3,2) FROM product_reviews r WHERE r.product_id=p.id AND r.status='approved'),0) AS average_rating,
                                COALESCE((SELECT COUNT(*)::int FROM product_reviews r WHERE r.product_id=p.id AND r.status='approved'),0) AS review_count"""
                             if reviews_table else "0::numeric AS average_rating, 0::int AS review_count")
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
                              {category_id_select}, {product_status_select}, {variant_status_select},
                              c.name AS category, {category_path_select}, v.id AS variant_id,
                              {('v.sku' if 'sku' in variant_columns else 'NULL::text AS sku')},
                              {('v.mrp' if 'mrp' in variant_columns else 'NULL::numeric AS mrp')},
                              {('v.selling_price' if 'selling_price' in variant_columns else 'NULL::numeric AS selling_price')},
                              {currency_select}, {image_select}, {specification_select}, {manufacturer_select}, {seller_select}, {review_select}{attribute_select}
                       FROM products p
                       JOIN product_variants v ON v.product_id = p.id
                       {category_join}
                       {category_parent_join}
                       WHERE {' AND '.join(where)}
                       ORDER BY p.name, v.id
                       LIMIT %s OFFSET %s"""
            rows = conn.execute(query, params).fetchall()
            rows = attach_catalogue_media_and_attributes(conn, rows)
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
            image_candidates = []
            if "image_url" in variant_columns:
                image_candidates.append("NULLIF(v.image_url, '')")
            for image_column in ("cover_image_url", "main_image_url", "image_url"):
                if image_column in product_columns:
                    image_candidates.append(f"NULLIF(p.{image_column}, '')")
            image_select = ("COALESCE(" + ", ".join(image_candidates) + ") AS image_url") if image_candidates else "NULL::text AS image_url"
            brand_select = "p.brand AS brand" if "brand" in product_columns else "NULL::text AS brand"
            description_select = "p.description AS description" if "description" in product_columns else "NULL::text AS description"
            specification_select = "p.specifications AS specifications" if "specifications" in product_columns else "'[]'::jsonb AS specifications"
            manufacturer_select = "p.manufacturer_details AS manufacturer_details" if "manufacturer_details" in product_columns else "'[]'::jsonb AS manufacturer_details"
            seller_select = "p.seller_details AS seller_details" if "seller_details" in product_columns else "'[]'::jsonb AS seller_details"
            currency_select = "v.currency AS currency" if "currency" in variant_columns else "'INR'::text AS currency"
            category_join = "LEFT JOIN product_categories c ON c.id = p.category_id" if "category_id" in product_columns else "LEFT JOIN product_categories c ON FALSE"
            sku_select = "v.sku AS sku" if "sku" in variant_columns else "NULL::text AS sku"
            mrp_select = "v.mrp AS mrp" if "mrp" in variant_columns else "NULL::numeric AS mrp"
            price_select = "v.selling_price AS selling_price" if "selling_price" in variant_columns else "NULL::numeric AS selling_price"
            attribute_columns = ("variant_type_name", "variant_type", "variant_value", "variant_type_value", "variant_short",
                                 "attribute_name", "attribute_value", "attributes", "attribute_values",
                                 "variant_attributes", "variant_label", "variant_name", "variant_description",
                                 "attribute_value_ids", "variant_attribute_values", "attribute_values_ids",
                                 "product_template_attribute_value_ids", "product_template_variant_value_ids",
                                 "quantity_label", "weight", "pack_size", "unit", "volume", "size")
            attribute_select = ", ".join(f"v.{column} AS {column}" for column in attribute_columns if column in variant_columns)
            attribute_select = (", " + attribute_select) if attribute_select else ""
            row = conn.execute(f"""SELECT p.id AS product_id, p.name, {description_select}, {brand_select},
                {specification_select}, {manufacturer_select}, {seller_select},
                c.name AS category, v.id AS variant_id, {sku_select}, {mrp_select},
                {price_select}, {currency_select}, {image_select}{attribute_select}
                FROM products p JOIN product_variants v ON v.product_id = p.id
                {category_join} WHERE v.id = %s AND {product_status} AND {variant_status}
                LIMIT 1""", (variant_id,)).fetchone()
            if not row:
                raise HTTPException(status_code=404, detail="Product not found")
            # Include sibling variants so the storefront can render one selector per
            # attribute even when a customer opens a product URL directly.
            sibling_variants = conn.execute(f"""SELECT p.id AS product_id, p.name, {description_select}, {brand_select},
                {specification_select}, {manufacturer_select}, {seller_select},
                c.name AS category, v.id AS variant_id, {sku_select}, {mrp_select},
                {price_select}, {currency_select}, {image_select}{attribute_select}
                FROM products p JOIN product_variants v ON v.product_id = p.id
                {category_join} WHERE p.id = %s AND {product_status} AND {variant_status}
                ORDER BY v.id""", (row["product_id"],)).fetchall()
            sibling_variants = attach_catalogue_media_and_attributes(conn, sibling_variants)
            row = attach_catalogue_media_and_attributes(conn, [row])[0]
            return {**row, "_variants": sibling_variants}
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



class VariantImageInput(BaseModel):
    image_url: str = Field(min_length=1, max_length=6000000)
    alt_text: str = Field(default="", max_length=240)
    sort_order: int = Field(default=0, ge=0, le=10000)


@app.post("/api/admin/products/{product_id}/variants/{variant_id}/images", status_code=201)
def add_variant_image(product_id: int, variant_id: int, body: VariantImageInput, authorization: str | None = Header(default=None)) -> dict[str, Any]:
    _admin_catalogue_user(authorization)
    image_url = body.image_url.strip()
    if not (image_url.startswith("https://") or image_url.startswith("http://") or image_url.startswith("data:image/")):
        raise HTTPException(status_code=422, detail="Use an HTTP(S) image URL or a valid image upload.")
    if image_url.startswith("data:image/") and ";base64," not in image_url:
        raise HTTPException(status_code=422, detail="Uploaded images must be encoded as an image data URL.")
    try:
        with psycopg.connect(database_url(), row_factory=dict_row, connect_timeout=8) as conn:
            if not conn.execute("SELECT id FROM product_variants WHERE id=%s AND product_id=%s", (variant_id, product_id)).fetchone():
                raise HTTPException(status_code=404, detail="Product variant not found.")
            if not conn.execute("SELECT to_regclass('public.product_variant_images') AS t").fetchone()["t"]:
                raise HTTPException(status_code=503, detail="Apply the dynamic catalogue schema migration first.")
            row = conn.execute(
                """INSERT INTO product_variant_images(variant_id,image_url,alt_text,sort_order)
                   VALUES(%s,%s,%s,%s) RETURNING id,variant_id,image_url,alt_text,sort_order,created_at""",
                (variant_id, image_url, body.alt_text.strip(), body.sort_order)
            ).fetchone()
            return {"image": row}
    except HTTPException:
        raise
    except psycopg.Error as exc:
        logger.exception("Variant image save failed")
        raise HTTPException(status_code=503, detail="Variant image could not be saved.") from exc


class ProductWriteInput(BaseModel):
    name: str = Field(min_length=1, max_length=240)
    selling_price: float = Field(gt=0, le=9999999999)
    mrp: float | None = Field(default=None, gt=0, le=9999999999)
    brand: str = Field(default="", max_length=160)
    description: str = Field(default="", max_length=4000)
    specifications: list[dict[str, str]] = Field(default_factory=list, max_length=100)
    manufacturer_details: list[dict[str, str]] = Field(default_factory=list, max_length=100)
    seller_details: list[dict[str, str]] = Field(default_factory=list, max_length=100)
    category_id: int | None = Field(default=None, gt=0)
    sku: str = Field(default="", max_length=120)
    # Image data URLs for 4 MB uploads are much longer than ordinary HTTP URLs.
    image_url: str = Field(default="", max_length=6000000)
    # When editing a product row, target the selected variant instead of silently changing the first one.
    variant_id: int | None = Field(default=None, gt=0)
    status: str = Field(default="active", pattern="^(active|inactive|draft)$")


def _admin_catalogue_user(authorization: str | None) -> dict[str, Any]:
    from .auth import _require
    return _require(authorization, {"super_admin", "admin"})


def _catalogue_columns(conn: Any, table: str) -> dict[str, dict[str, Any]]:
    rows = conn.execute(
        """SELECT column_name, is_nullable, column_default, is_identity
           FROM information_schema.columns
           WHERE table_schema=current_schema() AND table_name=%s""", (table,)
    ).fetchall()
    return {r["column_name"]: r for r in rows}


def _catalogue_insert(conn: Any, table: str, values: dict[str, Any]) -> dict[str, Any]:
    columns = _catalogue_columns(conn, table)
    if not columns:
        raise HTTPException(status_code=503, detail=f"The existing {table} table is unavailable.")
    chosen = {k: v for k, v in values.items() if k in columns and k != "id" and v is not None}
    missing = [name for name, meta in columns.items()
               if name not in chosen and name != "id" and meta["is_nullable"] == "NO"
               and meta["column_default"] is None and meta["is_identity"] != "YES"]
    if missing:
        raise HTTPException(status_code=503, detail=f"Catalogue schema requires additional fields: {', '.join(sorted(missing))}.")
    if not chosen:
        raise HTTPException(status_code=503, detail=f"No compatible fields found for {table}.")
    names = list(chosen)
    sql = f"INSERT INTO {table} ({', '.join(names)}) VALUES ({', '.join(['%s'] * len(names))}) RETURNING *"
    return conn.execute(sql, [chosen[k] for k in names]).fetchone()


@app.post("/api/admin/products", status_code=201)
def create_catalogue_product(
    body: ProductWriteInput,
    authorization: str | None = Header(default=None),
) -> dict[str, Any]:
    _admin_catalogue_user(authorization)
    try:
        with psycopg.connect(database_url(), row_factory=dict_row, connect_timeout=8) as conn:
            product_columns = _catalogue_columns(conn, "products")
            variant_columns = _catalogue_columns(conn, "product_variants")
            if not product_columns or not variant_columns:
                raise HTTPException(status_code=503, detail="The existing catalogue schema is unavailable.")
            # Keep the cover image attached to the product record where the existing
            # schema supports a text URL column, while retaining the variant image
            # below for storefronts that select a specific variant.
            cover_url = body.image_url.strip() or None
            product_values = {"product_code": "SB-" + uuid.uuid4().hex[:12].upper(),
                              "name": body.name.strip(), "brand": body.brand.strip(),
                              "description": body.description.strip(), "specifications": Jsonb(body.specifications),
                              "manufacturer_details": Jsonb(body.manufacturer_details), "seller_details": Jsonb(body.seller_details),
                              "category_id": body.category_id, "status": body.status,
                              "cover_image_url": cover_url, "main_image_url": cover_url, "image_url": cover_url}
            product = _catalogue_insert(conn, "products", product_values)
            variant_values = {"product_id": product["id"], "selling_price": body.selling_price,
                              "mrp": body.mrp, "sku": body.sku.strip() or None,
                              "image_url": body.image_url.strip() or None, "status": body.status}
            variant = _catalogue_insert(conn, "product_variants", variant_values)
            return {"product": product, "variant": variant}
    except HTTPException:
        raise
    except psycopg.Error as exc:
        logger.exception("Catalogue product creation failed")
        raise HTTPException(status_code=503, detail="Product could not be saved to the catalogue.") from exc


@app.put("/api/admin/products/{product_id}")
def update_catalogue_product(
    product_id: int,
    body: ProductWriteInput,
    authorization: str | None = Header(default=None),
) -> dict[str, Any]:
    _admin_catalogue_user(authorization)
    try:
        with psycopg.connect(database_url(), row_factory=dict_row, connect_timeout=8) as conn:
            product_columns = _catalogue_columns(conn, "products")
            variant_columns = _catalogue_columns(conn, "product_variants")
            if not product_columns or not variant_columns:
                raise HTTPException(status_code=503, detail="The existing catalogue schema is unavailable.")
            # Update the product-level cover as well as the selected variant image.
            # _catalogue_columns filters these optional fields to the columns that
            # actually exist, so this remains compatible with the live schema.
            cover_url = body.image_url.strip() or None
            product_values = {"name": body.name.strip(), "brand": body.brand.strip(),
                              "description": body.description.strip(), "specifications": Jsonb(body.specifications),
                              "manufacturer_details": Jsonb(body.manufacturer_details), "seller_details": Jsonb(body.seller_details),
                              "category_id": body.category_id, "status": body.status,
                              "cover_image_url": cover_url, "main_image_url": cover_url, "image_url": cover_url}
            product_values = {k: v for k, v in product_values.items() if k in product_columns}
            if not product_values:
                raise HTTPException(status_code=503, detail="The product schema has no editable fields.")
            assignments = ", ".join(f"{k}=%s" for k in product_values)
            product = conn.execute(
                f"UPDATE products SET {assignments} WHERE id=%s RETURNING *",
                [*product_values.values(), product_id]
            ).fetchone()
            if not product:
                raise HTTPException(status_code=404, detail="Product not found.")
            variant_values = {"selling_price": body.selling_price, "mrp": body.mrp,
                              "sku": body.sku.strip() or None, "image_url": body.image_url.strip() or None,
                              "status": body.status}
            variant_values = {k: v for k, v in variant_values.items() if k in variant_columns and v is not None}
            if body.variant_id is not None:
                variant = conn.execute(
                    "SELECT id FROM product_variants WHERE id=%s AND product_id=%s",
                    (body.variant_id, product_id),
                ).fetchone()
                if not variant:
                    raise HTTPException(status_code=404, detail="Selected variant does not belong to this product.")
            else:
                # Backward compatibility for older clients that only send product_id.
                variant = conn.execute(
                    "SELECT id FROM product_variants WHERE product_id=%s ORDER BY id LIMIT 1", (product_id,)
                ).fetchone()
            if variant and variant_values:
                assignments = ", ".join(f"{k}=%s" for k in variant_values)
                variant = conn.execute(
                    f"UPDATE product_variants SET {assignments} WHERE id=%s AND product_id=%s RETURNING *",
                    [*variant_values.values(), variant["id"], product_id]
                ).fetchone()
            else:
                raise HTTPException(status_code=404, detail="No variant exists for this product.")
            return {"product": product, "variant": variant}
    except HTTPException:
        raise
    except psycopg.Error as exc:
        logger.exception("Catalogue product update failed")
        raise HTTPException(status_code=503, detail="Product could not be updated.") from exc


class CategoryWriteInput(BaseModel):
    name: str = Field(min_length=1, max_length=160)
    parent_id: int | None = Field(default=None, gt=0)
    status: str = Field(default="active", pattern="^(active|inactive)$")


def _category_values(columns: dict[str, dict[str, Any]], name: str, parent_id: int | None, status: str) -> dict[str, Any]:
    clean_name = name.strip()
    slug = "-".join(part for part in re.sub(r"[^a-z0-9]+", "-", clean_name.lower()).strip("-").split("-") if part)
    candidates: dict[str, Any] = {
        "name": clean_name, "parent_id": parent_id, "status": status,
        "slug": slug, "code": slug.upper().replace("-", "_"),
        "category_code": slug.upper().replace("-", "_") or "CATEGORY",
        # Existing deployments may require category_code rather than code/slug.
        "category_code": slug.upper().replace("-", "_") or "CATEGORY",
        "description": "", "sort_order": 0, "position": 0,
        "is_active": status == "active", "active": status == "active",
    }
    return {key: value for key, value in candidates.items() if key in columns and (value is not None or key in {"parent_id"})}


@app.post("/api/admin/categories", status_code=201)
def create_catalogue_category(body: CategoryWriteInput, authorization: str | None = Header(default=None)) -> dict[str, Any]:
    _admin_catalogue_user(authorization)
    clean_name = body.name.strip()
    if not clean_name:
        raise HTTPException(status_code=422, detail="Enter a category name.")
    try:
        with psycopg.connect(database_url(), row_factory=dict_row, connect_timeout=8) as conn:
            columns = _catalogue_columns(conn, "product_categories")
            if not columns:
                raise HTTPException(status_code=503, detail="The existing category table is unavailable.")
            if body.parent_id is not None:
                if "parent_id" not in columns:
                    raise HTTPException(status_code=503, detail="Category nesting is not available in the current database schema.")
                if not conn.execute("SELECT id FROM product_categories WHERE id=%s", (body.parent_id,)).fetchone():
                    raise HTTPException(status_code=422, detail="Selected parent category does not exist.")
            values = _category_values(columns, clean_name, body.parent_id, body.status)
            return {"category": _catalogue_insert(conn, "product_categories", values)}
    except HTTPException:
        raise
    except psycopg.Error as exc:
        logger.exception("Category creation failed for name=%r parent_id=%r", clean_name, body.parent_id)
        raise HTTPException(status_code=503, detail="Category could not be saved. Check the category table constraints and server log.") from exc


@app.put("/api/admin/categories/{category_id}")
def update_catalogue_category(category_id: int, body: CategoryWriteInput, authorization: str | None = Header(default=None)) -> dict[str, Any]:
    _admin_catalogue_user(authorization)
    clean_name = body.name.strip()
    if not clean_name:
        raise HTTPException(status_code=422, detail="Enter a category name.")
    try:
        with psycopg.connect(database_url(), row_factory=dict_row, connect_timeout=8) as conn:
            columns = _catalogue_columns(conn, "product_categories")
            if not columns:
                raise HTTPException(status_code=503, detail="The existing category table is unavailable.")
            existing = conn.execute("SELECT id FROM product_categories WHERE id=%s", (category_id,)).fetchone()
            if not existing:
                raise HTTPException(status_code=404, detail="Category not found.")
            if body.parent_id == category_id:
                raise HTTPException(status_code=422, detail="A category cannot be its own parent.")
            if body.parent_id is not None:
                if "parent_id" not in columns:
                    raise HTTPException(status_code=503, detail="Category nesting is not available in the current database schema.")
                if not conn.execute("SELECT id FROM product_categories WHERE id=%s", (body.parent_id,)).fetchone():
                    raise HTTPException(status_code=422, detail="Selected parent category does not exist.")
                # Prevent cycles, including moving a category under one of its descendants.
                if conn.execute("""WITH RECURSIVE descendants(id) AS (
                    SELECT id FROM product_categories WHERE parent_id=%s
                    UNION ALL SELECT c.id FROM product_categories c JOIN descendants d ON c.parent_id=d.id
                ) SELECT 1 FROM descendants WHERE id=%s LIMIT 1""", (category_id, body.parent_id)).fetchone():
                    raise HTTPException(status_code=422, detail="A category cannot be moved under its own subcategory.")
            values = _category_values(columns, clean_name, body.parent_id, body.status)
            values = {key: value for key, value in values.items() if key in columns and key != "id"}
            assignments = ", ".join(f"{key}=%s" for key in values)
            row = conn.execute(f"UPDATE product_categories SET {assignments} WHERE id=%s RETURNING *", [*values.values(), category_id]).fetchone()
            return {"category": row}
    except HTTPException:
        raise
    except psycopg.Error as exc:
        logger.exception("Category update failed for id=%s", category_id)
        raise HTTPException(status_code=503, detail="Category could not be updated. Check the category table constraints and server log.") from exc


@app.get("/api/categories")
def list_categories(include_inactive: bool = False) -> dict[str, Any]:
    try:
        with psycopg.connect(database_url(), row_factory=dict_row, connect_timeout=8) as conn:
            columns = get_columns(conn, "product_categories")
            if not columns:
                raise HTTPException(status_code=503, detail="The existing category table is not available")
            status_filter = "" if include_inactive or "status" not in columns else "WHERE c.status = 'active'"
            parent_join = "LEFT JOIN product_categories parent ON parent.id = c.parent_id" if "parent_id" in columns else ""
            parent_select = "c.parent_id AS parent_id, parent.name AS parent_name" if "parent_id" in columns else "NULL::bigint AS parent_id, NULL::text AS parent_name"
            path_select = """CASE WHEN c.parent_id IS NULL THEN c.name ELSE
                COALESCE((WITH RECURSIVE ancestors(id, parent_id, name, depth) AS (
                    SELECT p.id, p.parent_id, p.name, 1 FROM product_categories p WHERE p.id=c.parent_id
                    UNION ALL SELECT p.id, p.parent_id, p.name, a.depth+1
                    FROM product_categories p JOIN ancestors a ON p.id=a.parent_id WHERE a.depth < 20
                ) SELECT string_agg(name, ' › ' ORDER BY depth DESC) FROM ancestors), '') || ' › ' || c.name END AS category_path""" if "parent_id" in columns else "c.name AS category_path"
            rows = conn.execute(f"""SELECT c.id, c.name, {parent_select}, {path_select}
                FROM product_categories c
                {parent_join}
                {status_filter}
                ORDER BY category_path""").fetchall()
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


# Authentication and role-based user administration are isolated from catalogue routes.
from .auth import router as auth_router
app.include_router(auth_router)


# Authenticated checkout, order management, and persisted store settings.
from .commerce import router as commerce_router
app.include_router(commerce_router)


# Accounting foundation: chart of accounts, GST setup, journals and P&L.
from .accounting import router as accounting_router
app.include_router(accounting_router)


# Shared operational APIs: customers, vendors, inventory, POS, purchasing, logistics and payroll.
from .operations import router as operations_router
app.include_router(operations_router)

# Sales invoices are created transactionally by POS and website checkout, then confirmed/paid by staff.
from .invoices import router as invoices_router
app.include_router(invoices_router)


from .loyalty import router as loyalty_router
app.include_router(loyalty_router)


# Advanced configurable catalogue, procurement, warehouse, returns and vendor portal APIs.
# Kept in a separate router so existing production operations endpoints remain intact.
from .integrated_operations import router as integrated_operations_router
app.include_router(integrated_operations_router)
