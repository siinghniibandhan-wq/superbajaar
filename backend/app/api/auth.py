"""Authentication endpoints. Requires migration 007 and a strong JWT_SECRET_KEY."""
from datetime import datetime, timedelta, timezone
import base64
import hashlib
import hmac
import json
import secrets

import psycopg
from fastapi import APIRouter, Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from psycopg.rows import dict_row
from pydantic import BaseModel, Field, field_validator

from app.core.config import settings

router = APIRouter(prefix="/auth", tags=["authentication"])
bearer = HTTPBearer(auto_error=False)
TOKEN_TTL_HOURS = 8


def _connect():
    if not settings.database_url:
        raise HTTPException(503, "Authentication database is not configured")
    try:
        return psycopg.connect(settings.database_url, row_factory=dict_row, connect_timeout=3)
    except psycopg.Error as exc:
        raise HTTPException(503, "Authentication database is unavailable") from exc


def _b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode().rstrip("=")


def _password_hash(password: str) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.scrypt(password.encode(), salt=salt, n=16384, r=8, p=1)
    return "scrypt$" + _b64(salt) + "$" + _b64(digest)


def _password_matches(password: str, encoded: str) -> bool:
    try:
        algorithm, salt_text, digest_text = encoded.split("$", 2)
        if algorithm != "scrypt":
            return False
        salt = base64.urlsafe_b64decode(salt_text + "=" * (-len(salt_text) % 4))
        expected = base64.urlsafe_b64decode(digest_text + "=" * (-len(digest_text) % 4))
        actual = hashlib.scrypt(password.encode(), salt=salt, n=16384, r=8, p=1)
        return hmac.compare_digest(actual, expected)
    except (ValueError, TypeError):
        return False


def _sign(payload: dict) -> str:
    secret = settings.jwt_secret_key
    if len(secret) < 32:
        raise HTTPException(503, "Authentication is not configured: set JWT_SECRET_KEY to a random secret of at least 32 characters")
    header = _b64(json.dumps({"alg": "HS256", "typ": "JWT"}, separators=(",", ":")).encode())
    body = _b64(json.dumps(payload, separators=(",", ":")).encode())
    signing_input = (header + "." + body).encode()
    signature = _b64(hmac.new(secret.encode(), signing_input, hashlib.sha256).digest())
    return header + "." + body + "." + signature


def _decode(token: str) -> dict:
    secret = settings.jwt_secret_key
    if len(secret) < 32:
        raise HTTPException(503, "Authentication is not configured")
    try:
        header, body, signature = token.split(".")
        expected = _b64(hmac.new(secret.encode(), (header + "." + body).encode(), hashlib.sha256).digest())
        if not hmac.compare_digest(signature, expected):
            raise ValueError("signature")
        meta = json.loads(base64.urlsafe_b64decode(header + "=" * (-len(header) % 4)))
        payload = json.loads(base64.urlsafe_b64decode(body + "=" * (-len(body) % 4)))
        if meta.get("alg") != "HS256" or int(payload["exp"]) <= int(datetime.now(timezone.utc).timestamp()):
            raise ValueError("expiry")
        return payload
    except (ValueError, KeyError, TypeError, json.JSONDecodeError):
        raise HTTPException(401, "Invalid or expired access token")


class LoginPayload(BaseModel):
    email: str = Field(min_length=3, max_length=254)
    password: str = Field(min_length=1, max_length=1024)

    @field_validator("email")
    @classmethod
    def normalize_email(cls, value):
        value = value.strip().lower()
        if "@" not in value or "." not in value.rsplit("@", 1)[-1] or " " in value:
            raise ValueError("Enter a valid email address")
        return value


def current_user(credentials: HTTPAuthorizationCredentials | None = Depends(bearer)):
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise HTTPException(401, "Sign in to continue")
    token = _decode(credentials.credentials)
    try:
        with _connect() as conn:
            row = conn.execute(
                "SELECT u.id,u.email,u.full_name,u.role,u.is_active FROM app_users u JOIN app_user_sessions s ON s.user_id=u.id WHERE u.id=%s AND s.token_id=%s AND s.revoked_at IS NULL AND s.expires_at>now()",
                (token.get("sub"), token.get("jti")),
            ).fetchone()
        if not row or not row["is_active"]:
            raise HTTPException(401, "Session is no longer active")
        return row
    except psycopg.Error as exc:
        raise HTTPException(503, "Authentication storage unavailable; verify migration 007") from exc


@router.post("/login")
def login(payload: LoginPayload):
    if len(settings.jwt_secret_key) < 32:
        raise HTTPException(503, "Authentication is not configured: set JWT_SECRET_KEY to a random secret of at least 32 characters")
    try:
        with _connect() as conn:
            user = conn.execute("SELECT id,email,full_name,role,password_hash,is_active FROM app_users WHERE email=%s", (payload.email,)).fetchone()
            if not user or not user["is_active"] or not _password_matches(payload.password, user["password_hash"]):
                raise HTTPException(401, "Invalid email or password")
            now = datetime.now(timezone.utc)
            expires = now + timedelta(hours=TOKEN_TTL_HOURS)
            token_id = secrets.token_urlsafe(24)
            token = _sign({"sub": str(user["id"]), "jti": token_id, "iat": int(now.timestamp()), "exp": int(expires.timestamp())})
            conn.execute("INSERT INTO app_user_sessions(user_id,token_id,expires_at) VALUES(%s,%s,%s)", (user["id"], token_id, expires))
        return {"access_token": token, "token_type": "bearer", "expires_at": expires.isoformat(), "user": {"id": user["id"], "email": user["email"], "full_name": user["full_name"], "role": user["role"]}}
    except HTTPException:
        raise
    except psycopg.Error as exc:
        raise HTTPException(503, "Authentication storage unavailable; verify migration 007") from exc


