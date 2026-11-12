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


def test_customer_claim_cancel_route_is_scoped_to_numeric_claim_ids():
    from app.core.auth_middleware import is_customer_identity_claim_route

    assert is_customer_identity_claim_route("POST", "/api/customer-auth/identity-claims/123/cancel")
    assert not is_customer_identity_claim_route("POST", "/api/customer-auth/identity-claims/not-a-number/cancel")
    assert not is_customer_identity_claim_route("DELETE", "/api/customer-auth/identity-claims/123/cancel")



def test_identity_review_rejects_unimplemented_otp_proof_methods():
    from pydantic import ValidationError
    from app.api.identity import ReviewIn

    for method in ("email_otp", "phone_otp", "automated_otp"):
        try:
            ReviewIn(decision="approve", proof_verified=True, proof_method=method,
                     reason="Evidence was checked by an administrator")
        except ValidationError:
            continue
        raise AssertionError(f"unsupported proof method was accepted: {method}")


def test_identity_review_accepts_documented_manual_evidence_methods():
    from app.api.identity import ReviewIn

    for method in ("document_review", "in_person", "verified_account", "business_registry"):
        payload = ReviewIn(decision="approve", proof_verified=True, proof_method=method,
                           reason="Evidence was checked by an administrator")
        assert payload.proof_method == method
