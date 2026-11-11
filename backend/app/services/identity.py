"""Canonical identity operations and contact-candidate normalisation.

Normalisation is not proof of ownership. Callers must verify control of a
contact or approve a trusted invitation before linking accounts or profiles.
"""
from __future__ import annotations

import re
from typing import Any


_EMAIL_RE = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")
_PHONE_ALLOWED_RE = re.compile(r"^[+\d().\-\s]+$")


def normalize_email(value: str) -> str:
    """Trim and case-fold an email candidate without asserting ownership."""
    if not isinstance(value, str):
        raise ValueError("Email address must be text")
    normalized = value.strip().casefold()
    if len(normalized) > 254 or not _EMAIL_RE.fullmatch(normalized):
        raise ValueError("Enter a valid email address")
    return normalized


def normalize_phone(value: str) -> str:
    """Return an E.164-style candidate; Indian local formats become +91."""
    if not isinstance(value, str):
        raise ValueError("Phone number must be text")
    candidate = value.strip()
    if not candidate or not _PHONE_ALLOWED_RE.fullmatch(candidate):
        raise ValueError("Enter a valid phone number")

    has_plus = candidate.startswith("+")
    digits = re.sub(r"\D", "", candidate)
    if not digits or len(digits) > 15 or (has_plus and digits.startswith("0")):
        raise ValueError("Enter a valid phone number")

    national = digits
    if len(digits) == 12 and digits.startswith("91"):
        national = digits[2:]
    elif len(digits) == 11 and digits.startswith("0"):
        national = digits[1:]
    if len(national) == 10 and national[0] in "6789":
        return "+91" + national

    if has_plus and 7 <= len(digits) <= 15 and digits[0] != "0":
        return "+" + digits
    raise ValueError("Enter a valid international phone number")


class IdentityService:
    """Database operations for identity parties; caller owns transaction scope."""

    def __init__(self, connection: Any):
        self.connection = connection

    def _event(
        self,
        *,
        party_id: int | None,
        event_type: str,
        event_data: dict[str, Any],
        actor_user_id: int | None = None,
        actor_party_id: int | None = None,
        reason: str | None = None,
    ) -> None:
        self.connection.execute(
            """
            INSERT INTO identity_events
                (party_id,event_type,event_data,actor_user_id,actor_party_id,reason)
            VALUES (%s,%s,%s::jsonb,%s,%s,%s)
            """,
            (
                party_id,
                event_type,
                __import__("json").dumps(event_data, separators=(",", ":")),
                actor_user_id,
                actor_party_id,
                reason,
            ),
        )

    def create_party(
        self,
        *,
        party_type: str,
        display_name: str,
        actor_user_id: int | None = None,
        reason: str | None = None,
    ) -> dict[str, Any]:
        if party_type not in {"individual", "organisation"}:
            raise ValueError("party_type must be individual or organisation")
        if not isinstance(display_name, str) or len(" ".join(display_name.split())) < 2:
            raise ValueError("display_name must contain at least two characters")
        clean_name = " ".join(display_name.split())
        row = self.connection.execute(
            """
            INSERT INTO identity_parties (party_type,display_name)
            VALUES (%s,%s)
            RETURNING id,sbid,party_type,display_name,status,created_at
            """,
            (party_type, clean_name),
        ).fetchone()
        result = dict(row)
        self._event(
            party_id=result["id"],
            event_type="party_created",
            event_data={"sbid": result["sbid"], "party_type": party_type},
            actor_user_id=actor_user_id,
            reason=reason,
        )
        return result

    def add_contact(
        self,
        *,
        party_id: int,
        contact_type: str,
        value: str,
        display_value: str | None = None,
        source: str = "self_service",
    ) -> dict[str, Any]:
        if contact_type == "email":
            normalized = normalize_email(value)
        elif contact_type == "phone":
            normalized = normalize_phone(value)
        else:
            raise ValueError("contact_type must be email or phone")
        shown = display_value.strip() if display_value else value.strip()
        if not shown:
            raise ValueError("display_value cannot be empty")
        row = self.connection.execute(
            """
            INSERT INTO identity_contacts
                (party_id,contact_type,normalized_value,display_value,
                 verification_status,is_primary,source)
            VALUES (%s,%s,%s,%s,'unverified',false,%s)
            RETURNING id,party_id,contact_type,normalized_value,display_value,
                      verification_status,is_primary,created_at
            """,
            (party_id, contact_type, normalized, shown, source),
        ).fetchone()
        result = dict(row)
        self._event(
            party_id=party_id,
            event_type="contact_added",
            event_data={"contact_id": result["id"], "contact_type": contact_type},
        )
        return result
