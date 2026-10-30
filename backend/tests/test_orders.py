from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_orders_requires_database_configuration(monkeypatch):
    from app.api import orders

    monkeypatch.setattr(orders.settings, "database_url", "")
    response = client.get("/api/orders")
    assert response.status_code == 503
    assert response.json()["detail"] == "Orders database is not configured"


def test_order_rejects_invalid_channel_before_database_access():
    response = client.post("/api/orders", json={
        "channel": "unknown", "customer_name": "Test customer",
        "lines": [{"variant_id": 1, "quantity": 1}],
    })
    assert response.status_code == 422


def test_order_rejects_invalid_delivery_pin_before_database_access():
    response = client.post("/api/orders", json={
        "channel": "website", "customer_name": "Test customer", "delivery_pin": "123",
        "lines": [{"variant_id": 1, "quantity": 1}],
    })
    assert response.status_code == 422


def test_order_requires_at_least_one_line():
    response = client.post("/api/orders", json={
        "channel": "pos", "customer_name": "Test customer", "lines": [],
    })
    assert response.status_code == 422


def test_order_status_rejects_unknown_value():
    response = client.patch("/api/orders/1/status", json={"status": "refunded"})
    assert response.status_code == 422

def test_order_rejects_duplicate_variant_lines():
    response = client.post("/api/orders", json={
        "channel": "website", "customer_name": "Test customer",
        "lines": [
            {"variant_id": 7, "quantity": 1},
            {"variant_id": 7, "quantity": 2},
        ],
    })
    assert response.status_code == 422
    assert "only once per order" in str(response.json())


def test_order_history_requires_database_configuration(monkeypatch):
    from app.api import orders

    monkeypatch.setattr(orders.settings, "database_url", "")
    response = client.get("/api/orders/1/history")
    assert response.status_code == 503
    assert response.json()["detail"] == "Orders database is not configured"


def test_order_history_rejects_non_integer_order_id():
    response = client.get("/api/orders/not-a-number/history")
    assert response.status_code == 422


def test_order_history_rejects_invalid_limit():
    response = client.get("/api/orders/1/history?limit=0")
    assert response.status_code == 422



def test_pos_order_requires_staff_selected_location_before_database_access():
    response = client.post("/api/orders", json={
        "channel": "pos", "customer_name": "Walk-in customer",
        "lines": [{"variant_id": 1, "quantity": 1}],
    })
    assert response.status_code == 422
    assert "staff-selected stock location" in response.json()["detail"]


def test_pos_order_rejects_invalid_location_id_before_database_access():
    response = client.post("/api/orders", json={
        "channel": "pos", "customer_name": "Walk-in customer", "location_id": 0,
        "lines": [{"variant_id": 1, "quantity": 1}],
    })
    assert response.status_code == 422
