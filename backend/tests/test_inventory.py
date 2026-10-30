from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_inventory_requires_database_configuration(monkeypatch):
    from app.api import inventory

    monkeypatch.setattr(inventory.settings, "database_url", "")
    response = client.get("/api/inventory/balances")
    assert response.status_code == 503
    assert response.json()["detail"] == "Inventory database is not configured"


def test_inventory_adjustment_rejects_zero_quantity():
    response = client.post("/api/inventory/adjustments", json={
        "variant_id": 1, "location_id": 1, "quantity": 0, "note": "Initial count",
    })
    assert response.status_code == 422


def test_inventory_adjustment_requires_note():
    response = client.post("/api/inventory/adjustments", json={
        "variant_id": 1, "location_id": 1, "quantity": 2,
    })
    assert response.status_code == 422


def test_stock_location_rejects_invalid_type_before_database_access():
    response = client.post("/api/inventory/locations", json={
        "name": "Main store", "location_type": "office",
    })
    assert response.status_code == 422


def test_stock_location_rejects_invalid_pin_code_before_database_access():
    response = client.post("/api/inventory/locations", json={
        "name": "Main store", "location_type": "store", "pin_code": "123",
    })
    assert response.status_code == 422


def test_inventory_issue_rejects_zero_quantity():
    response = client.post("/api/inventory/issues", json={
        "variant_id": 1, "location_id": 1, "quantity": 0, "note": "Damaged stock",
    })
    assert response.status_code == 422


def test_inventory_issue_requires_note():
    response = client.post("/api/inventory/issues", json={
        "variant_id": 1, "location_id": 1, "quantity": 1,
    })
    assert response.status_code == 422


def test_inventory_transfer_rejects_same_source_and_destination():
    response = client.post("/api/inventory/transfers", json={
        "variant_id": 1, "source_location_id": 1, "destination_location_id": 1,
        "quantity": 1, "note": "Move stock",
    })
    assert response.status_code == 422


def test_inventory_transfer_rejects_zero_quantity():
    response = client.post("/api/inventory/transfers", json={
        "variant_id": 1, "source_location_id": 1, "destination_location_id": 2,
        "quantity": 0, "note": "Move stock",
    })
    assert response.status_code == 422


def test_inventory_issue_requires_database_configuration(monkeypatch):
    from app.api import inventory

    monkeypatch.setattr(inventory.settings, "database_url", "")
    response = client.post("/api/inventory/issues", json={
        "variant_id": 1, "location_id": 1, "quantity": 1, "note": "Damaged stock",
    })
    assert response.status_code == 503
    assert response.json()["detail"] == "Inventory database is not configured"


def test_inventory_transfer_requires_database_configuration(monkeypatch):
    from app.api import inventory

    monkeypatch.setattr(inventory.settings, "database_url", "")
    response = client.post("/api/inventory/transfers", json={
        "variant_id": 1, "source_location_id": 1, "destination_location_id": 2,
        "quantity": 1, "note": "Move stock",
    })
    assert response.status_code == 503
    assert response.json()["detail"] == "Inventory database is not configured"


def test_inventory_count_rejects_negative_count():
    response = client.post("/api/inventory/counts", json={
        "variant_id": 1, "location_id": 1, "counted_quantity": -1, "note": "Cycle count",
    })
    assert response.status_code == 422


def test_inventory_count_requires_note():
    response = client.post("/api/inventory/counts", json={
        "variant_id": 1, "location_id": 1, "counted_quantity": 4,
    })
    assert response.status_code == 422


def test_inventory_issue_rejects_unknown_reason_type():
    response = client.post("/api/inventory/issues", json={
        "variant_id": 1, "location_id": 1, "quantity": 1,
        "note": "Damaged stock", "reason_type": "delete",
    })
    assert response.status_code == 422


def test_inventory_count_requires_database_configuration(monkeypatch):
    from app.api import inventory

    monkeypatch.setattr(inventory.settings, "database_url", "")
    response = client.post("/api/inventory/counts", json={
        "variant_id": 1, "location_id": 1, "counted_quantity": 4, "note": "Cycle count",
    })
    assert response.status_code == 503
    assert response.json()["detail"] == "Inventory database is not configured"


def test_physical_count_movement_reference_preserves_variance_direction():
    from decimal import Decimal
    from app.api.inventory import _physical_count_reference_type

    assert _physical_count_reference_type(Decimal("2.000")) == "physical_count_in"
    assert _physical_count_reference_type(Decimal("-2.000")) == "physical_count_out"


def test_stock_issue_movement_reference_preserves_reduction_reason():
    from app.api.inventory import _stock_issue_reference_type

    assert _stock_issue_reference_type("issue") == "manual_issue_out"
    assert _stock_issue_reference_type("scrap") == "manual_scrap_out"
