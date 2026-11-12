"""Customer-facing authentication and referral tracking, separate from staff/admin auth."""
from datetime import datetime, timedelta, timezone
import secrets

import psycopg
from fastapi import APIRouter, HTTPException, Request
from psycopg.rows import dict_row
from pydantic import BaseModel, EmailStr, Field, field_validator

from app.api.auth import _password_hash, _password_matches, _sign, _decode
from app.core.config import settings
from app.services.identity import IdentityService

router = APIRouter(prefix="/customer-auth", tags=["customer authentication"])
TOKEN_TTL_HOURS = 24 * 30


def _connect():
    if not settings.database_url:
        raise HTTPException(status_code=503, detail="Customer authentication database is not configured")
    try:
        return psycopg.connect(settings.database_url, row_factory=dict_row, connect_timeout=3)
    except psycopg.Error as exc:
        raise HTTPException(status_code=503, detail="Customer authentication storage is unavailable") from exc


def _new_referral_code(conn) -> str:
    for _ in range(8):
        code = "SB" + secrets.token_hex(4).upper()
        if not conn.execute("SELECT 1 FROM customer_accounts WHERE referral_code=%s", (code,)).fetchone():
            return code
    raise HTTPException(status_code=503, detail="Could not generate a unique referral code")


class CustomerRegister(BaseModel):
    full_name: str = Field(min_length=2, max_length=200)
    email: EmailStr
    phone: str = Field(min_length=7, max_length=20)
    password: str = Field(min_length=10, max_length=1024)
    referral_code: str | None = Field(default=None, max_length=24)

    @field_validator("full_name")
    @classmethod
    def clean_name(cls, value):
        value = " ".join(value.split())
        if len(value) < 2:
            raise ValueError("Enter your full name")
        return value

    @field_validator("email")
    @classmethod
    def clean_email(cls, value):
        return str(value).strip().lower()

    @field_validator("phone")
    @classmethod
    def clean_phone(cls, value):
        value = " ".join(value.split())
        digits = "".join(ch for ch in value if ch.isdigit())
        if len(digits) < 7 or len(digits) > 15:
            raise ValueError("Enter a valid mobile number")
        # Canonicalise Indian mobile numbers so +91, 91, 0-prefix and local
        # 10-digit forms cannot be used to create duplicate accounts.
        if len(digits) == 12 and digits.startswith("91"):
            digits = digits[2:]
        elif len(digits) == 11 and digits.startswith("0"):
            digits = digits[1:]
        if len(digits) == 10 and digits[0] in "6789":
            return "+91" + digits
        return ("+" if value.strip().startswith("+") else "") + digits

    @field_validator("referral_code")
    @classmethod
    def clean_referral_code(cls, value):
        if value is None or not value.strip():
            return None
        return value.strip().upper()


class CustomerLogin(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=1024)

    @field_validator("email")
    @classmethod
    def clean_email(cls, value):
        return str(value).strip().lower()


def _issue_session(conn, customer):
    now = datetime.now(timezone.utc)
    expires = now + timedelta(hours=TOKEN_TTL_HOURS)
    token_id = secrets.token_urlsafe(24)
    token = _sign({
        "sub": str(customer["id"]), "jti": token_id, "typ": "customer",
        "iat": int(now.timestamp()), "exp": int(expires.timestamp()),
    })
    conn.execute(
        "INSERT INTO customer_sessions (customer_id, token_id, expires_at) VALUES (%s,%s,%s)",
        (customer["id"], token_id, expires),
    )
    return {"access_token": token, "token_type": "bearer", "expires_at": expires.isoformat()}



