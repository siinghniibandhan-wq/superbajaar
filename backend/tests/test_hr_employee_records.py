import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.api.hr import EmergencyContactInput, EmploymentHistoryInput
from app.main import app

client = TestClient(app)


def test_emergency_contact_normalises_email_and_trims_values():
    contact = EmergencyContactInput(
        contact_name="  Asha Singh ",
        relationship=" Parent ",
        phone=" +91 98765 43210 ",
        email=" ASHA@EXAMPLE.COM ",
        address="  Ranchi ",
    )
    assert contact.contact_name == "Asha Singh"
    assert contact.relationship == "Parent"
    assert contact.email == "asha@example.com"
    assert contact.address == "Ranchi"


def test_emergency_contact_rejects_invalid_email_and_extra_fields():
    with pytest.raises(ValidationError, match="valid emergency contact email"):
        EmergencyContactInput(
            contact_name="Asha Singh", relationship="Parent",
            phone="9876543210", email="not-an-email",
        )
    with pytest.raises(ValidationError):
        EmergencyContactInput(
            contact_name="Asha Singh", relationship="Parent",
            phone="9876543210", employee_id=999,
        )


def test_employment_history_rejects_reversed_dates():
    with pytest.raises(ValidationError, match="end date cannot precede"):
        EmploymentHistoryInput(
            employer_name="Previous Company", job_title="Associate",
            start_date="2024-06-01", end_date="2024-05-31",
        )


def test_employment_history_rejects_future_start_date():
    with pytest.raises(ValidationError, match="cannot be in the future"):
        EmploymentHistoryInput(
            employer_name="Previous Company", job_title="Associate",
            start_date="2999-01-01",
        )


def test_employment_history_rejects_unknown_employment_type():
    with pytest.raises(ValidationError):
        EmploymentHistoryInput(
            employer_name="Previous Company", job_title="Associate",
            employment_type="permanent", start_date="2024-01-01",
        )


def test_employee_record_routes_require_hr_manager_session(monkeypatch):
    from app.core import config
    monkeypatch.setattr(config.settings, "database_url", "")
    assert client.get("/api/hr/employees/1/emergency-contacts").status_code == 401
    assert client.post("/api/hr/employees/1/emergency-contacts", json={
        "contact_name": "Asha Singh", "relationship": "Parent", "phone": "9876543210"
    }).status_code == 401
    assert client.get("/api/hr/employees/1/employment-history").status_code == 401
    assert client.get("/api/hr/employees/1/record-events").status_code == 401
    assert client.post("/api/hr/employees/1/emergency-contacts/1/deactivate", json={}).status_code == 401
    assert client.post("/api/hr/employees/1/employment-history", json={
        "employer_name": "Previous Company", "job_title": "Associate",
        "start_date": "2024-01-01"
    }).status_code == 401
