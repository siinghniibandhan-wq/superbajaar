"""Persistent warehouse picking and packing operations.

Picking/packing are operational records only: they never change inventory
balances, reservations, movements, cost layers or accounting. Dispatch remains
an Inventory-owned stock issue and is exposed separately.
"""
from decimal import Decimal
import hashlib
import json
import uuid
from uuid import UUID

import psycopg
from fastapi import APIRouter, HTTPException, Query, Request
from psycopg.rows import dict_row
from pydantic import BaseModel, Field, field_validator, model_validator

from app.core.config import settings

router = APIRouter(prefix="/fulfilment", tags=["fulfilment"])


def _connect():
    if not settings.database_url:
        raise HTTPException(status_code=503, detail="Fulfilment database is not configured")
    try:
        return psycopg.connect(settings.database_url, row_factory=dict_row)
    except psycopg.Error as exc:
        raise HTTPException(status_code=503, detail="Fulfilment database is unavailable") from exc


def _actor(request: Request):
    user_id = getattr(request.state, "user_id", None)
    email = getattr(request.state, "user_email", None)
    if not user_id or not email:
        raise HTTPException(status_code=401, detail="A valid staff session is required")
    return int(user_id), str(email)


def _db_error(exc):
    if getattr(exc, "sqlstate", None) == "23503":
        return HTTPException(status_code=422, detail="Referenced shipment, order or product line does not exist")
    if getattr(exc, "sqlstate", None) == "23505":
        return HTTPException(status_code=409, detail="Fulfilment record already exists")
    return HTTPException(status_code=503, detail="Fulfilment storage is unavailable; verify migration 031")


class PickLineUpdate(BaseModel):
    picked_quantity: Decimal = Field(ge=0, max_digits=14, decimal_places=3)
    short_quantity: Decimal = Field(default=Decimal("0"), ge=0, max_digits=14, decimal_places=3)
    short_reason: str | None = Field(default=None, max_length=500)

    @model_validator(mode="after")
    def short_pick_requires_reason(self):
        if self.short_quantity > 0 and not (self.short_reason and self.short_reason.strip()):
            raise ValueError("short_reason is required when a line is short-picked")
        if self.short_quantity == 0 and self.short_reason and self.short_reason.strip():
            raise ValueError("short_reason is only allowed for a short-picked line")
        return self


class PackageLineInput(BaseModel):
    pick_task_line_id: int = Field(gt=0)
    order_line_id: int = Field(gt=0)
    quantity: Decimal = Field(gt=0, max_digits=14, decimal_places=3)


class PackageCreate(BaseModel):
    package_number: str = Field(min_length=1, max_length=60)
    weight_grams: Decimal | None = Field(default=None, gt=0, max_digits=12, decimal_places=2)
    length_mm: Decimal | None = Field(default=None, gt=0, max_digits=12, decimal_places=2)
    width_mm: Decimal | None = Field(default=None, gt=0, max_digits=12, decimal_places=2)
    height_mm: Decimal | None = Field(default=None, gt=0, max_digits=12, decimal_places=2)
    lines: list[PackageLineInput] = Field(min_length=1, max_length=100)

    @field_validator("package_number")
    @classmethod
    def trim_package_number(cls, value):
        value = value.strip()
        if not value:
            raise ValueError("Package number cannot be blank")
        return value

    @model_validator(mode="after")
    def unique_order_lines(self):
        ids = [line.order_line_id for line in self.lines]
        if len(ids) != len(set(ids)):
            raise ValueError("Package lines must contain unique order_line_id values")
        return self


@router.get("/pick-tasks")
def list_pick_tasks(
    status: str | None = Query(default=None, pattern=r"^(pending|in_progress|short|completed|cancelled)$"),
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
):
    try:
        with _connect() as conn:
            where = " WHERE t.status=%s" if status else ""
            params = (status, limit, offset) if status else (limit, offset)
            rows = conn.execute(
                "SELECT t.id,t.shipment_id,d.shipment_reference,t.order_id,o.order_number,t.status,"
                "t.assigned_to_user_id,t.assigned_to_name,t.started_at,t.completed_at,t.created_at,t.updated_at,"
                "(SELECT count(*) FROM fulfilment_pick_task_lines l WHERE l.pick_task_id=t.id) AS line_count "
                "FROM fulfilment_pick_tasks t JOIN deliveries d ON d.id=t.shipment_id "
                "JOIN orders o ON o.id=t.order_id" + where +
                " ORDER BY t.created_at DESC LIMIT %s OFFSET %s", params,
            ).fetchall()
            total = conn.execute(
                "SELECT count(*) AS total FROM fulfilment_pick_tasks t" + where,
                (status,) if status else (),
            ).fetchone()["total"]
        return {"items": rows, "total": total, "limit": limit, "offset": offset}
    except psycopg.Error as exc:
        raise _db_error(exc) from exc


@router.get("/pick-tasks/{task_id}")
def get_pick_task(task_id: int):
    try:
        with _connect() as conn:
            task = conn.execute(
                "SELECT t.*,d.shipment_reference,o.order_number FROM fulfilment_pick_tasks t "
                "JOIN deliveries d ON d.id=t.shipment_id JOIN orders o ON o.id=t.order_id WHERE t.id=%s",
                (task_id,),
            ).fetchone()
            if task is None:
                raise HTTPException(status_code=404, detail="Pick task not found")
            lines = conn.execute(
                "SELECT l.id,l.order_line_id,l.variant_id,l.location_id,sl.name AS location_name,v.sku,p.name AS product_name,"
                "l.requested_quantity,l.picked_quantity,l.short_quantity,l.short_reason,"
                "COALESCE((SELECT sum(pl.quantity) FROM fulfilment_package_lines pl JOIN fulfilment_packages fp ON fp.id=pl.package_id "
                "WHERE pl.pick_task_line_id=l.id AND fp.status <> 'cancelled'),0) AS packed_quantity "
                 "FROM fulfilment_pick_task_lines l JOIN stock_locations sl ON sl.id=l.location_id JOIN product_variants v ON v.id=l.variant_id "
                "JOIN products p ON p.id=v.product_id WHERE l.pick_task_id=%s ORDER BY l.id",
                (task_id,),
            ).fetchall()
            packages = conn.execute(
                "SELECT id,package_number,status,weight_grams,length_mm,width_mm,height_mm,sealed_at "
                "FROM fulfilment_packages WHERE shipment_id=%s ORDER BY id", (task["shipment_id"],),
            ).fetchall()
        return {**task, "lines": lines, "packages": packages}
    except HTTPException:
        raise
    except psycopg.Error as exc:
        raise _db_error(exc) from exc


