from decimal import Decimal
from unittest.mock import MagicMock

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


def _fake_order_connection():
    conn = MagicMock()
    conn.__enter__.return_value = conn
    variant_cursor = MagicMock()
    variant_cursor.fetchall.return_value = [
        {"id": 7, "sku": "SB-TEST-7", "selling_price": Decimal("125.00")}
    ]
    order_cursor = MagicMock()
    order_cursor.fetchone.return_value = {
        "id": 101,
        "order_number": "SB-TEST-ORDER",
        "channel": "website",
        "customer_name": "Test customer",
        "customer_phone": None,
        "customer_email": None,
        "delivery_pin": None,
        "status": "placed",
        "subtotal": Decimal("125.00"),
        "total": Decimal("125.00"),
        "notes": None,
        "created_at": "2026-10-29T00:00:00Z",
        "updated_at": "2026-10-29T00:00:00Z",
    }

    def execute(sql, params=None):
        cursor = MagicMock()
        if "FROM product_variants" in sql:
            return variant_cursor
        if "INSERT INTO orders" in sql:
            # Mirror the optional email value returned by PostgreSQL.
            order_cursor.fetchone.return_value["customer_email"] = params[4]
            return order_cursor
        return cursor

    conn.execute.side_effect = execute
    return conn


def test_create_website_order_without_customer_email(monkeypatch):
    from app.api import orders

    monkeypatch.setattr(orders.settings, "database_url", "postgresql://test")
    monkeypatch.setattr(orders, "_connect", _fake_order_connection)
    response = client.post("/api/orders", json={
        "channel": "website",
        "customer_name": "Test customer",
        "lines": [{"variant_id": 7, "quantity": 1}],
    })
    assert response.status_code == 201
    assert response.json()["customer_email"] is None


def test_create_website_order_with_customer_email(monkeypatch):
    from app.api import orders

    monkeypatch.setattr(orders.settings, "database_url", "postgresql://test")
    monkeypatch.setattr(orders, "_connect", _fake_order_connection)
    response = client.post("/api/orders", json={
        "channel": "website",
        "customer_name": "Test customer",
        "customer_email": "customer@example.com",
        "lines": [{"variant_id": 7, "quantity": 1}],
    })
    assert response.status_code == 201
    assert response.json()["customer_email"] == "customer@example.com"


def test_order_listing_requires_authentication_when_database_is_configured(monkeypatch):
    from app.api import orders

    monkeypatch.setattr(orders.settings, "database_url", "postgresql://test")
    response = client.get("/api/orders")
    assert response.status_code == 401


def test_marking_dispatched_order_delivered_awards_loyalty_coins(monkeypatch):
    from app.api import orders

    conn = MagicMock()
    conn.__enter__.return_value = conn
    current = {"status": "dispatched", "customer_email": "customer@example.com", "order_number": "SB-ORDER-1"}
    updated = {"id": 101, "order_number": "SB-ORDER-1", "status": "delivered", "updated_at": "2026-10-29T00:00:00Z"}
    account = {"id": 55}
    lines = [{"line_id": 8, "line_total": Decimal("250.00"), "product_id": 3, "category_id": 2}]
    earned_inserts = []

    def execute(sql, params=None):
        cursor = MagicMock()
        if "SELECT status, customer_email, order_number FROM orders" in sql:
            cursor.fetchone.return_value = current
        elif "UPDATE orders SET status" in sql:
            cursor.fetchone.return_value = updated
        elif "SELECT id FROM loyalty_accounts" in sql:
            cursor.fetchone.return_value = account
        elif "SELECT ol.id AS line_id" in sql:
            cursor.fetchall.return_value = lines
        elif "scope_type='product'" in sql or "scope_type='category'" in sql:
            cursor.fetchone.return_value = None
        elif "scope_type='default'" in sql:
            cursor.fetchone.return_value = {"coins_per_100": Decimal("1")}
        elif "INSERT INTO loyalty_transactions" in sql:
            earned_inserts.append(params)
        return cursor

    conn.execute.side_effect = execute
    monkeypatch.setattr(orders, " _unused", None, raising=False)
    monkeypatch.setattr(orders.settings, "database_url", "")
    monkeypatch.setattr(orders, "_connect", lambda: conn)

    response = client.patch("/api/orders/101/status", json={"status": "delivered"})

    assert response.status_code == 200
    assert response.json()["status"] == "delivered"
    assert len(earned_inserts) == 1
    assert earned_inserts[0][1] == 2
    assert earned_inserts[0][-1] == "earn:order:101:line:8"
