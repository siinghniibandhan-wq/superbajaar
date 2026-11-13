"""Customer-owned email verification and private identity evidence APIs."""
from __future__ import annotations

import os
import secrets
from datetime import datetime, timedelta, timezone

import boto3
import psycopg
from fastapi import APIRouter, File, HTTPException, Request, UploadFile
from pydantic import BaseModel, Field
from psycopg.rows import dict_row

from app.core.config import settings
from app.services.identity import IdentityService
from app.services.identity_documents import (
    IdentityDocumentConfigurationError,
    IdentityDocumentError,
    create_identity_document_download_url,
    upload_identity_document,
)
from app.services.identity_otp import (
    OTPConfigurationError,
    OTPDeliveryError,
    deliver_otp,
    generate_otp,
    otp_digest,
    verify_otp_digest,
)

router = APIRouter(
    prefix="/customer-auth/identity-verification",
    tags=["customer identity verification"],
)


def _connect():
    if not settings.database_url:
        raise HTTPException(503, "Identity database is not configured")
    try:
        return psycopg.connect(settings.database_url, row_factory=dict_row, connect_timeout=3)
    except psycopg.Error as exc:
        raise HTTPException(503, "Identity storage is unavailable") from exc


def _customer_party(conn, customer_id: int) -> dict:
    row = conn.execute(
        """
        SELECT p.id AS party_id, p.status, p.display_name, c.email
        FROM customer_accounts c
        JOIN identity_profiles ip
          ON ip.profile_type='customer_account'
         AND ip.customer_account_id=c.id
         AND ip.status='active'
        JOIN identity_parties p ON p.id=ip.party_id
        WHERE c.id=%s AND c.is_active=TRUE
        """,
        (customer_id,),
    ).fetchone()
    if row is None or row["status"] != "active":
        raise HTTPException(409, "Your active customer identity is not available. Refresh your account and retry.")
    return row


class OTPRequestIn(BaseModel):
    purpose: str = Field(default="contact_verification", pattern=r"^contact_verification$")


class OTPVerifyIn(BaseModel):
    challenge_token: str = Field(min_length=20, max_length=160)
    code: str = Field(pattern=r"^[0-9]{6}$")


@router.post("/otp/request", status_code=202)
def request_identity_email_otp(payload: OTPRequestIn, request: Request):
    """Send a short-lived OTP only to the signed-in customer's own account email."""
    customer_id = getattr(request.state, "customer_id", None)
    if not customer_id:
        raise HTTPException(401, "Customer sign-in required")

    code = generate_otp()
    token = secrets.token_urlsafe(32)
    now = datetime.now(timezone.utc)
    try:
        with _connect() as conn:
            with conn.transaction():
                party = _customer_party(conn, customer_id)
                email = (party["email"] or "").strip().lower()
                if not email:
                    raise HTTPException(409, "Add an email address to your customer account first")
                recent = conn.execute(
                    """
                    SELECT count(*) AS total
                    FROM identity_otp_challenges
                    WHERE contact_type='email' AND normalized_contact=%s
                      AND created_at > now()-interval '1 hour'
                    """,
                    (email,),
                ).fetchone()["total"]
                if recent >= 5:
                    raise HTTPException(429, "Too many verification codes requested. Try again later.")
                digest = otp_digest(token, code)
                conn.execute(
                    """
                    INSERT INTO identity_otp_challenges
                      (challenge_token,purpose,channel,contact_type,normalized_contact,
                       otp_digest,target_party_id,expires_at)
                    VALUES (%s,'contact_verification','email','email',%s,%s,%s,%s)
                    """,
                    (token, email, digest, party["party_id"], now + timedelta(minutes=5)),
                )
        try:
            deliver_otp("email", email, code)
        except (OTPConfigurationError, OTPDeliveryError):
            with _connect() as conn:
                conn.execute("DELETE FROM identity_otp_challenges WHERE challenge_token=%s AND verified_at IS NULL", (token,))
            raise HTTPException(503, "Email verification delivery is not available. Contact support.")
        return {
            "challenge_token": token,
            "channel": "email",
            "masked_destination": email[:2] + "***@" + email.split("@")[-1],
            "expires_in_seconds": 300,
        }
    except HTTPException:
        raise
    except (psycopg.Error, OTPConfigurationError) as exc:
        raise HTTPException(503, "Unable to start email verification") from exc


