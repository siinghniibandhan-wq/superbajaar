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
    # Preserve duplicate source contacts as closed history, while retaining the
    # strongest verification evidence on the canonical contact row.
    conn.execute(
        """
        UPDATE identity_contacts target
        SET verification_status='verified',
            verified_at=COALESCE(target.verified_at, source.verified_at),
            updated_at=now()
        FROM identity_contacts source
        WHERE target.party_id=%s AND source.party_id=%s
          AND target.contact_type=source.contact_type
          AND target.normalized_value=source.normalized_value
          AND target.valid_to IS NULL AND source.valid_to IS NULL
          AND source.verification_status='verified'
          AND target.verification_status <> 'verified'
        """,
        (target_party_id, source_party_id),
    )
    conn.execute(
        """
        UPDATE identity_contacts source
        SET valid_to=GREATEST(now(), source.valid_from),
            is_primary=false,
            updated_at=now()
        WHERE source.party_id=%s AND source.valid_to IS NULL
          AND EXISTS (
              SELECT 1 FROM identity_contacts target
              WHERE target.party_id=%s AND target.valid_to IS NULL
                AND target.contact_type=source.contact_type
                AND target.normalized_value=source.normalized_value
          )
        """,
        (source_party_id, target_party_id),
    )
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
    conn.execute(
        """
        UPDATE identity_contacts source
        SET is_primary=false
        WHERE source.party_id=%s AND source.valid_to IS NULL AND source.is_primary=true
          AND EXISTS (
              SELECT 1 FROM identity_contacts target
              WHERE target.party_id=%s AND target.contact_type=source.contact_type
                AND target.valid_to IS NULL AND target.verification_status='verified'
                AND target.is_primary=true
          )
        """,
        (source_party_id, target_party_id),
    )
    conn.execute("UPDATE identity_contacts SET party_id=%s,updated_at=now() WHERE party_id=%s AND valid_to IS NULL", (target_party_id,source_party_id))
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
    return {"source_sbid": source["sbid"], "canonical_sbid": target["sbid"], "status": "merged"}


def _admin(request: Request):
    if not getattr(request.state, "user_id", None) or getattr(request.state, "role", "") not in {"super_admin", "admin"}:
        raise HTTPException(403, "Identity administration permission is required")


class LinkRequestIn(BaseModel):
    target_party_id: int = Field(gt=0)
    requester_party_id: int | None = Field(default=None, gt=0)
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


class ContactVerifyIn(BaseModel):
    proof_method: str = Field(pattern=r"^(document_review|in_person|verified_account|business_registry)$")
    reason: str = Field(min_length=5, max_length=500)


class RelationshipRevokeIn(BaseModel):
    reason: str = Field(min_length=5, max_length=500)


