from fastapi.testclient import TestClient

from app.core.config import settings
from app.main import app

client = TestClient(app, follow_redirects=False)


def test_providers_empty_when_unconfigured(monkeypatch):
    monkeypatch.setattr(settings, "google_oauth_client_id", "")
    monkeypatch.setattr(settings, "github_oauth_client_id", "")
    r = client.get("/api/customer-auth/oauth/providers")
    assert r.status_code == 200 and r.json() == {"providers": []}


def test_start_redirects_to_google_with_state(monkeypatch):
    monkeypatch.setattr(settings, "jwt_secret_key", "x" * 40)
    monkeypatch.setattr(settings, "google_oauth_client_id", "cid")
    monkeypatch.setattr(settings, "google_oauth_client_secret", "sec")
    monkeypatch.setattr(settings, "public_api_base_url", "https://api.example.com")
    r = client.get("/api/customer-auth/oauth/google/start")
    assert r.status_code == 302
    assert r.headers["location"].startswith("https://accounts.google.com/")
    assert "state=" in r.headers["location"]
    cookie = r.headers["set-cookie"].lower()
    assert "sb_oauth_nonce" in cookie
    assert "httponly" in cookie
    assert "secure" in cookie
    assert "samesite=lax" in cookie
    assert "max-age=600" in cookie


def test_callback_rejects_missing_nonce_cookie(monkeypatch):
    monkeypatch.setattr(settings, "jwt_secret_key", "x" * 40)
    monkeypatch.setattr(settings, "google_oauth_client_id", "cid")
    monkeypatch.setattr(settings, "google_oauth_client_secret", "sec")
    monkeypatch.setattr(settings, "public_api_base_url", "https://api.example.com")
    start = client.get("/api/customer-auth/oauth/google/start")
    state = start.headers["location"].split("state=")[1].split("&")[0]
    client.cookies.clear()
    r = client.get(f"/api/customer-auth/oauth/google/callback?code=abc&state={state}")
    assert r.status_code == 302 and "error=" in r.headers["location"]


def test_unknown_provider_404():
    assert client.get("/api/customer-auth/oauth/facebook/start").status_code == 404
