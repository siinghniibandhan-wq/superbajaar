from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_list_rfqs_requires_database_configuration(monkeypatch):
    from app.api import purchasing
    monkeypatch.setattr(purchasing.settings, "database_url", "")
    response = client.get("/api/purchasing/rfqs")
    assert response.status_code == 503
    assert response.json()["detail"] == "Purchasing database is not configured"


def test_list_quotations_requires_database_configuration(monkeypatch):
    from app.api import purchasing
    monkeypatch.setattr(purchasing.settings, "database_url", "")
    response = client.get("/api/purchasing/quotations")
    assert response.status_code == 503
    assert response.json()["detail"] == "Purchasing database is not configured"


def test_list_rfqs_rejects_invalid_status():
    response = client.get("/api/purchasing/rfqs?status=unknown")
    assert response.status_code == 422
