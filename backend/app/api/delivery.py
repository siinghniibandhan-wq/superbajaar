"""Delivery management records. Carrier integrations are not enabled."""
from datetime import datetime
from decimal import Decimal
from uuid import UUID, uuid4

import psycopg
from fastapi import APIRouter, HTTPException, Query, Request
from psycopg.rows import dict_row
from pydantic import BaseModel, Field, field_validator, model_validator

from app.core.config import settings
from app.services.fulfilment_dispatch import (
    FulfilmentDispatchError,
    dispatch_shipment,
    order_has_reservation,
)
from app.services.order_inventory import order_reservation_locations





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


class DeliveryPackageDispatchLine(BaseModel):
    package_line_id: int = Field(gt=0)
    quantity: Decimal = Field(gt=0, max_digits=14, decimal_places=3)


class DeliveryStatusUpdate(BaseModel):
    status: str
    dispatch_id: UUID | None = None
    dispatch_lines: list[DeliveryDispatchLine] | None = Field(default=None, min_length=1, max_length=100)
    package_lines: list[DeliveryPackageDispatchLine] | None = Field(default=None, min_length=1, max_length=100)
    tracking_reference: str | None = Field(default=None, max_length=200)
    assigned_to: str | None = Field(default=None, max_length=200)
    note: str | None = Field(default=None, max_length=1000)

    @field_validator("dispatch_lines")
    @classmethod
    def unique_dispatch_variants(cls, value):
        if value is not None:
            ids = [line.variant_id for line in value]
            if len(ids) != len(set(ids)):
                raise ValueError("Each variant can appear only once in a dispatch")
        return value

    @field_validator("status")
    @classmethod
    def valid_status(cls, value):
        if value not in DELIVERY_STATUSES:
            raise ValueError("Unsupported delivery status")
        return value

    @model_validator(mode="after")
    def dispatch_requires_idempotency_key(self):
        if self.status == "dispatched" and self.dispatch_id is None:
            raise ValueError("A unique dispatch_id is required for every dispatch event")
        if self.dispatch_lines is not None and self.status != "dispatched":
            raise ValueError("Dispatch quantities can only be supplied when status is dispatched")
        if self.package_lines is not None and self.status != "dispatched":
            raise ValueError("Package quantities can only be supplied when status is dispatched")
        if self.dispatch_lines is not None and self.package_lines is not None:
            raise ValueError("Use either variant dispatch quantities or package-line quantities, not both")
        if self.package_lines is not None:
            ids = [line.package_line_id for line in self.package_lines]
            if len(ids) != len(set(ids)):
                raise ValueError("Each package line can appear only once in a dispatch")
        return self


