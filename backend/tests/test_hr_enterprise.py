from datetime import date
from decimal import Decimal

import pytest
from fastapi import HTTPException

from app.api.hr_enterprise import (
    DOMAINS, REQUIRED, STATUSES, TRANSITIONS,
    _employee_transition_allowed, _initial_status, _validate, _ensure_offer_unexpired, _allowed_record_transitions,
    _ensure_goal_weight_limit, _ensure_assessment_attempt_limit, _calculate_asset_book_value, _ensure_performance_review_subject, _employee_loan_voucher_lines,
)


@pytest.mark.parametrize("domain", sorted(DOMAINS))
def test_every_enterprise_hr_domain_has_record_types_and_workflow_states(domain):
    assert REQUIRED[domain]
    assert STATUSES[domain]
    assert TRANSITIONS[domain]


def test_recruitment_candidate_email_is_normalised():
    result = _validate("recruitment", "candidate", {"first_name":"Candidate","email":"  CANDIDATE@EXAMPLE.COM "})
    assert result["email"] == "candidate@example.com"


def test_recruitment_candidate_rejects_invalid_email():
    with pytest.raises(HTTPException) as exc:
        _validate("recruitment", "candidate", {"first_name":"Candidate","email":"not-an-email"})
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


@pytest.mark.parametrize("existing,requested,limit", [
    ("0","100","100"),
    ("25","75","100"),
])
def test_travel_budget_guard_accepts_within_limit(existing, requested, limit):
    from app.api.hr_enterprise import _ensure_travel_amount_budget
    _ensure_travel_amount_budget(existing, requested, limit, "bookings")


@pytest.mark.parametrize("existing,requested,limit", [
    ("0","101","100"),
    ("60","50","100"),
])
def test_travel_budget_guard_rejects_over_limit(existing, requested, limit):
    from app.api.hr_enterprise import _ensure_travel_amount_budget
    with pytest.raises(HTTPException) as exc:
        _ensure_travel_amount_budget(existing, requested, limit, "bookings")
    assert exc.value.status_code == 422


def test_recruitment_rejects_duplicate_candidate_and_active_application():
    from app.api.hr_enterprise import _ensure_no_active_recruitment_duplicate
    _ensure_no_active_recruitment_duplicate(None, "duplicate")
    with pytest.raises(HTTPException) as exc:
        _ensure_no_active_recruitment_duplicate({"id": 12}, "A candidate with this email already exists")
    assert exc.value.status_code == 409
    assert "candidate" in exc.value.detail.lower()


def test_recruitment_duplicate_guard_reports_existing_application():
    from app.api.hr_enterprise import _ensure_no_active_recruitment_duplicate
    with pytest.raises(HTTPException) as exc:
        _ensure_no_active_recruitment_duplicate({"id": 28}, "This candidate already has an active application")
    assert exc.value.status_code == 409
    assert "application" in exc.value.detail.lower()


def test_recruitment_job_can_close_when_headcount_is_filled():
    assert "closed" in STATUSES["recruitment"]
    assert "closed" in TRANSITIONS["recruitment"]["open"]


def test_recruitment_candidate_requires_first_name():
    with pytest.raises(HTTPException) as exc:
        _validate("recruitment", "candidate", {"email":"candidate@example.com"})
    assert exc.value.status_code == 422
    assert "first name" in exc.value.detail.lower()


@pytest.mark.parametrize("filled,capacity", [(0,1),(1,3),(2,3)])
def test_recruitment_job_cannot_close_before_headcount_is_filled(filled,capacity):
    from app.api.hr_enterprise import _ensure_job_opening_closable
    with pytest.raises(HTTPException) as exc:
        _ensure_job_opening_closable(filled,capacity)
    assert exc.value.status_code == 409


def test_recruitment_job_can_close_at_approved_headcount():
    from app.api.hr_enterprise import _ensure_job_opening_closable
    _ensure_job_opening_closable(3,3)


