"""Facility metadata and internal warehouse-location hierarchy.

Physical stock_locations remain the inventory, purchasing and fulfilment facility IDs.
Internal locations are a separate addressable layer and never participate in delivery PIN serviceability.
"""
from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel, Field, field_validator
import psycopg
from psycopg.rows import dict_row

from app.core.config import settings

router = APIRouter(prefix="/inventory", tags=["inventory-locations"])
LOCATION_TYPES = {"receiving", "storage", "rack", "shelf", "bin", "picking", "packing", "dispatch", "quarantine", "repair"}


def _connect():
    if not settings.database_url:
        raise HTTPException(503, "Inventory database is not configured")
    try:
        return psycopg.connect(settings.database_url, row_factory=dict_row, connect_timeout=3)
    except psycopg.Error as exc:
        raise HTTPException(503, "Inventory database is unavailable") from exc


def _require_inventory_admin(request: Request):
    role = getattr(request.state, "role", None)
    if role not in {"super_admin", "admin", "manager"}:
        raise HTTPException(403, "Inventory manager permission is required")


def validate_internal_location_parent(*, facility_id: int, parent: dict | None, location_id: int | None = None):
    if parent is None:
        return None
    if int(parent["facility_id"]) != int(facility_id):
        raise HTTPException(422, "Parent internal location must belong to the selected facility")
    if location_id is not None and int(parent["id"]) == int(location_id):
        raise HTTPException(422, "An internal location cannot be its own parent")
    return int(parent["id"])


class FacilityMetadataUpdate(BaseModel):
    address_line1: str | None = Field(default=None, max_length=200)
    address_line2: str | None = Field(default=None, max_length=200)
    city: str | None = Field(default=None, max_length=100)
    district: str | None = Field(default=None, max_length=100)
    state: str | None = Field(default=None, max_length=100)
    region_code: str | None = Field(default=None, max_length=32)

    @field_validator("address_line1", "address_line2", "city", "district", "state", "region_code")
    @classmethod
    def trim_values(cls, value):
        return value.strip() if value is not None else value


class InternalLocationCreate(BaseModel):
    facility_id: int = Field(gt=0)
    parent_id: int | None = Field(default=None, gt=0)
    code: str = Field(min_length=1, max_length=40)
    name: str = Field(min_length=1, max_length=120)
    location_type: str = Field(pattern=r"^(receiving|storage|rack|shelf|bin|picking|packing|dispatch|quarantine|repair)$")

    @field_validator("code", "name")
    @classmethod
    def trim_required(cls, value):
        value = value.strip()
        if not value:
            raise ValueError("Value cannot be blank")
        return value


class InternalLocationUpdate(BaseModel):
    parent_id: int | None = Field(default=None, gt=0)
    code: str = Field(min_length=1, max_length=40)
    name: str = Field(min_length=1, max_length=120)
    location_type: str = Field(pattern=r"^(receiving|storage|rack|shelf|bin|picking|packing|dispatch|quarantine|repair)$")
    is_active: bool = True

    @field_validator("code", "name")
    @classmethod
    def trim_required(cls, value):
        value = value.strip()
        if not value:
            raise ValueError("Value cannot be blank")
        return value


@router.patch("/locations/{facility_id}/metadata")
def update_facility_metadata(facility_id: int, payload: FacilityMetadataUpdate, request: Request):
    _require_inventory_admin(request)
    fields = payload.model_dump(exclude_unset=True)
    if not fields:
        raise HTTPException(422, "Provide at least one facility field to update")
    allowed = {"address_line1", "address_line2", "city", "district", "state", "region_code"}
    assignments = ", ".join(f"{key}=%s" for key in fields)
    try:
        with _connect() as conn:
            row = conn.execute(
                f"UPDATE stock_locations SET {assignments} WHERE id=%s AND is_active=TRUE "
                "RETURNING id,name,location_type,pin_code,address_line1,address_line2,city,district,state,region_code",
                (*fields.values(), facility_id),
            ).fetchone()
            if row is None:
                raise HTTPException(404, "Active facility not found")
        return row
    except HTTPException:
        raise
    except psycopg.Error as exc:
        raise HTTPException(503, "Facility metadata could not be saved; verify the inventory facility migration") from exc


