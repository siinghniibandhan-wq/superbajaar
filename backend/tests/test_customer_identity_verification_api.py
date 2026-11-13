"""Route registration and authorization contract for customer identity verification."""
from app.api.customer_identity_verification import router
from app.api.identity import router as admin_identity_router
from app.core.auth_middleware import _action_for_request


def test_customer_identity_verification_routes_are_registered():
    routes = {(route.path, tuple(sorted(route.methods or []))) for route in router.routes}
    assert ("/customer-auth/identity-verification/otp/request", ("POST",)) in routes
    assert ("/customer-auth/identity-verification/otp/verify", ("POST",)) in routes
    assert ("/customer-auth/identity-verification/documents", ("POST",)) in routes
    assert ("/customer-auth/identity-verification/documents/{document_id}/download", ("GET",)) in routes


def test_customer_identity_verification_endpoints_are_scoped_under_customer_auth():
    assert router.prefix == "/customer-auth/identity-verification"
    assert all(route.path.startswith(router.prefix) for route in router.routes)



def test_admin_identity_evidence_review_routes_are_registered():
    routes = {(route.path, tuple(sorted(route.methods or []))) for route in admin_identity_router.routes}
    assert ("/identity/documents/review-queue", ("GET",)) in routes
    assert ("/identity/documents/{document_id}/download", ("GET",)) in routes
    assert ("/identity/documents/{document_id}/review", ("POST",)) in routes


def test_identity_document_review_uses_approval_permission():
    assert _action_for_request("POST", "/api/identity/documents/23/review") == "approve"



def test_target_owner_claim_confirmation_routes_are_registered():
    paths = {route.path for route in router.routes}
    assert "/customer-auth/identity-verification/claims/pending" in paths
    assert "/customer-auth/identity-verification/claims/{request_id}/otp/request" in paths
    assert "/customer-auth/identity-verification/claims/{request_id}/otp/verify" in paths


def test_target_owner_claim_confirmation_is_allowlisted_without_opening_staff_routes():
    from app.core.auth_middleware import is_customer_identity_verification_claim_route

    assert is_customer_identity_verification_claim_route(
        "GET", "/api/customer-auth/identity-verification/claims/pending"
    )
    assert is_customer_identity_verification_claim_route(
        "POST", "/api/customer-auth/identity-verification/claims/42/otp/verify"
    )
    assert not is_customer_identity_verification_claim_route(
        "POST", "/api/identity/review-queue/requests/42"
    )
    assert not is_customer_identity_verification_claim_route(
        "POST", "/api/customer-auth/identity-verification/claims/42/otp/delete"
    )
