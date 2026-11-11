"""Admin-only unified identity register and reviewed link-request workflow."""
from datetime import datetime, timedelta, timezone

import psycopg
from fastapi import APIRouter, HTTPException, Query, Request
from psycopg.rows import dict_row
from pydantic import BaseModel, Field

from app.core.config import settings
from app.services.identity import IdentityService

router = APIRouter(prefix="/identity", tags=["unified identity"])


def _connect():
    if not settings.database_url:
        raise HTTPException(503, "Identity database is not configured")
    try:
        return psycopg.connect(settings.database_url, row_factory=dict_row, connect_timeout=3)
    except psycopg.Error as exc:
        raise HTTPException(503, "Identity storage is unavailable") from exc


def _admin(request: Request):
    if not getattr(request.state, "user_id", None) or getattr(request.state, "role", "") not in {"super_admin", "admin"}:
        raise HTTPException(403, "Identity administration permission is required")


class LinkRequestIn(BaseModel):
    target_party_id: int = Field(gt=0)
    request_type: str = Field(pattern=r"^(claim_existing_identity|link_profile|organisation_relationship)$")
    requested_profile_type: str | None = Field(default=None, max_length=40)
    requested_source_id: str | None = Field(default=None, max_length=80)
    idempotency_key: str = Field(min_length=8, max_length=120)
    reason: str = Field(min_length=5, max_length=500)


class ReviewIn(BaseModel):
    decision: str = Field(pattern=r"^(approve|reject)$")
    proof_verified: bool = False
    proof_method: str | None = Field(default=None, max_length=40)
    reason: str = Field(min_length=5, max_length=500)


@router.get("")
def identity_register(request: Request, search: str | None = Query(default=None, max_length=120), party_type: str | None = None, limit: int = Query(default=50, ge=1, le=200), offset: int = Query(default=0, ge=0)):
    _admin(request)
    if party_type not in {None, "individual", "organisation"}:
        raise HTTPException(422, "Invalid party type")
    clauses = ["p.status <> 'merged'"]
    params = []
    if party_type:
        clauses.append("p.party_type=%s"); params.append(party_type)
    if search and search.strip():
        term = "%" + search.strip() + "%"
        clauses.append("(p.sbid ILIKE %s OR p.display_name ILIKE %s)")
        params.extend([term, term])
    where = " AND ".join(clauses)
    try:
        with _connect() as conn:
            rows = conn.execute(
                "SELECT p.id,p.sbid,p.party_type,p.display_name,p.status,p.created_at,"
                "(SELECT jsonb_agg(jsonb_build_object('profile_type',ip.profile_type,'profile_id',COALESCE(ip.customer_account_id,ip.crm_customer_id,ip.employee_id,ip.supplier_id),'status',ip.status)) FROM identity_profiles ip WHERE ip.party_id=p.id) AS profiles,"
                "(SELECT count(*) FROM identity_auth_accounts aa WHERE aa.party_id=p.id AND aa.status='active') AS active_login_count,"
                "(SELECT count(*) FROM identity_relationships ir WHERE (ir.from_party_id=p.id OR ir.to_party_id=p.id) AND ir.status='active') AS relationship_count "
                "FROM identity_parties p WHERE " + where + " ORDER BY p.created_at DESC LIMIT %s OFFSET %s",
                (*params, limit, offset),
            ).fetchall()
            total = conn.execute("SELECT count(*) AS total FROM identity_parties p WHERE " + where, params).fetchone()["total"]
        return {"items": rows, "total": total, "limit": limit, "offset": offset}
    except psycopg.Error as exc:
        raise HTTPException(503, "Unable to load identity register") from exc


@router.get("/parties/{party_id}")
def identity_detail(party_id: int, request: Request):
    _admin(request)
    try:
        with _connect() as conn:
            party = conn.execute("SELECT id,sbid,party_type,display_name,status,created_at,updated_at FROM identity_parties WHERE id=%s", (party_id,)).fetchone()
            if party is None:
                raise HTTPException(404, "Identity not found")
            profiles = conn.execute("SELECT id,profile_type,customer_account_id,crm_customer_id,employee_id,supplier_id,status,valid_from,valid_to FROM identity_profiles WHERE party_id=%s ORDER BY created_at", (party_id,)).fetchall()
            contacts = conn.execute("SELECT id,contact_type,CASE WHEN contact_type='email' THEN left(normalized_value,2)||'***@'||split_part(normalized_value,'@',2) ELSE left(normalized_value,3)||'******'||right(normalized_value,2) END AS masked_value,verification_status,is_primary,created_at FROM identity_contacts WHERE party_id=%s AND valid_to IS NULL ORDER BY created_at DESC", (party_id,)).fetchall()
            accounts = conn.execute("SELECT id,account_type,status,link_method,linked_at FROM identity_auth_accounts WHERE party_id=%s ORDER BY linked_at DESC", (party_id,)).fetchall()
            relationships = conn.execute("SELECT r.id,r.relationship_type,r.status,r.scope,r.valid_from,r.valid_to,fp.sbid AS from_sbid,fp.display_name AS from_name,tp.sbid AS to_sbid,tp.display_name AS to_name FROM identity_relationships r JOIN identity_parties fp ON fp.id=r.from_party_id JOIN identity_parties tp ON tp.id=r.to_party_id WHERE r.from_party_id=%s OR r.to_party_id=%s ORDER BY r.created_at DESC", (party_id, party_id)).fetchall()
            events = conn.execute("SELECT id,event_type,reason,event_data,created_at FROM identity_events WHERE party_id=%s ORDER BY created_at DESC,id DESC LIMIT 100", (party_id,)).fetchall()
        return {"party": party, "profiles": profiles, "contacts": contacts, "auth_accounts": accounts, "relationships": relationships, "events": events}
    except HTTPException:
        raise
    except psycopg.Error as exc:
        raise HTTPException(503, "Unable to load identity details") from exc