def _ensure_customer_identity(conn, customer_id: int, full_name: str) -> str:
    """Provision or resolve the individual identity for this exact authenticated customer account."""
    profile = conn.execute(
        "SELECT party_id,status FROM identity_profiles "
        "WHERE profile_type='customer_account' AND customer_account_id=%s FOR UPDATE",
        (customer_id,),
    ).fetchone()
    auth_link = conn.execute(
        "SELECT party_id,status FROM identity_auth_accounts "
        "WHERE account_type='customer' AND customer_account_id=%s FOR UPDATE",
        (customer_id,),
    ).fetchone()

    if profile and profile["status"] != "active":
        raise HTTPException(status_code=409, detail="Customer identity link is inactive and requires administrator review")
    if auth_link and auth_link["status"] != "active":
        raise HTTPException(status_code=409, detail="Customer login identity is inactive and requires administrator review")
    if profile and auth_link and profile["party_id"] != auth_link["party_id"]:
        raise HTTPException(status_code=409, detail="Customer identity links conflict and require administrator review")

    party_id = profile["party_id"] if profile else (auth_link["party_id"] if auth_link else None)
    identity = IdentityService(conn)
    if party_id is None:
        party = identity.create_party(
            party_type="individual",
            display_name=full_name,
            reason="Authenticated customer session assigned missing legacy identity",
        )
        party_id = party["id"]

    party = conn.execute(
        "SELECT id,sbid,party_type,status FROM identity_parties WHERE id=%s FOR UPDATE",
        (party_id,),
    ).fetchone()
    if party is None or party["party_type"] != "individual" or party["status"] != "active":
        raise HTTPException(status_code=409, detail="Customer identity is invalid or inactive and requires administrator review")

    if not profile:
        identity.link_profile(
            party_id=party_id,
            profile_type="customer_account",
            source_id=customer_id,
            link_method="authenticated_claim",
            reason="Authenticated customer session linked exact customer account",
        )
    if not auth_link:
        identity.link_auth_account(
            party_id=party_id,
            account_type="customer",
            source_id=customer_id,
            link_method="authenticated_claim",
        )
    return party["sbid"]

def _public_customer(row):
    return {
        "id": row["id"], "sbid": row.get("sbid"), "email": row["email"], "full_name": row["full_name"],
        "phone": row["phone"], "referral_code": row["referral_code"],
    }


class CustomerProfileUpdate(BaseModel):
    full_name: str = Field(min_length=2, max_length=200)

    @field_validator("full_name")
    @classmethod
    def clean_full_name(cls, value):
        value = " ".join(value.split())
        if len(value) < 2:
            raise ValueError("Full name must contain at least two characters")
        return value


@router.patch("/me")
def update_my_profile(payload: CustomerProfileUpdate, request: Request):
    customer_id = getattr(request.state, "customer_id", None)
    if not customer_id:
        raise HTTPException(status_code=401, detail="Customer sign-in required")
    try:
        with _connect() as conn:
            with conn.transaction():
                customer = conn.execute(
                    "UPDATE customer_accounts SET full_name=%s,updated_at=now() "
                    "WHERE id=%s AND is_active=TRUE RETURNING id,email,full_name,phone,referral_code",
                    (payload.full_name, customer_id),
                ).fetchone()
                if customer is None:
                    raise HTTPException(status_code=404, detail="Customer account not found")
                from app.services.identity import IdentityService
                identity = IdentityService(conn)
                profile = conn.execute(
                    "SELECT party_id FROM identity_profiles WHERE customer_account_id=%s "
                    "AND profile_type='customer_account' AND status='active' FOR UPDATE",
                    (customer_id,),
                ).fetchone()
                if profile:
                    party_id = profile["party_id"]
                    party = conn.execute(
                        "SELECT sbid FROM identity_parties WHERE id=%s FOR UPDATE", (party_id,)
                    ).fetchone()
                    if party is None:
                        raise HTTPException(status_code=409, detail="Customer identity link is invalid")
                    sbid = party["sbid"]
                    conn.execute(
                        "UPDATE identity_parties SET display_name=%s,updated_at=now() WHERE id=%s",
                        (payload.full_name, party_id),
                    )
                else:
                    party = identity.create_party(
                        party_type="individual", display_name=payload.full_name,
                        reason="Authenticated customer profile update assigned missing legacy identity",
                    )
                    party_id, sbid = party["id"], party["sbid"]
                    identity.link_profile(
                        party_id=party_id, profile_type="customer_account",
                        source_id=customer_id, link_method="authenticated_claim",
                        reason="Authenticated customer profile update assigned missing legacy identity",
                    )
                linked = conn.execute(
                    "SELECT party_id,status FROM identity_auth_accounts "
                    "WHERE account_type='customer' AND customer_account_id=%s FOR UPDATE",
                    (customer_id,),
                ).fetchone()
                if linked and (linked["party_id"] != party_id or linked["status"] != "active"):
                    raise HTTPException(status_code=409, detail="Customer login identity conflict requires administrator review")
                if not linked:
                    identity.link_auth_account(
                        party_id=party_id, account_type="customer", source_id=customer_id,
                        link_method="authenticated_claim",
                    )
                for contact_type, value in (("email", customer["email"]), ("phone", customer["phone"])):
                    if value:
                        try:
                            identity.add_contact(party_id=party_id, contact_type=contact_type,
                                                 value=value, source="authenticated_customer_profile")
                        except ValueError:
                            pass
                customer = {**customer, "sbid": sbid}
        return {"customer": _public_customer(customer)}
    except HTTPException:
        raise
    except psycopg.Error as exc:
        raise HTTPException(status_code=503, detail="Could not update customer profile") from exc


