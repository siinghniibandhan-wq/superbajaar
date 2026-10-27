from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_payments_requires_database_configuration(monkeypatch):
    from app.api.v1 import payments

    monkeypatch.setattr(payments.settings, "database_url", "")
    response = client.get("/api/v1/payments")
    assert response.status_code == 503
    assert response.json()["detail"] == "Payments database is not configured"


def test_payment_rejects_unknown_method_before_database_access():
    response = client.post("/api/v1/payments", json={
        "order_id": 1, "method": "crypto", "amount": 100,
    })
    assert response.status_code == 422


def test_payment_rejects_zero_amount_before_database_access():
    response = client.post("/api/v1/payments", json={
        "order_id": 1, "method": "upi", "amount": 0,
    })
    assert response.status_code == 422


def test_payment_rejects_unknown_status():
    response = client.patch("/api/v1/payments/1/status", json={"status": "settled_forever"})
    assert response.status_code == 422


def test_payment_cannot_be_created_as_captured_without_gateway_confirmation():
    response = client.post("/api/v1/payments", json={
        "order_id": 1, "method": "upi", "amount": 100, "status": "captured",
    })
    assert response.status_code == 422


def test_payment_cannot_be_created_as_refunded_without_gateway_confirmation():
    response = client.post("/api/v1/payments", json={
        "order_id": 1, "method": "upi", "amount": 100, "status": "refunded",
    })
    assert response.status_code == 422
