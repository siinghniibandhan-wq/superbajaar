import hashlib
import ipaddress
import time

import psycopg
from psycopg.rows import dict_row
from fastapi import HTTPException

from app.core.config import settings


_AUTH_LIMITS = {
    ("POST", "/api/auth/login"): (5, 60),
    ("POST", "/api/customer-auth/login"): (5, 60),
    ("POST", "/api/customer-auth/register"): (5, 60),
    ("POST", "/api/customer-auth/identity-verification/otp/request"): (3, 300),
    ("POST", "/api/customer-auth/identity-verification/otp/verify"): (5, 300),
    ("POST", "/api/portal-invitations/accept"): (5, 300),
}


def classify_rate_limit(method: str, path: str) -> tuple[int, int]:
    exact = _AUTH_LIMITS.get((method.upper(), path))
    if exact:
        return exact
    if method.upper() in {"POST", "PUT", "PATCH", "DELETE"}:
        return (60, 60)
    return (120, 60)


def rate_limit_bucket_key(client_ip: str, method: str, path: str) -> str:
    # Keep the key opaque; never persist raw IP addresses in the limiter table.
    route = path
    if path.startswith("/api/") and path.count("/") > 2:
        parts = path.strip("/").split("/")
        route = "/" + "/".join(parts[:2])
    material = f"{client_ip}|{method.upper()}|{route}".encode("utf-8")
    return hashlib.sha256(material).hexdigest()


def _trusted_client_ip(request) -> str:
    peer = request.client.host if request.client else "unknown"
    try:
        is_loopback_proxy = ipaddress.ip_address(peer).is_loopback
    except ValueError:
        is_loopback_proxy = False
    # Trust X-Real-IP only when the direct peer is a local reverse proxy.
    forwarded = request.headers.get("x-real-ip", "").strip()
    if is_loopback_proxy and forwarded:
        try:
            return str(ipaddress.ip_address(forwarded))
        except ValueError:
            pass
    return peer


def enforce_distributed_rate_limit(request) -> None:
    if not settings.database_url:
        return
    limit, window_seconds = classify_rate_limit(request.method, request.url.path)
    key = rate_limit_bucket_key(_trusted_client_ip(request), request.method, request.url.path)
    try:
        with psycopg.connect(settings.database_url, connect_timeout=2, row_factory=dict_row) as conn:
            row = conn.execute(
                """
                INSERT INTO api_rate_limit_buckets(bucket_key, window_started_at, request_count, updated_at)
                VALUES (%s, now(), 1, now())
                ON CONFLICT (bucket_key) DO UPDATE SET
                    request_count = CASE
                        WHEN api_rate_limit_buckets.window_started_at
                             <= now() - make_interval(secs => %s)
                        THEN 1 ELSE api_rate_limit_buckets.request_count + 1
                    END,
                    window_started_at = CASE
                        WHEN api_rate_limit_buckets.window_started_at
                             <= now() - make_interval(secs => %s)
                        THEN now() ELSE api_rate_limit_buckets.window_started_at
                    END,
                    updated_at = now()
                RETURNING request_count,
                    GREATEST(1, CEIL(EXTRACT(EPOCH FROM
                        (window_started_at + make_interval(secs => %s) - now())))::integer) AS retry_after
                """,
                (key, window_seconds, window_seconds, window_seconds),
            ).fetchone()
        if row["request_count"] > limit:
            raise HTTPException(
                status_code=429,
                detail="Too many requests; please retry later",
                headers={"Retry-After": str(row["retry_after"])},
            )
    except HTTPException:
        raise
    except psycopg.Error as exc:
        # Fail closed for mutations and authentication endpoints; reads remain available.
        if request.method.upper() in {"POST", "PUT", "PATCH", "DELETE"} or request.url.path.endswith(("/login", "/register")):
            raise HTTPException(status_code=503, detail="Rate-limit storage is unavailable") from exc
