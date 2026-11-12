from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_customers_requires_database_configuration(monkeypatch):
    from app.api import customers

    monkeypatch.setattr(customers.settings, "database_url", "")
    response = client.get("/api/customers")
    assert response.status_code == 503
    assert response.json()["detail"] == "Customer database is not configured"


def test_customer_rejects_blank_name_before_database_access():
    response = client.post("/api/customers", json={"name": "   "})
    assert response.status_code == 422


def test_customer_rejects_invalid_pin_before_database_access():
    response = client.post("/api/customers", json={"name": "Test Customer", "pin_code": "123"})
    assert response.status_code == 422


def test_customer_rejects_invalid_email_format_before_database_access():
    response = client.post("/api/customers", json={"name": "Test Customer", "email": "not-an-email"})
    assert response.status_code == 422


def test_support_case_rejects_invalid_priority_before_database_access():
    response = client.post("/api/customers/support-cases", json={
        "subject": "Order question", "description": "Customer needs help", "priority": "critical",
    })
    assert response.status_code == 422


def test_support_case_rejects_invalid_status_before_database_access():
    response = client.patch("/api/customers/support-cases/1", json={"status": "teleported"})
    assert response.status_code == 422



def test_customer_support_ticket_rejects_blank_subject_before_database_access():
    response = client.post("/api/customers/support-portal/tickets", json={
        "subject": "   ", "description": "Please help with my order",
    })
    assert response.status_code == 422


def test_customer_support_ticket_uses_database_handler_not_contact_lookup():
    response = client.get("/api/customers/support-portal/tickets/SUP-ABC123")
    assert response.status_code == 503
    assert response.json()["detail"] == "Customer database is not configured"


def test_crm_creation_returns_canonical_sbid(monkeypatch):
    from app.api import customers

    class Result:
        def fetchone(self):
            return {"id": 12, "name": "Test Customer", "email": None, "phone": None}

    class Connection:
        def __enter__(self):
            return self
        def __exit__(self, *args):
            return False
        def transaction(self):
            from contextlib import nullcontext
            return nullcontext()
        def execute(self, sql, params=()):
            assert "INSERT INTO customers" in sql
            return Result()

    class Identity:
        def __init__(self, conn):
            pass
        def create_party(self, **kwargs):
            return {"id": 77, "sbid": "SBID-0123456789ABCDEF0123"}
        def link_profile(self, **kwargs):
            return {"id": 3}

    monkeypatch.setattr(customers, "_connect", Connection)
    monkeypatch.setattr(customers, "IdentityService", Identity)
    row = customers.create_customer(customers.CustomerIn(name="Test Customer"))
    assert row["sbid"] == "SBID-0123456789ABCDEF0123"
