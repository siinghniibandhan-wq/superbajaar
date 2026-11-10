from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_delivery_requires_database_configuration(monkeypatch):
    from app.api import delivery

    monkeypatch.setattr(delivery.settings, "database_url", "")
    response = client.get("/api/delivery/shipments")
    assert response.status_code == 503
    assert response.json()["detail"] == "Delivery database is not configured"


def test_shipment_rejects_invalid_pin_before_database_access():
    response = client.post("/api/delivery/shipments", json={
        "order_id": 1, "delivery_pin": "123", "recipient_name": "Test",
        "recipient_phone": "1234567890", "address": "Test address",
    })
    assert response.status_code == 422


def test_shipment_rejects_blank_recipient_before_database_access():
    response = client.post("/api/delivery/shipments", json={
        "order_id": 1, "delivery_pin": "110001", "recipient_name": "  ",
        "recipient_phone": "1234567890", "address": "Test address",
    })
    assert response.status_code == 422


def test_shipment_status_rejects_unknown_value():
    response = client.patch("/api/delivery/shipments/1/status", json={"status": "teleported"})
    assert response.status_code == 422


def test_delivery_history_requires_database_configuration(monkeypatch):
    from app.api import delivery

    monkeypatch.setattr(delivery.settings, "database_url", "")
    response = client.get("/api/delivery/shipments/1/history")
    assert response.status_code == 503
    assert response.json()["detail"] == "Delivery database is not configured"


def test_delivery_history_rejects_non_integer_shipment_id():
    response = client.get("/api/delivery/shipments/not-a-number/history")
    assert response.status_code == 422


def test_delivery_history_rejects_invalid_limit():
    response = client.get("/api/delivery/shipments/1/history?limit=0")
    assert response.status_code == 422
