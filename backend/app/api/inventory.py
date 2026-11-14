"""Inventory read and adjustment endpoints. Requires the reviewed v1 schema."""
from decimal import Decimal
import hashlib
import json
from uuid import UUID, uuid4
from typing import Any

import psycopg
from fastapi import APIRouter, HTTPException, Query, Request
from psycopg.rows import dict_row
from pydantic import BaseModel, Field, field_validator
from datetime import date

from app.services.inventory_costing import allocate_cost_layers, create_cost_layer, transfer_cost_layers, money
from app.services.inventory_overview import load_inventory_overview

from app.core.config import settings
from app.api.organisation_policies import load_active_policy
from app.services.organisation_policy import validate_inventory_policy, resolve_minimum_remaining_shelf_life_days

router = APIRouter(prefix="/inventory", tags=["inventory"])

def _physical_count_reference_type(variance: Decimal) -> str:
    """Preserve the direction of a count variance without changing the ledger schema."""
    return "physical_count_in" if variance > 0 else "physical_count_out"


def _stock_issue_reference_type(reason_type: str) -> str:
    """Identify stock reductions while retaining the existing movement type contract."""
    return "manual_scrap_out" if reason_type == "scrap" else "manual_issue_out"


def _normalise_payload(value):
    if isinstance(value, dict):
        return {str(k): _normalise_payload(v) for k, v in sorted(value.items())}
    if isinstance(value, list):
        return [_normalise_payload(v) for v in value]
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return str(Decimal(str(value)).normalize())
    if isinstance(value, str):
        try:
            numeric=Decimal(value)
            if numeric.is_finite() and value.strip() and all(ch in "0123456789+-.eE" for ch in value.strip()):
                return str(numeric.normalize())
        except Exception:
            pass
    return value


def _inventory_payload_hash(payload: dict) -> str:
    canonical = json.dumps(_normalise_payload(payload), sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _payload_value(payload, key, default=None):
    return payload.get(key,default) if isinstance(payload,dict) else getattr(payload,key,default)


def _inventory_approval_threshold_triggered(conn, event_type: str, payload, location_id: int, event_policy: dict) -> bool:
    if event_policy.get("approval_required") is True:
        return True
    thresholds = event_policy.get("approval_thresholds") or {}
    if not thresholds:
        return False
    quantity = Decimal("0")
    if event_type in {"opening_valuation", "opening_balance", "stock_gain", "issue", "scrap", "transfer"}:
        quantity = Decimal(str(_payload_value(payload, "quantity", 0)))
    elif event_type == "physical_count":
        current = conn.execute(
            "SELECT on_hand FROM inventory_balances WHERE variant_id=%s AND location_id=%s",
            (_payload_value(payload, "variant_id"), location_id),
        ).fetchone()
        quantity = abs(Decimal(str(_payload_value(payload, "counted_quantity", 0))) - Decimal(str(current["on_hand"] if current else 0)))
    if "quantity" in thresholds and quantity > Decimal(str(thresholds["quantity"])):
        return True
    if "value_inr" not in thresholds:
        return False
    if event_type in {"opening_valuation", "opening_balance", "stock_gain"}:
        exposure = quantity * Decimal(str(_payload_value(payload, "unit_cost", 0)))
    elif event_type == "physical_count" and Decimal(str(_payload_value(payload, "counted_quantity", 0))) >= Decimal(str(
        (conn.execute(
            "SELECT on_hand FROM inventory_balances WHERE variant_id=%s AND location_id=%s",
            (_payload_value(payload, "variant_id"), location_id),
        ).fetchone() or {"on_hand": 0})["on_hand"]
    )):
        exposure = quantity * Decimal(str(_payload_value(payload, "unit_cost", 0) or 0))
    else:
        variant_id = _payload_value(payload, "variant_id")
        max_cost = conn.execute(
            "SELECT COALESCE(MAX(unit_cost),0) AS max_unit_cost FROM inventory_cost_layers "
            "WHERE variant_id=%s AND location_id=%s AND remaining_quantity>0",
            (variant_id, location_id),
        ).fetchone()
        exposure = quantity * Decimal(str(max_cost["max_unit_cost"] if max_cost else 0))
    return exposure > Decimal(str(thresholds["value_inr"]))

def _require_inventory_event_policy(conn, location_id: int, event_type: str, payload=None, request=None):
    location = conn.execute(
        "SELECT establishment_id FROM stock_locations WHERE id=%s AND is_active=TRUE FOR SHARE",
        (location_id,),
    ).fetchone()
    if not location:
        raise HTTPException(status_code=404, detail="Active stock location not found")
    if location["establishment_id"] is None:
        raise HTTPException(status_code=409, detail="Assign this stock location to an active establishment before controlled inventory operations")
    policy = load_active_policy(conn, int(location["establishment_id"]), "inventory")
    try:
        validate_inventory_policy(policy["policy_config"])
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=f"Inventory policy configuration is invalid: {exc}") from exc
    event_policy = policy["policy_config"]["event_policies"].get(event_type)
    if not isinstance(event_policy, dict):
        raise HTTPException(status_code=409, detail=f"Configure the '{event_type}' event in the active Inventory policy")
    approval_required = _inventory_approval_threshold_triggered(conn, event_type, payload, location_id, event_policy)
    if approval_required:
        if payload is None or request is None:
            raise HTTPException(status_code=409, detail=f"'{event_type}' requires an approved inventory request")
        actor_id = getattr(request.state, "user_id", None)
        if not actor_id:
            raise HTTPException(status_code=401, detail="Authenticated staff session required")
        payload_data = payload.model_dump(mode="json")
        approved = conn.execute(
            "SELECT id,created_by_user_id FROM inventory_event_approval_requests "
            "WHERE establishment_id=%s AND policy_version_id=%s AND event_type=%s "
            "AND location_id=%s AND payload_hash=%s AND status='approved' "
            "ORDER BY created_at DESC,id DESC LIMIT 1 FOR UPDATE",
            (int(location["establishment_id"]),policy["id"],event_type,location_id,_inventory_payload_hash(payload_data)),
        ).fetchone()
        if not approved:
            raise HTTPException(status_code=409, detail=f"Submit '{event_type}' for approval and obtain every configured approval stage before posting")
        if int(approved["created_by_user_id"]) != int(actor_id):
            raise HTTPException(status_code=403, detail="Only the original requester may post the approved inventory request")
        conn.execute(
            "UPDATE inventory_event_approval_requests SET status='posted',posted_at=now(),updated_at=now() WHERE id=%s",
            (approved["id"],),
        )
    elif event_policy.get("approval_required") is not False:
        raise HTTPException(status_code=409, detail=f"Set approval_required explicitly for the '{event_type}' event")
    return policy, event_policy




