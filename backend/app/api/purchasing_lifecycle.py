"""Purchasing requisition and approval lifecycle.

All writes are transactional and record the authenticated staff actor.
This router requires backend/schema/017_purchasing_lifecycle.sql.
"""
import hashlib
import json
from datetime import date
from decimal import Decimal
import uuid


import psycopg
from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel, Field, field_validator, model_validator

from app.api.purchasing import _connect, _db_error
from app.services.inventory_costing import money
from app.api.organisation_policies import load_active_policy
from app.services.organisation_policy import evaluate_purchase_policy, supplier_invoice_variance_within_tolerance

router = APIRouter(prefix="/purchasing", tags=["purchasing-lifecycle"])


class RequisitionLineInput(BaseModel):
    variant_id: int = Field(gt=0)
    quantity: Decimal = Field(gt=0, max_digits=14, decimal_places=3)
    estimated_unit_cost: Decimal | None = Field(default=None, ge=0, max_digits=14, decimal_places=2)
    specification: str | None = Field(default=None, max_length=2000)


class RequisitionCreate(BaseModel):
    location_id: int = Field(gt=0)
    department: str | None = Field(default=None, max_length=120)
    cost_centre: str | None = Field(default=None, max_length=120)
    required_by: date | None = None
    justification: str = Field(min_length=3, max_length=5000)
    lines: list[RequisitionLineInput] = Field(min_length=1, max_length=200)

    @field_validator("justification")
    @classmethod
    def valid_justification(cls, value):
        value = value.strip()
        if len(value) < 3:
            raise ValueError("Justification must contain at least 3 characters")
        return value

    @field_validator("lines")
    @classmethod
    def unique_variants(cls, lines):
        ids = [line.variant_id for line in lines]
        if len(ids) != len(set(ids)):
            raise ValueError("Each variant may appear once per requisition")
        return lines


class DecisionInput(BaseModel):
    reason: str | None = Field(default=None, max_length=2000)


def _validate_decision(decision: str, payload: DecisionInput):
    if decision not in {"approve", "reject"}:
        raise HTTPException(422, "Decision must be approve or reject")
    if decision == "reject" and not (payload.reason and payload.reason.strip()):
        raise HTTPException(422, "A reason is required when rejecting a requisition")


def _actor(request: Request):
    actor_id = getattr(request.state, "user_id", None)
    email = getattr(request.state, "user_email", None)
    role = getattr(request.state, "role", None)
    if not actor_id or not email or not role:
        raise HTTPException(401, "A valid staff session is required")
    return actor_id, email, role


def _purchase_policy_for_po(conn, purchase_order_id: int, bound_policy_id: int | None = None):
    po = conn.execute(
        "SELECT p.location_id,l.establishment_id,p.policy_version_id FROM purchase_orders p "
        "JOIN stock_locations l ON l.id=p.location_id WHERE p.id=%s FOR SHARE OF p,l",
        (purchase_order_id,),
    ).fetchone()
    if not po:
        raise HTTPException(404, "Related purchase order not found")
    if po["establishment_id"] is None:
        raise HTTPException(409, "Assign the purchase-order location to an active establishment before approval")
    policy_id = bound_policy_id or po["policy_version_id"]
    if policy_id is not None:
        policy = conn.execute(
            "SELECT * FROM organisation_policy_versions WHERE id=%s AND establishment_id=%s AND domain='purchase' FOR SHARE",
            (policy_id,po["establishment_id"]),
        ).fetchone()
        if policy is None:
            raise HTTPException(409, "The document's bound Purchase policy version is unavailable")
        return policy
    return load_active_policy(conn,int(po["establishment_id"]),"purchase")


def _record_purchase_approval_stage(
    conn, *, policy, document_type: str, document_id: int, revision: int,
    amount: Decimal, creator_user_id: int | None, actor_id: int,
    actor_email: str, actor_role: str, reason: str,
):
    if creator_user_id is None:
        raise HTTPException(409, "The document creator is not recorded; amend or recreate the draft to establish its approval owner")
    if int(creator_user_id) == int(actor_id):
        raise HTTPException(403, "The document creator cannot approve their own revision")
    evaluation = evaluate_purchase_policy(policy["policy_config"],Decimal(str(amount)))
    completed = conn.execute(
        "SELECT stage_sequence FROM organisation_policy_decisions WHERE domain='purchase' "
        "AND document_type=%s AND document_id=%s AND document_revision=%s AND decision='approved' "
        "ORDER BY stage_sequence",
        (document_type,document_id,revision),
    ).fetchall()
    completed_sequences = {int(item["stage_sequence"]) for item in completed}
    next_stage = next((stage for stage in evaluation["stages"] if int(stage["sequence"]) not in completed_sequences),None)
    if next_stage is None:
        raise HTTPException(409, "This document revision already has all required approvals")
    if actor_role not in next_stage["approver_roles"]:
        raise HTTPException(403, "Your role is not authorised for the next configured Purchase approval stage")
    conn.execute(
        "INSERT INTO organisation_policy_decisions "
        "(policy_version_id,establishment_id,domain,document_type,document_id,document_revision,"
        "stage_sequence,decision,actor_user_id,actor_email,actor_role,reason,evaluation_snapshot) "
        "VALUES(%s,%s,'purchase',%s,%s,%s,%s,'approved',%s,%s,%s,%s,%s::jsonb)",
        (policy["id"],policy["establishment_id"],document_type,document_id,revision,next_stage["sequence"],
         actor_id,actor_email,actor_role,reason,json.dumps(evaluation,default=str)),
    )
    conn.execute(
        "INSERT INTO purchasing_approval_events "
        "(document_type,document_id,action,actor_user_id,actor_email,actor_role,reason) "
        "VALUES(%s,%s,'approved',%s,%s,%s,%s)",
        (document_type,document_id,actor_id,actor_email,actor_role,reason),
    )
    complete = {int(stage["sequence"]) for stage in evaluation["stages"]}.issubset(
        completed_sequences | {int(next_stage["sequence"])}
    )
    return evaluation, next_stage, complete


@router.get("/requisitions")
def list_requisitions(
    status: str | None = None,
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
):
    allowed = {"draft", "submitted", "approved", "rejected", "cancelled", "partially_ordered", "ordered"}
    if status and status not in allowed:
        raise HTTPException(422, "Unsupported requisition status")
    try:
        with _connect() as conn:
            rows = conn.execute(
                "SELECT r.id,r.requisition_number,r.requester_email,r.department,r.cost_centre,"
                "r.location_id,sl.name AS location_name,r.required_by,r.justification,r.status,"
                "r.submitted_at,r.created_at,r.updated_at,"
                "(SELECT count(*) FROM purchase_requisition_lines l WHERE l.requisition_id=r.id) AS line_count "
                "FROM purchase_requisitions r JOIN stock_locations sl ON sl.id=r.location_id "
                + ("WHERE r.status=%s " if status else "")
                + "ORDER BY r.created_at DESC,r.id DESC LIMIT %s OFFSET %s",
                (status, limit, offset) if status else (limit, offset),
            ).fetchall()
            total = conn.execute(
                "SELECT count(*) AS total FROM purchase_requisitions" + (" WHERE status=%s" if status else ""),
                (status,) if status else (),
            ).fetchone()["total"]
        return {"items": rows, "total": total, "limit": limit, "offset": offset}
    except psycopg.Error as exc:
        raise _db_error(exc) from exc


@router.post("/requisitions", status_code=201)
def create_requisition(payload: RequisitionCreate, request: Request):
    actor_id, actor_email, _ = _actor(request)
    try:
        with _connect() as conn:
            with conn.transaction():
                location = conn.execute(
                    "SELECT id FROM stock_locations WHERE id=%s AND is_active=TRUE FOR SHARE",
                    (payload.location_id,),
                ).fetchone()
                if not location:
                    raise HTTPException(404, "Active stock location not found")
                ids = [line.variant_id for line in payload.lines]
                variants = conn.execute(
                    "SELECT id FROM product_variants WHERE id=ANY(%s) AND is_active=TRUE FOR SHARE",
                    (ids,),
                ).fetchall()
                if len(variants) != len(ids):
                    raise HTTPException(422, "One or more variants are missing or inactive")
                number = "PR-" + uuid.uuid4().hex[:12].upper()
                row = conn.execute(
                    "INSERT INTO purchase_requisitions(requisition_number,requester_user_id,requester_email,"
                    "department,cost_centre,location_id,required_by,justification) "
                    "VALUES(%s,%s,%s,%s,%s,%s,%s,%s) "
                    "RETURNING id,requisition_number,status,created_at",
                    (number, actor_id, actor_email, payload.department, payload.cost_centre,
                     payload.location_id, payload.required_by, payload.justification),
                ).fetchone()
                for line in payload.lines:
                    conn.execute(
                        "INSERT INTO purchase_requisition_lines(requisition_id,variant_id,quantity,estimated_unit_cost,specification) "
                        "VALUES(%s,%s,%s,%s,%s)",
                        (row["id"], line.variant_id, line.quantity, line.estimated_unit_cost, line.specification),
                    )
        return {**row, "requester_email": actor_email, "line_count": len(payload.lines)}
    except HTTPException:
        raise
    except psycopg.Error as exc:
        raise _db_error(exc) from exc


@router.get("/requisitions/{requisition_id}")
def get_requisition(requisition_id: int):
    try:
        with _connect() as conn:
            row = conn.execute(
                "SELECT r.id,r.requisition_number,r.requester_user_id,r.requester_email,r.department,"
                "r.cost_centre,r.location_id,sl.name AS location_name,r.required_by,r.justification,"
                "r.status,r.submitted_at,r.closed_at,r.created_at,r.updated_at "
                "FROM purchase_requisitions r JOIN stock_locations sl ON sl.id=r.location_id WHERE r.id=%s",
                (requisition_id,),
            ).fetchone()
            if not row:
                raise HTTPException(404, "Purchase requisition not found")
            lines = conn.execute(
                "SELECT l.id,l.variant_id,v.sku,p.name AS product_name,l.quantity,l.estimated_unit_cost,l.specification "
                "FROM purchase_requisition_lines l JOIN product_variants v ON v.id=l.variant_id "
                "JOIN products p ON p.id=v.product_id WHERE l.requisition_id=%s ORDER BY l.id",
                (requisition_id,),
            ).fetchall()
            events = conn.execute(
                "SELECT id,action,actor_email,actor_role,reason,created_at FROM purchasing_approval_events "
                "WHERE document_type='requisition' AND document_id=%s ORDER BY created_at,id",
                (requisition_id,),
            ).fetchall()
        return {**row, "lines": lines, "approval_events": events}
    except HTTPException:
        raise
    except psycopg.Error as exc:
        raise _db_error(exc) from exc


@router.post("/requisitions/{requisition_id}/submit")
def submit_requisition(requisition_id: int, request: Request):
    actor_id, actor_email, actor_role = _actor(request)
    try:
        with _connect() as conn:
            with conn.transaction():
                row = conn.execute(
                    "SELECT id,status,location_id,policy_version_id FROM purchase_requisitions WHERE id=%s FOR UPDATE",
                    (requisition_id,),
                ).fetchone()
                if not row:
                    raise HTTPException(404, "Purchase requisition not found")
                if row["status"] != "draft":
                    raise HTTPException(409, "Only draft requisitions can be submitted")
                location = conn.execute("SELECT establishment_id FROM stock_locations WHERE id=%s",(row["location_id"],)).fetchone()
                if not location or location["establishment_id"] is None:
                    raise HTTPException(409, "Assign the requisition location to an active establishment before submission")
                if row["policy_version_id"] is None:
                    policy = load_active_policy(conn,int(location["establishment_id"]),"purchase")
                    conn.execute("UPDATE purchase_requisitions SET policy_version_id=%s WHERE id=%s",(policy["id"],requisition_id))
                updated = conn.execute(
                    "UPDATE purchase_requisitions SET status='submitted',submitted_at=now(),updated_at=now() "
                    "WHERE id=%s RETURNING id,requisition_number,status,submitted_at",
                    (requisition_id,),
                ).fetchone()
                conn.execute(
                    "INSERT INTO purchasing_approval_events(document_type,document_id,action,actor_user_id,actor_email,actor_role) "
                    "VALUES('requisition',%s,'submitted',%s,%s,%s)",
                    (requisition_id, actor_id, actor_email, actor_role),
                )
        return updated
    except HTTPException:
        raise
    except psycopg.Error as exc:
        raise _db_error(exc) from exc


@router.post("/requisitions/{requisition_id}/decision")
def decide_requisition(
    requisition_id: int,
    decision: str,
    payload: DecisionInput,
    request: Request,
):
    actor_id, actor_email, actor_role = _actor(request)
    _validate_decision(decision, payload)
    try:
        with _connect() as conn:
            with conn.transaction():
                row = conn.execute(
                    "SELECT id,status,location_id,requester_user_id,approval_revision,policy_version_id "
                    "FROM purchase_requisitions WHERE id=%s FOR UPDATE",
                    (requisition_id,),
                ).fetchone()
                if not row:
                    raise HTTPException(404, "Purchase requisition not found")
                if row["status"] != "submitted":
                    raise HTTPException(409, "Only submitted requisitions can receive a decision")
                if decision == "approve":
                    amount = conn.execute(
                        "SELECT COALESCE(sum(quantity*estimated_unit_cost),0) AS amount "
                        "FROM purchase_requisition_lines WHERE requisition_id=%s",
                        (requisition_id,),
                    ).fetchone()["amount"]
                    location = conn.execute(
                        "SELECT establishment_id FROM stock_locations WHERE id=%s",
                        (row["location_id"],),
                    ).fetchone()
                    if not location or location["establishment_id"] is None:
                        raise HTTPException(409, "Assign the requisition location to an active establishment before approval")
                    if row["policy_version_id"] is not None:
                        policy = conn.execute(
                            "SELECT * FROM organisation_policy_versions WHERE id=%s AND establishment_id=%s AND domain='purchase' FOR SHARE",
                            (row["policy_version_id"],location["establishment_id"]),
                        ).fetchone()
                        if policy is None:
                            raise HTTPException(409, "The requisition's bound Purchase policy version is unavailable")
                    else:
                        policy = load_active_policy(conn,int(location["establishment_id"]),"purchase")
                    evaluation,next_stage,approval_complete = _record_purchase_approval_stage(
                        conn,policy=policy,document_type="requisition",document_id=requisition_id,
                        revision=int(row["approval_revision"]),amount=Decimal(str(amount)),
                        creator_user_id=row["requester_user_id"],actor_id=actor_id,
                        actor_email=actor_email,actor_role=actor_role,
                        reason=payload.reason.strip() if payload.reason else "Requisition approval",
                    )
                    conn.execute("UPDATE purchase_requisitions SET policy_version_id=%s WHERE id=%s",(policy["id"],requisition_id))
                    if not approval_complete:
                        return {"id":requisition_id,"status":"submitted","approval_pending":True,
                                "approved_stage":next_stage["sequence"],"required_stages":len(evaluation["stages"]),
                                "policy_version_id":policy["id"]}
                status = "approved" if decision == "approve" else "rejected"
                updated = conn.execute(
                    "UPDATE purchase_requisitions SET status=%s,closed_at=now(),updated_at=now() "
                    "WHERE id=%s RETURNING id,requisition_number,status,closed_at",
                    (status, requisition_id),
                ).fetchone()
                if decision == "reject":
                    conn.execute(
                        "INSERT INTO purchasing_approval_events(document_type,document_id,action,actor_user_id,actor_email,actor_role,reason) "
                        "VALUES('requisition',%s,%s,%s,%s,%s,%s)",
                        (requisition_id, status, actor_id, actor_email, actor_role,
                         payload.reason.strip() if payload.reason else None),
                    )
        return updated
    except HTTPException:
        raise
    except psycopg.Error as exc:
        raise _db_error(exc) from exc


