"""Invitation-only provisioning for supplier and employee portal identities."""
from datetime import datetime, timedelta, timezone
from email.message import EmailMessage
import os
import smtplib
import ssl

import psycopg
from fastapi import APIRouter, HTTPException, Request
from psycopg.rows import dict_row
from pydantic import BaseModel, Field

from app.api.auth import _password_hash
from app.core.config import settings
from app.services.portal_invitation import (
    hash_invitation_token,
    invitation_is_usable,
    issue_invitation_token,
    send_resend_email,
)

router = APIRouter(prefix="/portal-invitations", tags=["portal invitations"])


def _connect():
    if not settings.database_url:
        raise HTTPException(503, "Portal invitation database is not configured")
    try:
        return psycopg.connect(settings.database_url, row_factory=dict_row, connect_timeout=3)
    except psycopg.Error as exc:
        raise HTTPException(503, "Portal invitation storage is unavailable") from exc


class InvitationCreate(BaseModel):
    portal_type: str = Field(pattern="^(vendor|employee)$")
    record_id: int = Field(gt=0)


class InvitationAccept(BaseModel):
    token: str = Field(min_length=32, max_length=256)
    password: str = Field(min_length=12, max_length=1024)


def _send_invitation(email: str, portal_type: str, invitation_url: str) -> str:
    """Send with Resend or optional SMTP; fall back to the admin's copyable link."""
    subject = "Your Super Bajaar portal invitation"
    portal_label = "Vendor" if portal_type == "vendor" else "Employee"
    body = (
        f"You have been invited to activate your Super Bajaar {portal_label} Portal.\n\n"
        f"Use this one-time link within 48 hours:\n{invitation_url}\n\n"
        "If you were not expecting this invitation, please contact Super Bajaar."
    )
    provider = os.getenv("SB_EMAIL_PROVIDER", "smtp").strip().lower()

    if provider == "resend":
        api_key = os.getenv("RESEND_API_KEY", "").strip()
        sender = os.getenv("SB_SMTP_FROM", "onboarding@resend.dev").strip()
        # Resend's shared testing sender can only deliver to the account owner's
        # verified email. Do not attempt to send portal invitations to other users
        # until a verified sending domain is configured.
        test_recipient = os.getenv("RESEND_TEST_RECIPIENT", "").strip().lower()
        if not api_key or not test_recipient or email.strip().lower() != test_recipient:
            return "copy_link"
        message_id = send_resend_email(
            api_key=api_key,
            sender=sender,
            recipient=test_recipient,
            subject=subject,
            text=body,
        )
        return "sent" if message_id else "copy_link"

    host = os.getenv("SB_SMTP_HOST", "").strip()
    sender = os.getenv("SB_SMTP_FROM", "").strip()
    if not host or not sender:
        return "copy_link"
    try:
        port = int(os.getenv("SB_SMTP_PORT", "587"))
    except ValueError:
        return "copy_link"
    username = os.getenv("SB_SMTP_USERNAME", "")
    password = os.getenv("SB_SMTP_PASSWORD", "")
    message = EmailMessage()
    message["Subject"] = subject
    message["From"] = sender
    message["To"] = email
    message.set_content(body)
    try:
        context = ssl.create_default_context()
        with smtplib.SMTP(host, port, timeout=10) as smtp:
            smtp.starttls(context=context)
            if username:
                smtp.login(username, password)
            smtp.send_message(message)
        return "sent"
    except (OSError, smtplib.SMTPException):
        return "copy_link"


@router.get("/eligible-records")
def eligible_records(request: Request, portal_type: str):
    if not getattr(request.state, "user_id", None) or getattr(request.state, "role", "") not in {"super_admin", "admin"}:
        raise HTTPException(403, "Super Admin or Admin permission is required")
    if portal_type not in {"vendor", "employee"}:
        raise HTTPException(422, "Portal type must be vendor or employee")
    try:
        with _connect() as conn:
            if portal_type == "vendor":
                rows = conn.execute(
                    "SELECT s.id,s.name AS display_name,s.email FROM suppliers s "
                    "WHERE s.is_active=TRUE AND s.email IS NOT NULL AND NOT EXISTS "
                    "(SELECT 1 FROM vendor_portal_users v JOIN app_users u ON u.id=v.user_id "
                    "WHERE v.supplier_id=s.id AND v.is_active=TRUE AND u.is_active=TRUE) "
                    "ORDER BY s.name LIMIT 500"
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT e.id,(e.first_name || ' ' || e.last_name) AS display_name,e.email "
                    "FROM hr_employees e WHERE e.status<>'terminated' AND e.user_id IS NULL "
                    "ORDER BY e.first_name,e.last_name LIMIT 500"
                ).fetchall()
        return {"items": rows}
    except psycopg.Error as exc:
        raise HTTPException(503, "Unable to load eligible portal accounts") from exc