@router.get("/serviceability/{pin_code}")
def check_serviceability(pin_code: str):
    """Return eligible physical fulfilment facilities for this exact PIN; never expose internal bins."""
    if not pin_code.isdigit() or len(pin_code) != 6 or pin_code.startswith("0"):
        raise HTTPException(status_code=422, detail="Enter a valid six-digit Indian PIN code")
    try:
        with _connect() as conn:
            locations = conn.execute(
                "SELECT sl.id, sl.name, sl.location_type, sl.pin_code, sl.region_code, sl.city, sl.district, sl.state "
                "FROM stock_locations sl LEFT JOIN stock_location_profiles p ON p.location_id=sl.id "
                "WHERE sl.is_active=TRUE AND sl.is_fulfillable=TRUE "
                "AND COALESCE((p.profile_data->>'storefront_available')::boolean, TRUE)=TRUE "
                "AND COALESCE(p.profile_data->'service_pin_codes', "
                "CASE WHEN sl.pin_code IS NULL THEN '[]'::jsonb ELSE jsonb_build_array(sl.pin_code) END) "
                "@> jsonb_build_array(%s::text) "
                "AND (COALESCE(jsonb_array_length(p.profile_data->'operating_days'),0)=0 "
                "OR p.profile_data->'operating_days' ? lower(to_char(now() AT TIME ZONE 'Asia/Kolkata','Dy'))) "
                "AND (p.profile_data->>'opening_time' IS NULL OR "
                "to_char(now() AT TIME ZONE 'Asia/Kolkata','HH24:MI') >= p.profile_data->>'opening_time') "
                "AND (p.profile_data->>'closing_time' IS NULL OR "
                "to_char(now() AT TIME ZONE 'Asia/Kolkata','HH24:MI') <= p.profile_data->>'closing_time') "
                "ORDER BY COALESCE((p.profile_data->>'routing_priority')::integer,100), sl.id",
                (pin_code,),
            ).fetchall()
        return {
            "pin_code": pin_code,
            "serviceable": bool(locations),
            "status": "serviceable" if locations else "not_configured",
            "locations": [{"id": row["id"], "name": row["name"], "location_type": row["location_type"], "region_code": row["region_code"], "city": row["city"], "district": row["district"], "state": row["state"]} for row in locations],
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
                "SELECT d.id, d.shipment_reference, d.order_id, o.order_number, o.status AS order_status, "
                "d.delivery_pin, d.recipient_name, d.recipient_phone, d.address, d.location_id, d.status, "
                "d.tracking_reference, d.assigned_to, d.delivery_notes, d.created_at, d.updated_at, "
                "COALESCE((SELECT json_agg(json_build_object("
                "'variant_id',ol.variant_id,'sku',v.sku,'product_name',p.name,"
                "'ordered_quantity',ol.quantity,'dispatched_quantity',"
                "COALESCE((SELECT sum(m.quantity) FROM inventory_movements m "
                "WHERE m.variant_id=ol.variant_id AND m.reference_id=o.id::text "
                "AND m.reference_type='order_fulfilment' AND m.movement_type='sale'),0),"
                "'remaining_quantity',GREATEST(ol.quantity-COALESCE((SELECT sum(m.quantity) "
                "FROM inventory_movements m WHERE m.variant_id=ol.variant_id "
                "AND m.reference_id=o.id::text AND m.reference_type='order_fulfilment' "
                "AND m.movement_type='sale'),0),0)) ORDER BY ol.id) "
                "FROM order_lines ol JOIN product_variants v ON v.id=ol.variant_id "
                "JOIN products p ON p.id=v.product_id WHERE ol.order_id=o.id), '[]'::json) AS order_lines "
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
                order = conn.execute("SELECT id, status, delivery_pin FROM orders WHERE id=%s FOR SHARE", (payload.order_id,)).fetchone()
                if order is None:
                    raise HTTPException(status_code=404, detail="Order not found")
                if order["status"] in {"cancelled", "delivered"}:
                    raise HTTPException(status_code=409, detail="Cannot create a shipment for a cancelled or delivered order")
                if order["delivery_pin"] and order["delivery_pin"].strip() != payload.delivery_pin:
                    raise HTTPException(status_code=422, detail="Shipment delivery PIN must match the order delivery PIN")
                reservation_locations = order_reservation_locations(conn, payload.order_id)
                if len(reservation_locations) != 1:
                    raise HTTPException(status_code=409, detail="The order must have one complete warehouse reservation before a shipment can be created")
                reserved_location_id = reservation_locations[0]
                if payload.location_id is not None and payload.location_id != reserved_location_id:
                    raise HTTPException(status_code=409, detail="Shipment origin must match the warehouse that reserved the order")
                existing = conn.execute("SELECT id FROM deliveries WHERE order_id=%s AND status NOT IN ('cancelled','returned','failed')", (payload.order_id,)).fetchone()
                if existing:
                    raise HTTPException(status_code=409, detail="An active shipment already exists for this order")
                ref = "SBD-" + uuid4().hex[:10].upper()
                row = conn.execute(
                    "INSERT INTO deliveries (shipment_reference, order_id, delivery_pin, recipient_name, recipient_phone, address, location_id, status, delivery_notes) "
                    "VALUES (%s,%s,%s,%s,%s,%s,%s,'pending',%s) RETURNING id, shipment_reference, order_id, delivery_pin, recipient_name, recipient_phone, address, location_id, status, delivery_notes, created_at, updated_at",
                    (ref, payload.order_id, payload.delivery_pin, payload.recipient_name, payload.recipient_phone, payload.address, reserved_location_id, payload.delivery_notes),
                ).fetchone()
        return row
    except HTTPException:
        raise
    except psycopg.Error as exc:
        raise _db_error(exc) from exc


@router.patch("/shipments/{shipment_id}/status")
def update_shipment_status(shipment_id: int, payload: DeliveryStatusUpdate, request: Request):
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
                    "SELECT d.status, d.order_id, o.status AS order_status, o.order_number, o.customer_name "
                    "FROM deliveries d JOIN orders o ON o.id=d.order_id "
                    "WHERE d.id=%s FOR UPDATE OF d, o",
                    (shipment_id,),
                ).fetchone()
                if current is None:
                    raise HTTPException(status_code=404, detail="Shipment not found")
                old = current["status"]
                is_dispatch_event = payload.status == "dispatched"
                repeat_dispatch = old == "dispatched" and is_dispatch_event
                if old == payload.status and not repeat_dispatch:
                    return {"id": shipment_id, "status": old}
                if payload.status not in transitions[old] and not repeat_dispatch:
                    raise HTTPException(status_code=409, detail=f"Cannot change shipment status from {old} to {payload.status}")

                dispatch_result = None
                if is_dispatch_event:
                    try:
                        dispatch_result = dispatch_shipment(
                            conn,
                            shipment_id=shipment_id,
                            order_id=int(current["order_id"]),
                            order_status=current["order_status"],
                            order_number=current["order_number"],
                            customer_name=current["customer_name"],
                            dispatch_id=str(payload.dispatch_id),
                            dispatch_lines=payload.dispatch_lines,
                            package_lines=payload.package_lines,
                            note=payload.note,
                            actor_id=getattr(request.state, "user_id", None),
                            actor_email=getattr(request.state, "user_email", None),
                        )
                    except FulfilmentDispatchError as exc:
                        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc
                    if dispatch_result["duplicate"]:
                        return {"id": shipment_id, "status": old, "duplicate": True}
                elif payload.status in {"in_transit", "delivered", "failed"}:
                    if order_has_reservation(conn, int(current["order_id"])):
                        raise HTTPException(status_code=409, detail="Dispatch all remaining reserved quantities before progressing this shipment")

                row = conn.execute(
                    "UPDATE deliveries SET status=%s, tracking_reference=COALESCE(%s,tracking_reference), "
                    "assigned_to=COALESCE(%s,assigned_to), updated_at=now() "
                    "WHERE id=%s RETURNING id, shipment_reference, status, tracking_reference, assigned_to, updated_at",
                    (payload.status, payload.tracking_reference, payload.assigned_to, shipment_id),
                ).fetchone()
                history_note = dispatch_result["history_note"] if is_dispatch_event else payload.note
                conn.execute(
                    "INSERT INTO delivery_status_history (delivery_id, from_status, to_status, note) VALUES (%s,%s,%s,%s)",
                    (shipment_id, old, payload.status, history_note),
                )
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
                "SELECT id, from_status, to_status, CASE WHEN note LIKE '[dispatch-id:%;payload-sha256:%' "
                "THEN substring(note from position(']' in note) + 2) ELSE note END AS note, changed_at "
                "FROM delivery_status_history WHERE delivery_id = %s "
                "ORDER BY changed_at DESC, id DESC LIMIT %s",
                (shipment_id, limit),
            ).fetchall()
        return {"shipment_id": shipment_id, "shipment_reference": shipment["shipment_reference"], "items": rows}
    except HTTPException:
        raise
    except psycopg.Error as exc:
        raise _db_error(exc) from exc
