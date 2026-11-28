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
            "estimated_cost":"5000", "estimated_per_diem":"1000", "policy_id":1
        })
    assert exc.value.status_code == 422


def test_travel_request_rejects_non_positive_cost():
    with pytest.raises(HTTPException) as exc:
        _validate("travel", "request", {
            "destination":"Delhi", "purpose":"Supplier visit",
            "start_date":"2026-12-09", "end_date":"2026-12-10",
            "estimated_cost":"0", "estimated_per_diem":"1000", "policy_id":1
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
        "cycle_id":12, "summary":"Strong delivery",
        "rating":"4", "achievements":"Completed core goals",
        "development_areas":"Improve delegation"
    })
    assert result["rating"] == "4"
    with pytest.raises(HTTPException):
        _validate("performance", "self_review", {
            "cycle_id":12, "summary":"Strong delivery",
            "rating":"6", "achievements":"Completed core goals",
            "development_areas":"Improve delegation"
        })


def test_asset_custody_acknowledgement_is_an_employee_action():
    assert _employee_transition_allowed("assets", "assigned", "acknowledged")
    assert "acknowledged" in TRANSITIONS["assets"]["assigned"]
    assert "returned" in TRANSITIONS["assets"]["acknowledged"]



def test_performance_review_template_validates_sections_and_scale():
    result = _validate("performance", "review_template", {
        "name":"Annual review",
        "sections":'[{"key":"delivery","weight":60},{"key":"behaviour","weight":40}]',
        "rating_scale":"5"
    })
    assert isinstance(result["sections"], list)
    assert result["rating_scale"] == 5
    with pytest.raises(HTTPException):
        _validate("performance", "review_template", {
            "name":"Broken template", "sections":"{}", "rating_scale":"5"
        })


def test_performance_calibration_and_acknowledgement_are_validated():
    result = _validate("performance", "calibration", {
        "review_id":3, "calibrated_rating":"4.5", "rationale":"Consistent with peer outcomes"
    })
    assert result["calibrated_rating"] == "4.5"
    assert _validate("performance", "acknowledgement", {
        "review_id":3, "acknowledgement":"TRUE"
    })["acknowledgement"] is True
    with pytest.raises(HTTPException):
        _validate("performance", "acknowledgement", {
            "review_id":3, "acknowledgement":"maybe"
        })



def test_manager_review_starts_at_manager_review_stage():
    assert _initial_status("performance", "review") == "manager_review"
    assert _initial_status("performance", "self_review") == "self_review"



def test_learning_progress_evidence_is_bounded():
    result = _validate("learning", "progress", {
        "enrollment_id":5, "progress_percent":"75"
    })
    assert result["progress_percent"] == "75"
    assert _initial_status("learning", "progress") == "in_progress"
    with pytest.raises(HTTPException):
        _validate("learning", "progress", {
            "enrollment_id":5, "progress_percent":"101"
        })



def test_asset_warranty_dates_and_purchase_value_are_validated():
    result = _validate("assets", "asset", {
        "asset_type":"Laptop", "asset_tag":"SB-LAP-100",
        "purchase_value":"65000", "purchase_date":"2026-01-01",
        "warranty_expiry":"2028-01-01"
    })
    assert result["purchase_value"] == "65000"
    with pytest.raises(HTTPException):
        _validate("assets", "asset", {
            "asset_type":"Laptop", "asset_tag":"SB-LAP-101",
            "purchase_value":"65000", "purchase_date":"2026-12-01",
            "warranty_expiry":"2026-11-01"
        })



def test_travel_policy_and_request_amount_fields_are_validated():
    policy = _validate("travel", "travel_policy", {
        "name":"Standard", "employment_type":"all",
        "max_trip_cost":"50000", "per_diem_limit":"3000", "currency":"inr"
    })
    assert policy["currency"] == "INR"
    assert _initial_status("travel", "travel_policy") == "approved"
    request = _validate("travel", "request", {
        "destination":"Delhi", "purpose":"Client visit",
        "start_date":"2026-12-01", "end_date":"2026-12-03",
        "estimated_cost":"20000", "estimated_per_diem":"6000", "policy_id":4
    })
    assert request["policy_id"] == 4
    with pytest.raises(HTTPException):
        _validate("travel", "travel_policy", {
            "name":"Invalid", "employment_type":"all",
            "max_trip_cost":"0", "per_diem_limit":"3000", "currency":"INR"
        })



def test_performance_goal_requires_cycle_and_valid_weight():
    result = _validate("performance", "goal", {
        "cycle_id":8, "description":"Reduce picking errors",
        "measure":"Error rate", "target":"Below 1%", "weight":"25"
    })
    assert result["weight"] == "25"
    with pytest.raises(HTTPException):
        _validate("performance", "goal", {
            "cycle_id":8, "description":"Reduce picking errors",
            "measure":"Error rate", "target":"Below 1%", "weight":"110"
        })



