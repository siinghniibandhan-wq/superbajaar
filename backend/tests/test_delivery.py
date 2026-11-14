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



def test_serviceability_uses_profile_service_pins_and_operating_hours(monkeypatch):
    from app.api import delivery

    class Result:
        def fetchall(self):
            return [{"id": 5, "name": "Patna Dark Store", "location_type": "dark_store",
                     "pin_code": "800001", "region_code": None, "city": "Patna",
                     "district": "Patna", "state": "Bihar"}]

    class Connection:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def execute(self, query, params):
            self.query = query
            self.params = params
            return Result()

    conn = Connection()
    monkeypatch.setattr(delivery, "_connect", lambda: conn)

    result = delivery.check_serviceability("800002")

    assert result["serviceable"] is True
    assert result["locations"][0]["id"] == 5
    assert "stock_location_profiles" in conn.query
    assert "service_pin_codes" in conn.query
    assert "storefront_available" in conn.query
    assert "Asia/Kolkata" in conn.query
    assert conn.params == ("800002",)


def test_shipment_origin_is_derived_from_reserved_stock_location(monkeypatch):
    from contextlib import contextmanager
    from app.api import delivery

    class Result:
        def __init__(self, row):
            self.row = row

        def fetchone(self):
            return self.row

    class Connection:
        def __init__(self):
            self.calls = []

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        @contextmanager
        def transaction(self):
            yield self

        def execute(self, query, params):
            self.calls.append((query, params))
            if query.startswith("SELECT id, status, delivery_pin FROM orders"):
                return Result({"id": 8, "status": "ready_for_dispatch", "delivery_pin": "800001"})
            if query.startswith("SELECT id FROM deliveries"):
                return Result(None)
            if query.startswith("INSERT INTO deliveries"):
                return Result({"id": 9, "location_id": 55, "status": "pending"})
            raise AssertionError(f"Unexpected SQL: {query}")

    conn = Connection()
    monkeypatch.setattr(delivery, "_connect", lambda: conn)
    monkeypatch.setattr(delivery, "order_reservation_locations", lambda _conn, _order_id: [55])

    result = delivery.create_shipment(delivery.DeliveryCreate(
        order_id=8, delivery_pin="800001", recipient_name="Customer",
        recipient_phone="9876543210", address="Patna delivery address",
    ))

    assert result["location_id"] == 55
    insert_params = conn.calls[-1][1]
    assert insert_params[6] == 55


def test_shipment_rejects_facility_that_differs_from_order_reservation(monkeypatch):
    from contextlib import contextmanager
    from fastapi import HTTPException
    import pytest
    from app.api import delivery

    class Result:
        def __init__(self, row):
            self.row = row

        def fetchone(self):
            return self.row

    class Connection:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        @contextmanager
        def transaction(self):
            yield self

        def execute(self, query, params):
            if query.startswith("SELECT id, status, delivery_pin FROM orders"):
                return Result({"id": 8, "status": "ready_for_dispatch", "delivery_pin": "800001"})
            raise AssertionError("A mismatched location must be rejected before shipment creation")

    monkeypatch.setattr(delivery, "_connect", Connection)
    monkeypatch.setattr(delivery, "order_reservation_locations", lambda _conn, _order_id: [55])

    with pytest.raises(HTTPException) as error:
        delivery.create_shipment(delivery.DeliveryCreate(
            order_id=8, delivery_pin="800001", recipient_name="Customer",
            recipient_phone="9876543210", address="Patna delivery address", location_id=99,
        ))

    assert error.value.status_code == 409
