from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_orders_requires_database_configuration(monkeypatch):
    from app.api.v1 import orders

    monkeypatch.setattr(orders.settings, "database_url", "")
    response = client.get("/api/v1/orders")
    assert response.status_code == 503
    assert response.json()["detail"] == "Orders database is not configured"


def test_order_rejects_invalid_channel_before_database_access():
    response = client.post("/api/v1/orders", json={
        "channel": "unknown", "customer_name": "Test customer",
        "lines": [{"variant_id": 1, "quantity": 1}],
    })
    assert response.status_code == 422


def test_order_rejects_invalid_delivery_pin_before_database_access():
    response = client.post("/api/v1/orders", json={
        "channel": "website", "customer_name": "Test customer", "delivery_pin": "123",
        "lines": [{"variant_id": 1, "quantity": 1}],
    })
    assert response.status_code == 422


def test_order_requires_at_least_one_line():
    response = client.post("/api/v1/orders", json={
        "channel": "pos", "customer_name": "Test customer", "lines": [],
    })
    assert response.status_code == 422


def test_order_status_rejects_unknown_value():
    response = client.patch("/api/v1/orders/1/status", json={"status": "refunded"})
    assert response.status_code == 422
