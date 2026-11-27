import asyncio
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from app.core import auth_middleware


def request(method="GET", path="/api/orders"):
    return SimpleNamespace(
        method=method,
        url=SimpleNamespace(path=path),
        headers={},
        state=SimpleNamespace(),
    )


def test_protected_route_fails_closed_when_database_is_not_configured(monkeypatch):
    monkeypatch.setattr(auth_middleware.settings, "database_url", "")
    with pytest.raises(HTTPException) as exc:
        asyncio.run(auth_middleware.require_active_session(request()))
    assert exc.value.status_code == 503
    assert "authentication storage" in exc.value.detail.lower()


def test_public_health_route_remains_available_without_database(monkeypatch):
    monkeypatch.setattr(auth_middleware.settings, "database_url", "")
    asyncio.run(auth_middleware.require_active_session(request("GET", "/api/health")))


def test_public_catalogue_reads_remain_available_without_database(monkeypatch):
    monkeypatch.setattr(auth_middleware.settings, "database_url", "")
    req = request("GET", "/api/catalogue/products")
    asyncio.run(auth_middleware.require_active_session(req))
    assert req.state.public_catalogue is True


def test_security_headers_are_added_to_api_responses():
    from app.main import SecurityHeadersMiddleware

    async def app(scope, receive, send):
        await send({"type": "http.response.start", "status": 200, "headers": []})
        await send({"type": "http.response.body", "body": b"ok"})

    middleware = SecurityHeadersMiddleware(app)
    sent = []

    async def receive():
        return {"type": "http.request", "body": b"", "more_body": False}

    async def send(message):
        sent.append(message)

    asyncio.run(
        middleware(
            {"type": "http", "method": "GET", "path": "/api/health", "headers": []},
            receive,
            send,
        )
    )
    headers = dict(sent[0]["headers"])
    assert headers[b"x-content-type-options"] == b"nosniff"
    assert headers[b"referrer-policy"] == b"strict-origin-when-cross-origin"
    assert headers[b"content-security-policy"] == b"default-src 'none'; frame-ancestors 'none'"
    assert headers[b"x-frame-options"] == b"DENY"
