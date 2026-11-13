"""Secure OTP generation, hashing and delivery for unified identity verification.

Delivery destinations must already be controlled by the recipient. Telegram uses a
bot chat ID; WhatsApp uses a verified E.164 phone number and an approved template.
"""
from __future__ import annotations

import hashlib
import hmac
import os
import secrets

import boto3
import httpx


CHANNELS = {"email", "sms", "whatsapp", "telegram"}


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
    """Deliver OTP through a configured provider; never log or return the code."""
    if channel not in CHANNELS:
        raise ValueError("Unsupported OTP delivery channel")
    if not destination or not otp or len(otp) != 6 or not otp.isdigit():
        raise ValueError("A valid destination and OTP are required")

    message = f"Your Super Bajaar verification code is {otp}. It expires in 5 minutes. Do not share it."

    try:
        if channel == "email":
            sender = os.getenv("SB_OTP_FROM_EMAIL", "").strip()
            if not sender:
                raise OTPConfigurationError("Email OTP sender is not configured")
            region = os.getenv("AWS_REGION", "us-east-1")
            boto3.client("ses", region_name=region).send_email(
                Source=sender,
                Destination={"ToAddresses": [destination]},
                Message={
                    "Subject": {"Data": "Super Bajaar verification code", "Charset": "UTF-8"},
                    "Body": {"Text": {"Data": message, "Charset": "UTF-8"}},
                },
            )
        elif channel == "sms":
            region = os.getenv("AWS_REGION", "us-east-1")
            boto3.client("sns", region_name=region).publish(
                PhoneNumber=destination,
                Message=message,
                MessageAttributes={
                    "AWS.SNS.SMS.SMSType": {
                        "DataType": "String", "StringValue": "Transactional"
                    }
                },
            )
        elif channel == "whatsapp":
            token = os.getenv("SB_WHATSAPP_ACCESS_TOKEN", "").strip()
            phone_id = os.getenv("SB_WHATSAPP_PHONE_NUMBER_ID", "").strip()
            template = os.getenv("SB_WHATSAPP_OTP_TEMPLATE", "").strip()
            language = os.getenv("SB_WHATSAPP_OTP_LANGUAGE", "en").strip()
            version = os.getenv("SB_WHATSAPP_GRAPH_VERSION", "v22.0").strip()
            if not all((token, phone_id, template)):
                raise OTPConfigurationError("WhatsApp OTP template delivery is not configured")
            response = httpx.post(
                f"https://graph.facebook.com/{version}/{phone_id}/messages",
                headers={"Authorization": f"Bearer {token}"},
                json={
                    "messaging_product": "whatsapp",
                    "to": destination,
                    "type": "template",
                    "template": {
                        "name": template,
                        "language": {"code": language},
                        "components": [{
                            "type": "body",
                            "parameters": [{"type": "text", "text": otp}],
                        }],
                    },
                },
                timeout=10.0,
            )
            response.raise_for_status()
        else:
            token = os.getenv("SB_TELEGRAM_BOT_TOKEN", "").strip()
            if not token:
                raise OTPConfigurationError("Telegram bot delivery is not configured")
            response = httpx.post(
                f"https://api.telegram.org/bot{token}/sendMessage",
                json={"chat_id": destination, "text": message},
                timeout=10.0,
            )
            response.raise_for_status()
            if not response.json().get("ok"):
                raise OTPDeliveryError("Telegram rejected the verification message")
    except (OTPConfigurationError, ValueError):
        raise
    except Exception as exc:
        # Do not leak provider responses, destination details, or credentials.
        raise OTPDeliveryError("Unable to deliver the verification code") from exc
