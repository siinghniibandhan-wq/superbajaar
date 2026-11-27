from contextlib import nullcontext
from types import SimpleNamespace
from decimal import Decimal

import pytest
from fastapi import HTTPException

from app.api import payments


class ReplayConnection:
    def __init__(self, prior):
        self.prior = prior
        self.statements = []

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False

    def transaction(self):
        return nullcontext()

    def execute(self, query, params=()):
        self.statements.append((query, params))
        if "FROM payments WHERE idempotency_key=%s" in query:
            return type("Result", (), {"fetchone": lambda self: self.prior})()
        return type("Result", (), {"fetchone": lambda self: None})()


def test_payment_create_replays_same_actor_and_payload_without_creating_second_payment(monkeypatch):
    payload = payments.PaymentCreate(order_id=12, method="cod", amount=Decimal("25.00"))
    payload_hash = payments.payment_payload_sha256(payload.model_dump(mode="json"))
    prior = {
        "idempotency_payload_sha256": payload_hash,
        "id": 99,
        "payment_reference": "PAY-EXISTING",
        "order_id": 12,
        "method": "cod",
        "amount": Decimal("25.00"),
        "status": "pending",
        "provider_reference": None,
        "note": None,
        "created_at": None,
        "updated_at": None,
    }
    db = ReplayConnection(prior)
    monkeypatch.setattr(payments, "_connect", lambda: db)
    request = SimpleNamespace(state=SimpleNamespace(user_id=7))

    result = payments.create_payment(payload, request, "payment-retry-key-0001")

    assert result["id"] == 99
    assert result["payment_reference"] == "PAY-EXISTING"
    assert "idempotency_payload_sha256" not in result
    assert not any("INSERT INTO payments" in query for query, _ in db.statements)


def test_payment_create_rejects_reusing_key_with_changed_payload(monkeypatch):
    original = payments.PaymentCreate(order_id=12, method="cod", amount=Decimal("25.00"))
    changed = payments.PaymentCreate(order_id=12, method="cod", amount=Decimal("30.00"))
    prior = {
        "idempotency_payload_sha256": payments.payment_payload_sha256(original.model_dump(mode="json")),
        "id": 99,
    }
    monkeypatch.setattr(payments, "_connect", lambda: ReplayConnection(prior))
    request = SimpleNamespace(state=SimpleNamespace(user_id=7))

    with pytest.raises(HTTPException) as exc:
        payments.create_payment(changed, request, "payment-retry-key-0001")

    assert exc.value.status_code == 409
    assert "different payment payload" in exc.value.detail
