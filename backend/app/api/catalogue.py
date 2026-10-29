"""PostgreSQL-backed catalogue, attribute and variant API foundation."""
from typing import Any

import psycopg
from fastapi import APIRouter, File, Form, HTTPException, Query, Request, UploadFile
from psycopg.rows import dict_row
from pydantic import BaseModel, Field, field_validator
from uuid import uuid4

from app.core.config import settings

router = APIRouter(prefix="/catalogue", tags=["catalogue"])


class CategoryCreate(BaseModel):
    name: str = Field(min_length=1, max_length=160)
    slug: str = Field(min_length=1, max_length=180, pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
    description: str | None = None
    parent_id: int | None = Field(default=None, gt=0)

    @field_validator("name")
    @classmethod
    def name_not_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("Category name cannot be blank")
        return value.strip()


class ProductCreate(BaseModel):
    name: str = Field(min_length=1, max_length=240)
    slug: str = Field(min_length=1, max_length=260, pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
    category_id: int | None = Field(default=None, gt=0)
    description: str | None = None
    brand: str | None = Field(default=None, max_length=160)
    tax_code: str | None = Field(default=None, max_length=32)
    tax_rate: float | None = Field(default=None, ge=0, le=100)
    status: str = Field(default="active", pattern=r"^(draft|active)$")
    is_pos_available: bool = True
    is_website_available: bool = True
    delivery_options: list[str] = Field(default_factory=lambda: ["standard"], max_length=2)

    @field_validator("delivery_options")
    @classmethod
    def valid_delivery_options(cls, value: list[str]) -> list[str]:
        allowed = {"standard", "express"}
        if not value or len(set(value)) != len(value) or any(item not in allowed for item in value):
            raise ValueError("Select Standard and/or Express delivery")
        return value

    @field_validator("name")
    @classmethod
    def name_not_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("Product name cannot be blank")
        return value.strip()


class AttributeCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    code: str = Field(min_length=1, max_length=120, pattern=r"^[a-z][a-z0-9_]*$")
    value_type: str = Field(pattern=r"^(text|number|boolean|date|select|multi_select|colour|size)$")
    is_variant_attribute: bool = False
    is_required: bool = False
    options: list[Any] = Field(default_factory=list, max_length=200, validate_default=True)

    @field_validator("name")
    @classmethod
    def attribute_name_not_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("Attribute name cannot be blank")
        return value.strip()

    @field_validator("options")
    @classmethod
    def options_for_select_types(cls, value: list[Any], info):
        value_type = info.data.get("value_type")
        if value_type in {"select", "multi_select", "colour", "size"} and not value:
            raise ValueError("This attribute type requires at least one option")
        if value_type not in {"select", "multi_select", "colour", "size"} and value:
            raise ValueError("Options are only supported for select, multi_select, colour and size attributes")
        if any(not isinstance(option, (str, int, float, bool)) for option in value):
            raise ValueError("Attribute options must be simple scalar values")
        if len({str(option) for option in value}) != len(value):
            raise ValueError("Attribute options must be unique")
        return value



class ProductImageCreate(BaseModel):
    image_url: str = Field(min_length=8, max_length=2048)
    alt_text: str | None = Field(default=None, max_length=300)
    variant_id: int | None = Field(default=None, gt=0)
    sort_order: int = Field(default=0, ge=0, le=10000)
    is_primary: bool = False

    @field_validator("image_url")
    @classmethod
    def image_url_must_be_http(cls, value: str) -> str:
        from urllib.parse import urlparse
        parsed = urlparse(value.strip())
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise ValueError("Image URL must be an absolute HTTP or HTTPS URL")
        return value.strip()


class AttributeValueCreate(BaseModel):
    value: Any


class VariantCreate(BaseModel):
    sku: str | None = Field(default=None, max_length=100)
    barcode: str | None = Field(default=None, max_length=100)
    attributes: dict[str, Any] = Field(default_factory=dict)
    selling_price: float = Field(ge=0)
    mrp: float | None = Field(default=None, ge=0)
    cost_price: float | None = Field(default=None, ge=0)

    @field_validator("sku")
    @classmethod
    def normalize_optional_sku(cls, value: str | None) -> str | None:
        if value is None or not value.strip():
            return None
        return value.strip()

    @field_validator("mrp")
    @classmethod
    def mrp_not_below_selling_price(cls, value, info):
        selling = info.data.get("selling_price")
        if value is not None and selling is not None and value < selling:
            raise ValueError("MRP cannot be below selling price")
        return value


def _connection():
    if not settings.database_url:
        raise HTTPException(status_code=503, detail="Catalogue database is not configured")
    try:
        return psycopg.connect(settings.database_url, row_factory=dict_row, connect_timeout=3)
    except psycopg.Error as exc:
        raise HTTPException(status_code=503, detail="Catalogue database is unavailable") from exc


def _db_error(exc: psycopg.Error) -> HTTPException:
    code = getattr(exc, "sqlstate", None)
    if code == "23505":
        return HTTPException(status_code=409, detail="A record with this unique value already exists")
    if code == "23503":
        return HTTPException(status_code=422, detail="A referenced record does not exist")
    if code == "23514":
        return HTTPException(status_code=422, detail="The value violates a catalogue validation rule")
    return HTTPException(status_code=503, detail="Catalogue database operation failed")


def _require_product(conn, product_id: int) -> dict[str, Any]:
    row = conn.execute("SELECT id, status FROM products WHERE id = %s", (product_id,)).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="Product not found")
    return row


def _sku_token(value: Any, limit: int = 8) -> str:
    import re
    token = re.sub(r"[^A-Z0-9]+", "-", str(value or "").upper()).strip("-")
    return token[:limit].strip("-") or "GEN"

def _category_sku_code(category_name: str | None) -> str:
    import re
    slug = re.sub(r"[^a-z0-9]+", "-", (category_name or "").lower()).strip("-")
    mappings = {"fashion": "FS", "clothing": "FS", "apparel": "FS", "footwear": "FS", "grocery": "GR", "groceries": "GR", "electronics": "EL", "personal-care": "PC", "beauty": "PC", "pet-care": "PT", "fresh-products": "FR", "fresh": "FR", "home-kitchen": "HK"}
    if slug in mappings:
        return mappings[slug]
    return "".join(part[0] for part in slug.split("-") if part)[:3].upper() or "OT"

def _generate_variant_sku(conn, product_id: int, attributes: dict[str, Any]) -> str:
    product = conn.execute("SELECT p.id, p.name, p.brand, COALESCE(parent.name, c.name) AS category_name, c.name AS subcategory_name FROM products p LEFT JOIN categories c ON c.id = p.category_id LEFT JOIN categories parent ON parent.id = c.parent_id WHERE p.id = %s", (product_id,)).fetchone()
    if product is None:
        raise HTTPException(status_code=404, detail="Product not found")
    category_code = _category_sku_code(product["category_name"])
    normalized = {str(key).lower(): value for key, value in attributes.items()}
    department = str(next((normalized[key] for key in ("gender", "department", "audience") if key in normalized), product["subcategory_name"] or "")).strip().lower()
    department_code = "M" if department in {"m", "men", "mens", "male", "man"} else "W" if department in {"w", "women", "womens", "female", "woman"} else "K" if department in {"k", "kids", "kid", "children", "child"} else "U"
    brand_code = _sku_token(product["brand"], 8)
    product_name = str(product["name"]).upper()
    product_type_codes = [
        (("T-SHIRT", "TSHIRT", "TEE"), "TSH"),
        (("RICE",), "RIC"),
        (("JEAN", "DENIM"), "JNS"),
        (("SNEAKER", "SHOE", "FOOTWEAR"), "SH"),
        (("DRESS",), "DRS"),
        (("PHONE", "SMARTPHONE"), "PHN"),
        (("LAPTOP", "NOTEBOOK"), "LTP"),
        (("DETERGENT",), "DTR"),
        (("MILK",), "MLK"),
    ]
    product_code = next((code for terms, code in product_type_codes if any(term in product_name for term in terms)), "")
    if not product_code:
        words = [word for word in product_name.replace("-", " ").split() if word]
        product_code = _sku_token("".join(word[0] for word in words[:4]) or "PROD", 6)
    variant_tokens = []
    for key in sorted(attributes):
        value = attributes[key]
        if isinstance(value, (str, int, float)) and str(value).strip():
            variant_tokens.append(_sku_token(value, 8))
        elif isinstance(value, list):
            variant_tokens.extend(_sku_token(item, 8) for item in value if str(item).strip())
    base = f"SB-{category_code}-{department_code}-{brand_code}-{product_code}-{int(product_id):05d}"
    if variant_tokens:
        base += "-" + "-".join(variant_tokens[:4])
    existing = conn.execute("SELECT sku FROM product_variants WHERE product_id = %s ORDER BY id", (product_id,)).fetchall()
    version = len(existing) + 1
    while True:
        candidate = f"{base}-V{version:02d}"
        collision = conn.execute("SELECT 1 FROM product_variants WHERE sku = %s LIMIT 1", (candidate,)).fetchone()
        if collision is None:
            return candidate
        version += 1

def _validate_attribute_value(conn, attribute: dict[str, Any], value: Any) -> None:
    kind = attribute["value_type"]
    options = attribute["options"] or []
    valid = True
    if kind in {"select", "colour", "size"}:
        valid = value in options
    elif kind == "multi_select":
        valid = isinstance(value, list) and all(item in options for item in value) and len(value) == len(set(map(str, value)))
    elif kind == "text":
        valid = isinstance(value, str)
    elif kind == "number":
        valid = isinstance(value, (int, float)) and not isinstance(value, bool)
    elif kind == "boolean":
        valid = isinstance(value, bool)
    elif kind == "date":
        valid = isinstance(value, str) and len(value) == 10 and value[4:5] == "-" and value[7:8] == "-"
    if not valid:
        raise HTTPException(status_code=422, detail=f"Invalid value for attribute '{attribute['name']}'")


@router.get("/categories")
def list_categories(request: Request, limit: int = Query(default=100, ge=1, le=500), offset: int = Query(default=0, ge=0)):
    with _connection() as conn:
        rows = conn.execute(
            "SELECT id, parent_id, name, slug, description, is_active, created_at, updated_at "
            "FROM categories WHERE is_active = TRUE ORDER BY name LIMIT %s OFFSET %s", (limit, offset)
        ).fetchall()
    return {"items": rows, "limit": limit, "offset": offset}


@router.post("/categories", status_code=201)
def create_category(payload: CategoryCreate):
    try:
        with _connection() as conn:
            row = conn.execute(
                "INSERT INTO categories (parent_id, name, slug, description) VALUES (%s, %s, %s, %s) "
                "RETURNING id, parent_id, name, slug, description, is_active, created_at, updated_at",
                (payload.parent_id, payload.name, payload.slug, payload.description),
            ).fetchone()
        return row
    except psycopg.Error as exc:
        raise _db_error(exc) from exc


class CategoryUpdate(CategoryCreate):
    pass


@router.put("/categories/{category_id}")
def update_category(category_id: int, payload: CategoryUpdate):
    try:
        with _connection() as conn:
            current = conn.execute(
                "SELECT id FROM categories WHERE id=%s AND is_active=TRUE FOR UPDATE",
                (category_id,),
            ).fetchone()
            if current is None:
                raise HTTPException(status_code=404, detail="Active category not found")
            if payload.parent_id is not None:
                descendant = conn.execute(
                    "WITH RECURSIVE descendants(id, path) AS ("
                    "SELECT id, ARRAY[id] FROM categories WHERE parent_id=%s "
                    "UNION ALL "
                    "SELECT c.id, d.path || c.id FROM categories c "
                    "JOIN descendants d ON c.parent_id=d.id WHERE NOT c.id = ANY(d.path)"
                    ") SELECT 1 FROM descendants WHERE id=%s LIMIT 1",
                    (category_id, payload.parent_id),
                ).fetchone()
                if payload.parent_id == category_id or descendant is not None:
                    raise HTTPException(status_code=422, detail="A category cannot be nested under itself or its descendant")
            row = conn.execute(
                "UPDATE categories SET parent_id=%s, name=%s, slug=%s, description=%s, updated_at=now() "
                "WHERE id=%s AND is_active=TRUE "
                "RETURNING id, parent_id, name, slug, description, is_active, created_at, updated_at",
                (payload.parent_id, payload.name, payload.slug, payload.description, category_id),
            ).fetchone()
        return row
    except HTTPException:
        raise
    except psycopg.Error as exc:
        raise _db_error(exc) from exc


@router.get("/products")
def list_products(
    request: Request,
    category_id: int | None = Query(default=None, gt=0),
    status: str = Query(default="active", pattern="^(draft|active|archived|all)$"),
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
):
    clauses: list[str] = []
    params: list[Any] = []
    if category_id is not None:
        clauses.append("category_id = %s")
        params.append(category_id)
    public_catalogue = getattr(request.state, "public_catalogue", False)
    if public_catalogue:
        status = "active"
        clauses.append("is_website_available = TRUE")
    if status != "all":
        clauses.append("status = %s")
        params.append(status)
    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    params.extend([limit, offset])
    stock_projection = (
        "(SELECT SUM(ib.on_hand - ib.reserved) FROM inventory_balances ib "
        "JOIN product_variants stock_variant ON stock_variant.id=ib.variant_id "
        "JOIN stock_locations sl ON sl.id=ib.location_id "
        "WHERE stock_variant.product_id=p.id AND stock_variant.is_active=TRUE AND sl.is_active=TRUE) AS available_stock"
        if not public_catalogue else "NULL::numeric AS available_stock"
    )
    with _connection() as conn:
        rows = conn.execute(
            "SELECT p.id, p.category_id, p.name, p.slug, p.description, p.brand, p.status, p.tax_code, p.tax_rate, p.is_pos_available, p.is_website_available, p.delivery_options, p.created_at, p.updated_at, "
            "(SELECT COUNT(*) FROM product_variants v WHERE v.product_id=p.id AND v.is_active=TRUE) AS variant_count, "
            "(SELECT MIN(v.selling_price) FROM product_variants v WHERE v.product_id=p.id AND v.is_active=TRUE) AS min_selling_price, "
            "(SELECT MAX(v.selling_price) FROM product_variants v WHERE v.product_id=p.id AND v.is_active=TRUE) AS max_selling_price, "
            "(SELECT MIN(v.mrp) FROM product_variants v WHERE v.product_id=p.id AND v.is_active=TRUE) AS min_mrp, "
            f"{stock_projection} "
            f"FROM products p {where} ORDER BY p.name LIMIT %s OFFSET %s", tuple(params)
        ).fetchall()
    return {"items": rows, "limit": limit, "offset": offset}


@router.post("/products", status_code=201)
def create_product(payload: ProductCreate):
    try:
        with _connection() as conn:
            row = conn.execute(
                "INSERT INTO products (category_id, name, slug, description, brand, tax_code, tax_rate, status, is_pos_available, is_website_available, delivery_options) "
                "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s) "
                "RETURNING id, category_id, name, slug, description, brand, status, tax_code, tax_rate, is_pos_available, is_website_available, delivery_options, created_at, updated_at",
                (payload.category_id, payload.name, payload.slug, payload.description, payload.brand, payload.tax_code, payload.tax_rate, payload.status, payload.is_pos_available, payload.is_website_available, payload.delivery_options),
            ).fetchone()
        return row
    except psycopg.Error as exc:
        raise _db_error(exc) from exc


class ProductUpdate(ProductCreate):
    status: str = Field(default="active", pattern=r"^(draft|active|archived)$")

@router.put("/products/{product_id}")
def update_product(product_id: int, payload: ProductUpdate):
    try:
        with _connection() as conn:
            row = conn.execute("UPDATE products SET category_id=%s,name=%s,slug=%s,description=%s,brand=%s,tax_code=%s,tax_rate=%s,status=%s,is_pos_available=%s,is_website_available=%s,delivery_options=%s,updated_at=now() WHERE id=%s RETURNING id,category_id,name,slug,description,brand,status,tax_code,tax_rate,is_pos_available,is_website_available,delivery_options,created_at,updated_at", (payload.category_id,payload.name,payload.slug,payload.description,payload.brand,payload.tax_code,payload.tax_rate,payload.status,payload.is_pos_available,payload.is_website_available,payload.delivery_options,product_id)).fetchone()
            if row is None:
                raise HTTPException(status_code=404, detail="Product not found")
        return row
    except HTTPException:
        raise
    except psycopg.Error as exc:
        raise _db_error(exc) from exc

@router.post("/products/{product_id}/archive")
def archive_product(product_id: int):
    with _connection() as conn:
        row = conn.execute("UPDATE products SET status='archived',updated_at=now() WHERE id=%s AND status <> 'archived' RETURNING id,name,status", (product_id,)).fetchone()
        if row is None:
            raise HTTPException(status_code=404, detail="Product not found or already archived")
    return row

class AvailabilityRuleCreate(BaseModel):
    channel: str = Field(pattern=r"^(pos|website)$")
    region_code: str | None = Field(default=None, max_length=80)
    pincode: str | None = Field(default=None, pattern=r"^[0-9]{6}$")
    location_id: int | None = Field(default=None, gt=0)
    is_allowed: bool = True

    @field_validator("region_code")
    @classmethod
    def normalize_region(cls, value: str | None) -> str | None:
        return value.strip() if value and value.strip() else None


@router.get("/stock-locations")
def list_catalogue_stock_locations():
    with _connection() as conn:
        rows = conn.execute(
            "SELECT id, name, location_type, pin_code FROM stock_locations WHERE is_active=TRUE ORDER BY name"
        ).fetchall()
    return {"items": rows}


@router.get("/products/{product_id}/availability-rules")
def list_product_availability_rules(product_id: int):
    with _connection() as conn:
        _require_product(conn, product_id)
        rows = conn.execute(
            "SELECT id, product_id, channel, region_code, pincode, location_id, is_allowed, created_at "
            "FROM product_availability_rules WHERE product_id=%s ORDER BY channel, id",
            (product_id,),
        ).fetchall()
    return {"items": rows}


@router.put("/products/{product_id}/availability-rules")
def replace_product_availability_rules(product_id: int, payload: list[AvailabilityRuleCreate]):
    try:
        with _connection() as conn:
            _require_product(conn, product_id)
            for rule in payload:
                if not (rule.region_code or rule.pincode or rule.location_id):
                    raise HTTPException(status_code=422, detail="Each availability rule needs a region, pincode or warehouse")
                if rule.location_id is not None:
                    location = conn.execute(
                        "SELECT id FROM stock_locations WHERE id=%s AND is_active=TRUE",
                        (rule.location_id,),
                    ).fetchone()
                    if location is None:
                        raise HTTPException(status_code=422, detail="Selected warehouse/store location is not active")
            conn.execute("DELETE FROM product_availability_rules WHERE product_id=%s", (product_id,))
            rows = []
            for rule in payload:
                rows.append(conn.execute(
                    "INSERT INTO product_availability_rules (product_id,channel,region_code,pincode,location_id,is_allowed) "
                    "VALUES (%s,%s,%s,%s,%s,%s) RETURNING id,product_id,channel,region_code,pincode,location_id,is_allowed,created_at",
                    (product_id,rule.channel,rule.region_code,rule.pincode,rule.location_id,rule.is_allowed),
                ).fetchone())
        return {"items": rows}
    except HTTPException:
        raise
    except psycopg.Error as exc:
        raise _db_error(exc) from exc


@router.get("/products/{product_id}/attributes")
def list_product_attributes(product_id: int):
    with _connection() as conn:
        _require_product(conn, product_id)
        rows = conn.execute(
            "SELECT a.id, a.name, a.code, a.value_type, a.is_variant_attribute, a.is_required, a.options, pav.value "
            "FROM product_attributes a LEFT JOIN product_attribute_values pav "
            "ON pav.attribute_id = a.id AND pav.product_id = %s "
            "WHERE a.is_active = TRUE ORDER BY a.name", (product_id,)
        ).fetchall()
    return {"product_id": product_id, "items": rows}


@router.post("/attributes", status_code=201)
def create_attribute(payload: AttributeCreate):
    try:
        with _connection() as conn:
            row = conn.execute(
                "INSERT INTO product_attributes (name, code, value_type, is_variant_attribute, is_required, options) "
                "VALUES (%s, %s, %s, %s, %s, %s::jsonb) "
                "RETURNING id, name, code, value_type, is_variant_attribute, is_required, options, is_active, created_at",
                (payload.name, payload.code, payload.value_type, payload.is_variant_attribute, payload.is_required, __import__("json").dumps(payload.options)),
            ).fetchone()
        return row
    except psycopg.Error as exc:
        raise _db_error(exc) from exc


class AttributeOptionsUpdate(BaseModel):
    options: list[Any] = Field(max_length=200)

@router.put("/attributes/{attribute_id}/options")
def update_attribute_options(attribute_id: int, payload: AttributeOptionsUpdate):
    try:
        with _connection() as conn:
            row = conn.execute("SELECT id, name, value_type, options, is_active FROM product_attributes WHERE id=%s", (attribute_id,)).fetchone()
            if row is None or not row["is_active"]:
                raise HTTPException(status_code=404, detail="Active attribute not found")
            if row["value_type"] not in {"select", "multi_select", "colour", "size"}:
                raise HTTPException(status_code=422, detail="This attribute type does not support options")
            combined = list(row["options"] or [])
            for option in payload.options:
                if not isinstance(option, (str, int, float, bool)):
                    raise HTTPException(status_code=422, detail="Attribute options must be simple scalar values")
                if str(option).strip() and str(option) not in {str(item) for item in combined}:
                    combined.append(option)
            if not combined:
                raise HTTPException(status_code=422, detail="At least one option is required")
            updated = conn.execute("UPDATE product_attributes SET options=%s::jsonb WHERE id=%s RETURNING id,name,code,value_type,options,is_active", (__import__("json").dumps(combined), attribute_id)).fetchone()
        return updated
    except HTTPException:
        raise
    except psycopg.Error as exc:
        raise _db_error(exc) from exc

@router.get("/attributes")
def list_attributes(limit: int = Query(default=100, ge=1, le=500), offset: int = Query(default=0, ge=0)):
    with _connection() as conn:
        rows = conn.execute(
            "SELECT id, name, code, value_type, is_variant_attribute, is_required, options, is_active, created_at "
            "FROM product_attributes WHERE is_active = TRUE ORDER BY name LIMIT %s OFFSET %s", (limit, offset)
        ).fetchall()
    return {"items": rows, "limit": limit, "offset": offset}


@router.put("/products/{product_id}/attributes/{attribute_id}")
def set_product_attribute_value(product_id: int, attribute_id: int, payload: AttributeValueCreate):
    try:
        with _connection() as conn:
            _require_product(conn, product_id)
            attribute = conn.execute(
                "SELECT id, name, value_type, options, is_active FROM product_attributes WHERE id = %s",
                (attribute_id,),
            ).fetchone()
            if attribute is None or not attribute["is_active"]:
                raise HTTPException(status_code=404, detail="Active attribute not found")
            _validate_attribute_value(conn, attribute, payload.value)
            row = conn.execute(
                "INSERT INTO product_attribute_values (product_id, attribute_id, value) VALUES (%s, %s, %s::jsonb) "
                "ON CONFLICT (product_id, attribute_id) DO UPDATE SET value = EXCLUDED.value "
                "RETURNING id, product_id, attribute_id, value",
                (product_id, attribute_id, __import__("json").dumps(payload.value)),
            ).fetchone()
        return row
    except psycopg.Error as exc:
        raise _db_error(exc) from exc


@router.get("/products/{product_id}/variants")
def list_variants(product_id: int, limit: int = Query(default=100, ge=1, le=500), offset: int = Query(default=0, ge=0)):
    with _connection() as conn:
        _require_product(conn, product_id)
        rows = conn.execute(
            "SELECT id, product_id, sku, barcode, attributes, selling_price, mrp, cost_price, is_active, created_at, updated_at "
            "FROM product_variants WHERE product_id = %s ORDER BY sku LIMIT %s OFFSET %s",
            (product_id, limit, offset),
        ).fetchall()
    return {"product_id": product_id, "items": rows, "limit": limit, "offset": offset}


@router.post("/products/{product_id}/variants", status_code=201)
def create_variant(product_id: int, payload: VariantCreate):
    try:
        with _connection() as conn:
            _require_product(conn, product_id)
            attributes = conn.execute(
                "SELECT code, name, value_type, options, is_required FROM product_attributes "
                "WHERE is_active = TRUE AND is_variant_attribute = TRUE"
            ).fetchall()
            by_code = {row["code"]: row for row in attributes}
            unknown = sorted(set(payload.attributes) - set(by_code))
            if unknown:
                raise HTTPException(status_code=422, detail=f"Unknown or non-variant attributes: {', '.join(unknown)}")
            for code, value in payload.attributes.items():
                _validate_attribute_value(conn, by_code[code], value)
            sku = payload.sku.strip() if payload.sku else _generate_variant_sku(conn, product_id, payload.attributes)
            row = conn.execute(
                "INSERT INTO product_variants (product_id, sku, barcode, attributes, selling_price, mrp, cost_price) "
                "VALUES (%s, %s, %s, %s::jsonb, %s, %s, %s) "
                "RETURNING id, product_id, sku, barcode, attributes, selling_price, mrp, cost_price, is_active, created_at, updated_at",
                (product_id, sku, payload.barcode, __import__("json").dumps(payload.attributes), payload.selling_price, payload.mrp, payload.cost_price),
            ).fetchone()
        return row
    except HTTPException:
        raise
    except psycopg.Error as exc:
        raise _db_error(exc) from exc


class VariantUpdate(VariantCreate):
    pass


@router.put("/variants/{variant_id}")
def update_variant(variant_id: int, payload: VariantUpdate):
    try:
        with _connection() as conn:
            current = conn.execute(
                "SELECT id, product_id FROM product_variants WHERE id = %s AND is_active = TRUE",
                (variant_id,),
            ).fetchone()
            if current is None:
                raise HTTPException(status_code=404, detail="Active variant not found")
            definitions = conn.execute(
                "SELECT code, name, value_type, options FROM product_attributes "
                "WHERE is_active = TRUE AND is_variant_attribute = TRUE"
            ).fetchall()
            by_code = {row["code"]: row for row in definitions}
            unknown = sorted(set(payload.attributes) - set(by_code))
            if unknown:
                raise HTTPException(status_code=422, detail=f"Unknown or non-variant attributes: {', '.join(unknown)}")
            for code, value in payload.attributes.items():
                _validate_attribute_value(conn, by_code[code], value)
            row = conn.execute(
                "UPDATE product_variants SET barcode=%s, attributes=%s::jsonb, selling_price=%s, mrp=%s, "
                "cost_price=%s, updated_at=now() WHERE id=%s "
                "RETURNING id, product_id, sku, barcode, attributes, selling_price, mrp, cost_price, is_active, updated_at",
                (payload.barcode, __import__("json").dumps(payload.attributes), payload.selling_price,
                 payload.mrp, payload.cost_price, variant_id),
            ).fetchone()
        return row
    except HTTPException:
        raise
    except psycopg.Error as exc:
        raise _db_error(exc) from exc


@router.post("/variants/{variant_id}/archive")
def archive_variant(variant_id: int):
    try:
        with _connection() as conn:
            row = conn.execute(
                "UPDATE product_variants SET is_active=FALSE, updated_at=now() "
                "WHERE id=%s AND is_active=TRUE "
                "RETURNING id, product_id, sku, is_active, updated_at",
                (variant_id,),
            ).fetchone()
            if row is None:
                raise HTTPException(status_code=404, detail="Active variant not found or already archived")
        return row
    except HTTPException:
        raise
    except psycopg.Error as exc:
        raise _db_error(exc) from exc


@router.get("/products/{product_id}/images")
def list_product_images(product_id: int):
    try:
        with _connection() as conn:
            _require_product(conn, product_id)
            rows = conn.execute(
                "SELECT id, product_id, variant_id, image_url, alt_text, sort_order, is_primary, created_at "
                "FROM product_images WHERE product_id = %s ORDER BY variant_id NULLS FIRST, is_primary DESC, sort_order, id",
                (product_id,),
            ).fetchall()
        return {"items": rows}
    except HTTPException:
        raise
    except psycopg.Error as exc:
        raise _db_error(exc) from exc


@router.post("/products/{product_id}/images", status_code=201)
def create_product_image(product_id: int, payload: ProductImageCreate):
    try:
        with _connection() as conn:
            _require_product(conn, product_id)
            if payload.variant_id is not None:
                variant = conn.execute(
                    "SELECT id FROM product_variants WHERE id = %s AND product_id = %s",
                    (payload.variant_id, product_id),
                ).fetchone()
                if variant is None:
                    raise HTTPException(status_code=422, detail="Image variant must belong to the selected product")
            if payload.is_primary:
                conn.execute(
                    "UPDATE product_images SET is_primary=FALSE "
                    "WHERE product_id=%s AND variant_id IS NOT DISTINCT FROM %s AND is_primary=TRUE",
                    (product_id, payload.variant_id),
                )
            row = conn.execute(
                "INSERT INTO product_images (product_id, variant_id, image_url, alt_text, sort_order, is_primary) "
                "VALUES (%s, %s, %s, %s, %s, %s) "
                "RETURNING id, product_id, variant_id, image_url, alt_text, sort_order, is_primary, created_at",
                (product_id, payload.variant_id, payload.image_url, payload.alt_text, payload.sort_order, payload.is_primary),
            ).fetchone()
        return row
    except HTTPException:
        raise
    except psycopg.Error as exc:
        raise _db_error(exc) from exc



@router.post("/products/{product_id}/images/upload", status_code=201)
async def upload_product_image(
    product_id: int,
    file: UploadFile = File(...),
    variant_id: int | None = Form(default=None),
    alt_text: str | None = Form(default=None, max_length=300),
    sort_order: int = Form(default=0, ge=0, le=10000),
    is_primary: bool = Form(default=False),
):
    """Upload an image to configured object storage and register its gallery record."""
    allowed_types = {
        "image/jpeg": "jpg",
        "image/png": "png",
        "image/webp": "webp",
        "image/gif": "gif",
    }
    content_type = (file.content_type or "").lower()
    if content_type not in allowed_types:
        raise HTTPException(status_code=415, detail="Upload a JPEG, PNG, WebP or GIF image")
    if not settings.media_bucket or not settings.media_public_base_url:
        raise HTTPException(status_code=503, detail="Product image storage is not configured")
    data = await file.read(10 * 1024 * 1024 + 1)
    if not data:
        raise HTTPException(status_code=422, detail="Image file is empty")
    if len(data) > 10 * 1024 * 1024:
        raise HTTPException(status_code=413, detail="Image files must be 10 MB or smaller")
    signatures = {
        "image/jpeg": data.startswith(b"\\xff\\xd8\\xff"),
        "image/png": data.startswith(b"\\x89PNG\\r\\n\\x1a\\n"),
        "image/webp": len(data) >= 12 and data[:4] == b"RIFF" and data[8:12] == b"WEBP",
        "image/gif": data.startswith((b"GIF87a", b"GIF89a")),
    }
    if not signatures[content_type]:
        raise HTTPException(status_code=415, detail="The uploaded file content does not match its image type")
    try:
        with _connection() as conn:
            _require_product(conn, product_id)
            if variant_id is not None:
                variant = conn.execute(
                    "SELECT id FROM product_variants WHERE id=%s AND product_id=%s",
                    (variant_id, product_id),
                ).fetchone()
                if variant is None:
                    raise HTTPException(status_code=422, detail="Image variant must belong to the selected product")
        import boto3
        key = f"products/{product_id}/{uuid4().hex}.{allowed_types[content_type]}"
        client = boto3.client("s3", region_name=settings.aws_region)
        client.put_object(
            Bucket=settings.media_bucket,
            Key=key,
            Body=data,
            ContentType=content_type,
            CacheControl="public, max-age=31536000, immutable",
        )
        image_url = settings.media_public_base_url.rstrip("/") + "/" + key
        with _connection() as conn:
            if is_primary:
                conn.execute(
                    "UPDATE product_images SET is_primary=FALSE "
                    "WHERE product_id=%s AND variant_id IS NOT DISTINCT FROM %s AND is_primary=TRUE",
                    (product_id, variant_id),
                )
            row = conn.execute(
                "INSERT INTO product_images (product_id,variant_id,image_url,alt_text,sort_order,is_primary) "
                "VALUES (%s,%s,%s,%s,%s,%s) "
                "RETURNING id,product_id,variant_id,image_url,alt_text,sort_order,is_primary,created_at",
                (product_id, variant_id, image_url, alt_text or (file.filename or "")[:300] or None, sort_order, is_primary),
            ).fetchone()
        return row
    except HTTPException:
        raise
    except psycopg.Error as exc:
        raise _db_error(exc) from exc
    except Exception as exc:
        raise HTTPException(status_code=503, detail="Product image upload failed") from exc


class VariantPriceUpdate(BaseModel):
    selling_price: float = Field(ge=0, le=1000000000)
    mrp: float = Field(ge=0, le=1000000000)
    cost_price: float | None = Field(default=None, ge=0, le=1000000000)

    @field_validator("mrp")
    @classmethod
    def mrp_not_below_selling_price(cls, value: float, info):
        selling_price = info.data.get("selling_price")
        if selling_price is not None and value < selling_price:
            raise ValueError("MRP cannot be lower than selling price")
        return value


@router.get("/variants")
def list_all_variants(limit: int = Query(default=200, ge=1, le=500), offset: int = Query(default=0, ge=0)):
    try:
        with _connection() as conn:
            rows = conn.execute(
                "SELECT v.id, v.product_id, p.name AS product_name, v.sku, v.barcode, v.attributes, "
                "v.selling_price, v.mrp, v.cost_price, v.is_active "
                "FROM product_variants v JOIN products p ON p.id = v.product_id "
                "WHERE v.is_active = TRUE AND p.status = 'active' ORDER BY p.name, v.sku LIMIT %s OFFSET %s",
                (limit, offset),
            ).fetchall()
        return {"items": rows, "limit": limit, "offset": offset}
    except psycopg.Error as exc:
        raise _db_error(exc) from exc


@router.put("/variants/{variant_id}/price")
def update_variant_price(variant_id: int, payload: VariantPriceUpdate):
    try:
        with _connection() as conn:
            current = conn.execute(
                "SELECT id FROM product_variants WHERE id = %s AND is_active = TRUE FOR UPDATE",
                (variant_id,),
            ).fetchone()
            if current is None:
                raise HTTPException(status_code=404, detail="Active variant not found")
            row = conn.execute(
                "UPDATE product_variants SET selling_price = %s, mrp = %s, cost_price = %s, updated_at = now() "
                "WHERE id = %s "
                "RETURNING id, product_id, sku, selling_price, mrp, cost_price, updated_at",
                (payload.selling_price, payload.mrp, payload.cost_price, variant_id),
            ).fetchone()
        return row
    except HTTPException:
        raise
    except psycopg.Error as exc:
        raise _db_error(exc) from exc
