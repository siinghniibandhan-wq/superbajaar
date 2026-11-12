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