@router.get("/review-queue/requests")
def review_queue(request: Request, limit: int = Query(default=100, ge=1, le=300)):
    _admin(request)
    try:
        with _connect() as conn:
            rows = conn.execute(
                "SELECT r.id,r.request_type,r.status,r.requested_profile_type,r.requested_source_id,r.proof_method,r.proof_verified_at,r.reason,r.created_at,"
                "sp.sbid AS requester_sbid,tp.sbid AS target_sbid FROM identity_link_requests r "
                "LEFT JOIN identity_parties sp ON sp.id=r.requester_party_id LEFT JOIN identity_parties tp ON tp.id=r.target_party_id "
                "WHERE r.status IN ('pending','proof_required') ORDER BY r.created_at LIMIT %s", (limit,)
            ).fetchall()
        return {"items": rows}
    except psycopg.Error as exc:
        raise HTTPException(503, "Unable to load identity review queue") from exc


@router.post("/link-requests", status_code=201)
def create_link_request(payload: LinkRequestIn, request: Request):
    _admin(request)
    if payload.request_type == "link_profile" and (not payload.requested_profile_type or not payload.requested_source_id or not payload.requested_source_id.isdigit()):
        raise HTTPException(422, "Profile type and numeric source ID are required")
    try:
        with _connect() as conn:
            with conn.transaction():
                row = conn.execute(
                    "INSERT INTO identity_link_requests(idempotency_key,requester_party_id,target_party_id,request_type,status,requested_profile_type,requested_source_id,expires_at,request_context) "
                    "VALUES(%s,(SELECT party_id FROM identity_auth_accounts WHERE app_user_id=%s AND status='active'),%s,%s,'proof_required',%s,%s,%s,jsonb_build_object('reason',%s)) "
                    "ON CONFLICT(idempotency_key) DO NOTHING RETURNING id,status,created_at",
                    (payload.idempotency_key, request.state.user_id, payload.target_party_id, payload.request_type, payload.requested_profile_type, payload.requested_source_id, datetime.now(timezone.utc)+timedelta(days=7), payload.reason),
                ).fetchone()
                if row is None:
                    raise HTTPException(409, "This request has already been submitted")
                IdentityService(conn)._event(party_id=payload.target_party_id,event_type="link_requested",event_data={"request_id":row["id"],"request_type":payload.request_type},actor_user_id=request.state.user_id,reason=payload.reason)
        return {"request": row}
    except HTTPException:
        raise
    except psycopg.Error as exc:
        raise HTTPException(503, "Unable to create identity link request") from exc


@router.post("/review-queue/requests/{request_id}")
def review_link_request(request_id: int, payload: ReviewIn, request: Request):
    _admin(request)
    if payload.decision == "approve" and (not payload.proof_verified or not payload.proof_method):
        raise HTTPException(422, "Approval requires recorded proof verification and its method")
    try:
        with _connect() as conn:
            with conn.transaction():
                item = conn.execute("SELECT * FROM identity_link_requests WHERE id=%s FOR UPDATE", (request_id,)).fetchone()
                if item is None or item["status"] not in {"pending", "proof_required"}:
                    raise HTTPException(409, "Request is no longer reviewable")
                if item["expires_at"] <= datetime.now(timezone.utc):
                    conn.execute("UPDATE identity_link_requests SET status='expired',reviewed_at=now(),updated_at=now() WHERE id=%s", (request_id,))
                    raise HTTPException(410, "Identity request has expired")
                if payload.decision == "approve":
                    if item["request_type"] == "link_profile":
                        IdentityService(conn).link_profile(party_id=item["target_party_id"],profile_type=item["requested_profile_type"],source_id=int(item["requested_source_id"]),link_method="admin_verified",actor_user_id=request.state.user_id,reason=payload.reason)
                    else:
                        raise HTTPException(422, "This request type requires its dedicated verified workflow")
                    status = "approved"
                    conn.execute("UPDATE identity_link_requests SET status=%s,proof_method=%s,proof_verified_at=now(),reviewer_user_id=%s,review_reason=%s,reviewed_at=now(),updated_at=now() WHERE id=%s", (status,payload.proof_method,request.state.user_id,payload.reason,request_id))
                    event = "link_approved"
                else:
                    status = "rejected"
                    conn.execute("UPDATE identity_link_requests SET status=%s,reviewer_user_id=%s,review_reason=%s,reviewed_at=now(),updated_at=now() WHERE id=%s", (status,request.state.user_id,payload.reason,request_id))
                    event = "link_rejected"
                IdentityService(conn)._event(party_id=item["target_party_id"],event_type=event,event_data={"request_id":request_id,"status":status},actor_user_id=request.state.user_id,reason=payload.reason)
        return {"id": request_id, "status": status}
    except HTTPException:
        raise
    except psycopg.Error as exc:
        if getattr(exc, "sqlstate", None) == "23505":
            raise HTTPException(409, "That profile is already linked to an identity") from exc
        raise HTTPException(503, "Unable to review identity request") from exc