@router.get("")
def list_invitations(request: Request):
    if not getattr(request.state, "user_id", None) or getattr(request.state, "role", "") not in {"super_admin", "admin"}:
        raise HTTPException(403, "Super Admin or Admin permission is required")
    try:
        with _connect() as conn:
            rows = conn.execute(
                "SELECT id,portal_type,email,supplier_id,employee_id,expires_at,accepted_at,revoked_at,created_at "
                "FROM portal_invitations ORDER BY created_at DESC LIMIT 200"
            ).fetchall()
        return {"items": rows}
    except psycopg.Error as exc:
        raise HTTPException(503, "Unable to load portal invitations") from exc


@router.post("/{invitation_id}/revoke")
def revoke_invitation(invitation_id: int, request: Request):
    if not getattr(request.state, "user_id", None) or getattr(request.state, "role", "") not in {"super_admin", "admin"}:
        raise HTTPException(403, "Super Admin or Admin permission is required")
    try:
        with _connect() as conn:
            row = conn.execute(
                "UPDATE portal_invitations SET revoked_at=now() "
                "WHERE id=%s AND accepted_at IS NULL AND revoked_at IS NULL AND expires_at>now() "
                "RETURNING id,portal_type,email,revoked_at",
                (invitation_id,),
            ).fetchone()
        if not row:
            raise HTTPException(409, "Invitation is no longer pending or has expired")
        return row
    except HTTPException:
        raise
    except psycopg.Error as exc:
        raise HTTPException(503, "Unable to revoke invitation") from exc


@router.post("", status_code=201)
def create_invitation(payload: InvitationCreate, request: Request):
    actor_id = getattr(request.state, "user_id", None)
    role = getattr(request.state, "role", "")
    if not actor_id or role not in {"super_admin", "admin"}:
        raise HTTPException(403, "Super Admin or Admin permission is required")
    try:
        with _connect() as conn:
            with conn.transaction():
                if payload.portal_type == "vendor":
                    record = conn.execute(
                        "SELECT id,name,email,is_active FROM suppliers WHERE id=%s FOR SHARE",
                        (payload.record_id,),
                    ).fetchone()
                    if not record or not record["is_active"]:
                        raise HTTPException(404, "Active supplier not found")
                    email = (record["email"] or "").strip().lower()
                    full_name = record["name"]
                    if not email:
                        raise HTTPException(422, "Add a supplier email before inviting its vendor user")
                    employee_id = None
                    supplier_id = record["id"]
                else:
                    record = conn.execute(
                        "SELECT id,first_name,last_name,email,status,user_id FROM hr_employees WHERE id=%s FOR UPDATE",
                        (payload.record_id,),
                    ).fetchone()
                    if not record or record["status"] == "terminated":
                        raise HTTPException(404, "Active employee not found")
                    if record["user_id"] is not None:
                        raise HTTPException(409, "This employee is already linked to a login account")
                    email = record["email"].strip().lower()
                    full_name = (record["first_name"] + " " + record["last_name"]).strip()
                    employee_id = record["id"]
                    supplier_id = None
                existing = conn.execute(
                    "SELECT id FROM app_users WHERE lower(email)=lower(%s)",
                    (email,),
                ).fetchone()
                if existing:
                    raise HTTPException(409, "This email already belongs to a login account")
                conn.execute(
                    "UPDATE portal_invitations SET revoked_at=now() WHERE lower(email)=lower(%s) "
                    "AND accepted_at IS NULL AND revoked_at IS NULL AND expires_at<=now()",
                    (email,),
                )
                pending = conn.execute(
                    "SELECT id FROM portal_invitations WHERE lower(email)=lower(%s) "
                    "AND accepted_at IS NULL AND revoked_at IS NULL",
                    (email,),
                ).fetchone()
                if pending:
                    raise HTTPException(409, "A valid invitation already exists for this email")
                raw_token, token_hash = issue_invitation_token()
                expires_at = datetime.now(timezone.utc) + timedelta(hours=48)
                conn.execute(
                    "INSERT INTO portal_invitations(portal_type,email,supplier_id,employee_id,token_hash,expires_at,invited_by_user_id) "
                    "VALUES(%s,%s,%s,%s,%s,%s,%s)",
                    (payload.portal_type, email, supplier_id, employee_id, token_hash, expires_at, actor_id),
                )
        base_url = os.getenv("SB_PORTAL_BASE_URL", "").rstrip("/")
        route = "/vendor/activate" if payload.portal_type == "vendor" else "/employee/activate"
        invitation_url = f"{base_url}{route}?token={raw_token}" if base_url else f"{route}?token={raw_token}"
        delivery = _send_invitation(email, payload.portal_type, invitation_url)
        return {
            "status": "invited",
            "portal_type": payload.portal_type,
            "email": email,
            "full_name": full_name,
            "expires_at": expires_at.isoformat(),
            "delivery_status": delivery,
            "invitation_url": invitation_url,
        }
    except HTTPException:
        raise
    except psycopg.Error as exc:
        raise HTTPException(503, "Unable to create portal invitation") from exc