class FacilityProfileCreate(BaseModel):
    facility_code: str = Field(min_length=2, max_length=40, pattern=r"^[A-Za-z0-9][A-Za-z0-9_-]*$")
    address_line1: str = Field(min_length=3, max_length=200)
    address_line2: str | None = Field(default=None, max_length=200)
    city: str = Field(min_length=2, max_length=100)
    district: str | None = Field(default=None, max_length=100)
    state: str = Field(min_length=2, max_length=100)
    country: str = Field(default="India", min_length=2, max_length=80)
    pin_code: str = Field(pattern=r"^[0-9]{6}$")
    manager_name: str | None = Field(default=None, max_length=120)
    contact_phone: str | None = Field(default=None, pattern=r"^[+0-9 ()-]{7,20}$")
    contact_email: str | None = Field(default=None, max_length=254)
    emergency_contact: str | None = Field(default=None, max_length=120)
    capacity: Decimal | None = Field(default=None, gt=0, max_digits=14, decimal_places=3)
    capacity_unit: str | None = Field(default=None, max_length=30)
    operating_days: list[str] = Field(default_factory=list)
    opening_time: str | None = Field(default=None, pattern=r"^(?:[01][0-9]|2[0-3]):[0-5][0-9]$")
    closing_time: str | None = Field(default=None, pattern=r"^(?:[01][0-9]|2[0-3]):[0-5][0-9]$")
    receives_stock: bool = True
    dispatches_stock: bool = True
    gstin: str | None = Field(default=None, pattern=r"^[0-9]{2}[A-Z]{5}[0-9]{4}[A-Z][1-9A-Z]Z[0-9A-Z]$")
    licence_reference: str | None = Field(default=None, max_length=100)

    @field_validator("facility_code")
    @classmethod
    def normalise_facility_code(cls, value: str) -> str:
        return value.strip().upper()

    @field_validator("address_line1", "city", "state", "country")
    @classmethod
    def required_profile_text(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("This field cannot be blank")
        return value

    @field_validator("operating_days")
    @classmethod
    def valid_operating_days(cls, value: list[str]) -> list[str]:
        allowed = {"mon", "tue", "wed", "thu", "fri", "sat", "sun"}
        normalised = [day.strip().lower()[:3] for day in value]
        if len(set(normalised)) != len(normalised) or any(day not in allowed for day in normalised):
            raise ValueError("Operating days must be unique weekdays")
        return normalised


class StockLocationCreate(BaseModel):
    name: str = Field(min_length=1, max_length=160)
    location_type: str = Field(pattern=r"^(warehouse|store|dark_store)$")
    pin_code: str | None = Field(default=None, pattern=r"^[0-9]{6}$")
    establishment_id: int | None = Field(default=None, gt=0)
    is_fulfillable: bool = True

    @field_validator("name")
    @classmethod
    def location_name_not_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("Location name cannot be blank")
        return value.strip()


class EstablishmentAssignment(BaseModel):
    establishment_id: int = Field(gt=0)


class StockAdjustment(BaseModel):
    variant_id: int = Field(gt=0)
    location_id: int = Field(gt=0)
    quantity: Decimal = Field(gt=0, max_digits=14, decimal_places=3)
    unit_cost: Decimal = Field(ge=0, max_digits=14, decimal_places=4)
    adjustment_type: str = Field(default="opening_valuation", pattern=r"^(opening_valuation|opening_balance|stock_gain)$")
    batch_code: str | None = Field(default=None, max_length=100)
    expiry_date: date | None = None
    note: str = Field(min_length=3, max_length=500)



class StockIssue(BaseModel):
    variant_id: int = Field(gt=0)
    location_id: int = Field(gt=0)
    quantity: Decimal = Field(gt=0, max_digits=14, decimal_places=3)
    note: str = Field(min_length=3, max_length=500)
    reason_type: str = Field(default="issue", pattern=r"^(issue|scrap)$")
    allocation_method: str = Field(default="fifo", pattern=r"^(fifo|fefo)$")


class StockCount(BaseModel):
    variant_id: int = Field(gt=0)
    location_id: int = Field(gt=0)
    counted_quantity: Decimal = Field(ge=0, max_digits=14, decimal_places=3)
    unit_cost: Decimal | None = Field(default=None, ge=0, max_digits=14, decimal_places=4)
    batch_code: str | None = Field(default=None, max_length=100)
    expiry_date: date | None = None
    allocation_method: str = Field(default="fifo", pattern=r"^(fifo|fefo)$")
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


class InventoryApprovalRequestCreate(BaseModel):
    event_type: str = Field(min_length=1, max_length=80)
    location_id: int = Field(gt=0)
    payload: dict[str, Any]


class InventoryApprovalDecision(BaseModel):
    decision: str = Field(pattern="^(approved|rejected)$")
    reason: str = Field(min_length=3, max_length=1000)

    @field_validator("reason")
    @classmethod
    def non_blank_reason(cls, value: str) -> str:
        value=value.strip()
        if len(value) < 3:
            raise ValueError("A decision reason of at least 3 non-blank characters is required")
        return value


def _inventory_actor(request: Request):
    actor_id = getattr(request.state, "user_id", None)
    email = getattr(request.state, "user_email", None)
    role = getattr(request.state, "role", None)
    if not actor_id or not email or not role:
        raise HTTPException(401, "Authenticated staff session required")
    return int(actor_id), str(email), str(role)


def _require_inventory_establishment_scope(conn, actor_id: int, actor_role: str, establishment_id: int | None):
    if actor_role in {"super_admin", "admin"}:
        return
    if establishment_id is None:
        raise HTTPException(403, "This stock location is not assigned to a legal establishment")
    allowed = conn.execute(
        "SELECT 1 FROM hr_employees he JOIN hr_employee_statutory_profiles esp ON esp.employee_id=he.id "
        "WHERE he.user_id=%s AND esp.establishment_id=%s LIMIT 1",
        (actor_id, establishment_id),
    ).fetchone()
    if allowed is None:
        raise HTTPException(403, "You are not assigned to this legal establishment")


@router.get("/approval-requests")
def list_inventory_approval_requests(request: Request, status: str | None = Query(default=None, pattern="^(pending|approved|rejected|posted)$")):
    actor_id,_,actor_role=_inventory_actor(request)
    try:
        with _connect() as conn:
            rows = conn.execute(
                "SELECT r.id,r.establishment_id,r.policy_version_id,r.event_type,r.location_id,l.name AS location_name,"
                "r.payload,r.created_by_user_id,r.created_by_email,r.created_by_role,r.status,r.created_at,r.updated_at,r.posted_at,p.policy_config "
                "FROM inventory_event_approval_requests r JOIN stock_locations l ON l.id=r.location_id "
                "JOIN organisation_policy_versions p ON p.id=r.policy_version_id "
                "WHERE (%s::text IS NULL OR r.status=%s::text) AND ("
                "%s IN ('super_admin','admin') OR r.created_by_user_id=%s OR ("
                "r.establishment_id IN (SELECT esp.establishment_id FROM hr_employees he "
                "JOIN hr_employee_statutory_profiles esp ON esp.employee_id=he.id WHERE he.user_id=%s) "
                "AND EXISTS (SELECT 1 FROM jsonb_array_elements("
                "p.policy_config->'event_policies'->r.event_type->'stages') st "
                "WHERE st->'approver_roles' ? %s))) "
                "ORDER BY r.created_at DESC,r.id DESC LIMIT 300",
                (status,status,actor_role,actor_id,actor_id,actor_role),
            ).fetchall()
            items=[]
            for row in rows:
                item=dict(row)
                decisions=conn.execute(
                    "SELECT stage_sequence,decision,actor_user_id,actor_email,actor_role,reason,created_at "
                    "FROM organisation_policy_decisions WHERE domain='inventory' "
                    "AND document_type='inventory_event_request' AND document_id=%s ORDER BY stage_sequence",
                    (row["id"],),
                ).fetchall()
                item["decisions"]=decisions
                event_policy=item["policy_config"].get("event_policies",{}).get(item["event_type"],{})
                stages=sorted(event_policy.get("stages",[]),key=lambda stage:int(stage["sequence"]))
                completed={int(d["stage_sequence"]) for d in decisions if d["decision"]=="approved"}
                next_stage=next((stage for stage in stages if int(stage["sequence"]) not in completed),None)
                is_member = actor_role in {"super_admin","admin"}
                if not is_member:
                    membership=conn.execute(
                        "SELECT EXISTS(SELECT 1 FROM hr_employees he "
                        "JOIN hr_employee_statutory_profiles esp ON esp.employee_id=he.id "
                        "WHERE he.user_id=%s AND esp.establishment_id=%s) AS allowed",
                        (actor_id,row["establishment_id"]),
                    ).fetchone()
                    is_member=bool(membership and membership["allowed"])
                item["can_decide"]=(
                    item["status"]=="pending"
                    and int(item["created_by_user_id"]) != actor_id
                    and is_member and next_stage is not None
                    and actor_role in next_stage["approver_roles"]
                )
                item.pop("policy_config",None)
                items.append(item)
        return {"items":items}
    except psycopg.Error as exc:
        raise _db_error(exc) from exc


@router.post("/approval-requests", status_code=201)
def create_inventory_approval_request(payload: InventoryApprovalRequestCreate, request: Request):
    actor_id,email,role=_inventory_actor(request)
    models = {
        "opening_valuation": StockAdjustment, "opening_balance": StockAdjustment,
        "stock_gain": StockAdjustment, "issue": StockIssue, "scrap": StockIssue,
        "transfer": StockTransfer, "physical_count": StockCount,
    }
    model = models.get(payload.event_type)
    if model is None:
        raise HTTPException(422,"Unsupported inventory approval event type")
    try:
        validated_payload = model.model_validate(payload.payload)
    except ValueError as exc:
        raise HTTPException(422,f"Inventory approval payload is invalid: {exc}") from exc
    payload_data = validated_payload.model_dump(mode="json")
    expected_location = (
        payload_data.get("source_location_id") if payload.event_type == "transfer"
        else payload_data.get("location_id")
    )
    if expected_location != payload.location_id:
        raise HTTPException(422,"Approval request location must match the operation's stock location")
    if payload.event_type in {"opening_valuation","opening_balance","stock_gain"} and payload_data.get("adjustment_type") != payload.event_type:
        raise HTTPException(422,"Adjustment event type does not match the submitted operation")
    if payload.event_type in {"issue","scrap"} and payload_data.get("reason_type") != payload.event_type:
        raise HTTPException(422,"Issue event type does not match the submitted operation")
    try:
        with _connect() as conn:
            with conn.transaction():
                location=conn.execute(
                    "SELECT id,establishment_id FROM stock_locations WHERE id=%s AND is_active=TRUE FOR SHARE",
                    (payload.location_id,),
                ).fetchone()
                if not location:
                    raise HTTPException(404,"Active stock location not found")
                if location["establishment_id"] is None:
                    raise HTTPException(409,"Assign the stock location to an active legal establishment first")
                if role not in {"super_admin","admin"}:
                    membership=conn.execute(
                        "SELECT EXISTS(SELECT 1 FROM hr_employees he "
                        "JOIN hr_employee_statutory_profiles esp ON esp.employee_id=he.id "
                        "WHERE he.user_id=%s AND esp.establishment_id=%s) AS allowed",
                        (actor_id,location["establishment_id"]),
                    ).fetchone()
                    if not membership or not membership["allowed"]:
                        raise HTTPException(403,"You are not assigned to this legal establishment")
                policy=load_active_policy(conn,int(location["establishment_id"]),"inventory")
                try:
                    validate_inventory_policy(policy["policy_config"])
                except ValueError as exc:
                    raise HTTPException(422,f"Inventory policy is invalid: {exc}") from exc
                event_policy=policy["policy_config"]["event_policies"].get(payload.event_type)
                if not isinstance(event_policy,dict):
                    raise HTTPException(409,"This event is not configured in the active Inventory policy")
                if not _inventory_approval_threshold_triggered(
                    conn,payload.event_type,validated_payload,payload.location_id,event_policy
                ):
                    raise HTTPException(409,"This operation does not meet the configured approval requirement")
                payload_hash=_inventory_payload_hash(payload_data)
                row=conn.execute(
                    "INSERT INTO inventory_event_approval_requests "
                    "(establishment_id,policy_version_id,event_type,location_id,payload,payload_hash,created_by_user_id,created_by_email,created_by_role) "
                    "VALUES(%s,%s,%s,%s,%s::jsonb,%s,%s,%s,%s) RETURNING id,status,created_at",
                    (int(location["establishment_id"]),policy["id"],payload.event_type,payload.location_id,
                     json.dumps(payload_data,default=str),payload_hash,actor_id,email,role),
                ).fetchone()
        return {**row,"message":"Inventory operation submitted for staged approval. No stock movement has been posted."}
    except HTTPException:
        raise
    except psycopg.Error as exc:
        raise _db_error(exc) from exc


@router.post("/approval-requests/{request_id}/decision")
def decide_inventory_approval_request(request_id: int, payload: InventoryApprovalDecision, request: Request):
    actor_id,email,role=_inventory_actor(request)
    try:
        with _connect() as conn:
            with conn.transaction():
                approval=conn.execute(
                    "SELECT * FROM inventory_event_approval_requests WHERE id=%s FOR UPDATE",
                    (request_id,),
                ).fetchone()
                if not approval:
                    raise HTTPException(404,"Inventory approval request not found")
                if approval["status"] != "pending":
                    raise HTTPException(409,"Only pending inventory approval requests can receive a decision")
                if int(approval["created_by_user_id"]) == actor_id:
                    raise HTTPException(403,"The requester cannot approve or reject their own inventory operation")
                policy=conn.execute(
                    "SELECT * FROM organisation_policy_versions WHERE id=%s AND domain='inventory' "
                    "AND establishment_id=%s FOR SHARE",
                    (approval["policy_version_id"],approval["establishment_id"]),
                ).fetchone()
                if not policy:
                    raise HTTPException(409,"The request's bound Inventory policy version is unavailable")
                if role not in {"super_admin","admin"}:
                    membership=conn.execute(
                        "SELECT EXISTS(SELECT 1 FROM hr_employees he "
                        "JOIN hr_employee_statutory_profiles esp ON esp.employee_id=he.id "
                        "WHERE he.user_id=%s AND esp.establishment_id=%s) AS allowed",
                        (actor_id,approval["establishment_id"]),
                    ).fetchone()
                    if not membership or not membership["allowed"]:
                        raise HTTPException(403,"You are not assigned to this legal establishment")
                event_policy=policy["policy_config"]["event_policies"].get(approval["event_type"],{})
                stages=sorted(event_policy.get("stages",[]),key=lambda item:int(item["sequence"]))
                completed=conn.execute(
                    "SELECT stage_sequence FROM organisation_policy_decisions WHERE domain='inventory' "
                    "AND document_type='inventory_event_request' AND document_id=%s AND decision='approved' "
                    "ORDER BY stage_sequence",
                    (request_id,),
                ).fetchall()
                completed_sequences={int(item["stage_sequence"]) for item in completed}
                next_stage=next((stage for stage in stages if int(stage["sequence"]) not in completed_sequences),None)
                if next_stage is None:
                    raise HTTPException(409,"All approval stages have already been completed")
                if role not in next_stage["approver_roles"]:
                    raise HTTPException(403,"Your role is not authorised for the next configured Inventory approval stage")
                evaluation={"event_type":approval["event_type"],"stages":stages,"payload_hash":approval["payload_hash"]}
                conn.execute(
                    "INSERT INTO organisation_policy_decisions "
                    "(policy_version_id,establishment_id,domain,document_type,document_id,document_revision,"
                    "stage_sequence,decision,actor_user_id,actor_email,actor_role,reason,evaluation_snapshot) "
                    "VALUES(%s,%s,'inventory','inventory_event_request',%s,1,%s,%s,%s,%s,%s,%s,%s::jsonb)",
                    (policy["id"],approval["establishment_id"],request_id,next_stage["sequence"],payload.decision,
                     actor_id,email,role,payload.reason.strip(),json.dumps(evaluation,default=str)),
                )
                if payload.decision == "rejected":
                    status="rejected"
                else:
                    status="approved" if {int(stage["sequence"]) for stage in stages}.issubset(completed_sequences | {int(next_stage["sequence"])}) else "pending"
                conn.execute(
                    "UPDATE inventory_event_approval_requests SET status=%s,updated_at=now() WHERE id=%s",
                    (status,request_id),
                )
        return {"id":request_id,"status":status,"decision":payload.decision,"stage_sequence":int(next_stage["sequence"])}
    except HTTPException:
        raise
    except psycopg.Error as exc:
        if getattr(exc,"sqlstate",None)=="23505":
            raise HTTPException(409,"This approval stage already has a recorded decision") from exc
        raise _db_error(exc) from exc


def _connect():
    if not settings.database_url:
        raise HTTPException(status_code=503, detail="Inventory database is not configured")
    try:
        return psycopg.connect(settings.database_url, row_factory=dict_row, connect_timeout=3)
    except psycopg.Error as exc:
        raise HTTPException(status_code=503, detail="Inventory database is unavailable") from exc



@router.get("/overview")
def inventory_overview(request: Request) -> dict[str, Any]:
    """Return full-dataset dashboard aggregates and actor-scoped approval counts."""
    actor_id, _, actor_role = _inventory_actor(request)
    try:
        with _connect() as conn:
            return load_inventory_overview(conn, actor_id=actor_id, actor_role=actor_role)
    except psycopg.Error as exc:
        raise _db_error(exc) from exc


def _post_inventory_journal(
    conn, request: Request, movement_id: int, amount: Decimal, narration: str,
    *, event_type: str, debit_role: str, credit_role: str,
) -> int | None:
    """Post a mapped journal atomically with the inventory movement."""
    from app.api import accounting
    from app.services.accounting_posting import (
        PostingConfigurationError, build_inventory_mapping_lines, resolve_legal_entity_code,
    )

    if amount <= 0:
        return None
    event_date = accounting._today()
    location = conn.execute(
        "SELECT he.code AS legal_entity_code FROM inventory_movements im "
        "JOIN stock_locations sl ON sl.id=im.location_id "
        "LEFT JOIN hr_establishments he ON he.id=sl.establishment_id WHERE im.id=%s",
        (movement_id,),
    ).fetchone()
    if location is None:
        raise HTTPException(404, "Inventory movement location was not found for Accounting scope")
    legal_entity_code = resolve_legal_entity_code(location.get("legal_entity_code"))
    mappings = conn.execute(
        "SELECT * FROM accounting_event_account_mappings WHERE legal_entity_code=%s "
        "AND source_module='inventory' AND event_type=%s AND status='approved' "
        "AND effective_from<=%s AND (effective_to IS NULL OR effective_to>=%s)",
        (legal_entity_code, event_type, event_date, event_date),
    ).fetchall()
    try:
        lines = build_inventory_mapping_lines(
            amount=amount, mappings=mappings, legal_entity_code=legal_entity_code,
            event_type=event_type, debit_role=debit_role, credit_role=credit_role,
            event_date=event_date, narration=narration,
        )
    except PostingConfigurationError as exc:
        raise HTTPException(409, f"Inventory journal blocked by Finance mapping: {exc}") from exc
    return accounting._post_voucher(
        conn,
        {
            "voucher_type": "journal", "voucher_date": event_date,
            "narration": narration, "reference": f"Inventory movement {movement_id}",
            "taxable_total": amount, "total_amount": amount,
            "source_type": "inventory_movement", "source_id": str(movement_id),
            "idempotency_key": f"inventory-movement:{movement_id}",
        },
        lines, (request.state.user_id, request.state.user_email),
    )


def _db_error(exc: psycopg.Error) -> HTTPException:
    code = getattr(exc, "sqlstate", None)
    if code == "23503":
        return HTTPException(status_code=422, detail="Variant or stock location does not exist")
    if code == "23505":
        return HTTPException(status_code=409, detail="An equivalent inventory approval request or movement already exists")
    if code == "23514":
        return HTTPException(status_code=422, detail="Stock adjustment violates an inventory constraint")
    return HTTPException(status_code=503, detail="Inventory database operation failed")


@router.post("/locations", status_code=201)
def create_location(payload: StockLocationCreate, request: Request, profile: FacilityProfileCreate | None = None):
    if (payload.establishment_id is not None or not payload.is_fulfillable) and getattr(request.state, "role", None) not in {"super_admin", "admin"}:
        raise HTTPException(status_code=403, detail="Only Super Admin/Admin can assign a stock location to a legal establishment")
    try:
        with _connect() as conn:
            with conn.transaction():
                if payload.establishment_id is not None:
                    establishment = conn.execute(
                        "SELECT id FROM hr_establishments WHERE id=%s AND is_active=TRUE FOR SHARE",
                        (payload.establishment_id,),
                    ).fetchone()
                    if establishment is None:
                        raise HTTPException(status_code=404, detail="Active legal establishment not found")
                row = conn.execute(
                    "INSERT INTO stock_locations (name, location_type, pin_code, establishment_id, is_fulfillable) VALUES (%s, %s, %s, %s, %s) "
                    "RETURNING id, name, location_type, pin_code, establishment_id, is_active, is_fulfillable, created_at",
                    (payload.name, payload.location_type, payload.pin_code, payload.establishment_id, payload.is_fulfillable),
                ).fetchone()
                if profile is not None:
                    conn.execute(
                        "INSERT INTO stock_location_profiles (location_id, facility_code, profile_data) VALUES (%s,%s,%s::jsonb)",
                        (row["id"], profile.facility_code, json.dumps(profile.model_dump(mode="json"), default=str)),
                    )
        return {**dict(row), "profile": profile.model_dump(mode="json") if profile else None,
                "profile_status": "complete" if profile else "incomplete"}
    except HTTPException:
        raise
    except psycopg.Error as exc:
        code = getattr(exc, "sqlstate", None)
        if code == "23505":
            if "facility_code" in str(exc).lower():
                raise HTTPException(status_code=409, detail="A facility with this code already exists") from exc
            raise HTTPException(status_code=409, detail="A stock location with this name already exists") from exc
        raise _db_error(exc) from exc





@router.put("/locations/{location_id}/establishment")
def assign_location_establishment(location_id: int, payload: EstablishmentAssignment, request: Request):
    if getattr(request.state, "role", None) not in {"super_admin", "admin"}:
        raise HTTPException(status_code=403, detail="Only Super Admin/Admin can assign a stock location to a legal establishment")
    try:
        with _connect() as conn:
            with conn.transaction():
                establishment = conn.execute(
                    "SELECT id FROM hr_establishments WHERE id=%s AND is_active=TRUE FOR SHARE",
                    (payload.establishment_id,),
                ).fetchone()
                if establishment is None:
                    raise HTTPException(status_code=404, detail="Active legal establishment not found")
                row = conn.execute(
                    "UPDATE stock_locations SET establishment_id=%s "
                    "WHERE id=%s AND is_active=TRUE "
                    "RETURNING id,name,location_type,pin_code,establishment_id,is_active,created_at",
                    (payload.establishment_id,location_id),
                ).fetchone()
                if row is None:
                    raise HTTPException(status_code=404, detail="Active stock location not found")
        return row
    except HTTPException:
        raise
    except psycopg.Error as exc:
        raise _db_error(exc) from exc

@router.get("/locations")
def list_locations(limit: int = Query(default=100, ge=1, le=500), offset: int = Query(default=0, ge=0)):
    try:
        with _connect() as conn:
            rows = conn.execute(
                "SELECT l.id, l.name, l.location_type, l.pin_code, l.address_line1, l.address_line2, "
                "l.city, l.district, l.state, l.region_code, l.establishment_id, "
                "e.display_name AS establishment_name, l.is_active, l.is_fulfillable, l.created_at, "
                "p.facility_code, p.profile_data, CASE WHEN p.location_id IS NULL THEN 'incomplete' ELSE 'complete' END AS profile_status "
                "FROM stock_locations l LEFT JOIN hr_establishments e ON e.id=l.establishment_id "
                "LEFT JOIN stock_location_profiles p ON p.location_id=l.id "
                "WHERE l.is_active = TRUE ORDER BY l.name LIMIT %s OFFSET %s",
                (limit, offset),
            ).fetchall()
        items = []
        for row in rows:
            item = dict(row)
            item["profile"] = item.pop("profile_data", None)
            items.append(item)
        return {"items": items, "limit": limit, "offset": offset}
    except psycopg.Error as exc:
        raise _db_error(exc) from exc


@router.get("/locations/{location_id}/profile")
def get_location_profile(location_id: int):
    try:
        with _connect() as conn:
            row = conn.execute(
                "SELECT l.id,l.name,l.location_type,l.pin_code,l.establishment_id,l.is_active,l.is_fulfillable,"
                "p.facility_code,p.profile_data FROM stock_locations l "
                "LEFT JOIN stock_location_profiles p ON p.location_id=l.id WHERE l.id=%s",
                (location_id,),
            ).fetchone()
        if row is None:
            raise HTTPException(404, "Stock location not found")
        result = dict(row)
        result["profile"] = result.pop("profile_data", None)
        result["profile_status"] = "complete" if result["facility_code"] else "incomplete"
        return result
    except HTTPException:
        raise
    except psycopg.Error as exc:
        raise _db_error(exc) from exc


@router.put("/locations/{location_id}/profile")
def update_location_profile(location_id: int, profile: FacilityProfileCreate, request: Request):
    if getattr(request.state, "role", None) not in {"super_admin", "admin"}:
        raise HTTPException(403, "Only Super Admin/Admin can edit facility profiles")
    try:
        with _connect() as conn:
            with conn.transaction():
                exists = conn.execute("SELECT id FROM stock_locations WHERE id=%s FOR UPDATE", (location_id,)).fetchone()
                if not exists:
                    raise HTTPException(404, "Stock location not found")
                row = conn.execute(
                    "INSERT INTO stock_location_profiles(location_id,facility_code,profile_data) VALUES(%s,%s,%s::jsonb) "
                    "ON CONFLICT(location_id) DO UPDATE SET facility_code=EXCLUDED.facility_code,profile_data=EXCLUDED.profile_data,updated_at=now() "
                    "RETURNING location_id,facility_code,profile_data,updated_at",
                    (location_id, profile.facility_code, json.dumps(profile.model_dump(mode="json"), default=str)),
                ).fetchone()
        return {**dict(row), "profile_status": "complete"}
    except HTTPException:
        raise
    except psycopg.Error as exc:
        if getattr(exc, "sqlstate", None) == "23505":
            raise HTTPException(409, "A facility with this code already exists") from exc
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




@router.get("/cost-layer-reconciliation")
def cost_layer_reconciliation(
    location_id: int | None = Query(default=None, gt=0),
    variant_id: int | None = Query(default=None, gt=0),
    limit: int = Query(default=500, ge=1, le=2000),
) -> dict[str, Any]:
    """Compare operational on-hand quantity with valued lots and expose legacy/unvalued stock."""
    clauses = []
    params: list[Any] = []
    if location_id is not None:
        clauses.append("ib.location_id=%s"); params.append(location_id)
    if variant_id is not None:
        clauses.append("ib.variant_id=%s"); params.append(variant_id)
    where = "WHERE " + " AND ".join(clauses) if clauses else ""
    params.append(limit)
    try:
        with _connect() as conn:
            rows = conn.execute(
                "SELECT ib.variant_id,pv.sku,ib.location_id,sl.name AS location_name,ib.on_hand,ib.reserved,"
                "COALESCE(sum(cl.remaining_quantity),0) AS valued_quantity,"
                "COALESCE(sum(cl.remaining_quantity*cl.unit_cost),0) AS valued_stock_amount,"
                "COALESCE(sum(cl.remaining_quantity) FILTER (WHERE cl.expiry_date<CURRENT_DATE),0) AS expired_quantity,"
                "COALESCE(sum(cl.remaining_quantity) FILTER (WHERE cl.expiry_date IS NULL OR cl.expiry_date>=CURRENT_DATE),0) AS eligible_quantity,"
                "(ib.on_hand-COALESCE(sum(cl.remaining_quantity),0)) AS unvalued_or_overvalued_quantity "
                "FROM inventory_balances ib JOIN product_variants pv ON pv.id=ib.variant_id "
                "JOIN stock_locations sl ON sl.id=ib.location_id "
                "LEFT JOIN inventory_cost_layers cl ON cl.variant_id=ib.variant_id AND cl.location_id=ib.location_id "
                f"{where} GROUP BY ib.variant_id,pv.sku,ib.location_id,sl.name,ib.on_hand,ib.reserved "
                "ORDER BY sl.name,pv.sku LIMIT %s",
                tuple(params),
            ).fetchall()
        return {"items": rows, "limit": limit,
                "mismatched_count": sum(1 for row in rows if row["unvalued_or_overvalued_quantity"] != 0)}
    except psycopg.Error as exc:
        raise _db_error(exc) from exc


class ExpiredStockQuarantineRequest(BaseModel):
    variant_id: int = Field(gt=0)
    source_location_id: int = Field(gt=0)
    quarantine_location_id: int = Field(gt=0)
    quantity: Decimal | None = Field(default=None, gt=0, max_digits=14, decimal_places=3)
    idempotency_key: UUID
    reason: str = Field(min_length=3, max_length=1000)

    @field_validator("reason")
    @classmethod
    def clean_reason(cls, value):
        value = value.strip()
        if len(value) < 3:
            raise ValueError("A quarantine reason of at least 3 characters is required")
        return value


@router.get("/expired-stock")
def list_expired_stock(request: Request, limit: int = Query(default=100, ge=1, le=500), offset: int = Query(default=0, ge=0)):
    actor_id, _, actor_role = _inventory_actor(request)
    try:
        with _connect() as conn:
            allowed_establishments = None
            if actor_role not in {"super_admin", "admin"}:
                allowed_establishments = [row["establishment_id"] for row in conn.execute(
                    "SELECT esp.establishment_id FROM hr_employees he "
                    "JOIN hr_employee_statutory_profiles esp ON esp.employee_id=he.id WHERE he.user_id=%s",
                    (actor_id,),
                ).fetchall()]
                if not allowed_establishments:
                    raise HTTPException(403, "No legal-establishment stock scope is assigned to this user")
            scope_sql = "" if allowed_establishments is None else " AND sl.establishment_id=ANY(%s)"
            scope_params = () if allowed_establishments is None else (allowed_establishments,)
            total = conn.execute(
                "SELECT count(*) AS total FROM (SELECT cl.variant_id,cl.location_id FROM inventory_cost_layers cl "
                "JOIN stock_locations sl ON sl.id=cl.location_id WHERE cl.remaining_quantity>0 "
                "AND cl.expiry_date<CURRENT_DATE AND sl.is_active=TRUE AND sl.is_fulfillable=TRUE" + scope_sql +
                " GROUP BY cl.variant_id,cl.location_id) q", scope_params,
            ).fetchone()["total"]
            rows = conn.execute(
                "SELECT cl.variant_id,v.sku,p.name AS product_name,cl.location_id,sl.name AS location_name,"
                "sum(cl.remaining_quantity) AS expired_quantity,sum(cl.remaining_quantity*cl.unit_cost) AS expired_value,"
                "min(cl.expiry_date) AS earliest_expiry,count(*) AS layer_count "
                "FROM inventory_cost_layers cl JOIN stock_locations sl ON sl.id=cl.location_id "
                "JOIN product_variants v ON v.id=cl.variant_id JOIN products p ON p.id=v.product_id "
                "WHERE cl.remaining_quantity>0 AND cl.expiry_date<CURRENT_DATE AND sl.is_active=TRUE "
                "AND sl.is_fulfillable=TRUE" + scope_sql + " GROUP BY cl.variant_id,v.sku,p.name,cl.location_id,sl.name "
                "ORDER BY earliest_expiry,cl.location_id,cl.variant_id LIMIT %s OFFSET %s",
                (*scope_params, limit, offset),
            ).fetchall()
        return {"items": rows, "total": total, "limit": limit, "offset": offset}
    except psycopg.Error as exc:
        raise _db_error(exc) from exc


@router.post("/quarantine-expired")
def quarantine_expired_stock(payload: ExpiredStockQuarantineRequest, request: Request):
    actor_id, _, actor_role = _inventory_actor(request)
    if actor_role not in {"super_admin", "admin", "manager"}:
        raise HTTPException(403, "Only Super Admin, Admin or manager may quarantine expired inventory")
    from app.services.inventory_quarantine import plan_quarantine_transfer

    reference_id = str(payload.idempotency_key)
    canonical = {"variant_id": payload.variant_id, "source_location_id": payload.source_location_id,
                 "quarantine_location_id": payload.quarantine_location_id,
                 "quantity": str(payload.quantity) if payload.quantity is not None else None, "reason": payload.reason}
    payload_hash = hashlib.sha256(json.dumps(canonical, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()
    note = f"Expired stock quarantine: {payload.reason} [payload_sha256={payload_hash}]"
    try:
        with _connect() as conn:
            with conn.transaction():
                conn.execute("SELECT pg_advisory_xact_lock(hashtextextended(%s,0))", (f"inventory-expired-quarantine:{reference_id}",))
                prior = conn.execute(
                    "SELECT id,quantity,note FROM inventory_movements WHERE reference_type='inventory_expired_quarantine' "
                    "AND reference_id=%s AND movement_type='transfer_out' ORDER BY id LIMIT 1", (reference_id,),
                ).fetchone()
                if prior:
                    if f"payload_sha256={payload_hash}" not in (prior["note"] or ""):
                        raise HTTPException(409, "Expired-stock quarantine idempotency key was used with a different payload")
                    return {"variant_id": payload.variant_id, "source_location_id": payload.source_location_id,
                            "quarantine_location_id": payload.quarantine_location_id,
                            "quarantined_quantity": prior["quantity"], "replayed": True}

                locations = conn.execute(
                    "SELECT id,establishment_id,is_active,is_fulfillable FROM stock_locations WHERE id=ANY(%s) ORDER BY id FOR UPDATE",
                    ([payload.source_location_id, payload.quarantine_location_id],),
                ).fetchall()
                by_location = {int(row["id"]): row for row in locations}
                source = by_location.get(payload.source_location_id)
                destination = by_location.get(payload.quarantine_location_id)
                if source is not None:
                    _require_inventory_establishment_scope(conn, actor_id, actor_role, source["establishment_id"])
                if source is None or not source["is_active"] or not source["is_fulfillable"]:
                    raise HTTPException(409, "Expired stock source must be an active fulfilable stock location")
                if destination is None or not destination["is_active"] or destination["is_fulfillable"]:
                    raise HTTPException(409, "Expired stock quarantine destination must be active and non-fulfillable")
                if source["id"] == destination["id"] or source["establishment_id"] != destination["establishment_id"]:
                    raise HTTPException(409, "Expired stock must remain within the same legal establishment")

                layers = conn.execute(
                    "SELECT id,variant_id,location_id,receipt_movement_id,goods_receipt_line_id,batch_code,manufacture_date,"
                    "expiry_date,remaining_quantity,unit_cost FROM inventory_cost_layers WHERE variant_id=%s AND location_id=%s "
                    "AND remaining_quantity>0 AND expiry_date<CURRENT_DATE ORDER BY expiry_date,created_at,id FOR UPDATE",
                    (payload.variant_id, payload.source_location_id),
                ).fetchall()
                try:
                    allocations = plan_quarantine_transfer(layers, payload.quantity)
                except ValueError as exc:
                    raise HTTPException(409, str(exc)) from exc
                layer_by_id = {int(layer["id"]): layer for layer in layers}
                total_quantity = sum((item["quantity"] for item in allocations), Decimal("0"))
                source_balance = conn.execute(
                    "SELECT on_hand,reserved FROM inventory_balances WHERE variant_id=%s AND location_id=%s FOR UPDATE",
                    (payload.variant_id, payload.source_location_id),
                ).fetchone()
                if source_balance is None or Decimal(str(source_balance["on_hand"])) - Decimal(str(source_balance["reserved"])) < total_quantity:
                    raise HTTPException(409, "Source balance is lower than the expired cost-layer quantity")

                movement_out = conn.execute(
                    "INSERT INTO inventory_movements(variant_id,location_id,movement_type,quantity,reference_type,reference_id,note,created_by) "
                    "VALUES(%s,%s,'transfer_out',%s,'inventory_expired_quarantine',%s,%s,%s) RETURNING id",
                    (payload.variant_id, payload.source_location_id, total_quantity, reference_id, note, actor_id),
                ).fetchone()
                movement_in = conn.execute(
                    "INSERT INTO inventory_movements(variant_id,location_id,movement_type,quantity,reference_type,reference_id,note,created_by) "
                    "VALUES(%s,%s,'transfer_in',%s,'inventory_expired_quarantine',%s,%s,%s) RETURNING id",
                    (payload.variant_id, payload.quarantine_location_id, total_quantity, reference_id, note, actor_id),
                ).fetchone()
                conn.execute("UPDATE inventory_balances SET on_hand=on_hand-%s,updated_at=now() WHERE variant_id=%s AND location_id=%s",
                             (total_quantity, payload.variant_id, payload.source_location_id))
                conn.execute(
                    "INSERT INTO inventory_balances(variant_id,location_id,on_hand,reserved) VALUES(%s,%s,%s,0) "
                    "ON CONFLICT(variant_id,location_id) DO UPDATE SET on_hand=inventory_balances.on_hand+EXCLUDED.on_hand,updated_at=now()",
                    (payload.variant_id, payload.quarantine_location_id, total_quantity),
                )
                total_cost = Decimal("0.00")
                for allocation in allocations:
                    layer = layer_by_id[allocation["layer_id"]]
                    quantity = allocation["quantity"]
                    unit_cost = Decimal(str(layer["unit_cost"]))
                    cost = money(quantity * unit_cost)
                    conn.execute("UPDATE inventory_cost_layers SET remaining_quantity=remaining_quantity-%s WHERE id=%s",
                                 (quantity, layer["id"]))
                    conn.execute(
                        "INSERT INTO inventory_cost_allocations(issue_movement_id,cost_layer_id,quantity,unit_cost,total_cost,allocation_method) "
                        "VALUES(%s,%s,%s,%s,%s,'fefo')",
                        (movement_out["id"], layer["id"], quantity, unit_cost, cost),
                    )
                    create_cost_layer(
                        conn, movement_id=movement_in["id"], variant_id=payload.variant_id,
                        location_id=payload.quarantine_location_id, quantity=quantity, unit_cost=unit_cost,
                        goods_receipt_line_id=layer["goods_receipt_line_id"], batch_code=layer["batch_code"],
                        manufacture_date=layer["manufacture_date"], expiry_date=layer["expiry_date"], source_layer_id=layer["id"],
                    )
                    total_cost += cost
                remaining = conn.execute(
                    "SELECT COALESCE(sum(remaining_quantity),0) AS quantity FROM inventory_cost_layers "
                    "WHERE variant_id=%s AND location_id=%s AND remaining_quantity>0 AND expiry_date<CURRENT_DATE",
                    (payload.variant_id, payload.source_location_id),
                ).fetchone()["quantity"]
        return {"variant_id": payload.variant_id, "source_location_id": payload.source_location_id,
                "quarantine_location_id": payload.quarantine_location_id, "quarantined_quantity": total_quantity,
                "remaining_expired_quantity": remaining, "total_cost_transferred": total_cost, "replayed": False}
    except HTTPException:
        raise
    except psycopg.Error as exc:
        raise _db_error(exc) from exc


@router.get("/cost-layers")
def list_cost_layers(
    variant_id: int | None = Query(default=None, gt=0),
    location_id: int | None = Query(default=None, gt=0),
    include_depleted: bool = False,
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
) -> dict[str, Any]:
    """Read the lot-level valuation trail used by FIFO/FEFO allocations."""
    clauses: list[str] = []
    params: list[Any] = []
    if variant_id is not None:
        clauses.append("cl.variant_id=%s")
        params.append(variant_id)
    if location_id is not None:
        clauses.append("cl.location_id=%s")
        params.append(location_id)
    if not include_depleted:
        clauses.append("cl.remaining_quantity>0")
    where = "WHERE " + " AND ".join(clauses) if clauses else ""
    params.extend([limit, offset])
    try:
        with _connect() as conn:
            rows = conn.execute(
                "SELECT cl.id,cl.variant_id,pv.sku,cl.location_id,sl.name AS location_name,"
                "cl.receipt_movement_id,cl.purchase_order_line_id,cl.source_layer_id,cl.batch_code,"
                "cl.manufacture_date,cl.expiry_date,cl.received_quantity,cl.remaining_quantity,cl.unit_cost,"
                "(cl.remaining_quantity*cl.unit_cost) AS remaining_value,cl.created_at "
                "FROM inventory_cost_layers cl JOIN product_variants pv ON pv.id=cl.variant_id "
                "JOIN stock_locations sl ON sl.id=cl.location_id "
                f"{where} ORDER BY cl.created_at,cl.id LIMIT %s OFFSET %s",
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
def create_adjustment(payload: StockAdjustment, request: Request) -> dict[str, Any]:
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
                "SELECT id,establishment_id FROM stock_locations WHERE id = %s AND is_active = TRUE FOR SHARE",
                (payload.location_id,),
            ).fetchone()
            if location is None:
                raise HTTPException(status_code=404, detail="Active stock location not found")
            _require_inventory_event_policy(conn, payload.location_id, payload.adjustment_type, payload, request)
            balance = conn.execute(
                "SELECT on_hand FROM inventory_balances WHERE variant_id=%s AND location_id=%s FOR UPDATE",
                (payload.variant_id,payload.location_id),
            ).fetchone()
            current_on_hand = balance["on_hand"] if balance else Decimal("0")
            if payload.adjustment_type == "opening_valuation":
                valued = conn.execute(
                    "SELECT COALESCE(sum(remaining_quantity),0) AS quantity FROM inventory_cost_layers "
                    "WHERE variant_id=%s AND location_id=%s",
                    (payload.variant_id,payload.location_id),
                ).fetchone()["quantity"]
                unvalued = current_on_hand - valued
                if payload.quantity > unvalued:
                    raise HTTPException(
                        status_code=409,
                        detail=f"Opening valuation quantity {payload.quantity} exceeds unvalued on-hand quantity {unvalued}",
                    )
            else:
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
                "VALUES (%s, %s, 'adjustment', %s, %s, %s) "
                "RETURNING id, variant_id, location_id, movement_type, quantity, reference_type, note, created_at",
                (payload.variant_id, payload.location_id, payload.quantity,
                 "opening_valuation" if payload.adjustment_type == "opening_valuation" else
                 ("opening_stock" if payload.adjustment_type == "opening_balance" else "stock_gain"),
                 payload.note.strip()),
            ).fetchone()
            layer = create_cost_layer(
                conn, movement_id=movement["id"], variant_id=payload.variant_id,
                location_id=payload.location_id, quantity=payload.quantity,
                unit_cost=payload.unit_cost, batch_code=payload.batch_code,
                expiry_date=payload.expiry_date,
            )
            credit_code = "3900" if payload.adjustment_type in {"opening_balance", "opening_valuation"} else "4310"
            _post_inventory_journal(
                conn, request, movement["id"], payload.quantity * payload.unit_cost,
                "Opening inventory valuation" if credit_code == "3900" else "Inventory count surplus",
                event_type="inventory_adjustment", debit_role="inventory_asset",
                credit_role="opening_balance_equity" if credit_code == "3900" else "inventory_gain_income",
            )
        return {**movement, "cost_layer": layer}
    except HTTPException:
        raise
    except psycopg.Error as exc:
        raise _db_error(exc) from exc



@router.post("/issues", status_code=201)
def issue_stock(payload: StockIssue, request: Request) -> dict[str, Any]:
    """Reduce on-hand stock only when unreserved available quantity is sufficient."""
    try:
        with _connect() as conn:
            variant = conn.execute(
                "SELECT id,product_id FROM product_variants WHERE id = %s AND is_active = TRUE FOR SHARE",
                (payload.variant_id,),
            ).fetchone()
            if variant is None:
                raise HTTPException(status_code=404, detail="Active product variant not found")
            location = conn.execute(
                "SELECT id,establishment_id FROM stock_locations WHERE id = %s AND is_active = TRUE FOR SHARE",
                (payload.location_id,),
            ).fetchone()
            if location is None:
                raise HTTPException(status_code=404, detail="Active stock location not found")
            event_type = "scrap" if payload.reason_type == "scrap" else "issue"
            policy, event_policy = _require_inventory_event_policy(conn, payload.location_id, event_type, payload, request)
            minimum_shelf_life_days = resolve_minimum_remaining_shelf_life_days(
                policy["policy_config"], location_id=payload.location_id, product_id=int(variant["product_id"]),
                category_id=(conn.execute("SELECT category_id FROM products WHERE id=%s", (variant["product_id"],)).fetchone() or {}).get("category_id")
            )
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
                "VALUES (%s, %s, 'adjustment', %s, %s, %s) "
                "RETURNING id, variant_id, location_id, movement_type, quantity, reference_type, note, created_at",
                (payload.variant_id, payload.location_id, payload.quantity, _stock_issue_reference_type(payload.reason_type), payload.note.strip()),
            ).fetchone()
            costing = allocate_cost_layers(
                conn, movement_id=movement["id"], variant_id=payload.variant_id,
                location_id=payload.location_id, quantity=payload.quantity,
                method=payload.allocation_method, allow_expired=payload.reason_type == "scrap",
                minimum_remaining_shelf_life_days=minimum_shelf_life_days,
            )
            debit_code = "5020" if payload.reason_type == "scrap" else "5030"
            _post_inventory_journal(
                conn, request, movement["id"], costing["total_cost"],
                "Inventory scrap/write-off" if debit_code == "5020" else "Internal stock consumption",
                event_type="inventory_issue",
                debit_role="inventory_scrap_expense" if debit_code == "5020" else "inventory_issue_expense",
                credit_role="inventory_asset",
            )
        return {**movement, "costing": costing}
    except HTTPException:
        raise
    except psycopg.Error as exc:
        raise _db_error(exc) from exc



@router.post("/transfers", status_code=201)
def transfer_stock(payload: StockTransfer, request: Request) -> dict[str, Any]:
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
                "SELECT id,establishment_id,is_fulfillable FROM stock_locations WHERE id = ANY(%s) AND is_active = TRUE ORDER BY id FOR SHARE",
                ([payload.source_location_id, payload.destination_location_id],),
            ).fetchall()
            if len(locations) != 2:
                raise HTTPException(status_code=404, detail="Both stock locations must exist and be active")
            location_by_id = {int(item["id"]): item for item in locations}
            source_establishment = location_by_id[payload.source_location_id]["establishment_id"]
            destination_establishment = location_by_id[payload.destination_location_id]["establishment_id"]
            if not location_by_id[payload.source_location_id]["is_fulfillable"] or not location_by_id[payload.destination_location_id]["is_fulfillable"]:
                raise HTTPException(status_code=409, detail="Quarantine and repair holding stock cannot be transferred through normal fulfilment")
            if source_establishment is None or destination_establishment is None or int(source_establishment) != int(destination_establishment):
                raise HTTPException(status_code=409, detail="Inventory transfers must remain within one assigned legal establishment")
            policy, event_policy = _require_inventory_event_policy(conn,payload.source_location_id,"transfer",payload,request)
            product = conn.execute(
                "SELECT p.id,p.category_id FROM product_variants v JOIN products p ON p.id=v.product_id WHERE v.id=%s",
                (payload.variant_id,),
            ).fetchone()
            if product is None:
                raise HTTPException(status_code=404, detail="Product for transfer variant was not found")
            minimum_shelf_life_days = resolve_minimum_remaining_shelf_life_days(
                policy["policy_config"],location_id=payload.source_location_id,
                product_id=int(product["id"]),
                category_id=int(product["category_id"]) if product["category_id"] is not None else None,
            )
            locked_balances = conn.execute(
                "SELECT location_id, on_hand, reserved FROM inventory_balances "
                "WHERE variant_id = %s AND location_id = ANY(%s) ORDER BY location_id FOR UPDATE",
                (payload.variant_id, [payload.source_location_id, payload.destination_location_id]),
            ).fetchall()
            source = next((row for row in locked_balances if row["location_id"] == payload.source_location_id), None)
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
            transfer_reference = uuid4().hex
            for location_id, movement_type in (
                (payload.source_location_id, "transfer_out"),
                (payload.destination_location_id, "transfer_in"),
            ):
                row = conn.execute(
                    "INSERT INTO inventory_movements "
                    "(variant_id, location_id, movement_type, quantity, reference_type, reference_id, note) "
                    "VALUES (%s, %s, %s, %s, 'stock_transfer', %s, %s) "
                    "RETURNING id, variant_id, location_id, movement_type, quantity, reference_type, reference_id, note, created_at",
                    (payload.variant_id, location_id, movement_type, payload.quantity, transfer_reference, payload.note.strip()),
                ).fetchone()
                movement_rows.append(row)
            transfer_cost_layers(
                conn, source_movement_id=movement_rows[0]["id"],
                destination_movement_id=movement_rows[1]["id"], variant_id=payload.variant_id,
                source_location_id=payload.source_location_id,
                destination_location_id=payload.destination_location_id, quantity=payload.quantity,
                minimum_remaining_shelf_life_days=minimum_shelf_life_days,
            )
        return {"items": movement_rows, "quantity": payload.quantity, "status": "transferred"}
    except HTTPException:
        raise
    except psycopg.Error as exc:
        raise _db_error(exc) from exc



