from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_inventory_requires_database_configuration(monkeypatch):
    from app.api.v1 import inventory

    monkeypatch.setattr(inventory.settings, "database_url", "")
    response = client.get("/api/v1/inventory/balances")
    assert response.status_code == 503
    assert response.json()["detail"] == "Inventory database is not configured"


def test_inventory_adjustment_rejects_zero_quantity():
    response = client.post("/api/v1/inventory/adjustments", json={
        "variant_id": 1, "location_id": 1, "quantity": 0, "note": "Initial count",
    })
    assert response.status_code == 422


def test_inventory_adjustment_requires_note():
    response = client.post("/api/v1/inventory/adjustments", json={
        "variant_id": 1, "location_id": 1, "quantity": 2,
    })
    assert response.status_code == 422


def test_stock_location_rejects_invalid_type_before_database_access():
    response = client.post("/api/v1/inventory/locations", json={
        "name": "Main store", "location_type": "office",
    })
    assert response.status_code == 422


def test_stock_location_rejects_invalid_pin_code_before_database_access():
    response = client.post("/api/v1/inventory/locations", json={
        "name": "Main store", "location_type": "store", "pin_code": "123",
    })
    assert response.status_code == 422
