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