from datetime import datetime


class RFQCreate(BaseModel):
    requisition_id: int = Field(gt=0)
    supplier_ids: list[int] = Field(min_length=1, max_length=100)
    response_due_at: datetime | None = None
    terms: str | None = Field(default=None, max_length=5000)

    @field_validator("supplier_ids")
    @classmethod
    def unique_suppliers(cls, values):
        if any(value <= 0 for value in values) or len(values) != len(set(values)):
            raise ValueError("Select unique valid suppliers")
        return values


class QuotationLineInput(BaseModel):
    variant_id: int = Field(gt=0)
    quantity: Decimal = Field(gt=0, max_digits=14, decimal_places=3)
    unit_price: Decimal = Field(ge=0, max_digits=14, decimal_places=2)
    hsn_sac: str | None = Field(default=None, max_length=8)
    gst_rate: Decimal | None = Field(default=None, ge=0, le=100, max_digits=5, decimal_places=2)


class QuotationCreate(BaseModel):
    rfq_id: int = Field(gt=0)
    supplier_id: int = Field(gt=0)
    quotation_number: str = Field(min_length=1, max_length=80)
    valid_until: date | None = None
    lead_time_days: int | None = Field(default=None, ge=0, le=3650)
    freight_amount: Decimal = Field(default=0, ge=0, max_digits=14, decimal_places=2)
    discount_amount: Decimal = Field(default=0, ge=0, max_digits=14, decimal_places=2)
    tax_amount: Decimal = Field(default=0, ge=0, max_digits=14, decimal_places=2)
    payment_terms: str | None = Field(default=None, max_length=2000)
    delivery_terms: str | None = Field(default=None, max_length=2000)
    lines: list[QuotationLineInput] = Field(min_length=1, max_length=200)

    @field_validator("quotation_number")
    @classmethod
    def valid_quotation_number(cls, value):
        value = value.strip()
        if not value:
            raise ValueError("Quotation number cannot be blank")
        return value

    @field_validator("lines")
    @classmethod
    def unique_quotation_variants(cls, lines):
        ids = [line.variant_id for line in lines]
        if len(ids) != len(set(ids)):
            raise ValueError("Each variant may appear once per quotation")
        return lines


@router.get("/rfqs")
def list_rfqs(
    status: str | None = None,
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
):
    allowed = {"draft", "issued", "evaluation", "awarded", "cancelled", "closed"}
    if status and status not in allowed:
        raise HTTPException(422, "Unsupported RFQ status")
    try:
        with _connect() as conn:
            rows = conn.execute(
                "SELECT r.id,r.rfq_number,r.requisition_id,r.status,r.issue_date,r.response_due_at,"
                "r.currency,r.terms,r.created_at,r.updated_at,"
                "(SELECT count(*) FROM purchase_rfq_suppliers s WHERE s.rfq_id=r.id) AS supplier_count,"
                "(SELECT count(*) FROM supplier_quotations q WHERE q.rfq_id=r.id) AS quotation_count "
                "FROM purchase_rfqs r "
                + ("WHERE r.status=%s " if status else "")
                + "ORDER BY r.created_at DESC,r.id DESC LIMIT %s OFFSET %s",
                (status, limit, offset) if status else (limit, offset),
            ).fetchall()
            total = conn.execute(
                "SELECT count(*) AS total FROM purchase_rfqs" + (" WHERE status=%s" if status else ""),
                (status,) if status else (),
            ).fetchone()["total"]
        return {"items": rows, "total": total, "limit": limit, "offset": offset}
    except HTTPException:
        raise
    except psycopg.Error as exc:
        raise _db_error(exc) from exc


@router.get("/rfqs/{rfq_id}")
def get_rfq(rfq_id: int):
    try:
        with _connect() as conn:
            row = conn.execute(
                "SELECT r.id,r.rfq_number,r.requisition_id,r.status,r.issue_date,r.response_due_at,"
                "r.currency,r.terms,r.created_by_user_id,r.created_by_email,r.created_at,r.updated_at "
                "FROM purchase_rfqs r WHERE r.id=%s",
                (rfq_id,),
            ).fetchone()
            if row is None:
                raise HTTPException(404, "RFQ not found")
            lines = conn.execute(
                "SELECT l.id,l.variant_id,v.sku,p.name AS product_name,l.quantity,l.specification "
                "FROM purchase_rfq_lines l JOIN product_variants v ON v.id=l.variant_id "
                "JOIN products p ON p.id=v.product_id WHERE l.rfq_id=%s ORDER BY l.id",
                (rfq_id,),
            ).fetchall()
            suppliers = conn.execute(
                "SELECT s.id AS supplier_id,s.name,s.email,s.phone,rs.response_status,rs.invited_at "
                "FROM purchase_rfq_suppliers rs JOIN suppliers s ON s.id=rs.supplier_id "
                "WHERE rs.rfq_id=%s ORDER BY s.name,s.id",
                (rfq_id,),
            ).fetchall()
            quotations = conn.execute(
                "SELECT q.id,q.quotation_number,q.supplier_id,s.name AS supplier_name,q.status,"
                "q.quoted_at,q.valid_until,q.lead_time_days,q.freight_amount,q.discount_amount,"
                "q.tax_amount,q.payment_terms,q.delivery_terms,q.evaluation_notes "
                "FROM supplier_quotations q JOIN suppliers s ON s.id=q.supplier_id "
                "WHERE q.rfq_id=%s ORDER BY q.quoted_at DESC,q.id DESC",
                (rfq_id,),
            ).fetchall()
            quotation_lines = conn.execute(
                "SELECT ql.quotation_id,ql.variant_id,v.sku,p.name AS product_name,ql.quantity,"
                "ql.unit_price,ql.hsn_sac,ql.gst_rate FROM supplier_quotation_lines ql "
                "JOIN product_variants v ON v.id=ql.variant_id JOIN products p ON p.id=v.product_id "
                "JOIN supplier_quotations q ON q.id=ql.quotation_id WHERE q.rfq_id=%s "
                "ORDER BY ql.quotation_id,ql.id",
                (rfq_id,),
            ).fetchall()
        line_map = {}
        for line in quotation_lines:
            line_map.setdefault(line["quotation_id"], []).append(line)
        return {
            **row,
            "lines": lines,
            "suppliers": suppliers,
            "quotations": [{**quotation, "lines": line_map.get(quotation["id"], [])} for quotation in quotations],
        }
    except HTTPException:
        raise
    except psycopg.Error as exc:
        raise _db_error(exc) from exc


@router.get("/quotations")
def list_supplier_quotations(
    rfq_id: int | None = Query(default=None, gt=0),
    supplier_id: int | None = Query(default=None, gt=0),
    status: str | None = None,
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
):
    allowed = {"received", "under_review", "selected", "rejected", "expired", "withdrawn"}
    if status and status not in allowed:
        raise HTTPException(422, "Unsupported supplier quotation status")
    clauses = []
    params = []
    if rfq_id is not None:
        clauses.append("q.rfq_id=%s")
        params.append(rfq_id)
    if supplier_id is not None:
        clauses.append("q.supplier_id=%s")
        params.append(supplier_id)
    if status:
        clauses.append("q.status=%s")
        params.append(status)
    where = " WHERE " + " AND ".join(clauses) if clauses else ""
    try:
        with _connect() as conn:
            rows = conn.execute(
                "SELECT q.id,q.quotation_number,q.rfq_id,r.rfq_number,q.supplier_id,s.name AS supplier_name,"
                "q.status,q.quoted_at,q.valid_until,q.lead_time_days,q.freight_amount,q.discount_amount,q.tax_amount "
                "FROM supplier_quotations q JOIN purchase_rfqs r ON r.id=q.rfq_id "
                "JOIN suppliers s ON s.id=q.supplier_id" + where +
                " ORDER BY q.quoted_at DESC,q.id DESC LIMIT %s OFFSET %s",
                (*params, limit, offset),
            ).fetchall()
            total = conn.execute(
                "SELECT count(*) AS total FROM supplier_quotations q" + where,
                tuple(params),
            ).fetchone()["total"]
        return {"items": rows, "total": total, "limit": limit, "offset": offset}
    except HTTPException:
        raise
    except psycopg.Error as exc:
        raise _db_error(exc) from exc


@router.post("/rfqs", status_code=201)
def create_rfq(payload: RFQCreate, request: Request):
    actor_id, actor_email, _ = _actor(request)
    try:
        with _connect() as conn:
            with conn.transaction():
                req = conn.execute(
                    "SELECT id,status FROM purchase_requisitions WHERE id=%s FOR UPDATE",
                    (payload.requisition_id,),
                ).fetchone()
                if not req:
                    raise HTTPException(404, "Purchase requisition not found")
                if req["status"] != "approved":
                    raise HTTPException(409, "Only approved requisitions can be sent for quotation")
                suppliers = conn.execute(
                    "SELECT id FROM suppliers WHERE id=ANY(%s) AND is_active=TRUE FOR SHARE",
                    (payload.supplier_ids,),
                ).fetchall()
                if len(suppliers) != len(payload.supplier_ids):
                    raise HTTPException(422, "One or more suppliers are missing or inactive")
                lines = conn.execute(
                    "SELECT variant_id,quantity,specification FROM purchase_requisition_lines WHERE requisition_id=%s ORDER BY id",
                    (payload.requisition_id,),
                ).fetchall()
                if not lines:
                    raise HTTPException(409, "Requisition has no lines")
                number = "RFQ-" + uuid.uuid4().hex[:12].upper()
                rfq = conn.execute(
                    "INSERT INTO purchase_rfqs(rfq_number,requisition_id,status,response_due_at,terms,created_by_user_id,created_by_email) "
                    "VALUES(%s,%s,'draft',%s,%s,%s,%s) RETURNING id,rfq_number,status,created_at",
                    (number, payload.requisition_id, payload.response_due_at, payload.terms, actor_id, actor_email),
                ).fetchone()
                for line in lines:
                    conn.execute(
                        "INSERT INTO purchase_rfq_lines(rfq_id,variant_id,quantity,specification) VALUES(%s,%s,%s,%s)",
                        (rfq["id"], line["variant_id"], line["quantity"], line["specification"]),
                    )
                for supplier_id in payload.supplier_ids:
                    conn.execute(
                        "INSERT INTO purchase_rfq_suppliers(rfq_id,supplier_id) VALUES(%s,%s)",
                        (rfq["id"], supplier_id),
                    )
        return {**rfq, "supplier_count": len(payload.supplier_ids), "line_count": len(lines)}
    except HTTPException:
        raise
    except psycopg.Error as exc:
        raise _db_error(exc) from exc


@router.post("/rfqs/{rfq_id}/issue")
def issue_rfq(rfq_id: int, request: Request):
    actor_id, actor_email, actor_role = _actor(request)
    try:
        with _connect() as conn:
            with conn.transaction():
                rfq = conn.execute("SELECT id,status FROM purchase_rfqs WHERE id=%s FOR UPDATE", (rfq_id,)).fetchone()
                if not rfq:
                    raise HTTPException(404, "RFQ not found")
                if rfq["status"] != "draft":
                    raise HTTPException(409, "Only draft RFQs can be issued")
                count = conn.execute("SELECT count(*) AS n FROM purchase_rfq_suppliers WHERE rfq_id=%s", (rfq_id,)).fetchone()["n"]
                if not count:
                    raise HTTPException(409, "An RFQ needs at least one invited supplier")
                row = conn.execute(
                    "UPDATE purchase_rfqs SET status='issued',issue_date=current_date,updated_at=now() WHERE id=%s RETURNING id,rfq_number,status,issue_date",
                    (rfq_id,),
                ).fetchone()
                conn.execute(
                    "INSERT INTO purchasing_approval_events(document_type,document_id,action,actor_user_id,actor_email,actor_role,reason) "
                    "VALUES('quotation',%s,'issued',%s,%s,%s,'RFQ issued to invited suppliers')",
                    (rfq_id, actor_id, actor_email, actor_role),
                )
        return row
    except HTTPException:
        raise
    except psycopg.Error as exc:
        raise _db_error(exc) from exc


@router.post("/quotations", status_code=201)
def create_supplier_quotation(payload: QuotationCreate, request: Request):
    actor_id, actor_email, _ = _actor(request)
    try:
        with _connect() as conn:
            with conn.transaction():
                rfq = conn.execute(
                    "SELECT id,status FROM purchase_rfqs WHERE id=%s FOR UPDATE",
                    (payload.rfq_id,),
                ).fetchone()
                if not rfq:
                    raise HTTPException(404, "RFQ not found")
                if rfq["status"] not in {"issued", "evaluation"}:
                    raise HTTPException(409, "Quotations can only be recorded for an issued RFQ")
                invited = conn.execute(
                    "SELECT id FROM purchase_rfq_suppliers WHERE rfq_id=%s AND supplier_id=%s FOR SHARE",
                    (payload.rfq_id, payload.supplier_id),
                ).fetchone()
                if not invited:
                    raise HTTPException(422, "Supplier was not invited to this RFQ")
                rfq_lines = conn.execute(
                    "SELECT variant_id,quantity FROM purchase_rfq_lines WHERE rfq_id=%s",
                    (payload.rfq_id,),
                ).fetchall()
                expected = {int(row["variant_id"]): row["quantity"] for row in rfq_lines}
                received = {line.variant_id: line for line in payload.lines}
                if set(received) != set(expected):
                    raise HTTPException(422, "Quotation must cover every RFQ line exactly once")
                for variant_id, line in received.items():
                    if line.quantity != expected[variant_id]:
                        raise HTTPException(422, "Quotation quantity must match the RFQ quantity")
                quotation = conn.execute(
                    "INSERT INTO supplier_quotations(quotation_number,rfq_id,supplier_id,status,valid_until,lead_time_days,freight_amount,discount_amount,tax_amount,payment_terms,delivery_terms,created_by_user_id) "
                    "VALUES(%s,%s,%s,'received',%s,%s,%s,%s,%s,%s,%s,%s) RETURNING id,quotation_number,status,quoted_at",
                    (payload.quotation_number, payload.rfq_id, payload.supplier_id, payload.valid_until,
                     payload.lead_time_days, payload.freight_amount, payload.discount_amount,
                     payload.tax_amount, payload.payment_terms, payload.delivery_terms, actor_id),
                ).fetchone()
                for line in payload.lines:
                    conn.execute(
                        "INSERT INTO supplier_quotation_lines(quotation_id,rfq_line_id,variant_id,quantity,unit_price,hsn_sac,gst_rate) "
                        "SELECT %s,id,%s,%s,%s,%s,%s FROM purchase_rfq_lines WHERE rfq_id=%s AND variant_id=%s",
                        (quotation["id"], line.variant_id, line.quantity, line.unit_price, line.hsn_sac,
                         line.gst_rate, payload.rfq_id, line.variant_id),
                    )
                conn.execute(
                    "UPDATE purchase_rfq_suppliers SET response_status='responded' WHERE rfq_id=%s AND supplier_id=%s",
                    (payload.rfq_id, payload.supplier_id),
                )
                conn.execute("UPDATE purchase_rfqs SET status='evaluation',updated_at=now() WHERE id=%s AND status='issued'", (payload.rfq_id,))
        return {**quotation, "line_count": len(payload.lines)}
    except HTTPException:
        raise
    except psycopg.Error as exc:
        raise _db_error(exc) from exc


