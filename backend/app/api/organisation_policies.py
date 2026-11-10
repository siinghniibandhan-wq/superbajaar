"""Authenticated administration of organisation-scoped operational policies."""
from datetime import date
from typing import Any

import psycopg
from fastapi import APIRouter, HTTPException, Query, Request
from psycopg.rows import dict_row
from pydantic import BaseModel, Field

from app.core.config import settings
from app.services.organisation_policy import (
    PolicyConfigurationError, validate_inventory_policy, validate_purchase_policy,
)

router = APIRouter(prefix="/organisation-policies", tags=["organisation-policies"])


def _connect():
    if not settings.database_url:
        raise HTTPException(503, "Organisation policy database is not configured")
    try:
        return psycopg.connect(settings.database_url, row_factory=dict_row, connect_timeout=3)
    except psycopg.Error as exc:
        raise HTTPException(503, "Organisation policy database is unavailable") from exc


def _actor(request: Request) -> tuple[int, str, str]:
    user_id = getattr(request.state, "user_id", None)
    email = getattr(request.state, "user_email", None)
    role = getattr(request.state, "role", None)
    if not user_id or not email or not role:
        raise HTTPException(401, "An authenticated staff session is required")
    return int(user_id), str(email), str(role)


def _policy_admin(request: Request) -> tuple[int, str, str]:
    actor = _actor(request)
    if actor[2] not in {"owner", "admin"}:
        raise HTTPException(403, "Organisation policy administration permission is required")
    return actor


def _validate(domain: str, config: dict[str, Any]) -> None:
    try:
        if domain == "purchase":
            validate_purchase_policy(config)
        elif domain == "inventory":
            validate_inventory_policy(config)
        else:
            raise PolicyConfigurationError("Policy domain must be purchase or inventory")
    except PolicyConfigurationError as exc:
        raise HTTPException(422, str(exc)) from exc


class PolicyCreate(BaseModel):
    establishment_id: int = Field(gt=0)
    domain: str = Field(pattern="^(purchase|inventory)$")
    version_label: str = Field(min_length=1, max_length=120)
    effective_from: date
    effective_to: date | None = None
    policy_config: dict[str, Any]

    def validate_dates(self):
        if self.effective_to and self.effective_to < self.effective_from:
            raise ValueError("effective_to cannot be earlier than effective_from")
        if not self.version_label.strip():
            raise ValueError("version_label cannot be blank")
        return self


@router.get("")
def list_policies(
    request: Request,
    establishment_id: int | None = Query(default=None, gt=0),
    domain: str | None = Query(default=None, pattern="^(purchase|inventory)$"),
):
    actor_id, _, actor_role = _actor(request)
    try:
        with _connect() as conn:
            rows = conn.execute(
                "SELECT p.id,p.establishment_id,e.code AS establishment_code,e.display_name AS establishment_name,"
                "p.domain,p.version_label,p.effective_from,p.effective_to,p.policy_config,p.status,"
                "p.created_by_user_id,p.activated_by_user_id,p.activated_at,p.created_at,p.updated_at "
                "FROM organisation_policy_versions p JOIN hr_establishments e ON e.id=p.establishment_id "
                "WHERE (%s::bigint IS NULL OR p.establishment_id=%s::bigint) "
                "AND (%s::text IS NULL OR p.domain=%s::text) "
                "AND (%s IN ('owner','admin') OR p.establishment_id IN ("
                "SELECT esp.establishment_id FROM hr_employees he "
                "JOIN hr_employee_statutory_profiles esp ON esp.employee_id=he.id WHERE he.user_id=%s)) "
                "ORDER BY p.establishment_id,p.domain,p.created_at DESC",
                (establishment_id, establishment_id, domain, domain, actor_role, actor_id),
            ).fetchall()
        return {"items": rows}
    except psycopg.Error as exc:
        raise HTTPException(503, "Unable to read organisation policies") from exc


@router.post("", status_code=201)
def create_policy(payload: PolicyCreate, request: Request):
    actor, email, role = _policy_admin(request)
    if payload.effective_to and payload.effective_to < payload.effective_from:
        raise HTTPException(422, "effective_to cannot be earlier than effective_from")
    if not payload.version_label.strip():
        raise HTTPException(422, "version_label cannot be blank")
    try:
        with _connect() as conn:
            with conn.transaction():
                establishment = conn.execute(
                    "SELECT id FROM hr_establishments WHERE id=%s AND is_active=TRUE FOR SHARE",
                    (payload.establishment_id,),
                ).fetchone()
                if not establishment:
                    raise HTTPException(404, "Active establishment not found")
                row = conn.execute(
                    "INSERT INTO organisation_policy_versions "
                    "(establishment_id,domain,version_label,effective_from,effective_to,policy_config,created_by_user_id) "
                    "VALUES(%s,%s,%s,%s,%s,%s::jsonb,%s) RETURNING *",
                    (payload.establishment_id,payload.domain,payload.version_label.strip(),
                     payload.effective_from,payload.effective_to,
                     __import__("json").dumps(payload.policy_config),actor),
                ).fetchone()
                conn.execute(
                    "INSERT INTO organisation_policy_audit_events "
                    "(policy_version_id,event_type,actor_user_id,actor_email,actor_role,event_payload) "
                    "VALUES(%s,'created',%s,%s,%s,%s::jsonb)",
                    (row["id"],actor,email,role,__import__("json").dumps({"domain":payload.domain,"version_label":payload.version_label.strip()})),
                )
        return row
    except HTTPException:
        raise
    except psycopg.Error as exc:
        raise HTTPException(503, "Unable to create organisation policy") from exc