@router.get("/reconciliation/preview")
def legacy_reconciliation_preview(
    request: Request,
    limit: int = Query(default=100, ge=1, le=200),
):
    """Read-only exact-contact candidate report; matching never links or merges records."""
    _admin(request)
    query = """
        WITH source_records AS (
            SELECT 'customer_account'::text AS profile_type, ca.id AS source_id,
                   NULLIF(lower(trim(to_jsonb(ca)->>'email')), '') AS email_value,
                   NULLIF(regexp_replace(coalesce(nullif(trim(to_jsonb(ca)->>'phone'), ''),
                       nullif(trim(to_jsonb(ca)->>'mobile'), ''), nullif(trim(to_jsonb(ca)->>'mobile_number'), '')), '[^0-9]', '', 'g'), '') AS phone_digits
            FROM customer_accounts ca
            UNION ALL
            SELECT 'crm_customer', c.id,
                   NULLIF(lower(trim(coalesce(nullif(trim(to_jsonb(c)->>'email'), ''),
                       nullif(trim(to_jsonb(c)->>'customer_email'), '')))), ''),
                   NULLIF(regexp_replace(coalesce(nullif(trim(to_jsonb(c)->>'phone'), ''),
                       nullif(trim(to_jsonb(c)->>'customer_phone'), ''), nullif(trim(to_jsonb(c)->>'mobile'), ''),
                       nullif(trim(to_jsonb(c)->>'mobile_number'), '')), '[^0-9]', '', 'g'), '')
            FROM customers c
            UNION ALL
            SELECT 'employee', e.id,
                   NULLIF(lower(trim(coalesce(nullif(trim(to_jsonb(e)->>'email'), ''),
                       nullif(trim(to_jsonb(e)->>'work_email'), '')))), ''),
                   NULLIF(regexp_replace(coalesce(nullif(trim(to_jsonb(e)->>'phone'), ''),
                       nullif(trim(to_jsonb(e)->>'mobile'), ''), nullif(trim(to_jsonb(e)->>'mobile_number'), '')), '[^0-9]', '', 'g'), '')
            FROM hr_employees e
            UNION ALL
            SELECT 'vendor_organisation', s.id,
                   NULLIF(lower(trim(to_jsonb(s)->>'email')), ''),
                   NULLIF(regexp_replace(coalesce(nullif(trim(to_jsonb(s)->>'phone'), ''),
                       nullif(trim(to_jsonb(s)->>'mobile'), ''), nullif(trim(to_jsonb(s)->>'mobile_number'), '')), '[^0-9]', '', 'g'), '')
            FROM suppliers s
        ),
        contact_candidates AS (
            SELECT profile_type, source_id, 'email'::text AS contact_type,
                   email_value AS normalized_value
            FROM source_records WHERE email_value IS NOT NULL
            UNION ALL
            SELECT profile_type, source_id, 'phone',
                   CASE
                     WHEN length(phone_digits)=12 AND left(phone_digits,2)='91' THEN right(phone_digits,10)
                     WHEN length(phone_digits)=11 AND left(phone_digits,1)='0' THEN right(phone_digits,10)
                     ELSE phone_digits
                   END
            FROM source_records
            WHERE phone_digits IS NOT NULL AND length(phone_digits) BETWEEN 7 AND 15
        ),
        duplicate_contacts AS (
            SELECT contact_type, normalized_value,
                   count(*) AS match_count,
                   count(DISTINCT profile_type) AS profile_type_count
            FROM contact_candidates
            GROUP BY contact_type, normalized_value
            HAVING count(*) > 1
        )
        SELECT d.contact_type,
               CASE WHEN d.contact_type='email'
                    THEN left(d.normalized_value,2)||'***@'||split_part(d.normalized_value,'@',2)
                    ELSE left(d.normalized_value,3)||'******'||right(d.normalized_value,2)
               END AS masked_contact,
               d.match_count,
               d.profile_type_count,
               'manual_review_required'::text AS classification,
               'An exact contact match is only a candidate signal, not proof that records belong to the same person or organisation.'::text AS review_note,
               jsonb_agg(jsonb_build_object(
                   'profile_type', c.profile_type,
                   'source_id', c.source_id,
                   'sbid', p.sbid,
                   'profile_status', ip.status
               ) ORDER BY c.profile_type, c.source_id) AS records
        FROM duplicate_contacts d
        JOIN contact_candidates c
          ON c.contact_type=d.contact_type AND c.normalized_value=d.normalized_value
        LEFT JOIN identity_profiles ip
          ON ip.profile_type=c.profile_type
         AND CASE c.profile_type
             WHEN 'customer_account' THEN ip.customer_account_id
             WHEN 'crm_customer' THEN ip.crm_customer_id
             WHEN 'employee' THEN ip.employee_id
             ELSE ip.supplier_id
         END = c.source_id
        LEFT JOIN identity_parties p ON p.id=ip.party_id
        GROUP BY d.contact_type,d.normalized_value,d.match_count,d.profile_type_count
        ORDER BY d.match_count DESC,d.contact_type,d.normalized_value
        LIMIT %s
    """
    try:
        with _connect() as conn:
            rows = conn.execute(query, (limit,)).fetchall()
        return {
            "items": rows,
            "count": len(rows),
            "limit": limit,
            "read_only": True,
            "automatic_linking": False,
            "automatic_merging": False,
        }
    except psycopg.Error as exc:
        raise HTTPException(503, "Unable to generate the legacy identity reconciliation preview") from exc


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
            events = conn.execute("SELECT id,event_type,reason,event_data,created_at FROM identity_events WHERE party_id=%s OR event_data->>'to_party_id'=%s ORDER BY created_at DESC,id DESC LIMIT 100", (party_id, str(party_id))).fetchall()
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
                "SELECT r.id,r.request_type,r.status,r.requested_profile_type,r.requested_source_id,r.proof_method,r.proof_verified_at,r.request_context->>'reason' AS reason,r.request_context->>'requested_sbid' AS requested_sbid,r.created_at,"
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
                requester_party_id = payload.requester_party_id
                if payload.request_type == "organisation_relationship":
                    if requester_party_id is None:
                        requester = conn.execute(
                            "SELECT party_id FROM identity_auth_accounts "
                            "WHERE app_user_id=%s AND status='active'",
                            (request.state.user_id,),
                        ).fetchone()
                        requester_party_id = requester["party_id"] if requester else None
                    if requester_party_id is None:
                        raise HTTPException(409, "Select the individual identity that is requesting this organisation relationship")
                    parties = conn.execute(
                        "SELECT id,party_type,status FROM identity_parties "
                        "WHERE id IN (%s,%s) ORDER BY id FOR UPDATE",
                        (requester_party_id, payload.target_party_id),
                    ).fetchall()
                    by_id = {party["id"]: party for party in parties}
                    person = by_id.get(requester_party_id)
                    organisation = by_id.get(payload.target_party_id)
                    if not person or not organisation or person["status"] != "active" or organisation["status"] != "active":
                        raise HTTPException(409, "Both selected identities must be active")
                    if person["party_type"] != "individual" or organisation["party_type"] != "organisation":
                        raise HTTPException(409, "An organisation relationship must connect an individual to an organisation")
                elif requester_party_id is not None:
                    raise HTTPException(422, "A requester identity can only be selected for organisation relationship requests")
                else:
                    requester = conn.execute(
                        "SELECT party_id FROM identity_auth_accounts "
                        "WHERE app_user_id=%s AND status='active'",
                        (request.state.user_id,),
                    ).fetchone()
                    requester_party_id = requester["party_id"] if requester else None
                row = conn.execute(
                    "INSERT INTO identity_link_requests(idempotency_key,requester_party_id,target_party_id,request_type,status,requested_profile_type,requested_source_id,expires_at,request_context) "
                    "VALUES(%s,%s,%s,%s,'proof_required',%s,%s,%s,jsonb_build_object('reason',%s::text,'relationship_type',%s::text,'relationship_scope',%s::jsonb,'submitted_by_user_id',%s::bigint)) "
                    "ON CONFLICT(idempotency_key) DO NOTHING RETURNING id,status,created_at",
                    (payload.idempotency_key, requester_party_id, payload.target_party_id, payload.request_type, payload.requested_profile_type, payload.requested_source_id, datetime.now(timezone.utc)+timedelta(days=7), payload.reason, payload.relationship_type, __import__("json").dumps(payload.relationship_scope), request.state.user_id),
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
                    conn.execute(
                        "UPDATE identity_link_requests SET status='expired',reviewed_at=now(),updated_at=now() WHERE id=%s",
                        (request_id,),
                    )
                    return {"id": request_id, "status": "expired"}
                context = item["request_context"] or {}
                if payload.decision == "approve" and context.get("submitted_by_user_id") == request.state.user_id:
                    raise HTTPException(403, "A different administrator must review and approve this identity request")
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


@router.post("/relationships/{relationship_id}/revoke")
def revoke_relationship(relationship_id: int, payload: RelationshipRevokeIn, request: Request):
    """Revoke an active organisation relationship without deleting its history."""
    _admin(request)
    try:
        with _connect() as conn:
            with conn.transaction():
                relationship = conn.execute(
                    "SELECT id,from_party_id,status,valid_to FROM identity_relationships WHERE id=%s FOR UPDATE",
                    (relationship_id,),
                ).fetchone()
                if relationship is None:
                    raise HTTPException(404, "Identity relationship not found")
                if relationship["status"] != "active" or relationship["valid_to"] is not None:
                    raise HTTPException(409, "Only an active relationship can be revoked")
                result = IdentityService(conn).revoke_relationship(
                    relationship_id=relationship_id,
                    actor_user_id=request.state.user_id,
                    reason=payload.reason,
                )
                if result is None:
                    raise HTTPException(409, "Relationship state changed; refresh and retry")
        return {"id": result["id"], "status": result["status"], "valid_to": result["valid_to"]}
    except HTTPException:
        raise
    except psycopg.Error as exc:
        raise HTTPException(503, "Unable to revoke identity relationship") from exc


@router.post("/contacts/{contact_id}/verify")
def verify_contact(contact_id: int, payload: ContactVerifyIn, request: Request):
    """Record an administrator's evidence-based verification of a current contact."""
    _admin(request)
    try:
        with _connect() as conn:
            with conn.transaction():
                contact = conn.execute(
                    """
                    SELECT c.id,c.party_id,c.verification_status,c.valid_to,p.status AS party_status
                    FROM identity_contacts c
                    JOIN identity_parties p ON p.id=c.party_id
                    WHERE c.id=%s
                    FOR UPDATE OF c,p
                    """,
                    (contact_id,),
                ).fetchone()
                if contact is None:
                    raise HTTPException(404, "Identity contact not found")
                if contact["party_status"] != "active" or contact["valid_to"] is not None:
                    raise HTTPException(409, "Only a current contact on an active identity can be verified")
                if contact["verification_status"] not in {"unverified", "expired"}:
                    raise HTTPException(409, "This contact is not eligible for verification")
                result = IdentityService(conn).verify_contact(
                    contact_id=contact_id,
                    actor_user_id=request.state.user_id,
                    proof_method=payload.proof_method,
                    reason=payload.reason,
                )
                if result is None:
                    raise HTTPException(409, "Contact verification state changed; refresh and retry")
        return {"id": result["id"], "status": result["verification_status"], "verified_at": result["verified_at"]}
    except HTTPException:
        raise
    except psycopg.Error as exc:
        raise HTTPException(503, "Unable to verify identity contact") from exc


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
                result = _merge_claimed_party(
                    conn, source_party_id, payload.target_party_id,
                    request.state.user_id, payload.reason, payload.proof_method,
                )
        return result
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
                attached_history = conn.execute(
                    "SELECT "
                    "(SELECT count(*) FROM identity_loyalty_accounts WHERE party_id=%s) AS loyalty_count, "
                    "(SELECT count(*) FROM identity_referral_links WHERE referrer_party_id=%s OR referred_party_id=%s) AS referral_count, "
                    "(SELECT count(*) FROM identity_relationships WHERE (from_party_id=%s OR to_party_id=%s) AND status IN ('pending','active')) AS relationship_count",
                    (party_id, party_id, party_id, party_id, party_id),
                ).fetchone()
                contact_count = conn.execute(
                    "SELECT count(*) AS n FROM identity_contacts WHERE party_id=%s AND valid_to IS NULL",
                    (party_id,),
                ).fetchone()["n"]
                if contact_count or any(attached_history[key] for key in ("loyalty_count", "referral_count", "relationship_count")):
                    raise HTTPException(
                        409,
                        "This identity has contacts, loyalty, referral or organisation-relationship history. Resolve those associations explicitly before splitting the profile.",
                    )
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
