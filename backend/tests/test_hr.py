from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.api.hr import EmployeeInput, LeaveInput, PayrollRunInput, ReviewInput, SalaryRevisionInput, PayrollEarningInput
from app.main import app

client = TestClient(app)


def test_hr_employee_email_is_normalised():
    employee = EmployeeInput(
        employee_code="SB-2001", first_name="Asha", email=" Asha@Example.COM ",
        designation="Store Associate", joining_date="2026-11-01"
    )
    assert employee.email == "asha@example.com"


def test_hr_payroll_rejects_negative_manual_deduction():
    with pytest.raises(ValidationError):
        PayrollRunInput(
            period_start="2026-11-01", period_end="2026-11-30",
            deductions_by_employee={"12": Decimal("-1.00")}
        )


def test_hr_self_service_never_accepts_employee_id_from_client():
    response = client.post("/api/hr/attendance/punch", json={
        "employee_id": 123, "punch_type": "clock_in"
    })
    assert response.status_code == 422


def test_hr_self_service_requires_authenticated_staff_session(monkeypatch):
    from app.core import config
    monkeypatch.setattr(config.settings, "database_url", "")
    response = client.get("/api/hr/attendance/me?month=2026-11")
    assert response.status_code == 401


def test_hr_manager_only_endpoint_requires_authenticated_session(monkeypatch):
    from app.core import config
    monkeypatch.setattr(config.settings, "database_url", "")
    response = client.post("/api/hr/departments", json={
        "code": "OPS", "name": "Operations"
    })
    assert response.status_code == 401


def test_hr_payroll_month_requires_complete_calendar_period():
    with pytest.raises(ValidationError):
        PayrollRunInput(
            period_start="2026-11-02", period_end="2026-11-30"
        )


def test_hr_leave_rejects_end_date_before_start_date():
    with pytest.raises(ValidationError):
        LeaveInput(
            leave_type="annual",
            start_date="2026-11-12",
            end_date="2026-11-11",
            days=1,
            reason="Annual leave",
        )


def test_hr_employee_exit_date_cannot_precede_joining_date():
    with pytest.raises(ValidationError):
        EmployeeInput(
            employee_code="SB-EXIT-1",
            first_name="Asha",
            email="asha.exit@example.com",
            designation="Store Associate",
            joining_date="2026-11-12",
            exit_date="2026-11-11",
        )


def test_hr_rejection_requires_a_review_reason():
    with pytest.raises(ValidationError, match="A reason is required when rejecting a request"):
        ReviewInput(decision="rejected")


def test_hr_approval_can_have_no_review_reason():
    assert ReviewInput(decision="approved").note is None


def test_hr_leave_accrual_period_must_be_ordered():
    from app.api.hr import LeaveAccrualInput
    with pytest.raises(ValidationError, match="Accrual period end must not precede its start"):
        LeaveAccrualInput(period_start="2026-11-30",period_end="2026-11-01")


def test_hr_lifecycle_template_requires_valid_type():
    from app.api.hr import LifecycleTemplateInput
    with pytest.raises(ValidationError):
        LifecycleTemplateInput(name="Onboarding",lifecycle_type="recruitment")


def test_hr_leave_policy_rejects_reversed_effective_period():
    from app.api.hr import LeavePolicyInput
    with pytest.raises(ValidationError,match="Leave policy end date cannot precede its start date"):
        LeavePolicyInput(
            establishment_id=1,leave_type="annual",version_label="Policy",
            effective_from="2026-11-30",effective_to="2026-11-01"
        )


def test_hr_shift_definition_requires_valid_iana_timezone():
    from app.api.hr import ShiftDefinitionInput
    with pytest.raises(ValidationError,match="valid IANA timezone"):
        ShiftDefinitionInput(
            establishment_id=1,code="DAY",name="Day shift",
            local_start_time="09:00",local_end_time="18:00",
            effective_from="2026-01-01",timezone="Mars/Olympus"
        )


