from pathlib import Path

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_customer_redemption_quote_requires_customer_session(monkeypatch):
    from app.api import loyalty

    monkeypatch.setattr(loyalty.settings, "database_url", "")
    response = client.get("/api/loyalty/customer/redemption-quote?amount=100")
    assert response.status_code == 401
    assert response.json()["detail"] == "Customer sign-in required"


def test_order_rejects_coin_redemption_for_non_website_channels(monkeypatch):
    from app.api import orders

    monkeypatch.setattr(orders.settings, "database_url", "")
    response = client.post("/api/orders", json={
        "channel": "manual",
        "customer_name": "Test Customer",
        "delivery_pin": "560001",
        "redeem_coins": 10,
        "lines": [{"variant_id": 1, "quantity": 1}],
    })
    assert response.status_code == 422
    assert "website checkout" in response.json()["detail"].lower()


def test_loyalty_migration_is_required_and_additive():
    root = Path(__file__).resolve().parents[1]
    required = (root / "schema_required.txt").read_text()
    migration = root / "schema" / "028_super_coins_checkout_redemption.sql"

    assert "028_super_coins_checkout_redemption.sql" in required
    assert migration.exists()
    sql = migration.read_text().lower()
    assert "create table if not exists" in sql
    assert "drop table" not in sql
    assert "drop column" not in sql
    assert "truncate " not in sql


def test_admin_loyalty_accounts_use_shared_balance_calculation(monkeypatch):
    from starlette.requests import Request
    from app.api import loyalty

    class Result:
        def fetchall(self):
            return [{
                "id": 17,
                "customer_email": "customer@example.com",
                "card_number": "SB-TEST17",
                "created_at": "2026-11-03T00:00:00Z",
            }]

    class Connection:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def execute(self, query, params):
            assert "GROUP BY" not in query
            assert "loyalty_expiration_allocations" not in query
            assert params == (50, 0)
            return Result()

    monkeypatch.setattr(loyalty, "_admin", lambda _request: None)
    monkeypatch.setattr(loyalty, "_connection", lambda: Connection())
    monkeypatch.setattr(loyalty, "available_balance", lambda _conn, account_id: 23 if account_id == 17 else 0)

    request = Request({
        "type": "http",
        "method": "GET",
        "path": "/api/loyalty/admin/accounts",
        "headers": [],
        "query_string": b"",
    })
    response = loyalty.list_loyalty_accounts(request, limit=50, offset=0)

    assert response["items"][0]["available_coins"] == 23
    assert response["items"][0]["card_number"] == "SB-TEST17"



def test_super_coins_permissions_migration_is_required_and_least_privilege():
    root = Path(__file__).resolve().parents[1]
    required = (root / "schema_required.txt").read_text()
    migration = root / "schema" / "030_super_coins_loyalty_permissions.sql"

    assert "030_super_coins_loyalty_permissions.sql" in required
    assert migration.exists()
    sql = migration.read_text().lower()

    assert "grant select, insert on table public.loyalty_expiration_allocations" in sql
    assert "grant select, insert, update on table public.loyalty_order_redemptions" in sql
    assert "grant insert on table public.loyalty_redemption_restorations" in sql
    assert "pg_get_serial_sequence" in sql
    assert "grant usage, select on sequence" in sql
    assert "grant all" not in sql
    assert "on all tables" not in sql
    assert "on all sequences" not in sql
    assert "drop table" not in sql
    assert "truncate " not in sql


def test_admin_can_update_partner_enquiry_status(monkeypatch):
    from starlette.requests import Request
    from app.api import loyalty

    class Result:
        def fetchone(self):
            return {"id": 12, "status": "reviewing", "updated_at": "2026-11-11T00:00:00Z"}

    class Connection:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def execute(self, query, params):
            assert "UPDATE partner_enquiries SET status=%s" in query
            assert params == ("reviewing", 12)
            return Result()

    monkeypatch.setattr(loyalty, "_admin", lambda _request: None)
    monkeypatch.setattr(loyalty, "_connection", lambda: Connection())
    request = Request({
        "type": "http", "method": "PATCH",
        "path": "/api/loyalty/admin/partner-enquiries/12",
        "headers": [], "query_string": b"",
    })
    response = loyalty.update_partner_enquiry_status(
        12, loyalty.PartnerEnquiryStatus(status="reviewing"), request
    )
    assert response["id"] == 12
    assert response["status"] == "reviewing"
