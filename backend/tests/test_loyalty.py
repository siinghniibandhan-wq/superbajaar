from unittest.mock import MagicMock

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_loyalty_rules_are_public_and_return_default_rule(monkeypatch):
    from app.api import loyalty

    conn = MagicMock()
    conn.__enter__.return_value = conn
    conn.execute.return_value.fetchall.return_value = [
        {"scope_type": "default", "scope_id": None, "coins_per_100": 1, "is_active": True}
    ]
    monkeypatch.setattr(loyalty.settings, "database_url", "postgresql://test")
    monkeypatch.setattr(loyalty, "_connection", lambda: conn)

    response = client.get("/api/loyalty/rules")

    assert response.status_code == 200
    body = response.json()
    assert body["default_coins_per_100"] == 1
    assert body["expiry_days"] == 365
    assert any(item["scope_type"] == "default" for item in body["items"])
