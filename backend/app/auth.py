import hashlib
import hmac
import json
import os
import secrets
import time
from functools import lru_cache
from typing import Any
from urllib.request import Request, urlopen

import psycopg
from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel, Field
from psycopg.rows import dict_row

router = APIRouter(prefix="/api/auth", tags=["authentication"])


@lru_cache(maxsize=8)
def _read_ssm_parameter(name: str) -> str:
    """Read a deployment secret from Parameter Store using the EC2 instance role."""
    import boto3

    region = os.getenv("AWS_REGION") or os.getenv("AWS_DEFAULT_REGION") or boto3.Session().region_name
    if not region:
        # EC2 does not always export its region to the application environment.
        token_request = Request(
            "http://169.254.169.254/latest/api/token",
            data=b"",
            headers={"X-aws-ec2-metadata-token-ttl-seconds": "60"},
            method="PUT",
        )
        with urlopen(token_request, timeout=2) as response:
            metadata_token = response.read().decode()
        document_request = Request(
            "http://169.254.169.254/latest/dynamic/instance-identity/document",
            headers={"X-aws-ec2-metadata-token": metadata_token},
        )
        with urlopen(document_request, timeout=2) as response:
            region = json.loads(response.read().decode())["region"]
    client = boto3.client("ssm", region_name=region)
    path = f"/superbajaar/{name}"
    return client.get_parameter(Name=path, WithDecryption=True)["Parameter"]["Value"]


def _setting(name: str) -> str:
    """Prefer an explicitly injected environment value; otherwise use AWS SSM."""
    value = os.getenv(name, "").strip()
    if value:
        return value
    try:
        return _read_ssm_parameter(name).strip()
    except Exception:
        # Never log parameter values or cloud credentials; callers return safe config errors.
        return ""


ROLES = {"super_admin", "admin", "staff", "customer"}
STATUSES = {"active", "suspended", "disabled"}


def _db() -> str:
    value = os.getenv("DATABASE_URL", "").strip()
    if not value:
        raise HTTPException(status_code=503, detail="Database is not configured")
    return value


def _hash_password(password: str, salt: bytes | None = None) -> str:
    salt = salt or secrets.token_bytes(16)
    derived = hashlib.scrypt(password.encode(), salt=salt, n=2**14, r=8, p=1, dklen=32)
    return salt.hex() + "$" + derived.hex()


def _check_password(password: str, encoded: str) -> bool:
    try:
        salt_hex, expected = encoded.split("$", 1)
        actual = _hash_password(password, bytes.fromhex(salt_hex)).split("$", 1)[1]
        return hmac.compare_digest(actual, expected)
    except (ValueError, TypeError):
        return False


def _secret() -> bytes:
    value = _setting("AUTH_TOKEN_SECRET")
    if len(value) < 32:
        raise HTTPException(status_code=503, detail="AUTH_TOKEN_SECRET must be configured with at least 32 characters")
    return value.encode()


def _token(user_id: int) -> str:
    payload = json.dumps({"sub": user_id, "exp": int(time.time()) + 43200}, separators=(",", ":")).encode().hex()
    signature = hmac.new(_secret(), payload.encode(), hashlib.sha256).hexdigest()
    return payload + "." + signature