@router.post("/register", status_code=201)
def register(payload: CustomerRegister):
    if len(settings.jwt_secret_key) < 32:
        raise HTTPException(status_code=503, detail="Customer authentication is not configured")
    email = str(payload.email).strip().lower()
    try:
        with _connect() as conn:
            with conn.transaction():
                phone = payload.phone.strip()
                phone_digits = "".join(ch for ch in phone if ch.isdigit())
                if len(phone_digits) == 12 and phone_digits.startswith("91"):
                    phone_digits = phone_digits[2:]
                elif len(phone_digits) == 11 and phone_digits.startswith("0"):
                    phone_digits = phone_digits[1:]
                existing = conn.execute(
                    "SELECT id FROM customer_accounts WHERE lower(email)=lower(%s) "
                    "OR CASE WHEN length(regexp_replace(phone, '[^0-9]', '', 'g'))=12 AND left(regexp_replace(phone, '[^0-9]', '', 'g'),2)='91' "
                    "THEN right(regexp_replace(phone, '[^0-9]', '', 'g'),10) "
                    "WHEN length(regexp_replace(phone, '[^0-9]', '', 'g'))=11 AND left(regexp_replace(phone, '[^0-9]', '', 'g'),1)='0' "
                    "THEN right(regexp_replace(phone, '[^0-9]', '', 'g'),10) "
                    "ELSE regexp_replace(phone, '[^0-9]', '', 'g') END=%s LIMIT 1",
                    (email, phone_digits),
                ).fetchone()
                if existing:
                    raise HTTPException(status_code=409, detail="An account with this email or mobile number already exists. Please sign in or use your own contact details.")
                # Reject returning buyers by checking legacy customer/order/loyalty records
                # only where the expected contact columns exist in this deployment.
                legacy_columns = conn.execute(
                    "SELECT table_name, column_name FROM information_schema.columns "
                    "WHERE table_schema='public' AND table_name IN ('customers','orders','loyalty_accounts') "
                    "AND column_name IN ('email','customer_email','phone','customer_phone','mobile','mobile_number')"
                ).fetchall()
                from psycopg import sql
                for item in legacy_columns:
                    col = item["column_name"]
                    if col in ("email", "customer_email"):
                        value = email
                        expression = sql.SQL("lower(trim({})) = %s").format(sql.Identifier(col))
                    else:
                        value = phone_digits
                        expression = sql.SQL("CASE WHEN length(regexp_replace(coalesce({}, ''), '[^0-9]', '', 'g'))=12 AND left(regexp_replace(coalesce({}, ''), '[^0-9]', '', 'g'),2)='91' THEN right(regexp_replace(coalesce({}, ''), '[^0-9]', '', 'g'),10) WHEN length(regexp_replace(coalesce({}, ''), '[^0-9]', '', 'g'))=11 AND left(regexp_replace(coalesce({}, ''), '[^0-9]', '', 'g'),1)='0' THEN right(regexp_replace(coalesce({}, ''), '[^0-9]', '', 'g'),10) ELSE regexp_replace(coalesce({}, ''), '[^0-9]', '', 'g') END = %s").format(*[sql.Identifier(col)]*7)
                    if not value:
                        continue
                    found = conn.execute(
                        sql.SQL("SELECT 1 FROM {} WHERE ").format(sql.Identifier(item["table_name"])) + expression + sql.SQL(" LIMIT 1"),
                        (value,),
                    ).fetchone()
                    if found:
                        label = "email address" if col in ("email", "customer_email") else "mobile number"
                        raise HTTPException(status_code=409, detail=f"This {label} is already associated with an existing Super Bajaar customer record.")
                referrer = None
                referral_code = payload.referral_code
                if referral_code:
                    referrer = conn.execute(
                        "SELECT id, email, phone FROM customer_accounts WHERE referral_code=%s AND is_active=TRUE",
                        (referral_code,),
                    ).fetchone()
                    if referrer is None:
                        raise HTTPException(status_code=422, detail="Referral code is invalid")
                    referrer_phone_digits = "".join(ch for ch in (referrer["phone"] or "") if ch.isdigit())
                    if referrer["email"].strip().lower() == email or (
                        referrer_phone_digits and phone_digits == referrer_phone_digits
                    ):
                        raise HTTPException(status_code=422, detail="You cannot use your own referral details")
                own_code = _new_referral_code(conn)
                customer = conn.execute(
                    "INSERT INTO customer_accounts (email,full_name,phone,password_hash,referral_code,referred_by_customer_id) "
                    "VALUES (%s,%s,%s,%s,%s,%s) "
                    "RETURNING id,email,full_name,phone,referral_code",
                    (email, payload.full_name, phone, _password_hash(payload.password), own_code,
                     referrer["id"] if referrer else None),
                ).fetchone()
                # Create the permanent individual identity without changing the legacy customer ID.
                # Contact points remain unverified until the existing verification flow proves control.
                from app.services.identity import IdentityService
                identity = IdentityService(conn)
                party = identity.create_party(
                    party_type="individual",
                    display_name=customer["full_name"],
                    reason="Customer self-registration",
                )
                identity.link_profile(
                    party_id=party["id"],
                    profile_type="customer_account",
                    source_id=customer["id"],
                    link_method="authenticated_claim",
                )
                identity.link_auth_account(
                    party_id=party["id"],
                    account_type="customer",
                    source_id=customer["id"],
                    link_method="authenticated_claim",
                )
                identity.add_contact(
                    party_id=party["id"],
                    contact_type="email",
                    value=email,
                    source="customer_registration",
                )
                identity.add_contact(
                    party_id=party["id"],
                    contact_type="phone",
                    value=phone,
                    source="customer_registration",
                )
                # Track the referral only; no reward is issued until reward rules are confirmed.
                if referrer:
                    referral = conn.execute(
                        "INSERT INTO customer_referrals (referrer_customer_id,referred_customer_id,referral_code) "
                        "VALUES (%s,%s,%s) RETURNING id",
                        (referrer["id"], customer["id"], referral_code),
                    ).fetchone()
                    referrer_party = conn.execute(
                        "SELECT party_id FROM identity_profiles WHERE profile_type='customer_account' "
                        "AND customer_account_id=%s AND status='active'",
                        (referrer["id"],),
                    ).fetchone()
                    # Link only through the existing customer-account FK mapping, never email/phone similarity.
                    if referrer_party and referrer_party["party_id"] != party["id"]:
                        conn.execute(
                            "INSERT INTO identity_referral_links(referral_id,referrer_party_id,referred_party_id) "
                            "VALUES(%s,%s,%s)",
                            (referral["id"], referrer_party["party_id"], party["id"]),
                        )
                        identity._event(
                            party_id=referrer_party["party_id"], event_type="profile_linked",
                            event_data={"profile_type":"referral","referral_id":referral["id"],"referred_party_id":party["id"]},
                            reason="Referral identity association created from verified customer account links",
                        )
                # Create the customer's existing loyalty card now; coin balance remains in its ledger.
                card_number = "SB-" + secrets.token_hex(5).upper()
                loyalty_account = conn.execute(
                    "INSERT INTO loyalty_accounts (customer_email,card_number) VALUES (%s,%s) "
                    "ON CONFLICT (customer_email) DO NOTHING RETURNING id",
                    (email, card_number),
                ).fetchone()
                # The just-authenticated registration owns this newly issued card; never infer ownership of an old card by email.
                if loyalty_account:
                    conn.execute(
                        "INSERT INTO identity_loyalty_accounts(party_id,loyalty_account_id,link_method) "
                        "VALUES(%s,%s,'verified_customer_account')",
                        (party["id"], loyalty_account["id"]),
                    )
                customer = dict(customer)
                customer["sbid"] = party["sbid"]
                session = _issue_session(conn, customer)
        return {**session, "customer": _public_customer(customer)}
    except HTTPException:
        raise
    except psycopg.errors.UniqueViolation as exc:
        raise HTTPException(status_code=409, detail="An account with this email or referral code already exists") from exc
    except psycopg.Error as exc:
        raise HTTPException(status_code=503, detail="Could not create customer account; verify customer-account migrations") from exc


