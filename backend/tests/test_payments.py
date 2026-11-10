import asyncio
import hashlib
import hmac
import json
from contextlib import nullcontext
from decimal import Decimal
from types import SimpleNamespace

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


class _FakeResult:
    def __init__(self, row=None):
        self.row = row

    def fetchone(self):
        return self.row


class _FakePaymentConnection:
    def __init__(
        self, *, payment=None, event=None, previous_event=None, order=None,
        inserted_payment=None,
    ):
        self.payment = payment
        self.event = event
        self.previous_event = previous_event
        self.order = order
        self.inserted_payment = inserted_payment
        self.statements = []

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False

    def transaction(self):
        return nullcontext()

    def commit(self):
        pass

    def execute(self, query, params=()):
        normalized_query = " ".join(query.split())
        self.statements.append((normalized_query, params))
        if "INSERT INTO payment_provider_events" in normalized_query:
            return _FakeResult(self.event)
        if "INSERT INTO payments" in normalized_query:
            return _FakeResult(self.inserted_payment)
        if "SELECT payload_sha256" in normalized_query:
            return _FakeResult(self.previous_event)
        if "FROM payments p JOIN orders o" in normalized_query:
            return _FakeResult(self.payment)
        if "FROM payments WHERE provider_order_id" in normalized_query:
            return _FakeResult(self.payment)
        if "FROM payments WHERE order_id" in normalized_query:
            return _FakeResult()
        if "FROM orders WHERE id=%s FOR UPDATE" in normalized_query:
            return _FakeResult(self.order)
        return _FakeResult()


def test_payments_requires_database_configuration(monkeypatch):
    from app.api import payments

    monkeypatch.setattr(payments.settings, "database_url", "")
    response = client.get("/api/payments")
    assert response.status_code == 503
    assert response.json()["detail"] == "Payments database is not configured"


def test_payment_rejects_unknown_method_before_database_access():
    response = client.post("/api/payments", json={
        "order_id": 1, "method": "crypto", "amount": 100,
    })
    assert response.status_code == 422


def test_payment_rejects_zero_amount_before_database_access():
    response = client.post("/api/payments", json={
        "order_id": 1, "method": "upi", "amount": 0,
    })
    assert response.status_code == 422


def test_payment_rejects_unknown_status():
    response = client.patch("/api/payments/1/status", json={"status": "settled_forever"})
    assert response.status_code == 422


def test_payment_cannot_be_created_as_captured_without_gateway_confirmation():
    response = client.post("/api/payments", json={
        "order_id": 1, "method": "upi", "amount": 100, "status": "captured",
    })
    assert response.status_code == 422


def test_payment_cannot_be_created_as_refunded_without_gateway_confirmation():
    response = client.post("/api/payments", json={
        "order_id": 1, "method": "upi", "amount": 100, "status": "refunded",
    })
    assert response.status_code == 422


def test_payment_status_cannot_be_marked_captured_without_provider_verification():
    response = client.patch("/api/payments/1/status", json={"status": "captured"})
    assert response.status_code == 422


def test_payment_status_cannot_be_marked_refunded_without_provider_verification():
    response = client.patch("/api/payments/1/status", json={"status": "refunded"})
    assert response.status_code == 422


def test_payment_status_cannot_be_marked_authorized_without_provider_verification():
    response = client.patch("/api/payments/1/status", json={"status": "authorized"})
    assert response.status_code == 422
    assert "verified provider confirmation" in response.json()["detail"][0]["msg"]


def test_razorpay_webhook_route_exists_and_fails_closed_without_secret(monkeypatch):
    from app.core import config

    monkeypatch.setattr(config.settings, "database_url", "")
    monkeypatch.setattr(config.settings, "razorpay_webhook_secret", "")
    response = client.post(
        "/api/razorpay/webhook",
        content=b'{"event":"payment.captured"}',
        headers={"X-Razorpay-Signature": "0" * 64, "x-razorpay-event-id": "evt_test_1"},
    )
    assert response.status_code == 503
    assert response.json()["detail"] == "Razorpay webhook is not configured"


def test_razorpay_order_creation_fails_closed_without_credentials(monkeypatch):
    from app.core import config

    monkeypatch.setattr(config.settings, "database_url", "")
    monkeypatch.setattr(config.settings, "razorpay_key_id", "")
    monkeypatch.setattr(config.settings, "razorpay_key_secret", "")
    response = client.post("/api/razorpay/orders", json={"order_id": 1})
    assert response.status_code == 503
    assert response.json()["detail"] == "Razorpay payments are not configured"


