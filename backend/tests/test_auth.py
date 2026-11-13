from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_login_rejects_bad_email_before_database_access():
    response = client.post("/api/auth/login", json={"email": "bad", "password": "anything"})
    assert response.status_code == 422


def test_login_requires_configured_signing_secret(monkeypatch):
    from app.api import auth
    monkeypatch.setattr(auth.settings, "jwt_secret_key", "")
    response = client.post("/api/auth/login", json={"email": "owner@example.com", "password": "long-enough-password"})
    assert response.status_code == 503


def test_me_requires_bearer_token():
    response = client.get("/api/auth/me")
    assert response.status_code == 401


def test_invalid_bearer_token_is_rejected():
    response = client.get("/api/auth/me", headers={"Authorization": "Bearer not-a-token"})
    assert response.status_code in (401, 503)


def test_protected_api_returns_service_unavailable_when_jwt_secret_missing(monkeypatch):
    from app.api import auth
    monkeypatch.setattr(auth.settings, "jwt_secret_key", "")
    response = client.get("/api/catalogue/categories", headers={"Authorization": "Bearer invalid"})
    assert response.status_code == 503


def test_super_admin_role_is_supported_but_owner_is_removed():
    from app.api.auth import USER_ROLES
    assert "super_admin" in USER_ROLES
    assert "owner" not in USER_ROLES


def test_only_super_admin_can_create_or_assign_super_admin_role():
    from app.api.auth import _can_manage_privileged_roles
    assert _can_manage_privileged_roles("super_admin")
    assert not _can_manage_privileged_roles("admin")


def test_identity_review_submission_requires_approve_permission():
    from app.core.auth_middleware import _action_for_request

    assert _action_for_request("POST", "/api/identity/review-queue/requests/42") == "approve"
    assert _action_for_request("GET", "/api/identity/review-queue/requests") == "read"
    assert _action_for_request("POST", "/api/identity/link-requests") == "create"
    assert _action_for_request("POST", "/api/identity/parties/42/merge") == "create"

def test_customer_identity_claim_routes_are_allowed_for_customer_sessions_only():
    from app.core.auth_middleware import is_customer_identity_claim_route

    assert is_customer_identity_claim_route("GET", "/api/customer-auth/identity-claims")
    assert is_customer_identity_claim_route("POST", "/api/customer-auth/identity-claims")
    assert not is_customer_identity_claim_route("DELETE", "/api/customer-auth/identity-claims")
    assert not is_customer_identity_claim_route("GET", "/api/identity")




def test_user_create_defaults_to_internal_account_without_linkage():
    from app.api.auth import UserCreate

    payload = UserCreate(
        email="staff@example.com",
        full_name="Staff User",
        password="long-enough-password",
    )
    assert payload.account_type == "internal"
    assert payload.employee_id is None
    assert payload.supplier_id is None


def test_user_create_requires_employee_record_for_employee_account():
    import pytest
    from pydantic import ValidationError
    from app.api.auth import UserCreate

    with pytest.raises(ValidationError):
        UserCreate(
            email="employee@example.com",
            full_name="Employee User",
            password="long-enough-password",
            account_type="employee",
        )


def test_user_create_accepts_employee_record_linkage():
    from app.api.auth import UserCreate

    payload = UserCreate(
        email="employee@example.com",
        full_name="Employee User",
        password="long-enough-password",
        account_type="employee",
        employee_id=42,
    )
    assert payload.account_type == "employee"
    assert payload.employee_id == 42


def test_user_create_requires_vendor_record_for_vendor_account():
    import pytest
    from pydantic import ValidationError
    from app.api.auth import UserCreate

    with pytest.raises(ValidationError):
        UserCreate(
            email="vendor@example.com",
            full_name="Vendor User",
            password="long-enough-password",
            account_type="vendor",
        )


def test_user_create_rejects_mixed_employee_and_vendor_links():
    import pytest
    from pydantic import ValidationError
    from app.api.auth import UserCreate

    with pytest.raises(ValidationError):
        UserCreate(
            email="employee@example.com",
            full_name="Employee User",
            password="long-enough-password",
            account_type="employee",
            employee_id=42,
            supplier_id=7,
        )



def test_existing_login_link_requires_employee_or_vendor_target():
    import pytest
    from pydantic import ValidationError
    from app.api.auth import UserLinkInput

    with pytest.raises(ValidationError):
        UserLinkInput(account_type="employee")


def test_existing_login_link_accepts_employee_target():
    from app.api.auth import UserLinkInput

    payload = UserLinkInput(account_type="employee", employee_id=42)
    assert payload.employee_id == 42
    assert payload.supplier_id is None


def test_existing_login_link_accepts_vendor_target():
    from app.api.auth import UserLinkInput

    payload = UserLinkInput(account_type="vendor", supplier_id=9)
    assert payload.supplier_id == 9
    assert payload.employee_id is None
