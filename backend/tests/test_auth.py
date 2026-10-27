from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_login_rejects_bad_email_before_database_access():
    response = client.post("/api/v1/auth/login", json={"email": "bad", "password": "anything"})
    assert response.status_code == 422


def test_login_requires_configured_signing_secret(monkeypatch):
    from app.api.v1 import auth

    monkeypatch.setattr(auth.settings, "jwt_secret_key", "")
    response = client.post("/api/v1/auth/login", json={"email": "owner@example.com", "password": "long-enough-password"})
    assert response.status_code == 503


def test_me_requires_bearer_token():
    response = client.get("/api/v1/auth/me")
    assert response.status_code == 401


def test_invalid_bearer_token_is_rejected():
    response = client.get("/api/v1/auth/me", headers={"Authorization": "Bearer not-a-token"})
    assert response.status_code in (401, 503)
