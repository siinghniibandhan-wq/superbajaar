"""Cryptographically safe invitation primitives shared by external portals."""
from datetime import datetime, timezone
import hashlib
import secrets


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