@router.post("/accept", status_code=201)
def accept_invitation(payload: InvitationAccept):
    if len(settings.jwt_secret_key) < 32:
        raise HTTPException(503, "Authentication is not configured")
    try:
        with _connect() as conn:
            with conn.transaction():
                invitation = conn.execute(
                    "SELECT id,portal_type,email,supplier_id,employee_id,expires_at,accepted_at,revoked_at "
                    "FROM portal_invitations WHERE token_hash=%s FOR UPDATE",
                    (hash_invitation_token(payload.token),),
                ).fetchone()
                if not invitation or not invitation_is_usable(
                    invitation["expires_at"], invitation["accepted_at"], invitation["revoked_at"]
                ):
                    raise HTTPException(410, "This invitation is invalid, expired or already used")
                if conn.execute("SELECT id FROM app_users WHERE lower(email)=lower(%s)", (invitation["email"],)).fetchone():
                    raise HTTPException(409, "A login account already exists for this email")
                if invitation["portal_type"] == "vendor":
                    record = conn.execute(
                        "SELECT name,is_active FROM suppliers WHERE id=%s FOR UPDATE",
                        (invitation["supplier_id"],),
                    ).fetchone()
                    if not record or not record["is_active"]:
                        raise HTTPException(403, "This supplier account is inactive")
                    full_name = record["name"]
                else:
                    record = conn.execute(
                        "SELECT first_name,last_name,status,user_id FROM hr_employees WHERE id=%s FOR UPDATE",
                        (invitation["employee_id"],),
                    ).fetchone()
                    if not record or record["status"] == "terminated" or record["user_id"] is not None:
                        raise HTTPException(403, "This employee account is no longer eligible for activation")
                    full_name = (record["first_name"] + " " + record["last_name"]).strip()
                user = conn.execute(
                    "INSERT INTO app_users(email,full_name,password_hash,role,is_active) "
                    "VALUES(%s,%s,%s,'staff',TRUE) RETURNING id,email,full_name,role",
                    (invitation["email"], full_name, _password_hash(payload.password)),
                ).fetchone()
                if invitation["portal_type"] == "vendor":
                    conn.execute(
                        "INSERT INTO vendor_portal_users(user_id,supplier_id) VALUES(%s,%s)",
                        (user["id"], invitation["supplier_id"]),
                    )
                else:
                    conn.execute(
                        "UPDATE hr_employees SET user_id=%s,updated_at=now() WHERE id=%s AND user_id IS NULL",
                        (user["id"], invitation["employee_id"]),
                    )
                conn.execute("UPDATE portal_invitations SET accepted_at=now() WHERE id=%s", (invitation["id"],))
        return {"status": "activated", "portal_type": invitation["portal_type"], "user": user}
    except HTTPException:
        raise
    except psycopg.Error as exc:
        if getattr(exc, "sqlstate", None) == "23505":
            raise HTTPException(409, "An account or portal link already exists for this email") from exc
        raise HTTPException(503, "Unable to activate portal account") from exc