@router.post("/shipments/{shipment_id}/pick-task", status_code=201)
def create_pick_task(shipment_id: int, request: Request):
    actor_id, _ = _actor(request)
    try:
        with _connect() as conn:
            with conn.transaction():
                shipment = conn.execute(
                    "SELECT d.id,d.order_id,d.status,o.status AS order_status "
                    "FROM deliveries d JOIN orders o ON o.id=d.order_id "
                    "WHERE d.id=%s FOR UPDATE OF d,o", (shipment_id,),
                ).fetchone()
                if shipment is None:
                    raise HTTPException(status_code=404, detail="Shipment not found")
                if shipment["status"] in {"cancelled","returned","delivered"} or shipment["order_status"] != "ready_for_dispatch":
                    raise HTTPException(status_code=409, detail="Only active shipments for orders ready for dispatch can be picked")
                existing = conn.execute(
                    "SELECT id FROM fulfilment_pick_tasks WHERE shipment_id=%s", (shipment_id,),
                ).fetchone()
                if existing:
                    raise HTTPException(status_code=409, detail="A pick task already exists for this shipment")
                conn.execute(
                    "SELECT id FROM order_lines WHERE order_id=%s ORDER BY id FOR UPDATE",
                    (shipment["order_id"],),
                ).fetchall()
                rows = conn.execute(
                    "SELECT ol.id AS order_line_id,ol.variant_id,m.location_id,"
                    "SUM(CASE WHEN m.movement_type='reservation' AND m.reference_type='order_reservation' THEN m.quantity "
                    "WHEN m.movement_type='release' AND m.reference_type='order_reservation' THEN -m.quantity "
                    "WHEN m.movement_type='sale' AND m.reference_type='order_fulfilment' THEN -m.quantity ELSE 0 END) AS outstanding "
                    "FROM order_lines ol JOIN inventory_movements m ON m.variant_id=ol.variant_id "
                    "AND m.reference_id=ol.order_id::text AND m.reference_type IN ('order_reservation','order_fulfilment') "
                    "WHERE ol.order_id=%s GROUP BY ol.id,ol.variant_id,m.location_id "
                    "HAVING SUM(CASE WHEN m.movement_type='reservation' AND m.reference_type='order_reservation' THEN m.quantity "
                    "WHEN m.movement_type='release' AND m.reference_type='order_reservation' THEN -m.quantity "
                    "WHEN m.movement_type='sale' AND m.reference_type='order_fulfilment' THEN -m.quantity ELSE 0 END)>0 "
                    "ORDER BY m.location_id,ol.id",
                    (shipment["order_id"],),
                ).fetchall()
                if not rows or any(Decimal(str(row["outstanding"])) <= 0 for row in rows):
                    raise HTTPException(status_code=409, detail="No fully reserved outstanding order lines are available to pick")
                task = conn.execute(
                    "INSERT INTO fulfilment_pick_tasks(shipment_id,order_id,status,created_by_user_id) "
                    "VALUES(%s,%s,'pending',%s) RETURNING id,shipment_id,order_id,status,created_at",
                    (shipment_id, shipment["order_id"], actor_id),
                ).fetchone()
                for row in rows:
                    conn.execute(
                        "INSERT INTO fulfilment_pick_task_lines(pick_task_id,order_line_id,variant_id,location_id,requested_quantity) "
                        "VALUES(%s,%s,%s,%s,%s)",
                        (task["id"], row["order_line_id"], row["variant_id"], row["location_id"], row["outstanding"]),
                    )
        return task
    except HTTPException:
        raise
    except psycopg.Error as exc:
        raise _db_error(exc) from exc


@router.patch("/pick-tasks/{task_id}/lines/{line_id}")
def update_pick_line(task_id: int, line_id: int, payload: PickLineUpdate, request: Request):
    _actor(request)
    try:
        with _connect() as conn:
            with conn.transaction():
                task = conn.execute(
                    "SELECT status FROM fulfilment_pick_tasks WHERE id=%s FOR UPDATE", (task_id,),
                ).fetchone()
                if task is None:
                    raise HTTPException(status_code=404, detail="Pick task not found")
                if task["status"] not in {"pending","in_progress","short"}:
                    raise HTTPException(status_code=409, detail="This pick task is no longer editable")
                line = conn.execute(
                    "SELECT requested_quantity FROM fulfilment_pick_task_lines WHERE id=%s AND pick_task_id=%s FOR UPDATE",
                    (line_id, task_id),
                ).fetchone()
                if line is None:
                    raise HTTPException(status_code=404, detail="Pick task line not found")
                if payload.picked_quantity + payload.short_quantity > line["requested_quantity"]:
                    raise HTTPException(status_code=422, detail="Picked plus short quantity cannot exceed requested quantity")
                conn.execute(
                    "UPDATE fulfilment_pick_task_lines SET picked_quantity=%s,short_quantity=%s,short_reason=%s,updated_at=now() WHERE id=%s",
                    (payload.picked_quantity,payload.short_quantity,payload.short_reason.strip() if payload.short_reason else None,line_id),
                )
                conn.execute(
                    "UPDATE fulfilment_pick_tasks SET status='in_progress',started_at=COALESCE(started_at,now()),updated_at=now() WHERE id=%s",
                    (task_id,),
                )
        return {"id": line_id, "picked_quantity": payload.picked_quantity, "short_quantity": payload.short_quantity}
    except HTTPException:
        raise
    except psycopg.Error as exc:
        raise _db_error(exc) from exc


@router.post("/pick-tasks/{task_id}/complete")
def complete_pick_task(task_id: int, request: Request):
    _actor(request)
    try:
        with _connect() as conn:
            with conn.transaction():
                task = conn.execute("SELECT id,status FROM fulfilment_pick_tasks WHERE id=%s FOR UPDATE",(task_id,)).fetchone()
                if task is None:
                    raise HTTPException(status_code=404, detail="Pick task not found")
                if task["status"] not in {"in_progress","short"}:
                    raise HTTPException(status_code=409, detail="Start and record the pick before completing it")
                summary = conn.execute(
                    "SELECT count(*) AS total,count(*) FILTER (WHERE picked_quantity+short_quantity=requested_quantity) AS complete,"
                    "COALESCE(sum(short_quantity),0) AS short_total FROM fulfilment_pick_task_lines WHERE pick_task_id=%s",
                    (task_id,),
                ).fetchone()
                if not summary["total"] or summary["total"] != summary["complete"]:
                    raise HTTPException(status_code=409, detail="Every pick line must be fully picked or explicitly short-picked")
                status = "short" if Decimal(str(summary["short_total"])) > 0 else "completed"
                row = conn.execute(
                    "UPDATE fulfilment_pick_tasks SET status=%s,completed_at=now(),updated_at=now() WHERE id=%s "
                    "RETURNING id,status,completed_at", (status,task_id),
                ).fetchone()
        return row
    except HTTPException:
        raise
    except psycopg.Error as exc:
        raise _db_error(exc) from exc