@router.post("/login")
def login(payload: CustomerLogin):
    if len(settings.jwt_secret_key) < 32:
        raise HTTPException(status_code=503, detail="Customer authentication is not configured")
    email = str(payload.email).strip().lower()
    try:
        with _connect() as conn:
            with conn.transaction():
                customer = conn.execute(
                    "SELECT ca.id,ca.email,ca.full_name,ca.phone,ca.password_hash,ca.referral_code,ca.is_active,iparty.sbid "
                    "FROM customer_accounts ca "
                    "LEFT JOIN identity_profiles ip ON ip.customer_account_id=ca.id "
                    "AND ip.profile_type='customer_account' AND ip.status='active' "
                    "LEFT JOIN identity_parties iparty ON iparty.id=ip.party_id "
                    "WHERE ca.email=%s FOR UPDATE OF ca",
                    (email,),
                ).fetchone()
                if not customer or not customer["is_active"] or not _password_matches(payload.password, customer["password_hash"]):
                    raise HTTPException(status_code=401, detail="Invalid email or password")
                customer = {**customer, "sbid": _ensure_customer_identity(conn, customer["id"], customer["full_name"])}
                session = _issue_session(conn, customer)
        return {**session, "customer": _public_customer(customer)}
    except HTTPException:
        raise
    except psycopg.Error as exc:
        raise HTTPException(status_code=503, detail="Customer authentication storage is unavailable") from exc


