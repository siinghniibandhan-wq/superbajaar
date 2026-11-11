import pytest

from app.services.identity import normalize_email, normalize_phone


def test_normalize_email_trims_and_casefolds_verified_contact_candidate():
    assert normalize_email("  Buyer+Test@Example.COM ") == "buyer+test@example.com"


@pytest.mark.parametrize("value,expected", [
    ("9876543210", "+919876543210"),
    ("09876543210", "+919876543210"),
    ("919876543210", "+919876543210"),
    ("+91 98765 43210", "+919876543210"),
])
def test_normalize_indian_mobile_formats_to_one_canonical_value(value, expected):
    assert normalize_phone(value) == expected


def test_normalize_phone_preserves_non_indian_international_prefix():
    assert normalize_phone("+1 (415) 555-0134") == "+14155550134"


@pytest.mark.parametrize("value", ["", "123", "not-a-number", "+", "0000000000"])
def test_normalize_phone_rejects_invalid_or_unusable_values(value):
    with pytest.raises(ValueError):
        normalize_phone(value)
