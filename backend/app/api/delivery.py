"""Delivery management records. Carrier integrations are not enabled."""
from datetime import datetime
import uuid

import psycopg
from fastapi import APIRouter, HTTPException, Query
from psycopg.rows import dict_row
from pydantic import BaseModel, Field, field_validator

from app.core.config import settings

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


class DeliveryStatusUpdate(BaseModel):
    status: str
    tracking_reference: str | None = Field(default=None, max_length=200)
    assigned_to: str | None = Field(default=None, max_length=200)
    note: str | None = Field(default=None, max_length=1000)

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
                "d.delivery_notes, d.created_at, d.updated_at FROM deliveries d JOIN orders o ON o.id=d.order_id" +
                where + " ORDER BY d.created_at DESC LIMIT %s OFFSET %s", (*params, limit, offset)
            ).fetchall()
            total = conn.execute("SELECT count(*) AS total FROM deliveries d JOIN orders o ON o.id=d.order_id" + where, params).fetchone()["total"]
        return {"items": rows, "total": total, "limit": limit, "offset": offset}
    except psycopg.Error as exc:
        raise _db_error(exc) from exc


@router.post("/shipments", status_code=201)
def _rank_locations_by_available_stock(locations):
    """Prefer the eligible location with the greatest total unreserved stock."""
    return sorted(locations, key=lambda location: (-location["available_stock"], location["id"]))


def _available_location_query(conn, order_id: int, pin_code: str):
    """Return locations serving the PIN that can fulfil every order line."""
    return conn.execute(
        """
        SELECT sl.id, sl.name,
               SUM(ib.on_hand - ib.reserved) AS available_stock
        FROM stock_locations sl
        JOIN inventory_balances ib ON ib.location_id = sl.id
        JOIN order_lines ol
          ON ol.variant_id = ib.variant_id AND ol.order_id = %s
        WHERE sl.is_active = TRUE
          AND sl.pin_code = %s
        GROUP BY sl.id, sl.name
        HAVING COUNT(DISTINCT ol.variant_id) = (
                   SELECT COUNT(DISTINCT variant_id)
                   FROM order_lines WHERE order_id = %s
               )
           AND BOOL_AND((ib.on_hand - ib.reserved) >= ol.quantity)
        ORDER BY available_stock DESC, sl.id
        """,
        (order_id, pin_code, order_id),
    ).fetchall()


def create_shipment(payload: DeliveryCreate):
    try:
        with _connect() as conn:
            with conn.transaction():
                order = conn.execute("SELECT id, status, channel, delivery_pin FROM orders WHERE id=%s FOR SHARE", (payload.order_id,)).fetchone()
                if order is None:
                    raise HTTPException(status_code=404, detail="Order not found")
                if order["status"] in {"cancelled", "delivered"}:
                    raise HTTPException(status_code=409, detail="Cannot create a shipment for a cancelled or delivered order")
                order_pin = (order["delivery_pin"] or "").strip()
                if not order_pin:
                    raise HTTPException(status_code=422, detail="The order has no delivery PIN; update the order before creating a shipment")
                if order_pin != payload.delivery_pin:
                    raise HTTPException(status_code=422, detail="Shipment delivery PIN must match the order delivery PIN")

                if order["channel"] == "website":
                    eligible_locations = _available_location_query(conn, payload.order_id, order_pin)
                    if not eligible_locations:
                        raise HTTPException(status_code=409, detail="No active location serving this PIN has enough available stock for every order item")
                    selected_location = _rank_locations_by_available_stock(eligible_locations)[0]
                    if payload.location_id is not None and payload.location_id != selected_location["id"]:
                        raise HTTPException(status_code=422, detail="Website shipments are assigned automatically to the eligible location with the most available stock")
                    location_id = selected_location["id"]
                else:
                    if payload.location_id is None:
                        raise HTTPException(status_code=422, detail="Select the fulfilment store/location for POS or manual orders")
                    selected_location = conn.execute(
                        "SELECT id FROM stock_locations WHERE id=%s AND is_active=TRUE AND pin_code=%s",
                        (payload.location_id, order_pin),
                    ).fetchone()
                    if selected_location is None:
                        raise HTTPException(status_code=422, detail="Selected location is inactive or is not configured for the order delivery PIN")
                    stock_check = conn.execute(
                        """
                        SELECT COUNT(DISTINCT ol.variant_id) AS matched_variants,
                               COUNT(DISTINCT CASE
                                   WHEN ib.on_hand - ib.reserved >= ol.quantity
                                   THEN ol.variant_id END) AS available_variants
                        FROM order_lines ol
                        LEFT JOIN inventory_balances ib
                          ON ib.variant_id=ol.variant_id AND ib.location_id=%s
                        WHERE ol.order_id=%s
                        """,
                        (payload.location_id, payload.order_id),
                    ).fetchone()
                    if stock_check["matched_variants"] != stock_check["available_variants"]:
                        raise HTTPException(status_code=409, detail="Selected location does not have enough available stock for every order item")
                    location_id = payload.location_id

                existing = conn.execute("SELECT id FROM deliveries WHERE order_id=%s AND status NOT IN ('cancelled','returned','failed')", (payload.order_id,)).fetchone()
                if existing:
                    raise HTTPException(status_code=409, detail="An active shipment already exists for this order")
                ref = "SBD-" + uuid.uuid4().hex[:10].upper()
                row = conn.execute(
                    "INSERT INTO deliveries (shipment_reference, order_id, delivery_pin, recipient_name, recipient_phone, address, location_id, status, delivery_notes) "
                    "VALUES (%s,%s,%s,%s,%s,%s,%s,'pending',%s) RETURNING id, shipment_reference, order_id, delivery_pin, recipient_name, recipient_phone, address, location_id, status, delivery_notes, created_at, updated_at",
                    (ref, payload.order_id, payload.delivery_pin, payload.recipient_name, payload.recipient_phone, payload.address, location_id, payload.delivery_notes),
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
                current = conn.execute("SELECT status FROM deliveries WHERE id=%s FOR UPDATE", (shipment_id,)).fetchone()
                if current is None:
                    raise HTTPException(status_code=404, detail="Shipment not found")
                old = current["status"]
                if old == payload.status:
                    return {"id": shipment_id, "status": old}
                if payload.status not in transitions[old]:
                    raise HTTPException(status_code=409, detail=f"Cannot change shipment status from {old} to {payload.status}")
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