@router.get("/me")
def me(request: Request):
    customer_id = getattr(request.state, "customer_id", None)
    if not customer_id:
        raise HTTPException(status_code=401, detail="Customer sign-in required")
    try:
        with _connect() as conn:
            with conn.transaction():
                customer = conn.execute(
                    "SELECT id,email,full_name,phone,referral_code "
                    "FROM customer_accounts WHERE id=%s AND is_active=TRUE FOR UPDATE",
                    (customer_id,),
                ).fetchone()
                if customer is None:
                    raise HTTPException(status_code=401, detail="Customer account is no longer active")
                customer = {**customer, "sbid": _ensure_customer_identity(conn, customer_id, customer["full_name"])}
        return {"customer": _public_customer(customer)}
    except HTTPException:
        raise
    except psycopg.Error as exc:
        raise HTTPException(status_code=503, detail="Could not load customer account") from exc


class IdentityClaimIn(BaseModel):
    target_sbid: str = Field(pattern=r"(?i)^SBID-[A-F0-9]{20}$")
    reason: str = Field(min_length=5, max_length=500)


@router.post("/identity-claims", status_code=202)
def request_identity_claim(payload: IdentityClaimIn, request: Request):
    """Authenticated customer request to claim an existing SBID; never confirms whether it exists."""
    customer_id = getattr(request.state, "customer_id", None)
    if not customer_id:
        raise HTTPException(status_code=401, detail="Customer sign-in required")
    requested_sbid = payload.target_sbid.strip().upper()
    try:
        with _connect() as conn:
            with conn.transaction():
                customer = conn.execute(
                    "SELECT id,full_name FROM customer_accounts WHERE id=%s AND is_active=TRUE FOR UPDATE",
                    (customer_id,),
                ).fetchone()
                if not customer:
                    raise HTTPException(status_code=401, detail="Customer account is no longer active")
                own = conn.execute(
                    "SELECT party_id FROM identity_profiles WHERE profile_type='customer_account' AND customer_account_id=%s AND status='active'",
                    (customer_id,),
                ).fetchone()
                if own is None:
                    service = IdentityService(conn)
                    party = service.create_party(
                        party_type="individual", display_name=customer["full_name"],
                        reason="Legacy customer initiated identity claim",
                    )
                    service.link_profile(
                        party_id=party["id"], profile_type="customer_account",
                        source_id=customer_id, link_method="authenticated_claim",
                        reason="Legacy customer identity claim",
                    )
                    service.link_auth_account(
                        party_id=party["id"], account_type="customer",
                        source_id=customer_id, link_method="authenticated_claim",
                    )
                    own_party_id = party["id"]
                else:
                    own_party_id = own["party_id"]
                conn.execute("SELECT id FROM identity_parties WHERE id=%s FOR UPDATE", (own_party_id,))
                recent_claims = conn.execute(
                    """
                    WITH RECURSIVE customer_identity_parties(party_id) AS (
                        SELECT %s::bigint
                        UNION
                        SELECT alias.source_party_id
                        FROM identity_aliases alias
                        JOIN customer_identity_parties current_party
                          ON alias.canonical_party_id = current_party.party_id
                    )
                    SELECT count(*) AS total
                    FROM identity_link_requests
                    WHERE request_type='claim_existing_identity'
                      AND requester_party_id IN (SELECT party_id FROM customer_identity_parties)
                      AND created_at > now() - interval '1 hour'
                    """,
                    (own_party_id,),
                ).fetchone()["total"]
                if recent_claims >= 5:
                    raise HTTPException(status_code=429, detail="Too many identity claims. Try again after the review limit resets.")
                target = conn.execute(
                    "SELECT id FROM identity_parties WHERE upper(sbid)=%s AND status='active'",
                    (requested_sbid,),
                ).fetchone()
                # A missing target and a valid target have the same public response.
                if target and target["id"] != own_party_id:
                    conn.execute(
                        "INSERT INTO identity_link_requests(idempotency_key,requester_party_id,target_party_id,request_type,status,expires_at,request_context) "
                        "VALUES(%s,%s,%s,'claim_existing_identity','proof_required',now()+interval '7 days',jsonb_build_object('reason',%s::text,'requested_sbid',%s::text))",
                        (secrets.token_urlsafe(24), own_party_id, target["id"], payload.reason, requested_sbid),
                    )
                    IdentityService(conn)._event(
                        party_id=target["id"], event_type="link_requested",
                        event_data={"request_type":"claim_existing_identity"},
                        actor_party_id=own_party_id, reason="Authenticated customer identity claim submitted",
                    )
                elif target is None:
                    # Keep a customer-visible, non-enumerating submission history even
                    # when no current SBID matches. Admins can review and close it safely.
                    conn.execute(
                        "INSERT INTO identity_link_requests(idempotency_key,requester_party_id,target_party_id,request_type,status,expires_at,request_context) "
                        "VALUES(%s,%s,NULL,'claim_existing_identity','proof_required',now()+interval '7 days',jsonb_build_object('reason',%s::text,'requested_sbid',%s::text))",
                        (secrets.token_urlsafe(24), own_party_id, payload.reason, requested_sbid),
                    )
                    IdentityService(conn)._event(
                        party_id=own_party_id, event_type="link_requested",
                        event_data={"request_type":"claim_existing_identity","target_resolution":"unmatched"},
                        actor_party_id=own_party_id, reason="Authenticated customer identity claim submitted",
                    )
        return {"status": "submitted", "message": "If the identity can be matched, the request will be reviewed. We will not disclose identity details here."}
    except HTTPException:
        raise
    except psycopg.Error as exc:
        raise HTTPException(status_code=503, detail="Unable to submit identity claim") from exc


