"""Request authentication and role authorization dependency.

FastAPI dependencies run after request parsing/validation, allowing malformed
requests to return 422 while valid protected requests still require a session.
"""
from fastapi import HTTPException, Request
import psycopg
from psycopg.rows import dict_row

from app.api.auth import _decode
from app.core.config import settings


def method_is_public_serviceability(method: str, path: str, prefix: str) -> bool:
    return method == "GET" and path.startswith(prefix + "/delivery/serviceability/")


def _is_public_catalogue_read(method: str, path: str, prefix: str) -> bool:
    return method == "GET" and path in {
        prefix + "/catalogue/categories",
        prefix + "/catalogue/products",
        prefix + "/catalogue/variants",
    }


def _role_can_write(role: str, path: str) -> bool:
    if role in {"owner", "admin"}:
        return True
    if role == "viewer":
        return False
    if role == "manager":
        return path.startswith((
            "/api/inventory/", "/api/orders", "/api/payments",
            "/api/delivery/", "/api/customers", "/api/purchasing/",
        ))
    if role == "staff":
        return (
            path == "/api/orders"
            or (path.startswith("/api/orders/") and path.endswith("/status"))
            or path == "/api/delivery/shipments"
            or (path.startswith("/api/delivery/shipments/") and path.endswith("/status"))
            or path == "/api/customers/support-cases"
            or (path.startswith("/api/customers/support-cases/") and path.count("/") == 4)
        )
    return False


async def require_active_session(request: Request) -> None:
    """Authenticate a valid request and enforce role-based write access."""
    path = request.url.path
    prefix = settings.api_prefix.rstrip("/")
    public = {prefix + "/health", prefix + "/auth/login", prefix + "/customer-auth/register", prefix + "/customer-auth/login"}
    if method_is_public_serviceability(request.method, path, prefix):
        return
    # Public storefront support portal; tracking requires matching contact details.
    if path == prefix + "/loyalty/partner-enquiries" and request.method == "POST":
        return
    if request.method == "GET" and path in {
        prefix + "/loyalty/rules",
        prefix + "/loyalty/quote",
        prefix + "/loyalty/customer/account",
    }:
        return
    if path == prefix + "/customers/support-portal/tickets" and request.method == "POST":
        return
    if path.startswith(prefix + "/customers/support-portal/tickets/") and request.method == "GET":
        return
    if request.method == "OPTIONS" or not path.startswith(prefix + "/") or path in public:
        return

    # When DB configuration is absent, let each database-backed handler return
    # its explicit 503 response. With a configured database, auth remains required.
    if not settings.database_url:
        return

    if _is_public_catalogue_read(request.method, path, prefix):
        request.state.public_catalogue = True
        return

    authorization = request.headers.get("authorization", "")
    if not authorization.lower().startswith("bearer "):
        raise HTTPException(status_code=401, detail="Sign in to continue")
    try:
        claims = _decode(authorization.split(" ", 1)[1].strip())
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=401, detail="Invalid or expired access token") from exc

    if claims.get("typ") == "customer":
        customer_routes = {
            ("GET", prefix + "/customer-auth/me"),
            ("POST", prefix + "/customer-auth/logout"),
            ("GET", prefix + "/customer-auth/referrals"),
            ("GET", prefix + "/loyalty/customer/me"),
            ("POST", prefix + "/loyalty/customer/redeem"),
        }
        is_website_order = request.method == "POST" and path == prefix + "/orders"
        if (request.method, path) not in customer_routes and not is_website_order:
            raise HTTPException(status_code=403, detail="Customer session cannot access staff resources")
        try:
            with psycopg.connect(settings.database_url, row_factory=dict_row, connect_timeout=3) as conn:
                customer = conn.execute(
                    "SELECT c.id, c.email FROM customer_accounts c JOIN customer_sessions s ON s.customer_id=c.id "
                    "WHERE c.id=%s AND s.token_id=%s AND c.is_active=TRUE AND s.revoked_at IS NULL AND s.expires_at>now()",
                    (claims.get("sub"), claims.get("jti")),
                ).fetchone()
        except psycopg.Error as exc:
            raise HTTPException(status_code=503, detail="Customer authentication storage unavailable; verify migration 010") from exc
        if customer is None:
            raise HTTPException(status_code=401, detail="Customer session is no longer active")
        request.state.role = "customer"
        request.state.customer_id = customer["id"]
        request.state.customer_email = customer["email"]
        request.state.customer_token_id = claims.get("jti")
        if is_website_order:
            request.state.customer_checkout = True
        return

    if claims.get("typ"):
        raise HTTPException(status_code=401, detail="Invalid access token type")

    try:
        with psycopg.connect(settings.database_url, row_factory=dict_row, connect_timeout=3) as conn:
            row = conn.execute(
                "SELECT u.id, u.role FROM app_users u JOIN app_user_sessions s ON s.user_id=u.id "
                "WHERE u.id=%s AND s.token_id=%s AND u.is_active=TRUE AND s.revoked_at IS NULL AND s.expires_at>now()",
                (claims.get("sub"), claims.get("jti")),
            ).fetchone()
    except psycopg.Error as exc:
        raise HTTPException(
            status_code=503,
            detail="Authentication storage unavailable; verify database connectivity and migration 007",
        ) from exc
    if row is None:
        raise HTTPException(status_code=401, detail="Session is no longer active")

    role = row["role"]
    request.state.role = role
    if request.method not in {"GET", "HEAD"} and not _role_can_write(role, path):
        raise HTTPException(status_code=403, detail="Your role does not have permission to change this resource")