@router.post("/{policy_id}/validate")
def validate_policy(policy_id: int, request: Request):
    actor, email, role = _policy_admin(request)
    try:
        with _connect() as conn:
            with conn.transaction():
                row = conn.execute(
                    "SELECT * FROM organisation_policy_versions WHERE id=%s FOR UPDATE",
                    (policy_id,),
                ).fetchone()
                if not row:
                    raise HTTPException(404, "Policy version not found")
                if row["status"] != "draft":
                    raise HTTPException(409, "Only draft policies can be validated")
                _validate(row["domain"], row["policy_config"])
                conn.execute(
                    "INSERT INTO organisation_policy_audit_events "
                    "(policy_version_id,event_type,actor_user_id,actor_email,actor_role,event_payload) "
                    "VALUES(%s,'validated',%s,%s,%s,'{}'::jsonb)",
                    (policy_id,actor,email,role),
                )
        return {"id": policy_id, "valid": True, "message": "Policy configuration is valid"}
    except HTTPException:
        raise
    except psycopg.Error as exc:
        raise HTTPException(503, "Unable to validate organisation policy") from exc


@router.post("/{policy_id}/activate")
def activate_policy(policy_id: int, request: Request):
    actor, email, role = _policy_admin(request)
    try:
        with _connect() as conn:
            with conn.transaction():
                row = conn.execute(
                    "SELECT * FROM organisation_policy_versions WHERE id=%s FOR UPDATE",
                    (policy_id,),
                ).fetchone()
                if not row:
                    raise HTTPException(404, "Policy version not found")
                if row["status"] != "draft":
                    raise HTTPException(409, "Only draft policies can be activated")
                if row["effective_from"] > date.today() or (row["effective_to"] and row["effective_to"] < date.today()):
                    raise HTTPException(422, "Policy must be within its effective date range before activation")
                _validate(row["domain"], row["policy_config"])
                conn.execute(
                    "UPDATE organisation_policy_versions SET status='retired',updated_at=now() "
                    "WHERE establishment_id=%s AND domain=%s AND status='active'",
                    (row["establishment_id"],row["domain"]),
                )
                activated = conn.execute(
                    "UPDATE organisation_policy_versions SET status='active',activated_by_user_id=%s,"
                    "activated_at=now(),updated_at=now() WHERE id=%s RETURNING *",
                    (actor,policy_id),
                ).fetchone()
                conn.execute(
                    "INSERT INTO organisation_policy_audit_events "
                    "(policy_version_id,event_type,actor_user_id,actor_email,actor_role,event_payload) "
                    "VALUES(%s,'activated',%s,%s,%s,%s::jsonb)",
                    (policy_id,actor,email,role,__import__("json").dumps({"effective_from":str(row["effective_from"])})),
                )
        return activated
    except HTTPException:
        raise
    except psycopg.Error as exc:
        raise HTTPException(503, "Unable to activate organisation policy") from exc


@router.get("/{policy_id}/history")
def policy_history(policy_id: int, request: Request):
    actor_id, _, actor_role = _actor(request)
    try:
        with _connect() as conn:
            policy=conn.execute(
                "SELECT id,establishment_id,domain,version_label,status FROM organisation_policy_versions WHERE id=%s",
                (policy_id,),
            ).fetchone()
            if not policy:
                raise HTTPException(404,"Policy version not found")
            if actor_role not in {"owner","admin"}:
                membership=conn.execute(
                    "SELECT EXISTS(SELECT 1 FROM hr_employees he "
                    "JOIN hr_employee_statutory_profiles esp ON esp.employee_id=he.id "
                    "WHERE he.user_id=%s AND esp.establishment_id=%s) AS allowed",
                    (actor_id,policy["establishment_id"]),
                ).fetchone()
                if not membership or not membership["allowed"]:
                    raise HTTPException(403,"You are not assigned to this legal establishment")
            audit=conn.execute(
                "SELECT id,event_type,actor_user_id,actor_email,actor_role,reason,event_payload,created_at "
                "FROM organisation_policy_audit_events WHERE policy_version_id=%s ORDER BY created_at DESC,id DESC",
                (policy_id,),
            ).fetchall()
            decisions=conn.execute(
                "SELECT id,domain,document_type,document_id,document_revision,stage_sequence,decision,"
                "actor_user_id,actor_email,actor_role,reason,evaluation_snapshot,created_at "
                "FROM organisation_policy_decisions WHERE policy_version_id=%s ORDER BY created_at DESC,id DESC",
                (policy_id,),
            ).fetchall()
        return {"policy":policy,"audit_events":audit,"decisions":decisions}
    except HTTPException:
        raise
    except psycopg.Error as exc:
        raise HTTPException(503,"Unable to read organisation policy history") from exc


def load_active_policy(conn, establishment_id: int, domain: str, effective_at: date | None = None):
    effective_at = effective_at or date.today()
    rows = conn.execute(
        "SELECT * FROM organisation_policy_versions WHERE establishment_id=%s AND domain=%s "
        "AND status='active' AND effective_from<=%s AND (effective_to IS NULL OR effective_to>=%s) "
        "ORDER BY id FOR SHARE",
        (establishment_id,domain,effective_at,effective_at),
    ).fetchall()
    if len(rows) != 1:
        raise HTTPException(409, "No unique active organisation policy applies; configure and activate the required policy")
    return rows[0]
