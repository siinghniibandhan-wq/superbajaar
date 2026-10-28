from unittest.mock import MagicMock, patch

import psycopg
from fastapi.testclient import TestClient

import app.api.health as health_module
from app.main import app

client = TestClient(app)


def _mock_connection(table_names=("orders", "loyalty_rules", "schema_migrations")):
    conn = MagicMock()
    conn.__enter__.return_value = conn
    conn.execute.return_value.fetchall.return_value = [(name,) for name in table_names]
    return conn


def test_root_reports_running_and_configured_port():
    response = client.get("/")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "running"
    assert body["port"] == 8001


def test_api_health_reports_connected_when_required_tables_exist():
    with patch.object(health_module.settings, "database_url", "postgresql://test"), \
         patch.object(health_module.psycopg, "connect", return_value=_mock_connection()):
        response = client.get("/api/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "database": "connected"}


def test_api_health_is_degraded_when_required_table_is_missing():
    with patch.object(health_module.settings, "database_url", "postgresql://test"), \
         patch.object(health_module.psycopg, "connect", return_value=_mock_connection(("orders",))):
        response = client.get("/api/health")
    assert response.status_code == 503
    assert response.json() == {"status": "degraded", "database": "unavailable"}


def test_api_health_returns_safe_503_when_database_unavailable():
    with patch.object(health_module.settings, "database_url", "postgresql://secret-password@host/db"), \
         patch.object(health_module.psycopg, "connect", side_effect=psycopg.OperationalError("sensitive exception detail")):
        response = client.get("/api/health")
    assert response.status_code == 503
    assert response.json() == {"status": "degraded", "database": "unavailable"}
    assert "secret-password" not in response.text
    assert "sensitive exception detail" not in response.text
