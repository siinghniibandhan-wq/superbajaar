from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_root_reports_running_and_configured_port():
    response = client.get("/")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "running"
    assert body["port"] == 8001


def test_versioned_health_endpoint():
    response = client.get("/api/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