@router.post("/shipments/{shipment_id}/packages", status_code=201)
def create_package(shipment_id: int, payload: PackageCreate, request: Request):
    actor_id, _ = _actor(request)
    try:
        with _connect() as conn:
            with conn.transaction():
                task = conn.execute(
                    "SELECT id,status FROM fulfilment_pick_tasks WHERE shipment_id=%s FOR UPDATE",
                    (shipment_id,),
                ).fetchone()
                if task is None or task["status"] not in {"completed","short"}:
                    raise HTTPException(status_code=409, detail="Complete the pick task before creating packages")
                package = conn.execute(
                    "INSERT INTO fulfilment_packages(shipment_id,package_number,weight_grams,length_mm,width_mm,height_mm,created_by_user_id) "
                    "VALUES(%s,%s,%s,%s,%s,%s,%s) RETURNING id,shipment_id,package_number,status,created_at",
                    (shipment_id,payload.package_number,payload.weight_grams,payload.length_mm,payload.width_mm,payload.height_mm,actor_id),
                ).fetchone()
                for item in payload.lines:
                    pick_line = conn.execute(
                        "SELECT l.order_line_id,l.variant_id,l.picked_quantity,"
                        "COALESCE((SELECT sum(pl.quantity) FROM fulfilment_package_lines pl WHERE pl.pick_task_line_id=l.id),0) AS packed "
                        "FROM fulfilment_pick_task_lines l WHERE l.id=%s AND l.pick_task_id=%s FOR UPDATE",
                        (item.pick_task_line_id,task["id"]),
                    ).fetchone()
                    if pick_line is None or int(pick_line["order_line_id"]) != item.order_line_id:
                        raise HTTPException(status_code=422, detail="Package line must reference a line from this shipment's pick task")
                    available = Decimal(str(pick_line["picked_quantity"])) - Decimal(str(pick_line["packed"]))
                    if item.quantity > available:
                        raise HTTPException(status_code=409, detail="Package quantity exceeds the picked quantity not yet packed")
                    conn.execute(
                        "INSERT INTO fulfilment_package_lines(package_id,pick_task_line_id,order_line_id,variant_id,quantity) "
                        "VALUES(%s,%s,%s,%s,%s)",
                        (package["id"],item.pick_task_line_id,item.order_line_id,pick_line["variant_id"],item.quantity),
                    )
        return package
    except HTTPException:
        raise
    except psycopg.Error as exc:
        raise _db_error(exc) from exc


@router.patch("/packages/{package_id}/seal")
def seal_package(package_id: int, request: Request):
    _actor(request)
    try:
        with _connect() as conn:
            with conn.transaction():
                package = conn.execute("SELECT id,shipment_id,status FROM fulfilment_packages WHERE id=%s FOR UPDATE",(package_id,)).fetchone()
                if package is None:
                    raise HTTPException(status_code=404, detail="Package not found")
                if package["status"] != "draft":
                    raise HTTPException(status_code=409, detail="Only draft packages can be sealed")
                count = conn.execute("SELECT count(*) AS n FROM fulfilment_package_lines WHERE package_id=%s",(package_id,)).fetchone()["n"]
                if not count:
                    raise HTTPException(status_code=409, detail="An empty package cannot be sealed")
                row = conn.execute(
                    "UPDATE fulfilment_packages SET status='sealed',sealed_at=now(),updated_at=now() WHERE id=%s "
                    "RETURNING id,package_number,status,sealed_at", (package_id,),
                ).fetchone()
                pick = conn.execute(
                    "SELECT t.id,d.status AS shipment_status FROM fulfilment_pick_tasks t "
                    "JOIN deliveries d ON d.id=t.shipment_id WHERE t.shipment_id=%s FOR UPDATE OF t,d",
                    (package["shipment_id"],),
                ).fetchone()
                completeness = conn.execute(
                    "SELECT (NOT EXISTS (SELECT 1 FROM fulfilment_pick_task_lines l WHERE l.pick_task_id=%s "
                    "AND l.picked_quantity <> COALESCE((SELECT sum(pl.quantity) FROM fulfilment_package_lines pl "
                    "JOIN fulfilment_packages p ON p.id=pl.package_id WHERE pl.pick_task_line_id=l.id AND p.status='sealed'),0)) "
                    "AND NOT EXISTS (SELECT 1 FROM fulfilment_packages p WHERE p.shipment_id=%s AND p.status='draft')) AS complete",
                    (pick["id"],package["shipment_id"]),
                ).fetchone()
                if completeness and completeness["complete"] and pick["shipment_status"] == "pending":
                    conn.execute("UPDATE deliveries SET status='packed',updated_at=now() WHERE id=%s",(package["shipment_id"],))
                    conn.execute(
                        "INSERT INTO delivery_status_history(delivery_id,from_status,to_status,note) VALUES(%s,'pending','packed','All picked quantities packed and packages sealed')",
                        (package["shipment_id"],),
                    )
        return row
    except HTTPException:
        raise
    except psycopg.Error as exc:
        raise _db_error(exc) from exc


class ReturnLineInput(BaseModel):
    order_line_id: int = Field(gt=0)
    quantity: Decimal = Field(gt=0, max_digits=14, decimal_places=3)


class ReturnCreate(BaseModel):
    reason: str = Field(min_length=3, max_length=1000)
    lines: list[ReturnLineInput] = Field(min_length=1, max_length=100)

    @field_validator("reason")
    @classmethod
    def trim_reason(cls, value):
        value = value.strip()
        if len(value) < 3:
            raise ValueError("Return reason must contain at least three characters")
        return value

    @model_validator(mode="after")
    def unique_lines(self):
        ids = [line.order_line_id for line in self.lines]
        if len(ids) != len(set(ids)):
            raise ValueError("Return lines must contain unique order_line_id values")
        return self


