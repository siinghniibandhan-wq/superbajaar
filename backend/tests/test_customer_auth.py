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


def test_customer_profile_update_requires_customer_session():
    response = client.patch("/api/customer-auth/me", json={"full_name": "Updated Buyer"})
    assert response.status_code == 401


def test_customer_profile_update_rejects_blank_name():
    response = client.patch("/api/customer-auth/me", json={"full_name": "  "})
    assert response.status_code == 422



def test_authenticated_customer_identity_is_provisioned_from_exact_account_id(monkeypatch):
    from app.api import customer_auth

    calls = []

    class Identity:
        def __init__(self, conn):
            pass

        def create_party(self, **kwargs):
            calls.append(("create_party", kwargs))
            return {"id": 91, "sbid": "SBID-0123456789ABCDEF0123"}

        def link_profile(self, **kwargs):
            calls.append(("link_profile", kwargs))

        def link_auth_account(self, **kwargs):
            calls.append(("link_auth_account", kwargs))

    class Connection:
        def execute(self, query, params=()):
            if "FROM identity_profiles" in query:
                return type("Result", (), {"fetchone": lambda self: None})()
            if "FROM identity_auth_accounts" in query:
                return type("Result", (), {"fetchone": lambda self: None})()
            if "FROM identity_parties" in query:
                return type("Result", (), {"fetchone": lambda self: {
                    "id": 91, "sbid": "SBID-0123456789ABCDEF0123",
                    "party_type": "individual", "status": "active",
                }})()
            raise AssertionError(f"Unexpected query: {query}")

    monkeypatch.setattr(customer_auth, "IdentityService", Identity)
    result = customer_auth._ensure_customer_identity(Connection(), 42, "Existing Customer")

    assert result == "SBID-0123456789ABCDEF0123"
    assert calls[0][0] == "create_party"
    assert calls[1][0] == "link_profile"
    assert calls[1][1]["source_id"] == 42
    assert calls[2][0] == "link_auth_account"
    assert calls[2][1]["source_id"] == 42


def test_authenticated_customer_identity_rejects_conflicting_profile_and_login_links(monkeypatch):
    from fastapi import HTTPException
    from app.api import customer_auth

    class Identity:
        def __init__(self, conn):
            raise AssertionError("IdentityService must not be used for conflicting links")

    class Connection:
        def execute(self, query, params=()):
            if "FROM identity_profiles" in query:
                return type("Result", (), {"fetchone": lambda self: {"party_id": 10, "status": "active"}})()
            if "FROM identity_auth_accounts" in query:
                return type("Result", (), {"fetchone": lambda self: {"party_id": 11, "status": "active"}})()
            raise AssertionError(f"Unexpected query: {query}")

    monkeypatch.setattr(customer_auth, "IdentityService", Identity)
    try:
        customer_auth._ensure_customer_identity(Connection(), 42, "Existing Customer")
    except HTTPException as exc:
        assert exc.status_code == 409
        assert "conflict" in exc.detail
    else:
        raise AssertionError("Conflicting identity links must be rejected")
