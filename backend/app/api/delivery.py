"""Delivery management records. Carrier integrations are not enabled."""
from datetime import datetime
import uuid

import psycopg
from fastapi import APIRouter, HTTPException, Query
from psycopg.rows import dict_row
from pydantic import BaseModel, Field, field_validator

from app.core.config import settings
from app.services.order_inventory import dispatch_order_stock, order_fulfilment_started, order_reservation_locations, reserve_order_stock

router = APIRouter(prefix="/delivery", tags=["delivery"])
DELIVERY_STATUSES = {"pending", "packed", "assigned", "dispatched", "in_transit", "delivered", "failed", "returned", "cancelled"}


def _connect():
    if not settings.database_url:
        raise HTTPException(status_code=503, detail="Delivery database is not configured")
    try:
        return psycopg.connect(settings.database_url, row_factory=dict_row)
    except psycopg.Error as exc:
        raise HTTPException(status_code=503, detail="Delivery database is unavailable") from exc


def _db_error(exc):
    if getattr(exc, "sqlstate", None) == "23503":
        return HTTPException(status_code=422, detail="Referenced order or location does not exist")
    return HTTPException(status_code=503, detail="Delivery storage is unavailable; verify the delivery migration")


class DeliveryCreate(BaseModel):
    order_id: int = Field(gt=0)
    delivery_pin: str = Field(pattern=r"^[0-9]{6}$")
    recipient_name: str = Field(min_length=1, max_length=200)
    recipient_phone: str = Field(min_length=7, max_length=20)
    address: str = Field(min_length=5, max_length=1000)
    location_id: int | None = Field(default=None, gt=0)
    delivery_notes: str | None = Field(default=None, max_length=1000)

    @field_validator("recipient_name", "address", "recipient_phone")
    @classmethod
    def trim_required(cls, value):
        if not value.strip():
            raise ValueError("Field cannot be blank")
        return value.strip()


class DeliveryDispatchLine(BaseModel):
    variant_id: int = Field(gt=0)
    quantity: int = Field(gt=0)


class DeliveryStatusUpdate(BaseModel):
    status: str
    dispatch_lines: list[DeliveryDispatchLine] | None = Field(default=None, max_length=100)
    tracking_reference: str | None = Field(default=None, max_length=200)
    assigned_to: str | None = Field(default=None, max_length=200)
    note: str | None = Field(default=None, max_length=1000)

    @field_validator("dispatch_lines")
    @classmethod
    def unique_dispatch_variants(cls, value):
        if value is not None:
            ids = [line.variant_id for line in value]
            if len(ids) != len(set(ids)):
                raise ValueError("Each variant can appear only once in a partial dispatch")
        return value

    @field_validator("status")
    @classmethod
    def valid_status(cls, value):
        if value not in DELIVERY_STATUSES:
            raise ValueError("Unsupported delivery status")
        return value


@router.get("/serviceability/{pin_code}")
def check_serviceability(pin_code: str):
    """Check whether an active stock location is configured for this exact PIN."""
    if not pin_code.isdigit() or len(pin_code) != 6 or pin_code.startswith("0"):
        raise HTTPException(status_code=422, detail="Enter a valid six-digit Indian PIN code")
    try:
        with _connect() as conn:
            locations = conn.execute(
                "SELECT id, name FROM stock_locations WHERE is_active=TRUE AND pin_code=%s ORDER BY name",
                (pin_code,),
            ).fetchall()
        return {
            "pin_code": pin_code,
            "serviceable": bool(locations),
            "status": "serviceable" if locations else "not_configured",
            "locations": [{"id": row["id"], "name": row["name"]} for row in locations],
            "message": "Delivery is configured for this PIN." if locations else "Delivery is not configured for this PIN yet.",
        }
    except psycopg.Error as exc:
        raise _db_error(exc) from exc