def test_recruitment_email_requires_smtp_configuration(monkeypatch):
    from app.services.hr_candidate_email import CandidateEmailConfigurationError, send_candidate_email
    for key in ("SB_HR_SMTP_HOST","SB_HR_SMTP_FROM","SB_HR_SMTP_USERNAME","SB_HR_SMTP_PASSWORD"):
        monkeypatch.delenv(key, raising=False)
    with pytest.raises(CandidateEmailConfigurationError) as exc:
        send_candidate_email(recipient="candidate@example.com",subject="Interview",body="Your interview is confirmed.")
    assert "SB_HR_SMTP_HOST" in str(exc.value)
    assert "SB_HR_SMTP_PASSWORD" in str(exc.value)


def test_recruitment_email_uses_authenticated_starttls_smtp(monkeypatch):
    import app.services.hr_candidate_email as mailer
    sent=[]
    class FakeSMTP:
        def __init__(self,host,port,timeout): sent.append(("connect",host,port,timeout))
        def __enter__(self): return self
        def __exit__(self,*args): return False
        def ehlo(self): sent.append(("ehlo",))
        def starttls(self): sent.append(("starttls",))
        def login(self,user,password): sent.append(("login",user,password))
        def send_message(self,message): sent.append(("send",message["To"],message["Subject"]))
    monkeypatch.setenv("SB_HR_SMTP_HOST","smtp.example.com")
    monkeypatch.setenv("SB_HR_SMTP_PORT","587")
    monkeypatch.setenv("SB_HR_SMTP_FROM","hr@example.com")
    monkeypatch.setenv("SB_HR_SMTP_USERNAME","hr@example.com")
    monkeypatch.setenv("SB_HR_SMTP_PASSWORD","test-secret")
    monkeypatch.setattr(mailer.smtplib,"SMTP",FakeSMTP)
    mailer.send_candidate_email(recipient="candidate@example.com",subject=" Interview ",body="Details")
    assert ("starttls",) in sent
    assert ("login","hr@example.com","test-secret") in sent
    assert ("send","candidate@example.com","Interview") in sent

@pytest.mark.parametrize("email", [
    "candidate", "candidate@", "@example.com", "candidate@example",
    "candidate name@example.com", "candidate@example.com extra",
])
def test_recruitment_candidate_rejects_malformed_email_addresses(email):
    with pytest.raises(HTTPException) as exc:
        _validate("recruitment", "candidate", {"first_name":"Candidate","email":email})
    assert exc.value.status_code == 422


def test_recruitment_candidate_trims_names_and_phone():
    result = _validate("recruitment", "candidate", {
        "first_name":"  Asha ", "last_name":" Singh  ",
        "email":" ASHA@EXAMPLE.COM ", "phone":" +91 98765 43210 ",
        "source":" Referral "
    })
    assert result["first_name"] == "Asha"
    assert result["last_name"] == "Singh"
    assert result["email"] == "asha@example.com"
    assert result["phone"] == "+91 98765 43210"
    assert result["source"] == "Referral"


def test_recruitment_job_rejects_unknown_employment_type_and_fractional_headcount():
    with pytest.raises(HTTPException) as employment_error:
        _validate("recruitment", "job_opening", {
            "department":"Operations", "employment_type":"unknown",
            "location":"Patna", "headcount":2
        })
    assert employment_error.value.status_code == 422
    with pytest.raises(HTTPException) as headcount_error:
        _validate("recruitment", "job_opening", {
            "department":"Operations", "employment_type":"full_time",
            "location":"Patna", "headcount":1.5
        })
    assert headcount_error.value.status_code == 422


def test_recruitment_interview_requires_valid_datetime_and_normalises_it():
    result = _validate("recruitment", "interview", {
        "application_id":"12", "interviewer_employee_id":"7",
        "scheduled_at":"2026-12-03T10:30", "interview_type":"  Technical "
    })
    assert result["application_id"] == 12
    assert result["interviewer_employee_id"] == 7
    assert result["scheduled_at"] == "2026-12-03T10:30:00"
    assert result["interview_type"] == "Technical"
    with pytest.raises(HTTPException):
        _validate("recruitment", "interview", {
            "application_id":12, "interviewer_employee_id":7,
            "scheduled_at":"not-a-date", "interview_type":"Technical"
        })