from app.services.inventory_costing import create_cost_layer, money


class GRNLineInput(BaseModel):
    line_id: int = Field(gt=0)
    quantity: Decimal = Field(gt=0, max_digits=14, decimal_places=3)
    batch_code: str | None = Field(default=None, max_length=120)
    manufacture_date: date | None = None
    expiry_date: date | None = None

    @field_validator("batch_code")
    @classmethod
    def clean_batch(cls, value):
        if value is not None and not value.strip():
            raise ValueError("Batch code cannot be blank")
        return value.strip() if value else None


class GRNCreate(BaseModel):
    idempotency_key: uuid.UUID
    supplier_delivery_note: str | None = Field(default=None, max_length=120)
    note: str | None = Field(default=None, max_length=2000)
    lines: list[GRNLineInput] = Field(min_length=1, max_length=200)

    @field_validator("lines")
    @classmethod
    def unique_grn_lines(cls, lines):
        ids = [line.line_id for line in lines]
        if len(ids) != len(set(ids)):
            raise ValueError("Each purchase order line may appear once per GRN")
        return lines


class QCLineInput(BaseModel):
    goods_receipt_line_id: int = Field(gt=0)
    disposition: str = Field(pattern=r"^(accepted|rejected|damaged|quarantined)$")
    quantity: Decimal = Field(gt=0, max_digits=14, decimal_places=3)
    reason: str | None = Field(default=None, max_length=1000)


class QCSubmit(BaseModel):
    idempotency_key: uuid.UUID
    lines: list[QCLineInput] = Field(min_length=1, max_length=200)

    @field_validator("lines")
    @classmethod
    def unique_qc_lines(cls, lines):
        ids = [line.goods_receipt_line_id for line in lines]
        if len(ids) != len(set(ids)):
            raise ValueError("Each GRN line may appear once per QC submission")
        return lines


def _payload_hash(value: dict) -> str:
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


@router.post("/orders/{purchase_id}/grns", status_code=201)
def create_goods_receipt(purchase_id: int, payload: GRNCreate, request: Request):
    actor_id, actor_email, _ = _actor(request)
    canonical = {
        "supplier_delivery_note": payload.supplier_delivery_note,
        "note": payload.note,
        "lines": [
            {"line_id": line.line_id, "quantity": str(line.quantity), "batch_code": line.batch_code,
             "manufacture_date": str(line.manufacture_date) if line.manufacture_date else None,
             "expiry_date": str(line.expiry_date) if line.expiry_date else None}
            for line in sorted(payload.lines, key=lambda item: item.line_id)
        ],
    }
    digest = _payload_hash(canonical)
    try:
        with _connect() as conn:
            with conn.transaction():
                po = conn.execute(
                    "SELECT id,supplier_id,location_id,status FROM purchase_orders WHERE id=%s FOR UPDATE",
                    (purchase_id,),
                ).fetchone()
                if not po:
                    raise HTTPException(404, "Purchase order not found")
                existing = conn.execute(
                    "SELECT id,grn_number,payload_hash,status,received_at FROM goods_receipts "
                    "WHERE purchase_order_id=%s AND idempotency_key=%s",
                    (purchase_id, payload.idempotency_key),
                ).fetchone()
                if existing:
                    if existing["payload_hash"] != digest:
                        raise HTTPException(409, "GRN idempotency key was already used with a different payload")
                    return {**existing, "replayed": True}
                if po["status"] not in {"ordered", "partially_received"}:
                    raise HTTPException(409, "Only ordered or partially received purchase orders can receive a GRN")
                ids = [line.line_id for line in payload.lines]
                po_lines = conn.execute(
                    "SELECT id,variant_id,quantity_ordered,quantity_received,unit_cost "
                    "FROM purchase_order_lines WHERE purchase_order_id=%s AND id=ANY(%s) FOR UPDATE",
                    (purchase_id, ids),
                ).fetchall()
                by_id = {int(row["id"]): row for row in po_lines}
                if len(by_id) != len(ids):
                    raise HTTPException(422, "A GRN line does not belong to this purchase order")
                for line in payload.lines:
                    row = by_id[line.line_id]
                    if line.quantity > row["quantity_ordered"] - row["quantity_received"]:
                        raise HTTPException(409, "GRN quantity exceeds the outstanding purchase quantity")
                    if line.manufacture_date and line.expiry_date and line.expiry_date < line.manufacture_date:
                        raise HTTPException(422, "Expiry date cannot precede manufacture date")
                number = "GRN-" + uuid.uuid4().hex[:12].upper()
                grn = conn.execute(
                    "INSERT INTO goods_receipts(grn_number,purchase_order_id,supplier_id,location_id,idempotency_key,payload_hash,supplier_delivery_note,received_by_user_id,received_by_email,note,status) "
                    "VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,'qc_pending') "
                    "RETURNING id,grn_number,payload_hash,status,received_at",
                    (number,purchase_id,po["supplier_id"],po["location_id"],payload.idempotency_key,
                     digest,payload.supplier_delivery_note,actor_id,actor_email,payload.note),
                ).fetchone()
                for line in payload.lines:
                    row = by_id[line.line_id]
                    conn.execute(
                        "INSERT INTO goods_receipt_lines(goods_receipt_id,purchase_order_line_id,variant_id,received_quantity,batch_code,manufacture_date,expiry_date,unit_cost) "
                        "VALUES(%s,%s,%s,%s,%s,%s,%s,%s)",
                        (grn["id"],line.line_id,row["variant_id"],line.quantity,line.batch_code,
                         line.manufacture_date,line.expiry_date,row["unit_cost"]),
                    )
                    conn.execute(
                        "UPDATE purchase_order_lines SET quantity_received=quantity_received+%s WHERE id=%s",
                        (line.quantity,line.line_id),
                    )
                open_lines = conn.execute(
                    "SELECT count(*) AS n FROM purchase_order_lines WHERE purchase_order_id=%s AND quantity_received<quantity_ordered",
                    (purchase_id,),
                ).fetchone()["n"]
                po_status = "received" if open_lines == 0 else "partially_received"
                conn.execute("UPDATE purchase_orders SET status=%s,updated_at=now() WHERE id=%s", (po_status,purchase_id))
        return {**grn, "replayed": False, "line_count": len(payload.lines)}
    except HTTPException:
        raise
    except psycopg.Error as exc:
        raise _db_error(exc) from exc


@router.get("/grns")
def list_goods_receipts(
    purchase_order_id: int | None = Query(default=None, gt=0),
    quarantined_only: bool = False,
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
):
    try:
        clauses = []
        params = []
        if purchase_order_id is not None:
            clauses.append("g.purchase_order_id=%s")
            params.append(purchase_order_id)
        if quarantined_only:
            clauses.append("EXISTS (SELECT 1 FROM goods_receipt_lines ql WHERE ql.goods_receipt_id=g.id AND ql.quarantined_quantity>0)")
        where = " WHERE " + " AND ".join(clauses) if clauses else ""
        with _connect() as conn:
            rows = conn.execute(
                "SELECT g.id,g.grn_number,g.purchase_order_id,po.purchase_number,s.name AS supplier_name,"
                "g.location_id,g.status,g.received_at,g.supplier_delivery_note,"
                "(SELECT count(*) FROM goods_receipt_lines l WHERE l.goods_receipt_id=g.id) AS line_count,"
                "(SELECT COALESCE(sum(l.quarantined_quantity),0) FROM goods_receipt_lines l WHERE l.goods_receipt_id=g.id) AS quarantined_quantity "
                "FROM goods_receipts g JOIN purchase_orders po ON po.id=g.purchase_order_id "
                "JOIN suppliers s ON s.id=g.supplier_id" + where +
                " ORDER BY g.received_at DESC,g.id DESC LIMIT %s OFFSET %s",
                (*params,limit,offset),
            ).fetchall()
        return {"items": rows, "limit": limit, "offset": offset}
    except psycopg.Error as exc:
        raise _db_error(exc) from exc


@router.get("/grns/{grn_id}")
def get_goods_receipt(grn_id: int):
    try:
        with _connect() as conn:
            grn = conn.execute(
                "SELECT id,grn_number,purchase_order_id,supplier_id,location_id,status,received_at,note,supplier_delivery_note "
                "FROM goods_receipts WHERE id=%s",
                (grn_id,),
            ).fetchone()
            if not grn:
                raise HTTPException(404, "Goods receipt not found")
            lines = conn.execute(
                "SELECT l.id,l.purchase_order_line_id,l.variant_id,v.sku,p.name AS product_name,"
                "l.received_quantity,l.accepted_quantity,l.rejected_quantity,l.damaged_quantity,l.quarantined_quantity,"
                "l.batch_code,l.manufacture_date,l.expiry_date,l.unit_cost "
                "FROM goods_receipt_lines l JOIN product_variants v ON v.id=l.variant_id "
                "JOIN products p ON p.id=v.product_id WHERE l.goods_receipt_id=%s ORDER BY l.id",
                (grn_id,),
            ).fetchall()
            events = conn.execute(
                "SELECT e.id,e.goods_receipt_line_id,e.disposition,e.quantity,e.reason,e.actor_email,e.created_at "
                "FROM goods_receipt_qc_events e JOIN goods_receipt_lines l ON l.id=e.goods_receipt_line_id "
                "WHERE l.goods_receipt_id=%s ORDER BY e.created_at,e.id",
                (grn_id,),
            ).fetchall()
        return {**grn, "lines": lines, "qc_events": events}
    except HTTPException:
        raise
    except psycopg.Error as exc:
        raise _db_error(exc) from exc


@router.post("/grns/{grn_id}/qc")
def submit_goods_receipt_qc(grn_id: int, payload: QCSubmit, request: Request):
    actor_id, actor_email, actor_role = _actor(request)
    canonical = {
        "lines": [
            {"goods_receipt_line_id": line.goods_receipt_line_id,"disposition": line.disposition,
             "quantity": str(line.quantity),"reason": line.reason}
            for line in sorted(payload.lines, key=lambda item: item.goods_receipt_line_id)
        ]
    }
    digest = _payload_hash(canonical)
    try:
        with _connect() as conn:
            with conn.transaction():
                grn = conn.execute(
                    "SELECT id,purchase_order_id,location_id,status FROM goods_receipts WHERE id=%s FOR UPDATE",
                    (grn_id,),
                ).fetchone()
                if not grn:
                    raise HTTPException(404, "Goods receipt not found")
                if actor_role not in {"owner", "admin"}:
                    establishment = conn.execute(
                        "SELECT establishment_id FROM stock_locations WHERE id=%s",
                        (grn["location_id"],),
                    ).fetchone()
                    allowed_scope = conn.execute(
                        "SELECT 1 FROM hr_employees he JOIN hr_employee_statutory_profiles esp ON esp.employee_id=he.id "
                        "WHERE he.user_id=%s AND esp.establishment_id=%s LIMIT 1",
                        (actor_id, establishment["establishment_id"] if establishment else None),
                    ).fetchone()
                    if allowed_scope is None:
                        raise HTTPException(403, "You are not assigned to this legal establishment")
                prior = conn.execute(
                    "SELECT idempotency_key,payload_hash,goods_receipt_line_id FROM goods_receipt_qc_events "
                    "WHERE idempotency_key=%s ORDER BY goods_receipt_line_id",
                    (payload.idempotency_key,),
                ).fetchall()
                if prior:
                    if any(row["payload_hash"] != digest for row in prior):
                        raise HTTPException(409, "QC idempotency key was already used with a different payload")
                    if len(prior) != len(payload.lines):
                        raise HTTPException(409, "QC idempotency key was already used for a different set of lines")
                    return {"goods_receipt_id": grn_id, "replayed": True, "event_count": len(prior)}
                if grn["status"] in {"accepted", "rejected", "cancelled"}:
                    raise HTTPException(409, "This goods receipt has already completed QC")
                ids = [line.goods_receipt_line_id for line in payload.lines]
                rows = conn.execute(
                    "SELECT id,variant_id,purchase_order_line_id,received_quantity,accepted_quantity,rejected_quantity,"
                    "damaged_quantity,quarantined_quantity,batch_code,manufacture_date,expiry_date,unit_cost "
                    "FROM goods_receipt_lines WHERE goods_receipt_id=%s AND id=ANY(%s) FOR UPDATE",
                    (grn_id,ids),
                ).fetchall()
                by_id = {int(row["id"]): row for row in rows}
                if len(by_id) != len(ids):
                    raise HTTPException(422, "A QC line does not belong to this goods receipt")
                for line in payload.lines:
                    row = by_id[line.goods_receipt_line_id]
                    processed = row["accepted_quantity"]+row["rejected_quantity"]+row["damaged_quantity"]+row["quarantined_quantity"]
                    if processed + line.quantity > row["received_quantity"]:
                        raise HTTPException(409, "QC quantity exceeds the uninspected GRN quantity")
                for line in payload.lines:
                    row = by_id[line.goods_receipt_line_id]
                    column = {
                        "accepted": "accepted_quantity",
                        "rejected": "rejected_quantity",
                        "damaged": "damaged_quantity",
                        "quarantined": "quarantined_quantity",
                    }[line.disposition]
                    conn.execute(
                        f"UPDATE goods_receipt_lines SET {column}={column}+%s WHERE id=%s",
                        (line.quantity,line.goods_receipt_line_id),
                    )
                    qc_event = conn.execute(
                        "INSERT INTO goods_receipt_qc_events(goods_receipt_line_id,disposition,quantity,reason,actor_user_id,actor_email,idempotency_key,payload_hash) "
                        "VALUES(%s,%s,%s,%s,%s,%s,%s,%s) RETURNING id",
                        (line.goods_receipt_line_id,line.disposition,line.quantity,line.reason,actor_id,actor_email,
                         payload.idempotency_key,digest),
                    ).fetchone()
                    if line.disposition == "accepted":
                        movement = conn.execute(
                            "INSERT INTO inventory_movements(variant_id,location_id,movement_type,quantity,reference_type,reference_id,note) "
                            "VALUES(%s,%s,'receipt',%s,'purchase_order',%s,%s) "
                            "RETURNING id",
                            (row["variant_id"],grn["location_id"],line.quantity,str(grn["purchase_order_id"]),line.reason or "QC accepted goods"),
                        ).fetchone()
                        conn.execute(
                            "INSERT INTO inventory_balances(variant_id,location_id,on_hand,reserved) VALUES(%s,%s,%s,0) "
                            "ON CONFLICT(variant_id,location_id) DO UPDATE SET on_hand=inventory_balances.on_hand+EXCLUDED.on_hand,updated_at=now()",
                            (row["variant_id"],grn["location_id"],line.quantity),
                        )
                        create_cost_layer(
                            conn,movement_id=movement["id"],variant_id=row["variant_id"],location_id=grn["location_id"],
                            quantity=line.quantity,unit_cost=row["unit_cost"],purchase_order_line_id=row["purchase_order_line_id"],
                            goods_receipt_line_id=line.goods_receipt_line_id,batch_code=row["batch_code"],
                            manufacture_date=row["manufacture_date"],expiry_date=row["expiry_date"],
                        )
                        from app.api import accounting
                        from app.services.accounting_posting import PostingConfigurationError, build_inventory_mapping_lines
                        event_date = accounting._today()
                        accepted_value = money(line.quantity * row["unit_cost"])
                        from app.services.accounting_posting import resolve_legal_entity_code
                        legal_entity_row = conn.execute(
                            "SELECT he.code AS legal_entity_code FROM stock_locations sl "
                            "LEFT JOIN hr_establishments he ON he.id=sl.establishment_id WHERE sl.id=%s",
                            (grn["location_id"],),
                        ).fetchone()
                        if legal_entity_row is None:
                            raise HTTPException(404, "GRN stock location was not found for Accounting scope")
                        legal_entity_code = resolve_legal_entity_code(legal_entity_row.get("legal_entity_code"))
                        mappings = conn.execute(
                            "SELECT * FROM accounting_event_account_mappings WHERE legal_entity_code=%s "
                            "AND source_module='inventory' AND event_type='qc_acceptance' AND status='approved' "
                            "AND effective_from<=%s AND (effective_to IS NULL OR effective_to>=%s)",
                            (legal_entity_code,event_date,event_date),
                        ).fetchall()
                        try:
                            journal_lines = build_inventory_mapping_lines(
                                amount=accepted_value,mappings=mappings,legal_entity_code=legal_entity_code,
                                event_type="qc_acceptance",debit_role="inventory_asset",
                                credit_role="grni_clearing",event_date=event_date,
                                narration=f"QC accepted GRN stock {grn['id']}",
                            )
                        except PostingConfigurationError as exc:
                            raise HTTPException(409,f"GRN QC accounting blocked by Finance mapping: {exc}") from exc
                        accounting._post_voucher(
                            conn,
                            {
                                "voucher_type":"journal","voucher_date":event_date,
                                "narration":f"QC accepted GRN stock {grn['id']}",
                                "reference":f"GRN {grn['id']} QC event {qc_event['id']}",
                                "taxable_total":accepted_value,"total_amount":accepted_value,
                                "source_type":"purchasing_qc_acceptance","source_id":str(qc_event["id"]),
                                "idempotency_key":f"purchasing-qc-acceptance:{qc_event['id']}",
                            },
                            journal_lines,(actor_id,actor_email),
                        )
                totals = conn.execute(
                    "SELECT COALESCE(sum(received_quantity),0) AS received,"
                    "COALESCE(sum(accepted_quantity),0) AS accepted,"
                    "COALESCE(sum(rejected_quantity+damaged_quantity+quarantined_quantity),0) AS nonaccepted,"
                    "COALESCE(sum(accepted_quantity+rejected_quantity+damaged_quantity+quarantined_quantity),0) AS processed "
                    "FROM goods_receipt_lines WHERE goods_receipt_id=%s",
                    (grn_id,),
                ).fetchone()
                if totals["processed"] < totals["received"]:
                    status = "qc_pending"
                elif totals["accepted"] == totals["received"]:
                    status = "accepted"
                elif totals["accepted"] > 0:
                    status = "partially_accepted"
                else:
                    status = "rejected"
                conn.execute("UPDATE goods_receipts SET status=%s WHERE id=%s", (status,grn_id))
        return {"goods_receipt_id": grn_id, "status": status, "replayed": False, "event_count": len(payload.lines)}
    except HTTPException:
        raise
    except psycopg.Error as exc:
        raise _db_error(exc) from exc


