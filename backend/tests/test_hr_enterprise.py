import pytest
from fastapi import HTTPException

from app.api.hr_enterprise import (
    DOMAINS, REQUIRED, STATUSES, TRANSITIONS,
    _employee_transition_allowed, _initial_status, _validate,
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



def test_typed_workflows_start_in_their_business_state():
    assert _initial_status("recruitment", "interview") == "interview"
    assert _initial_status("recruitment", "offer") == "offered"
    assert _initial_status("travel", "booking") == "booked"
    assert _initial_status("travel", "claim") == "claimed"
    assert _initial_status("exit", "clearance") == "clearance"
    assert _initial_status("assets", "maintenance") == "maintenance"


def test_recruitment_offer_requires_positive_salary_and_valid_currency():
    result = _validate("recruitment", "offer", {
        "application_id": 15, "offered_salary": "45000",
        "currency": "inr", "expires_on": "2026-12-31"
    })
    assert result["offered_salary"] == "45000"
    assert result["currency"] == "INR"
    with pytest.raises(HTTPException):
        _validate("recruitment", "offer", {
            "application_id": 15, "offered_salary": "0",
            "currency": "INR", "expires_on": "2026-12-31"
        })


def test_exit_settlement_must_reconcile_to_net_due():
    result = _validate("exit", "settlement", {
        "exit_record_id": 7, "gross_due": "60000",
        "deductions": "5000", "net_due": "55000", "payable_on": "2027-01-05"
    })
    assert result["net_due"] == "55000"
    with pytest.raises(HTTPException):
        _validate("exit", "settlement", {
            "exit_record_id": 7, "gross_due": "60000",
            "deductions": "5000", "net_due": "57000", "payable_on": "2027-01-05"
        })


def test_learning_assessment_scores_are_bounded():
    with pytest.raises(HTTPException):
        _validate("learning", "assessment", {
            "enrollment_id": 4, "score": "105", "pass_score": "70"
        })



def test_invalid_exit_and_asset_dates_return_validation_errors():
    with pytest.raises(HTTPException) as exit_error:
        _validate("exit", "case", {"reason":"Personal reasons","last_working_date":"not-a-date"})
    assert exit_error.value.status_code == 422
    with pytest.raises(HTTPException) as asset_error:
        _validate("assets", "asset_request", {
            "asset_type":"Laptop", "purpose":"New starter equipment", "needed_by":"not-a-date"
        })
    assert asset_error.value.status_code == 422


def test_new_record_types_are_registered_for_each_domain():
    assert "interview" in REQUIRED["recruitment"]
    assert "offer" in REQUIRED["recruitment"]
    assert "review_cycle" in REQUIRED["performance"]
    assert "assessment" in REQUIRED["learning"]
    assert "asset_request" in REQUIRED["assets"]
    assert "booking" in REQUIRED["travel"]
    assert "settlement" in REQUIRED["exit"]



def test_employee_self_review_rating_is_bounded():
    result = _validate("performance", "self_review", {
        "cycle":"FY2026", "summary":"Strong delivery",
        "rating":"4", "achievements":"Completed core goals",
        "development_areas":"Improve delegation"
    })
    assert result["rating"] == "4"
    with pytest.raises(HTTPException):
        _validate("performance", "self_review", {
            "cycle":"FY2026", "summary":"Strong delivery",
            "rating":"6", "achievements":"Completed core goals",
            "development_areas":"Improve delegation"
        })


def test_asset_custody_acknowledgement_is_an_employee_action():
    assert _employee_transition_allowed("assets", "assigned", "acknowledged")
    assert "acknowledged" in TRANSITIONS["assets"]["assigned"]
    assert "returned" in TRANSITIONS["assets"]["acknowledged"]
