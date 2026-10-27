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


def test_shipment_creation_locks_order_before_active_shipment_check(monkeypatch):
    from fastapi import HTTPException
    from app.api.v1 import delivery

    class Result:
        def __init__(self, row):
            self.row = row

        def fetchone(self):
            return self.row

    class FakeConnection:
        def __init__(self):
            self.queries = []

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def transaction(self):
            return self

        def execute(self, query, params=()):
            self.queries.append(query)
            if "FROM orders" in query:
                return Result({"id": 10, "status": "placed", "delivery_pin": "110001"})
            if "FROM deliveries" in query:
                return Result({"id": 20})
            raise AssertionError(f"Unexpected SQL: {query}")

    fake = FakeConnection()
    monkeypatch.setattr(delivery, "_connect", lambda: fake)
    payload = delivery.DeliveryCreate(
        order_id=10, delivery_pin="110001", recipient_name="Test",
        recipient_phone="1234567890", address="Test address",
    )

    try:
        delivery.create_shipment(payload)
        assert False, "Expected duplicate active shipment to be rejected"
    except HTTPException as exc:
        assert exc.status_code == 409

    assert "FOR UPDATE" in fake.queries[0].upper()
    assert "FOR SHARE" not in fake.queries[0].upper()
    assert "FROM deliveries" in fake.queries[1]