@router.get("/me")
def me(user=Depends(current_user)):
    return {"user": {key: user[key] for key in ("id", "email", "full_name", "role")}}


@router.post("/logout")
def logout(credentials: HTTPAuthorizationCredentials | None = Depends(bearer), user=Depends(current_user)):
    token = _decode(credentials.credentials)
    try:
        with _connect() as conn:
            conn.execute("UPDATE app_user_sessions SET revoked_at=now() WHERE token_id=%s AND user_id=%s AND revoked_at IS NULL", (token["jti"], user["id"]))
        return {"status": "logged_out"}
    except psycopg.Error as exc:
        raise HTTPException(503, "Unable to revoke session") from exc


USER_ROLES = {"owner", "admin", "manager", "staff", "viewer"}


def _require_user_admin(user: dict):
    if user.get("role") not in {"owner", "admin"}:
        raise HTTPException(403, "Owner or admin permission is required")
    return user


def _require_owner_for_owner_change(actor: dict, target: dict, next_role: str, next_active: bool):
    if target.get("role") == "owner" and (next_role != "owner" or not next_active):
        if actor.get("role") != "owner":
            raise HTTPException(403, "Only an owner can demote or deactivate another owner")
    return None


class UserCreate(BaseModel):
    email: str = Field(min_length=3, max_length=254)
    full_name: str = Field(min_length=1, max_length=200)
    password: str = Field(min_length=12, max_length=1024)
    role: str = "staff"

    @field_validator("email")
    @classmethod
    def normalize_user_email(cls, value):
        value = value.strip().lower()
        if "@" not in value or "." not in value.rsplit("@", 1)[-1] or " " in value:
            raise ValueError("Enter a valid email address")
        return value

    @field_validator("full_name")
    @classmethod
    def validate_user_name(cls, value):
        value = value.strip()
        if not value:
            raise ValueError("Full name cannot be blank")
        return value

    @field_validator("role")
    @classmethod
    def validate_user_role(cls, value):
        if value not in USER_ROLES:
            raise ValueError("Unsupported user role")
        return value


class UserUpdate(BaseModel):
    role: str | None = None
    is_active: bool | None = None

    @field_validator("role")
    @classmethod
    def validate_optional_user_role(cls, value):
        if value is not None and value not in USER_ROLES:
            raise ValueError("Unsupported user role")
        return value


@router.get("/users")
def list_users(user=Depends(current_user)):
    _require_user_admin(user)
    try:
        with _connect() as conn:
            rows = conn.execute(
                "SELECT id,email,full_name,role,is_active,created_at,updated_at FROM app_users ORDER BY created_at,id"
            ).fetchall()
        return {"items": rows}
    except psycopg.Error as exc:
        raise HTTPException(503, "Unable to load users; verify migration 007") from exc


@router.post("/users", status_code=201)
def create_user(payload: UserCreate, user=Depends(current_user)):
    _require_user_admin(user)
    if payload.role in {"owner", "admin"} and user["role"] != "owner":
        raise HTTPException(403, "Only an owner can create owner or admin accounts")
    try:
        with _connect() as conn:
            row = conn.execute(
                "INSERT INTO app_users(email,full_name,password_hash,role) VALUES(%s,%s,%s,%s) "
                "RETURNING id,email,full_name,role,is_active,created_at,updated_at",
                (payload.email, payload.full_name, _password_hash(payload.password), payload.role),
            ).fetchone()
        return row
    except psycopg.Error as exc:
        if getattr(exc, "sqlstate", None) == "23505":
            raise HTTPException(409, "An account with this email already exists") from exc
        raise HTTPException(503, "Unable to create user; verify migration 007") from exc


@router.patch("/users/{user_id}")
def update_user(user_id: int, payload: UserUpdate, user=Depends(current_user)):
    _require_user_admin(user)
    if payload.role is None and payload.is_active is None:
        raise HTTPException(422, "Provide role or is_active")
    if payload.role in {"owner", "admin"} and user["role"] != "owner":
        raise HTTPException(403, "Only an owner can assign owner or admin roles")
    if user_id == user["id"] and payload.is_active is False:
        raise HTTPException(409, "You cannot deactivate your own account")
    try:
        with _connect() as conn:
            with conn.transaction():
                target = conn.execute("SELECT id,role,is_active FROM app_users WHERE id=%s FOR UPDATE", (user_id,)).fetchone()
                if target is None:
                    raise HTTPException(404, "User not found")
                next_role = payload.role if payload.role is not None else target["role"]
                next_active = payload.is_active if payload.is_active is not None else target["is_active"]
                _require_owner_for_owner_change(user, target, next_role, next_active)
                if target["role"] == "owner" and (next_role != "owner" or not next_active):
                    owners = conn.execute("SELECT count(*) AS n FROM app_users WHERE role='owner' AND is_active=TRUE").fetchone()["n"]
                    if owners <= 1:
                        raise HTTPException(409, "The last active owner cannot be demoted or deactivated")
                row = conn.execute(
                    "UPDATE app_users SET role=%s,is_active=%s,updated_at=now() WHERE id=%s "
                    "RETURNING id,email,full_name,role,is_active,created_at,updated_at",
                    (next_role, next_active, user_id),
                ).fetchone()
                if not next_active:
                    conn.execute("UPDATE app_user_sessions SET revoked_at=now() WHERE user_id=%s AND revoked_at IS NULL", (user_id,))
        return row
    except HTTPException:
        raise
    except psycopg.Error as exc:
        raise HTTPException(503, "Unable to update user; verify migration 007") from exc
