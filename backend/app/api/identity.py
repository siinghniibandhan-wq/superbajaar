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


def _merge_claimed_party(conn, source_party_id: int, target_party_id: int, actor_user_id: int, reason: str, proof_method: str):
    """Merge a verified claimant into the canonical party without losing linked history."""
    if source_party_id == target_party_id:
        raise HTTPException(409, "The requesting account is already linked to that identity")
    rows = conn.execute(
        "SELECT id,sbid,party_type,status FROM identity_parties WHERE id IN (%s,%s) ORDER BY id FOR UPDATE",
        (source_party_id, target_party_id),
    ).fetchall()
    parties = {row["id"]: row for row in rows}
    source, target = parties.get(source_party_id), parties.get(target_party_id)
    if not source or not target or source["status"] != "active" or target["status"] != "active":
        raise HTTPException(409, "Both identities must be active")
    if source["party_type"] != target["party_type"]:
        raise HTTPException(409, "Individual and organisation identities cannot be merged")
    if conn.execute(
        "SELECT 1 FROM identity_profiles a JOIN identity_profiles b ON b.party_id=%s AND b.profile_type=a.profile_type WHERE a.party_id=%s LIMIT 1",
        (target_party_id, source_party_id),
    ).fetchone():
        raise HTTPException(409, "Both identities contain the same profile type; manual profile resolution is required")
    if conn.execute(
        "SELECT 1 FROM identity_contacts a JOIN identity_contacts b ON b.party_id=%s AND b.contact_type=a.contact_type AND b.normalized_value=a.normalized_value AND b.valid_to IS NULL WHERE a.party_id=%s AND a.valid_to IS NULL LIMIT 1",
        (target_party_id, source_party_id),
    ).fetchone():
        raise HTTPException(409, "Both identities contain the same contact; resolve the contact conflict before merging")
    if conn.execute(
        "SELECT 1 FROM identity_relationships WHERE (from_party_id=%s AND to_party_id=%s) OR (from_party_id=%s AND to_party_id=%s) LIMIT 1",
        (source_party_id,target_party_id,target_party_id,source_party_id),
    ).fetchone():
        raise HTTPException(409, "A direct relationship would collapse during this merge")
    if conn.execute(
        "SELECT 1 FROM identity_referral_links WHERE (referrer_party_id=%s AND referred_party_id=%s) OR (referrer_party_id=%s AND referred_party_id=%s) LIMIT 1",
        (source_party_id,target_party_id,target_party_id,source_party_id),
    ).fetchone():
        raise HTTPException(409, "A referral would become a self-referral")
    conn.execute("UPDATE identity_profiles SET party_id=%s,updated_at=now() WHERE party_id=%s", (target_party_id,source_party_id))
    conn.execute("UPDATE identity_auth_accounts SET party_id=%s WHERE party_id=%s", (target_party_id,source_party_id))
    conn.execute("UPDATE identity_contacts SET party_id=%s,updated_at=now() WHERE party_id=%s", (target_party_id,source_party_id))
    conn.execute("UPDATE identity_relationships SET from_party_id=%s,updated_at=now() WHERE from_party_id=%s", (target_party_id,source_party_id))
    conn.execute("UPDATE identity_relationships SET to_party_id=%s,updated_at=now() WHERE to_party_id=%s", (target_party_id,source_party_id))
    conn.execute("UPDATE identity_loyalty_accounts SET party_id=%s WHERE party_id=%s", (target_party_id,source_party_id))
    conn.execute("UPDATE identity_referral_links SET referrer_party_id=%s WHERE referrer_party_id=%s", (target_party_id,source_party_id))
    conn.execute("UPDATE identity_referral_links SET referred_party_id=%s WHERE referred_party_id=%s", (target_party_id,source_party_id))
    conn.execute(
        "INSERT INTO identity_aliases(alias_sbid,source_party_id,canonical_party_id,merge_reason,merged_by_user_id) VALUES(%s,%s,%s,%s,%s)",
        (source["sbid"],source_party_id,target_party_id,reason,actor_user_id),
    )
    conn.execute(
        "UPDATE identity_parties SET status='merged',merged_into_party_id=%s,updated_at=now() WHERE id=%s",
        (target_party_id,source_party_id),
    )
    IdentityService(conn)._event(
        party_id=target_party_id,event_type="party_merged",
        event_data={"source_party_id":source_party_id,"source_sbid":source["sbid"],"canonical_sbid":target["sbid"],"proof_method":proof_method},
        actor_user_id=actor_user_id,reason=reason,
    )
    return {"source_sbid": source["sbid"], "canonical_sbid": target["sbid"]}


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
    relationship_type: str | None = Field(default=None, max_length=40)
    relationship_scope: dict = Field(default_factory=dict)


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
            loyalty = conn.execute("SELECT l.id,l.loyalty_account_id,left(a.card_number,3)||'******'||right(a.card_number,2) AS masked_card_number,l.link_method,l.linked_at FROM identity_loyalty_accounts l JOIN loyalty_accounts a ON a.id=l.loyalty_account_id WHERE l.party_id=%s ORDER BY l.linked_at DESC", (party_id,)).fetchall()
            referrals = conn.execute("SELECT r.id,r.referral_id,r.referrer_party_id,r.referred_party_id,r.linked_at,fp.sbid AS referrer_sbid,tp.sbid AS referred_sbid FROM identity_referral_links r JOIN identity_parties fp ON fp.id=r.referrer_party_id JOIN identity_parties tp ON tp.id=r.referred_party_id WHERE r.referrer_party_id=%s OR r.referred_party_id=%s ORDER BY r.linked_at DESC", (party_id,party_id)).fetchall()
            relationships = conn.execute("SELECT r.id,r.relationship_type,r.status,r.scope,r.valid_from,r.valid_to,fp.sbid AS from_sbid,fp.display_name AS from_name,tp.sbid AS to_sbid,tp.display_name AS to_name FROM identity_relationships r JOIN identity_parties fp ON fp.id=r.from_party_id JOIN identity_parties tp ON tp.id=r.to_party_id WHERE r.from_party_id=%s OR r.to_party_id=%s ORDER BY r.created_at DESC", (party_id, party_id)).fetchall()
            events = conn.execute("SELECT id,event_type,reason,event_data,created_at FROM identity_events WHERE party_id=%s ORDER BY created_at DESC,id DESC LIMIT 100", (party_id,)).fetchall()
        return {"party": party, "profiles": profiles, "contacts": contacts, "auth_accounts": accounts, "loyalty_accounts": loyalty, "referrals": referrals, "relationships": relationships, "events": events}
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
    if payload.request_type == "organisation_relationship" and payload.relationship_type not in {"representative", "owner", "director", "authorised_vendor_user", "accountant", "business_partner"}:
        raise HTTPException(422, "A supported organisation relationship type is required")
    try:
        with _connect() as conn:
            with conn.transaction():
                row = conn.execute(
                    "INSERT INTO identity_link_requests(idempotency_key,requester_party_id,target_party_id,request_type,status,requested_profile_type,requested_source_id,expires_at,request_context) "
                    "VALUES(%s,(SELECT party_id FROM identity_auth_accounts WHERE app_user_id=%s AND status='active'),%s,%s,'proof_required',%s,%s,%s,jsonb_build_object('reason',%s,'relationship_type',%s,'relationship_scope',%s::jsonb)) "
                    "ON CONFLICT(idempotency_key) DO NOTHING RETURNING id,status,created_at",
                    (payload.idempotency_key, request.state.user_id, payload.target_party_id, payload.request_type, payload.requested_profile_type, payload.requested_source_id, datetime.now(timezone.utc)+timedelta(days=7), payload.reason, payload.relationship_type, __import__("json").dumps(payload.relationship_scope)),
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
            # Persist expiry in its own committed transaction. Raising inside the
            # review transaction would roll this status change back.
            expired = conn.execute(
                "UPDATE identity_link_requests SET status='expired',reviewed_at=now(),updated_at=now() "
                "WHERE id=%s AND status IN ('pending','proof_required') AND expires_at<=now() RETURNING id",
                (request_id,),
            ).fetchone()
            if expired:
                return {"id": request_id, "status": "expired"}
            with conn.transaction():
                item = conn.execute("SELECT * FROM identity_link_requests WHERE id=%s FOR UPDATE", (request_id,)).fetchone()
                if item is None or item["status"] not in {"pending", "proof_required"}:
                    raise HTTPException(409, "Request is no longer reviewable")
                if item["expires_at"] <= datetime.now(timezone.utc):
                    # A concurrent expiry can only be reported; commit the status
                    # update after leaving this transaction.
                    raise HTTPException(410, "Identity request has expired; refresh the review queue")
                if payload.decision == "approve":
                    service = IdentityService(conn)
                    if item["request_type"] == "link_profile":
                        service.link_profile(
                            party_id=item["target_party_id"],
                            profile_type=item["requested_profile_type"],
                            source_id=int(item["requested_source_id"]),
                            link_method="admin_verified",
                            actor_user_id=request.state.user_id,
                            reason=payload.reason,
                        )
                    elif item["request_type"] == "organisation_relationship":
                        context = item["request_context"] or {}
                        relation_type = context.get("relationship_type")
                        scope = context.get("relationship_scope") or {}
                        if relation_type not in {"representative", "owner", "director", "authorised_vendor_user", "accountant", "business_partner"}:
                            raise HTTPException(422, "The requested relationship type is invalid")
                        if not item["requester_party_id"]:
                            raise HTTPException(409, "The requesting identity must be resolved before approval")
                        parties = conn.execute(
                            "SELECT id,party_type,status FROM identity_parties WHERE id IN (%s,%s) ORDER BY id FOR UPDATE",
                            (item["requester_party_id"], item["target_party_id"]),
                        ).fetchall()
                        by_id = {p["id"]: p for p in parties}
                        requester = by_id.get(item["requester_party_id"])
                        target = by_id.get(item["target_party_id"])
                        if not requester or not target or requester["status"] != "active" or target["status"] != "active":
                            raise HTTPException(409, "Both identities must be active")
                        if target["party_type"] != "organisation" or requester["party_type"] != "individual":
                            raise HTTPException(409, "An organisation relationship must connect an individual to an organisation")
                        service.create_relationship(
                            from_party_id=requester["id"],
                            to_party_id=target["id"],
                            relationship_type=relation_type,
                            scope=scope,
                            actor_user_id=request.state.user_id,
                            reason=payload.reason,
                        )
                        conn.execute(
                            "UPDATE identity_relationships SET approved_by_user_id=%s WHERE from_party_id=%s AND to_party_id=%s AND relationship_type=%s AND status='active'",
                            (request.state.user_id, requester["id"], target["id"], relation_type),
                        )
                    elif item["request_type"] == "claim_existing_identity":
                        if not item["requester_party_id"] or not item["target_party_id"]:
                            raise HTTPException(409, "The requesting and claimed identities must both be resolved")
                        _merge_claimed_party(
                            conn, item["requester_party_id"], item["target_party_id"],
                            request.state.user_id, payload.reason, payload.proof_method,
                        )
                    else:
                        raise HTTPException(422, "This request type is not supported by the review workflow")
                    status = "approved"
                    conn.execute(
                        "UPDATE identity_link_requests SET status=%s,proof_method=%s,proof_verified_at=now(),reviewer_user_id=%s,review_reason=%s,reviewed_at=now(),updated_at=now() WHERE id=%s",
                        (status,payload.proof_method,request.state.user_id,payload.reason,request_id),
                    )
                    event = "link_approved"
                else:
                    status = "rejected"
                    conn.execute(
                        "UPDATE identity_link_requests SET status=%s,reviewer_user_id=%s,review_reason=%s,reviewed_at=now(),updated_at=now() WHERE id=%s",
                        (status,request.state.user_id,payload.reason,request_id),
                    )
                    event = "link_rejected"
                IdentityService(conn)._event(
                    party_id=item["target_party_id"], event_type=event,
                    event_data={"request_id":request_id,"status":status},
                    actor_user_id=request.state.user_id, reason=payload.reason,
                )
        return {"id": request_id, "status": status}
    except HTTPException:
        raise
    except psycopg.Error as exc:
        if getattr(exc, "sqlstate", None) == "23505":
            raise HTTPException(409, "That profile or relationship is already linked") from exc
        raise HTTPException(503, "Unable to review identity request") from exc


class LoyaltyLinkIn(BaseModel):
    customer_account_id: int = Field(gt=0)
    loyalty_account_id: int = Field(gt=0)
    verification_confirmed: bool
    proof_method: str = Field(min_length=3, max_length=40)
    reason: str = Field(min_length=5, max_length=500)


@router.post("/loyalty-links", status_code=201)
def link_loyalty_account(payload: LoyaltyLinkIn, request: Request):
    _admin(request)
    if not payload.verification_confirmed:
        raise HTTPException(422, "Verify ownership of the existing loyalty account before linking")
    try:
        with _connect() as conn:
            with conn.transaction():
                party = conn.execute(
                    "SELECT p.id FROM identity_profiles ip JOIN identity_parties p ON p.id=ip.party_id "
                    "WHERE ip.profile_type='customer_account' AND ip.customer_account_id=%s AND ip.status='active' AND p.status='active' FOR UPDATE OF p",
                    (payload.customer_account_id,),
                ).fetchone()
                if party is None:
                    raise HTTPException(409, "Customer account has no active SBID; resolve its identity first")
                loyalty = conn.execute("SELECT id FROM loyalty_accounts WHERE id=%s", (payload.loyalty_account_id,)).fetchone()
                if loyalty is None:
                    raise HTTPException(404, "Loyalty account not found")
                row = conn.execute(
                    "INSERT INTO identity_loyalty_accounts(party_id,loyalty_account_id,link_method,linked_by_user_id) VALUES(%s,%s,'admin_verified',%s) RETURNING id,party_id,loyalty_account_id,linked_at",
                    (party["id"], payload.loyalty_account_id, request.state.user_id),
                ).fetchone()
                IdentityService(conn)._event(party_id=party["id"],event_type="profile_linked",event_data={"profile_type":"loyalty_account","loyalty_account_id":payload.loyalty_account_id,"proof_method":payload.proof_method},actor_user_id=request.state.user_id,reason=payload.reason)
        return {"link": row}
    except HTTPException:
        raise
    except psycopg.Error as exc:
        if getattr(exc, "sqlstate", None) == "23505":
            raise HTTPException(409, "This loyalty account is already linked") from exc
        raise HTTPException(503, "Unable to link loyalty account") from exc


@router.post("/referral-links/{referral_id}", status_code=201)
def link_referral_parties(referral_id: int, request: Request):
    _admin(request)
    try:
        with _connect() as conn:
            with conn.transaction():
                referral = conn.execute(
                    "SELECT r.id,r.referrer_customer_id,r.referred_customer_id FROM customer_referrals r WHERE r.id=%s FOR UPDATE",
                    (referral_id,),
                ).fetchone()
                if referral is None:
                    raise HTTPException(404, "Referral record not found")
                parties = conn.execute(
                    "SELECT customer_account_id,party_id FROM identity_profiles WHERE profile_type='customer_account' AND status='active' AND customer_account_id IN (%s,%s) FOR UPDATE",
                    (referral["referrer_customer_id"], referral["referred_customer_id"]),
                ).fetchall()
                mapping = {row["customer_account_id"]: row["party_id"] for row in parties}
                if referral["referrer_customer_id"] not in mapping or referral["referred_customer_id"] not in mapping:
                    raise HTTPException(409, "Both referral customer accounts must have verified SBID profile links first")
                row = conn.execute(
                    "INSERT INTO identity_referral_links(referral_id,referrer_party_id,referred_party_id) VALUES(%s,%s,%s) RETURNING id,referral_id,referrer_party_id,referred_party_id,linked_at",
                    (referral_id,mapping[referral["referrer_customer_id"]],mapping[referral["referred_customer_id"]]),
                ).fetchone()
                IdentityService(conn)._event(party_id=mapping[referral["referrer_customer_id"]],event_type="profile_linked",event_data={"profile_type":"referral","referral_id":referral_id,"referred_party_id":mapping[referral["referred_customer_id"]]},actor_user_id=request.state.user_id,reason="Referral SBID association created from existing customer account links")
        return {"link": row}
    except HTTPException:
        raise
    except psycopg.Error as exc:
        if getattr(exc, "sqlstate", None) == "23505":
            raise HTTPException(409, "This referral is already linked") from exc
        raise HTTPException(503, "Unable to link referral identities") from exc


class MergeIn(BaseModel):
    target_party_id: int = Field(gt=0)
    proof_verified: bool
    proof_method: str = Field(min_length=3, max_length=40)
    reason: str = Field(min_length=5, max_length=500)


@router.post("/parties/{source_party_id}/merge")
def merge_parties(source_party_id: int, payload: MergeIn, request: Request):
    _admin(request)
    if not payload.proof_verified:
        raise HTTPException(422, "Merge requires documented proof verification")
    if source_party_id == payload.target_party_id:
        raise HTTPException(422, "Source and target identities must differ")
    try:
        with _connect() as conn:
            with conn.transaction():
                rows = conn.execute(
                    "SELECT id,sbid,party_type,status FROM identity_parties WHERE id IN (%s,%s) ORDER BY id FOR UPDATE",
                    (source_party_id,payload.target_party_id),
                ).fetchall()
                parties = {row["id"]: row for row in rows}
                source, target = parties.get(source_party_id), parties.get(payload.target_party_id)
                if not source or not target or source["status"] != "active" or target["status"] != "active":
                    raise HTTPException(409, "Both identities must exist and be active")
                if source["party_type"] != target["party_type"]:
                    raise HTTPException(409, "Individual and organisation identities cannot be merged")
                conflict = conn.execute(
                    "SELECT 1 FROM identity_profiles a JOIN identity_profiles b ON b.party_id=%s AND b.profile_type=a.profile_type "
                    "WHERE a.party_id=%s LIMIT 1", (target_party_id,source_party_id),
                ).fetchone()
                if conflict:
                    raise HTTPException(409, "Both identities contain the same profile type; resolve the profile conflict before merging")
                collapses = conn.execute(
                    "SELECT 1 FROM identity_relationships WHERE (from_party_id=%s AND to_party_id=%s) OR (from_party_id=%s AND to_party_id=%s) LIMIT 1",
                    (source_party_id,target_party_id,target_party_id,source_party_id),
                ).fetchone()
                if collapses:
                    raise HTTPException(409, "These identities already have a direct relationship; resolve it before merging")
                referral_conflict = conn.execute(
                    "SELECT 1 FROM identity_referral_links WHERE (referrer_party_id=%s AND referred_party_id=%s) OR (referrer_party_id=%s AND referred_party_id=%s) LIMIT 1",
                    (source_party_id,target_party_id,target_party_id,source_party_id),
                ).fetchone()
                if referral_conflict:
                    raise HTTPException(409, "A referral link would collapse into a self-referral; resolve it before merging")
                conn.execute("UPDATE identity_profiles SET party_id=%s,updated_at=now() WHERE party_id=%s", (target_party_id,source_party_id))
                conn.execute("UPDATE identity_auth_accounts SET party_id=%s WHERE party_id=%s", (target_party_id,source_party_id))
                conn.execute("UPDATE identity_contacts SET party_id=%s,updated_at=now() WHERE party_id=%s", (target_party_id,source_party_id))
                conn.execute("UPDATE identity_relationships SET from_party_id=%s,updated_at=now() WHERE from_party_id=%s", (target_party_id,source_party_id))
                conn.execute("UPDATE identity_relationships SET to_party_id=%s,updated_at=now() WHERE to_party_id=%s", (target_party_id,source_party_id))
                conn.execute("UPDATE identity_loyalty_accounts SET party_id=%s WHERE party_id=%s", (target_party_id,source_party_id))
                conn.execute("UPDATE identity_referral_links SET referrer_party_id=%s WHERE referrer_party_id=%s", (target_party_id,source_party_id))
                conn.execute("UPDATE identity_referral_links SET referred_party_id=%s WHERE referred_party_id=%s", (target_party_id,source_party_id))
                conn.execute("INSERT INTO identity_aliases(alias_sbid,source_party_id,canonical_party_id,merge_reason,merged_by_user_id) VALUES(%s,%s,%s,%s,%s)", (source["sbid"],source_party_id,target_party_id,payload.reason,request.state.user_id))
                conn.execute("UPDATE identity_parties SET status='merged',merged_into_party_id=%s,updated_at=now() WHERE id=%s", (target_party_id,source_party_id))
                service = IdentityService(conn)
                service._event(party_id=target_party_id,event_type="party_merged",event_data={"source_party_id":source_party_id,"source_sbid":source["sbid"],"canonical_sbid":target["sbid"],"proof_method":payload.proof_method},actor_user_id=request.state.user_id,reason=payload.reason)
        return {"source_sbid": source["sbid"], "canonical_sbid": target["sbid"], "status": "merged"}
    except HTTPException:
        raise
    except psycopg.Error as exc:
        if getattr(exc, "sqlstate", None) == "23505":
            raise HTTPException(409, "Merge would violate an identity uniqueness rule") from exc
        raise HTTPException(503, "Unable to merge identities") from exc


class SplitIn(BaseModel):
    profile_id: int = Field(gt=0)
    reason: str = Field(min_length=5, max_length=500)


@router.post("/parties/{party_id}/split-profile", status_code=201)
def split_profile(party_id: int, payload: SplitIn, request: Request):
    _admin(request)
    try:
        with _connect() as conn:
            with conn.transaction():
                party = conn.execute("SELECT id,party_type,display_name,status FROM identity_parties WHERE id=%s FOR UPDATE", (party_id,)).fetchone()
                if party is None or party["status"] != "active":
                    raise HTTPException(404, "Active identity not found")
                profile = conn.execute("SELECT id,profile_type,customer_account_id,crm_customer_id,employee_id,supplier_id FROM identity_profiles WHERE id=%s AND party_id=%s AND status='active' FOR UPDATE", (payload.profile_id,party_id)).fetchone()
                if profile is None:
                    raise HTTPException(404, "Active profile does not belong to this identity")
                new_party = IdentityService(conn).create_party(party_type=party["party_type"],display_name=party["display_name"],actor_user_id=request.state.user_id,reason=payload.reason)
                conn.execute("UPDATE identity_profiles SET party_id=%s,updated_at=now() WHERE id=%s", (new_party["id"],payload.profile_id))
                if profile["profile_type"] == "customer_account":
                    conn.execute("UPDATE identity_auth_accounts SET party_id=%s WHERE party_id=%s AND customer_account_id=%s", (new_party["id"],party_id,profile["customer_account_id"]))
                elif profile["profile_type"] == "employee":
                    employee = conn.execute("SELECT user_id FROM hr_employees WHERE id=%s", (profile["employee_id"],)).fetchone()
                    if employee and employee["user_id"]:
                        conn.execute("UPDATE identity_auth_accounts SET party_id=%s WHERE party_id=%s AND app_user_id=%s", (new_party["id"],party_id,employee["user_id"]))
                IdentityService(conn)._event(party_id=party_id,event_type="party_split",event_data={"new_party_id":new_party["id"],"new_sbid":new_party["sbid"],"profile_id":payload.profile_id,"profile_type":profile["profile_type"]},actor_user_id=request.state.user_id,reason=payload.reason)
        return {"party": new_party, "moved_profile_id": payload.profile_id}
    except HTTPException:
        raise
    except psycopg.Error as exc:
        raise HTTPException(503, "Unable to split identity profile") from exc