def test_recruitment_offer_rejects_non_iso_currency_and_past_expiry():
    with pytest.raises(HTTPException) as currency_error:
        _validate("recruitment", "offer", {
            "application_id":15, "offered_salary":"45000",
            "currency":"INR1", "expires_on":"2026-12-31"
        })
    assert currency_error.value.status_code == 422
    with pytest.raises(HTTPException) as expiry_error:
        _validate("recruitment", "offer", {
            "application_id":15, "offered_salary":"45000",
            "currency":"INR", "expires_on":"2026-01-01"
        })
    assert expiry_error.value.status_code == 422

def test_recruitment_application_starts_in_screening_and_can_progress():
    assert _initial_status("recruitment", "application") == "screening"
    assert "shortlisted" in TRANSITIONS["recruitment"]["screening"]
    assert "interview" in TRANSITIONS["recruitment"]["shortlisted"]
    assert "offered" in TRANSITIONS["recruitment"]["interview"]


def test_recruitment_hire_rejects_expired_or_invalid_offer():
    _ensure_offer_unexpired("2026-12-31", today=date(2026,12,1))
    with pytest.raises(HTTPException) as expired:
        _ensure_offer_unexpired("2026-11-30", today=date(2026,12,1))
    assert expired.value.status_code == 409
    with pytest.raises(HTTPException) as malformed:
        _ensure_offer_unexpired("not-a-date", today=date(2026,12,1))
    assert malformed.value.status_code == 409

def test_recruitment_record_types_have_distinct_transition_permissions():
    assert _allowed_record_transitions("recruitment","job_opening","open") == {"closed","archived"}
    assert _allowed_record_transitions("recruitment","candidate","draft") == {"withdrawn","archived"}
    assert _allowed_record_transitions("recruitment","application","screening") == {"shortlisted","rejected","withdrawn"}
    assert _allowed_record_transitions("recruitment","interview","interview") == {"completed"}
    assert _allowed_record_transitions("recruitment","offer","offered") == {"rejected","withdrawn"}
    assert _allowed_record_transitions("recruitment","communication","completed") == set()
    assert _allowed_record_transitions("recruitment","job_opening","open") != TRANSITIONS["recruitment"]["open"]


@pytest.mark.parametrize(("domain","record_type","status","expected"), [
    ("documents","employee_document","pending",{"under_review","archived"}),
    ("documents","employee_document","verified",{"expired","archived"}),
    ("performance","review_cycle","self_review",{"manager_review"}),
    ("performance","review_template","draft",{"active","cancelled"}),
    ("learning","course","planned",{"enrolled","cancelled"}),
    ("learning","certificate","completed",{"expired","archived"}),
    ("assets","allocation","requested",{"approved","rejected"}),
    ("assets","asset","available",{"assigned","maintenance","written_off"}),
    ("travel","request","submitted",{"approved","rejected"}),
    ("travel","booking","booked",set()),
    ("exit","case","handover",{"clearance"}),
    ("exit","settlement","settlement_review",{"completed"}),
])
def test_non_recruitment_workflow_transitions_are_record_specific(domain,record_type,status,expected):
    assert _allowed_record_transitions(domain,record_type,status)==expected


def test_non_recruitment_records_cannot_use_another_record_types_transitions():
    assert _allowed_record_transitions("learning","certificate","completed") != TRANSITIONS["learning"].get("completed",set())
    assert _allowed_record_transitions("travel","booking","booked")==set()
    assert _allowed_record_transitions("assets","asset","available") != _allowed_record_transitions("assets","allocation","requested")

def test_travel_reimbursement_requires_claim_record_and_not_request_record():
    assert _allowed_record_transitions("travel","claim","claimed")=={"reimbursed"}
    assert _allowed_record_transitions("travel","request","claimed")==set()

def test_performance_goal_weights_cannot_exceed_cycle_total():
    _ensure_goal_weight_limit("65", "35")
    with pytest.raises(HTTPException) as exc:
        _ensure_goal_weight_limit("80", "25")
    assert exc.value.status_code == 422


@pytest.mark.parametrize("attempts,maximum", [(0,1),(2,3),(4,5)])
def test_learning_assessment_attempt_limit_allows_remaining_attempts(attempts,maximum):
    _ensure_assessment_attempt_limit(attempts,maximum)


