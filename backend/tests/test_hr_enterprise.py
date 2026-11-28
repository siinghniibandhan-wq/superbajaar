import pytest
from fastapi import HTTPException

from app.api.hr_enterprise import (
    DOMAINS, EMPLOYEE_TRANSITIONS, REQUIRED, STATUSES, TRANSITIONS,
    _employee_transition_allowed, _validate,
)


@pytest.mark.parametrize("domain", sorted(DOMAINS))
def test_every_enterprise_hr_domain_has_record_types_and_workflow_states(domain):
    assert REQUIRED[domain]
    assert STATUSES[domain]
    assert TRANSITIONS[domain]


def test_recruitment_candidate_email_is_normalised():
    result = _validate("recruitment", "candidate", {"email":"  CANDIDATE@EXAMPLE.COM "})
    assert result["email"] == "candidate@example.com"


def test_recruitment_candidate_rejects_invalid_email():
    with pytest.raises(HTTPException) as exc:
        _validate("recruitment", "candidate", {"email":"not-an-email"})
    assert exc.value.status_code == 422


def test_travel_request_rejects_reversed_dates():
    with pytest.raises(HTTPException) as exc:
        _validate("travel", "request", {
            "destination":"Delhi", "purpose":"Supplier visit",
            "start_date":"2026-12-10", "end_date":"2026-12-09",
            "estimated_cost":"5000"
        })
    assert exc.value.status_code == 422


def test_travel_request_rejects_non_positive_cost():
    with pytest.raises(HTTPException) as exc:
        _validate("travel", "request", {
            "destination":"Delhi", "purpose":"Supplier visit",
            "start_date":"2026-12-09", "end_date":"2026-12-10",
            "estimated_cost":"0"
        })
    assert exc.value.status_code == 422


def test_employee_document_requires_checksum_and_safe_mime_type():
    with pytest.raises(HTTPException):
        _validate("documents", "employee_document", {
            "document_type":"identity", "file_name":"id.pdf",
            "object_key":"employee-docs/1/id.pdf",
            "content_type":"application/pdf", "sha256":"invalid"
        })
    with pytest.raises(HTTPException):
        _validate("documents", "employee_document", {
            "document_type":"identity", "file_name":"id.exe",
            "object_key":"employee-docs/1/id.exe",
            "content_type":"application/x-msdownload", "sha256":"a"*64
        })


def test_domain_transition_graph_rejects_skipped_approval_stages():
    assert "hired" not in TRANSITIONS["recruitment"]["open"]
    assert "completed" not in TRANSITIONS["travel"]["submitted"]
    assert "completed" not in TRANSITIONS["exit"]["clearance"]


def test_unknown_record_type_is_rejected():
    with pytest.raises(HTTPException) as exc:
        _validate("assets", "unknown", {})
    assert exc.value.status_code == 422



def test_employee_can_submit_own_travel_and_withdraw_exit():
    assert _employee_transition_allowed("travel", "draft", "submitted")
    assert _employee_transition_allowed("exit", "initiated", "withdrawn")


def test_employee_can_submit_self_review_and_update_learning_progress():
    assert _employee_transition_allowed("performance", "active", "self_review")
    assert _employee_transition_allowed("learning", "enrolled", "in_progress")
    assert _employee_transition_allowed("learning", "in_progress", "completed")


def test_employee_cannot_approve_or_complete_manager_workflows():
    assert not _employee_transition_allowed("travel", "submitted", "approved")
    assert not _employee_transition_allowed("assets", "requested", "approved")
    assert not _employee_transition_allowed("documents", "under_review", "verified")
    assert not _employee_transition_allowed("recruitment", "offered", "hired")
