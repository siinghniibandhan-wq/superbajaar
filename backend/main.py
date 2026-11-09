"""Compatibility entry point for deployments running uvicorn main:app.

The maintained FastAPI application lives in app.main and registers every
module under the public /api prefix (without /v1). Keeping this shim
prevents an older, standalone application in this file from being served by
the existing systemd/Gunicorn command.
"""
from app.main import app

__all__ = ["app"]
