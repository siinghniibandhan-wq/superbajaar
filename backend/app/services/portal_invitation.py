"""Cryptographically safe invitation primitives shared by external portals."""
from datetime import datetime, timezone
import hashlib
import json
import secrets
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


def issue_invitation_token() -> tuple[str, str]:
    """Return a one-time raw token and its SHA-256 digest for persistence."""
    raw_token = secrets.token_urlsafe(36)
    return raw_token, hash_invitation_token(raw_token)


def hash_invitation_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def invitation_is_usable(
    expires_at: datetime,
    accepted_at: datetime | None,
    revoked_at: datetime | None,
    now: datetime | None = None,
) -> bool:
    """An invitation is usable exactly once, before expiry, unless revoked."""
    instant = now or datetime.now(timezone.utc)
    if instant.tzinfo is None:
        instant = instant.replace(tzinfo=timezone.utc)
    expiry = expires_at if expires_at.tzinfo else expires_at.replace(tzinfo=timezone.utc)
    return accepted_at is None and revoked_at is None and expiry > instant


def send_resend_email(
    *,
    api_key: str,
    sender: str,
    recipient: str,
    subject: str,
    text: str,
) -> str | None:
    """Send a transactional email via Resend; return its message ID on success."""
    if not api_key.strip() or not sender.strip() or not recipient.strip():
        return None
    payload = json.dumps(
        {"from": sender, "to": [recipient], "subject": subject, "text": text}
    ).encode("utf-8")
    request = Request(
        "https://api.resend.com/emails",
        data=payload,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "User-Agent": "Super-Bajaar/1.0",
        },
        method="POST",
    )
    try:
        with urlopen(request, timeout=10) as response:
            result = json.loads(response.read().decode("utf-8"))
        message_id = result.get("id") if isinstance(result, dict) else None
        return message_id if isinstance(message_id, str) and message_id else None
    except (HTTPError, URLError, TimeoutError, OSError, ValueError, json.JSONDecodeError):
        # Never log the request, response body, or API key; callers use link fallback.
        return None