def test_learning_assessment_attempt_limit_blocks_exhausted_or_invalid_limits():
    with pytest.raises(HTTPException) as exc:
        _ensure_assessment_attempt_limit(3,3)
    assert exc.value.status_code == 409
    with pytest.raises(HTTPException):
        _ensure_assessment_attempt_limit(0,0)
    with pytest.raises(HTTPException):
        _ensure_assessment_attempt_limit(0,21)

@pytest.mark.parametrize("record_type,expected", [
    ("procurement","requested"),
    ("stock_receipt","received"),
    ("asset_loss","investigating"),
])
def test_asset_supply_chain_records_have_initial_lifecycle_states(record_type,expected):
    assert _initial_status("assets",record_type)==expected


def test_asset_procurement_requires_valid_line_items_and_positive_total():
    result=_validate("assets","procurement",{
        "vendor":"Vendor A","requested_by":"Facilities","estimated_total":"2500",
        "items":[{"description":"Laptop","quantity":"2","unit_cost":"1250"}]
    })
    assert result["estimated_total"]=="2500"
    with pytest.raises(HTTPException):
        _validate("assets","procurement",{
            "vendor":"Vendor A","requested_by":"Facilities","estimated_total":"0",
            "items":[{"description":"Laptop","quantity":"2","unit_cost":"0"}]
        })


def test_asset_stock_reconciliation_requires_reason_for_variance():
    result=_validate("assets","stock_reconciliation",{
        "location":"Warehouse A","counted_at":"2026-11-28",
        "expected_count":"10","physical_count":"8","variance_reason":"Two units not located"
    })
    assert result["variance"]==-2
    with pytest.raises(HTTPException):
        _validate("assets","stock_reconciliation",{
            "location":"Warehouse A","counted_at":"2026-11-28",
            "expected_count":"10","physical_count":"8","variance_reason":"No"
        })

def test_asset_straight_line_depreciation_respects_salvage_floor():
    result=_calculate_asset_book_value("12000","2000",60,"2024-01-01","2026-01-01","straight_line")
    assert result["elapsed_months"]==24
    assert result["accumulated_depreciation"]=="4000.00"
    assert result["book_value"]=="8000.00"


def test_asset_reducing_balance_depreciation_and_invalid_inputs():
    result=_calculate_asset_book_value("10000","1000",60,"2024-01-01","2026-01-01","reducing_balance","20")
    assert result["book_value"]=="6400.00"
    with pytest.raises(HTTPException):
        _calculate_asset_book_value("10000","11000",60,"2024-01-01","2026-01-01")

def test_travel_policy_normalises_and_stores_job_grade():
    result=_validate("travel","travel_policy",{
        "name":"Manager travel","employment_type":"full_time","job_grade":"M2",
        "max_trip_cost":"50000","per_diem_limit":"3000","currency":"inr"
    })
    assert result["job_grade"]=="M2"
    assert result["currency"]=="INR"


def test_travel_policy_defaults_job_grade_to_all():
    result=_validate("travel","travel_policy",{
        "name":"General travel","employment_type":"all",
        "max_trip_cost":"50000","per_diem_limit":"3000","currency":"INR"
    })
    assert result["job_grade"]=="all"

def test_performance_cycle_activation_requires_complete_weighted_goals():
    _ensure_goal_weight_limit("100","0")
    with pytest.raises(HTTPException):
        _ensure_goal_weight_limit("100","1")

def test_analytics_report_validates_schedule_and_filters():
    result=_validate("analytics","report",{
        "report_type":"enterprise","frequency":"monthly",
        "filters":{"domain":"assets","department_id":"4","status":"requested"}
    })
    assert result["frequency"]=="monthly"
    assert result["filters"]["department_id"]==4
    assert result["delivery_channel"]=="workspace_snapshot"
    with pytest.raises(HTTPException):
        _validate("analytics","report",{
            "report_type":"enterprise","frequency":"yearly","filters":{}
        })

