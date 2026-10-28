from fastapi import APIRouter
from fastapi.responses import JSONResponse
import psycopg

from app.core.config import settings

router = APIRouter(tags=["health"])


@router.get("/health")
def health():
    if not settings.database_url:
        return JSONResponse({"status": "degraded", "database": "unavailable"}, status_code=503)
    try:
        with psycopg.connect(settings.database_url, connect_timeout=3) as conn:
            conn.execute("SELECT 1")
    except psycopg.Error:
        return JSONResponse({"status": "degraded", "database": "unavailable"}, status_code=503)
    return {"status": "ok", "database": "connected"}
