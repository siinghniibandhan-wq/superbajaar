from fastapi.testclient import TestClient

from app.main import app


client = TestClient(app)


def test_organisation_policy_endpoint_requires_authenticated_staff_actor(monkeypatch):
    from app.core.config import settings

    monkeypatch.setattr(settings, "database_url", "")
    response = client.get("/api/organisation-policies")
    assert response.status_code == 401
    assert response.json()["detail"] == "An authenticated staff session is required"


def test_organisation_policy_configuration_is_not_exposed_without_staff_actor(monkeypatch):
    from app.core.config import settings

    monkeypatch.setattr(settings, "database_url", "")
    response = client.post("/api/organisation-policies", json={
        "establishment_id": 1,
        "domain": "purchase",
        "version_label": "Initial",
        "effective_from": "2026-11-02",
        "policy_config": {},
    })
    assert response.status_code == 401
    assert response.json()["detail"] == "An authenticated staff session is required"