@router.get("/internal-locations")
def list_internal_locations(
    facility_id: int = Query(gt=0),
    include_inactive: bool = False,
):
    try:
        with _connect() as conn:
            facility = conn.execute(
                "SELECT id,name,location_type,pin_code,is_active FROM stock_locations WHERE id=%s",
                (facility_id,),
            ).fetchone()
            if facility is None:
                raise HTTPException(404, "Facility not found")
            rows = conn.execute(
                "SELECT id,facility_id,parent_id,code,name,location_type,is_active,created_at,updated_at "
                "FROM stock_internal_locations WHERE facility_id=%s AND (%s OR is_active=TRUE) "
                "ORDER BY code,id",
                (facility_id, include_inactive),
            ).fetchall()
        return {"facility": facility, "items": rows}
    except HTTPException:
        raise
    except psycopg.Error as exc:
        raise HTTPException(503, "Internal locations are unavailable; verify the inventory facility migration") from exc


@router.post("/internal-locations", status_code=201)
def create_internal_location(payload: InternalLocationCreate, request: Request):
    _require_inventory_admin(request)
    try:
        with _connect() as conn:
            with conn.transaction():
                facility = conn.execute(
                    "SELECT id FROM stock_locations WHERE id=%s AND is_active=TRUE FOR SHARE",
                    (payload.facility_id,),
                ).fetchone()
                if facility is None:
                    raise HTTPException(404, "Active facility not found")
                parent = None
                if payload.parent_id is not None:
                    parent = conn.execute(
                        "SELECT id,facility_id FROM stock_internal_locations WHERE id=%s AND is_active=TRUE FOR SHARE",
                        (payload.parent_id,),
                    ).fetchone()
                parent_id = validate_internal_location_parent(facility_id=payload.facility_id, parent=parent)
                row = conn.execute(
                    "INSERT INTO stock_internal_locations(facility_id,parent_id,code,name,location_type) "
                    "VALUES(%s,%s,%s,%s,%s) RETURNING id,facility_id,parent_id,code,name,location_type,is_active,created_at",
                    (payload.facility_id,parent_id,payload.code,payload.name,payload.location_type),
                ).fetchone()
        return row
    except HTTPException:
        raise
    except psycopg.errors.UniqueViolation as exc:
        raise HTTPException(409, "An internal location with this code already exists in the facility") from exc
    except psycopg.errors.ForeignKeyViolation as exc:
        raise HTTPException(422, "Selected parent location is invalid") from exc
    except psycopg.Error as exc:
        raise HTTPException(503, "Internal location could not be created; verify the inventory facility migration") from exc


@router.put("/internal-locations/{location_id}")
def update_internal_location(location_id: int, payload: InternalLocationUpdate, request: Request):
    _require_inventory_admin(request)
    try:
        with _connect() as conn:
            with conn.transaction():
                current = conn.execute(
                    "SELECT id,facility_id,parent_id FROM stock_internal_locations WHERE id=%s FOR UPDATE",
                    (location_id,),
                ).fetchone()
                if current is None:
                    raise HTTPException(404, "Internal location not found")
                parent = None
                if payload.parent_id is not None:
                    parent = conn.execute(
                        "SELECT id,facility_id FROM stock_internal_locations WHERE id=%s AND is_active=TRUE FOR SHARE",
                        (payload.parent_id,),
                    ).fetchone()
                    if parent is None:
                        raise HTTPException(422, "Selected parent location is not active")
                parent_id = validate_internal_location_parent(
                    facility_id=current["facility_id"], parent=parent, location_id=location_id
                )
                if parent_id is not None:
                    cycle = conn.execute(
                        "WITH RECURSIVE descendants(id) AS ("
                        "SELECT id FROM stock_internal_locations WHERE parent_id=%s "
                        "UNION ALL SELECT child.id FROM stock_internal_locations child "
                        "JOIN descendants d ON child.parent_id=d.id) "
                        "SELECT EXISTS(SELECT 1 FROM descendants WHERE id=%s) AS creates_cycle",
                        (location_id, parent_id),
                    ).fetchone()["creates_cycle"]
                    if cycle:
                        raise HTTPException(422, "An internal location cannot be moved beneath one of its descendants")
                row = conn.execute(
                    "UPDATE stock_internal_locations SET parent_id=%s,code=%s,name=%s,location_type=%s,"
                    "is_active=%s,updated_at=now() WHERE id=%s "
                    "RETURNING id,facility_id,parent_id,code,name,location_type,is_active,updated_at",
                    (parent_id,payload.code,payload.name,payload.location_type,payload.is_active,location_id),
                ).fetchone()
        return row
    except HTTPException:
        raise
    except psycopg.errors.UniqueViolation as exc:
        raise HTTPException(409, "An internal location with this code already exists in the facility") from exc
    except psycopg.Error as exc:
        raise HTTPException(503, "Internal location could not be updated; verify the inventory facility migration") from exc
