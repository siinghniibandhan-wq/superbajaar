import pytest

from fastapi.testclient import TestClient

from app.main import app
from app.services.hr_overview import month_period

client = TestClient(app)


def test_hr_overview_month_period_covers_complete_calendar_month():
    start, end = month_period("2026-11")
    assert start.isoformat() == "2026-11-01"
    assert end.isoformat() == "2026-12-01"


@pytest.mark.parametrize("value", ["2026-1", "2026-13", "2026-00", "26-11", "2026-11-01", ""])
def test_hr_overview_rejects_invalid_month(value):
    with pytest.raises(ValueError):
        month_period(value)


def test_hr_overview_month_period_handles_leap_february():
    start, end = month_period("2028-02")
    assert start.isoformat() == "2028-02-01"
    assert end.isoformat() == "2028-03-01"


def test_hr_overview_requires_authenticated_manager_session(monkeypatch):
    from app.core import config
    monkeypatch.setattr(config.settings, "database_url", "")
    response = client.get("/api/hr/overview?month=2026-11")
    assert response.status_code == 401


def test_hr_overview_rejects_invalid_month_before_database_access(monkeypatch):
    from app.core import config
    monkeypatch.setattr(config.settings, "database_url", "")
    response = client.get("/api/hr/overview?month=2026-13")
    assert response.status_code == 422
