"""How each product is bought: packed (per variant) or bulk (one bulk unit, split into variants later).

A product with no saved row is packed, so existing purchasing is unchanged.
Lives under /purchasing so the existing Purchasing permissions apply.
"""
import logging
from typing import Literal

import psycopg
from fastapi import APIRouter, HTTPException, Request
from psycopg.rows import dict_row
from pydantic import BaseModel

from app.core.config import settings

router = APIRouter(prefix="/purchasing/product-modes", tags=["purchasing"])
logger = logging.getLogger(__name__)


class PurchaseModeSave(BaseModel):
    purchase_mode: Literal["packed", "bulk"]
    bulk_unit: Literal["kg", "litre", "piece"] | None = None


def _connection():
    if not settings.database_url:
        raise HTTPException(status_code=503, detail="Purchasing database is not configured")
    try:
        return psycopg.connect(settings.database_url, row_factory=dict_row, connect_timeout=3)
    except psycopg.Error as exc:
        raise HTTPException(status_code=503, detail="Purchasing database is unavailable") from exc


def _shape(product_id: int, row) -> dict:
    if not row:
        return {"product_id": product_id, "purchase_mode": "packed", "bulk_unit": None}
    return {"product_id": product_id, "purchase_mode": row["purchase_mode"], "bulk_unit": row["bulk_unit"]}


@router.get("")
def list_modes():
    """Only products marked bulk; every other product is packed."""
    try:
        with _connection() as conn:
            rows = conn.execute(
                "SELECT product_id, purchase_mode, bulk_unit FROM product_purchase_modes WHERE purchase_mode='bulk' ORDER BY product_id"
            ).fetchall()
    except psycopg.Error as exc:
        logger.warning("Purchase modes unavailable: %s", exc)
        raise HTTPException(status_code=503, detail="Purchase modes are unavailable; verify migration 052") from exc
    return {"items": [{"product_id": int(r["product_id"]), "purchase_mode": r["purchase_mode"], "bulk_unit": r["bulk_unit"]} for r in rows]}


@router.get("/{product_id}")
def get_mode(product_id: int):
    try:
        with _connection() as conn:
            row = conn.execute(
                "SELECT purchase_mode, bulk_unit FROM product_purchase_modes WHERE product_id=%s", (product_id,)
            ).fetchone()
    except psycopg.Error as exc:
        logger.warning("Purchase mode unavailable: %s", exc)
        raise HTTPException(status_code=503, detail="Purchase modes are unavailable; verify migration 052") from exc
    return _shape(product_id, row)


@router.put("/{product_id}")
def save_mode(product_id: int, payload: PurchaseModeSave, request: Request):
    unit = payload.bulk_unit if payload.purchase_mode == "bulk" else None
    if payload.purchase_mode == "bulk" and unit is None:
        raise HTTPException(status_code=422, detail="Choose a buying unit (kg, litre or piece) for a bulk product")
    who = str(getattr(request.state, "user_email", "") or "staff")
    try:
        with _connection() as conn:
            with conn.transaction():
                if conn.execute("SELECT 1 FROM products WHERE id=%s", (product_id,)).fetchone() is None:
                    raise HTTPException(status_code=404, detail="Product not found")
                row = conn.execute(
                    "INSERT INTO product_purchase_modes (product_id, purchase_mode, bulk_unit, updated_by) VALUES (%s,%s,%s,%s) "
                    "ON CONFLICT (product_id) DO UPDATE SET purchase_mode=EXCLUDED.purchase_mode, bulk_unit=EXCLUDED.bulk_unit, "
                    "updated_by=EXCLUDED.updated_by, updated_at=now() RETURNING purchase_mode, bulk_unit",
                    (product_id, payload.purchase_mode, unit, who),
                ).fetchone()
    except HTTPException:
        raise
    except psycopg.Error as exc:
        logger.warning("Purchase mode save failed: %s", exc)
        raise HTTPException(status_code=503, detail="Could not save; verify migration 052") from exc
    return _shape(product_id, row)