class QuarantineReleaseLineInput(BaseModel):
    goods_receipt_line_id: int = Field(gt=0)
    quantity: Decimal = Field(gt=0, max_digits=14, decimal_places=3)
    reason: str = Field(min_length=3, max_length=1000)

    @field_validator("reason")
    @classmethod
    def clean_release_reason(cls, value):
        value = value.strip()
        if len(value) < 3:
            raise ValueError("A release reason of at least 3 characters is required")
        return value


class QuarantineReleaseInput(BaseModel):
    idempotency_key: uuid.UUID
    lines: list[QuarantineReleaseLineInput] = Field(min_length=1, max_length=200)

    @field_validator("lines")
    @classmethod
    def unique_release_lines(cls, lines):
        ids = [line.goods_receipt_line_id for line in lines]
        if len(ids) != len(set(ids)):
            raise ValueError("Each quarantined GRN line may appear once per release")
        return lines


@router.post("/grns/{grn_id}/release-quarantine")
def release_goods_receipt_quarantine(grn_id: int, payload: QuarantineReleaseInput, request: Request):
    """Release inspected supplier stock from quarantine into saleable inventory atomically."""
    actor_id, actor_email, actor_role = _actor(request)
    if actor_role not in {"owner", "admin", "manager"}:
        raise HTTPException(403, "Inventory manager permission is required to release quarantined stock")
    from app.services.inventory_quarantine import calculate_quarantine_release
    from app.services.inventory_costing import create_cost_layer, money
    from app.services.accounting_posting import PostingConfigurationError, build_inventory_mapping_lines

    canonical = {
        "lines": [
            {"goods_receipt_line_id": line.goods_receipt_line_id,
             "quantity": str(line.quantity), "reason": line.reason}
            for line in sorted(payload.lines, key=lambda item: item.goods_receipt_line_id)
        ]
    }
    digest = _payload_hash(canonical)
    try:
        from app.api import accounting
        with _connect() as conn:
            with conn.transaction():
                grn = conn.execute(
                    "SELECT id,purchase_order_id,location_id,status FROM goods_receipts WHERE id=%s FOR UPDATE",
                    (grn_id,),
                ).fetchone()
                if not grn:
                    raise HTTPException(404, "Goods receipt not found")
                prior = conn.execute(
                    "SELECT id,payload_hash,goods_receipt_line_id,disposition FROM goods_receipt_qc_events "
                    "WHERE idempotency_key=%s ORDER BY goods_receipt_line_id",
                    (payload.idempotency_key,),
                ).fetchall()
                if prior:
                    if any(row["payload_hash"] != digest or row["disposition"] != "released" for row in prior):
                        raise HTTPException(409, "Quarantine release idempotency key was already used with a different payload")
                    if len(prior) != len(payload.lines):
                        raise HTTPException(409, "Quarantine release idempotency key was used for a different set of lines")
                    return {"goods_receipt_id": grn_id, "status": grn["status"], "replayed": True,
                            "event_count": len(prior)}
                if grn["status"] in {"accepted", "rejected", "cancelled"}:
                    raise HTTPException(409, "This goods receipt is not eligible for quarantine release")
                line_ids = [line.goods_receipt_line_id for line in payload.lines]
                rows = conn.execute(
                    "SELECT id,variant_id,purchase_order_line_id,received_quantity,accepted_quantity,"
                    "rejected_quantity,damaged_quantity,quarantined_quantity,batch_code,manufacture_date,"
                    "expiry_date,unit_cost,(expiry_date IS NULL OR expiry_date>=CURRENT_DATE) AS is_releasable "
                    "FROM goods_receipt_lines "
                    "WHERE goods_receipt_id=%s AND id=ANY(%s) FOR UPDATE",
                    (grn_id, line_ids),
                ).fetchall()
                by_id = {int(row["id"]): row for row in rows}
                if len(by_id) != len(line_ids):
                    raise HTTPException(422, "A quarantine release line does not belong to this goods receipt")

                released_events = []
                for line in payload.lines:
                    row = by_id[line.goods_receipt_line_id]
                    if not row["is_releasable"]:
                        raise HTTPException(409, "Expired supplier stock cannot be released to saleable inventory; move it through expired-stock quarantine")
                    try:
                        quantities = calculate_quarantine_release(row["quarantined_quantity"], line.quantity)
                    except ValueError as exc:
                        raise HTTPException(409, str(exc)) from exc
                    conn.execute(
                        "UPDATE goods_receipt_lines SET quarantined_quantity=%s,accepted_quantity=accepted_quantity+%s "
                        "WHERE id=%s",
                        (quantities["remaining_quarantined"], quantities["accepted_quantity"], line.goods_receipt_line_id),
                    )
                    event = conn.execute(
                        "INSERT INTO goods_receipt_qc_events(goods_receipt_line_id,disposition,quantity,reason,"
                        "actor_user_id,actor_email,idempotency_key,payload_hash) "
                        "VALUES(%s,'released',%s,%s,%s,%s,%s,%s) RETURNING id",
                        (line.goods_receipt_line_id, line.quantity, line.reason, actor_id, actor_email,
                         payload.idempotency_key, digest),
                    ).fetchone()
                    movement = conn.execute(
                        "INSERT INTO inventory_movements(variant_id,location_id,movement_type,quantity,"
                        "reference_type,reference_id,note) VALUES(%s,%s,'receipt',%s,'purchase_order',%s,%s) RETURNING id",
                        (row["variant_id"], grn["location_id"], line.quantity, str(grn["purchase_order_id"]),
                         f"Quarantine release GRN {grn_id}: {line.reason}"),
                    ).fetchone()
                    conn.execute(
                        "INSERT INTO inventory_balances(variant_id,location_id,on_hand,reserved) VALUES(%s,%s,%s,0) "
                        "ON CONFLICT(variant_id,location_id) DO UPDATE SET "
                        "on_hand=inventory_balances.on_hand+EXCLUDED.on_hand,updated_at=now()",
                        (row["variant_id"], grn["location_id"], line.quantity),
                    )
                    create_cost_layer(
                        conn, movement_id=movement["id"], variant_id=row["variant_id"],
                        location_id=grn["location_id"], quantity=line.quantity, unit_cost=row["unit_cost"],
                        purchase_order_line_id=row["purchase_order_line_id"],
                        goods_receipt_line_id=line.goods_receipt_line_id, batch_code=row["batch_code"],
                        manufacture_date=row["manufacture_date"], expiry_date=row["expiry_date"],
                    )
                    legal_entity = conn.execute(
                        "SELECT COALESCE(he.code,'DEFAULT') AS code FROM stock_locations sl "
                        "LEFT JOIN hr_establishments he ON he.id=sl.establishment_id WHERE sl.id=%s",
                        (grn["location_id"],),
                    ).fetchone()["code"]
                    event_date = accounting._today()
                    mappings = conn.execute(
                        "SELECT * FROM accounting_event_account_mappings WHERE legal_entity_code=%s "
                        "AND source_module='inventory' AND event_type='qc_acceptance' AND status='approved' "
                        "AND effective_from<=%s AND (effective_to IS NULL OR effective_to>=%s)",
                        (legal_entity, event_date, event_date),
                    ).fetchall()
                    accepted_value = money(line.quantity * row["unit_cost"])
                    try:
                        journal_lines = build_inventory_mapping_lines(
                            amount=accepted_value, mappings=mappings, legal_entity_code=legal_entity,
                            event_type="qc_acceptance", debit_role="inventory_asset", credit_role="grni_clearing",
                            event_date=event_date, narration=f"Quarantine release GRN {grn_id} line {line.goods_receipt_line_id}",
                        )
                    except PostingConfigurationError as exc:
                        raise HTTPException(409, f"Quarantine release accounting blocked by Finance mapping: {exc}") from exc
                    accounting._post_voucher(
                        conn,
                        {"voucher_type":"journal", "voucher_date":event_date,
                         "narration":f"Quarantine release GRN {grn_id}",
                         "reference":f"GRN {grn_id} release event {event['id']}",
                         "taxable_total":accepted_value, "total_amount":accepted_value,
                         "source_type":"purchasing_qc_release", "source_id":str(event["id"]),
                         "idempotency_key":f"purchasing-qc-release:{event['id']}"},
                        journal_lines, (actor_id, actor_email),
                    )
                    released_events.append(event["id"])

                totals = conn.execute(
                    "SELECT COALESCE(sum(received_quantity),0) AS received,"
                    "COALESCE(sum(accepted_quantity),0) AS accepted,"
                    "COALESCE(sum(rejected_quantity+damaged_quantity+quarantined_quantity),0) AS nonaccepted,"
                    "COALESCE(sum(accepted_quantity+rejected_quantity+damaged_quantity+quarantined_quantity),0) AS processed "
                    "FROM goods_receipt_lines WHERE goods_receipt_id=%s",
                    (grn_id,),
                ).fetchone()
                if totals["processed"] < totals["received"]:
                    status = "qc_pending"
                elif totals["accepted"] == totals["received"]:
                    status = "accepted"
                elif totals["accepted"] > 0:
                    status = "partially_accepted"
                else:
                    status = "rejected"
                conn.execute("UPDATE goods_receipts SET status=%s WHERE id=%s", (status, grn_id))
        return {"goods_receipt_id": grn_id, "status": status, "replayed": False,
                "event_count": len(released_events), "released_event_ids": released_events}
    except HTTPException:
        raise
    except psycopg.Error as exc:
        raise _db_error(exc) from exc


class SupplierInvoiceLineInput(BaseModel):
    purchase_order_line_id: int = Field(gt=0)
    goods_receipt_line_id: int = Field(gt=0)
    quantity: Decimal = Field(gt=0, max_digits=14, decimal_places=3)
    unit_rate: Decimal = Field(ge=0, max_digits=14, decimal_places=2)
    taxable_value: Decimal = Field(ge=0, max_digits=16, decimal_places=2)
    hsn_sac: str | None = Field(default=None, max_length=8)
    gst_rate: Decimal | None = Field(default=None, ge=0, le=100, max_digits=5, decimal_places=2)
    cgst_amount: Decimal = Field(default=0, ge=0, max_digits=16, decimal_places=2)
    sgst_amount: Decimal = Field(default=0, ge=0, max_digits=16, decimal_places=2)
    igst_amount: Decimal = Field(default=0, ge=0, max_digits=16, decimal_places=2)

    @model_validator(mode="after")
    def validate_line_tax(self):
        cgst = self.cgst_amount
        sgst = self.sgst_amount
        igst = self.igst_amount
        tax_total = cgst + sgst + igst
        if self.gst_rate is None:
            if tax_total:
                raise ValueError("A GST rate is required when a supplier invoice line has GST")
            return self

        expected_tax = (self.taxable_value * self.gst_rate / Decimal("100")).quantize(Decimal("0.01"))
        if abs(tax_total - expected_tax) > Decimal("0.01"):
            raise ValueError("Supplier invoice line GST must match taxable value multiplied by GST rate")

        intra_state = igst == 0 and abs(cgst - sgst) <= Decimal("0.01")
        inter_state = cgst == 0 and sgst == 0
        if tax_total and not (intra_state or inter_state):
            raise ValueError("Supplier invoice line must use matching CGST/SGST or IGST, not both")
        return self


