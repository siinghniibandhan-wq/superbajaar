"""Inventory read and adjustment endpoints. Requires the reviewed v1 schema."""
from decimal import Decimal
from typing import Any

import psycopg
from fastapi import APIRouter, HTTPException, Query
from psycopg.rows import dict_row
from pydantic import BaseModel, Field, field_validator

from app.core.config import settings

router = APIRouter(prefix="/inventory", tags=["inventory"])


class StockLocationCreate(BaseModel):
    name: str = Field(min_length=1, max_length=160)
    location_type: str = Field(pattern=r"^(warehouse|store|dark_store)$")
    pin_code: str | None = Field(default=None, pattern=r"^[0-9]{6}$")

    @field_validator("name")
    @classmethod
    def location_name_not_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("Location name cannot be blank")
        return value.strip()


class StockAdjustment(BaseModel):
    variant_id: int = Field(gt=0)
    location_id: int = Field(gt=0)
    quantity: Decimal = Field(gt=0, max_digits=14, decimal_places=3)
    note: str = Field(min_length=3, max_length=500)



class StockIssue(BaseModel):
    variant_id: int = Field(gt=0)
    location_id: int = Field(gt=0)
    quantity: Decimal = Field(gt=0, max_digits=14, decimal_places=3)
    note: str = Field(min_length=3, max_length=500)


class StockTransfer(BaseModel):
    variant_id: int = Field(gt=0)
    source_location_id: int = Field(gt=0)
    destination_location_id: int = Field(gt=0)
    quantity: Decimal = Field(gt=0, max_digits=14, decimal_places=3)
    note: str = Field(min_length=3, max_length=500)

    @field_validator("destination_location_id")
    @classmethod
    def destination_must_differ_from_source(cls, value: int, info):
        source = info.data.get("source_location_id")
        if source is not None and value == source:
            raise ValueError("Source and destination locations must be different")
        return value

def _connect():
    if not settings.database_url:
        raise HTTPException(status_code=503, detail="Inventory database is not configured")
    try:
        return psycopg.connect(settings.database_url, row_factory=dict_row, connect_timeout=3)
    except psycopg.Error as exc:
        raise HTTPException(status_code=503, detail="Inventory database is unavailable") from exc


def _db_error(exc: psycopg.Error) -> HTTPException:
    code = getattr(exc, "sqlstate", None)
    if code == "23503":
        return HTTPException(status_code=422, detail="Variant or stock location does not exist")
    if code == "23514":
        return HTTPException(status_code=422, detail="Stock adjustment violates an inventory constraint")
    return HTTPException(status_code=503, detail="Inventory database operation failed")


@router.post("/locations", status_code=201)
def create_location(payload: StockLocationCreate):
    try:
        with _connect() as conn:
            row = conn.execute(
                "INSERT INTO stock_locations (name, location_type, pin_code) VALUES (%s, %s, %s) "
                "RETURNING id, name, location_type, pin_code, is_active, created_at",
                (payload.name, payload.location_type, payload.pin_code),
            ).fetchone()
        return row
    except psycopg.Error as exc:
        code = getattr(exc, "sqlstate", None)
        if code == "23505":
            raise HTTPException(status_code=409, detail="A stock location with this name already exists") from exc
        raise _db_error(exc) from exc


@router.get("/locations")
def list_locations(limit: int = Query(default=100, ge=1, le=500), offset: int = Query(default=0, ge=0)):
    try:
        with _connect() as conn:
            rows = conn.execute(
                "SELECT id, name, location_type, pin_code, is_active, created_at "
                "FROM stock_locations WHERE is_active = TRUE ORDER BY name LIMIT %s OFFSET %s",
                (limit, offset),
            ).fetchall()
        return {"items": rows, "limit": limit, "offset": offset}
    except psycopg.Error as exc:
        raise _db_error(exc) from exc