@router.get("/identity-claims")
def list_identity_claims(request: Request):
    """Return only claim requests initiated by the signed-in customer.

    Target SBIDs and target profile details are deliberately excluded so this
    endpoint cannot be used to enumerate other customers or identities.
    """
    customer_id = getattr(request.state, "customer_id", None)
    if not customer_id:
        raise HTTPException(status_code=401, detail="Customer sign-in required")
    try:
        with _connect() as conn:
            rows = conn.execute(
                """
                WITH RECURSIVE customer_identity_parties(party_id) AS (
                    SELECT party_id
                    FROM identity_profiles
                    WHERE profile_type = 'customer_account'
                      AND customer_account_id = %s
                      AND status = 'active'
                    UNION
                    SELECT alias.source_party_id
                    FROM identity_aliases alias
                    JOIN customer_identity_parties current_party
                      ON alias.canonical_party_id = current_party.party_id
                )
                SELECT r.id, r.status, r.created_at, r.updated_at,
                       r.reviewed_at, r.review_reason, r.proof_method, r.expires_at
                FROM identity_link_requests r
                WHERE r.request_type = 'claim_existing_identity'
                  AND r.requester_party_id IN (SELECT party_id FROM customer_identity_parties)
                ORDER BY r.created_at DESC, r.id DESC
                LIMIT 50
                """,
                (customer_id,),
            ).fetchall()
        return {"items": rows}
    except psycopg.Error as exc:
        raise HTTPException(status_code=503, detail="Could not load your identity claims") from exc


