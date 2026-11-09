"""Pricing read models and SKU price updates for the admin Pricing workspace."""
from decimal import Decimal

import psycopg
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field, field_validator
from psycopg.rows import dict_row

from app.core.config import settings

router = APIRouter(prefix="/pricing", tags=["pricing"])


def _connect():
    if not settings.database_url:
        raise HTTPException(status_code=503, detail="Pricing database is not configured")
    try:
        return psycopg.connect(settings.database_url, row_factory=dict_row)
    except psycopg.Error as exc:
        raise HTTPException(status_code=503, detail="Pricing database is unavailable") from exc


def _db_error(exc: psycopg.Error):
    if getattr(exc, "sqlstate", None) == "23503":
        return HTTPException(status_code=422, detail="Referenced product variant does not exist")
    return HTTPException(status_code=503, detail="Pricing data is unavailable")


class PriceUpdate(BaseModel):
    selling_price: Decimal = Field(ge=0, max_digits=14, decimal_places=2)
    mrp: Decimal = Field(ge=0, max_digits=14, decimal_places=2)
    cost_price: Decimal | None = Field(default=None, ge=0, max_digits=14, decimal_places=2)

    @field_validator("mrp")
    @classmethod
    def mrp_not_below_selling_price(cls, value, info):
        selling = info.data.get("selling_price")
        if selling is not None and value < selling:
            raise ValueError("MRP cannot be lower than selling price")
        return value


@router.get("/overview")
def pricing_overview():
    try:
        with _connect() as conn:
            row = conn.execute(
                """SELECT count(*) AS variant_count,
                          count(*) FILTER (WHERE selling_price IS NULL OR selling_price <= 0) AS missing_price_count,
                          count(*) FILTER (WHERE mrp < selling_price) AS invalid_mrp_count,
                          COALESCE(avg(selling_price), 0) AS average_selling_price,
                          COALESCE(sum(selling_price), 0) AS sum_selling_prices
                   FROM product_variants v
                   JOIN products p ON p.id = v.product_id
                   WHERE v.is_active = TRUE AND p.status = 'active'"""
            ).fetchone()
        return {"source": "postgresql", "metrics": row}
    except psycopg.Error as exc:
        raise _db_error(exc) from exc


@router.get("/variants")
def pricing_variants(
    search: str | None = Query(default=None, max_length=200),
    limit: int = Query(default=200, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
):
    clauses = ["v.is_active = TRUE", "p.status = 'active'"]
    params = []
    if search and search.strip():
        term = "%" + search.strip() + "%"
        clauses.append("(p.name ILIKE %s OR v.sku ILIKE %s OR COALESCE(v.barcode, '') ILIKE %s)")
        params.extend([term, term, term])
    where = " AND ".join(clauses)
    try:
        with _connect() as conn:
            items = conn.execute(
                f"""SELECT v.id, v.product_id, p.name AS product_name, v.sku, v.barcode,
                           v.attributes, v.selling_price, v.mrp, v.cost_price, v.updated_at
                    FROM product_variants v JOIN products p ON p.id=v.product_id
                    WHERE {where}
                    ORDER BY p.name, v.sku LIMIT %s OFFSET %s""",
                (*params, limit, offset),
            ).fetchall()
            total = conn.execute(
                f"SELECT count(*) AS total FROM product_variants v JOIN products p ON p.id=v.product_id WHERE {where}",
                params,
            ).fetchone()["total"]
        return {"items": items, "total": total, "limit": limit, "offset": offset, "source": "postgresql"}
    except psycopg.Error as exc:
        raise _db_error(exc) from exc


@router.put("/variants/{variant_id}/price")
def update_price(variant_id: int, payload: PriceUpdate):
    try:
        with _connect() as conn:
            with conn.transaction():
                current = conn.execute(
                    "SELECT id FROM product_variants WHERE id=%s AND is_active=TRUE FOR UPDATE",
                    (variant_id,),
                ).fetchone()
                if current is None:
                    raise HTTPException(status_code=404, detail="Active variant not found")
                updated = conn.execute(
                    """UPDATE product_variants
                       SET selling_price=%s, mrp=%s, cost_price=%s, updated_at=now()
                       WHERE id=%s
                       RETURNING id, product_id, sku, selling_price, mrp, cost_price, updated_at""",
                    (payload.selling_price, payload.mrp, payload.cost_price, variant_id),
                ).fetchone()
        return updated
    except HTTPException:
        raise
    except psycopg.Error as exc:
        raise _db_error(exc) from exc