class SupplierInvoiceCreate(BaseModel):
    purchase_order_id: int = Field(gt=0)
    invoice_number: str = Field(min_length=1, max_length=100)
    invoice_date: date
    due_date: date | None = None
    supplier_gstin: str | None = Field(default=None, min_length=15, max_length=15)
    taxable_value: Decimal = Field(ge=0, max_digits=16, decimal_places=2)
    cgst_amount: Decimal = Field(default=0, ge=0, max_digits=16, decimal_places=2)
    sgst_amount: Decimal = Field(default=0, ge=0, max_digits=16, decimal_places=2)
    igst_amount: Decimal = Field(default=0, ge=0, max_digits=16, decimal_places=2)
    cess_amount: Decimal = Field(default=0, ge=0, max_digits=16, decimal_places=2)
    freight_amount: Decimal = Field(default=0, ge=0, max_digits=16, decimal_places=2)
    discount_amount: Decimal = Field(default=0, ge=0, max_digits=16, decimal_places=2)
    invoice_total: Decimal = Field(gt=0, max_digits=16, decimal_places=2)
    source_document_uri: str | None = Field(default=None, max_length=2000)
    lines: list[SupplierInvoiceLineInput] = Field(min_length=1, max_length=200)

    @field_validator("invoice_number")
    @classmethod
    def clean_invoice_number(cls, value):
        value = value.strip()
        if not value:
            raise ValueError("Supplier invoice number cannot be blank")
        return value

    @field_validator("lines")
    @classmethod
    def unique_invoice_po_lines(cls, lines):
        ids = [line.purchase_order_line_id for line in lines]
        if len(ids) != len(set(ids)):
            raise ValueError("Each purchase order line may appear once per supplier invoice")
        return lines

    @field_validator("due_date")
    @classmethod
    def valid_due_date(cls, value, info):
        invoice_date = info.data.get("invoice_date")
        if value and invoice_date and value < invoice_date:
            raise ValueError("Due date cannot precede invoice date")
        return value

    @field_validator("invoice_total")
    @classmethod
    def invoice_total_matches_components(cls, value, info):
        components = sum((info.data.get(key) or Decimal("0") for key in (
            "taxable_value", "cgst_amount", "sgst_amount", "igst_amount",
            "cess_amount", "freight_amount"
        )), Decimal("0")) - (info.data.get("discount_amount") or Decimal("0"))
        if abs(value - components) > Decimal("0.01"):
            raise ValueError("Invoice total must equal taxable value + GST + cess + freight - discount")
        return value


def validate_supplier_invoice_tax_mode(lines: list[SupplierInvoiceLineInput]) -> None:
    has_igst = any(line.igst_amount for line in lines)
    has_cgst_sgst = any(line.cgst_amount or line.sgst_amount for line in lines)
    if has_igst and has_cgst_sgst:
        raise HTTPException(422, "A supplier invoice cannot mix IGST with CGST/SGST across its lines")


@router.get("/supplier-invoices")
def list_supplier_invoices(
    purchase_order_id: int | None = Query(default=None, gt=0),
    match_status: str | None = None,
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
):
    allowed = {"pending", "matched", "variance", "blocked", "approved", "rejected"}
    if match_status and match_status not in allowed:
        raise HTTPException(422, "Unsupported invoice match status")
    clauses = []
    params = []
    if purchase_order_id:
        clauses.append("i.purchase_order_id=%s"); params.append(purchase_order_id)
    if match_status:
        clauses.append("i.match_status=%s"); params.append(match_status)
    where = "WHERE " + " AND ".join(clauses) if clauses else ""
    params.extend([limit, offset])
    try:
        with _connect() as conn:
            rows = conn.execute(
                "SELECT i.id,i.invoice_number,i.supplier_id,s.name AS supplier_name,i.purchase_order_id,"
                "po.purchase_number,i.invoice_date,i.due_date,i.invoice_total,i.match_status,"
                "COALESCE((SELECT sum(a.allocated_amount) FROM supplier_payment_allocations a WHERE a.supplier_invoice_id=i.id),0) AS paid_amount "
                "FROM supplier_invoices i JOIN suppliers s ON s.id=i.supplier_id "
                "JOIN purchase_orders po ON po.id=i.purchase_order_id "
                f"{where} ORDER BY i.invoice_date DESC,i.id DESC LIMIT %s OFFSET %s",
                tuple(params),
            ).fetchall()
        return {"items": rows, "limit": limit, "offset": offset}
    except psycopg.Error as exc:
        raise _db_error(exc) from exc


@router.post("/supplier-invoices", status_code=201)
def create_supplier_invoice(payload: SupplierInvoiceCreate, request: Request):
    actor_id, actor_email, _ = _actor(request)
    try:
        with _connect() as conn:
            with conn.transaction():
                po = conn.execute(
                    "SELECT id,supplier_id,status,policy_version_id FROM purchase_orders WHERE id=%s FOR UPDATE",
                    (payload.purchase_order_id,),
                ).fetchone()
                if not po:
                    raise HTTPException(404, "Purchase order not found")
                if po["status"] in {"draft", "cancelled"}:
                    raise HTTPException(409, "Invoice cannot be matched to a draft or cancelled purchase order")
                invoice_policy = _purchase_policy_for_po(conn,po["id"],po["policy_version_id"])
                line_taxable = sum((line.taxable_value for line in payload.lines), Decimal("0"))
                line_cgst = sum((line.cgst_amount for line in payload.lines), Decimal("0"))
                line_sgst = sum((line.sgst_amount for line in payload.lines), Decimal("0"))
                line_igst = sum((line.igst_amount for line in payload.lines), Decimal("0"))
                validate_supplier_invoice_tax_mode(payload.lines)
                for actual, expected, name in (
                    (line_taxable, payload.taxable_value, "taxable value"),
                    (line_cgst, payload.cgst_amount, "CGST"),
                    (line_sgst, payload.sgst_amount, "SGST"),
                    (line_igst, payload.igst_amount, "IGST"),
                ):
                    if abs(actual - expected) > Decimal("0.01"):
                        raise HTTPException(422, f"Invoice line {name} does not match the invoice header")
                variance = False
                validated = []
                for line in payload.lines:
                    po_line = conn.execute(
                        "SELECT id,variant_id,unit_cost FROM purchase_order_lines "
                        "WHERE id=%s AND purchase_order_id=%s FOR SHARE",
                        (line.purchase_order_line_id,payload.purchase_order_id),
                    ).fetchone()
                    grn_line = conn.execute(
                        "SELECT id,variant_id,purchase_order_line_id,accepted_quantity,goods_receipt_id "
                        "FROM goods_receipt_lines WHERE id=%s FOR SHARE",
                        (line.goods_receipt_line_id,),
                    ).fetchone()
                    if not po_line or not grn_line or grn_line["purchase_order_line_id"] != line.purchase_order_line_id:
                        raise HTTPException(422, "Invoice line must match a purchase order line and its GRN line")
                    grn = conn.execute(
                        "SELECT id,purchase_order_id,status FROM goods_receipts WHERE id=%s FOR SHARE",
                        (grn_line["goods_receipt_id"],),
                    ).fetchone()
                    if not grn or grn["purchase_order_id"] != payload.purchase_order_id:
                        raise HTTPException(422, "Invoice GRN line belongs to a different purchase order")
                    if not supplier_invoice_grn_is_accepted(grn["status"]):
                        raise HTTPException(409, "Supplier invoices require a QC-accepted goods receipt")
                    if grn_line["variant_id"] != po_line["variant_id"]:
                        raise HTTPException(422, "Invoice variant does not match the purchase order")
                    invoiced = conn.execute(
                        "SELECT COALESCE(sum(il.quantity),0) AS quantity FROM supplier_invoice_lines il "
                        "JOIN supplier_invoices si ON si.id=il.supplier_invoice_id "
                        "WHERE il.goods_receipt_line_id=%s AND si.match_status<>'rejected'",
                        (line.goods_receipt_line_id,),
                    ).fetchone()["quantity"]
                    if line.quantity > grn_line["accepted_quantity"] - invoiced:
                        raise HTTPException(409, "Invoice quantity exceeds QC-accepted and uninvoiced GRN quantity")
                    if abs(line.taxable_value - (line.quantity * line.unit_rate)) > Decimal("0.01"):
                        raise HTTPException(422, "Invoice line taxable value must equal quantity multiplied by unit rate")
                    if line.unit_rate != po_line["unit_cost"]:
                        variance = True
                    validated.append((line,po_line,grn_line))
                invoice = conn.execute(
                    "INSERT INTO supplier_invoices(supplier_id,purchase_order_id,supplier_gstin,invoice_number,invoice_date,due_date,"
                    "taxable_value,cgst_amount,sgst_amount,igst_amount,cess_amount,freight_amount,discount_amount,invoice_total,"
                    "source_document_uri,match_status,created_by_user_id,created_by_email,policy_version_id) "
                    "VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) "
                    "RETURNING id,invoice_number,invoice_date,invoice_total,match_status,created_at",
                    (po["supplier_id"],payload.purchase_order_id,payload.supplier_gstin,payload.invoice_number,
                     payload.invoice_date,payload.due_date,payload.taxable_value,payload.cgst_amount,payload.sgst_amount,
                     payload.igst_amount,payload.cess_amount,payload.freight_amount,payload.discount_amount,
                     payload.invoice_total,payload.source_document_uri,"variance" if variance else "matched",
                     actor_id,actor_email,invoice_policy["id"]),
                ).fetchone()
                for line,po_line,grn_line in validated:
                    conn.execute(
                        "INSERT INTO supplier_invoice_lines(supplier_invoice_id,purchase_order_line_id,goods_receipt_line_id,"
                        "variant_id,quantity,unit_rate,taxable_value,hsn_sac,gst_rate,cgst_amount,sgst_amount,igst_amount) "
                        "VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                        (invoice["id"],line.purchase_order_line_id,line.goods_receipt_line_id,po_line["variant_id"],
                         line.quantity,line.unit_rate,line.taxable_value,line.hsn_sac,line.gst_rate,
                         line.cgst_amount,line.sgst_amount,line.igst_amount),
                    )
                invoice_grni = money(
                    payload.taxable_value + payload.freight_amount - payload.discount_amount
                )
                receipt_grni = money(sum(
                    (line.quantity * po_line["unit_cost"] for line,po_line,_ in validated),
                    Decimal("0"),
                ))
                line_price_variance = sum(
                    (abs(line.quantity * (line.unit_rate - po_line["unit_cost"])) for line, po_line, _ in validated),
                    Decimal("0"),
                )
                grni_variance = abs(invoice_grni - receipt_grni)
                try:
                    grni_within_tolerance = supplier_invoice_variance_within_tolerance(
                        invoice_policy["policy_config"], grni_variance,
                    )
                    price_within_tolerance = supplier_invoice_variance_within_tolerance(
                        invoice_policy["policy_config"], line_price_variance,
                    )
                except ValueError as exc:
                    raise HTTPException(409, f"Supplier invoice variance policy is invalid: {exc}") from exc
                match_status = (
                    "matched" if grni_within_tolerance and price_within_tolerance else
                    "blocked" if not grni_within_tolerance else
                    "variance"
                )
                conn.execute(
                    "UPDATE supplier_invoices SET match_status=%s WHERE id=%s",
                    (match_status, invoice["id"]),
                )
                invoice["match_status"] = match_status
        return invoice
    except HTTPException:
        raise
    except psycopg.errors.UniqueViolation as exc:
        raise HTTPException(409, "This supplier invoice number has already been recorded") from exc
    except psycopg.Error as exc:
        raise _db_error(exc) from exc


def build_supplier_invoice_voucher_lines(invoice: dict, codes: dict) -> list[dict]:
    """Build the GRNI-clearing purchase invoice voucher from a matched supplier bill."""
    from decimal import Decimal

    if Decimal(str(invoice.get("cess_amount") or 0)) != 0:
        raise HTTPException(422, "Supplier invoice cess requires a configured input-cess ledger account; approval is blocked")
    grni_amount = (
        Decimal(str(invoice["taxable_value"]))
        + Decimal(str(invoice.get("freight_amount") or 0))
        - Decimal(str(invoice.get("discount_amount") or 0))
    ).quantize(Decimal("0.01"))
    if grni_amount <= 0:
        raise HTTPException(422, "Net GRNI amount after freight and discount must be positive")
    lines = [
        {"account_id": codes["2050"]["id"], "debit": grni_amount,
         "narration": "Clear goods received not invoiced"}
    ]
    for key, code, narration in (
        ("cgst_amount", "1300", "Input CGST"),
        ("sgst_amount", "1301", "Input SGST"),
        ("igst_amount", "1302", "Input IGST"),
    ):
        amount = Decimal(str(invoice.get(key) or 0)).quantize(Decimal("0.01"))
        if amount:
            lines.append({"account_id": codes[code]["id"], "debit": amount, "narration": narration})
    lines.append({
        "account_id": codes["2000"]["id"],
        "credit": Decimal(str(invoice["invoice_total"])).quantize(Decimal("0.01")),
        "narration": "Supplier accounts payable",
    })
    return lines


def supplier_invoice_grn_is_accepted(status: str) -> bool:
    """Only QC-accepted GRNs may support supplier invoice matching."""
    return status in {"accepted", "partially_accepted"}


def supplier_invoice_grni_matches(invoice: dict, receipt_grni_amount) -> bool:
    invoice_grni_amount = (
        Decimal(str(invoice["taxable_value"]))
        + Decimal(str(invoice.get("freight_amount") or 0))
        - Decimal(str(invoice.get("discount_amount") or 0))
    )
    return money(invoice_grni_amount) == money(Decimal(str(receipt_grni_amount)))


class SupplierInvoiceReviewReason(BaseModel):
    reason: str = Field(min_length=3, max_length=1000)

    @field_validator("reason")
    @classmethod
    def clean_review_reason(cls, value):
        value = value.strip()
        if len(value) < 3:
            raise ValueError("A review reason of at least 3 characters is required")
        return value


