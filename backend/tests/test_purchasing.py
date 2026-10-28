from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_purchasing_requires_database_configuration(monkeypatch):
    from app.api import purchasing

    monkeypatch.setattr(purchasing.settings, "database_url", "")
    response = client.get("/api/purchasing/suppliers")
    assert response.status_code == 503
    assert response.json()["detail"] == "Purchasing database is not configured"


def test_supplier_rejects_blank_name_before_database_access():
    response = client.post("/api/purchasing/suppliers", json={"name": "   "})
    assert response.status_code == 422


def test_supplier_rejects_invalid_gstin_shape_before_database_access():
    response = client.post("/api/purchasing/suppliers", json={"name": "Test supplier", "gstin": "INVALID"})
    assert response.status_code == 422


def test_purchase_order_requires_at_least_one_line():
    response = client.post("/api/purchasing/orders", json={
        "supplier_id": 1, "location_id": 1, "lines": [],
    })
    assert response.status_code == 422


def test_purchase_order_rejects_duplicate_variant_lines():
    response = client.post("/api/purchasing/orders", json={
        "supplier_id": 1, "location_id": 1,
        "lines": [
            {"variant_id": 1, "quantity": 2, "unit_cost": 10},
            {"variant_id": 1, "quantity": 3, "unit_cost": 11},
        ],
    })
    assert response.status_code == 422


def test_goods_receipt_requires_lines():
    response = client.post("/api/purchasing/orders/1/receive", json={"lines": []})
    assert response.status_code == 422


def test_purchase_order_approval_requires_database_configuration(monkeypatch):
    from app.api import purchasing

    monkeypatch.setattr(purchasing.settings, "database_url", "")
    response = client.post("/api/purchasing/orders/1/approve")
    assert response.status_code == 503
    assert response.json()["detail"] == "Purchasing database is not configured"


def test_purchase_order_approval_rejects_non_integer_id():
    response = client.post("/api/purchasing/orders/not-a-number/approve")
    assert response.status_code == 422
