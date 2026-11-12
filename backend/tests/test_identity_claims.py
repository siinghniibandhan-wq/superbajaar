from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_customer_identity_claim_submission_requires_customer_session():
    response = client.post(
        "/api/customer-auth/identity-claims",
        json={"target_sbid": "SBID-0123456789ABCDEF0123", "reason": "This is my existing profile"},
    )
    assert response.status_code == 401


def test_customer_identity_claim_status_requires_customer_session():
    response = client.get("/api/customer-auth/identity-claims")
    assert response.status_code == 401


def test_customer_identity_claim_status_does_not_accept_another_customer_id():
    response = client.get("/api/customer-auth/identity-claims?customer_id=123")
    assert response.status_code == 401


def test_legacy_identity_reconciliation_preview_requires_admin_session():
    response = client.get("/api/identity/reconciliation/preview")
    assert response.status_code == 403


def test_customer_identity_claim_cancellation_requires_customer_session():
    response = client.post("/api/customer-auth/identity-claims/123/cancel")
    assert response.status_code == 401