@router.post("/supplier-invoices/{invoice_id}/approve")
def approve_supplier_invoice(invoice_id: int, request: Request):
    actor_id, actor_email, actor_role = _actor(request)
    posting_exception = None
    try:
        from app.api import accounting
        from app.services.accounting_posting import (
            PostingConfigurationError, build_supplier_invoice_mapping_lines,
        )
        with _connect() as conn:
            with conn.transaction():
                invoice = conn.execute(
                    "SELECT i.*,s.name AS supplier_name,he.code AS legal_entity_code "
                    "FROM supplier_invoices i JOIN suppliers s ON s.id=i.supplier_id "
                    "JOIN purchase_orders po ON po.id=i.purchase_order_id "
                    "JOIN stock_locations sl ON sl.id=po.location_id "
                    "LEFT JOIN hr_establishments he ON he.id=sl.establishment_id "
                    "WHERE i.id=%s FOR UPDATE OF i",
                    (invoice_id,),
                ).fetchone()
                if not invoice:
                    raise HTTPException(404, "Supplier invoice not found")
                if invoice["match_status"] == "approved" and invoice["accounting_voucher_id"]:
                    return {"id": invoice_id, "invoice_number": invoice["invoice_number"],
                            "match_status": "approved", "accounting_voucher_id": invoice["accounting_voucher_id"],
                            "idempotent_replay": True}
                if invoice["match_status"] != "matched":
                    raise HTTPException(409, "Only fully matched supplier invoices can be approved")

                policy = _purchase_policy_for_po(conn, invoice["purchase_order_id"], invoice["policy_version_id"])
                evaluation, next_stage, approval_complete = _record_purchase_approval_stage(
                    conn, policy=policy, document_type="supplier_invoice", document_id=invoice_id,
                    revision=int(invoice["approval_revision"]), amount=Decimal(str(invoice["invoice_total"])),
                    creator_user_id=invoice["created_by_user_id"], actor_id=actor_id,
                    actor_email=actor_email, actor_role=actor_role,
                    reason="Supplier invoice approval",
                )
                conn.execute(
                    "UPDATE supplier_invoices SET policy_version_id=%s,updated_at=now() WHERE id=%s",
                    (policy["id"],invoice_id),
                )
                if not approval_complete:
                    return {
                        "id": invoice_id, "invoice_number": invoice["invoice_number"],
                        "match_status": "matched", "approval_pending": True,
                        "approved_stage": next_stage["sequence"],
                        "required_stages": len(evaluation["stages"]),
                        "policy_version_id": policy["id"],
                    }
                receipt_grni = conn.execute(
                    "SELECT COALESCE(sum(il.quantity * pol.unit_cost),0) AS amount "
                    "FROM supplier_invoice_lines il "
                    "JOIN purchase_order_lines pol ON pol.id=il.purchase_order_line_id "
                    "WHERE il.supplier_invoice_id=%s",
                    (invoice_id,),
                ).fetchone()["amount"]
                if not supplier_invoice_grni_matches(invoice, receipt_grni):
                    raise HTTPException(
                        409,
                        "Invoice GRNI amount does not match the received stock value for these quantities; "
                        "approval is blocked until an accounting variance policy is approved",
                    )

                from app.services.accounting_posting import resolve_legal_entity_code
                legal_entity_code = resolve_legal_entity_code(invoice.get("legal_entity_code"))
                mappings = conn.execute(
                    "SELECT * FROM accounting_event_account_mappings WHERE legal_entity_code=%s "
                    "AND source_module='purchasing' AND event_type='supplier_invoice_approval' "
                    "AND status='approved' AND effective_from<=%s "
                    "AND (effective_to IS NULL OR effective_to>=%s)",
                    (legal_entity_code, invoice["invoice_date"], invoice["invoice_date"]),
                ).fetchall()
                try:
                    lines = build_supplier_invoice_mapping_lines(
                        invoice, mappings, legal_entity_code=legal_entity_code,
                        event_date=invoice["invoice_date"],
                    )
                except PostingConfigurationError as exc:
                    posting_exception = str(exc)
                    conn.execute(
                        "INSERT INTO accounting_posting_exceptions(source_module,source_type,source_id,event_key,"
                        "event_date,status,exception_code,exception_message,attempts,last_attempt_at,updated_at) "
                        "VALUES('purchasing','supplier_invoice',%s,'supplier-invoice-approved-v1',%s,"
                        "'exception','mapping_or_balance_error',%s,1,now(),now()) "
                        "ON CONFLICT(source_module,source_type,source_id,event_key) DO UPDATE SET "
                        "status='exception',exception_code=EXCLUDED.exception_code,"
                        "exception_message=EXCLUDED.exception_message,"
                        "attempts=accounting_posting_exceptions.attempts+1,"
                        "last_attempt_at=now(),updated_at=now()",
                        (str(invoice_id), invoice["invoice_date"], posting_exception[:2000]),
                    )
                if posting_exception is None:
                    voucher_id = accounting._post_voucher(conn, {
                        "voucher_type": "purchase",
                        "voucher_date": invoice["invoice_date"],
                        "narration": f"Supplier invoice {invoice['invoice_number']} against accepted GRN",
                        "reference": invoice["invoice_number"],
                        "party_type": "supplier",
                        "party_name": invoice["supplier_name"],
                        "party_gstin": invoice["supplier_gstin"],
                        "due_date": invoice["due_date"],
                        "taxable_total": invoice["taxable_value"],
                        "tax_total": (Decimal(str(invoice["cgst_amount"])) +
                                      Decimal(str(invoice["sgst_amount"])) +
                                      Decimal(str(invoice["igst_amount"]))),
                        "total_amount": invoice["invoice_total"],
                        "source_type": "supplier_invoice",
                        "source_id": str(invoice_id),
                        "idempotency_key": f"supplier-invoice:{invoice_id}",
                    }, lines, (actor_id, actor_email))
                    row = conn.execute(
                        "UPDATE supplier_invoices SET match_status='approved',accounting_voucher_id=%s,updated_at=now() "
                        "WHERE id=%s RETURNING id,invoice_number,match_status,accounting_voucher_id,updated_at",
                        (voucher_id, invoice_id),
                    ).fetchone()
                    conn.execute(
                        "INSERT INTO purchasing_approval_events(document_type,document_id,action,actor_user_id,actor_email,actor_role) "
                        "VALUES('supplier_invoice',%s,'approved',%s,%s,%s)",
                        (invoice_id,actor_id,actor_email,actor_role),
                    )
                    conn.execute(
                        "INSERT INTO accounting_posting_exceptions(source_module,source_type,source_id,event_key,"
                        "event_date,status,voucher_id,attempts,last_attempt_at,updated_at) "
                        "VALUES('purchasing','supplier_invoice',%s,'supplier-invoice-approved-v1',%s,"
                        "'posted',%s,1,now(),now()) "
                        "ON CONFLICT(source_module,source_type,source_id,event_key) DO UPDATE SET "
                        "status='posted',voucher_id=EXCLUDED.voucher_id,exception_code=NULL,"
                        "exception_message=NULL,attempts=accounting_posting_exceptions.attempts+1,"
                        "last_attempt_at=now(),updated_at=now()",
                        (str(invoice_id), invoice["invoice_date"], voucher_id),
                    )
        if posting_exception:
            raise HTTPException(
                409,
                "Supplier invoice remains matched but was not approved: Finance mapping exception recorded. "
                + posting_exception,
            )
        return {**row, "idempotent_replay": False}
    except HTTPException:
        raise
    except psycopg.Error as exc:
        raise _db_error(exc) from exc


@router.post("/supplier-invoices/{invoice_id}/resolve-variance")
def resolve_supplier_invoice_variance(invoice_id: int, payload: SupplierInvoiceReviewReason, request: Request):
    actor_id, actor_email, actor_role = _actor(request)
    if actor_role not in {"owner", "admin"}:
        raise HTTPException(403, "Owner or admin permission is required to resolve supplier invoice variances")
    try:
        with _connect() as conn:
            with conn.transaction():
                invoice = conn.execute(
                    "SELECT i.id,i.match_status,i.taxable_value,i.freight_amount,i.discount_amount "
                    "FROM supplier_invoices i WHERE i.id=%s FOR UPDATE",
                    (invoice_id,),
                ).fetchone()
                if not invoice:
                    raise HTTPException(404, "Supplier invoice not found")
                if invoice["match_status"] == "matched":
                    return {"id": invoice_id, "match_status": "matched", "idempotent_replay": True}
                if invoice["match_status"] != "variance":
                    raise HTTPException(409, "Only price-variance invoices can be resolved")
                receipt_grni = conn.execute(
                    "SELECT COALESCE(sum(il.quantity * pol.unit_cost),0) AS amount "
                    "FROM supplier_invoice_lines il "
                    "JOIN purchase_order_lines pol ON pol.id=il.purchase_order_line_id "
                    "WHERE il.supplier_invoice_id=%s",
                    (invoice_id,),
                ).fetchone()["amount"]
                if not supplier_invoice_grni_matches(invoice, receipt_grni):
                    raise HTTPException(
                        409,
                        "Invoice net GRNI does not match the received stock value; the variance cannot be resolved without an approved accounting adjustment policy",
                    )
                conn.execute(
                    "UPDATE supplier_invoices SET match_status='matched',updated_at=now() WHERE id=%s",
                    (invoice_id,),
                )
                conn.execute(
                    "INSERT INTO purchasing_approval_events(document_type,document_id,action,actor_user_id,actor_email,actor_role,reason) "
                    "VALUES('supplier_invoice',%s,'approved',%s,%s,%s,%s)",
                    (
                        invoice_id,actor_id,actor_email,actor_role,
                        "Price variance reviewed and matched to received GRNI: " + payload.reason,
                    ),
                )
        return {"id": invoice_id, "match_status": "matched", "idempotent_replay": False}
    except HTTPException:
        raise
    except psycopg.Error as exc:
        raise _db_error(exc) from exc


@router.post("/supplier-invoices/{invoice_id}/reject")
def reject_supplier_invoice(invoice_id: int, payload: SupplierInvoiceReviewReason, request: Request):
    actor_id, actor_email, actor_role = _actor(request)
    if actor_role not in {"owner", "admin"}:
        raise HTTPException(403, "Owner or admin permission is required to reject supplier invoices")
    try:
        with _connect() as conn:
            with conn.transaction():
                invoice = conn.execute(
                    "SELECT id,match_status FROM supplier_invoices WHERE id=%s FOR UPDATE",
                    (invoice_id,),
                ).fetchone()
                if not invoice:
                    raise HTTPException(404, "Supplier invoice not found")
                if invoice["match_status"] == "rejected":
                    return {"id": invoice_id, "match_status": "rejected", "idempotent_replay": True}
                if invoice["match_status"] not in {"variance", "blocked", "matched"}:
                    raise HTTPException(409, "Only unapproved supplier invoices can be rejected")
                conn.execute(
                    "UPDATE supplier_invoices SET match_status='rejected',updated_at=now() WHERE id=%s",
                    (invoice_id,),
                )
                conn.execute(
                    "INSERT INTO purchasing_approval_events(document_type,document_id,action,actor_user_id,actor_email,actor_role,reason) "
                    "VALUES('supplier_invoice',%s,'rejected',%s,%s,%s,%s)",
                    (invoice_id,actor_id,actor_email,actor_role,payload.reason),
                )
        return {"id": invoice_id, "match_status": "rejected", "idempotent_replay": False}
    except HTTPException:
        raise
    except psycopg.Error as exc:
        raise _db_error(exc) from exc


class PaymentAllocationInput(BaseModel):
    accounting_voucher_id: int = Field(gt=0)
    allocated_amount: Decimal = Field(gt=0, max_digits=16, decimal_places=2)


@router.post("/supplier-invoices/{invoice_id}/payment-allocations", status_code=201)
def allocate_supplier_payment(invoice_id: int, payload: PaymentAllocationInput, request: Request):
    actor_id, actor_email, _ = _actor(request)
    try:
        with _connect() as conn:
            with conn.transaction():
                invoice = conn.execute(
                    "SELECT i.id,i.supplier_id,i.invoice_total,i.match_status,s.name AS supplier_name "
                    "FROM supplier_invoices i JOIN suppliers s ON s.id=i.supplier_id WHERE i.id=%s FOR UPDATE OF i",
                    (invoice_id,),
                ).fetchone()
                if not invoice:
                    raise HTTPException(404, "Supplier invoice not found")
                if invoice["match_status"] != "approved":
                    raise HTTPException(409, "Only approved supplier invoices can receive payment allocations")
                voucher = conn.execute(
                    "SELECT id,voucher_type,status,party_type,party_name,total_amount "
                    "FROM accounting_vouchers WHERE id=%s FOR UPDATE",
                    (payload.accounting_voucher_id,),
                ).fetchone()
                if not voucher or voucher["status"] != "posted" or voucher["voucher_type"] != "payment":
                    raise HTTPException(422, "Allocation must reference an already-posted Accounting payment voucher")
                if voucher["party_type"] != "supplier" or (voucher["party_name"] or "").strip().casefold() != invoice["supplier_name"].strip().casefold():
                    raise HTTPException(422, "Payment voucher supplier does not match the invoice supplier")
                invoice_paid = conn.execute(
                    "SELECT COALESCE(sum(allocated_amount),0) AS amount FROM supplier_payment_allocations WHERE supplier_invoice_id=%s",
                    (invoice_id,),
                ).fetchone()["amount"]
                if invoice_paid + payload.allocated_amount > invoice["invoice_total"]:
                    raise HTTPException(409, "Payment allocation exceeds the invoice outstanding balance")
                voucher_allocated = conn.execute(
                    "SELECT COALESCE(sum(allocated_amount),0) AS amount FROM supplier_payment_allocations WHERE accounting_voucher_id=%s",
                    (payload.accounting_voucher_id,),
                ).fetchone()["amount"]
                if voucher_allocated + payload.allocated_amount > voucher["total_amount"]:
                    raise HTTPException(409, "Payment allocation exceeds the posted voucher amount")
                row = conn.execute(
                    "INSERT INTO supplier_payment_allocations(supplier_invoice_id,accounting_voucher_id,allocated_amount,currency,created_by_user_id,created_by_email) "
                    "VALUES(%s,%s,%s,%s,%s,%s) RETURNING id,supplier_invoice_id,accounting_voucher_id,allocated_amount,currency,allocated_at",
                    (invoice_id,payload.accounting_voucher_id,payload.allocated_amount,"INR",actor_id,actor_email),
                ).fetchone()
        return row
    except HTTPException:
        raise
    except psycopg.errors.UniqueViolation as exc:
        raise HTTPException(409, "This Accounting payment voucher is already allocated to the invoice") from exc
    except psycopg.Error as exc:
        raise _db_error(exc) from exc


class SupplierReturnLineInput(BaseModel):
    goods_receipt_line_id: int = Field(gt=0)
    quantity: Decimal = Field(gt=0, max_digits=14, decimal_places=3)
    reason: str | None = Field(default=None, max_length=1000)


class SupplierReturnCreate(BaseModel):
    goods_receipt_id: int = Field(gt=0)
    supplier_invoice_id: int = Field(gt=0)
    reason: str = Field(min_length=3, max_length=2000)
    lines: list[SupplierReturnLineInput] = Field(min_length=1, max_length=200)

    @field_validator("reason")
    @classmethod
    def clean_return_reason(cls, value):
        value = value.strip()
        if len(value) < 3:
            raise ValueError("Return reason must contain at least 3 characters")
        return value

    @field_validator("lines")
    @classmethod
    def unique_return_lines(cls, lines):
        ids = [line.goods_receipt_line_id for line in lines]
        if len(ids) != len(set(ids)):
            raise ValueError("Each GRN line may appear once per supplier return")
        return lines


