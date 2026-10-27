from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_delivery_requires_database_configuration(monkeypatch):
    from app.api.v1 import delivery

    monkeypatch.setattr(delivery.settings, "database_url", "")
    response = client.get("/api/v1/delivery/shipments")
    assert response.status_code == 503
    assert response.json()["detail"] == "Delivery database is not configured"


def test_shipment_rejects_invalid_pin_before_database_access():
    response = client.post("/api/v1/delivery/shipments", json={
        "order_id": 1, "delivery_pin": "123", "recipient_name": "Test",
        "recipient_phone": "1234567890", "address": "Test address",
    })
    assert response.status_code == 422


def test_shipment_rejects_blank_recipient_before_database_access():
    response = client.post("/api/v1/delivery/shipments", json={
        "order_id": 1, "delivery_pin": "110001", "recipient_name": "  ",
        "recipient_phone": "1234567890", "address": "Test address",
    })
    assert response.status_code == 422


def test_shipment_status_rejects_unknown_value():
    response = client.patch("/api/v1/delivery/shipments/1/status", json={"status": "teleported"})
    assert response.status_code == 422
