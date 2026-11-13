"""Secure OTP generation, hashing and delivery for unified identity verification."""
from __future__ import annotations

import hashlib
import hmac
import os
import secrets

from app.services.portal_invitation import send_resend_email


CHANNELS = {"email"}


class OTPConfigurationError(RuntimeError):
    pass


class OTPDeliveryError(RuntimeError):
    pass


def generate_otp() -> str:
    """Generate a cryptographically random six-digit code."""
    return f"{secrets.randbelow(1_000_000):06d}"


def otp_digest(challenge_token: str, otp: str, secret: str | None = None) -> str:
    """Return a keyed digest; the raw OTP is never persisted."""
    key = secret or os.getenv("IDENTITY_OTP_HMAC_SECRET", "")
    if len(key) < 32:
        raise OTPConfigurationError("Identity OTP signing secret is not configured")
    if not challenge_token or len(otp) != 6 or not otp.isdigit():
        raise ValueError("Invalid OTP challenge or code")
    return hmac.new(
        key.encode("utf-8"),
        f"{challenge_token}:{otp}".encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()


def verify_otp_digest(challenge_token: str, otp: str, expected_digest: str,
                      secret: str | None = None) -> bool:
    try:
        actual = otp_digest(challenge_token, otp, secret)
    except (ValueError, OTPConfigurationError):
        return False
    return hmac.compare_digest(actual, expected_digest)


def deliver_otp(channel: str, destination: str, otp: str) -> None:
    """Send identity OTP through the repository's existing Resend integration."""
    if channel not in CHANNELS:
        raise OTPConfigurationError("Only the configured Resend email channel is enabled")
    if not destination or not otp or len(otp) != 6 or not otp.isdigit():
        raise ValueError("A valid destination and OTP are required")

    provider = os.getenv("SB_EMAIL_PROVIDER", "smtp").strip().lower()
    api_key = os.getenv("RESEND_API_KEY", "").strip()
    sender = os.getenv("SB_SMTP_FROM", "onboarding@resend.dev").strip()
    test_recipient = os.getenv("RESEND_TEST_RECIPIENT", "").strip().lower()
    if provider != "resend" or not api_key or not sender:
        raise OTPConfigurationError("Resend email delivery is not configured")
    # The shared Resend testing sender may only send to the account's verified
    # test recipient. A verified custom domain sender can deliver to recipients.
    if sender.lower() == "onboarding@resend.dev" and destination.strip().lower() != test_recipient:
        raise OTPConfigurationError("Resend testing sender cannot deliver to this recipient")

    message = (
        f"Your Super Bajaar verification code is {otp}. "
        "It expires in 5 minutes. Do not share it."
    )
    try:
        message_id = send_resend_email(
            api_key=api_key,
            sender=sender,
            recipient=destination,
            subject="Your Super Bajaar verification code",
            text=message,
        )
    except Exception as exc:
        raise OTPDeliveryError("Unable to deliver the verification code") from exc
    if not message_id:
        raise OTPDeliveryError("Resend could not deliver the verification code")