@router.post("/supplier-returns", status_code=201)
def create_supplier_return(payload: SupplierReturnCreate, request: Request):
    actor_id, actor_email, _ = _actor(request)
    try:
        with _connect() as conn:
            with conn.transaction():
                grn = conn.execute(
                    "SELECT id,purchase_order_id,supplier_id,status FROM goods_receipts WHERE id=%s FOR SHARE",
                    (payload.goods_receipt_id,),
                ).fetchone()
                if not grn:
                    raise HTTPException(404, "Goods receipt not found")
                if grn["status"] not in {"accepted", "partially_accepted"}:
                    raise HTTPException(409, "Supplier returns require QC-accepted GRN stock")
                invoice = conn.execute(
                    "SELECT id,match_status FROM supplier_invoices "
                    "WHERE id=%s AND supplier_id=%s AND purchase_order_id=%s FOR UPDATE",
                    (payload.supplier_invoice_id,grn["supplier_id"],grn["purchase_order_id"]),
                ).fetchone()
                if not invoice:
                    raise HTTPException(422, "Supplier invoice does not belong to this supplier and purchase order")
                if invoice["match_status"] != "approved":
                    raise HTTPException(409, "Supplier returns must link to an approved supplier invoice")
                number = "SR-" + uuid.uuid4().hex[:12].upper()
                result = conn.execute(
                    "INSERT INTO supplier_returns(return_number,supplier_id,purchase_order_id,goods_receipt_id,supplier_invoice_id,reason,created_by_user_id,created_by_email) "
                    "VALUES(%s,%s,%s,%s,%s,%s,%s,%s) RETURNING id,return_number,status,created_at",
                    (number,grn["supplier_id"],grn["purchase_order_id"],grn["id"],payload.supplier_invoice_id,
                     payload.reason,actor_id,actor_email),
                ).fetchone()
                for line in payload.lines:
                    grn_line = conn.execute(
                        "SELECT id,variant_id,accepted_quantity,unit_cost FROM goods_receipt_lines "
                        "WHERE id=%s AND goods_receipt_id=%s FOR UPDATE",
                        (line.goods_receipt_line_id,grn["id"]),
                    ).fetchone()
                    if not grn_line:
                        raise HTTPException(422, "Return line does not belong to the selected GRN")
                    returned = conn.execute(
                        "SELECT COALESCE(sum(rl.quantity),0) AS quantity FROM supplier_return_lines rl "
                        "JOIN supplier_returns r ON r.id=rl.supplier_return_id "
                        "WHERE rl.goods_receipt_line_id=%s AND r.status<>'cancelled'",
                        (line.goods_receipt_line_id,),
                    ).fetchone()["quantity"]
                    if line.quantity > grn_line["accepted_quantity"] - returned:
                        raise HTTPException(409, "Return quantity exceeds QC-accepted quantity not already returned")
                    invoice_line = conn.execute(
                        "SELECT quantity FROM supplier_invoice_lines "
                        "WHERE supplier_invoice_id=%s AND goods_receipt_line_id=%s FOR SHARE",
                        (payload.supplier_invoice_id,grn_line["id"]),
                    ).fetchone()
                    if not invoice_line:
                        raise HTTPException(409, "Every returned GRN line must be covered by the selected approved supplier invoice")
                    previously_returned = conn.execute(
                        "SELECT COALESCE(sum(srl.quantity),0) AS quantity "
                        "FROM supplier_return_lines srl "
                        "JOIN supplier_returns sr ON sr.id=srl.supplier_return_id "
                        "WHERE sr.supplier_invoice_id=%s AND sr.status<>'cancelled' "
                        "AND srl.goods_receipt_line_id=%s",
                        (payload.supplier_invoice_id,grn_line["id"]),
                    ).fetchone()["quantity"]
                    if not supplier_return_invoice_quantity_available(
                        invoice_line["quantity"], previously_returned, line.quantity
                    ):
                        raise HTTPException(409, "Return quantity exceeds the remaining quantity on the linked supplier invoice")
                    conn.execute(
                        "INSERT INTO supplier_return_lines(supplier_return_id,goods_receipt_line_id,variant_id,quantity,unit_cost,reason) "
                        "VALUES(%s,%s,%s,%s,%s,%s)",
                        (result["id"],grn_line["id"],grn_line["variant_id"],line.quantity,grn_line["unit_cost"],line.reason),
                    )
        return {**result, "line_count": len(payload.lines)}
    except HTTPException:
        raise
    except psycopg.Error as exc:
        raise _db_error(exc) from exc


@router.get("/supplier-returns")
def list_supplier_returns(
    status: str | None = None,
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
):
    allowed = {"draft", "submitted", "approved", "dispatched", "credited", "cancelled"}
    if status and status not in allowed:
        raise HTTPException(422, "Unsupported supplier return status")
    try:
        with _connect() as conn:
            rows = conn.execute(
                "SELECT r.id,r.return_number,r.supplier_id,s.name AS supplier_name,r.purchase_order_id,"
                "po.purchase_number,r.goods_receipt_id,r.supplier_invoice_id,r.status,r.reason,"
                "r.debit_note_number,r.debit_note_date,r.created_at,"
                "(SELECT count(*) FROM supplier_return_lines l WHERE l.supplier_return_id=r.id) AS line_count "
                "FROM supplier_returns r JOIN suppliers s ON s.id=r.supplier_id "
                "JOIN purchase_orders po ON po.id=r.purchase_order_id "
                + ("WHERE r.status=%s " if status else "")
                + "ORDER BY r.created_at DESC,r.id DESC LIMIT %s OFFSET %s",
                (status,limit,offset) if status else (limit,offset),
            ).fetchall()
        return {"items": rows, "limit": limit, "offset": offset}
    except psycopg.Error as exc:
        raise _db_error(exc) from exc


@router.post("/supplier-returns/{return_id}/submit")
def submit_supplier_return(return_id: int, request: Request):
    actor_id, actor_email, actor_role = _actor(request)
    try:
        with _connect() as conn:
            with conn.transaction():
                row = conn.execute(
                    "SELECT id,status,purchase_order_id,policy_version_id FROM supplier_returns WHERE id=%s FOR UPDATE",
                    (return_id,),
                ).fetchone()
                if not row:
                    raise HTTPException(404, "Supplier return not found")
                if row["status"] != "draft":
                    raise HTTPException(409, "Only draft supplier returns can be submitted")
                policy = _purchase_policy_for_po(conn,row["purchase_order_id"],row["policy_version_id"])
                conn.execute("UPDATE supplier_returns SET policy_version_id=%s WHERE id=%s",(policy["id"],return_id))
                updated = conn.execute(
                    "UPDATE supplier_returns SET status='submitted',updated_at=now() WHERE id=%s RETURNING id,return_number,status",
                    (return_id,),
                ).fetchone()
                conn.execute(
                    "INSERT INTO purchasing_approval_events(document_type,document_id,action,actor_user_id,actor_email,actor_role) "
                    "VALUES('supplier_return',%s,'submitted',%s,%s,%s)",
                    (return_id,actor_id,actor_email,actor_role),
                )
        return updated
    except HTTPException:
        raise
    except psycopg.Error as exc:
        raise _db_error(exc) from exc


@router.post("/supplier-returns/{return_id}/approve")
def approve_supplier_return(return_id: int, request: Request):
    actor_id, actor_email, actor_role = _actor(request)
    try:
        with _connect() as conn:
            with conn.transaction():
                row = conn.execute(
                    "SELECT id,status,purchase_order_id,created_by_user_id,approval_revision,policy_version_id "
                    "FROM supplier_returns WHERE id=%s FOR UPDATE",
                    (return_id,),
                ).fetchone()
                if not row:
                    raise HTTPException(404, "Supplier return not found")
                if row["status"] != "submitted":
                    raise HTTPException(409, "Only submitted supplier returns can be approved")
                return_value = conn.execute(
                    "SELECT COALESCE(sum(quantity*unit_cost),0) AS amount FROM supplier_return_lines WHERE supplier_return_id=%s",
                    (return_id,),
                ).fetchone()["amount"]
                policy = _purchase_policy_for_po(conn,row["purchase_order_id"],row["policy_version_id"])
                evaluation,next_stage,approval_complete = _record_purchase_approval_stage(
                    conn,policy=policy,document_type="supplier_return",document_id=return_id,
                    revision=int(row["approval_revision"]),amount=Decimal(str(return_value)),
                    creator_user_id=row["created_by_user_id"],actor_id=actor_id,
                    actor_email=actor_email,actor_role=actor_role,reason="Supplier return approval",
                )
                conn.execute("UPDATE supplier_returns SET policy_version_id=%s WHERE id=%s",(policy["id"],return_id))
                if not approval_complete:
                    return {"id":return_id,"status":"submitted","approval_pending":True,
                            "approved_stage":next_stage["sequence"],"required_stages":len(evaluation["stages"]),
                            "policy_version_id":policy["id"]}
                updated = conn.execute(
                    "UPDATE supplier_returns SET status='approved',approved_by_user_id=%s,approved_by_email=%s,updated_at=now() "
                    "WHERE id=%s RETURNING id,return_number,status",
                    (actor_id,actor_email,return_id),
                ).fetchone()
        return updated
    except HTTPException:
        raise
    except psycopg.Error as exc:
        raise _db_error(exc) from exc



def _dispatch_supplier_return_line(conn, *, return_id: int, return_number: str, establishment_id: int, line) -> list[dict]:
    """Return QC-accepted stock within the PO legal establishment, retaining GRN-line provenance."""
    grn_line_id = line["goods_receipt_line_id"]
    locations = conn.execute(
        "SELECT DISTINCT cl.location_id FROM inventory_cost_layers cl "
        "JOIN stock_locations sl ON sl.id=cl.location_id "
        "WHERE cl.goods_receipt_line_id=%s AND cl.remaining_quantity>0 "
        "AND sl.establishment_id=%s AND sl.is_active=TRUE ORDER BY cl.location_id",
        (grn_line_id,establishment_id),
    ).fetchall()
    location_ids = [row["location_id"] for row in locations]
    if not location_ids:
        raise HTTPException(409, "No remaining valued stock exists for this GRN batch")

    balances = conn.execute(
        "SELECT location_id,on_hand,reserved FROM inventory_balances "
        "WHERE variant_id=%s AND location_id=ANY(%s) ORDER BY location_id FOR UPDATE",
        (line["variant_id"], location_ids),
    ).fetchall()
    available_by_location = {
        row["location_id"]: max(Decimal("0"), row["on_hand"] - row["reserved"])
        for row in balances
    }
    layers = conn.execute(
        "SELECT id,location_id,remaining_quantity,unit_cost FROM inventory_cost_layers "
        "WHERE goods_receipt_line_id=%s AND location_id=ANY(%s) AND remaining_quantity>0 "
        "ORDER BY location_id,created_at,id FOR UPDATE",
        (grn_line_id, location_ids),
    ).fetchall()

    allocatable = sum(
        (min(
            available_by_location.get(location_id, Decimal("0")),
            sum((layer["remaining_quantity"] for layer in layers
                 if layer["location_id"] == location_id), Decimal("0")),
        ) for location_id in location_ids),
        Decimal("0"),
    )
    if allocatable < line["quantity"]:
        raise HTTPException(
            409,
            "Insufficient unreserved, valued stock from this GRN batch across warehouses",
        )

    remaining = line["quantity"]
    dispatched = []
    for layer in layers:
        if remaining <= 0:
            break
        location_id = layer["location_id"]
        location_available = available_by_location.get(location_id, Decimal("0"))
        if location_available <= 0:
            continue
        take = min(remaining, layer["remaining_quantity"], location_available)
        if take <= 0:
            continue
        movement = conn.execute(
            "INSERT INTO inventory_movements(variant_id,location_id,movement_type,quantity,reference_type,reference_id,note) "
            "VALUES(%s,%s,'adjustment',%s,'supplier_return',%s,%s) RETURNING id",
            (line["variant_id"], location_id, take, str(return_id),
             "Supplier return " + return_number),
        ).fetchone()
        conn.execute(
            "UPDATE inventory_cost_layers SET remaining_quantity=remaining_quantity-%s WHERE id=%s",
            (take, layer["id"]),
        )
        conn.execute(
            "INSERT INTO inventory_cost_allocations(issue_movement_id,cost_layer_id,quantity,unit_cost,total_cost,allocation_method) "
            "VALUES(%s,%s,%s,%s,%s,'fifo')",
            (movement["id"], layer["id"], take, layer["unit_cost"], money(take * layer["unit_cost"])),
        )
        conn.execute(
            "UPDATE inventory_balances SET on_hand=on_hand-%s,updated_at=now() "
            "WHERE variant_id=%s AND location_id=%s",
            (take, line["variant_id"], location_id),
        )
        available_by_location[location_id] -= take
        remaining -= take
        dispatched.append({"location_id": location_id, "quantity": take, "movement_id": movement["id"]})
    if remaining > 0:
        raise HTTPException(409, "Insufficient unreserved, valued stock from this GRN batch across warehouses")
    return dispatched


@router.post("/supplier-returns/{return_id}/dispatch")
def dispatch_supplier_return(return_id: int, request: Request):
    actor_id, actor_email, actor_role = _actor(request)
    try:
        with _connect() as conn:
            with conn.transaction():
                ret = conn.execute(
                    "SELECT r.id,r.return_number,r.status,sl.establishment_id "
                    "FROM supplier_returns r JOIN purchase_orders po ON po.id=r.purchase_order_id "
                    "JOIN stock_locations sl ON sl.id=po.location_id WHERE r.id=%s FOR UPDATE OF r",
                    (return_id,),
                ).fetchone()
                if not ret:
                    raise HTTPException(404, "Supplier return not found")
                if ret["status"] == "dispatched" or ret["status"] == "credited":
                    return {**ret, "idempotent_replay": True}
                if ret["status"] != "approved":
                    raise HTTPException(409, "Only approved supplier returns can be dispatched")
                lines = conn.execute(
                    "SELECT id,goods_receipt_line_id,variant_id,quantity,unit_cost FROM supplier_return_lines "
                    "WHERE supplier_return_id=%s ORDER BY id FOR UPDATE",
                    (return_id,),
                ).fetchall()
                for line in lines:
                    _dispatch_supplier_return_line(
                        conn, return_id=return_id, return_number=ret["return_number"],
                        establishment_id=int(ret["establishment_id"]), line=line,
                    )
                updated = conn.execute(
                    "UPDATE supplier_returns SET status='dispatched',updated_at=now() WHERE id=%s RETURNING id,return_number,status",
                    (return_id,),
                ).fetchone()
                conn.execute(
                    "INSERT INTO purchasing_approval_events(document_type,document_id,action,actor_user_id,actor_email,actor_role) "
                    "VALUES('supplier_return',%s,'dispatched',%s,%s,%s)",
                    (return_id,actor_id,actor_email,actor_role),
                )
        return {**updated, "idempotent_replay": False}
    except HTTPException:
        raise
    except psycopg.Error as exc:
        raise _db_error(exc) from exc


class SupplierReturnCredit(BaseModel):
    debit_note_number: str = Field(min_length=1, max_length=100)
    debit_note_date: date
    accounting_voucher_id: int = Field(gt=0)

    @field_validator("debit_note_number")
    @classmethod
    def clean_debit_note_number(cls, value):
        value = value.strip()
        if not value:
            raise ValueError("Debit note number cannot be blank")
        return value


def supplier_return_ap_debit_matches(debit_note_total, ap_debit) -> bool:
    """A supplier debit note must reduce AP by its complete posted voucher amount."""
    return money(debit_note_total) == money(ap_debit)


def supplier_return_valuation_matches(returned_value, debit_note_value) -> bool:
    """Require the posted supplier debit note to equal the returned inventory cost valuation."""
    return Decimal(str(returned_value)).quantize(Decimal("0.01")) == Decimal(str(debit_note_value)).quantize(Decimal("0.01"))


def supplier_return_gst_reversal_matches(expected, actual) -> bool:
    """Match input-tax credit reversals component-wise to the returned invoice quantity."""
    keys = ("cgst", "sgst", "igst")
    return all(money(expected.get(key, 0)) == money(actual.get(key, 0)) for key in keys)


def supplier_return_voucher_is_unallocated(existing_return_id) -> bool:
    """A posted debit-note voucher can settle only one supplier return."""
    return existing_return_id is None


