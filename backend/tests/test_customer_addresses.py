from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_customer_addresses_require_customer_session():
    assert client.get("/api/customer-auth/addresses").status_code == 401


def test_customer_address_creation_requires_customer_session():
    response = client.post("/api/customer-auth/addresses", json={
        "label": "Home",
        "recipient_name": "Test Buyer",
        "phone": "+919876543210",
        "address": "12 Example Road, Patna",
        "pin_code": "800001",
        "is_default": True,
    })
    assert response.status_code == 401


def test_customer_address_update_and_delete_require_customer_session():
    assert client.patch("/api/customer-auth/addresses/1", json={"label": "Work"}).status_code == 401
    assert client.delete("/api/customer-auth/addresses/1").status_code == 401
