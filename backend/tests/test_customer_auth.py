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



def _request_with_peer(peer, headers=None):
    from starlette.requests import Request

    encoded_headers = [(key.lower().encode(), value.encode()) for key, value in (headers or {}).items()]
    return Request({
        "type": "http",
        "asgi": {"version": "3.0"},
        "http_version": "1.1",
        "method": "POST",
        "scheme": "http",
        "path": "/api/customer-auth/login",
        "raw_path": b"/api/customer-auth/login",
        "query_string": b"",
        "headers": encoded_headers,
        "client": (peer, 12345),
        "server": ("testserver", 80),
    })


def test_customer_auth_uses_x_real_ip_only_from_local_nginx():
    from app.api.customer_auth import _client_ip

    request = _request_with_peer("127.0.0.1", {
        "X-Real-IP": "203.0.113.10",
        "X-Forwarded-For": "198.51.100.99",
    })
    assert _client_ip(request) == "203.0.113.10"


def test_customer_auth_ignores_spoofed_ip_headers_from_nonlocal_peer():
    from app.api.customer_auth import _client_ip

    request = _request_with_peer("198.51.100.20", {
        "X-Real-IP": "203.0.113.10",
        "X-Forwarded-For": "192.0.2.44",
    })
    assert _client_ip(request) == "198.51.100.20"


def test_customer_auth_rate_limit_blocks_sixth_attempt_for_same_ip(monkeypatch):
    from fastapi import HTTPException
    from app.api import customer_auth

    monkeypatch.setattr(customer_auth, "_RATE_LIMIT_BUCKETS", {})
    request = _request_with_peer("198.51.100.30")
    for _ in range(5):
        customer_auth._enforce_rate_limit(request, "login", ["person@example.com"])
    try:
        customer_auth._enforce_rate_limit(request, "login", ["person@example.com"])
        assert False, "sixth attempt should be rate limited"
    except HTTPException as exc:
        assert exc.status_code == 429
        assert "Retry-After" in exc.headers


def test_customer_auth_rate_limit_applies_to_identifier_across_ips(monkeypatch):
    from fastapi import HTTPException
    from app.api import customer_auth

    monkeypatch.setattr(customer_auth, "_RATE_LIMIT_BUCKETS", {})
    for index in range(5):
        request = _request_with_peer(f"198.51.100.{index + 1}")
        customer_auth._enforce_rate_limit(request, "login", ["person@example.com"])
    request = _request_with_peer("198.51.100.99")
    try:
        customer_auth._enforce_rate_limit(request, "login", ["person@example.com"])
        assert False, "sixth attempt for the same identifier should be rate limited"
    except HTTPException as exc:
        assert exc.status_code == 429


def test_customer_registration_rejects_phone_with_letters():
    response = client.post("/api/customer-auth/register", json={
        "full_name": "Test Customer",
        "email": "customer@example.com",
        "phone": "abc9876543210",
        "password": "strong-enough-password",
    })
    assert response.status_code == 422