def test_razorpay_webhook_rejects_invalid_signature_before_database_access(monkeypatch):
    from app.core import config

    monkeypatch.setattr(config.settings, "database_url", "")
    monkeypatch.setattr(config.settings, "razorpay_webhook_secret", "test-webhook-secret")
    body = b'{"event":"payment.captured","payload":{}}'
    response = client.post(
        "/api/razorpay/webhook",
        content=body,
        headers={
            "X-Razorpay-Signature": "0" * 64,
            "x-razorpay-event-id": "evt_invalid_signature",
        },
    )
    assert response.status_code == 400
    assert response.json()["detail"] == "Invalid Razorpay webhook signature"



def test_razorpay_verify_rejects_malformed_provider_identifiers_before_network_access():
    response = client.post(
        "/api/razorpay/verify",
        json={
            "razorpay_order_id": "https://attacker.example/",
            "razorpay_payment_id": "pay_test123",
            "razorpay_signature": "0" * 64,
        },
    )
    assert response.status_code == 422


def test_razorpay_verify_fails_closed_without_both_api_credentials(monkeypatch):
    from app.core import config

    monkeypatch.setattr(config.settings, "database_url", "")
    monkeypatch.setattr(config.settings, "razorpay_key_id", "rzp_test_key")
    monkeypatch.setattr(config.settings, "razorpay_key_secret", "")
    response = client.post(
        "/api/razorpay/verify",
        json={
            "razorpay_order_id": "order_test123456",
            "razorpay_payment_id": "pay_test123456",
            "razorpay_signature": "0" * 64,
        },
    )
    assert response.status_code == 503
    assert response.json()["detail"] == "Razorpay payments are not configured"


def test_razorpay_verify_confirms_captured_payment_with_provider_and_updates_order(monkeypatch):
    from app.api import payments

    key_secret = "test-razorpay-secret"
    order_id = "order_test123456"
    payment_id = "pay_test123456"
    message = f"{order_id}|{payment_id}".encode()
    signature = hmac.new(key_secret.encode(), message, hashlib.sha256).hexdigest()
    payload = payments.RazorpayPaymentVerify(
        razorpay_order_id=order_id,
        razorpay_payment_id=payment_id,
        razorpay_signature=signature,
    )
    db = _FakePaymentConnection(payment={
        "id": 21,
        "order_id": 41,
        "amount": Decimal("12.34"),
        "currency": "INR",
        "status": "pending",
        "order_status": "placed",
        "customer_email": "buyer@example.com",
        "order_number": "SB-ORDER-41",
    })
    provider_response = SimpleNamespace(
        raise_for_status=lambda: None,
        json=lambda: {
            "id": payment_id,
            "order_id": order_id,
            "amount": 1234,
            "currency": "INR",
            "status": "captured",
        },
    )

    class _FakeAsyncClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *_):
            return False

        async def get(self, url, *, auth):
            self.url = url
            self.auth = auth
            return provider_response

    provider_client = _FakeAsyncClient()
    monkeypatch.setattr(payments.settings, "razorpay_key_id", "rzp_test_key")
    monkeypatch.setattr(payments.settings, "razorpay_key_secret", key_secret)
    monkeypatch.setattr(payments, "_connect", lambda: db)
    monkeypatch.setattr(payments.httpx, "AsyncClient", lambda **_: provider_client)
    request = SimpleNamespace(state=SimpleNamespace(
        role="customer",
        customer_email="buyer@example.com",
    ))

    result = asyncio.run(payments.verify_razorpay_payment(payload, request))

    assert result == {
        "status": "captured",
        "order_number": "SB-ORDER-41",
        "order_status": "confirmed",
        "refund_required": False,
    }
    assert provider_client.url == f"https://api.razorpay.com/v1/payments/{payment_id}"
    assert provider_client.auth == ("rzp_test_key", key_secret)
    assert any("UPDATE payments SET status='captured'" in query for query, _ in db.statements)
    assert any("UPDATE orders SET status='confirmed'" in query for query, _ in db.statements)


def test_razorpay_order_creation_creates_provider_order_and_local_attempt(monkeypatch):
    from app.api import payments

    db = _FakePaymentConnection(
        order={
            "id": 41,
            "order_number": "SB-ORDER-41",
            "customer_email": "buyer@example.com",
            "total": Decimal("12.34"),
            "status": "placed",
        },
        inserted_payment={"id": 21},
    )
    provider_response = SimpleNamespace(
        raise_for_status=lambda: None,
        json=lambda: {
            "id": "order_test123456",
            "amount": 1234,
            "currency": "INR",
        },
    )

    class _FakeProviderClient:
        def __enter__(self):
            return self

        def __exit__(self, *_):
            return False

        def post(self, url, *, auth, json):
            self.url = url
            self.auth = auth
            self.payload = json
            return provider_response

    provider_client = _FakeProviderClient()
    monkeypatch.setattr(payments.settings, "razorpay_key_id", "rzp_test_key")
    monkeypatch.setattr(payments.settings, "razorpay_key_secret", "test-razorpay-secret")
    monkeypatch.setattr(payments, "_connect", lambda: db)
    monkeypatch.setattr(payments.httpx, "Client", lambda **_: provider_client)
    request = SimpleNamespace(state=SimpleNamespace(
        role="customer",
        customer_email="buyer@example.com",
    ))

    result = payments.create_razorpay_order(
        payments.RazorpayOrderCreate(order_id=41),
        request,
    )

    assert result == {
        "key_id": "rzp_test_key",
        "razorpay_order_id": "order_test123456",
        "amount": 1234,
        "currency": "INR",
        "payment_id": 21,
        "order_number": "SB-ORDER-41",
    }
    assert provider_client.url == "https://api.razorpay.com/v1/orders"
    assert provider_client.auth == ("rzp_test_key", "test-razorpay-secret")
    assert provider_client.payload["amount"] == 1234
    assert any("INSERT INTO payments" in query for query, _ in db.statements)


