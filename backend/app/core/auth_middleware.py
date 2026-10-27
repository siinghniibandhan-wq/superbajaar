from fastapi import Request
from fastapi.responses import JSONResponse
import psycopg
from psycopg.rows import dict_row

from app.api.v1.auth import _decode
from app.core.config import settings


async def require_active_session(request: Request, call_next):
    path = request.url.path
    prefix = settings.api_v1_prefix.rstrip("/")
    public = {prefix + "/health", prefix + "/auth/login"}
    if request.method == "OPTIONS" or not path.startswith(prefix + "/") or path in public:
        return await call_next(request)
    authorization = request.headers.get("authorization", "")
    if not authorization.lower().startswith("bearer "):
        return JSONResponse(status_code=401, content={"detail": "Sign in to continue"})
    try:
        claims = _decode(authorization.split(" ", 1)[1].strip())
        if not settings.database_url:
            return JSONResponse(status_code=503, content={"detail": "Authentication database is not configured"})
        with psycopg.connect(settings.database_url, row_factory=dict_row, connect_timeout=3) as conn:
            row = conn.execute(
                "SELECT u.id FROM app_users u JOIN app_user_sessions s ON s.user_id=u.id "
                "WHERE u.id=%s AND s.token_id=%s AND u.is_active=TRUE AND s.revoked_at IS NULL AND s.expires_at>now()",
                (claims.get("sub"), claims.get("jti")),
            ).fetchone()
        if row is None:
            return JSONResponse(status_code=401, content={"detail": "Session is no longer active"})
    except Exception:
        return JSONResponse(status_code=401, content={"detail": "Invalid or expired access token"})
    return await call_next(request)
