import pytest

from app.services.pos_tender import validate_pos_tender


def test_pos_tender_requires_a_checkout_idempotency_key():
    with pytest.raises(ValueError, match="idempotency key"):
        validate_pos_tender(channel="pos", method="cod", checkout_idempotency_key=None)


def test_pos_tender_rejects_non_pos_channels():
    with pytest.raises(ValueError, match="only be attached to POS"):
        validate_pos_tender(channel="website", method="upi", checkout_idempotency_key="checkout-123")


def test_pos_tender_accepts_supported_method_with_idempotency_key():
    assert validate_pos_tender(channel="pos", method="upi", checkout_idempotency_key="checkout-123") is True


def test_pos_tender_rejects_unsupported_method():
    with pytest.raises(ValueError, match="unsupported POS tender method"):
        validate_pos_tender(channel="pos", method="crypto", checkout_idempotency_key="checkout-123")


def test_legacy_checkout_hash_payload_omits_new_optional_tender_field():
    from app.services.pos_tender import checkout_payload_for_hash

    legacy = {"channel": "website", "customer_name": "Buyer", "pos_payment_method": None}
    assert checkout_payload_for_hash(legacy) == {"channel": "website", "customer_name": "Buyer"}


def test_explicit_pos_tender_participates_in_checkout_hash_payload():
    from app.services.pos_tender import checkout_payload_for_hash

    payload = {"channel": "pos", "customer_name": "Walk-in", "pos_payment_method": "upi"}
    assert checkout_payload_for_hash(payload) == payload