def test_razorpay_webhook_processes_captured_payment_and_deduplicates_event(monkeypatch):
    from app.api import payments

    secret = "test-webhook-secret"
    event_id = "evt_checkout_captured_1"
    body = json.dumps({
        "event": "payment.captured",
        "payload": {
            "payment": {
                "entity": {
                    "id": "pay_test123456",
                    "order_id": "order_test123456",
                    "amount": 1234,
                    "currency": "INR",
                },
            },
        },
    }, separators=(",", ":")).encode()
    payload_hash = hashlib.sha256(body).hexdigest()
    signature = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    payment = {
        "id": 21,
        "order_id": 41,
        "amount": Decimal("12.34"),
        "currency": "INR",
        "status": "pending",
    }
    processed_db = _FakePaymentConnection(payment=payment, event={"id": 77})
    duplicate_db = _FakePaymentConnection(previous_event={"payload_sha256": payload_hash})
    databases = iter((processed_db, duplicate_db))
    monkeypatch.setattr(payments.settings, "razorpay_webhook_secret", secret)
    monkeypatch.setattr(payments, "_connect", lambda: next(databases))
    headers = {
        "X-Razorpay-Signature": signature,
        "X-Razorpay-Event-Id": event_id,
    }

    response = client.post("/api/razorpay/webhook", content=body, headers=headers)
    duplicate_response = client.post("/api/razorpay/webhook", content=body, headers=headers)

    assert response.status_code == 200
    assert duplicate_response.status_code == 200
    assert any("UPDATE payments SET status='captured'" in query for query, _ in processed_db.statements)
    assert any("UPDATE orders SET status='confirmed'" in query for query, _ in processed_db.statements)
    assert not any(
        "FROM payments WHERE provider_order_id" in query
        for query, _ in duplicate_db.statements
    )


def test_razorpay_verify_reports_captured_payment_for_cancelled_order_without_claiming_confirmation(monkeypatch):
    from app.api import payments

    key_secret = "test-razorpay-secret"
    order_id = "order_test123456"
    payment_id = "pay_test123456"
    signature = hmac.new(
        key_secret.encode(),
        f"{order_id}|{payment_id}".encode(),
        hashlib.sha256,
    ).hexdigest()
    payload = payments.RazorpayPaymentVerify(
        razorpay_order_id=order_id,
        razorpay_payment_id=payment_id,
        razorpay_signature=signature,
    )
    db = _FakePaymentConnection(payment={
        "id": 21,
        "order_id": 41,
        "amount": Decimal("12.34"),
        "currency": "INR",
        "status": "pending",
        "order_status": "cancelled",
        "customer_email": "buyer@example.com",
        "order_number": "SB-ORDER-41",
    })
    provider_response = SimpleNamespace(
        raise_for_status=lambda: None,
        json=lambda: {
            "id": payment_id,
            "order_id": order_id,
            "amount": 1234,
            "currency": "INR",
            "status": "captured",
        },
    )

    class _FakeAsyncClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *_):
            return False

        async def get(self, url, *, auth):
            return provider_response

    monkeypatch.setattr(payments.settings, "razorpay_key_id", "rzp_test_key")
    monkeypatch.setattr(payments.settings, "razorpay_key_secret", key_secret)
    monkeypatch.setattr(payments, "_connect", lambda: db)
    monkeypatch.setattr(payments.httpx, "AsyncClient", lambda **_: _FakeAsyncClient())
    request = SimpleNamespace(state=SimpleNamespace(
        role="customer",
        customer_email="buyer@example.com",
    ))

    result = asyncio.run(payments.verify_razorpay_payment(payload, request))

    assert result == {
        "status": "captured",
        "order_number": "SB-ORDER-41",
        "order_status": "cancelled",
        "refund_required": True,
    }
    assert any("UPDATE payments SET status='captured'" in query for query, _ in db.statements)
    assert not any("UPDATE orders SET status='confirmed'" in query for query, _ in db.statements)