@router.post("/identity-claims/{request_id}/cancel")
def cancel_identity_claim(request_id: int, request: Request):
    """Cancel only the signed-in customer's own unreviewed identity claim."""
    customer_id = getattr(request.state, "customer_id", None)
    if not customer_id:
        raise HTTPException(status_code=401, detail="Customer sign-in required")
    try:
        with _connect() as conn:
            with conn.transaction():
                claim = conn.execute(
                    """
                    WITH RECURSIVE customer_identity_parties(party_id) AS (
                        SELECT party_id
                        FROM identity_profiles
                        WHERE profile_type='customer_account'
                          AND customer_account_id=%s AND status='active'
                        UNION
                        SELECT alias.source_party_id
                        FROM identity_aliases alias
                        JOIN customer_identity_parties current_party
                          ON alias.canonical_party_id=current_party.party_id
                    )
                    SELECT r.id,r.requester_party_id,r.status
                    FROM identity_link_requests r
                    WHERE r.id=%s
                      AND r.request_type='claim_existing_identity'
                      AND r.requester_party_id IN (SELECT party_id FROM customer_identity_parties)
                    FOR UPDATE OF r
                    """,
                    (customer_id, request_id),
                ).fetchone()
                if claim is None:
                    raise HTTPException(404, "Identity claim not found")
                if claim["status"] not in {"pending", "proof_required"}:
                    raise HTTPException(409, "Only an unreviewed identity claim can be cancelled")
                updated = conn.execute(
                    """
                    UPDATE identity_link_requests
                    SET status='cancelled',reviewed_at=now(),
                        review_reason='Cancelled by customer',updated_at=now()
                    WHERE id=%s AND status IN ('pending','proof_required')
                    RETURNING id
                    """,
                    (request_id,),
                ).fetchone()
                if updated is None:
                    raise HTTPException(409, "Claim status changed; refresh and retry")
                IdentityService(conn)._event(
                    party_id=claim["requester_party_id"],
                    event_type="link_cancelled",
                    event_data={"request_id": request_id, "request_type": "claim_existing_identity"},
                    actor_party_id=claim["requester_party_id"],
                    reason="Customer cancelled their identity claim",
                )
        return {"id": request_id, "status": "cancelled"}
    except HTTPException:
        raise
    except psycopg.Error as exc:
        raise HTTPException(status_code=503, detail="Unable to cancel identity claim") from exc


@router.post("/logout")
def logout(request: Request):
    token_id = getattr(request.state, "customer_token_id", None)
    customer_id = getattr(request.state, "customer_id", None)
    if not token_id or not customer_id:
        raise HTTPException(status_code=401, detail="Customer sign-in required")
    try:
        with _connect() as conn:
            conn.execute(
                "UPDATE customer_sessions SET revoked_at=now() WHERE token_id=%s AND customer_id=%s AND revoked_at IS NULL",
                (token_id, customer_id),
            )
        return {"status": "logged_out"}
    except psycopg.Error as exc:
        raise HTTPException(status_code=503, detail="Could not end customer session") from exc


