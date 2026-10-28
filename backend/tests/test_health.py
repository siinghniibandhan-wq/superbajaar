from unittest.mock import patch

import psycopg
from fastapi.testclient import TestClient

import app.api.health as health_module
from app.main import app

client = TestClient(app)


def test_root_reports_running_and_configured_port():
    response = client.get("/")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "running"
    assert body["port"] == 8001


def test_api_health_reports_database_connected():
    with patch.object(health_module.settings, "database_url", "postgresql://test"), \
         patch.object(health_module.psycopg, "connect"):
        response = client.get("/api/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "database": "connected"}


def test_api_health_returns_503_when_database_unavailable():
    with patch.object(health_module.settings, "database_url", "postgresql://test"), \
         patch.object(health_module.psycopg, "connect", side_effect=psycopg.OperationalError("down")):
        response = client.get("/api/health")
    assert response.status_code == 503
    assert response.json() == {"status": "degraded", "database": "unavailable"}