@router.get("/shipments")
def list_shipments(
    status: str | None = Query(default=None),
    search: str | None = Query(default=None, max_length=200),
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
):
    if status and status not in DELIVERY_STATUSES:
        raise HTTPException(status_code=422, detail="Unsupported delivery status")
    clauses, params = [], []
    if status:
        clauses.append("d.status=%s"); params.append(status)
    if search and search.strip():
        term = "%" + search.strip() + "%"
        clauses.append("(d.shipment_reference ILIKE %s OR o.order_number ILIKE %s OR d.recipient_name ILIKE %s OR d.delivery_pin ILIKE %s)")
        params.extend([term, term, term, term])
    where = (" WHERE " + " AND ".join(clauses)) if clauses else ""
    try:
        with _connect() as conn:
            rows = conn.execute(
                "SELECT d.id, d.shipment_reference, d.order_id, o.order_number, d.delivery_pin, d.recipient_name, "
                "d.recipient_phone, d.address, d.location_id, d.status, d.tracking_reference, d.assigned_to, "
                "d.delivery_notes, d.created_at, d.updated_at, "
                "COALESCE((SELECT json_agg(json_build_object('variant_id', l.variant_id, 'sku', v.sku, "
                "'product_name', p.name, 'ordered_quantity', l.quantity, 'remaining_quantity', "
                "GREATEST(l.quantity - COALESCE((SELECT sum(m.quantity) FROM inventory_movements m "
                "WHERE m.variant_id=l.variant_id AND m.reference_id=o.id::text "
                "AND m.reference_type='order_fulfilment' AND m.movement_type='sale'),0),0)) ORDER BY l.id) "
                "FROM order_lines l JOIN product_variants v ON v.id=l.variant_id "
                "JOIN products p ON p.id=v.product_id WHERE l.order_id=o.id), '[]'::json) AS order_lines "
                "FROM deliveries d JOIN orders o ON o.id=d.order_id" +
                where + " ORDER BY d.created_at DESC LIMIT %s OFFSET %s", (*params, limit, offset)
            ).fetchall()
            total = conn.execute("SELECT count(*) AS total FROM deliveries d JOIN orders o ON o.id=d.order_id" + where, params).fetchone()["total"]
        return {"items": rows, "total": total, "limit": limit, "offset": offset}
    except psycopg.Error as exc:
        raise _db_error(exc) from exc


@router.post("/shipments", status_code=201)
def create_shipment(payload: DeliveryCreate):
    try:
        with _connect() as conn:
            with conn.transaction():
                order = conn.execute("SELECT id, status, delivery_pin FROM orders WHERE id=%s FOR UPDATE", (payload.order_id,)).fetchone()
                if order is None:
                    raise HTTPException(status_code=404, detail="Order not found")
                if order["status"] in {"cancelled", "delivered"}:
                    raise HTTPException(status_code=409, detail="Cannot create a shipment for a cancelled or delivered order")
                if order["delivery_pin"] and order["delivery_pin"].strip() != payload.delivery_pin:
                    raise HTTPException(status_code=422, detail="Shipment delivery PIN must match the order delivery PIN")
                existing = conn.execute("SELECT id FROM deliveries WHERE order_id=%s AND status NOT IN ('cancelled','returned','failed','delivered')", (payload.order_id,)).fetchone()
                if existing:
                    raise HTTPException(status_code=409, detail="An active shipment already exists for this order")
                active_reserved_locations = order_reservation_locations(conn, payload.order_id)
                shipment_location_id = payload.location_id
                if len(active_reserved_locations) > 1:
                    raise HTTPException(status_code=409, detail="Order stock is allocated across multiple locations; shipment location needs review")
                if active_reserved_locations:
                    reserved_location_id = active_reserved_locations[0]
                    if shipment_location_id is not None and shipment_location_id != reserved_location_id:
                        raise HTTPException(status_code=409, detail="Shipment location must match the location holding this order's reservation")
                    shipment_location_id = reserved_location_id
                else:
                    if order_fulfilment_started(conn, payload.order_id):
                        raise HTTPException(status_code=409, detail="This order has already been fully dispatched")
                    order_lines = conn.execute(
                        "SELECT variant_id, quantity FROM order_lines WHERE order_id=%s ORDER BY variant_id",
                        (payload.order_id,),
                    ).fetchall()
                    if not order_lines:
                        raise HTTPException(status_code=409, detail="Order has no lines to fulfil")
                    try:
                        shipment_location_id = reserve_order_stock(
                            conn, payload.order_id, payload.delivery_pin,
                            [(int(line["variant_id"]), int(line["quantity"])) for line in order_lines],
                            location_id=shipment_location_id,
                        )
                    except ValueError as exc:
                        raise HTTPException(status_code=409, detail=str(exc)) from exc
                if shipment_location_id is None:
                    raise HTTPException(status_code=409, detail="A stock location must be selected before shipment creation")
                ref = "SBD-" + uuid.uuid4().hex[:10].upper()
                row = conn.execute(
                    "INSERT INTO deliveries (shipment_reference, order_id, delivery_pin, recipient_name, recipient_phone, address, location_id, status, delivery_notes) "
                    "VALUES (%s,%s,%s,%s,%s,%s,%s,'pending',%s) RETURNING id, shipment_reference, order_id, delivery_pin, recipient_name, recipient_phone, address, location_id, status, delivery_notes, created_at, updated_at",
                    (ref, payload.order_id, payload.delivery_pin, payload.recipient_name, payload.recipient_phone, payload.address, shipment_location_id, payload.delivery_notes),
                ).fetchone()
        return row
    except HTTPException:
        raise
    except psycopg.Error as exc:
        raise _db_error(exc) from exc