def _current(authorization: str | None) -> dict[str, Any]:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Sign in required")
    try:
        payload, signature = authorization[7:].split(".", 1)
        expected = hmac.new(_secret(), payload.encode(), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(signature, expected):
            raise ValueError()
        data = json.loads(bytes.fromhex(payload))
        if int(data["exp"]) < int(time.time()):
            raise ValueError()
        user_id = int(data["sub"])
    except (ValueError, KeyError, TypeError, json.JSONDecodeError):
        raise HTTPException(status_code=401, detail="Invalid or expired session")
    with psycopg.connect(_db(), row_factory=dict_row, connect_timeout=8) as conn:
        user = conn.execute("SELECT id,email,full_name,role,status,created_at,last_login FROM app_users WHERE id=%s", (user_id,)).fetchone()
    if not user or user["status"] != "active":
        raise HTTPException(status_code=401, detail="Account is unavailable")
    return user


def _require(authorization: str | None, roles: set[str]) -> dict[str, Any]:
    user = _current(authorization)
    if user["role"] not in roles:
        raise HTTPException(status_code=403, detail="Insufficient permissions")
    return user


def _ensure_user_schema(conn: Any) -> None:
    """Create only the isolated Super Bajaar account tables when first needed.

    This is independent of Odoo and does not alter catalogue or product tables.
    CREATE TABLE IF NOT EXISTS is safe to repeat on subsequent bootstrap attempts.
    """
    conn.execute("""
        CREATE TABLE IF NOT EXISTS app_users (
            id BIGSERIAL PRIMARY KEY,
            email TEXT NOT NULL UNIQUE,
            full_name TEXT NOT NULL,
            password_hash TEXT NOT NULL,
            role TEXT NOT NULL DEFAULT 'customer'
                CHECK (role IN ('super_admin', 'admin', 'staff', 'customer')),
            status TEXT NOT NULL DEFAULT 'active'
                CHECK (status IN ('active', 'suspended', 'disabled')),
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            last_login TIMESTAMPTZ
        )
    """)
    conn.execute("CREATE UNIQUE INDEX IF NOT EXISTS app_users_email_lower_unique ON app_users (lower(email))")
    conn.execute("CREATE INDEX IF NOT EXISTS app_users_role_status_idx ON app_users (role, status)")
    conn.execute("""
        CREATE TABLE IF NOT EXISTS user_audit_log (
            id BIGSERIAL PRIMARY KEY,
            actor_user_id BIGINT REFERENCES app_users(id) ON DELETE SET NULL,
            target_user_id BIGINT REFERENCES app_users(id) ON DELETE SET NULL,
            action TEXT NOT NULL,
            details JSONB NOT NULL DEFAULT '{}'::jsonb,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS user_audit_log_created_idx ON user_audit_log (created_at DESC)")
    conn.execute("CREATE INDEX IF NOT EXISTS user_audit_log_target_idx ON user_audit_log (target_user_id, created_at DESC)")


def _audit(conn: Any, actor_id: int | None, target_id: int | None, action: str, details: dict[str, Any]) -> None:
    conn.execute("INSERT INTO user_audit_log(actor_user_id,target_user_id,action,details) VALUES (%s,%s,%s,%s::jsonb)",
                 (actor_id, target_id, action, json.dumps(details)))


class RegisterInput(BaseModel):
    email: str = Field(min_length=5, max_length=254)
    full_name: str = Field(min_length=1, max_length=120)
    password: str = Field(min_length=10, max_length=200)


class LoginInput(BaseModel):
    email: str = Field(min_length=5, max_length=254)
    password: str = Field(min_length=1, max_length=200)


class BootstrapInput(BaseModel):
    email: str = Field(min_length=5, max_length=254)
    full_name: str = Field(min_length=1, max_length=120)
    password: str = Field(min_length=12, max_length=200)
    bootstrap_key: str = Field(min_length=24, max_length=300)


class UserUpdate(BaseModel):
    role: str | None = None
    status: str | None = None
    full_name: str | None = Field(default=None, min_length=1, max_length=120)


@router.post("/register", status_code=201)
def register(body: RegisterInput) -> dict[str, Any]:
    email = body.email.strip().lower()
    if "@" not in email or "." not in email.rsplit("@", 1)[-1]:
        raise HTTPException(status_code=422, detail="Enter a valid email address")
    configured_super_admin = _setting("SUPER_ADMIN_EMAIL").strip().lower()
    if configured_super_admin and hmac.compare_digest(email, configured_super_admin):
        raise HTTPException(status_code=403, detail="This email is reserved for Super Admin bootstrap")
    try:
        with psycopg.connect(_db(), row_factory=dict_row, connect_timeout=8) as conn:
            row = conn.execute(
                "INSERT INTO app_users(email,full_name,password_hash,role,status) VALUES (%s,%s,%s,'customer','active') RETURNING id,email,full_name,role,status",
                (email, body.full_name.strip(), _hash_password(body.password)),
            ).fetchone()
            _audit(conn, row["id"], row["id"], "account.registered", {})
            return {"user": row, "access_token": _token(row["id"]), "token_type": "bearer"}
    except psycopg.errors.UniqueViolation:
        raise HTTPException(status_code=409, detail="An account with this email already exists")
    except psycopg.Error as exc:
        raise HTTPException(status_code=503, detail="User storage is not configured; apply schema 006") from exc


@router.post("/login")
def login(body: LoginInput) -> dict[str, Any]:
    email = body.email.strip().lower()
    try:
        with psycopg.connect(_db(), row_factory=dict_row, connect_timeout=8) as conn:
            user = conn.execute("SELECT * FROM app_users WHERE email=%s", (email,)).fetchone()
            if not user or not _check_password(body.password, user["password_hash"]):
                raise HTTPException(status_code=401, detail="Email or password is incorrect")
            if user["status"] != "active":
                raise HTTPException(status_code=403, detail="Account is not active")
            conn.execute("UPDATE app_users SET last_login=now() WHERE id=%s", (user["id"],))
            _audit(conn, user["id"], user["id"], "session.created", {})
            safe_user = {key: user[key] for key in ("id", "email", "full_name", "role", "status")}
            return {"user": safe_user, "access_token": _token(user["id"]), "token_type": "bearer"}
    except HTTPException:
        raise
    except psycopg.Error as exc:
        raise HTTPException(status_code=503, detail="User storage is not configured; apply schema 006") from exc


@router.post("/bootstrap", status_code=201)
def bootstrap(body: BootstrapInput) -> dict[str, Any]:
    expected_key = _setting("SUPER_ADMIN_BOOTSTRAP_KEY")
    configured_email = _setting("SUPER_ADMIN_EMAIL").strip().lower()
    if len(expected_key) < 24 or not configured_email:
        raise HTTPException(status_code=503, detail="Configure SUPER_ADMIN_EMAIL and SUPER_ADMIN_BOOTSTRAP_KEY first")
    if not hmac.compare_digest(body.bootstrap_key, expected_key) or body.email.strip().lower() != configured_email:
        raise HTTPException(status_code=403, detail="Bootstrap credentials do not match server configuration")
    try:
        with psycopg.connect(_db(), row_factory=dict_row, connect_timeout=8) as conn:
            _ensure_user_schema(conn)
            conn.execute("LOCK TABLE app_users IN EXCLUSIVE MODE")
            if conn.execute("SELECT id FROM app_users WHERE role='super_admin' LIMIT 1").fetchone():
                raise HTTPException(status_code=409, detail="Super Admin has already been initialized")
            row = conn.execute(
                "INSERT INTO app_users(email,full_name,password_hash,role,status) VALUES (%s,%s,%s,'super_admin','active') RETURNING id,email,full_name,role,status",
                (configured_email, body.full_name.strip(), _hash_password(body.password)),
            ).fetchone()
            _audit(conn, row["id"], row["id"], "super_admin.bootstrapped", {})
            return {"user": row, "access_token": _token(row["id"]), "token_type": "bearer"}
    except HTTPException:
        raise
    except psycopg.errors.UniqueViolation:
        raise HTTPException(status_code=409, detail="This email already has an account; contact an administrator")
    except psycopg.Error as exc:
        raise HTTPException(status_code=503, detail="User storage is not configured; apply schema 006") from exc


@router.get("/me")
def me(authorization: str | None = Header(default=None)) -> dict[str, Any]:
    return {"user": _current(authorization)}


@router.get("/users")
def list_users(authorization: str | None = Header(default=None), search: str = "") -> dict[str, Any]:
    _require(authorization, {"super_admin", "admin"})
    try:
        with psycopg.connect(_db(), row_factory=dict_row, connect_timeout=8) as conn:
            rows = conn.execute(
                """SELECT id,email,full_name,role,status,created_at,last_login
                   FROM app_users WHERE email ILIKE %s OR full_name ILIKE %s
                   ORDER BY created_at DESC LIMIT 200""",
                (f"%{search[:100]}%", f"%{search[:100]}%"),
            ).fetchall()
            return {"items": rows}
    except psycopg.Error as exc:
        raise HTTPException(status_code=503, detail="User storage is not configured; apply schema 006") from exc


@router.patch("/users/{user_id}")
def update_user(user_id: int, body: UserUpdate, authorization: str | None = Header(default=None)) -> dict[str, Any]:
    actor = _require(authorization, {"super_admin"})
    changes = body.model_dump(exclude_unset=True, exclude_none=True)
    if not changes:
        raise HTTPException(status_code=422, detail="Provide at least one field")
    if "role" in changes and changes["role"] not in ROLES:
        raise HTTPException(status_code=422, detail="Invalid role")
    if "role" in changes and changes["role"] == "super_admin":
        configured_super_admin = _setting("SUPER_ADMIN_EMAIL").strip().lower()
        try:
            with psycopg.connect(_db(), row_factory=dict_row, connect_timeout=8) as conn:
                target = conn.execute("SELECT email FROM app_users WHERE id=%s", (user_id,)).fetchone()
        except psycopg.Error as exc:
            raise HTTPException(status_code=503, detail="Could not verify Super Admin identity") from exc
        if not target or not configured_super_admin or target["email"].strip().lower() != configured_super_admin:
            raise HTTPException(status_code=403, detail="Only the configured Super Admin email can hold this role")
    if "status" in changes and changes["status"] not in STATUSES:
        raise HTTPException(status_code=422, detail="Invalid account status")
    if user_id == actor["id"] and (changes.get("role", actor["role"]) != "super_admin" or changes.get("status", actor["status"]) != "active"):
        raise HTTPException(status_code=409, detail="You cannot remove or disable your own Super Admin account")
    allowed = {"role", "status", "full_name"}
    assignments = [f"{key} = %s" for key in changes if key in allowed]
    values = [changes[key] for key in changes if key in allowed]
    assignments.append("updated_at = now()")
    try:
        with psycopg.connect(_db(), row_factory=dict_row, connect_timeout=8) as conn:
            row = conn.execute(
                f"UPDATE app_users SET {', '.join(assignments)} WHERE id=%s RETURNING id,email,full_name,role,status,created_at,last_login",
                (*values, user_id),
            ).fetchone()
            if not row:
                raise HTTPException(status_code=404, detail="User not found")
            _audit(conn, actor["id"], user_id, "user.updated", changes)
            return {"user": row}
    except HTTPException:
        raise
    except psycopg.Error as exc:
        raise HTTPException(status_code=503, detail="Could not update user") from exc


@router.get("/audit")
def audit_log(authorization: str | None = Header(default=None)) -> dict[str, Any]:
    _require(authorization, {"super_admin"})
    try:
        with psycopg.connect(_db(), row_factory=dict_row, connect_timeout=8) as conn:
            rows = conn.execute(
                """SELECT id,actor_user_id,target_user_id,action,details,created_at
                   FROM user_audit_log ORDER BY created_at DESC LIMIT 200"""
            ).fetchall()
            return {"items": rows}
    except psycopg.Error as exc:
        raise HTTPException(status_code=503, detail="Audit storage is not configured; apply schema 006") from exc
