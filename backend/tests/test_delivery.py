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

 

def test_location_ranking_prefers_highest_available_stock():
    from app.api.delivery import _rank_locations_by_available_stock

    locations = [
        {"id": 7, "available_stock": 12},
        {"id": 3, "available_stock": 28},
        {"id": 5, "available_stock": 28},
    ]

    ranked = _rank_locations_by_available_stock(locations)

    assert [location["id"] for location in ranked] == [3, 5, 7]


def test_location_ranking_does_not_mutate_database_rows():
    from app.api.delivery import _rank_locations_by_available_stock

    locations = [
        {"id": 2, "available_stock": 4},
        {"id": 1, "available_stock": 9},
    ]

    ranked = _rank_locations_by_available_stock(locations)

    assert ranked[0]["id"] == 1
    assert [location["id"] for location in locations] == [2, 1]