@router.get("/balances")
def list_balances(
    location_id: int | None = Query(default=None, gt=0),
    variant_id: int | None = Query(default=None, gt=0),
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
) -> dict[str, Any]:
    clauses: list[str] = []
    params: list[Any] = []
    if location_id is not None:
        clauses.append("ib.location_id = %s")
        params.append(location_id)
    if variant_id is not None:
        clauses.append("ib.variant_id = %s")
        params.append(variant_id)
    where = "WHERE " + " AND ".join(clauses) if clauses else ""
    params.extend([limit, offset])
    try:
        with _connect() as conn:
            rows = conn.execute(
                "SELECT ib.variant_id, pv.sku, pv.product_id, ib.location_id, sl.name AS location_name, "
                "ib.on_hand, ib.reserved, (ib.on_hand - ib.reserved) AS available, ib.updated_at "
                "FROM inventory_balances ib JOIN product_variants pv ON pv.id = ib.variant_id "
                "JOIN stock_locations sl ON sl.id = ib.location_id "
                f"{where} ORDER BY sl.name, pv.sku LIMIT %s OFFSET %s",
                tuple(params),
            ).fetchall()
        return {"items": rows, "limit": limit, "offset": offset}
    except psycopg.Error as exc:
        raise _db_error(exc) from exc


@router.get("/movements")
def list_movements(
    variant_id: int | None = Query(default=None, gt=0),
    location_id: int | None = Query(default=None, gt=0),
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
) -> dict[str, Any]:
    clauses: list[str] = []
    params: list[Any] = []
    if variant_id is not None:
        clauses.append("variant_id = %s")
        params.append(variant_id)
    if location_id is not None:
        clauses.append("location_id = %s")
        params.append(location_id)
    where = "WHERE " + " AND ".join(clauses) if clauses else ""
    params.extend([limit, offset])
    try:
        with _connect() as conn:
            rows = conn.execute(
                "SELECT id, variant_id, location_id, movement_type, quantity, reference_type, reference_id, note, created_at "
                f"FROM inventory_movements {where} ORDER BY created_at DESC, id DESC LIMIT %s OFFSET %s",
                tuple(params),
            ).fetchall()
        return {"items": rows, "limit": limit, "offset": offset}
    except psycopg.Error as exc:
        raise _db_error(exc) from exc


@router.post("/adjustments", status_code=201)
def create_adjustment(payload: StockAdjustment) -> dict[str, Any]:
    """Record a positive stock receipt adjustment atomically; no negative-stock writes."""
    try:
        with _connect() as conn:
            variant = conn.execute(
                "SELECT id FROM product_variants WHERE id = %s AND is_active = TRUE FOR SHARE",
                (payload.variant_id,),
            ).fetchone()
            if variant is None:
                raise HTTPException(status_code=404, detail="Active product variant not found")
            location = conn.execute(
                "SELECT id FROM stock_locations WHERE id = %s AND is_active = TRUE FOR SHARE",
                (payload.location_id,),
            ).fetchone()
            if location is None:
                raise HTTPException(status_code=404, detail="Active stock location not found")
            conn.execute(
                "INSERT INTO inventory_balances (variant_id, location_id, on_hand, reserved) "
                "VALUES (%s, %s, %s, 0) "
                "ON CONFLICT (variant_id, location_id) DO UPDATE "
                "SET on_hand = inventory_balances.on_hand + EXCLUDED.on_hand, updated_at = now()",
                (payload.variant_id, payload.location_id, payload.quantity),
            )
            movement = conn.execute(
                "INSERT INTO inventory_movements "
                "(variant_id, location_id, movement_type, quantity, reference_type, note) "
                "VALUES (%s, %s, 'adjustment', %s, 'manual_adjustment', %s) "
                "RETURNING id, variant_id, location_id, movement_type, quantity, reference_type, note, created_at",
                (payload.variant_id, payload.location_id, payload.quantity, payload.note.strip()),
            ).fetchone()
        return movement
    except HTTPException:
        raise
    except psycopg.Error as exc:
        raise _db_error(exc) from exc