class ReturnLineInspection(BaseModel):
    received_quantity: Decimal = Field(ge=0, max_digits=14, decimal_places=3)
    inspection_status: str
    inspection_note: str | None = Field(default=None, max_length=1000)

    @field_validator("inspection_status")
    @classmethod
    def valid_inspection(cls, value):
        if value not in {"accepted", "rejected", "damaged", "quarantined"}:
            raise ValueError("Unsupported return inspection status")
        return value


@router.get("/returns")
def list_returns(
    status: str | None = Query(default=None, pattern=r"^(requested|authorised|received|inspection|approved|rejected|closed)$"),
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
):
    try:
        with _connect() as conn:
            where = " WHERE r.status=%s" if status else ""
            params = (status, limit, offset) if status else (limit, offset)
            rows = conn.execute(
                "SELECT r.id,r.return_number,r.shipment_id,d.shipment_reference,r.order_id,o.order_number,"
                "r.status,r.reason,r.received_at,r.created_at,"
                "(SELECT count(*) FROM fulfilment_return_lines l WHERE l.return_id=r.id) AS line_count "
                "FROM fulfilment_returns r JOIN deliveries d ON d.id=r.shipment_id "
                "JOIN orders o ON o.id=r.order_id" + where +
                " ORDER BY r.created_at DESC LIMIT %s OFFSET %s", params,
            ).fetchall()
            total = conn.execute("SELECT count(*) AS total FROM fulfilment_returns r" + where,
                                 (status,) if status else ()).fetchone()["total"]
        return {"items": rows, "total": total, "limit": limit, "offset": offset}
    except psycopg.Error as exc:
        raise _db_error(exc) from exc


@router.post("/shipments/{shipment_id}/returns", status_code=201)
def create_return(shipment_id: int, payload: ReturnCreate, request: Request):
    actor_id, _ = _actor(request)
    try:
        with _connect() as conn:
            with conn.transaction():
                shipment = conn.execute(
                    "SELECT d.id,d.order_id,d.status FROM deliveries d WHERE d.id=%s FOR UPDATE",
                    (shipment_id,),
                ).fetchone()
                if shipment is None:
                    raise HTTPException(status_code=404, detail="Shipment not found")
                if shipment["status"] not in {"delivered", "returned", "failed", "in_transit"}:
                    raise HTTPException(status_code=409, detail="Returns can only be requested after dispatch")
                order_lines = conn.execute(
                    "SELECT ol.id,ol.variant_id,ol.quantity,"
                    "COALESCE((SELECT sum(io.quantity) FROM inventory_order_issues io "
                    "WHERE io.order_id=ol.order_id AND io.order_line_id=ol.id),0) AS dispatched,"
                    "COALESCE((SELECT sum(CASE WHEN rr.status='closed' THEN rl.received_quantity ELSE rl.requested_quantity END) "
                    "FROM fulfilment_return_lines rl JOIN fulfilment_returns rr ON rr.id=rl.return_id "
                    "WHERE rl.order_line_id=ol.id AND rr.status<>'rejected'),0) AS already_requested "
                    "FROM order_lines ol WHERE ol.order_id=%s ORDER BY ol.id FOR UPDATE",
                    (shipment["order_id"],),
                ).fetchall()
                by_id = {int(line["id"]): line for line in order_lines}
                for item in payload.lines:
                    line = by_id.get(item.order_line_id)
                    if line is None:
                        raise HTTPException(status_code=422, detail="Return line does not belong to this order")
                    remaining = Decimal(str(line["dispatched"])) - Decimal(str(line["already_requested"]))
                    if item.quantity > remaining:
                        raise HTTPException(status_code=409, detail="Return quantity exceeds dispatched quantity not already requested")
                number = "SBR-" + uuid.uuid4().hex[:12].upper()
                ret = conn.execute(
                    "INSERT INTO fulfilment_returns(return_number,shipment_id,order_id,status,reason,requested_by_user_id) "
                    "VALUES(%s,%s,%s,'requested',%s,%s) RETURNING id,return_number,shipment_id,order_id,status,reason,created_at",
                    (number,shipment_id,shipment["order_id"],payload.reason,actor_id),
                ).fetchone()
                for item in payload.lines:
                    line = by_id[item.order_line_id]
                    conn.execute(
                        "INSERT INTO fulfilment_return_lines(return_id,order_line_id,variant_id,requested_quantity) "
                        "VALUES(%s,%s,%s,%s)",
                        (ret["id"],item.order_line_id,line["variant_id"],item.quantity),
                    )
        return ret
    except HTTPException:
        raise
    except psycopg.Error as exc:
        raise _db_error(exc) from exc


@router.post("/returns/{return_id}/receive")
def receive_return(return_id: int, request: Request):
    actor_id, _ = _actor(request)
    try:
        with _connect() as conn:
            with conn.transaction():
                ret = conn.execute("SELECT id,status FROM fulfilment_returns WHERE id=%s FOR UPDATE",(return_id,)).fetchone()
                if ret is None:
                    raise HTTPException(status_code=404, detail="Return not found")
                if ret["status"] not in {"requested","authorised"}:
                    raise HTTPException(status_code=409, detail="Return is not awaiting physical receipt")
                lines = conn.execute("SELECT id,requested_quantity FROM fulfilment_return_lines WHERE return_id=%s FOR UPDATE",(return_id,)).fetchall()
                if not lines:
                    raise HTTPException(status_code=409, detail="Return has no lines")
                conn.execute(
                    "UPDATE fulfilment_return_lines SET received_quantity=requested_quantity,updated_at=now() WHERE return_id=%s",
                    (return_id,),
                )
                row = conn.execute(
                    "UPDATE fulfilment_returns SET status='inspection',received_by_user_id=%s,received_at=now(),updated_at=now() "
                    "WHERE id=%s RETURNING id,return_number,status,received_at", (actor_id,return_id),
                ).fetchone()
        return row
    except HTTPException:
        raise
    except psycopg.Error as exc:
        raise _db_error(exc) from exc