@router.post("/otp/verify")
def verify_identity_email_otp(payload: OTPVerifyIn, request: Request):
    """Verify the signed-in customer's own email and record it on their SBID."""
    customer_id = getattr(request.state, "customer_id", None)
    if not customer_id:
        raise HTTPException(401, "Customer sign-in required")
    invalid_code = False
    try:
        with _connect() as conn:
            with conn.transaction():
                party = _customer_party(conn, customer_id)
                challenge = conn.execute(
                    """
                    SELECT id,normalized_contact,otp_digest,attempts,max_attempts,
                           expires_at,verified_at,consumed_at
                    FROM identity_otp_challenges
                    WHERE challenge_token=%s AND target_party_id=%s
                      AND purpose='contact_verification' AND channel='email'
                    FOR UPDATE
                    """,
                    (payload.challenge_token, party["party_id"]),
                ).fetchone()
                if challenge is None:
                    raise HTTPException(404, "Verification challenge not found")
                if challenge["consumed_at"] is not None or challenge["verified_at"] is not None:
                    raise HTTPException(409, "This verification code has already been used")
                if challenge["expires_at"] <= datetime.now(timezone.utc):
                    raise HTTPException(410, "Verification code has expired")
                if challenge["attempts"] >= challenge["max_attempts"]:
                    raise HTTPException(429, "Too many incorrect codes. Request a new code.")
                if not verify_otp_digest(payload.challenge_token, payload.code, challenge["otp_digest"]):
                    conn.execute(
                        "UPDATE identity_otp_challenges SET attempts=attempts+1 WHERE id=%s",
                        (challenge["id"],),
                    )
                    invalid_code = True
                if not invalid_code:
                    verified_at = datetime.now(timezone.utc)
                    conn.execute(
                    "UPDATE identity_otp_challenges SET verified_at=%s,consumed_at=%s WHERE id=%s",
                    (verified_at, verified_at, challenge["id"]),
                    existing = conn.execute(
                    """
                    SELECT id FROM identity_contacts
                    WHERE party_id=%s AND contact_type='email'
                      AND normalized_value=%s AND valid_to IS NULL
                    ORDER BY id DESC LIMIT 1 FOR UPDATE
                    """,
                    (party["party_id"], challenge["normalized_contact"]),
                    ).fetchone()
                    if existing:
                        conn.execute(
                        """
                        UPDATE identity_contacts
                        SET verification_status='verified',verified_at=%s,updated_at=now()
                        WHERE id=%s
                        """,
                        (verified_at, existing["id"]),
                    )
                else:
                    conn.execute(
                        """
                        INSERT INTO identity_contacts
                          (party_id,contact_type,normalized_value,display_value,
                           verification_status,verified_at,is_primary,source)
                        VALUES (%s,'email',%s,%s,'verified',%s,true,'customer_email_otp')
                        """,
                        (party["party_id"], challenge["normalized_contact"], party["email"], verified_at),
                        )
                    IdentityService(conn)._event(
                    party_id=party["party_id"],
                    event_type="contact_verified",
                    event_data={"contact_type": "email", "verification_method": "email_otp"},
                    actor_party_id=party["party_id"],
                    reason="Customer verified control of their account email",
                    )
        if invalid_code:
            raise HTTPException(400, "Incorrect verification code")
        return {"status": "verified", "contact_type": "email"}
    except HTTPException:
        raise
    except psycopg.Error as exc:
        raise HTTPException(503, "Unable to verify the email address") from exc


@router.post("/documents", status_code=201)
async def upload_identity_evidence(
    request: Request,
    document_type: str,
    file: UploadFile = File(...),
):
    """Upload identity evidence for the signed-in customer's own SBID."""
    customer_id = getattr(request.state, "customer_id", None)
    if not customer_id:
        raise HTTPException(401, "Customer sign-in required")
    content = await file.read(10 * 1024 * 1024 + 1)
    content_type = file.content_type or ""
    try:
        with _connect() as conn:
            party = _customer_party(conn, customer_id)
        stored = upload_identity_document(
            party_id=party["party_id"], user_id=customer_id,
            document_type=document_type, content_type=content_type, content=content,
        )
        try:
            with _connect() as conn:
                with conn.transaction():
                    row = conn.execute(
                        """
                        INSERT INTO identity_verification_documents
                          (party_id,document_type,object_key,content_type,file_size_bytes,
                           sha256_hex,status)
                        VALUES (%s,%s,%s,%s,%s,%s,'pending_review')
                        RETURNING id,status,created_at
                        """,
                        (party["party_id"], document_type, stored["object_key"],
                         stored["content_type"], stored["file_size_bytes"], stored["sha256_hex"]),
                    ).fetchone()
        except Exception:
            bucket = os.getenv("SB_PRIVATE_DOCUMENT_BUCKET", "").strip()
            region = os.getenv("SB_S3_REGION", "").strip() or os.getenv("AWS_REGION", "").strip()
            if bucket and region:
                boto3.client("s3", region_name=region).delete_object(Bucket=bucket, Key=stored["object_key"])
            raise
        return {"document": row}
    except (IdentityDocumentError, IdentityDocumentConfigurationError) as exc:
        raise HTTPException(422 if isinstance(exc, IdentityDocumentError) else 503, str(exc)) from exc
    except HTTPException:
        raise
    except psycopg.Error as exc:
        raise HTTPException(503, "Unable to save identity evidence") from exc
    finally:
        await file.close()


@router.get("/documents/{document_id}/download")
def download_identity_evidence(document_id: int, request: Request):
    """Issue a short-lived download URL only for the signed-in customer's own evidence."""
    customer_id = getattr(request.state, "customer_id", None)
    if not customer_id:
        raise HTTPException(401, "Customer sign-in required")
    try:
        with _connect() as conn:
            party = _customer_party(conn, customer_id)
            document = conn.execute(
                """
                SELECT object_key FROM identity_verification_documents
                WHERE id=%s AND party_id=%s
                """,
                (document_id, party["party_id"]),
            ).fetchone()
            if document is None:
                raise HTTPException(404, "Identity document not found")
        url = create_identity_document_download_url(
            party_id=party["party_id"], object_key=document["object_key"]
        )
        return {"url": url, "expires_in_seconds": 300}
    except HTTPException:
        raise
    except (IdentityDocumentError, IdentityDocumentConfigurationError) as exc:
        raise HTTPException(503, "Identity document storage is unavailable") from exc
    except psycopg.Error as exc:
        raise HTTPException(503, "Unable to retrieve identity evidence") from exc
