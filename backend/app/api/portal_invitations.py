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
from app.services.identity import IdentityService
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
    representative_name: str | None = Field(default=None, min_length=2, max_length=200)


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
                "SELECT id,portal_type,email,supplier_id,employee_id,representative_name,expires_at,accepted_at,revoked_at,created_at "
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
    if payload.portal_type == "vendor" and not (payload.representative_name or "").strip():
        raise HTTPException(422, "Enter the authorised representative’s full name")
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
                    full_name = payload.representative_name.strip()
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
                    "INSERT INTO portal_invitations(portal_type,email,supplier_id,employee_id,representative_name,token_hash,expires_at,invited_by_user_id) "
                    "VALUES(%s,%s,%s,%s,%s,%s,%s,%s)",
                    (payload.portal_type, email, supplier_id, employee_id, (payload.representative_name or full_name).strip(), token_hash, expires_at, actor_id),
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


def _ensure_employee_portal_identity(conn, identity, employee_id: int, user_id: int, email: str, full_name: str) -> int:
    """Reuse the employee's HR-created SBID when activating its portal login."""
    employee_party = conn.execute(
        "SELECT p.id FROM identity_profiles ip "
        "JOIN identity_parties p ON p.id=ip.party_id "
        "WHERE ip.profile_type='employee' AND ip.employee_id=%s "
        "AND ip.status='active' AND p.status='active' FOR UPDATE OF p",
        (employee_id,),
    ).fetchone()
    if employee_party:
        party_id = employee_party["id"]
    else:
        party = identity.create_party(
            party_type="individual", display_name=full_name,
            reason="Legacy employee portal invitation accepted",
        )
        party_id = party["id"]
        identity.link_profile(
            party_id=party_id, profile_type="employee", source_id=employee_id,
            link_method="verified_invitation",
            reason="Legacy employee portal identity backfill",
        )

    existing_login = conn.execute(
        "SELECT party_id,status FROM identity_auth_accounts WHERE app_user_id=%s",
        (user_id,),
    ).fetchone()
    if existing_login:
        if existing_login["party_id"] != party_id or existing_login["status"] != "active":
            raise HTTPException(409, "This login is already linked to another or inactive identity")
    else:
        identity.link_auth_account(
            party_id=party_id, account_type="staff", source_id=user_id,
            link_method="verified_invitation",
        )

    normalized_email = (email or "").strip().lower()
    if normalized_email:
        existing_contact = conn.execute(
            "SELECT id FROM identity_contacts WHERE party_id=%s AND contact_type='email' "
            "AND normalized_value=%s AND valid_to IS NULL LIMIT 1",
            (party_id, normalized_email),
        ).fetchone()
        if not existing_contact:
            identity.add_contact(
                party_id=party_id, contact_type="email",
                value=normalized_email, source="employee_invitation",
            )
    return party_id


@router.post("/accept", status_code=201)
def accept_invitation(payload: InvitationAccept):
    if len(settings.jwt_secret_key) < 32:
        raise HTTPException(503, "Authentication is not configured")
    try:
        with _connect() as conn:
            with conn.transaction():
                invitation = conn.execute(
                    "SELECT id,portal_type,email,supplier_id,employee_id,representative_name,expires_at,accepted_at,revoked_at "
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
                    full_name = (invitation["representative_name"] or "").strip()
                    if len(full_name) < 2:
                        raise HTTPException(409, "This vendor invitation has no authorised representative name; issue a new invitation")
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
                identity = IdentityService(conn)
                if invitation["portal_type"] == "vendor":
                    organisation = conn.execute(
                        "SELECT p.id,p.display_name FROM identity_profiles ip JOIN identity_parties p ON p.id=ip.party_id "
                        "WHERE ip.profile_type='vendor_organisation' AND ip.supplier_id=%s AND ip.status='active' FOR UPDATE OF p",
                        (invitation["supplier_id"],),
                    ).fetchone()
                    if organisation is None:
                        supplier = conn.execute("SELECT name FROM suppliers WHERE id=%s", (invitation["supplier_id"],)).fetchone()
                        organisation = identity.create_party(party_type="organisation", display_name=supplier["name"], reason="Vendor portal invitation accepted")
                        identity.link_profile(party_id=organisation["id"], profile_type="vendor_organisation", source_id=invitation["supplier_id"], link_method="verified_invitation")
                    representative = identity.create_party(party_type="individual", display_name=full_name, reason="Vendor representative accepted invitation")
                    identity.link_auth_account(party_id=representative["id"], account_type="staff", source_id=user["id"], link_method="verified_invitation")
                    identity.add_contact(party_id=representative["id"], contact_type="email", value=invitation["email"], source="vendor_invitation")
                    identity.create_relationship(from_party_id=representative["id"], to_party_id=organisation["id"], relationship_type="authorised_vendor_user", scope={"supplier_id": invitation["supplier_id"], "portal_access": True}, reason="Accepted vendor portal invitation")
                    conn.execute(
                        "INSERT INTO vendor_portal_users(user_id,supplier_id) VALUES(%s,%s)",
                        (user["id"], invitation["supplier_id"]),
                    )
                else:
                    _ensure_employee_portal_identity(
                        conn, identity, invitation["employee_id"], user["id"],
                        invitation["email"], full_name,
                    )
                    updated_employee = conn.execute(
                        "UPDATE hr_employees SET user_id=%s,updated_at=now() "
                        "WHERE id=%s AND user_id IS NULL RETURNING id",
                        (user["id"], invitation["employee_id"]),
                    ).fetchone()
                    if updated_employee is None:
                        raise HTTPException(409, "This employee was linked to a login account by another activation")
                conn.execute("UPDATE portal_invitations SET accepted_at=now() WHERE id=%s", (invitation["id"],))
        return {"status": "activated", "portal_type": invitation["portal_type"], "user": user}
    except HTTPException:
        raise
    except psycopg.Error as exc:
        if getattr(exc, "sqlstate", None) == "23505":
            raise HTTPException(409, "An account or portal link already exists for this email") from exc
        raise HTTPException(503, "Unable to activate portal account") from exc