@router.patch("/returns/{return_id}/lines/{line_id}/inspection")
def inspect_return_line(return_id: int, line_id: int, payload: ReturnLineInspection, request: Request):
    actor_id, _ = _actor(request)
    try:
        with _connect() as conn:
            with conn.transaction():
                ret = conn.execute("SELECT status FROM fulfilment_returns WHERE id=%s FOR UPDATE",(return_id,)).fetchone()
                if ret is None:
                    raise HTTPException(status_code=404, detail="Return not found")
                if ret["status"] != "inspection":
                    raise HTTPException(status_code=409, detail="Return must be physically received before inspection")
                line = conn.execute(
                    "SELECT requested_quantity,received_quantity FROM fulfilment_return_lines "
                    "WHERE id=%s AND return_id=%s FOR UPDATE",(line_id,return_id),
                ).fetchone()
                if line is None:
                    raise HTTPException(status_code=404, detail="Return line not found")
                if payload.received_quantity > line["requested_quantity"]:
                    raise HTTPException(status_code=422, detail="Received quantity cannot exceed the requested quantity")
                if payload.received_quantity != line["received_quantity"]:
                    conn.execute(
                        "UPDATE fulfilment_return_lines SET received_quantity=%s,updated_at=now() WHERE id=%s",
                        (payload.received_quantity,line_id),
                    )
                conn.execute(
                    "UPDATE fulfilment_return_lines SET inspection_status=%s,inspection_note=%s,"
                    "inspected_by_user_id=%s,inspected_at=now(),updated_at=now() WHERE id=%s",
                    (payload.inspection_status,payload.inspection_note,actor_id,line_id),
                )
                pending = conn.execute(
                    "SELECT count(*) AS n FROM fulfilment_return_lines WHERE return_id=%s AND inspection_status='pending'",
                    (return_id,),
                ).fetchone()["n"]
                status = "inspection" if pending else "approved"
                conn.execute("UPDATE fulfilment_returns SET status=%s,updated_at=now() WHERE id=%s",(status,return_id))
        return {"id":line_id,"inspection_status":payload.inspection_status,"return_status":status,
                "inventory_disposition_required": status=="approved"}
    except HTTPException:
        raise
    except psycopg.Error as exc:
        raise _db_error(exc) from exc


@router.get("/returns/{return_id}")
def get_return(return_id: int):
    try:
        with _connect() as conn:
            ret = conn.execute(
                "SELECT r.*,d.shipment_reference,o.order_number FROM fulfilment_returns r "
                "JOIN deliveries d ON d.id=r.shipment_id JOIN orders o ON o.id=r.order_id WHERE r.id=%s",
                (return_id,),
            ).fetchone()
            if ret is None:
                raise HTTPException(status_code=404, detail="Return not found")
            lines = conn.execute(
                "SELECT l.id,l.order_line_id,l.variant_id,v.sku,p.name AS product_name,"
                "l.requested_quantity,l.received_quantity,l.inspection_status,l.disposition,"
                "l.inventory_movement_id,l.disposition_location_id,l.accounting_voucher_id,l.disposition_posted_at,"
                "l.inspection_note,l.inspected_at,"
                "COALESCE((SELECT sum(cl.remaining_quantity) FROM fulfilment_return_dispatch_allocations rda "
                "JOIN inventory_cost_layers cl ON cl.receipt_movement_id=rda.inventory_movement_id "
                "WHERE rda.return_line_id=l.id AND rda.disposition='quarantine'),0) AS quarantine_remaining_quantity,"
                "COALESCE((SELECT sum(cl.remaining_quantity) FROM fulfilment_return_dispatch_allocations rda "
                "JOIN inventory_cost_layers cl ON cl.receipt_movement_id=rda.inventory_movement_id "
                "WHERE rda.return_line_id=l.id AND rda.disposition='quarantine' "
                "AND (cl.expiry_date IS NULL OR cl.expiry_date>=CURRENT_DATE)),0) AS quarantine_releasable_quantity,"
                "COALESCE((SELECT sum(m.quantity) FROM inventory_movements m "
                "WHERE m.reference_type='fulfilment_return_quarantine_release' AND m.movement_type='transfer_out' "
                "AND m.reference_id LIKE l.id::text || ':%'),0) AS quarantine_released_quantity "
                "FROM fulfilment_return_lines l JOIN product_variants v ON v.id=l.variant_id "
                "JOIN products p ON p.id=v.product_id WHERE l.return_id=%s ORDER BY l.id",
                (return_id,),
            ).fetchall()
        return {**ret,"lines":lines}
    except HTTPException:
        raise
    except psycopg.Error as exc:
        raise _db_error(exc) from exc


class ReturnDisposition(BaseModel):
    disposition: str = Field(pattern=r"^(restock|quarantine|repair|write_off)$")
    location_id: int | None = Field(default=None, gt=0)
    note: str | None = Field(default=None, max_length=1000)

    @model_validator(mode="after")
    def location_matches_disposition(self):
        if self.disposition == "write_off" and self.location_id is not None:
            raise ValueError("Write-off does not accept a stock location")
        if self.disposition != "write_off" and self.location_id is None:
            raise ValueError("A controlled destination location is required")
        return self