def test_hr_shift_assignment_requires_timezone_aware_ordered_timestamps():
    from app.api.hr import ShiftAssignmentInput
    with pytest.raises(ValidationError,match="timezone offset"):
        ShiftAssignmentInput(
            employee_id=1,shift_definition_id=1,work_date="2026-11-01",
            planned_start_at="2026-11-01T09:00:00",
            planned_end_at="2026-11-01T18:00:00"
        )
    with pytest.raises(ValidationError,match="after its start"):
        ShiftAssignmentInput(
            employee_id=1,shift_definition_id=1,work_date="2026-11-01",
            planned_start_at="2026-11-01T18:00:00+05:30",
            planned_end_at="2026-11-01T09:00:00+05:30"
        )


def test_hr_salary_revision_requires_a_reason_and_valid_effective_range():
    with pytest.raises(ValidationError, match="Salary revision reason"):
        SalaryRevisionInput(
            effective_from="2026-12-01", basic_salary=30000, hra=12000,
            special_allowance=5000, other_allowance=1000, reason="  "
        )

    with pytest.raises(ValidationError, match="Salary revision end date"):
        SalaryRevisionInput(
            effective_from="2026-12-01", effective_to="2026-11-30",
            basic_salary=30000, hra=12000, special_allowance=5000,
            other_allowance=1000, reason="Annual revision"
        )


def test_hr_salary_revision_rejects_negative_components():
    with pytest.raises(ValidationError):
        SalaryRevisionInput(
            effective_from="2026-12-01", basic_salary=-1, hra=0,
            special_allowance=0, other_allowance=0, reason="Annual revision"
        )


def test_hr_salary_revisions_follow_full_calendar_month_payroll_periods():
    with pytest.raises(ValidationError, match="first day of a calendar month"):
        SalaryRevisionInput(
            effective_from="2026-12-15", basic_salary=30000, hra=12000,
            special_allowance=5000, other_allowance=1000, reason="Mid-month change"
        )


def test_hr_salary_history_is_manager_only_without_a_session(monkeypatch):
    from app.core import config
    monkeypatch.setattr(config.settings, "database_url", "")
    response = client.get("/api/hr/employees/1/salary-revisions")
    assert response.status_code == 401


def test_hr_overtime_earning_requires_matching_hours_and_rate():
    earning = PayrollEarningInput(
        earning_type="overtime", period_start="2026-12-01", period_end="2026-12-31",
        amount="1500.00", hours="10", hourly_rate="150",
        reason="Approved weekend overtime"
    )
    assert earning.amount == Decimal("1500.00")

    with pytest.raises(ValidationError, match="must equal hours multiplied by hourly rate"):
        PayrollEarningInput(
            earning_type="overtime", period_start="2026-12-01", period_end="2026-12-31",
            amount="1400.00", hours="10", hourly_rate="150",
            reason="Approved weekend overtime"
        )


def test_hr_incentive_earning_requires_a_full_calendar_month():
    with pytest.raises(ValidationError, match="full calendar month"):
        PayrollEarningInput(
            earning_type="incentive", period_start="2026-12-02", period_end="2026-12-31",
            amount="1000.00", reason="Monthly sales incentive"
        )


def test_hr_final_settlement_earning_types_are_supported_with_manual_amounts():
    for earning_type in ("arrears", "leave_encashment", "gratuity", "notice_pay", "final_settlement"):
        earning = PayrollEarningInput(
            earning_type=earning_type, period_start="2026-12-01", period_end="2026-12-31",
            amount="2500.00", reason="Approved final settlement component"
        )
        assert earning.earning_type == earning_type



def test_hr_payroll_rejection_requires_a_reason():
    from app.api.hr import PayrollApprovalInput
    with pytest.raises(ValidationError, match="A reason is required when rejecting payroll"):
        PayrollApprovalInput(decision="rejected")
    assert PayrollApprovalInput(decision="rejected", note="Incorrect payroll totals").note == "Incorrect payroll totals"
