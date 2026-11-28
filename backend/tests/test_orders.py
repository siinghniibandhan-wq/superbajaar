from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_orders_requires_database_configuration(monkeypatch):
    from app.api import orders

    monkeypatch.setattr(orders.settings, "database_url", "")
    response = client.get("/api/orders")
    assert response.status_code == 503
    assert response.json()["detail"] == "Orders database is not configured"


def test_order_requires_idempotency_key_before_database_access():
    response = client.post("/api/orders", json={
        "channel": "website", "customer_name": "Test customer",
        "lines": [{"variant_id": 1, "quantity": 1}],
    })
    assert response.status_code == 422
    assert "checkout_idempotency_key" in str(response.json())


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


def test_checkout_idempotency_uses_transaction_scoped_advisory_lock():
    from app.api.orders import _lock_checkout_idempotency_key

    class RecordingConnection:
        def __init__(self):
            self.calls = []

        def execute(self, statement, params):
            self.calls.append((statement, params))

    conn = RecordingConnection()
    _lock_checkout_idempotency_key(conn, "checkout-attempt-123")

    assert len(conn.calls) == 1
    statement, params = conn.calls[0]
    assert "pg_advisory_xact_lock" in statement
    assert "hashtextextended" in statement
    assert params == ("checkout-attempt-123",)

def test_promotion_code_is_normalized_and_validated():
    from app.api.orders import PromotionCreate
    payload = PromotionCreate(
        code=" welcome-10 ", name="Welcome", discount_type="percent", discount_value="10",
    )
    assert payload.code == "WELCOME-10"
    assert payload.maximum_discount is None


@pytest.mark.parametrize("payload", [
    {"code":"A","name":"Short","discount_type":"percent","discount_value":"101"},
    {"code":"FIXED","name":"Fixed","discount_type":"fixed","discount_value":"10","maximum_discount":"5"},
    {"code":"BAD CODE","name":"Bad","discount_type":"fixed","discount_value":"10"},
])
def test_promotion_configuration_rejects_invalid_values(payload):
    from app.api.orders import PromotionCreate
    from pydantic import ValidationError
    with pytest.raises(ValidationError):
        PromotionCreate(**payload)


def test_promotion_admin_routes_require_admin(monkeypatch):
    response = client.get("/api/orders/promotions")
    assert response.status_code == 403
    response = client.post("/api/orders/promotions", json={
        "code":"SAVE10","name":"Save ten","discount_type":"percent","discount_value":10,
    })
    assert response.status_code == 403


def test_promotion_quote_requires_database_configuration(monkeypatch):
    from app.api import orders
    monkeypatch.setattr(orders.settings, "database_url", "")
    response = client.get("/api/orders/promotions/quote?code=SAVE10&subtotal=100")
    assert response.status_code == 503
