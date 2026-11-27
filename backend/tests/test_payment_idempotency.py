import hashlib
import json
from decimal import Decimal

from app.api.payments import payment_payload_sha256


def test_payment_idempotency_hash_is_stable_for_equivalent_payloads():
    payload = {"order_id": 12, "method": "cash", "amount": Decimal("10.00"), "note": None}
    assert payment_payload_sha256(payload) == payment_payload_sha256(dict(payload))


def test_payment_idempotency_hash_changes_when_amount_changes():
    first = {"order_id": 12, "method": "cash", "amount": Decimal("10.00")}
    second = {"order_id": 12, "method": "cash", "amount": Decimal("11.00")}
    assert payment_payload_sha256(first) != payment_payload_sha256(second)