@router.post("/counts", status_code=201)
def record_physical_count(payload: StockCount, request: Request) -> dict[str, Any]:
    """Reconcile a physical count while protecting reserved stock and recording the variance."""
    try:
        with _connect() as conn:
            variant = conn.execute(
                "SELECT id FROM product_variants WHERE id = %s AND is_active = TRUE FOR SHARE",
                (payload.variant_id,),
            ).fetchone()
            if variant is None:
                raise HTTPException(status_code=404, detail="Active product variant not found")
            location = conn.execute(
                "SELECT id,establishment_id FROM stock_locations WHERE id = %s AND is_active = TRUE FOR SHARE",
                (payload.location_id,),
            ).fetchone()
            if location is None:
                raise HTTPException(status_code=404, detail="Active stock location not found")
            _require_inventory_event_policy(conn, payload.location_id, "physical_count",payload,request)
            balance = conn.execute(
                "SELECT on_hand, reserved FROM inventory_balances "
                "WHERE variant_id = %s AND location_id = %s FOR UPDATE",
                (payload.variant_id, payload.location_id),
            ).fetchone()
            current = balance["on_hand"] if balance else Decimal("0")
            reserved = balance["reserved"] if balance else Decimal("0")
            if payload.counted_quantity < reserved:
                raise HTTPException(status_code=409, detail="Counted quantity cannot be lower than reserved stock")
            variance = payload.counted_quantity - current
            if variance > 0 and payload.unit_cost is None:
                raise HTTPException(status_code=422, detail="unit_cost is required when a physical count increases stock")
            movement = None
            costing = None
            if variance != 0:
                movement = conn.execute(
                    "INSERT INTO inventory_movements "
                    "(variant_id, location_id, movement_type, quantity, reference_type, note) "
                    "VALUES (%s, %s, 'adjustment', %s, %s, %s) "
                    "RETURNING id, variant_id, location_id, movement_type, quantity, reference_type, note, created_at",
                    (payload.variant_id, payload.location_id, abs(variance), _physical_count_reference_type(variance), payload.note.strip()),
                ).fetchone()
                if variance > 0:
                    create_cost_layer(
                        conn, movement_id=movement["id"], variant_id=payload.variant_id,
                        location_id=payload.location_id, quantity=variance, unit_cost=payload.unit_cost,
                        batch_code=payload.batch_code, expiry_date=payload.expiry_date,
                    )
                else:
                    costing = allocate_cost_layers(
                        conn, movement_id=movement["id"], variant_id=payload.variant_id,
                        location_id=payload.location_id, quantity=abs(variance),
                        method=payload.allocation_method, allow_expired=True,
                    )
                if variance > 0:
                    _post_inventory_journal(
                        conn, request, movement["id"], variance * payload.unit_cost,
                        "Physical count surplus", event_type="inventory_count",
                        debit_role="inventory_asset", credit_role="inventory_gain_income",
                    )
                else:
                    _post_inventory_journal(
                        conn, request, movement["id"], costing["total_cost"],
                        "Physical count stock shortage", event_type="inventory_count",
                        debit_role="stock_count_variance_expense", credit_role="inventory_asset",
                    )
            conn.execute(
                "INSERT INTO inventory_balances (variant_id, location_id, on_hand, reserved) "
                "VALUES (%s, %s, %s, 0) ON CONFLICT (variant_id, location_id) DO UPDATE "
                "SET on_hand = EXCLUDED.on_hand, updated_at = now()",
                (payload.variant_id, payload.location_id, payload.counted_quantity),
            )
        return {
            "status": "counted",
            "variant_id": payload.variant_id,
            "location_id": payload.location_id,
            "previous_quantity": current,
            "counted_quantity": payload.counted_quantity,
            "variance": variance,
            "movement": movement,
            "costing": costing,
        }
    except HTTPException:
        raise
    except psycopg.Error as exc:
        raise _db_error(exc) from exc