@router.post("/returns/{return_id}/lines/{line_id}/disposition")
def post_return_disposition(return_id: int, line_id: int, payload: ReturnDisposition, request: Request):
    """Post inspected returned stock, original cost and accounting reclassification atomically."""
    actor_id, actor_email = _actor(request)
    if getattr(request.state, "role", None) not in {"owner", "admin", "manager"}:
        raise HTTPException(status_code=403, detail="Only owner, admin or manager may post return disposition")
    from app.services.inventory_costing import create_cost_layer, money
    from app.services.accounting_posting import PostingConfigurationError, build_inventory_mapping_lines

    try:
        with _connect() as conn:
            with conn.transaction():
                ret = conn.execute(
                    "SELECT id,order_id,status FROM fulfilment_returns WHERE id=%s FOR UPDATE",
                    (return_id,),
                ).fetchone()
                if ret is None:
                    raise HTTPException(status_code=404, detail="Return not found")
                line = conn.execute(
                    "SELECT id,order_line_id,variant_id,received_quantity,inspection_status,disposition,"
                    "disposition_location_id,accounting_voucher_id,disposition_posted_at "
                    "FROM fulfilment_return_lines WHERE id=%s AND return_id=%s FOR UPDATE",
                    (line_id, return_id),
                ).fetchone()
                if line is None:
                    raise HTTPException(status_code=404, detail="Return line not found")
                if line["disposition_posted_at"] is not None:
                    if line["disposition"] == payload.disposition and line["disposition_location_id"] == payload.location_id:
                        return {"id": line_id, "status": "posted", "duplicate": True,
                                "accounting_voucher_id": line["accounting_voucher_id"]}
                    raise HTTPException(status_code=409, detail="Return disposition has already been posted and is immutable")
                if ret["status"] != "approved":
                    raise HTTPException(status_code=409, detail="Every return line must be inspected before disposition")
                received = Decimal(str(line["received_quantity"]))
                if received <= 0:
                    raise HTTPException(status_code=409, detail="A return with no physically received quantity cannot be disposed")
                allowed_inspections = {
                    "restock": {"accepted"},
                    "quarantine": {"quarantined", "damaged"},
                    "repair": {"quarantined", "damaged"},
                    "write_off": {"damaged", "rejected", "quarantined"},
                }
                if line["inspection_status"] not in allowed_inspections[payload.disposition]:
                    raise HTTPException(status_code=409, detail="Inspection result is not eligible for this disposition")

                destination = None
                if payload.disposition != "write_off":
                    destination = conn.execute(
                        "SELECT id,establishment_id,is_active,is_fulfillable FROM stock_locations "
                        "WHERE id=%s FOR UPDATE",
                        (payload.location_id,),
                    ).fetchone()
                    if destination is None or not destination["is_active"]:
                        raise HTTPException(status_code=409, detail="Destination stock location must exist and be active")
                    if payload.disposition == "restock" and not destination["is_fulfillable"]:
                        raise HTTPException(status_code=409, detail="Restock destination must be a fulfilable stock location")
                    if payload.disposition in {"quarantine", "repair"} and destination["is_fulfillable"]:
                        raise HTTPException(status_code=409, detail="Quarantine and repair require a non-fulfillable holding location")

                source_rows = conn.execute(
                    "SELECT io.movement_id,im.location_id,he.code AS legal_entity_code,ica.cost_layer_id,ica.quantity,ica.unit_cost,"
                    "cl.batch_code,cl.manufacture_date,cl.expiry_date,cl.goods_receipt_line_id,"
                    "COALESCE((SELECT sum(rda.quantity) FROM fulfilment_return_dispatch_allocations rda "
                    "WHERE rda.source_dispatch_movement_id=io.movement_id AND rda.source_cost_layer_id=ica.cost_layer_id),0) AS returned_quantity "
                    "FROM inventory_order_issues io JOIN inventory_movements im ON im.id=io.movement_id "
                    "JOIN stock_locations sl ON sl.id=im.location_id "
                    "JOIN hr_establishments he ON he.id=sl.establishment_id "
                    "JOIN inventory_cost_allocations ica ON ica.issue_movement_id=io.movement_id "
                    "JOIN inventory_cost_layers cl ON cl.id=ica.cost_layer_id "
                    "WHERE io.order_id=%s AND io.order_line_id=%s "
                    "ORDER BY im.created_at,im.id,ica.id FOR UPDATE OF io,im,ica,cl",
                    (ret["order_id"], line["order_line_id"]),
                ).fetchall()
                if not source_rows:
                    raise HTTPException(status_code=409, detail="Original dispatch cost allocations are missing; return cannot be valued")
                if destination is not None:
                    source_establishments = conn.execute(
                        "SELECT DISTINCT establishment_id FROM stock_locations WHERE id=ANY(%s)",
                        ([row["location_id"] for row in source_rows],),
                    ).fetchall()
                    source_legal_entities = {row["legal_entity_code"] for row in source_rows}
                    if (len(source_establishments) != 1
                            or source_establishments[0]["establishment_id"] != destination["establishment_id"]
                            or len(source_legal_entities) != 1):
                        raise HTTPException(status_code=409, detail="Return disposition must remain within the original legal establishment")

                total_cost = Decimal("0.00")
                primary_movement_id = None
                remaining = received
                for source in source_rows:
                    available = Decimal(str(source["quantity"])) - Decimal(str(source["returned_quantity"]))
                    if available <= 0 or remaining <= 0:
                        continue
                    take = min(available, remaining)
                    unit_cost = Decimal(str(source["unit_cost"]))
                    cost = money(take * unit_cost)
                    movement_id = None
                    if destination is not None:
                        movement = conn.execute(
                            "INSERT INTO inventory_movements(variant_id,location_id,movement_type,quantity,reference_type,reference_id,note) "
                            "VALUES(%s,%s,'return',%s,'fulfilment_return',%s,%s) RETURNING id",
                            (line["variant_id"], payload.location_id, take, str(return_id),
                             (payload.note or f"Return {return_id} disposition: {payload.disposition}")[:500]),
                        ).fetchone()
                        movement_id = movement["id"]
                        if primary_movement_id is None:
                            primary_movement_id = movement_id
                        conn.execute(
                            "INSERT INTO inventory_balances(variant_id,location_id,on_hand,reserved) VALUES(%s,%s,%s,0) "
                            "ON CONFLICT(variant_id,location_id) DO UPDATE SET on_hand=inventory_balances.on_hand+EXCLUDED.on_hand,updated_at=now()",
                            (line["variant_id"], payload.location_id, take),
                        )
                        create_cost_layer(
                            conn, movement_id=movement_id, variant_id=line["variant_id"],
                            location_id=payload.location_id, quantity=take, unit_cost=unit_cost,
                            goods_receipt_line_id=source["goods_receipt_line_id"],
                            batch_code=source["batch_code"], manufacture_date=source["manufacture_date"],
                            expiry_date=source["expiry_date"],
                            source_layer_id=source["cost_layer_id"],
                        )
                    conn.execute(
                        "INSERT INTO fulfilment_return_dispatch_allocations(return_line_id,source_dispatch_movement_id,"
                        "source_cost_layer_id,quantity,unit_cost,total_cost,disposition,destination_location_id,inventory_movement_id) "
                        "VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                        (line_id,source["movement_id"],source["cost_layer_id"],take,unit_cost,cost,
                         payload.disposition,payload.location_id,movement_id),
                    )
                    total_cost += cost
                    remaining -= take
                if remaining > 0:
                    raise HTTPException(status_code=409, detail=f"Return quantity exceeds remaining dispatched valued quantity by {remaining}")

                total_cost = money(total_cost)
                voucher_id = None
                if total_cost > 0:
                    from app.api import accounting
                    event_date = accounting._today()
                    event_type = "inventory_return_writeoff" if payload.disposition == "write_off" else "inventory_return"
                    debit_role = "inventory_return_writeoff_expense" if payload.disposition == "write_off" else "inventory_asset"
                    legal_entity_code = next(iter(source_legal_entities)) if payload.disposition != "write_off" else source_rows[0]["legal_entity_code"]
                    if len({row["legal_entity_code"] for row in source_rows}) != 1:
                        raise HTTPException(status_code=409, detail="Original dispatch allocations span multiple legal entities")
                    mappings = conn.execute(
                        "SELECT * FROM accounting_event_account_mappings WHERE legal_entity_code=%s "
                        "AND source_module='inventory' AND event_type=%s AND status='approved' "
                        "AND effective_from<=%s AND (effective_to IS NULL OR effective_to>=%s)",
                        (legal_entity_code,event_type,event_date,event_date),
                    ).fetchall()
                    try:
                        journal_lines = build_inventory_mapping_lines(
                            amount=total_cost,mappings=mappings,legal_entity_code=legal_entity_code,
                            event_type=event_type,debit_role=debit_role,
                            credit_role="inventory_cogs_reversal",event_date=event_date,
                            narration=f"Return {payload.disposition} against order {ret['order_id']}",
                        )
                    except PostingConfigurationError as exc:
                        raise HTTPException(status_code=409,detail=f"Return accounting blocked by Finance mapping: {exc}") from exc
                    voucher_id = accounting._post_voucher(
                        conn,
                        {"voucher_type":"journal","voucher_date":event_date,
                         "narration":f"Inventory return disposition {return_id}/{line_id}",
                         "reference":f"Return {return_id} line {line_id}",
                         "taxable_total":total_cost,"total_amount":total_cost,
                         "source_type":"fulfilment_return_line","source_id":str(line_id),
                         "idempotency_key":f"fulfilment-return-line:{line_id}"},
                        journal_lines,(actor_id,actor_email),
                    )
                    conn.execute(
                        "UPDATE fulfilment_return_dispatch_allocations SET accounting_voucher_id=%s WHERE return_line_id=%s",
                        (voucher_id,line_id),
                    )

                conn.execute(
                    "UPDATE fulfilment_return_lines SET disposition=%s,disposition_location_id=%s,"
                    "inventory_movement_id=%s,accounting_voucher_id=%s,disposition_posted_at=now(),updated_at=now() WHERE id=%s",
                    (payload.disposition,payload.location_id,primary_movement_id,voucher_id,line_id),
                )
                remaining_lines = conn.execute(
                    "SELECT count(*) AS n FROM fulfilment_return_lines WHERE return_id=%s AND disposition_posted_at IS NULL",
                    (return_id,),
                ).fetchone()["n"]
                if remaining_lines == 0:
                    conn.execute("UPDATE fulfilment_returns SET status='closed',closed_at=now(),updated_at=now() WHERE id=%s",
                                 (return_id,))
        return {"id":line_id,"status":"posted","duplicate":False,"disposition":payload.disposition,
                "location_id":payload.location_id,"total_cost":total_cost,"accounting_voucher_id":voucher_id}
    except HTTPException:
        raise
    except psycopg.Error as exc:
        raise _db_error(exc) from exc


