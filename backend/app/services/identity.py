"""Canonical, validation-only helpers for identity contact candidates.

Normalisation is not proof of ownership and must never be used by itself to
merge or link two identity parties.
"""
from __future__ import annotations

import re


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
    if not digits or len(digits) > 15 or digits.startswith("0") and has_plus:
        raise ValueError("Enter a valid phone number")

    # India: accept ten-digit national numbers, trunk-zero format, and 91 prefix.
    national = digits
    if len(digits) == 12 and digits.startswith("91"):
        national = digits[2:]
    elif len(digits) == 11 and digits.startswith("0"):
        national = digits[1:]
    if len(national) == 10 and national[0] in "6789":
        return "+91" + national

    # An explicit international number must have 7–15 digits and a non-zero
    # country-code prefix. Do not guess a country for other local numbers.
    if has_plus and 7 <= len(digits) <= 15 and digits[0] != "0":
        return "+" + digits
    raise ValueError("Enter a valid international phone number")
