from fastapi import HTTPException, Request
from fastapi.responses import JSONResponse
import psycopg
from psycopg.rows import dict_row

from app.api.auth import _decode
from app.core.config import settings


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


async def require_active_session(request: Request, call_next):
    path = request.url.path
    prefix = settings.api_prefix.rstrip("/")
    public = {prefix + "/health", prefix + "/auth/login"}
    if request.method == "OPTIONS" or not path.startswith(prefix + "/") or path in public:
        return await call_next(request)

    # Public storefront reads are restricted to active catalogue data by route handlers.
    if _is_public_catalogue_read(request.method, path, prefix):
        request.state.public_catalogue = True
        return await call_next(request)
    # Public order creation is constrained to channel=website in create_order().
    if request.method == "POST" and path == prefix + "/orders":
        request.state.public_checkout = True
        request.state.role = "public"
        return await call_next(request)

    authorization = request.headers.get("authorization", "")
    if not authorization.lower().startswith("bearer "):
        return JSONResponse(status_code=401, content={"detail": "Sign in to continue"})
    try:
        claims = _decode(authorization.split(" ", 1)[1].strip())
    except HTTPException as exc:
        return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail})
    except Exception:
        return JSONResponse(status_code=401, content={"detail": "Invalid or expired access token"})

    if not settings.database_url:
        return JSONResponse(status_code=503, content={"detail": "Authentication database is not configured"})
    try:
        with psycopg.connect(settings.database_url, row_factory=dict_row, connect_timeout=3) as conn:
            row = conn.execute(
                "SELECT u.id, u.role FROM app_users u JOIN app_user_sessions s ON s.user_id=u.id "
                "WHERE u.id=%s AND s.token_id=%s AND u.is_active=TRUE AND s.revoked_at IS NULL AND s.expires_at>now()",
                (claims.get("sub"), claims.get("jti")),
            ).fetchone()
    except psycopg.Error:
        return JSONResponse(status_code=503, content={"detail": "Authentication storage unavailable; verify database connectivity and migration 007"})
    if row is None:
        return JSONResponse(status_code=401, content={"detail": "Session is no longer active"})

    role = row["role"]
    request.state.role = role
    if request.method not in {"GET", "HEAD"} and not _role_can_write(role, path):
        return JSONResponse(status_code=403, content={"detail": "Your role does not have permission to change this resource"})
    return await call_next(request)
