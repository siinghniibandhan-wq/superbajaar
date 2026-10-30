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
    response = client.get(
        "/api/catalogue/categories",
        headers={"Authorization": "Bearer invalid"},
    )
    assert response.status_code == 503



def test_admin_cannot_demote_or_deactivate_another_owner():
    from fastapi import HTTPException
    import pytest
    from app.api.auth import _require_owner_for_owner_change

    admin = {"id": 10, "role": "admin"}
    owner = {"id": 20, "role": "owner", "is_active": True}
    with pytest.raises(HTTPException) as error:
        _require_owner_for_owner_change(admin, owner, "admin", True)
    assert error.value.status_code == 403
    with pytest.raises(HTTPException) as error:
        _require_owner_for_owner_change(admin, owner, "owner", False)
    assert error.value.status_code == 403


def test_owner_can_manage_another_owner_subject_to_last_owner_guard():
    from app.api.auth import _require_owner_for_owner_change

    owner_actor = {"id": 10, "role": "owner"}
    target = {"id": 20, "role": "owner", "is_active": True}
    assert _require_owner_for_owner_change(owner_actor, target, "admin", True) is None
    assert _require_owner_for_owner_change(owner_actor, target, "owner", False) is None


def test_admin_can_update_non_owner_user_without_owner_privilege():
    from app.api.auth import _require_owner_for_owner_change

    admin = {"id": 10, "role": "admin"}
    staff = {"id": 20, "role": "staff", "is_active": True}
    assert _require_owner_for_owner_change(admin, staff, "viewer", True) is None
