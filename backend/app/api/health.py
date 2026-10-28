from fastapi import APIRouter
from fastapi.responses import JSONResponse
import psycopg

from app.core.config import settings

router = APIRouter(tags=["health"])

_REQUIRED_TABLES = {"orders", "loyalty_rules", "schema_migrations"}


@router.get("/health")
def health():
    """Readiness probe that reports only safe status fields."""
    if not settings.database_url:
        return JSONResponse(
            {"status": "degraded", "database": "unavailable"},
            status_code=503,
        )
    try:
        with psycopg.connect(settings.database_url, connect_timeout=3) as conn:
            rows = conn.execute(
                "SELECT table_name FROM information_schema.tables "
                "WHERE table_schema = 'public' AND table_name = ANY(%s)",
                (list(_REQUIRED_TABLES),),
            ).fetchall()
        present = {row[0] if not isinstance(row, dict) else row["table_name"] for row in rows}
        if not _REQUIRED_TABLES.issubset(present):
            return JSONResponse(
                {"status": "degraded", "database": "unavailable"},
                status_code=503,
            )
    except psycopg.Error:
        # Never return connection strings, SQL, or driver exception details.
        return JSONResponse(
            {"status": "degraded", "database": "unavailable"},
            status_code=503,
        )
    return {"status": "ok", "database": "connected"}
