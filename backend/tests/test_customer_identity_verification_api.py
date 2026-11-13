"""Route registration and authorization contract for customer identity verification."""
from app.api.customer_identity_verification import router
from app.core.auth_middleware import require_active_session


def test_customer_identity_verification_routes_are_registered():
    routes = {(route.path, tuple(sorted(route.methods or []))) for route in router.routes}
    assert ("/customer-auth/identity-verification/otp/request", ("POST",)) in routes
    assert ("/customer-auth/identity-verification/otp/verify", ("POST",)) in routes
    assert ("/customer-auth/identity-verification/documents", ("POST",)) in routes
    assert ("/customer-auth/identity-verification/documents/{document_id}/download", ("GET",)) in routes


def test_customer_identity_verification_endpoints_are_scoped_under_customer_auth():
    assert router.prefix == "/customer-auth/identity-verification"
    assert all(route.path.startswith(router.prefix) for route in router.routes)
