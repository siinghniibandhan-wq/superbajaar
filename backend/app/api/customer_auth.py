"""Customer-facing authentication and referral tracking, separate from staff/admin auth."""
from datetime import datetime, timedelta, timezone
import secrets

import psycopg
from fastapi import APIRouter, HTTPException, Request
from psycopg.rows import dict_row
from pydantic import BaseModel, EmailStr, Field, field_validator

from app.api.auth import _password_hash, _password_matches, _sign, _decode
from app.core.config import settings

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


def _public_customer(row):
    return {
        "id": row["id"], "email": row["email"], "full_name": row["full_name"],
        "phone": row["phone"], "referral_code": row["referral_code"],
    }


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
                        expression = sql.SQL("CASE WHEN length(regexp_replace(coalesce({}, ''), '[^0-9]', '', 'g'))=12 AND left(regexp_replace(coalesce({}, ''), '[^0-9]', '', 'g'),2)='91' THEN right(regexp_replace(coalesce({}, ''), '[^0-9]', '', 'g'),10) WHEN length(regexp_replace(coalesce({}, ''), '[^0-9]', '', 'g'))=11 AND left(regexp_replace(coalesce({}, ''), '[^0-9]', '', 'g'),1)='0' THEN right(regexp_replace(coalesce({}, ''), '[^0-9]', '', 'g'),10) ELSE regexp_replace(coalesce({}, ''), '[^0-9]', '', 'g') END = %s").format(*[sql.Identifier(col)]*6)
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
                # Track the referral only; no reward is issued until reward rules are confirmed.
                if referrer:
                    conn.execute(
                        "INSERT INTO customer_referrals (referrer_customer_id,referred_customer_id,referral_code) "
                        "VALUES (%s,%s,%s)",
                        (referrer["id"], customer["id"], referral_code),
                    )
                # Create the customer's existing loyalty card now; coin balance remains in its ledger.
                card_number = "SB-" + secrets.token_hex(5).upper()
                conn.execute(
                    "INSERT INTO loyalty_accounts (customer_email,card_number) VALUES (%s,%s) "
                    "ON CONFLICT (customer_email) DO NOTHING",
                    (email, card_number),
                )
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
                    "SELECT id,email,full_name,phone,password_hash,referral_code,is_active "
                    "FROM customer_accounts WHERE email=%s",
                    (email,),
                ).fetchone()
                if not customer or not customer["is_active"] or not _password_matches(payload.password, customer["password_hash"]):
                    raise HTTPException(status_code=401, detail="Invalid email or password")
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
            customer = conn.execute(
                "SELECT id,email,full_name,phone,referral_code FROM customer_accounts WHERE id=%s AND is_active=TRUE",
                (customer_id,),
            ).fetchone()
        if customer is None:
            raise HTTPException(status_code=401, detail="Customer account is no longer active")
        return {"customer": _public_customer(customer)}
    except HTTPException:
        raise
    except psycopg.Error as exc:
        raise HTTPException(status_code=503, detail="Could not load customer account") from exc


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