@router.post("/issues", status_code=201)
def issue_stock(payload: StockIssue) -> dict[str, Any]:
    """Reduce on-hand stock only when unreserved available quantity is sufficient."""
    try:
        with _connect() as conn:
            variant = conn.execute(
                "SELECT id FROM product_variants WHERE id = %s AND is_active = TRUE FOR SHARE",
                (payload.variant_id,),
            ).fetchone()
            if variant is None:
                raise HTTPException(status_code=404, detail="Active product variant not found")
            location = conn.execute(
                "SELECT id FROM stock_locations WHERE id = %s AND is_active = TRUE FOR SHARE",
                (payload.location_id,),
            ).fetchone()
            if location is None:
                raise HTTPException(status_code=404, detail="Active stock location not found")
            balance = conn.execute(
                "SELECT on_hand, reserved FROM inventory_balances "
                "WHERE variant_id = %s AND location_id = %s FOR UPDATE",
                (payload.variant_id, payload.location_id),
            ).fetchone()
            available = (balance["on_hand"] - balance["reserved"]) if balance else Decimal("0")
            if payload.quantity > available:
                raise HTTPException(status_code=409, detail="Insufficient available stock; reserved units cannot be issued")
            conn.execute(
                "UPDATE inventory_balances SET on_hand = on_hand - %s, updated_at = now() "
                "WHERE variant_id = %s AND location_id = %s",
                (payload.quantity, payload.variant_id, payload.location_id),
            )
            movement = conn.execute(
                "INSERT INTO inventory_movements "
                "(variant_id, location_id, movement_type, quantity, reference_type, note) "
                "VALUES (%s, %s, 'adjustment', %s, 'manual_issue', %s) "
                "RETURNING id, variant_id, location_id, movement_type, quantity, reference_type, note, created_at",
                (payload.variant_id, payload.location_id, payload.quantity, payload.note.strip()),
            ).fetchone()
        return movement
    except HTTPException:
        raise
    except psycopg.Error as exc:
        raise _db_error(exc) from exc


@router.post("/transfers", status_code=201)
def transfer_stock(payload: StockTransfer) -> dict[str, Any]:
    """Atomically move available stock between two active locations."""
    if payload.source_location_id == payload.destination_location_id:
        raise HTTPException(status_code=422, detail="Source and destination locations must be different")
    try:
        with _connect() as conn:
            variant = conn.execute(
                "SELECT id FROM product_variants WHERE id = %s AND is_active = TRUE FOR SHARE",
                (payload.variant_id,),
            ).fetchone()
            if variant is None:
                raise HTTPException(status_code=404, detail="Active product variant not found")
            locations = conn.execute(
                "SELECT id FROM stock_locations WHERE id = ANY(%s) AND is_active = TRUE ORDER BY id FOR SHARE",
                ([payload.source_location_id, payload.destination_location_id],),
            ).fetchall()
            if len(locations) != 2:
                raise HTTPException(status_code=404, detail="Both stock locations must exist and be active")
            source = conn.execute(
                "SELECT on_hand, reserved FROM inventory_balances "
                "WHERE variant_id = %s AND location_id = %s FOR UPDATE",
                (payload.variant_id, payload.source_location_id),
            ).fetchone()
            available = (source["on_hand"] - source["reserved"]) if source else Decimal("0")
            if payload.quantity > available:
                raise HTTPException(status_code=409, detail="Insufficient available stock; reserved units cannot be transferred")
            conn.execute(
                "UPDATE inventory_balances SET on_hand = on_hand - %s, updated_at = now() "
                "WHERE variant_id = %s AND location_id = %s",
                (payload.quantity, payload.variant_id, payload.source_location_id),
            )
            conn.execute(
                "INSERT INTO inventory_balances (variant_id, location_id, on_hand, reserved) "
                "VALUES (%s, %s, %s, 0) ON CONFLICT (variant_id, location_id) DO UPDATE "
                "SET on_hand = inventory_balances.on_hand + EXCLUDED.on_hand, updated_at = now()",
                (payload.variant_id, payload.destination_location_id, payload.quantity),
            )
            movement_rows = []
            for location_id, movement_type in (
                (payload.source_location_id, "transfer_out"),
                (payload.destination_location_id, "transfer_in"),
            ):
                row = conn.execute(
                    "INSERT INTO inventory_movements "
                    "(variant_id, location_id, movement_type, quantity, reference_type, reference_id, note) "
                    "VALUES (%s, %s, %s, %s, 'stock_transfer', %s, %s) "
                    "RETURNING id, variant_id, location_id, movement_type, quantity, reference_type, reference_id, note, created_at",
                    (payload.variant_id, location_id, movement_type, payload.quantity, None, payload.note.strip()),
                ).fetchone()
                movement_rows.append(row)
        return {"items": movement_rows, "quantity": payload.quantity, "status": "transferred"}
    except HTTPException:
        raise
    except psycopg.Error as exc:
        raise _db_error(exc) from exc