def test_exit_settlement_component_breakdowns_must_reconcile():
    result=_validate("exit","settlement",{
        "exit_record_id":7,"gross_due":"60000","deductions":"5000","net_due":"55000","payable_on":"2027-01-05",
        "earnings_breakdown":[{"type":"final_salary","amount":"45000"},{"type":"leave_encashment","amount":"15000"}],
        "deductions_breakdown":[{"type":"loan_recovery","amount":"5000"}]
    })
    assert len(result["earnings_breakdown"])==2
    assert result["deductions_breakdown"][0]["amount"]=="5000"
    with pytest.raises(HTTPException):
        _validate("exit","settlement",{
            "exit_record_id":7,"gross_due":"60000","deductions":"5000","net_due":"55000","payable_on":"2027-01-05",
            "earnings_breakdown":[{"type":"final_salary","amount":"40000"}]
        })

from app.services.hr_exit_settlement import calculate_exit_settlement, validate_exit_policy


def test_exit_policy_requires_explicit_jurisdiction_rules():
    with pytest.raises(HTTPException):
        validate_exit_policy({"daily_wage_basis":"basic"})
    config=validate_exit_policy({
        "daily_wage_basis":"basic","working_days_divisor":"26",
        "gratuity":{"enabled":True,"minimum_service_years":"5","days_per_service_year":"15","divisor":"26"},
        "leave_encashment":{"enabled":True,"divisor":"26"},
        "notice_pay":{"enabled":True,"treatment":"deduction"},
        "statutory_deductions":[{"name":"policy_tax","basis":"gross","rate_percent":"10"}]
    })
    assert config["daily_wage_basis"]=="basic"


def test_exit_settlement_calculates_policy_earnings_leave_and_loan_deductions():
    result=calculate_exit_settlement(
        config={
            "daily_wage_basis":"basic","working_days_divisor":"26",
            "gratuity":{"enabled":True,"minimum_service_years":"5","days_per_service_year":"15","divisor":"26"},
            "leave_encashment":{"enabled":True,"divisor":"26","leave_types":["earned"]},
            "notice_pay":{"enabled":True,"treatment":"deduction"},
            "statutory_deductions":[{"name":"policy_tax","basis":"gross","rate_percent":"5"}]
        },
        monthly_basic="26000",monthly_gross="40000",service_years="6",
        leave_balances={"earned":"10","sick":"5"},
        loan_balances=[{"id":3,"loan_reference":"LN-3","outstanding_amount":"2000"}],
        notice_days_unserved=2
    )
    assert result["gross_due"]=="100000.00"
    assert result["deductions"]=="9000.00"
    assert result["net_due"]=="91000.00"
    assert any(x["type"]=="employee_loan_recovery" for x in result["deductions_breakdown"])


def test_travel_advance_requires_approval_before_disbursement():
    assert _allowed_record_transitions("travel","advance","requested")=={"approved","rejected"}
    assert _allowed_record_transitions("travel","advance","approved")=={"disbursed"}

from app.services.hr_travel_integrations import create_provider_booking, TravelIntegrationConfigurationError


def test_travel_booking_requires_stable_idempotency_reference():
    with pytest.raises(HTTPException):
        _validate("travel","booking",{"travel_record_id":5,"booked_cost":"1000"})
    result=_validate("travel","booking",{
        "travel_record_id":5,"booked_cost":"1000","client_reference":"hr-trip-2026-0001",
        "booking_details":"{}"
    })
    assert result["client_reference"]=="hr-trip-2026-0001"
    assert result["booking_details"]=={}
    assert result["booked_cost"]=="1000"

    with pytest.raises(HTTPException):
        _validate("travel","booking",{
            "travel_record_id":5,"booked_cost":"1000","client_reference":"hr-trip-2026-0002",
            "booking_details":"not-json"
        })
    with pytest.raises(HTTPException):
        _validate("travel","booking",{
            "travel_record_id":5,"booked_cost":"1000","client_reference":"hr-trip-2026-0003",
            "booking_details":"[]"
        })
    with pytest.raises(HTTPException):
        _validate("travel","booking",{
            "travel_record_id":5,"booked_cost":"0","client_reference":"hr-trip-2026-0004",
            "booking_details":"{}"
        })