def test_job_opening_requires_positive_headcount():
    result = _validate("recruitment", "job_opening", {
        "department":"Operations", "employment_type":"full_time",
        "location":"Patna", "headcount":"3"
    })
    assert result["headcount"] == 3
    assert result["filled_headcount"] == 0
    with pytest.raises(HTTPException):
        _validate("recruitment", "job_opening", {
            "department":"Operations", "employment_type":"full_time",
            "location":"Patna", "headcount":"0"
        })



def test_recruitment_interview_feedback_and_communication_logs():
    feedback = _validate("recruitment", "interview_feedback", {
        "interview_id":12, "interviewer_employee_id":4,
        "rating":"4", "decision":"pass", "feedback":"Strong operational knowledge"
    })
    assert feedback["rating"] == "4"
    communication = _validate("recruitment", "communication", {
        "candidate_id":9, "channel":"email", "direction":"outbound",
        "subject":"Interview invitation", "message":"Your interview is scheduled.",
        "occurred_at":"2026-12-01T10:30"
    })
    assert communication["occurred_at"] == "2026-12-01T10:30:00"
    with pytest.raises(HTTPException):
        _validate("recruitment", "interview_feedback", {
            "interview_id":12, "interviewer_employee_id":4,
            "rating":"8", "decision":"pass", "feedback":"Out of range"
        })



def test_archive_event_records_the_record_id_and_complete_state(monkeypatch):
    import app.api.hr_enterprise as api
    from contextlib import contextmanager

    old = {"id": 23, "domain": "assets", "status": "available", "version": 1}
    updated = {"id": 23, "domain": "assets", "status": "archived", "version": 2}
    calls = []

    class FakeTransaction:
        def __enter__(self): return self
        def __exit__(self, *_args): return False

    class FakeConnection:
        def transaction(self): return FakeTransaction()
        def execute(self, sql, params=()):
            calls.append((sql, params))
            if sql.startswith("SELECT * FROM hr_enterprise_records"):
                return type("Result", (), {"fetchone": lambda self: old})()
            if sql.startswith("UPDATE hr_enterprise_records"):
                return type("Result", (), {"fetchone": lambda self: updated})()
            return type("Result", (), {"fetchone": lambda self: None})()

    @contextmanager
    def fake_connection():
        yield FakeConnection()

    monkeypatch.setattr(api, "_manager", lambda _request: 7)
    monkeypatch.setattr(api, "_hr_connection", fake_connection)
    result = api.archive_record("assets", 23, object())
    event_sql, event_params = calls[-1]
    assert result == updated
    assert "VALUES(%s,'archived',%s,'archived',%s::jsonb,%s::jsonb,%s)" in event_sql
    assert event_params[0] == 23
    assert event_params[1] == "available"
    assert event_params[2] == '{"id": 23, "domain": "assets", "status": "available", "version": 1}'
    assert event_params[3] == '{"id": 23, "domain": "assets", "status": "archived", "version": 2}'
    assert event_params[4] == 7


@pytest.mark.parametrize("status", ["draft", "approved", "booked", "in_progress", "claimed", "reimbursed"])
def test_travel_claim_rejects_non_completed_status(status):
    from app.api.hr_enterprise import _ensure_travel_claimable
    with pytest.raises(HTTPException) as exc:
        _ensure_travel_claimable(status)
    assert exc.value.status_code == 409


def test_travel_claim_accepts_completed_status():
    from app.api.hr_enterprise import _ensure_travel_claimable
    _ensure_travel_claimable("completed")


@pytest.mark.parametrize("status,active", [
    ("available", False),
    ("approved", False),
    ("available", True),
    ("assigned", False),
    ("maintenance", False),
    ("written_off", False),
])
def test_asset_allocation_guard(status, active):
    from app.api.hr_enterprise import _ensure_asset_allocatable
    if status in {"available", "approved"} and not active:
        _ensure_asset_allocatable(status, active)
    else:
        with pytest.raises(HTTPException) as exc:
            _ensure_asset_allocatable(status, active)
        assert exc.value.status_code == 409


@pytest.mark.parametrize("status", ["draft", "screening", "shortlisted", "interview", "offered", "rejected", "withdrawn"])
def test_candidate_hireable_until_hired(status):
    from app.api.hr_enterprise import _ensure_candidate_hireable
    _ensure_candidate_hireable(status)


def test_candidate_cannot_be_hired_twice():
    from app.api.hr_enterprise import _ensure_candidate_hireable
    with pytest.raises(HTTPException) as exc:
        _ensure_candidate_hireable("hired")
    assert exc.value.status_code == 409
