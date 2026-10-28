"""Owner-controlled user and role administration."""
from typing import Literal

import psycopg
from fastapi import APIRouter, Depends, HTTPException
from psycopg.rows import dict_row
from pydantic import BaseModel, Field, field_validator

from app.api.v1.auth import _password_hash, current_user
from app.core.config import settings

router = APIRouter(prefix="/users", tags=["user administration"])
Role = Literal["owner", "admin", "manager", "staff", "viewer"]


class UserCreate(BaseModel):
    email: str = Field(min_length=3, max_length=254)
    full_name: str = Field(min_length=1, max_length=160)
    password: str = Field(min_length=12, max_length=128)
    role: Role = "staff"

    @field_validator("email")
    @classmethod
    def normalize_email(cls, value):
        value = value.strip().lower()
        if value.count("@") != 1 or "." not in value.rsplit("@", 1)[-1] or " " in value:
            raise ValueError("Enter a valid email address")
        return value

    @field_validator("full_name")
    @classmethod
    def validate_name(cls, value):
        value = value.strip()
        if not value:
            raise ValueError("Full name is required")
        return value


class UserUpdate(BaseModel):
    full_name: str | None = Field(default=None, min_length=1, max_length=160)
    role: Role | None = None
    is_active: bool | None = None

    @field_validator("full_name")
    @classmethod
    def normalize_name(cls, value):
        if value is None:
            return value
        value = value.strip()
        if not value:
            raise ValueError("Full name cannot be blank")
        return value


def _connect():
    if not settings.database_url:
        raise HTTPException(503, "User administration database is not configured")
    try:
        return psycopg.connect(settings.database_url, row_factory=dict_row, connect_timeout=3)
    except psycopg.Error as exc:
        raise HTTPException(503, "User administration database is unavailable") from exc


def _require_owner(user):
    if user.get("role") != "owner":
        raise HTTPException(403, "Only the store owner can manage user accounts and roles")


@router.get("")
def list_users(user=Depends(current_user)):
    _require_owner(user)
    try:
        with _connect() as conn:
            rows = conn.execute(
                "SELECT id,email,full_name,role,is_active,created_at,updated_at FROM app_users ORDER BY id"
            ).fetchall()
        return {"users": [dict(row) for row in rows]}
    except HTTPException:
        raise
    except psycopg.Error as exc:
        raise HTTPException(503, "Unable to read users; verify migration 007_access_control.sql") from exc


@router.post("", status_code=201)
def create_user(payload: UserCreate, user=Depends(current_user)):
    _require_owner(user)
    try:
        with _connect() as conn:
            row = conn.execute(
                """INSERT INTO app_users (email, full_name, password_hash, role)
                   VALUES (%s, %s, %s, %s)
                   RETURNING id,email,full_name,role,is_active,created_at,updated_at""",
                (payload.email, payload.full_name, _password_hash(payload.password), payload.role),
            ).fetchone()
        return {"user": dict(row)}
    except psycopg.errors.UniqueViolation as exc:
        raise HTTPException(409, "An account with this email already exists") from exc
    except HTTPException:
        raise
    except psycopg.Error as exc:
        raise HTTPException(503, "Unable to create user; verify migration 007_access_control.sql") from exc


@router.patch("/{user_id}")
def update_user(user_id: int, payload: UserUpdate, user=Depends(current_user)):
    _require_owner(user)
    if payload.full_name is None and payload.role is None and payload.is_active is None:
        raise HTTPException(422, "Provide at least one field to update")
    if user_id == user["id"] and payload.is_active is False:
        raise HTTPException(409, "You cannot deactivate your own signed-in account")
    if user_id == user["id"] and payload.role is not None and payload.role != "owner":
        raise HTTPException(409, "You cannot remove your own owner role")
    try:
        with _connect() as conn:
            target = conn.execute(
                "SELECT id,role,is_active FROM app_users WHERE id=%s FOR UPDATE", (user_id,)
            ).fetchone()
            if not target:
                raise HTTPException(404, "User not found")
            removes_active_owner = (
                target["role"] == "owner" and target["is_active"]
                and (payload.role is not None and payload.role != "owner" or payload.is_active is False)
            )
            if removes_active_owner:
                owners = conn.execute(
                    "SELECT count(*) AS total FROM app_users WHERE role='owner' AND is_active=TRUE"
                ).fetchone()["total"]
                if owners <= 1:
                    raise HTTPException(409, "The last active owner cannot be demoted or deactivated")
            fields = {key: value for key, value in payload.model_dump(exclude_unset=True).items() if value is not None}
            assignments = []
            values = []
            for field in ("full_name", "role", "is_active"):
                if field in fields:
                    assignments.append(f"{field}=%s")
                    values.append(fields[field])
            assignments.append("updated_at=now()")
            values.append(user_id)
            row = conn.execute(
                f"UPDATE app_users SET {', '.join(assignments)} WHERE id=%s "
                "RETURNING id,email,full_name,role,is_active,created_at,updated_at",
                values,
            ).fetchone()
            if payload.is_active is False:
                conn.execute(
                    "UPDATE app_user_sessions SET revoked_at=now() WHERE user_id=%s AND revoked_at IS NULL",
                    (user_id,),
                )
        return {"user": dict(row)}
    except HTTPException:
        raise
    except psycopg.Error as exc:
        raise HTTPException(503, "Unable to update user account") from exc