class ReturnQuarantineRelease(BaseModel):
    destination_location_id: int = Field(gt=0)
    idempotency_key: UUID
    reason: str = Field(min_length=3, max_length=1000)

    @field_validator("reason")
    @classmethod
    def clean_reason(cls, value):
        value = value.strip()
        if len(value) < 3:
            raise ValueError("A release reason of at least 3 characters is required")
        return value


@router.post("/returns/{return_id}/lines/{line_id}/release-quarantine")
def release_return_quarantine(return_id: int, line_id: int, payload: ReturnQuarantineRelease, request: Request):
    """Move inspected customer-return quarantine stock to a saleable same-entity facility."""
    actor_id, actor_email = _actor(request)
    if getattr(request.state, "role", None) not in {"owner", "admin", "manager"}:
        raise HTTPException(status_code=403, detail="Only owner, admin or manager may release returned quarantine stock")
    from app.services.inventory_costing import create_cost_layer, money

    reference_id = f"{line_id}:{payload.idempotency_key}"
    canonical = {
        "return_id": return_id, "line_id": line_id,
        "destination_location_id": payload.destination_location_id, "reason": payload.reason,
    }
    payload_hash = hashlib.sha256(json.dumps(canonical, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()
    note = f"Return line {line_id} quarantine release: {payload.reason} [payload_sha256={payload_hash}]"
    try:
        with _connect() as conn:
            with conn.transaction():
                conn.execute("SELECT pg_advisory_xact_lock(hashtextextended(%s,0))", (f"return-quarantine-release:{reference_id}",))
                prior = conn.execute(
                    "SELECT id,quantity,note FROM inventory_movements WHERE reference_type='fulfilment_return_quarantine_release' "
                    "AND reference_id=%s AND movement_type='transfer_out' ORDER BY id LIMIT 1",
                    (reference_id,),
                ).fetchone()
                if prior:
                    if f"payload_sha256={payload_hash}" not in (prior["note"] or ""):
                        raise HTTPException(status_code=409, detail="Quarantine release idempotency key was used with a different payload")
                    return {"return_id": return_id, "return_line_id": line_id, "released_quantity": prior["quantity"], "replayed": True}

                line = conn.execute(
                    "SELECT l.id,l.variant_id,l.disposition,l.disposition_location_id,l.disposition_posted_at,"
                    "r.status AS return_status FROM fulfilment_return_lines l "
                    "JOIN fulfilment_returns r ON r.id=l.return_id WHERE l.id=%s AND l.return_id=%s FOR UPDATE OF l,r",
                    (line_id, return_id),
                ).fetchone()
                if line is None:
                    raise HTTPException(status_code=404, detail="Return line not found")
                if line["return_status"] != "closed" or line["disposition"] != "quarantine" or line["disposition_posted_at"] is None:
                    raise HTTPException(status_code=409, detail="Only a closed, inspected return line already posted to quarantine can be released")
                source = conn.execute(
                    "SELECT id,establishment_id,is_active,is_fulfillable FROM stock_locations WHERE id=%s FOR UPDATE",
                    (line["disposition_location_id"],),
                ).fetchone()
                destination = conn.execute(
                    "SELECT id,establishment_id,is_active,is_fulfillable FROM stock_locations WHERE id=%s FOR UPDATE",
                    (payload.destination_location_id,),
                ).fetchone()
                if source is not None and getattr(request.state, "role", None) not in {"owner", "admin"}:
                    allowed_scope = conn.execute(
                        "SELECT 1 FROM hr_employees he JOIN hr_employee_statutory_profiles esp ON esp.employee_id=he.id "
                        "WHERE he.user_id=%s AND esp.establishment_id=%s LIMIT 1",
                        (actor_id, source["establishment_id"]),
                    ).fetchone()
                    if allowed_scope is None:
                        raise HTTPException(status_code=403, detail="You are not assigned to this legal establishment")
                if source is None or not source["is_active"] or source["is_fulfillable"]:
                    raise HTTPException(status_code=409, detail="Original return quarantine location must remain active and non-fulfillable")
                if destination is None or not destination["is_active"] or not destination["is_fulfillable"]:
                    raise HTTPException(status_code=409, detail="Release destination must be an active fulfilable stock location")
                if source["id"] == destination["id"] or source["establishment_id"] != destination["establishment_id"]:
                    raise HTTPException(status_code=409, detail="Return quarantine release must move to a different location in the same legal establishment")

                layers = conn.execute(
                    "SELECT cl.id,cl.variant_id,cl.location_id,cl.receipt_movement_id,cl.goods_receipt_line_id,"
                    "cl.batch_code,cl.manufacture_date,cl.expiry_date,cl.received_quantity,cl.remaining_quantity,cl.unit_cost,"
                    "(cl.expiry_date IS NULL OR cl.expiry_date>=CURRENT_DATE) AS is_releasable "
                    "FROM fulfilment_return_dispatch_allocations rda "
                    "JOIN inventory_cost_layers cl ON cl.receipt_movement_id=rda.inventory_movement_id "
                    "WHERE rda.return_line_id=%s AND rda.disposition='quarantine' AND cl.remaining_quantity>0 "
                    "ORDER BY cl.created_at,cl.id FOR UPDATE OF rda,cl",
                    (line_id,),
                ).fetchall()
                if not layers:
                    raise HTTPException(status_code=409, detail="No quarantined return cost-layer quantity remains to release")
                from app.services.inventory_quarantine import split_releasable_layers
                releasable, expired_quantity = split_releasable_layers(layers)
                if not releasable:
                    raise HTTPException(status_code=409, detail=f"All remaining return quarantine quantity is expired ({expired_quantity}); it cannot be released to saleable stock")
                if any(int(layer["variant_id"]) != int(line["variant_id"]) or int(layer["location_id"]) != int(source["id"]) for layer in releasable):
                    raise HTTPException(status_code=409, detail="Return quarantine cost-layer provenance does not match the recorded holding location")

                total_quantity = sum((Decimal(str(layer["remaining_quantity"])) for layer in releasable), Decimal("0"))
                source_balance = conn.execute(
                    "SELECT on_hand,reserved FROM inventory_balances WHERE variant_id=%s AND location_id=%s FOR UPDATE",
                    (line["variant_id"], source["id"]),
                ).fetchone()
                if source_balance is None or Decimal(str(source_balance["on_hand"])) - Decimal(str(source_balance["reserved"])) < total_quantity:
                    raise HTTPException(status_code=409, detail="Quarantine facility balance is lower than the remaining return cost-layer quantity")

                movement_out = conn.execute(
                    "INSERT INTO inventory_movements(variant_id,location_id,movement_type,quantity,reference_type,reference_id,note,created_by) "
                    "VALUES(%s,%s,'transfer_out',%s,'fulfilment_return_quarantine_release',%s,%s,%s) RETURNING id",
                    (line["variant_id"], source["id"], total_quantity, reference_id, note, actor_id),
                ).fetchone()
                movement_in = conn.execute(
                    "INSERT INTO inventory_movements(variant_id,location_id,movement_type,quantity,reference_type,reference_id,note,created_by) "
                    "VALUES(%s,%s,'transfer_in',%s,'fulfilment_return_quarantine_release',%s,%s,%s) RETURNING id",
                    (line["variant_id"], destination["id"], total_quantity, reference_id, note, actor_id),
                ).fetchone()
                conn.execute(
                    "UPDATE inventory_balances SET on_hand=on_hand-%s,updated_at=now() WHERE variant_id=%s AND location_id=%s",
                    (total_quantity, line["variant_id"], source["id"]),
                )
                conn.execute(
                    "INSERT INTO inventory_balances(variant_id,location_id,on_hand,reserved) VALUES(%s,%s,%s,0) "
                    "ON CONFLICT(variant_id,location_id) DO UPDATE SET on_hand=inventory_balances.on_hand+EXCLUDED.on_hand,updated_at=now()",
                    (line["variant_id"], destination["id"], total_quantity),
                )
                total_cost = Decimal("0.00")
                for layer in releasable:
                    quantity = Decimal(str(layer["remaining_quantity"]))
                    unit_cost = Decimal(str(layer["unit_cost"]))
                    cost = money(quantity * unit_cost)
                    conn.execute(
                        "UPDATE inventory_cost_layers SET remaining_quantity=remaining_quantity-%s WHERE id=%s",
                        (quantity, layer["id"]),
                    )
                    conn.execute(
                        "INSERT INTO inventory_cost_allocations(issue_movement_id,cost_layer_id,quantity,unit_cost,total_cost,allocation_method) "
                        "VALUES(%s,%s,%s,%s,%s,'fifo')",
                        (movement_out["id"], layer["id"], quantity, unit_cost, cost),
                    )
                    create_cost_layer(
                        conn, movement_id=movement_in["id"], variant_id=layer["variant_id"],
                        location_id=destination["id"], quantity=quantity, unit_cost=unit_cost,
                        goods_receipt_line_id=layer["goods_receipt_line_id"], batch_code=layer["batch_code"],
                        manufacture_date=layer["manufacture_date"], expiry_date=layer["expiry_date"],
                        source_layer_id=layer["id"],
                    )
                    total_cost += cost
                remaining = conn.execute(
                    "SELECT COALESCE(sum(cl.remaining_quantity),0) AS quantity "
                    "FROM fulfilment_return_dispatch_allocations rda JOIN inventory_cost_layers cl "
                    "ON cl.receipt_movement_id=rda.inventory_movement_id "
                    "WHERE rda.return_line_id=%s AND rda.disposition='quarantine'",
                    (line_id,),
                ).fetchone()["quantity"]
        return {"return_id": return_id, "return_line_id": line_id, "released_quantity": total_quantity,
                "remaining_quarantine_quantity": remaining, "expired_quantity_not_released": expired_quantity,
                "total_cost_transferred": total_cost, "replayed": False}
    except HTTPException:
        raise
    except psycopg.Error as exc:
        raise _db_error(exc) from exc
