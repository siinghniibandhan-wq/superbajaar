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



def test_public_support_ticket_rejects_invalid_payload_before_database_access():
    response = client.post("/api/customers/support-portal/tickets", json={
        "name": "Test Customer", "phone": "1234567890", "email": "not-an-email",
        "subject": "Order help", "description": "Please help with my order",
    })
    assert response.status_code == 422


def test_public_support_ticket_tracking_requires_both_contact_fields():
    response = client.get("/api/customers/support-portal/tickets/SUP-ABC123?email=customer@example.com")
    assert response.status_code == 422
    assert "both the email address and phone number" in response.json()["detail"]


def test_public_support_ticket_requires_contact_details():
    response = client.get("/api/customers/support-portal/tickets/SUP-ABC123")
    assert response.status_code == 422