@router.patch("/shipments/{shipment_id}/status")
def update_shipment_status(shipment_id: int, payload: DeliveryStatusUpdate):
    transitions = {
        "pending": {"packed", "cancelled"}, "packed": {"assigned", "cancelled"},
        "assigned": {"dispatched", "cancelled"}, "dispatched": {"in_transit", "delivered", "failed"},
        "in_transit": {"delivered", "failed", "returned"}, "failed": {"assigned", "returned"},
        "delivered": set(), "returned": set(), "cancelled": set(),
    }
    try:
        with _connect() as conn:
            with conn.transaction():
                current = conn.execute(
                    "SELECT d.status, d.order_id FROM deliveries d JOIN orders o ON o.id=d.order_id "
                    "WHERE d.id=%s FOR UPDATE OF d, o",
                    (shipment_id,),
                ).fetchone()
                if current is None:
                    raise HTTPException(status_code=404, detail="Shipment not found")
                old = current["status"]
                if old == payload.status:
                    return {"id": shipment_id, "status": old}
                if payload.status not in transitions[old]:
                    raise HTTPException(status_code=409, detail=f"Cannot change shipment status from {old} to {payload.status}")
                if payload.dispatch_lines is not None and payload.status != "dispatched":
                    raise HTTPException(status_code=422, detail="Dispatch quantities can only be supplied when marking a shipment dispatched")
                if payload.status == "dispatched":
                    order_id = int(current["order_id"])
                    try:
                        requested = ({line.variant_id: line.quantity for line in payload.dispatch_lines} if payload.dispatch_lines is not None else None)
                        dispatched_lines = dispatch_order_stock(conn, order_id, requested)
                    except ValueError as exc:
                        raise HTTPException(status_code=409, detail=str(exc)) from exc
                    if dispatched_lines == 0 and not order_fulfilment_started(conn, order_id):
                        raise HTTPException(status_code=409, detail="No outstanding stock reservation exists for this order")
                row = conn.execute(
                    "UPDATE deliveries SET status=%s, tracking_reference=COALESCE(%s,tracking_reference), assigned_to=COALESCE(%s,assigned_to), updated_at=now() "
                    "WHERE id=%s RETURNING id, shipment_reference, status, tracking_reference, assigned_to, updated_at",
                    (payload.status, payload.tracking_reference, payload.assigned_to, shipment_id),
                ).fetchone()
                conn.execute("INSERT INTO delivery_status_history (delivery_id, from_status, to_status, note) VALUES (%s,%s,%s,%s)",
                    (shipment_id, old, payload.status, payload.note))
        return row
    except HTTPException:
        raise
    except psycopg.Error as exc:
        raise _db_error(exc) from exc



@router.get("/shipments/{shipment_id}/history")
def shipment_status_history(
    shipment_id: int,
    limit: int = Query(default=100, ge=1, le=500),
):
    """Return the recorded status transitions for a shipment in chronological order."""
    try:
        with _connect() as conn:
            shipment = conn.execute(
                "SELECT id, shipment_reference FROM deliveries WHERE id = %s",
                (shipment_id,),
            ).fetchone()
            if shipment is None:
                raise HTTPException(status_code=404, detail="Shipment not found")
            rows = conn.execute(
                "SELECT id, from_status, to_status, note, changed_at "
                "FROM delivery_status_history WHERE delivery_id = %s "
                "ORDER BY changed_at DESC, id DESC LIMIT %s",
                (shipment_id, limit),
            ).fetchall()
        return {"shipment_id": shipment_id, "shipment_reference": shipment["shipment_reference"], "items": rows}
    except HTTPException:
        raise
    except psycopg.Error as exc:
        raise _db_error(exc) from exc