@router.get("/referrals")
def referrals(request: Request):
    customer_id = getattr(request.state, "customer_id", None)
    if not customer_id:
        raise HTTPException(status_code=401, detail="Customer sign-in required")
    try:
        with _connect() as conn:
            customer = conn.execute(
                "SELECT referral_code FROM customer_accounts WHERE id=%s AND is_active=TRUE",
                (customer_id,),
            ).fetchone()
            if not customer:
                raise HTTPException(status_code=401, detail="Customer account is no longer active")
            rows = conn.execute(
                "SELECT r.id, c.full_name AS referred_customer, r.status, r.reward_coins, r.created_at "
                "FROM customer_referrals r JOIN customer_accounts c ON c.id=r.referred_customer_id "
                "WHERE r.referrer_customer_id=%s ORDER BY r.created_at DESC LIMIT 100",
                (customer_id,),
            ).fetchall()
        return {
            "referral_code": customer["referral_code"],
            "referral_link_path": "/customer/register?ref=" + customer["referral_code"],
            "reward_status": "When a referred customer\u0027s first order is delivered, both customers receive 100 Super Coins each.",
            "items": rows,
        }
    except HTTPException:
        raise
    except psycopg.Error as exc:
        raise HTTPException(status_code=503, detail="Could not load referral information") from exc


def _signed_in_customer_email(conn, request: Request) -> str:
    customer_id = getattr(request.state, "customer_id", None)
    if not customer_id:
        raise HTTPException(status_code=401, detail="Customer sign-in required")
    customer = conn.execute(
        "SELECT email FROM customer_accounts WHERE id=%s AND is_active=TRUE", (customer_id,)
    ).fetchone()
    if not customer:
        raise HTTPException(status_code=401, detail="Customer account is no longer active")
    return str(customer["email"]).strip().lower()


@router.get("/orders")
def my_orders(request: Request, limit: int = 50, offset: int = 0):
    """Orders placed by the signed-in customer only (matched on the verified account email)."""
    if not getattr(request.state, "customer_id", None):
        raise HTTPException(status_code=401, detail="Customer sign-in required")
    limit = max(1, min(int(limit), 100))
    offset = max(0, int(offset))
    try:
        with _connect() as conn:
            email = _signed_in_customer_email(conn, request)
            rows = conn.execute(
                "SELECT o.id, o.order_number, o.status, o.total, o.created_at, "
                "(SELECT count(*) FROM order_lines l WHERE l.order_id=o.id) AS line_count, "
                "(SELECT p.status FROM payments p WHERE p.order_id=o.id ORDER BY p.created_at DESC LIMIT 1) AS payment_status "
                "FROM orders o WHERE o.channel='website' AND lower(o.customer_email)=%s "
                "ORDER BY o.created_at DESC LIMIT %s OFFSET %s",
                (email, limit, offset),
            ).fetchall()
        return {"items": rows, "limit": limit, "offset": offset}
    except HTTPException:
        raise
    except psycopg.Error as exc:
        raise HTTPException(status_code=503, detail="Could not load your orders") from exc


@router.get("/orders/{order_number}")
def my_order_detail(order_number: str, request: Request):
    """One order with its items and delivery progress, only if it belongs to the signed-in customer."""
    if not getattr(request.state, "customer_id", None):
        raise HTTPException(status_code=401, detail="Customer sign-in required")
    try:
        with _connect() as conn:
            email = _signed_in_customer_email(conn, request)
            order = conn.execute(
                "SELECT id, order_number, status, subtotal, total, delivery_pin, notes, created_at, updated_at "
                "FROM orders WHERE order_number=%s AND channel='website' AND lower(customer_email)=%s",
                (order_number.strip(), email),
            ).fetchone()
            if order is None:
                raise HTTPException(status_code=404, detail="Order not found")
            lines = conn.execute(
                "SELECT l.id, v.sku, p.name AS product_name, l.quantity, l.unit_price, l.line_total "
                "FROM order_lines l JOIN product_variants v ON v.id=l.variant_id "
                "JOIN products p ON p.id=v.product_id WHERE l.order_id=%s ORDER BY l.id",
                (order["id"],),
            ).fetchall()
            shipments = conn.execute(
                "SELECT shipment_reference, status, tracking_reference, updated_at "
                "FROM deliveries WHERE order_id=%s ORDER BY created_at",
                (order["id"],),
            ).fetchall()
            payments = conn.execute(
                "SELECT status, amount, created_at FROM payments WHERE order_id=%s ORDER BY created_at DESC",
                (order["id"],),
            ).fetchall()
        order.pop("id", None)
        return {"order": order, "lines": lines, "shipments": shipments, "payments": payments}
    except HTTPException:
        raise
    except psycopg.Error as exc:
        raise HTTPException(status_code=503, detail="Could not load this order") from exc
