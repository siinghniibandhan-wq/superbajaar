from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_customer_login_rejects_invalid_email_before_database_access():
    response = client.post("/api/customer-auth/login", json={"email": "not-an-email", "password": "anything"})
    assert response.status_code == 422


def test_customer_registration_requires_strong_enough_password():
    response = client.post("/api/customer-auth/register", json={
        "full_name": "Test Customer",
        "email": "customer@example.com",
        "password": "short",
    })
    assert response.status_code == 422


def test_customer_profile_requires_customer_session():
    response = client.get("/api/customer-auth/me")
    assert response.status_code == 401


def test_customer_referral_endpoint_requires_customer_session():
    response = client.get("/api/customer-auth/referrals")
    assert response.status_code == 401


def test_customer_order_history_requires_customer_session():
    assert client.get("/api/customer-auth/orders").status_code == 401
    assert client.get("/api/customer-auth/orders/SB-1").status_code == 401

def test_customer_identity_claim_rejects_malformed_sbid_before_authentication():
    response = client.post(
        "/api/customer-auth/identity-claims",
        json={"target_sbid": "SBID-NOT-A-REAL-ID", "reason": "I believe this belongs to me"},
    )
    assert response.status_code == 422



def test_public_customer_response_includes_generated_sbid():
    from app.api.customer_auth import _public_customer

    customer = _public_customer({
        "id": 7,
        "sbid": "SBID-0123456789ABCDEF0123",
        "email": "buyer@example.com",
        "full_name": "Test Buyer",
        "phone": "+919876543210",
        "referral_code": "SB12345678",
    })

    assert customer["sbid"] == "SBID-0123456789ABCDEF0123"