def test_travel_provider_fails_closed_without_secrets(monkeypatch):
    for key in ("SB_TRAVEL_BOOKING_API_URL","SB_TRAVEL_BOOKING_API_TOKEN","SB_TRAVEL_BOOKING_PROVIDER"):
        monkeypatch.delenv(key,raising=False)
    with pytest.raises(TravelIntegrationConfigurationError):
        create_provider_booking(travel={"destination":"Patna"},booking={"booked_cost":"1000","client_reference":"hr-trip-2026-0001"},record_id=99)


def test_travel_booking_provider_must_confirm_and_stay_within_policy(monkeypatch):
    import app.services.hr_travel_integrations as travel
    class FakeResponse:
        def raise_for_status(self): pass
        def json(self): return {"booking_reference":"BOOK-12345","status":"pending","confirmed_amount":"100"}
    monkeypatch.setenv("SB_TRAVEL_BOOKING_API_URL","https://provider.example.test")
    monkeypatch.setenv("SB_TRAVEL_BOOKING_API_TOKEN","test-token")
    monkeypatch.setenv("SB_TRAVEL_BOOKING_PROVIDER","test-provider")
    monkeypatch.setattr(travel.httpx,"post",lambda *args,**kwargs:FakeResponse())
    with pytest.raises(HTTPException,match="has not confirmed"):
        travel.create_provider_booking(
            travel={"destination":"Delhi","employee_id":7},
            booking={"client_reference":"HR-TRAVEL-123","booked_cost":"100","maximum_allowed_amount":"500"},
            record_id=9,
        )


def test_travel_booking_provider_rejects_confirmed_amount_above_policy(monkeypatch):
    import app.services.hr_travel_integrations as travel
    class FakeResponse:
        def raise_for_status(self): pass
        def json(self): return {"booking_reference":"BOOK-12345","status":"confirmed","confirmed_amount":"600"}
    monkeypatch.setenv("SB_TRAVEL_BOOKING_API_URL","https://provider.example.test")
    monkeypatch.setenv("SB_TRAVEL_BOOKING_API_TOKEN","test-token")
    monkeypatch.setenv("SB_TRAVEL_BOOKING_PROVIDER","test-provider")
    monkeypatch.setattr(travel.httpx,"post",lambda *args,**kwargs:FakeResponse())
    with pytest.raises(HTTPException,match="policy ceiling"):
        travel.create_provider_booking(
            travel={"destination":"Delhi","employee_id":7},
            booking={"client_reference":"HR-TRAVEL-123","booked_cost":"100","maximum_allowed_amount":"500"},
            record_id=9,
        )


def test_performance_feedback_and_acknowledgement_are_scoped_to_review_subject():
    assert _ensure_performance_review_subject(7,7) == 7
    assert _ensure_performance_review_subject(None,7) == 7
    with pytest.raises(HTTPException) as exc:
        _ensure_performance_review_subject(8,7)
    assert exc.value.status_code == 403
    with pytest.raises(HTTPException) as exc:
        _ensure_performance_review_subject(7,None)
    assert exc.value.status_code == 409


def test_employee_loan_disbursement_posts_debit_receivable_and_credit_bank():
    lines=_employee_loan_voucher_lines(1150,1010,"2500.00","disbursement")
    assert lines[0]["account_id"]==1150 and lines[0]["debit"]==Decimal("2500.00")
    assert lines[1]["account_id"]==1010 and lines[1]["credit"]==Decimal("2500.00")
    assert sum((line["debit"] for line in lines),Decimal("0"))==sum((line["credit"] for line in lines),Decimal("0"))


def test_employee_loan_repayment_posts_debit_bank_and_credit_receivable():
    lines=_employee_loan_voucher_lines(1150,1010,"500.00","repayment")
    assert lines[0]["account_id"]==1010 and lines[0]["debit"]==Decimal("500.00")
    assert lines[1]["account_id"]==1150 and lines[1]["credit"]==Decimal("500.00")
    assert sum((line["debit"] for line in lines),Decimal("0"))==sum((line["credit"] for line in lines),Decimal("0"))


def test_employee_loan_accounting_rejects_same_account_and_invalid_amount():
    with pytest.raises(HTTPException):
        _employee_loan_voucher_lines(1150,1150,"500","disbursement")
    with pytest.raises(HTTPException):
        _employee_loan_voucher_lines(1150,1010,"0","repayment")