def supplier_return_invoice_quantity_available(invoice_line_quantity, previously_returned, requested) -> bool:
    """Prevent cumulative returns from exceeding the quantity covered by an invoice line."""
    invoice_quantity = Decimal(str(invoice_line_quantity))
    prior_quantity = Decimal(str(previously_returned))
    requested_quantity = Decimal(str(requested))
    return invoice_quantity > 0 and prior_quantity >= 0 and requested_quantity > 0 and prior_quantity + requested_quantity <= invoice_quantity


@router.post("/supplier-returns/{return_id}/credit")
def credit_supplier_return(return_id: int, payload: SupplierReturnCredit, request: Request):
    actor_id, actor_email, actor_role = _actor(request)
    try:
        with _connect() as conn:
            with conn.transaction():
                ret = conn.execute(
                    "SELECT r.id,r.status,r.supplier_id,r.supplier_invoice_id,s.name AS supplier_name,r.accounting_voucher_id,"
                    "r.debit_note_number,r.debit_note_date "
                    "FROM supplier_returns r JOIN suppliers s ON s.id=r.supplier_id "
                    "WHERE r.id=%s FOR UPDATE OF r",
                    (return_id,),
                ).fetchone()
                if not ret:
                    raise HTTPException(404, "Supplier return not found")
                if ret["status"] == "credited":
                    if (ret["accounting_voucher_id"] == payload.accounting_voucher_id
                            and ret["debit_note_number"] == payload.debit_note_number.strip()
                            and ret["debit_note_date"] == payload.debit_note_date):
                        return {"id": return_id, "status": "credited",
                                "debit_note_number": ret["debit_note_number"],
                                "debit_note_date": ret["debit_note_date"],
                                "accounting_voucher_id": ret["accounting_voucher_id"],
                                "idempotent_replay": True}
                    raise HTTPException(409, "Supplier return has already been credited with a different debit note")
                if ret["status"] != "dispatched":
                    raise HTTPException(409, "Only dispatched supplier returns can be credited")
                voucher = conn.execute(
                    "SELECT id,voucher_type,status,party_type,party_name,total_amount "
                    "FROM accounting_vouchers WHERE id=%s FOR UPDATE",
                    (payload.accounting_voucher_id,),
                ).fetchone()
                if not voucher or voucher["status"] != "posted" or voucher["voucher_type"] != "debit_note":
                    raise HTTPException(422, "Credit confirmation must reference a posted Accounting debit-note voucher")
                if voucher["party_type"] != "supplier" or (voucher["party_name"] or "").strip().casefold() != ret["supplier_name"].strip().casefold():
                    raise HTTPException(422, "Debit-note voucher supplier does not match the return supplier")
                existing_return = conn.execute(
                    "SELECT id FROM supplier_returns WHERE accounting_voucher_id=%s AND id<>%s LIMIT 1",
                    (payload.accounting_voucher_id,return_id),
                ).fetchone()
                if not supplier_return_voucher_is_unallocated(existing_return["id"] if existing_return else None):
                    raise HTTPException(409, "This debit-note voucher has already been applied to another supplier return")
                ap_debit = conn.execute(
                    "SELECT COALESCE(sum(l.debit),0) AS amount "
                    "FROM accounting_voucher_lines l JOIN accounting_accounts a ON a.id=l.account_id "
                    "WHERE l.voucher_id=%s AND a.code='2000'",
                    (payload.accounting_voucher_id,),
                ).fetchone()["amount"]
                if not supplier_return_ap_debit_matches(voucher["total_amount"], ap_debit):
                    raise HTTPException(409, "Supplier debit-note voucher does not reduce accounts payable by its full posted amount")
                if not ret["supplier_invoice_id"]:
                    raise HTTPException(409, "Supplier return must be linked to its approved supplier invoice before GST reversal")
                expected_gst = conn.execute(
                    "SELECT count(*) AS matched_lines,"
                    "COALESCE(sum(round(sil.cgst_amount * srl.quantity / NULLIF(sil.quantity,0),2)),0) AS cgst,"
                    "COALESCE(sum(round(sil.sgst_amount * srl.quantity / NULLIF(sil.quantity,0),2)),0) AS sgst,"
                    "COALESCE(sum(round(sil.igst_amount * srl.quantity / NULLIF(sil.quantity,0),2)),0) AS igst "
                    "FROM supplier_return_lines srl "
                    "JOIN supplier_invoice_lines sil ON sil.supplier_invoice_id=%s "
                    "AND sil.goods_receipt_line_id=srl.goods_receipt_line_id "
                    "WHERE srl.supplier_return_id=%s",
                    (ret["supplier_invoice_id"], return_id),
                ).fetchone()
                return_line_count = conn.execute(
                    "SELECT count(*) AS n FROM supplier_return_lines WHERE supplier_return_id=%s",
                    (return_id,),
                ).fetchone()["n"]
                if not return_line_count or expected_gst["matched_lines"] != return_line_count:
                    raise HTTPException(409, "Every returned GRN line must match a line on the linked supplier invoice to calculate GST reversal")
                actual_gst = conn.execute(
                    "SELECT COALESCE(sum(l.credit) FILTER (WHERE a.code='1300'),0) AS cgst,"
                    "COALESCE(sum(l.credit) FILTER (WHERE a.code='1301'),0) AS sgst,"
                    "COALESCE(sum(l.credit) FILTER (WHERE a.code='1302'),0) AS igst "
                    "FROM accounting_voucher_lines l JOIN accounting_accounts a ON a.id=l.account_id "
                    "WHERE l.voucher_id=%s",
                    (payload.accounting_voucher_id,),
                ).fetchone()
                if not supplier_return_gst_reversal_matches(expected_gst, actual_gst):
                    raise HTTPException(
                        409,
                        "Supplier debit-note input GST reversal does not match the linked invoice tax apportioned to returned quantities",
                    )
                expected = conn.execute(
                    "SELECT COALESCE(sum(a.total_cost),0) AS returned_value "
                    "FROM inventory_movements m JOIN inventory_cost_allocations a ON a.issue_movement_id=m.id "
                    "WHERE m.reference_type='supplier_return' AND m.reference_id=%s AND m.movement_type='adjustment'",
                    (str(return_id),),
                ).fetchone()["returned_value"]
                if Decimal(str(expected)).quantize(Decimal("0.01")) <= 0:
                    raise HTTPException(409, "No dispatched inventory cost valuation exists for this supplier return")
                credited_inventory_value = conn.execute(
                    "SELECT COALESCE(sum(l.credit),0) AS amount "
                    "FROM accounting_voucher_lines l JOIN accounting_accounts a ON a.id=l.account_id "
                    "WHERE l.voucher_id=%s AND a.code = ANY(%s)",
                    (payload.accounting_voucher_id, ["1200", "2050"]),
                ).fetchone()["amount"]
                if not supplier_return_valuation_matches(expected, credited_inventory_value):
                    raise HTTPException(
                        409,
                        f"Debit-note inventory/GRNI credit {credited_inventory_value} does not match returned inventory valuation {expected}; GST reversal is reconciled separately",
                    )
                updated = conn.execute(
                    "UPDATE supplier_returns SET status='credited',debit_note_number=%s,debit_note_date=%s,accounting_voucher_id=%s,updated_at=now() "
                    "WHERE id=%s RETURNING id,return_number,status,debit_note_number,debit_note_date,accounting_voucher_id",
                    (payload.debit_note_number.strip(),payload.debit_note_date,payload.accounting_voucher_id,return_id),
                ).fetchone()
                conn.execute(
                    "INSERT INTO purchasing_approval_events(document_type,document_id,action,actor_user_id,actor_email,actor_role) "
                    "VALUES('supplier_return',%s,'credited',%s,%s,%s)",
                    (return_id,actor_id,actor_email,actor_role),
                )
        return {**updated, "idempotent_replay": False}
    except HTTPException:
        raise
    except psycopg.Error as exc:
        raise _db_error(exc) from exc


class RFQAwardInput(BaseModel):
    quotation_id: int = Field(gt=0)


@router.post("/rfqs/{rfq_id}/award", status_code=201)
def award_rfq_quotation(rfq_id: int, payload: RFQAwardInput, request: Request):
    """Select one valid RFQ quotation and create a linked draft PO atomically.

    The PO remains draft and must pass the existing PO approval workflow before
    it can be ordered. Quoted freight, discount, tax and terms are retained in
    its notes because the current purchase_orders schema has no dedicated
    commercial-terms columns.
    """
    actor_id, actor_email, actor_role = _actor(request)
    if actor_role not in {"owner", "admin"}:
        raise HTTPException(403, "Owner or admin permission is required to award an RFQ")

    try:
        with _connect() as conn:
            with conn.transaction():
                rfq = conn.execute(
                    "SELECT id,rfq_number,requisition_id,status FROM purchase_rfqs WHERE id=%s FOR UPDATE",
                    (rfq_id,),
                ).fetchone()
                if not rfq:
                    raise HTTPException(404, "RFQ not found")
                if rfq["status"] != "evaluation":
                    raise HTTPException(409, "Only RFQs under evaluation can be awarded")

                quotation = conn.execute(
                    "SELECT id,quotation_number,rfq_id,supplier_id,status,valid_until,lead_time_days,"
                    "freight_amount,discount_amount,tax_amount,payment_terms,delivery_terms "
                    "FROM supplier_quotations WHERE id=%s AND rfq_id=%s FOR UPDATE",
                    (payload.quotation_id, rfq_id),
                ).fetchone()
                if not quotation:
                    raise HTTPException(404, "Quotation not found for this RFQ")
                if quotation["status"] not in {"received", "under_review"}:
                    raise HTTPException(409, "Only received or under-review quotations can be awarded")
                if quotation["valid_until"] and quotation["valid_until"] < date.today():
                    raise HTTPException(409, "The selected quotation has expired")

                invited = conn.execute(
                    "SELECT id FROM purchase_rfq_suppliers WHERE rfq_id=%s AND supplier_id=%s FOR SHARE",
                    (rfq_id, quotation["supplier_id"]),
                ).fetchone()
                if not invited:
                    raise HTTPException(409, "The quoted supplier is not an invited RFQ supplier")

                req = conn.execute(
                    "SELECT id,location_id,status FROM purchase_requisitions WHERE id=%s FOR UPDATE",
                    (rfq["requisition_id"],),
                ).fetchone()
                if not req:
                    raise HTTPException(409, "The RFQ requisition no longer exists")
                if req["status"] not in {"approved", "partially_ordered"}:
                    raise HTTPException(409, "The requisition is not available for ordering")

                lines = conn.execute(
                    "SELECT ql.variant_id,ql.quantity,ql.unit_price,ql.hsn_sac,ql.gst_rate,"
                    "rl.quantity AS rfq_quantity "
                    "FROM supplier_quotation_lines ql "
                    "JOIN purchase_rfq_lines rl ON rl.id=ql.rfq_line_id "
                    "WHERE ql.quotation_id=%s AND rl.rfq_id=%s ORDER BY ql.variant_id FOR SHARE",
                    (quotation["id"], rfq_id),
                ).fetchall()
                rfq_lines = conn.execute(
                    "SELECT variant_id,quantity FROM purchase_rfq_lines WHERE rfq_id=%s ORDER BY variant_id",
                    (rfq_id,),
                ).fetchall()
                if not lines or len(lines) != len(rfq_lines):
                    raise HTTPException(409, "The quotation does not cover every RFQ line")
                quoted = {int(line["variant_id"]): line for line in lines}
                expected = {int(line["variant_id"]): line["quantity"] for line in rfq_lines}
                if set(quoted) != set(expected) or any(quoted[key]["quantity"] != expected[key] for key in expected):
                    raise HTTPException(409, "The quotation quantities no longer match the RFQ")

                # A provenance row is the durable one-award-per-quotation link.
                already_awarded = conn.execute(
                    "SELECT po.purchase_number FROM purchase_order_provenance pop "
                    "JOIN purchase_orders po ON po.id=pop.purchase_order_id "
                    "WHERE pop.awarded_quotation_id=%s FOR SHARE",
                    (quotation["id"],),
                ).fetchone()
                if already_awarded:
                    raise HTTPException(409, "This quotation has already been converted to a purchase order")

                subtotal = sum((line["quantity"] * line["unit_price"] for line in lines), Decimal("0"))
                terms = [
                    f"RFQ {rfq['rfq_number']} awarded from quotation {quotation['quotation_number']}.",
                    f"Quoted freight: {quotation['freight_amount']}; discount: {quotation['discount_amount']}; tax: {quotation['tax_amount']}.",
                ]
                if quotation["lead_time_days"] is not None:
                    terms.append(f"Quoted lead time: {quotation['lead_time_days']} days.")
                if quotation["payment_terms"]:
                    terms.append(f"Payment terms: {quotation['payment_terms']}")
                if quotation["delivery_terms"]:
                    terms.append(f"Delivery terms: {quotation['delivery_terms']}")
                notes = "\\n".join(terms)
                po_number = "PO-" + uuid.uuid4().hex[:12].upper()
                po = conn.execute(
                    "INSERT INTO purchase_orders(purchase_number,supplier_id,location_id,status,subtotal,notes) "
                    "VALUES(%s,%s,%s,'draft',%s,%s) "
                    "RETURNING id,purchase_number,supplier_id,location_id,status,subtotal,notes,created_at",
                    (po_number, quotation["supplier_id"], req["location_id"], subtotal, notes),
                ).fetchone()
                for line in lines:
                    conn.execute(
                        "INSERT INTO purchase_order_lines(purchase_order_id,variant_id,quantity_ordered,unit_cost) "
                        "VALUES(%s,%s,%s,%s)",
                        (po["id"], line["variant_id"], line["quantity"], line["unit_price"]),
                    )
                conn.execute(
                    "INSERT INTO purchase_order_provenance(purchase_order_id,requisition_id,awarded_quotation_id,"
                    "created_by_user_id,created_by_email) VALUES(%s,%s,%s,%s,%s)",
                    (po["id"], req["id"], quotation["id"], actor_id, actor_email),
                )
                conn.execute(
                    "UPDATE supplier_quotations SET status=CASE WHEN id=%s THEN 'selected' ELSE 'rejected' END "
                    "WHERE rfq_id=%s AND status IN ('received','under_review')",
                    (quotation["id"], rfq_id),
                )
                conn.execute(
                    "UPDATE purchase_rfqs SET status='awarded',updated_at=now() WHERE id=%s",
                    (rfq_id,),
                )
                conn.execute(
                    "UPDATE purchase_requisitions SET status='ordered',updated_at=now() WHERE id=%s",
                    (req["id"],),
                )
                conn.execute(
                    "INSERT INTO purchasing_approval_events(document_type,document_id,action,actor_user_id,"
                    "actor_email,actor_role,reason) VALUES('quotation',%s,'approved',%s,%s,%s,%s)",
                    (rfq_id, actor_id, actor_email, actor_role,
                     f"Awarded quotation {quotation['quotation_number']} and created draft PO {po_number}"),
                )
        return {**po, "rfq_id": rfq_id, "quotation_id": payload.quotation_id,
                "approval_required": True}
    except HTTPException:
        raise
    except psycopg.Error as exc:
        raise _db_error(exc) from exc
