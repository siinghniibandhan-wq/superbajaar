"""HR, attendance, leave, reimbursements and payroll APIs.

Employee self-service is bound to the authenticated app_users identity. Managers
cannot impersonate employees through request payloads. Statutory deductions are
explicit payroll inputs; this module does not invent PF/ESI/PT/TDS rates.
"""
from calendar import monthrange
from contextlib import contextmanager
from datetime import date, datetime
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
from decimal import Decimal
from typing import Any

import psycopg
from fastapi import APIRouter, HTTPException, Query, Request
from psycopg.rows import dict_row
from pydantic import BaseModel, Field, field_validator, model_validator

from app.core.config import settings
from app.api.accounting import _actor as _accounting_actor, _post_voucher
from app.services.accounting_posting import PostingConfigurationError, build_payroll_accrual_lines
from app.services.hr_overview import month_period, month_trend_period
from app.services.hr_statutory_payroll import (
    StatutoryPolicyError, assess_policy_readiness, calculate_statutory_payroll,
)

router = APIRouter(prefix="/hr", tags=["hr"])


def _connect():
    if not settings.database_url:
        raise HTTPException(503, "HR database is not configured")
    try:
        return psycopg.connect(settings.database_url, row_factory=dict_row, connect_timeout=3)
    except psycopg.Error as exc:
        raise HTTPException(503, "HR database is unavailable") from exc


@contextmanager
def _hr_connection():
    """Keep a missing additive HR migration isolated to the HR feature surface."""
    try:
        with _connect() as conn:
            yield conn
    except psycopg.errors.UndefinedTable as exc:
        raise HTTPException(503, "HR workflow database update is not available yet; retry after the schema release") from exc
    except psycopg.Error as exc:
        raise _db_error(exc) from exc


def _actor(request: Request) -> int:
    user_id = getattr(request.state, "user_id", None)
    if not user_id:
        raise HTTPException(401, "An authenticated staff session is required")
    return int(user_id)


def _manager(request: Request) -> int:
    actor = _actor(request)
    if getattr(request.state, "role", "") not in {"super_admin", "owner", "admin", "manager"}:
        raise HTTPException(403, "HR manager permission is required")
    return actor


def _require_independent_reviewer(submitter_id: int | None, reviewer_id: int, record_name: str) -> None:
    """Prevent the same manager from submitting and approving a financial/control record."""
    if submitter_id is not None and int(submitter_id) == int(reviewer_id):
        raise HTTPException(403, f"A {record_name} must be reviewed by a different authorised user")


def _employee(conn, user_id: int):
    row = conn.execute(
        "SELECT id,employee_code,first_name,last_name,email,department_id,status "
        "FROM hr_employees WHERE user_id=%s AND status<>'terminated'",
        (user_id,),
    ).fetchone()
    if row is None:
        raise HTTPException(404, "No active employee profile is linked to this staff account")
    return row


def _validate_reporting_manager(conn, employee_id: int, manager_id: int | None):
    """Reject self-reporting and cycles in the employee reporting hierarchy."""
    if manager_id is None:
        return
    if employee_id == manager_id:
        raise HTTPException(422, "An employee cannot report to themselves")
    creates_cycle = conn.execute(
        "WITH RECURSIVE descendants(id) AS ("
        " SELECT id FROM hr_employees WHERE id=%s"
        " UNION"
        " SELECT e.id FROM hr_employees e JOIN descendants d "
        " ON e.reports_to_employee_id=d.id"
        ") SELECT EXISTS(SELECT 1 FROM descendants WHERE id=%s) AS creates_cycle",
        (employee_id, manager_id),
    ).fetchone()["creates_cycle"]
    if creates_cycle:
        raise HTTPException(422, "Reporting manager assignment would create a reporting cycle")


def _db_error(exc: psycopg.Error):
    if getattr(exc, "sqlstate", None) == "23505":
        return HTTPException(409, "A record with the same unique value already exists")
    if getattr(exc, "sqlstate", None) == "23503":
        return HTTPException(422, "A referenced employee, department or accounting record does not exist")
    if getattr(exc, "sqlstate", None) == "23514":
        return HTTPException(422, "The request violates an HR data constraint")
    return HTTPException(503, "HR database operation failed")


class DepartmentInput(BaseModel):
    code: str = Field(min_length=2, max_length=32)
    name: str = Field(min_length=2, max_length=128)
    description: str | None = Field(default=None, max_length=1000)

    @field_validator("code", "name")
    @classmethod
    def trim_nonblank(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Value cannot be blank")
        return value


class EmployeeInput(BaseModel):
    user_id: int | None = Field(default=None, gt=0)
    employee_code: str = Field(min_length=2, max_length=32)
    first_name: str = Field(min_length=1, max_length=64)
    last_name: str = Field(default="", max_length=64)
    email: str = Field(min_length=5, max_length=254)
    phone: str = Field(default="", max_length=32)
    department_id: int | None = Field(default=None, gt=0)
    designation: str = Field(min_length=2, max_length=128)
    reports_to_employee_id: int | None = Field(default=None, gt=0)
    employment_type: str = Field(default="full_time", pattern="^(full_time|part_time|contract|intern|shift_worker)$")
    status: str = Field(default="active", pattern="^(active|probation|on_leave|notice_period|terminated)$")
    joining_date: date
    exit_date: date | None = None
    basic_salary: Decimal = Field(default=Decimal("0"), ge=0, max_digits=14, decimal_places=2)
    hra: Decimal = Field(default=Decimal("0"), ge=0, max_digits=14, decimal_places=2)
    special_allowance: Decimal = Field(default=Decimal("0"), ge=0, max_digits=14, decimal_places=2)
    other_allowance: Decimal = Field(default=Decimal("0"), ge=0, max_digits=14, decimal_places=2)

    @field_validator("email")
    @classmethod
    def normalise_email(cls, value: str) -> str:
        value = value.strip().lower()
        if "@" not in value or value.startswith("@") or value.endswith("@"):
            raise ValueError("A valid email address is required")
        return value

    @model_validator(mode="after")
    def ordered_employment_dates(self):
        if self.exit_date and self.exit_date < self.joining_date:
            raise ValueError("Employee exit date cannot precede joining date")
        if self.status == "terminated" and self.exit_date is None:
            raise ValueError("Exit date is required when terminating an employee")
        return self


class AttendanceAdjustmentInput(BaseModel):
    clock_in_at: Any
    clock_out_at: Any | None = None
    reason: str = Field(min_length=5, max_length=500)

    @field_validator("reason")
    @classmethod
    def require_adjustment_reason(cls, value: str) -> str:
        value = value.strip()
        if len(value) < 5:
            raise ValueError("Attendance adjustment reason must contain at least 5 characters")
        return value


class PunchInput(BaseModel):
    model_config = {"extra": "forbid"}
    punch_type: str = Field(pattern="^(clock_in|clock_out)$")
    note: str | None = Field(default=None, max_length=500)
    latitude: float | None = Field(default=None, ge=-90, le=90)
    longitude: float | None = Field(default=None, ge=-180, le=180)
    accuracy_meters: float | None = Field(default=None, gt=0, le=10000)

    @model_validator(mode="after")
    def paired_coordinates(self):
        if (self.latitude is None) != (self.longitude is None):
            raise ValueError("Latitude and longitude must be provided together")
        if self.accuracy_meters is not None and self.latitude is None:
            raise ValueError("Location accuracy requires GPS coordinates")
        return self


class LeaveInput(BaseModel):
    leave_type: str = Field(pattern="^(annual|sick|casual|unpaid|other)$")
    start_date: date
    end_date: date
    days: Decimal = Field(gt=0, max_digits=6, decimal_places=2)
    reason: str = Field(min_length=3, max_length=1000)

    @model_validator(mode="after")
    def ordered_date_range(self):
        if self.end_date < self.start_date:
            raise ValueError("Leave end date cannot precede its start date")
        return self


class ReviewInput(BaseModel):
    decision: str = Field(pattern="^(approved|rejected)$")
    note: str | None = Field(default=None, max_length=1000)

    @model_validator(mode="after")
    def rejection_requires_reason(self):
        if self.decision == "rejected" and not (self.note and self.note.strip()):
            raise ValueError("A reason is required when rejecting a request")
        return self


class ExpenseInput(BaseModel):
    category: str = Field(min_length=2, max_length=64)
    amount: Decimal = Field(gt=0, max_digits=14, decimal_places=2)
    expense_date: date
    description: str = Field(min_length=3, max_length=1000)
    receipt_reference: str | None = Field(default=None, max_length=500)


class PayrollRunInput(BaseModel):
    period_start: date
    period_end: date
    deductions_by_employee: dict[int, Decimal] = Field(default_factory=dict)
    deduction_notes: dict[int, str] = Field(default_factory=dict)
    notes: str | None = Field(default=None, max_length=1000)

    @field_validator("deductions_by_employee")
    @classmethod
    def nonnegative_deductions(cls, value):
        if any(amount < 0 for amount in value.values()):
            raise ValueError("Payroll deductions cannot be negative")
        return value

    @model_validator(mode="after")
    def full_calendar_month(self):
        if self.period_start.day != 1:
            raise ValueError("Payroll period must start on the first day of a month")
        last_day = monthrange(self.period_start.year, self.period_start.month)[1]
        if self.period_end != date(self.period_start.year, self.period_start.month, last_day):
            raise ValueError("Payroll period must cover one complete calendar month")
        for employee_id, amount in self.deductions_by_employee.items():
            if amount > 0:
                reason = self.deduction_notes.get(employee_id)
                if not reason or len(reason.strip()) < 5:
                    raise ValueError("A reason is required for every manual payroll deduction")
        return self


class PayrollApprovalInput(BaseModel):
    decision: str = Field(pattern="^(approved|rejected)$")
    note: str | None = Field(default=None, max_length=1000)

    @model_validator(mode="after")
    def rejection_requires_reason(self):
        if self.decision == "rejected" and not (self.note and self.note.strip()):
            raise ValueError("A reason is required when rejecting payroll")
        return self


class PayrollPaymentInput(BaseModel):
    accounting_voucher_id: int = Field(gt=0)


class SalaryRevisionInput(BaseModel):
    effective_from: date
    effective_to: date | None = None
    basic_salary: Decimal = Field(ge=0, max_digits=14, decimal_places=2)
    hra: Decimal = Field(ge=0, max_digits=14, decimal_places=2)
    special_allowance: Decimal = Field(ge=0, max_digits=14, decimal_places=2)
    other_allowance: Decimal = Field(ge=0, max_digits=14, decimal_places=2)
    reason: str = Field(max_length=500)

    @field_validator("reason")
    @classmethod
    def salary_revision_reason_required(cls, value: str) -> str:
        value = value.strip()
        if len(value) < 5:
            raise ValueError("Salary revision reason must contain at least 5 characters")
        return value

    @model_validator(mode="after")
    def ordered_salary_period(self):
        if self.effective_from.day != 1:
            raise ValueError("Salary revision must start on the first day of a calendar month")
        if self.effective_to:
            last_day = monthrange(self.effective_to.year, self.effective_to.month)[1]
            if self.effective_to < self.effective_from:
                raise ValueError("Salary revision end date cannot precede its effective date")
            if self.effective_to.day != last_day:
                raise ValueError("Salary revision must end on the last day of a calendar month")
        return self



class PayrollEarningInput(BaseModel):
    earning_type: str = Field(pattern="^(overtime|incentive|bonus|arrears|leave_encashment|gratuity|notice_pay|final_settlement)$")
    period_start: date
    period_end: date
    amount: Decimal = Field(gt=0, max_digits=14, decimal_places=2)
    hours: Decimal | None = Field(default=None, gt=0, max_digits=8, decimal_places=2)
    hourly_rate: Decimal | None = Field(default=None, gt=0, max_digits=14, decimal_places=2)
    reason: str = Field(max_length=500)

    @field_validator("reason")
    @classmethod
    def earning_reason_required(cls, value: str) -> str:
        value = value.strip()
        if len(value) < 5:
            raise ValueError("Payroll earning reason must contain at least 5 characters")
        return value

    @model_validator(mode="after")
    def validate_earning_period_and_overtime(self):
        if self.period_start.day != 1:
            raise ValueError("Payroll earning period must cover a full calendar month")
        last_day = monthrange(self.period_start.year, self.period_start.month)[1]
        if self.period_end != date(self.period_start.year,self.period_start.month,last_day):
            raise ValueError("Payroll earning period must cover a full calendar month")
        if self.earning_type == "overtime":
            if self.hours is None or self.hourly_rate is None:
                raise ValueError("Overtime requires both hours and hourly rate")
            expected = (self.hours * self.hourly_rate).quantize(Decimal("0.01"))
            if expected != self.amount:
                raise ValueError("Overtime amount must equal hours multiplied by hourly rate")
        elif self.hours is not None or self.hourly_rate is not None:
            raise ValueError("Hours and hourly rate are only accepted for overtime")
        return self



@router.get("/overview")
def hr_overview(request: Request, month: str = Query(..., pattern=r"^\d{4}-(0[1-9]|1[0-2])$")):
    """Return organisation-wide HR management metrics for one calendar month."""
    _manager(request)
    try:
        period_start, period_end = month_period(month)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc

    try:
        with _hr_connection() as conn:
            workforce = conn.execute(
                "SELECT count(*)::int AS total, "
                "count(*) FILTER (WHERE status IN ('active','probation','on_leave','notice_period'))::int AS active, "
                "count(*) FILTER (WHERE status='terminated')::int AS inactive, "
                "count(*) FILTER (WHERE joining_date >= %s AND joining_date < %s)::int AS joiners, "
                "count(*) FILTER (WHERE exit_date >= %s AND exit_date < %s)::int AS exits "
                "FROM hr_employees",
                (period_start, period_end, period_start, period_end),
            ).fetchone()
            departments = conn.execute(
                "SELECT d.id,d.name,count(e.id) FILTER (WHERE e.status IN "
                "('active','probation','on_leave','notice_period'))::int AS headcount "
                "FROM hr_departments d LEFT JOIN hr_employees e ON e.department_id=d.id "
                "WHERE d.is_active=true GROUP BY d.id,d.name ORDER BY d.name"
            ).fetchall()
            attendance = conn.execute(
                "SELECT count(DISTINCT employee_id)::int AS present, "
                "count(*) FILTER (WHERE clock_out_at IS NULL)::int AS open_sessions "
                "FROM hr_attendance_sessions WHERE clock_in_at >= %s AND clock_in_at < %s",
                (period_start, period_end),
            ).fetchone()
            on_leave = conn.execute(
                "SELECT count(DISTINCT employee_id)::int AS employees "
                "FROM hr_leave_requests WHERE status='approved' "
                "AND start_date < %s AND end_date >= %s",
                (period_end, period_start),
            ).fetchone()["employees"]
            scheduled_attendance = conn.execute(
                "WITH scheduled AS ("
                " SELECT sa.employee_id,sa.work_date,"
                " EXISTS (SELECT 1 FROM hr_attendance_sessions hs "
                "         WHERE hs.employee_id=sa.employee_id "
                "           AND (hs.clock_in_at AT TIME ZONE sd.timezone)::date=sa.work_date) AS attended "
                " FROM hr_shift_assignments sa "
                " JOIN hr_shift_definitions sd ON sd.id=sa.shift_definition_id "
                " WHERE sa.status='published' AND sa.work_date >= %s AND sa.work_date < %s "
                "   AND NOT EXISTS (SELECT 1 FROM hr_holiday_calendars hc "
                "                   JOIN hr_holidays h ON h.calendar_id=hc.id "
                "                   WHERE hc.establishment_id=sd.establishment_id "
                "                     AND hc.status='approved' "
                "                     AND hc.effective_year=extract(year FROM sa.work_date)::int "
                "                     AND h.holiday_date=sa.work_date) "
                "   AND NOT EXISTS (SELECT 1 FROM hr_leave_requests lr "
                "                   WHERE lr.employee_id=sa.employee_id AND lr.status='approved' "
                "                     AND lr.start_date<=sa.work_date AND lr.end_date>=sa.work_date)"
                ") "
                "SELECT count(*)::int AS scheduled_days, "
                "count(*) FILTER (WHERE attended)::int AS attended_days, "
                "count(*) FILTER (WHERE NOT attended)::int AS absent_days, "
                "count(DISTINCT employee_id) FILTER (WHERE attended)::int AS present_employees, "
                "count(DISTINCT employee_id) FILTER (WHERE NOT attended)::int AS absent_employees "
                "FROM scheduled",
                (period_start, period_end),
            ).fetchone()
            payroll = conn.execute(
                "SELECT count(*)::int AS run_count, "
                "COALESCE(sum(total_gross),0)::numeric(16,2) AS gross, "
                "COALESCE(sum(total_deductions),0)::numeric(16,2) AS employee_deductions, "
                "COALESCE(sum(total_employer_contributions),0)::numeric(16,2) AS employer_contributions, "
                "COALESCE(sum(total_net),0)::numeric(16,2) AS net "
                "FROM hr_payroll_runs WHERE period_start >= %s AND period_start < %s "
                "AND status IN ('approved','paid')",
                (period_start, period_end),
            ).fetchone()
            run_statuses = conn.execute(
                "SELECT status,count(*)::int AS count FROM hr_payroll_runs "
                "WHERE period_start >= %s AND period_start < %s GROUP BY status ORDER BY status",
                (period_start, period_end),
            ).fetchall()
            approvals = conn.execute(
                "SELECT (SELECT count(*) FROM hr_leave_requests WHERE status='pending')::int AS leave_count, "
                "(SELECT count(*) FROM hr_expenses WHERE status='pending')::int AS expense_count, "
                "(SELECT count(*) FROM hr_employee_salary_versions WHERE status='draft')::int AS salary_revision_count, "
                "(SELECT count(*) FROM hr_payroll_earning_adjustments WHERE status='pending')::int AS earning_count, "
                "(SELECT count(*) FROM hr_employee_lifecycle_tasks WHERE status IN ('pending','in_progress') "
                "AND due_date < CURRENT_DATE)::int AS lifecycle_overdue_count"
            ).fetchone()
            controls = conn.execute(
                "SELECT (SELECT count(*) FROM hr_statutory_remittances WHERE status='pending')::int AS pending_remittances, "
                "(SELECT count(*) FROM hr_employees e LEFT JOIN hr_employee_statutory_profiles p "
                "ON p.employee_id=e.id WHERE e.status IN ('active','probation','on_leave','notice_period') "
                "AND p.employee_id IS NULL)::int AS employees_without_statutory_profile, "
                "(SELECT count(*) FROM hr_payroll_runs r LEFT JOIN hr_payroll_accrual_postings p "
                "ON p.payroll_run_id=r.id WHERE r.status IN ('approved','paid') AND p.id IS NULL AND r.accounting_accrual_voucher_id IS NULL)::int "
                "AS accounting_exceptions, "
                "(SELECT count(*) FROM hr_employees WHERE status IN ('active','probation','on_leave','notice_period') "
                "AND (department_id IS NULL OR length(trim(designation))=0))::int AS employee_data_issues, "
                "(SELECT count(*) FROM hr_employees WHERE status IN ('active','probation','on_leave','notice_period') "
                "AND user_id IS NULL)::int AS employees_without_portal_user, "
                "(SELECT count(*) FROM portal_invitations WHERE portal_type='employee' AND accepted_at IS NULL "
                "AND revoked_at IS NULL AND expires_at>now())::int AS pending_employee_invitations"
            ).fetchone()
            establishments = conn.execute(
                "SELECT id,code,display_name FROM hr_establishments WHERE is_active=true ORDER BY display_name"
            ).fetchall()
            statutory_readiness = []
            if establishments:
                policy_rows = conn.execute(
                    "SELECT establishment_id,component,effective_from,effective_to,status "
                    "FROM hr_statutory_policy_versions WHERE effective_from <= %s "
                    "AND (effective_to IS NULL OR effective_to >= %s)",
                    (period_end - date.resolution, period_end - date.resolution),
                ).fetchall()
                for establishment in establishments:
                    assessment = assess_policy_readiness(
                        [policy for policy in policy_rows if policy["establishment_id"] == establishment["id"]],
                        period_end - date.resolution,
                    )
                    statutory_readiness.append({
                        "establishment_id": establishment["id"],
                        "establishment": establishment["display_name"],
                        **assessment,
                    })
            controls = dict(controls)
            controls["statutory_readiness"] = (
                "not_configured" if not establishments else
                "ready" if all(item["ready"] for item in statutory_readiness) else "incomplete"
            )
            controls["establishments"] = statutory_readiness
            trend_start, _ = month_trend_period(month, 6)
            headcount_trend = conn.execute(
                "SELECT to_char(months.month_start,'YYYY-MM') AS month, "
                "count(e.id) FILTER (WHERE e.joining_date < (months.month_start + interval '1 month')::date "
                "AND (e.exit_date IS NULL OR e.exit_date >= months.month_start))::int AS headcount "
                "FROM generate_series(%s::date,%s::date,interval '1 month') "
                "AS months(month_start) LEFT JOIN hr_employees e ON true "
                "GROUP BY months.month_start ORDER BY months.month_start",
                (trend_start, period_end),
            ).fetchall()
            payroll_trend = conn.execute(
                "SELECT to_char(period_start,'YYYY-MM') AS month, "
                "COALESCE(sum(total_gross),0)::numeric(16,2) AS gross "
                "FROM hr_payroll_runs WHERE period_start >= %s AND period_start < %s "
                "AND status IN ('approved','paid') GROUP BY period_start ORDER BY period_start",
                (trend_start, period_end),
            ).fetchall()
            accounting_status = "exceptions" if controls["accounting_exceptions"] else "no_exceptions_detected"
            return {
                "period": {"month": month, "start_date": period_start.isoformat(),
                           "end_date": (period_end.fromordinal(period_end.toordinal() - 1)).isoformat()},
                "workforce": {**workforce, "departments": departments,
                              "department_count": len(departments)},
                "attendance": {
                    "available": bool(scheduled_attendance["scheduled_days"]),
                    "reason": None if scheduled_attendance["scheduled_days"] else
                    "No published shift schedule exists for this month; absence and attendance rate cannot be calculated.",
                    "present": (scheduled_attendance["present_employees"] if scheduled_attendance["scheduled_days"] else attendance["present"]),
                    "absent": scheduled_attendance["absent_employees"] if scheduled_attendance["scheduled_days"] else None,
                    "late": None,
                    "scheduled_shift_days": scheduled_attendance["scheduled_days"],
                    "attended_shift_days": scheduled_attendance["attended_days"],
                    "absent_shift_days": scheduled_attendance["absent_days"],
                    "on_leave": on_leave, "open_sessions": attendance["open_sessions"],
                    "rate": round(scheduled_attendance["attended_days"] * 100 / scheduled_attendance["scheduled_days"], 1)
                        if scheduled_attendance["scheduled_days"] else None,
                },
                "payroll": {**payroll, "run_statuses": run_statuses,
                            "accounting_status": accounting_status,
                            "exceptions": controls["accounting_exceptions"]},
                "approvals": approvals,
                "controls": controls,
                "trends": {"headcount": headcount_trend, "payroll_gross": payroll_trend,
                           "attendance": {"available": False, "reason": "Reliable shift and holiday history is required."}},
                "data_quality": {
                    "partial": True,
                    "unavailable_metrics": ["attendance.late", "attendance.trend"],
                },
            }
    except HTTPException:
        raise
    except psycopg.Error as exc:
        raise _db_error(exc) from exc


@router.get("/departments")
def list_departments(request: Request):
    _actor(request)
    try:
        with _hr_connection() as conn:
            return {"items": conn.execute(
                "SELECT d.id,d.code,d.name,d.description,d.is_active,d.created_at,"
                "count(e.id) FILTER (WHERE e.status<>'terminated') AS employee_count "
                "FROM hr_departments d LEFT JOIN hr_employees e ON e.department_id=d.id "
                "GROUP BY d.id ORDER BY d.name"
            ).fetchall()}
    except psycopg.Error as exc:
        raise _db_error(exc) from exc


@router.post("/departments", status_code=201)
def create_department(payload: DepartmentInput, request: Request):
    actor = _manager(request)
    try:
        with _hr_connection() as conn:
            return conn.execute(
                "INSERT INTO hr_departments(code,name,description) VALUES(%s,%s,%s) "
                "RETURNING id,code,name,description,is_active,created_at",
                (payload.code, payload.name, payload.description),
            ).fetchone()
    except psycopg.Error as exc:
        raise _db_error(exc) from exc


@router.put("/departments/{department_id}")
def update_department(department_id: int, payload: DepartmentInput, request: Request):
    _manager(request)
    try:
        with _hr_connection() as conn:
            row = conn.execute(
                "UPDATE hr_departments SET code=%s,name=%s,description=%s,updated_at=now() "
                "WHERE id=%s RETURNING id,code,name,description,is_active,updated_at",
                (payload.code,payload.name,payload.description,department_id),
            ).fetchone()
            if row is None:
                raise HTTPException(404,"Department not found")
            return row
    except HTTPException:
        raise
    except psycopg.Error as exc:
        raise _db_error(exc) from exc


@router.post("/departments/{department_id}/deactivate")
def deactivate_department(department_id: int, request: Request):
    _manager(request)
    try:
        with _hr_connection() as conn:
            row=conn.execute(
                "UPDATE hr_departments SET is_active=false,updated_at=now() WHERE id=%s AND is_active=true "
                "RETURNING id,code,name,is_active",(department_id,)
            ).fetchone()
            if row is None:
                raise HTTPException(404,"Active department not found")
            return row
    except HTTPException:
        raise
    except psycopg.Error as exc:
        raise _db_error(exc) from exc


@router.get("/employees")
def list_employees(request: Request, limit: int = Query(100, ge=1, le=500), offset: int = Query(0, ge=0)):
    actor = _actor(request)
    role = getattr(request.state, "role", "")
    try:
        with _hr_connection() as conn:
            if role in {"super_admin", "owner", "admin", "manager"}:
                rows = conn.execute(
                    "SELECT e.id,e.user_id,e.employee_code,e.first_name,e.last_name,e.email,e.phone,"
                    "e.department_id,d.name AS department_name,e.designation,e.reports_to_employee_id,"
                    "e.employment_type,e.status,e.joining_date,e.exit_date,"
                    "COALESCE(sv.basic_salary,e.basic_salary) AS basic_salary,"
                    "COALESCE(sv.hra,e.hra) AS hra,"
                    "COALESCE(sv.special_allowance,e.special_allowance) AS special_allowance,"
                    "COALESCE(sv.other_allowance,e.other_allowance) AS other_allowance,e.created_at,e.updated_at "
                    "FROM hr_employees e LEFT JOIN hr_departments d ON d.id=e.department_id "
                    "LEFT JOIN LATERAL (SELECT v.basic_salary,v.hra,v.special_allowance,v.other_allowance "
                    "FROM hr_employee_salary_versions v WHERE v.employee_id=e.id AND v.status='approved' "
                    "AND v.effective_from<=CURRENT_DATE AND (v.effective_to IS NULL OR v.effective_to>=CURRENT_DATE) "
                    "ORDER BY v.effective_from DESC LIMIT 1) sv ON true "
                    "ORDER BY e.employee_code LIMIT %s OFFSET %s", (limit, offset)
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT e.id,e.user_id,e.employee_code,e.first_name,e.last_name,e.email,e.phone,"
                    "e.department_id,d.name AS department_name,e.designation,e.reports_to_employee_id,"
                    "e.employment_type,e.status,e.joining_date,e.exit_date "
                    "FROM hr_employees e LEFT JOIN hr_departments d ON d.id=e.department_id "
                    "WHERE e.user_id=%s", (actor,)
                ).fetchall()
            return {"items": rows, "limit": limit, "offset": offset}
    except psycopg.Error as exc:
        raise _db_error(exc) from exc


def _link_employee_login_identity(conn, identity, party_id: int, user_id: int, actor_user_id: int):
    """Link an employee login only when it is not already owned by another SBID."""
    linked = conn.execute(
        "SELECT party_id,status FROM identity_auth_accounts WHERE app_user_id=%s",
        (user_id,),
    ).fetchone()
    if linked:
        if linked["party_id"] != party_id or linked["status"] != "active":
            raise HTTPException(409, "This staff login is already linked to another or inactive identity; resolve the identity conflict before onboarding")
        return
    identity.link_auth_account(
        party_id=party_id, account_type="staff", source_id=user_id,
        link_method="admin_verified", actor_user_id=actor_user_id,
    )


@router.post("/employees", status_code=201)
def create_employee(payload: EmployeeInput, request: Request):
    actor = _manager(request)
    try:
        with _hr_connection() as conn:
            row = conn.execute(
                "INSERT INTO hr_employees(user_id,employee_code,first_name,last_name,email,phone,department_id,"
                "designation,reports_to_employee_id,employment_type,status,joining_date,exit_date,basic_salary,"
                "hra,special_allowance,other_allowance,created_by_user_id) "
                "VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) "
                "RETURNING id,user_id,employee_code,first_name,last_name,email,phone,department_id,designation,"
                "employment_type,status,joining_date,basic_salary,hra,special_allowance,other_allowance,created_at",
                (payload.user_id,payload.employee_code.strip(),payload.first_name.strip(),payload.last_name.strip(),
                 payload.email,payload.phone.strip(),payload.department_id,payload.designation.strip(),
                 payload.reports_to_employee_id,payload.employment_type,payload.status,payload.joining_date,
                 payload.exit_date,payload.basic_salary,payload.hra,payload.special_allowance,
                 payload.other_allowance,actor),
            ).fetchone()
            conn.execute(
                "INSERT INTO hr_employee_salary_versions(employee_id,effective_from,basic_salary,hra,"
                "special_allowance,other_allowance,status,reason,created_by_user_id,reviewed_by_user_id,reviewed_at) "
                "VALUES(%s,%s,%s,%s,%s,%s,'approved','Opening salary profile approved when employee was created',%s,%s,now())",
                (row["id"],payload.joining_date,payload.basic_salary,payload.hra,
                 payload.special_allowance,payload.other_allowance,actor,actor),
            )
            # Create the permanent identity at employee onboarding, not only when
            # a portal invitation is accepted. Keep the HR employee ID unchanged.
            from app.services.identity import IdentityService
            identity = IdentityService(conn)
            existing = conn.execute(
                "SELECT party_id FROM identity_profiles WHERE profile_type='employee' "
                "AND employee_id=%s AND status='active' FOR UPDATE",
                (row["id"],),
            ).fetchone()
            if existing:
                party_id = existing["party_id"]
            else:
                party = identity.create_party(
                    party_type="individual",
                    display_name=(row["first_name"] + " " + row["last_name"]).strip(),
                    actor_user_id=actor,
                    reason="HR employee created",
                )
                party_id = party["id"]
                identity.link_profile(
                    party_id=party_id, profile_type="employee", source_id=row["id"],
                    link_method="admin_verified", actor_user_id=actor,
                    reason="HR employee created",
                )
                if row["email"]:
                    try:
                        identity.add_contact(party_id=party_id, contact_type="email",
                                             value=row["email"], source="hr_employee")
                    except ValueError:
                        # Legacy HR email validation is intentionally retained;
                        # malformed optional contact data must not block onboarding.
                        pass
                if row["phone"]:
                    try:
                        identity.add_contact(party_id=party_id, contact_type="phone",
                                             value=row["phone"], source="hr_employee")
                    except ValueError:
                        # HR may hold landlines or non-E.164 extensions; do not
                        # block employee onboarding over optional contact normalisation.
                        pass
            if row["user_id"]:
                _link_employee_login_identity(conn, identity, party_id, row["user_id"], actor)
            return row
    except psycopg.Error as exc:
        raise _db_error(exc) from exc


@router.put("/employees/{employee_id}")
def update_employee(employee_id: int, payload: EmployeeInput, request: Request):
    _manager(request)
    try:
        with _hr_connection() as conn:
            _validate_reporting_manager(conn, employee_id, payload.reports_to_employee_id)
            row = conn.execute(
                "UPDATE hr_employees SET user_id=%s,employee_code=%s,first_name=%s,last_name=%s,email=%s,phone=%s,"
                "department_id=%s,designation=%s,reports_to_employee_id=%s,employment_type=%s,status=%s,"
                "joining_date=%s,exit_date=%s,updated_at=now() "
                "WHERE id=%s RETURNING id,user_id,employee_code,first_name,last_name,email,status,updated_at",
                (payload.user_id,payload.employee_code.strip(),payload.first_name.strip(),payload.last_name.strip(),
                 payload.email,payload.phone.strip(),payload.department_id,payload.designation.strip(),
                 payload.reports_to_employee_id,payload.employment_type,payload.status,payload.joining_date,
                 payload.exit_date,employee_id),
            ).fetchone()
            if row is None:
                raise HTTPException(404, "Employee not found")
            if row["status"] == "terminated" and row["user_id"] is not None:
                # Termination closes employee self-service access without disabling
                # a shared administrator identity.
                conn.execute(
                    "UPDATE app_users SET is_active=FALSE WHERE id=%s AND role='staff'",
                    (row["user_id"],),
                )
                conn.execute(
                    "UPDATE portal_invitations SET revoked_at=now() WHERE employee_id=%s "
                    "AND accepted_at IS NULL AND revoked_at IS NULL",
                    (employee_id,),
                )
            return row
    except HTTPException:
        raise
    except psycopg.Error as exc:
        raise _db_error(exc) from exc


@router.get("/employees/{employee_id}/salary-revisions")
def list_salary_revisions(employee_id: int, request: Request):
    _manager(request)
    try:
        with _hr_connection() as conn:
            employee = conn.execute("SELECT id FROM hr_employees WHERE id=%s", (employee_id,)).fetchone()
            if employee is None:
                raise HTTPException(404, "Employee not found")
            return {"items": conn.execute(
                "SELECT id,employee_id,effective_from,effective_to,basic_salary,hra,special_allowance,"
                "other_allowance,status,reason,review_note,created_by_user_id,reviewed_by_user_id,"
                "reviewed_at,created_at FROM hr_employee_salary_versions "
                "WHERE employee_id=%s ORDER BY effective_from DESC,id DESC", (employee_id,)
            ).fetchall()}
    except HTTPException:
        raise
    except psycopg.Error as exc:
        raise _db_error(exc) from exc


@router.post("/employees/{employee_id}/salary-revisions", status_code=201)
def create_salary_revision(employee_id: int, payload: SalaryRevisionInput, request: Request):
    actor = _manager(request)
    try:
        with _hr_connection() as conn:
            employee = conn.execute("SELECT id FROM hr_employees WHERE id=%s FOR UPDATE", (employee_id,)).fetchone()
            if employee is None:
                raise HTTPException(404, "Employee not found")
            row = conn.execute(
                "INSERT INTO hr_employee_salary_versions(employee_id,effective_from,effective_to,basic_salary,"
                "hra,special_allowance,other_allowance,reason,created_by_user_id) "
                "VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s) "
                "RETURNING id,employee_id,effective_from,effective_to,basic_salary,hra,special_allowance,"
                "other_allowance,status,reason,created_at",
                (employee_id,payload.effective_from,payload.effective_to,payload.basic_salary,payload.hra,
                 payload.special_allowance,payload.other_allowance,payload.reason,actor),
            ).fetchone()
            return row
    except HTTPException:
        raise
    except psycopg.Error as exc:
        raise _db_error(exc) from exc


@router.post("/employees/{employee_id}/salary-revisions/{revision_id}/review")
def review_salary_revision(employee_id: int, revision_id: int, payload: PayrollApprovalInput, request: Request):
    actor = _manager(request)
    try:
        with _hr_connection() as conn:
            employee = conn.execute("SELECT id FROM hr_employees WHERE id=%s FOR UPDATE", (employee_id,)).fetchone()
            if employee is None:
                raise HTTPException(404, "Employee not found")
            revision = conn.execute(
                "SELECT * FROM hr_employee_salary_versions WHERE id=%s AND employee_id=%s FOR UPDATE",
                (revision_id,employee_id),
            ).fetchone()
            if revision is None:
                raise HTTPException(404, "Salary revision not found")
            if revision["status"] != "draft":
                raise HTTPException(409, "Only draft salary revisions can be reviewed")
            _require_independent_reviewer(revision["created_by_user_id"], actor, "salary revision")
            if payload.decision == "rejected":
                return conn.execute(
                    "UPDATE hr_employee_salary_versions SET status='rejected',review_note=%s,"
                    "reviewed_by_user_id=%s,reviewed_at=now(),updated_at=now() WHERE id=%s "
                    "RETURNING id,status,review_note,reviewed_by_user_id,reviewed_at",
                    (payload.note,actor,revision_id),
                ).fetchone()

            period_start = revision["effective_from"].replace(day=1)
            period_end = date(
                revision["effective_from"].year,
                revision["effective_from"].month,
                monthrange(revision["effective_from"].year,revision["effective_from"].month)[1],
            )
            closed_payroll = conn.execute(
                "SELECT id,status FROM hr_payroll_runs WHERE period_start=%s AND period_end=%s "
                "AND status IN ('approved','paid') LIMIT 1",
                (period_start,period_end),
            ).fetchone()
            if closed_payroll:
                raise HTTPException(409, "Salary revision cannot change a month whose payroll is already approved or paid")

            latest = conn.execute(
                "SELECT id,effective_from,effective_to FROM hr_employee_salary_versions "
                "WHERE employee_id=%s AND status='approved' ORDER BY effective_from DESC LIMIT 1 FOR UPDATE",
                (employee_id,),
            ).fetchone()
            if latest and revision["effective_from"] <= latest["effective_from"]:
                raise HTTPException(409, "A salary revision must take effect after the latest approved revision")
            if latest and latest["effective_to"] is None:
                conn.execute(
                    "UPDATE hr_employee_salary_versions SET effective_to=%s,updated_at=now() WHERE id=%s",
                    (revision["effective_from"] - __import__("datetime").timedelta(days=1),latest["id"]),
                )
            approved = conn.execute(
                "UPDATE hr_employee_salary_versions SET status='approved',review_note=%s,"
                "reviewed_by_user_id=%s,reviewed_at=now(),updated_at=now() WHERE id=%s "
                "RETURNING id,status,effective_from,effective_to,basic_salary,hra,special_allowance,"
                "other_allowance,review_note,reviewed_by_user_id,reviewed_at",
                (payload.note,actor,revision_id),
            ).fetchone()
            if revision["effective_from"] <= date.today():
                conn.execute(
                    "UPDATE hr_employees SET basic_salary=%s,hra=%s,special_allowance=%s,other_allowance=%s,"
                    "updated_at=now() WHERE id=%s",
                    (revision["basic_salary"],revision["hra"],revision["special_allowance"],
                     revision["other_allowance"],employee_id),
                )
            return approved
    except HTTPException:
        raise
    except psycopg.Error as exc:
        raise _db_error(exc) from exc


@router.get("/attendance/me")
def attendance_me(request: Request, month: str = Query(..., pattern=r"^\d{4}-\d{2}$")):
    actor = _actor(request)
    try:
        with _hr_connection() as conn:
            employee = _employee(conn, actor)
            start = date.fromisoformat(month + "-01")
            end = date(start.year, start.month, monthrange(start.year, start.month)[1])
            rows = conn.execute(
                "SELECT id,clock_in_at,clock_out_at,clock_in_note,clock_out_note,source,"
                "round(extract(epoch FROM (COALESCE(clock_out_at,now())-clock_in_at))/3600.0,2) AS hours "
                "FROM hr_attendance_sessions WHERE employee_id=%s AND clock_in_at >= %s "
                "AND clock_in_at < (%s::date + interval '1 day') ORDER BY clock_in_at DESC",
                (employee["id"],start,end),
            ).fetchall()
            return {"employee": employee, "month": month, "items": rows}
    except HTTPException:
        raise
    except (ValueError, psycopg.Error) as exc:
        if isinstance(exc, ValueError):
            raise HTTPException(422, "Month must be YYYY-MM") from exc
        raise _db_error(exc) from exc


@router.post("/attendance/punch", status_code=201)
def attendance_punch(payload: PunchInput, request: Request):
    actor = _actor(request)
    try:
        with _hr_connection() as conn:
            employee = _employee(conn, actor)
            profile = conn.execute(
                "SELECT establishment_id FROM hr_employee_statutory_profiles WHERE employee_id=%s",
                (employee["id"],),
            ).fetchone()
            policy = None
            locations = []
            if profile:
                policy = conn.execute(
                    "SELECT * FROM hr_attendance_policies WHERE establishment_id=%s "
                    "AND effective_from<=CURRENT_DATE AND (effective_to IS NULL OR effective_to>=CURRENT_DATE) "
                    "ORDER BY effective_from DESC LIMIT 1",
                    (profile["establishment_id"],),
                ).fetchone()
                if policy and policy["geofence_enabled"]:
                    locations = conn.execute(
                        "SELECT * FROM hr_attendance_work_locations WHERE establishment_id=%s AND is_active=true",
                        (profile["establishment_id"],),
                    ).fetchall()
            is_clock_in = payload.punch_type == "clock_in"
            requires_location = bool(policy and policy["geofence_enabled"] and (
                policy["geofence_enforced"]
                or (is_clock_in and policy["require_location_on_clock_in"])
                or (not is_clock_in and policy["require_location_on_clock_out"])
            ))
            if requires_location and payload.latitude is None:
                raise HTTPException(422, "GPS coordinates are required by the active attendance policy")
            matched_location_id = None
            if payload.latitude is not None and policy and policy["geofence_enabled"]:
                from app.services.hr_attendance import is_within_geofence
                for location in locations:
                    if is_within_geofence(
                        latitude=payload.latitude, longitude=payload.longitude,
                        center_latitude=float(location["latitude"]),
                        center_longitude=float(location["longitude"]),
                        radius_meters=location["radius_meters"],
                    ):
                        matched_location_id = location["id"]
                        break
                if policy["geofence_enforced"] and matched_location_id is None:
                    raise HTTPException(403, "You are outside the permitted attendance work locations")
            if is_clock_in:
                try:
                    row = conn.execute(
                        "INSERT INTO hr_attendance_sessions(employee_id,clock_in_note,created_by_user_id,"
                        "last_modified_by_user_id,clock_in_latitude,clock_in_longitude,clock_in_accuracy_meters,"
                        "clock_in_work_location_id) VALUES(%s,%s,%s,%s,%s,%s,%s,%s) "
                        "RETURNING id,employee_id,clock_in_at,clock_out_at,source",
                        (employee["id"],payload.note,actor,actor,payload.latitude,payload.longitude,
                         payload.accuracy_meters,matched_location_id),
                    ).fetchone()
                except psycopg.errors.UniqueViolation as exc:
                    raise HTTPException(409, "You are already clocked in") from exc
            else:
                row = conn.execute(
                    "UPDATE hr_attendance_sessions SET clock_out_at=now(),clock_out_note=%s,closed_by_user_id=%s,"
                    "last_modified_by_user_id=%s,clock_out_latitude=%s,clock_out_longitude=%s,"
                    "clock_out_accuracy_meters=%s,clock_out_work_location_id=%s "
                    "WHERE id=(SELECT id FROM hr_attendance_sessions WHERE employee_id=%s AND clock_out_at IS NULL "
                    "ORDER BY clock_in_at DESC LIMIT 1 FOR UPDATE) "
                    "RETURNING id,employee_id,clock_in_at,clock_out_at,source",
                    (payload.note,actor,actor,payload.latitude,payload.longitude,payload.accuracy_meters,
                     matched_location_id,employee["id"]),
                ).fetchone()
                if row is None:
                    raise HTTPException(409, "No open attendance session exists")
            return row
    except HTTPException:
        raise
    except psycopg.Error as exc:
        raise _db_error(exc) from exc


@router.get("/attendance/register")
def attendance_register(
    request: Request,
    start_date: date,
    end_date: date,
    employee_id: int | None = Query(default=None, gt=0),
    department_id: int | None = Query(default=None, gt=0),
):
    _manager(request)
    if end_date < start_date or (end_date-start_date).days > 93:
        raise HTTPException(422, "Date range must be ordered and no longer than 94 days")
    try:
        with _hr_connection() as conn:
            rows = conn.execute(
                "SELECT e.id AS employee_id,e.employee_code,e.first_name,e.last_name,"
                "e.department_id,d.name AS department_name,s.id,s.clock_in_at,s.clock_out_at,"
                "round(extract(epoch FROM (COALESCE(s.clock_out_at,now())-s.clock_in_at))/3600.0,2) AS hours,"
                "a.id AS shift_assignment_id,a.planned_start_at,a.planned_end_at,"
                "sh.timezone,COALESCE(p.grace_minutes,0) AS grace_minutes,"
                "COALESCE(p.break_minutes,sh.break_minutes,0) AS break_minutes "
                "FROM hr_employees e LEFT JOIN hr_departments d ON d.id=e.department_id "
                "LEFT JOIN hr_attendance_sessions s ON s.employee_id=e.id "
                "AND s.clock_in_at >= %s AND s.clock_in_at < (%s::date + interval '1 day') "
                "LEFT JOIN hr_shift_assignments a ON a.employee_id=e.id AND a.status='published' "
                "AND a.work_date=(s.clock_in_at AT TIME ZONE COALESCE((SELECT timezone FROM hr_shift_definitions WHERE id=a.shift_definition_id),'Asia/Kolkata'))::date "
                "LEFT JOIN hr_shift_definitions sh ON sh.id=a.shift_definition_id "
                "LEFT JOIN LATERAL (SELECT grace_minutes,break_minutes FROM hr_attendance_policies ap "
                "WHERE ap.establishment_id=sh.establishment_id AND ap.effective_from<=a.work_date "
                "AND (ap.effective_to IS NULL OR ap.effective_to>=a.work_date) "
                "ORDER BY ap.effective_from DESC LIMIT 1) p ON true "
                "WHERE e.status<>'terminated' AND (%s::bigint IS NULL OR e.id=%s) "
                "AND (%s::bigint IS NULL OR e.department_id=%s) "
                "ORDER BY e.employee_code,s.clock_in_at",
                (start_date,end_date,employee_id,employee_id,department_id,department_id),
            ).fetchall()
            from app.services.hr_attendance import calculate_shift_metrics
            items = []
            totals = {"sessions": 0, "worked_minutes": 0, "late_minutes": 0,
                      "early_departure_minutes": 0, "overtime_minutes": 0}
            for source in rows:
                item = dict(source)
                if item.get("id") and item.get("planned_start_at") and item.get("planned_end_at"):
                    metrics = calculate_shift_metrics(
                        clock_in_at=item["clock_in_at"], clock_out_at=item["clock_out_at"],
                        planned_start_at=item["planned_start_at"], planned_end_at=item["planned_end_at"],
                        grace_minutes=item["grace_minutes"], break_minutes=item["break_minutes"],
                    )
                else:
                    metrics = {"worked_minutes": int(float(item.get("hours") or 0) * 60),
                               "late_minutes": None, "early_departure_minutes": None,
                               "overtime_minutes": None}
                item.update(metrics)
                if item.get("id"):
                    totals["sessions"] += 1
                    totals["worked_minutes"] += metrics["worked_minutes"]
                    for key in ("late_minutes", "early_departure_minutes", "overtime_minutes"):
                        if metrics[key] is not None:
                            totals[key] += metrics[key]
                items.append(item)
            return {"items": items, "summary": totals, "start_date": start_date, "end_date": end_date}
    except HTTPException:
        raise
    except psycopg.Error as exc:
        raise _db_error(exc) from exc


@router.patch("/attendance/sessions/{session_id}")
def request_attendance_correction(session_id: int, payload: AttendanceAdjustmentInput, request: Request):
    """Submit a correction for independent review; never mutate the source session here."""
    actor = _manager(request)
    try:
        clock_in = datetime.fromisoformat(str(payload.clock_in_at).replace("Z", "+00:00"))
        clock_out = datetime.fromisoformat(str(payload.clock_out_at).replace("Z", "+00:00")) if payload.clock_out_at else None
    except ValueError as exc:
        raise HTTPException(422, "Attendance timestamps must be valid ISO date-time values") from exc
    if clock_in.tzinfo is None or (clock_out is not None and clock_out.tzinfo is None):
        raise HTTPException(422, "Attendance timestamps must include a timezone offset")
    if clock_out and clock_out < clock_in:
        raise HTTPException(422, "Check-out cannot be earlier than check-in")
    try:
        with _hr_connection() as conn:
            session = conn.execute(
                "SELECT id,employee_id FROM hr_attendance_sessions WHERE id=%s FOR UPDATE",
                (session_id,),
            ).fetchone()
            if session is None:
                raise HTTPException(404, "Attendance session not found")
            row = conn.execute(
                "INSERT INTO hr_attendance_correction_requests "
                "(attendance_session_id,employee_id,requested_clock_in_at,requested_clock_out_at,reason,requested_by_user_id) "
                "VALUES(%s,%s,%s,%s,%s,%s) RETURNING *",
                (session_id,session["employee_id"],clock_in,clock_out,payload.reason.strip(),actor),
            ).fetchone()
            return {"status": "pending_review", "request": row}
    except HTTPException:
        raise
    except psycopg.errors.UniqueViolation as exc:
        raise HTTPException(409, "A correction request is already awaiting review for this session") from exc
    except psycopg.Error as exc:
        raise _db_error(exc) from exc


@router.get("/attendance/sessions/{session_id}/audit")
def attendance_session_audit(session_id: int, request: Request):
    _manager(request)
    with _hr_connection() as conn:
        exists = conn.execute(
            "SELECT id FROM hr_attendance_sessions WHERE id=%s",
            (session_id,),
        ).fetchone()
        if exists is None:
            raise HTTPException(404, "Attendance session not found")
        rows = conn.execute(
            "SELECT id,attendance_session_id,employee_id,event_type,actor_user_id,"
            "before_state,after_state,created_at FROM hr_attendance_audit_events "
            "WHERE attendance_session_id=%s ORDER BY created_at,id",
            (session_id,),
        ).fetchall()
        return {"items": rows}


@router.get("/attendance/corrections")
def list_attendance_corrections(request: Request, status: str = Query(default="pending", pattern="^(pending|approved|rejected|cancelled|all)$")):
    _manager(request)
    with _hr_connection() as conn:
        rows = conn.execute(
            "SELECT c.*,e.employee_code,e.first_name,e.last_name "
            "FROM hr_attendance_correction_requests c "
            "JOIN hr_employees e ON e.id=c.employee_id "
            "WHERE (%s='all' OR c.status=%s) ORDER BY c.created_at DESC",
            (status,status),
        ).fetchall()
        return {"items": rows}


@router.patch("/attendance/corrections/{correction_id}/review")
def review_attendance_correction(correction_id: int, payload: ReviewInput, request: Request):
    actor = _manager(request)
    try:
        with _hr_connection() as conn:
            correction = conn.execute(
                "SELECT * FROM hr_attendance_correction_requests WHERE id=%s FOR UPDATE",
                (correction_id,),
            ).fetchone()
            if correction is None or correction["status"] != "pending":
                raise HTTPException(409, "Correction request not found or already reviewed")
            if correction["requested_by_user_id"] == actor:
                raise HTTPException(403, "A correction must be reviewed by a different authorised user")
            if payload.decision == "approved":
                updated = conn.execute(
                    "UPDATE hr_attendance_sessions SET clock_in_at=%s,clock_out_at=%s,"
                    "source='manager_adjustment',last_modified_by_user_id=%s,closed_by_user_id=%s,"
                    "clock_in_note=concat_ws(E'\\n',nullif(clock_in_note,''),'Approved HR correction: '||%s),"
                    "clock_out_note=CASE WHEN %s IS NULL THEN clock_out_note ELSE "
                    "concat_ws(E'\\n',nullif(clock_out_note,''),'Approved HR correction: '||%s) END "
                    "WHERE id=%s RETURNING id",
                    (correction["requested_clock_in_at"],correction["requested_clock_out_at"],actor,actor,
                     correction["reason"],correction["requested_clock_out_at"],correction["reason"],
                     correction["attendance_session_id"]),
                ).fetchone()
                if updated is None:
                    raise HTTPException(404, "Attendance session no longer exists")
            reviewed = conn.execute(
                "UPDATE hr_attendance_correction_requests SET status=%s,reviewed_by_user_id=%s,"
                "review_note=%s,reviewed_at=now() WHERE id=%s AND status='pending' RETURNING *",
                (payload.decision,actor,payload.note,correction_id),
            ).fetchone()
            return reviewed
    except HTTPException:
        raise
    except psycopg.Error as exc:
        raise _db_error(exc) from exc


@router.get("/leave")
def list_leave(request: Request):
    actor = _actor(request)
    role = getattr(request.state, "role", "")
    try:
        with _hr_connection() as conn:
            if role in {"super_admin","owner","admin","manager"}:
                rows = conn.execute(
                    "SELECT l.*,e.employee_code,e.first_name,e.last_name,e.user_id AS employee_user_id FROM hr_leave_requests l "
                    "JOIN hr_employees e ON e.id=l.employee_id ORDER BY l.created_at DESC"
                ).fetchall()
            else:
                employee = _employee(conn,actor)
                rows = conn.execute("SELECT * FROM hr_leave_requests WHERE employee_id=%s ORDER BY created_at DESC",(employee["id"],)).fetchall()
            return {"items": rows}
    except HTTPException:
        raise
    except psycopg.Error as exc:
        raise _db_error(exc) from exc


@router.post("/leave", status_code=201)
def create_leave(payload: LeaveInput, request: Request):
    actor = _actor(request)
    if payload.end_date < payload.start_date:
        raise HTTPException(422, "Leave end date must be on or after the start date")
    try:
        with _hr_connection() as conn:
            employee = _employee(conn,actor)
            overlap = conn.execute(
                "SELECT id FROM hr_leave_requests WHERE employee_id=%s AND status IN ('pending','approved') "
                "AND daterange(start_date,end_date,'[]') && daterange(%s,%s,'[]') FOR UPDATE",
                (employee["id"],payload.start_date,payload.end_date),
            ).fetchone()
            if overlap:
                raise HTTPException(409, "This leave period overlaps an existing pending or approved request")
            return conn.execute(
                "INSERT INTO hr_leave_requests(employee_id,leave_type,start_date,end_date,days,reason) "
                "VALUES(%s,%s,%s,%s,%s,%s) RETURNING *",
                (employee["id"],payload.leave_type,payload.start_date,payload.end_date,payload.days,payload.reason.strip()),
            ).fetchone()
    except HTTPException:
        raise
    except psycopg.Error as exc:
        raise _db_error(exc) from exc


@router.patch("/leave/{leave_id}/review")
def review_leave(leave_id: int, payload: ReviewInput, request: Request):
    actor = _manager(request)
    try:
        with _hr_connection() as conn:
            request_row = conn.execute(
                "SELECT lr.id,e.user_id FROM hr_leave_requests lr "
                "JOIN hr_employees e ON e.id=lr.employee_id WHERE lr.id=%s AND lr.status='pending' FOR UPDATE OF lr",
                (leave_id,),
            ).fetchone()
            if request_row is None:
                raise HTTPException(409, "Leave request not found or already reviewed")
            _require_independent_reviewer(request_row["user_id"], actor, "leave request")
            row = conn.execute(
                "UPDATE hr_leave_requests SET status=%s,reviewed_by_user_id=%s,review_note=%s,reviewed_at=now() "
                "WHERE id=%s AND status='pending' RETURNING *",
                (payload.decision,actor,payload.note,leave_id),
            ).fetchone()
            if payload.decision == "approved":
                policy = conn.execute(
                    "SELECT p.* FROM hr_leave_policies p "
                    "JOIN hr_employee_statutory_profiles sp ON sp.establishment_id=p.establishment_id "
                    "WHERE sp.employee_id=%s AND p.leave_type=%s AND p.status='approved' "
                    "AND p.effective_from<=%s AND (p.effective_to IS NULL OR p.effective_to>=%s) "
                    "ORDER BY p.effective_from DESC LIMIT 1",
                    (row["employee_id"],row["leave_type"],row["start_date"],row["end_date"])
                ).fetchone()
                if policy and row["leave_type"] != "unpaid":
                    balance = conn.execute(
                        "SELECT COALESCE(sum(quantity_days),0) AS days FROM hr_leave_ledger "
                        "WHERE employee_id=%s AND leave_type=%s AND effective_date<=%s",
                        (row["employee_id"],row["leave_type"],row["start_date"])
                    ).fetchone()["days"]
                    if not policy["allow_negative_balance"] and balance < row["days"]:
                        raise HTTPException(409,"Insufficient leave balance under the approved leave policy")
                    conn.execute(
                        "INSERT INTO hr_leave_ledger(employee_id,leave_type,policy_id,transaction_type,source_type,"
                        "source_id,effective_date,quantity_days,reason,actor_user_id) "
                        "VALUES(%s,%s,%s,'consumption','leave_request',%s,%s,%s,%s,%s) "
                        "ON CONFLICT DO NOTHING",
                        (row["employee_id"],row["leave_type"],policy["id"],row["id"],row["start_date"],
                         -row["days"],"Approved leave request #"+str(row["id"]),actor)
                    )
            return row
    except HTTPException:
        raise
    except psycopg.Error as exc:
        raise _db_error(exc) from exc


@router.get("/expenses")
def list_expenses(request: Request):
    actor = _actor(request)
    role = getattr(request.state,"role","")
    try:
        with _hr_connection() as conn:
            if role in {"super_admin","owner","admin","manager"}:
                rows=conn.execute(
                    "SELECT x.*,e.employee_code,e.first_name,e.last_name,e.user_id AS employee_user_id FROM hr_expenses x "
                    "JOIN hr_employees e ON e.id=x.employee_id ORDER BY x.created_at DESC"
                ).fetchall()
            else:
                employee=_employee(conn,actor)
                rows=conn.execute("SELECT * FROM hr_expenses WHERE employee_id=%s ORDER BY created_at DESC",(employee["id"],)).fetchall()
            return {"items":rows}
    except HTTPException:
        raise
    except psycopg.Error as exc:
        raise _db_error(exc) from exc


@router.post("/expenses",status_code=201)
def create_expense(payload: ExpenseInput,request: Request):
    actor=_actor(request)
    try:
        with _hr_connection() as conn:
            employee=_employee(conn,actor)
            return conn.execute(
                "INSERT INTO hr_expenses(employee_id,category,amount,expense_date,description,receipt_reference) "
                "VALUES(%s,%s,%s,%s,%s,%s) RETURNING *",
                (employee["id"],payload.category.strip(),payload.amount,payload.expense_date,payload.description.strip(),payload.receipt_reference),
            ).fetchone()
    except HTTPException:
        raise
    except psycopg.Error as exc:
        raise _db_error(exc) from exc


@router.patch("/expenses/{expense_id}/review")
def review_expense(expense_id:int,payload:ReviewInput,request:Request):
    actor=_manager(request)
    try:
        with _hr_connection() as conn:
            expense = conn.execute(
                "SELECT x.id,e.user_id FROM hr_expenses x JOIN hr_employees e ON e.id=x.employee_id "
                "WHERE x.id=%s AND x.status='pending' FOR UPDATE OF x",
                (expense_id,),
            ).fetchone()
            if expense is None:
                raise HTTPException(409,"Expense not found or already reviewed")
            _require_independent_reviewer(expense["user_id"], actor, "expense claim")
            row=conn.execute(
                "UPDATE hr_expenses SET status=%s,reviewed_by_user_id=%s,review_note=%s,reviewed_at=now() "
                "WHERE id=%s AND status='pending' RETURNING *",
                (payload.decision,actor,payload.note,expense_id),
            ).fetchone()
            return row
    except HTTPException:
        raise
    except psycopg.Error as exc:
        raise _db_error(exc) from exc


@router.get("/payroll/earning-adjustments")
def list_payroll_earning_adjustments(request: Request, limit: int = Query(250, ge=1, le=1000)):
    _manager(request)
    try:
        with _hr_connection() as conn:
            return {"items": conn.execute(
                "SELECT a.*,e.employee_code,e.first_name,e.last_name FROM hr_payroll_earning_adjustments a "
                "JOIN hr_employees e ON e.id=a.employee_id "
                "ORDER BY a.period_start DESC,e.employee_code,a.created_at DESC LIMIT %s", (limit,)
            ).fetchall()}
    except psycopg.Error as exc:
        raise _db_error(exc) from exc


@router.post("/employees/{employee_id}/earning-adjustments", status_code=201)
def create_payroll_earning_adjustment(employee_id: int, payload: PayrollEarningInput, request: Request):
    actor = _manager(request)
    try:
        with _hr_connection() as conn:
            employee = conn.execute("SELECT id FROM hr_employees WHERE id=%s FOR UPDATE", (employee_id,)).fetchone()
            if employee is None:
                raise HTTPException(404, "Employee not found")
            closed = conn.execute(
                "SELECT id FROM hr_payroll_runs WHERE period_start=%s AND period_end=%s "
                "AND status IN ('approved','paid') LIMIT 1",
                (payload.period_start,payload.period_end),
            ).fetchone()
            if closed:
                raise HTTPException(409, "Earnings cannot be added after the period payroll is approved or paid")
            return conn.execute(
                "INSERT INTO hr_payroll_earning_adjustments(employee_id,earning_type,period_start,period_end,"
                "amount,hours,hourly_rate,reason,created_by_user_id) "
                "VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s) "
                "RETURNING id,employee_id,earning_type,period_start,period_end,amount,hours,hourly_rate,reason,status,created_at",
                (employee_id,payload.earning_type,payload.period_start,payload.period_end,payload.amount,
                 payload.hours,payload.hourly_rate,payload.reason,actor),
            ).fetchone()
    except HTTPException:
        raise
    except psycopg.Error as exc:
        raise _db_error(exc) from exc


@router.post("/payroll/earning-adjustments/{adjustment_id}/review")
def review_payroll_earning_adjustment(adjustment_id: int, payload: PayrollApprovalInput, request: Request):
    actor = _manager(request)
    try:
        with _hr_connection() as conn:
            adjustment = conn.execute(
                "SELECT * FROM hr_payroll_earning_adjustments WHERE id=%s FOR UPDATE",
                (adjustment_id,),
            ).fetchone()
            if adjustment is None:
                raise HTTPException(404, "Payroll earning adjustment not found")
            if adjustment["status"] != "pending":
                raise HTTPException(409, "Only pending payroll earning adjustments can be reviewed")
            _require_independent_reviewer(adjustment["created_by_user_id"], actor, "variable earning")
            closed = conn.execute(
                "SELECT id FROM hr_payroll_runs WHERE period_start=%s AND period_end=%s "
                "AND status IN ('approved','paid') LIMIT 1",
                (adjustment["period_start"],adjustment["period_end"]),
            ).fetchone()
            if closed:
                raise HTTPException(409, "The period payroll is already approved or paid")
            status = "approved" if payload.decision == "approved" else "rejected"
            return conn.execute(
                "UPDATE hr_payroll_earning_adjustments SET status=%s,review_note=%s,"
                "reviewed_by_user_id=%s,reviewed_at=now(),updated_at=now() WHERE id=%s "
                "RETURNING id,employee_id,earning_type,period_start,period_end,amount,hours,hourly_rate,"
                "reason,status,review_note,reviewed_by_user_id,reviewed_at",
                (status,payload.note,actor,adjustment_id),
            ).fetchone()
    except HTTPException:
        raise
    except psycopg.Error as exc:
        raise _db_error(exc) from exc


@router.get("/payroll/runs")
def list_payroll_runs(request: Request):
    _manager(request)
    try:
        with _hr_connection() as conn:
            return {"items":conn.execute(
                "SELECT r.*,(SELECT count(*) FROM hr_payslips p WHERE p.payroll_run_id=r.id) AS employee_count,"
                "(SELECT count(*) FROM hr_payroll_statutory_snapshots s WHERE s.payroll_run_id=r.id) AS statutory_snapshot_count,"
                "((SELECT count(*) FROM hr_payslips p WHERE p.payroll_run_id=r.id)>0 AND "
                "(SELECT count(*) FROM hr_payroll_statutory_snapshots s WHERE s.payroll_run_id=r.id)="
                "4*(SELECT count(*) FROM hr_payslips p WHERE p.payroll_run_id=r.id)) AS statutory_ready,"
                "(SELECT COALESCE(json_agg(json_build_object('establishment_id',ap.establishment_id,"
                "'legal_entity_code',e.code,'voucher_id',ap.accounting_voucher_id,'total_amount',ap.total_amount) "
                "ORDER BY e.code),'[]'::json) FROM hr_payroll_accrual_postings ap "
                "JOIN hr_establishments e ON e.id=ap.establishment_id WHERE ap.payroll_run_id=r.id) "
                "AS accounting_accrual_postings "
                "FROM hr_payroll_runs r ORDER BY r.period_start DESC"
            ).fetchall()}
    except psycopg.Error as exc:
        raise _db_error(exc) from exc


@router.post("/payroll/runs",status_code=201)
def calculate_payroll(payload: PayrollRunInput, request: Request):
    actor = _manager(request)
    if payload.period_start.day != 1 or payload.period_end != date(
        payload.period_start.year, payload.period_start.month,
        monthrange(payload.period_start.year, payload.period_start.month)[1]
    ):
        raise HTTPException(422, "Payroll calculation currently requires one complete calendar month")
    try:
        with _hr_connection() as conn:
            existing = conn.execute(
                "SELECT id,status FROM hr_payroll_runs WHERE period_start=%s AND period_end=%s FOR UPDATE",
                (payload.period_start, payload.period_end),
            ).fetchone()
            if existing and existing["status"] not in {"draft", "calculated"}:
                raise HTTPException(409, "An approved or paid payroll run cannot be recalculated")
            if existing:
                run_id = existing["id"]
                conn.execute("UPDATE hr_expenses SET reimbursed_in_payroll_id=NULL WHERE reimbursed_in_payroll_id=%s", (run_id,))
                conn.execute("UPDATE hr_payroll_earning_adjustments SET payroll_run_id=NULL WHERE payroll_run_id=%s", (run_id,))
                conn.execute("DELETE FROM hr_payroll_statutory_snapshots WHERE payroll_run_id=%s", (run_id,))
                conn.execute("DELETE FROM hr_payslips WHERE payroll_run_id=%s", (run_id,))
            else:
                run_id = conn.execute(
                    "INSERT INTO hr_payroll_runs(period_start,period_end,created_by_user_id,notes) "
                    "VALUES(%s,%s,%s,%s) RETURNING id",
                    (payload.period_start, payload.period_end, actor, payload.notes),
                ).fetchone()["id"]

            employees = conn.execute(
                "SELECT e.id,COALESCE(sv.basic_salary,e.basic_salary) AS basic_salary,"
                "COALESCE(sv.hra,e.hra) AS hra,"
                "COALESCE(sv.special_allowance,e.special_allowance) AS special_allowance,"
                "COALESCE(sv.other_allowance,e.other_allowance) AS other_allowance,"
                "e.joining_date,e.exit_date FROM hr_employees e "
                "LEFT JOIN LATERAL (SELECT v.basic_salary,v.hra,v.special_allowance,v.other_allowance "
                "FROM hr_employee_salary_versions v WHERE v.employee_id=e.id AND v.status='approved' "
                "AND v.effective_from<=%s AND (v.effective_to IS NULL OR v.effective_to>=%s) "
                "ORDER BY v.effective_from DESC LIMIT 1) sv ON true "
                "WHERE e.status IN ('active','probation','notice_period') "
                "AND e.joining_date<=%s AND (e.exit_date IS NULL OR e.exit_date>=%s) "
                "ORDER BY e.id FOR SHARE OF e",
                (payload.period_end,payload.period_end,payload.period_end,payload.period_start),
            ).fetchall()
            if not employees:
                raise HTTPException(409, "No active employees are eligible for this payroll period")

            gross_total = Decimal("0")
            deduction_total = Decimal("0")
            reimbursement_total = Decimal("0")
            net_total = Decimal("0")
            employer_total = Decimal("0")
            incomplete_employees = []

            for employee in employees:
                reimburse = conn.execute(
                    "SELECT COALESCE(sum(amount),0) AS amount FROM hr_expenses "
                    "WHERE employee_id=%s AND status='approved' AND expense_date BETWEEN %s AND %s "
                    "AND reimbursed_in_payroll_id IS NULL",
                    (employee["id"], payload.period_start, payload.period_end),
                ).fetchone()["amount"]
                active_start = max(payload.period_start, employee["joining_date"])
                active_end = min(payload.period_end, employee["exit_date"] or payload.period_end)
                active_days = (active_end - active_start).days + 1
                month_days = monthrange(payload.period_start.year, payload.period_start.month)[1]
                factor = Decimal(active_days) / Decimal(month_days)
                basic = (Decimal(str(employee["basic_salary"])) * factor).quantize(Decimal("0.01"))
                hra = (Decimal(str(employee["hra"])) * factor).quantize(Decimal("0.01"))
                special = (Decimal(str(employee["special_allowance"])) * factor).quantize(Decimal("0.01"))
                other = (Decimal(str(employee["other_allowance"])) * factor).quantize(Decimal("0.01"))
                fixed_gross = basic + hra + special + other
                earning_rows = conn.execute(
                    "SELECT id,earning_type,amount,hours,hourly_rate,reason "
                    "FROM hr_payroll_earning_adjustments WHERE employee_id=%s AND period_start=%s "
                    "AND period_end=%s AND status='approved' AND payroll_run_id IS NULL "
                    "ORDER BY id FOR UPDATE",
                    (employee["id"],payload.period_start,payload.period_end),
                ).fetchall()
                variable_earnings_total = sum(
                    (Decimal(str(item["amount"])) for item in earning_rows), Decimal("0")
                )
                gross = fixed_gross + variable_earnings_total

                profile = conn.execute(
                    "SELECT * FROM hr_employee_statutory_profiles WHERE employee_id=%s "
                    "AND effective_from<=%s AND (effective_to IS NULL OR effective_to>=%s)",
                    (employee["id"], payload.period_end, payload.period_end),
                ).fetchone()
                statutory_employee = Decimal("0")
                statutory_employer = Decimal("0")
                statutory_breakdown = {}
                if profile is None:
                    incomplete_employees.append({"employee_id": employee["id"], "reason": "missing_employee_statutory_profile"})
                else:
                    policies = conn.execute(
                        "SELECT * FROM hr_statutory_policy_versions WHERE establishment_id=%s "
                        "AND status='approved' AND effective_from<=%s "
                        "AND (effective_to IS NULL OR effective_to>=%s) ORDER BY component,id",
                        (profile["establishment_id"], payload.period_end, payload.period_end),
                    ).fetchall()
                    readiness = assess_policy_readiness(policies, payload.period_end)
                    if not readiness["ready"]:
                        incomplete_employees.append({
                            "employee_id": employee["id"],
                            "reason": "statutory_policy_incomplete",
                            "missing_components": readiness["missing_components"],
                            "duplicate_components": readiness["duplicate_components"],
                        })
                    else:
                        inputs = {
                            "basic": basic, "hra": hra, "special_allowance": special,
                            "other_allowance": other, "gross": gross,
                            "annualized_gross": (
                                Decimal(str(employee["basic_salary"])) + Decimal(str(employee["hra"]))
                                + Decimal(str(employee["special_allowance"])) + Decimal(str(employee["other_allowance"]))
                                + variable_earnings_total / Decimal("12")
                            ),
                            "tds_regime": profile["tds_regime"],
                            "projected_annual_taxable_income": (profile["declarations"] or {}).get("projected_annual_taxable_income"),
                            "applicability": {"pf": profile["pf_applicable_override"], "esi": profile["esi_applicable_override"], "pt": profile["pt_applicable_override"]},
                            "declarations": profile["declarations"],
                            "exemptions": profile["exemptions"],
                            "previous_employer_income": profile["previous_employer_income"],
                        }
                        try:
                            calculated = calculate_statutory_payroll(policies, inputs, payload.period_end)
                        except StatutoryPolicyError as exc:
                            incomplete_employees.append({
                                "employee_id": employee["id"], "reason": "policy_calculation_invalid",
                                "detail": str(exc),
                            })
                        else:
                            statutory_employee = calculated["employee_deductions_total"]
                            statutory_employer = calculated["employer_contributions_total"]
                            statutory_breakdown = {
                                key: {
                                    "employee_amount": str(value["employee_amount"]),
                                    "employer_amount": str(value["employer_amount"]),
                                    "enabled": value["enabled"],
                                    "policy_version_id": value.get("policy_version_id"),
                                    "details": value.get("details", {}),
                                } for key, value in calculated["components"].items()
                            }
                            policy_by_component = {p["component"]: p for p in policies}
                            for component, value in calculated["components"].items():
                                selected = policy_by_component[component]
                                conn.execute(
                                    "INSERT INTO hr_payroll_statutory_snapshots("
                                    "payroll_run_id,employee_id,establishment_id,component,policy_version_id,"
                                    "policy_snapshot,input_snapshot,employee_amount,employer_amount,calculation_details"
                                    ") VALUES(%s,%s,%s,%s,%s,%s::jsonb,%s::jsonb,%s,%s,%s::jsonb)",
                                    (run_id, employee["id"], profile["establishment_id"], component,
                                     selected["id"], __import__("json").dumps(dict(selected), default=str),
                                     __import__("json").dumps(inputs, default=str),
                                     value["employee_amount"], value["employer_amount"],
                                     __import__("json").dumps(value.get("details", {}), default=str)),
                                )

                manual_deduction = Decimal(str(payload.deductions_by_employee.get(employee["id"], Decimal("0"))))
                deduction = manual_deduction + statutory_employee
                if deduction > gross + Decimal(str(reimburse)):
                    raise HTTPException(422, f"Deductions exceed gross earnings for employee {employee['id']}")
                net = gross + Decimal(str(reimburse)) - deduction
                deduction_breakdown = {
                    "manual_deduction": str(manual_deduction),
                    "manual_note": payload.deduction_notes.get(employee["id"], ""),
                    "statutory": statutory_breakdown,
                }
                earnings_breakdown = {
                    "basic": str(basic), "hra": str(hra),
                    "special_allowance": str(special), "other_allowance": str(other),
                    "variable_earnings": [{
                        "type": item["earning_type"], "amount": str(item["amount"]),
                        "hours": str(item["hours"]) if item["hours"] is not None else None,
                        "hourly_rate": str(item["hourly_rate"]) if item["hourly_rate"] is not None else None,
                        "reason": item["reason"],
                    } for item in earning_rows],
                }
                conn.execute(
                    "INSERT INTO hr_payslips(payroll_run_id,employee_id,basic_salary,hra,special_allowance,"
                    "other_allowance,reimbursements,gross_earnings,deductions,net_pay,employer_contributions,"
                    "deduction_breakdown,earnings_breakdown) "
                    "VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s::jsonb,%s::jsonb)",
                    (run_id, employee["id"], basic, hra, special, other, reimburse, gross, deduction, net,
                     statutory_employer, __import__("json").dumps(deduction_breakdown),
                     __import__("json").dumps(earnings_breakdown)),
                )
                if earning_rows:
                    conn.execute(
                        "UPDATE hr_payroll_earning_adjustments SET payroll_run_id=%s WHERE id=ANY(%s)",
                        (run_id,[item["id"] for item in earning_rows]),
                    )
                conn.execute(
                    "UPDATE hr_expenses SET reimbursed_in_payroll_id=%s WHERE employee_id=%s AND status='approved' "
                    "AND expense_date BETWEEN %s AND %s AND reimbursed_in_payroll_id IS NULL",
                    (run_id, employee["id"], payload.period_start, payload.period_end),
                )
                gross_total += gross
                deduction_total += deduction
                reimbursement_total += Decimal(str(reimburse))
                net_total += net
                employer_total += statutory_employer

            conn.execute(
                "UPDATE hr_payroll_runs SET status='calculated',total_gross=%s,total_deductions=%s,"
                "total_reimbursements=%s,total_net=%s,total_employer_contributions=%s,notes=%s,updated_at=now() "
                "WHERE id=%s",
                (gross_total, deduction_total, reimbursement_total, net_total, employer_total, payload.notes, run_id),
            )
            return {
                "id": run_id, "status": "calculated", "employee_count": len(employees),
                "total_gross": gross_total, "total_deductions": deduction_total,
                "total_reimbursements": reimbursement_total, "total_net": net_total,
                "total_employer_contributions": employer_total,
                "statutory_readiness": "incomplete" if incomplete_employees else "ready",
                "incomplete_employees": incomplete_employees,
                "approval_blocked": bool(incomplete_employees),
            }
    except HTTPException:
        raise
    except psycopg.Error as exc:
        raise _db_error(exc) from exc


@router.get("/payroll/runs/{run_id}/payslips")
def list_payslips(run_id:int,request:Request):
    _manager(request)
    try:
        with _hr_connection() as conn:
            return {"items":conn.execute(
                "SELECT p.*,e.employee_code,e.first_name,e.last_name,e.email "
                "FROM hr_payslips p JOIN hr_employees e ON e.id=p.employee_id "
                "WHERE p.payroll_run_id=%s ORDER BY e.employee_code",(run_id,)
            ).fetchall()}
    except psycopg.Error as exc:
        raise _db_error(exc) from exc


@router.get("/payroll/me/payslips")
def my_payslips(request:Request):
    actor=_actor(request)
    try:
        with _hr_connection() as conn:
            employee=_employee(conn,actor)
            return {"items":conn.execute(
                "SELECT p.*,r.period_start,r.period_end,r.status AS payroll_status,"
                "e.employee_code,e.first_name,e.last_name "
                "FROM hr_payslips p JOIN hr_payroll_runs r ON r.id=p.payroll_run_id "
                "JOIN hr_employees e ON e.id=p.employee_id "
                "WHERE p.employee_id=%s AND r.status IN ('approved','paid') ORDER BY r.period_start DESC",
                (employee["id"],)
            ).fetchall()}
    except HTTPException:
        raise
    except psycopg.Error as exc:
        raise _db_error(exc) from exc




def _post_approved_payroll_accrual(conn, run_id: int, actor: tuple[int | None, str | None]) -> dict:
    """Post one balanced payroll accrual journal per legal establishment."""
    run = conn.execute(
        "SELECT id,period_start,period_end,accounting_accrual_voucher_id "
        "FROM hr_payroll_runs WHERE id=%s FOR UPDATE",
        (run_id,),
    ).fetchone()
    if run is None:
        raise HTTPException(404, "Payroll run not found")
    if run["accounting_accrual_voucher_id"]:
        return {"status": "posted", "voucher_id": run["accounting_accrual_voucher_id"]}

    establishments = conn.execute(
        "SELECT DISTINCT e.id,e.code FROM hr_payroll_statutory_snapshots s "
        "JOIN hr_establishments e ON e.id=s.establishment_id "
        "WHERE s.payroll_run_id=%s ORDER BY e.code,e.id",
        (run_id,),
    ).fetchall()
    if not establishments:
        return {"status": "exception", "exception": "No establishment-scoped statutory snapshots exist for this payroll run."}

    source_type = "hr_payroll_accrual"
    event_key = "payroll-approved-v2"
    posted = []
    errors = []
    for establishment in establishments:
        establishment_id = establishment["id"]
        legal_entity_code = establishment["code"]
        existing = conn.execute(
            "SELECT id,accounting_voucher_id,total_amount FROM hr_payroll_accrual_postings "
            "WHERE payroll_run_id=%s AND establishment_id=%s",
            (run_id,establishment_id),
        ).fetchone()
        if existing:
            posted.append({
                "establishment_id": establishment_id,
                "legal_entity_code": legal_entity_code,
                "voucher_id": existing["accounting_voucher_id"],
                "total_amount": existing["total_amount"],
            })
            continue

        source_id = f"{run_id}:{establishment_id}"
        try:
            totals = conn.execute(
                "SELECT COALESCE(sum(p.gross_earnings),0) AS gross,"
                "COALESCE(sum(p.reimbursements),0) AS reimbursements,"
                "COALESCE(sum(p.net_pay),0) AS net_pay,"
                "COALESCE(sum(COALESCE((p.deduction_breakdown->>'manual_deduction')::numeric,0)),0) AS manual_deductions "
                "FROM hr_payslips p WHERE p.payroll_run_id=%s AND EXISTS ("
                "SELECT 1 FROM hr_payroll_statutory_snapshots s WHERE s.payroll_run_id=p.payroll_run_id "
                "AND s.employee_id=p.employee_id AND s.establishment_id=%s)",
                (run_id,establishment_id),
            ).fetchone()
            statutory_rows = conn.execute(
                "SELECT component,COALESCE(sum(employee_amount),0) AS employee_amount,"
                "COALESCE(sum(employer_amount),0) AS employer_amount "
                "FROM hr_payroll_statutory_snapshots WHERE payroll_run_id=%s AND establishment_id=%s "
                "GROUP BY component",
                (run_id,establishment_id),
            ).fetchall()
            statutory_employee = {row["component"]: row["employee_amount"] for row in statutory_rows}
            statutory_employer = {row["component"]: row["employer_amount"] for row in statutory_rows}
            mappings = conn.execute(
                "SELECT * FROM accounting_event_account_mappings WHERE legal_entity_code=%s "
                "AND source_module='hr' AND event_type='payroll_accrual' AND status='approved' "
                "AND effective_from<=%s AND (effective_to IS NULL OR effective_to>=%s)",
                (legal_entity_code,run["period_end"],run["period_end"]),
            ).fetchall()
            lines = build_payroll_accrual_lines(
                gross=totals["gross"], reimbursements=totals["reimbursements"],
                net_pay=totals["net_pay"], manual_deductions=totals["manual_deductions"],
                statutory_employee=statutory_employee, statutory_employer=statutory_employer,
                mappings=mappings, legal_entity_code=legal_entity_code, event_date=run["period_end"],
            )
            debit_total = sum((Decimal(str(line["debit"])) for line in lines), Decimal("0.00"))
            header = {
                "voucher_type": "journal", "voucher_date": run["period_end"],
                "narration": f"Payroll accrual for {run['period_start']} to {run['period_end']} · {legal_entity_code}",
                "reference": f"HR-PAYROLL-{run_id}-{legal_entity_code}", "party_type": "other",
                "party_name": f"Payroll {legal_entity_code}", "total_amount": debit_total,
                "source_type": source_type, "source_id": source_id,
                "idempotency_key": f"hr-payroll-accrual:{run_id}:{establishment_id}",
            }
            with conn.transaction():
                voucher_id = _post_voucher(conn, header, lines, actor)
            conn.execute(
                "INSERT INTO hr_payroll_accrual_postings(payroll_run_id,establishment_id,accounting_voucher_id,total_amount) "
                "VALUES(%s,%s,%s,%s)",
                (run_id,establishment_id,voucher_id,debit_total),
            )
            conn.execute(
                "INSERT INTO accounting_posting_exceptions(source_module,source_type,source_id,event_key,event_date,"
                "status,voucher_id,attempts,last_attempt_at,updated_at) "
                "VALUES('hr',%s,%s,%s,%s,'posted',%s,1,now(),now()) "
                "ON CONFLICT(source_module,source_type,source_id,event_key) DO UPDATE SET "
                "status='posted',voucher_id=EXCLUDED.voucher_id,exception_code=NULL,exception_message=NULL,"
                "attempts=accounting_posting_exceptions.attempts+1,last_attempt_at=now(),updated_at=now()",
                (source_type,source_id,event_key,run["period_end"],voucher_id),
            )
            posted.append({
                "establishment_id": establishment_id,
                "legal_entity_code": legal_entity_code,
                "voucher_id": voucher_id,
                "total_amount": debit_total,
            })
        except (PostingConfigurationError, HTTPException) as exc:
            code = "mapping_or_balance_error" if isinstance(exc, PostingConfigurationError) else "accounting_posting_rejected"
            message = str(exc) if isinstance(exc, PostingConfigurationError) else str(exc.detail)
            conn.execute(
                "INSERT INTO accounting_posting_exceptions(source_module,source_type,source_id,event_key,event_date,"
                "status,exception_code,exception_message,attempts,last_attempt_at,updated_at) "
                "VALUES('hr',%s,%s,%s,%s,'exception',%s,%s,1,now(),now()) "
                "ON CONFLICT(source_module,source_type,source_id,event_key) DO UPDATE SET "
                "status='exception',exception_code=EXCLUDED.exception_code,exception_message=EXCLUDED.exception_message,"
                "attempts=accounting_posting_exceptions.attempts+1,last_attempt_at=now(),updated_at=now()",
                (source_type,source_id,event_key,run["period_end"],code,message[:2000]),
            )
            errors.append({"establishment_id": establishment_id, "legal_entity_code": legal_entity_code, "exception": message})

    if len(establishments) == 1 and len(posted) == 1 and not errors:
        conn.execute(
            "UPDATE hr_payroll_runs SET accounting_accrual_voucher_id=%s,updated_at=now() WHERE id=%s",
            (posted[0]["voucher_id"],run_id),
        )
    if errors:
        return {"status": "exception", "posted": posted, "errors": errors}
    return {"status": "posted", "postings": posted}


@router.post("/payroll/runs/{run_id}/approve")
def approve_payroll(run_id:int,payload:PayrollApprovalInput,request:Request):
    actor=_manager(request)
    try:
        with _hr_connection() as conn:
            run = conn.execute(
                "SELECT id,status,period_start,period_end,created_by_user_id FROM hr_payroll_runs WHERE id=%s FOR UPDATE",
                (run_id,),
            ).fetchone()
            if run is None or run["status"] != "calculated":
                raise HTTPException(409, "Payroll run is not in a reviewable calculated state")
            _require_independent_reviewer(run["created_by_user_id"], actor, "payroll run")
            if payload.decision=="rejected":
                row=conn.execute(
                    "UPDATE hr_payroll_runs SET status='draft',notes=concat_ws(E'\\n',notes,%s),updated_at=now() "
                    "WHERE id=%s AND status='calculated' RETURNING id,status",
                    (payload.note,run_id),
                ).fetchone()
            else:
                pending_earnings = conn.execute(
                    "SELECT count(*) AS total FROM hr_payroll_earning_adjustments "
                    "WHERE period_start=%s AND period_end=%s AND status='pending'",
                    (run["period_start"],run["period_end"]),
                ).fetchone()["total"]
                if pending_earnings:
                    raise HTTPException(
                        409,
                        f"Payroll approval blocked: {pending_earnings} variable earning item(s) "
                        "are still awaiting review for this period."
                    )
                incomplete = conn.execute(
                    "SELECT e.employee_code, count(s.id) AS snapshot_count "
                    "FROM hr_payslips p JOIN hr_employees e ON e.id=p.employee_id "
                    "LEFT JOIN hr_payroll_statutory_snapshots s "
                    "ON s.payroll_run_id=p.payroll_run_id AND s.employee_id=p.employee_id "
                    "WHERE p.payroll_run_id=%s GROUP BY e.employee_code "
                    "HAVING count(s.id)<>4 ORDER BY e.employee_code",
                    (run_id,),
                ).fetchall()
                if incomplete:
                    codes = ", ".join(row["employee_code"] for row in incomplete)
                    raise HTTPException(
                        409,
                        "Payroll approval blocked: approved PF, ESI, PT and TDS policy snapshots "
                        f"are not complete for employees: {codes}. Complete employee statutory profiles "
                        "and establishment policies, then recalculate the draft payroll."
                    )
                row=conn.execute(
                    "UPDATE hr_payroll_runs SET status='approved',approved_by_user_id=%s,approved_at=now(),"
                    "updated_at=now() WHERE id=%s AND status='calculated' RETURNING id,status,total_net,"
                    "total_employer_contributions",
                    (actor,run_id),
                ).fetchone()
            if row is None:
                raise HTTPException(409,"Payroll run is not in a reviewable calculated state")
            posting = {"status": "not_applicable"}
            if payload.decision != "rejected":
                posting = _post_approved_payroll_accrual(conn, run_id, _accounting_actor(request))
            return {**row, "accounting_accrual": posting}
    except HTTPException:
        raise
    except psycopg.Error as exc:
        raise _db_error(exc) from exc



@router.post("/payroll/runs/{run_id}/accounting/retry")
def retry_payroll_accounting_posting(run_id: int, request: Request):
    """Retry an approved payroll accrual after Finance resolves its mapping exception."""
    actor = _manager(request)
    try:
        with _hr_connection() as conn:
            run = conn.execute(
                "SELECT id,status FROM hr_payroll_runs WHERE id=%s FOR UPDATE", (run_id,)
            ).fetchone()
            if run is None:
                raise HTTPException(404, "Payroll run not found")
            if run["status"] not in {"approved", "paid"}:
                raise HTTPException(409, "Only an approved or paid payroll run can retry its accrual posting")
            return _post_approved_payroll_accrual(conn, run_id, _accounting_actor(request))
    except HTTPException:
        raise
    except psycopg.Error as exc:
        raise _db_error(exc) from exc


@router.post("/payroll/runs/{run_id}/pay")
def mark_payroll_paid(run_id:int,payload:PayrollPaymentInput,request:Request):
    actor=_manager(request)
    try:
        with _hr_connection() as conn:
            run=conn.execute("SELECT id,status,total_net,accounting_voucher_id FROM hr_payroll_runs WHERE id=%s FOR UPDATE",(run_id,)).fetchone()
            if run is None:
                raise HTTPException(404,"Payroll run not found")
            if run["status"]=="paid" and run["accounting_voucher_id"]==payload.accounting_voucher_id:
                return {"id":run_id,"status":"paid","accounting_voucher_id":payload.accounting_voucher_id}
            if run["status"]!="approved":
                raise HTTPException(409,"Only an approved payroll run can be marked paid")
            voucher=conn.execute(
                "SELECT id,voucher_type,status,total_amount FROM accounting_vouchers WHERE id=%s FOR UPDATE",
                (payload.accounting_voucher_id,),
            ).fetchone()
            if not voucher or voucher["status"]!="posted" or voucher["voucher_type"]!="payment":
                raise HTTPException(422,"Payroll must reference an already-posted Accounting payment voucher")
            if Decimal(str(voucher["total_amount"])) != Decimal(str(run["total_net"])):
                raise HTTPException(409,"Accounting payment voucher amount must equal the payroll net total")
            used=conn.execute(
                "SELECT id FROM hr_payroll_runs WHERE accounting_voucher_id=%s AND id<>%s",
                (payload.accounting_voucher_id,run_id),
            ).fetchone()
            if used:
                raise HTTPException(409,"This Accounting payment voucher is already linked to another payroll run")
            row=conn.execute(
                "UPDATE hr_payroll_runs SET status='paid',accounting_voucher_id=%s,paid_at=now(),updated_at=now() "
                "WHERE id=%s RETURNING id,status,accounting_voucher_id,paid_at",
                (payload.accounting_voucher_id,run_id),
            ).fetchone()
            conn.execute("UPDATE hr_expenses SET status='reimbursed' WHERE reimbursed_in_payroll_id=%s",(run_id,))
            return row
    except HTTPException:
        raise
    except psycopg.Error as exc:
        raise _db_error(exc) from exc


class EstablishmentInput(BaseModel):
    code: str = Field(min_length=2, max_length=32)
    legal_name: str = Field(min_length=2, max_length=200)
    display_name: str = Field(min_length=2, max_length=120)
    state_code: str = Field(pattern="^[A-Z]{2}$")
    address: dict[str, Any] = Field(default_factory=dict)
    registrations: dict[str, Any] = Field(default_factory=dict)


class StatutoryPolicyInput(BaseModel):
    establishment_id: int = Field(gt=0)
    component: str = Field(pattern="^(pf|esi|pt|tds)$")
    version_label: str = Field(min_length=2, max_length=100)
    effective_from: date
    effective_to: date | None = None
    policy_config: dict[str, Any]
    source_references: list[dict[str, Any]] = Field(default_factory=list)
    review_due_on: date | None = None

    @model_validator(mode="after")
    def valid_period(self):
        if self.effective_to and self.effective_to < self.effective_from:
            raise ValueError("Policy end date cannot precede its start date")
        return self


class EmployeeStatutoryProfileInput(BaseModel):
    establishment_id: int = Field(gt=0)
    uan: str | None = Field(default=None, max_length=32)
    esic_number: str | None = Field(default=None, max_length=32)
    pan: str | None = Field(default=None, max_length=10)
    tds_regime: str | None = Field(default=None, pattern="^(old|new)$")
    pf_applicable_override: bool | None = None
    esi_applicable_override: bool | None = None
    pt_applicable_override: bool | None = None
    override_reason: str | None = Field(default=None, max_length=1000)
    declarations: dict[str, Any] = Field(default_factory=dict)
    exemptions: dict[str, Any] = Field(default_factory=dict)
    previous_employer_income: dict[str, Any] = Field(default_factory=dict)
    effective_from: date
    effective_to: date | None = None

    @model_validator(mode="after")
    def require_override_reason(self):
        if any(value is not None for value in (self.pf_applicable_override,self.esi_applicable_override,self.pt_applicable_override)) and not (self.override_reason or "").strip():
            raise ValueError("An employee statutory applicability override requires a reason")
        return self


@router.get("/establishments")
def list_hr_establishments(request: Request):
    _manager(request)
    try:
        with _hr_connection() as conn:
            return {"items": conn.execute(
                "SELECT * FROM hr_establishments ORDER BY display_name"
            ).fetchall()}
    except psycopg.Error as exc:
        raise _db_error(exc) from exc


@router.post("/establishments", status_code=201)
def create_hr_establishment(payload: EstablishmentInput, request: Request):
    actor = _manager(request)
    try:
        with _hr_connection() as conn:
            return conn.execute(
                "INSERT INTO hr_establishments(code,legal_name,display_name,state_code,address,registrations,created_by_user_id) "
                "VALUES(%s,%s,%s,%s,%s::jsonb,%s::jsonb,%s) "
                "RETURNING id,code,legal_name,display_name,state_code,address,registrations,is_active,created_at",
                (payload.code.strip(),payload.legal_name.strip(),payload.display_name.strip(),payload.state_code,
                 __import__("json").dumps(payload.address),__import__("json").dumps(payload.registrations),actor),
            ).fetchone()
    except psycopg.Error as exc:
        raise _db_error(exc) from exc


@router.put("/establishments/{establishment_id}")
def update_hr_establishment(establishment_id: int, payload: EstablishmentInput, request: Request):
    _manager(request)
    try:
        with _hr_connection() as conn:
            row=conn.execute(
                "UPDATE hr_establishments SET code=%s,legal_name=%s,display_name=%s,state_code=%s,"
                "address=%s::jsonb,registrations=%s::jsonb,updated_at=now() WHERE id=%s "
                "RETURNING id,code,legal_name,display_name,state_code,address,registrations,is_active,updated_at",
                (payload.code.strip(),payload.legal_name.strip(),payload.display_name.strip(),payload.state_code,
                 __import__("json").dumps(payload.address),__import__("json").dumps(payload.registrations),establishment_id),
            ).fetchone()
            if row is None:
                raise HTTPException(404,"Establishment not found")
            return row
    except HTTPException:
        raise
    except psycopg.Error as exc:
        raise _db_error(exc) from exc


@router.post("/establishments/{establishment_id}/deactivate")
def deactivate_hr_establishment(establishment_id: int, request: Request):
    _manager(request)
    try:
        with _hr_connection() as conn:
            in_use=conn.execute(
                "SELECT EXISTS(SELECT 1 FROM hr_employee_statutory_profiles WHERE establishment_id=%s) "
                "OR EXISTS(SELECT 1 FROM hr_statutory_policy_versions WHERE establishment_id=%s AND status IN ('draft','in_review')) AS in_use",
                (establishment_id,establishment_id),
            ).fetchone()["in_use"]
            if in_use:
                raise HTTPException(409,"This establishment has employee compliance profiles or pending policies; it cannot be deactivated.")
            row=conn.execute(
                "UPDATE hr_establishments SET is_active=false,updated_at=now() WHERE id=%s AND is_active=true "
                "RETURNING id,code,display_name,is_active",(establishment_id,)
            ).fetchone()
            if row is None:
                raise HTTPException(404,"Active establishment not found")
            return row
    except HTTPException:
        raise
    except psycopg.Error as exc:
        raise _db_error(exc) from exc


@router.get("/statutory/policies")
def list_statutory_policies(request: Request, establishment_id: int | None = Query(default=None, gt=0)):
    _manager(request)
    try:
        with _hr_connection() as conn:
            return {"items": conn.execute(
                "SELECT p.*,e.code AS establishment_code,e.display_name,e.state_code "
                "FROM hr_statutory_policy_versions p JOIN hr_establishments e ON e.id=p.establishment_id "
                "WHERE (%s::bigint IS NULL OR p.establishment_id=%s::bigint) ORDER BY p.effective_from DESC,p.component",
                (establishment_id,establishment_id),
            ).fetchall()}
    except psycopg.Error as exc:
        raise _db_error(exc) from exc


@router.post("/statutory/policies", status_code=201)
def create_statutory_policy(payload: StatutoryPolicyInput, request: Request):
    actor = _manager(request)
    try:
        with _hr_connection() as conn:
            row = conn.execute(
                "INSERT INTO hr_statutory_policy_versions(establishment_id,component,version_label,effective_from,"
                "effective_to,policy_config,source_references,review_due_on,created_by_user_id) "
                "VALUES(%s,%s,%s,%s,%s,%s::jsonb,%s::jsonb,%s,%s) "
                "RETURNING *",
                (payload.establishment_id,payload.component,payload.version_label.strip(),payload.effective_from,
                 payload.effective_to,__import__("json").dumps(payload.policy_config),
                 __import__("json").dumps(payload.source_references),payload.review_due_on,actor),
            ).fetchone()
            conn.execute(
                "INSERT INTO hr_statutory_audit_events(establishment_id,policy_version_id,event_type,reason,after_state,actor_user_id) "
                "VALUES(%s,%s,'policy_created','Policy version created',%s::jsonb,%s)",
                (payload.establishment_id,row["id"],__import__("json").dumps({"status":"draft","component":payload.component}),actor),
            )
            return row
    except psycopg.Error as exc:
        raise _db_error(exc) from exc


@router.post("/statutory/policies/{policy_id}/submit")
def submit_statutory_policy(policy_id: int, request: Request):
    actor = _manager(request)
    try:
        with _hr_connection() as conn:
            row = conn.execute(
                "UPDATE hr_statutory_policy_versions SET status='in_review',submitted_by_user_id=%s,updated_at=now() "
                "WHERE id=%s AND status='draft' RETURNING id,establishment_id,component,status",
                (actor,policy_id),
            ).fetchone()
            if row is None:
                raise HTTPException(409,"Only a draft statutory policy can be submitted")
            conn.execute(
                "INSERT INTO hr_statutory_audit_events(establishment_id,policy_version_id,event_type,reason,after_state,actor_user_id) "
                "VALUES(%s,%s,'policy_submitted','Policy submitted for approval',%s::jsonb,%s)",
                (row["establishment_id"],policy_id,__import__("json").dumps({"status":"in_review"}),actor),
            )
            return row
    except HTTPException:
        raise
    except psycopg.Error as exc:
        raise _db_error(exc) from exc


@router.post("/statutory/policies/{policy_id}/approve")
def approve_statutory_policy(policy_id: int, request: Request):
    actor = _manager(request)
    try:
        with _hr_connection() as conn:
            policy = conn.execute(
                "SELECT * FROM hr_statutory_policy_versions WHERE id=%s FOR UPDATE",(policy_id,)
            ).fetchone()
            if policy is None or policy["status"] != "in_review":
                raise HTTPException(409,"Only a policy in review can be approved")
            _require_independent_reviewer(policy["submitted_by_user_id"], actor, "statutory policy")
            overlap = conn.execute(
                "SELECT id FROM hr_statutory_policy_versions WHERE establishment_id=%s AND component=%s "
                "AND status='approved' AND id<>%s AND daterange(effective_from,COALESCE(effective_to,'infinity'::date),'[]') "
                "&& daterange(%s,COALESCE(%s,'infinity'::date),'[]') LIMIT 1",
                (policy["establishment_id"],policy["component"],policy_id,policy["effective_from"],policy["effective_to"]),
            ).fetchone()
            if overlap:
                raise HTTPException(409,"Another approved policy overlaps this component's effective period")
            row = conn.execute(
                "UPDATE hr_statutory_policy_versions SET status='approved',approved_by_user_id=%s,"
                "approved_at=now(),updated_at=now() WHERE id=%s RETURNING id,establishment_id,component,status,approved_at",
                (actor,policy_id),
            ).fetchone()
            conn.execute(
                "INSERT INTO hr_statutory_audit_events(establishment_id,policy_version_id,event_type,reason,after_state,actor_user_id) "
                "VALUES(%s,%s,'policy_approved','Policy version approved',%s::jsonb,%s)",
                (policy["establishment_id"],policy_id,__import__("json").dumps({"status":"approved"}),actor),
            )
            return row
    except HTTPException:
        raise
    except psycopg.Error as exc:
        raise _db_error(exc) from exc


@router.put("/employees/{employee_id}/statutory-profile")
def upsert_employee_statutory_profile(employee_id: int, payload: EmployeeStatutoryProfileInput, request: Request):
    actor = _manager(request)
    if payload.effective_to and payload.effective_to < payload.effective_from:
        raise HTTPException(422,"Profile end date cannot precede its start date")
    try:
        with _hr_connection() as conn:
            employee = conn.execute("SELECT id FROM hr_employees WHERE id=%s",(employee_id,)).fetchone()
            if employee is None:
                raise HTTPException(404,"Employee not found")
            row = conn.execute(
                "INSERT INTO hr_employee_statutory_profiles(employee_id,establishment_id,uan,esic_number,pan,"
                "tds_regime,pf_applicable_override,esi_applicable_override,pt_applicable_override,override_reason,declarations,"
                "exemptions,previous_employer_income,effective_from,effective_to,updated_by_user_id) "
                "VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s::jsonb,%s::jsonb,%s::jsonb,%s,%s,%s) "
                "ON CONFLICT(employee_id) DO UPDATE SET establishment_id=EXCLUDED.establishment_id,uan=EXCLUDED.uan,"
                "esic_number=EXCLUDED.esic_number,pan=EXCLUDED.pan,tds_regime=EXCLUDED.tds_regime,"
                "pf_applicable_override=EXCLUDED.pf_applicable_override,esi_applicable_override=EXCLUDED.esi_applicable_override,"
                "pt_applicable_override=EXCLUDED.pt_applicable_override,override_reason=EXCLUDED.override_reason,declarations=EXCLUDED.declarations,"
                "exemptions=EXCLUDED.exemptions,previous_employer_income=EXCLUDED.previous_employer_income,"
                "effective_from=EXCLUDED.effective_from,effective_to=EXCLUDED.effective_to,"
                "updated_by_user_id=EXCLUDED.updated_by_user_id,updated_at=now() RETURNING *",
                (employee_id,payload.establishment_id,payload.uan,payload.esic_number,payload.pan,payload.tds_regime,
                 payload.pf_applicable_override,payload.esi_applicable_override,payload.pt_applicable_override,
                 payload.override_reason,__import__("json").dumps(payload.declarations),__import__("json").dumps(payload.exemptions),
                 __import__("json").dumps(payload.previous_employer_income),payload.effective_from,payload.effective_to,actor),
            ).fetchone()
            conn.execute(
                "INSERT INTO hr_statutory_audit_events(establishment_id,employee_id,event_type,reason,after_state,actor_user_id) "
                "VALUES(%s,%s,'employee_profile_updated','Employee statutory profile updated',%s::jsonb,%s)",
                (payload.establishment_id,employee_id,__import__("json").dumps({"tds_regime":payload.tds_regime}),actor),
            )
            return row
    except HTTPException:
        raise
    except psycopg.Error as exc:
        raise _db_error(exc) from exc


class RemittanceGenerationInput(BaseModel):
    due_dates_by_component: dict[str, date] = Field(default_factory=dict)

class RemittanceFileInput(BaseModel):
    challan_reference: str = Field(min_length=2, max_length=120)

@router.get("/employees/{employee_id}/statutory-profile")
def get_employee_statutory_profile(employee_id: int, request: Request):
    _manager(request)
    try:
        with _hr_connection() as conn:
            row = conn.execute(
                "SELECT * FROM hr_employee_statutory_profiles WHERE employee_id=%s", (employee_id,)
            ).fetchone()
            if row is None:
                raise HTTPException(404, "Employee statutory profile not found")
            return row
    except HTTPException:
        raise
    except psycopg.Error as exc:
        raise _db_error(exc) from exc


@router.get("/statutory/remittances")
def list_statutory_remittances(request: Request, establishment_id: int | None = Query(default=None, gt=0), status: str | None = Query(default=None, pattern="^(pending|paid|filed)$")):
    _manager(request)
    try:
        with _hr_connection() as conn:
            return {"items": conn.execute(
                "SELECT r.*,e.display_name,e.state_code,pr.period_start AS payroll_period_start,pr.period_end AS payroll_period_end "
                "FROM hr_statutory_remittances r JOIN hr_establishments e ON e.id=r.establishment_id "
                "JOIN hr_payroll_runs pr ON pr.id=r.payroll_run_id "
                "WHERE (%s::bigint IS NULL OR r.establishment_id=%s::bigint) AND (%s::text IS NULL OR r.status=%s::text) "
                "ORDER BY r.due_date NULLS LAST,r.period_end DESC,r.component",
                (establishment_id,establishment_id,status,status),
            ).fetchall()}
    except psycopg.Error as exc:
        raise _db_error(exc) from exc

@router.post("/payroll/runs/{run_id}/statutory-remittances", status_code=201)
def generate_statutory_remittances(run_id: int, payload: RemittanceGenerationInput, request: Request):
    actor = _manager(request)
    try:
        with _hr_connection() as conn:
            run = conn.execute("SELECT * FROM hr_payroll_runs WHERE id=%s FOR SHARE", (run_id,)).fetchone()
            if run is None:
                raise HTTPException(404, "Payroll run not found")
            if run["status"] not in {"approved", "paid"}:
                raise HTTPException(409, "Approve payroll before generating statutory remittances")
            totals = conn.execute(
                "SELECT establishment_id,component,sum(employee_amount) AS employee_amount,"
                "sum(employer_amount) AS employer_amount FROM hr_payroll_statutory_snapshots "
                "WHERE payroll_run_id=%s GROUP BY establishment_id,component ORDER BY establishment_id,component",
                (run_id,),
            ).fetchall()
            if not totals:
                raise HTTPException(409, "No statutory payroll snapshots are available for remittance")
            items = []
            for item in totals:
                employee_amount = item["employee_amount"] or Decimal("0")
                employer_amount = item["employer_amount"] or Decimal("0")
                row = conn.execute(
                    "INSERT INTO hr_statutory_remittances(payroll_run_id,establishment_id,component,period_start,period_end,"
                    "due_date,employee_amount,employer_amount,total_amount,created_by_user_id) "
                    "VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) "
                    "ON CONFLICT(payroll_run_id,establishment_id,component) DO NOTHING RETURNING *",
                    (run_id,item["establishment_id"],item["component"],run["period_start"],run["period_end"],
                     payload.due_dates_by_component.get(item["component"]),employee_amount,employer_amount,
                     employee_amount+employer_amount,actor),
                ).fetchone()
                if row is None:
                    row = conn.execute(
                        "SELECT * FROM hr_statutory_remittances WHERE payroll_run_id=%s AND establishment_id=%s AND component=%s",
                        (run_id,item["establishment_id"],item["component"]),
                    ).fetchone()
                items.append(row)
            return {"items": items}
    except HTTPException:
        raise
    except psycopg.Error as exc:
        raise _db_error(exc) from exc

@router.post("/statutory/remittances/{remittance_id}/pay")
def pay_statutory_remittance(remittance_id: int, payload: PayrollPaymentInput, request: Request):
    actor = _manager(request)
    try:
        with _hr_connection() as conn:
            item = conn.execute("SELECT * FROM hr_statutory_remittances WHERE id=%s FOR UPDATE", (remittance_id,)).fetchone()
            if item is None:
                raise HTTPException(404, "Statutory remittance not found")
            if item["status"] == "paid" and item["payment_voucher_id"] == payload.accounting_voucher_id:
                return item
            if item["status"] != "pending":
                raise HTTPException(409, "Only a pending statutory remittance can be paid")
            voucher = conn.execute(
                "SELECT id,voucher_type,status,total_amount FROM accounting_vouchers WHERE id=%s FOR SHARE",
                (payload.accounting_voucher_id,),
            ).fetchone()
            if not voucher or voucher["status"] != "posted" or voucher["voucher_type"] != "payment":
                raise HTTPException(422, "Remittance requires an already-posted Accounting payment voucher")
            if Decimal(str(voucher["total_amount"])) != Decimal(str(item["total_amount"])):
                raise HTTPException(409, "Accounting payment voucher amount must equal the remittance total")
            used = conn.execute(
                "SELECT id FROM hr_payroll_runs WHERE accounting_voucher_id=%s "
                "UNION ALL SELECT id FROM hr_statutory_remittances WHERE payment_voucher_id=%s AND id<>%s LIMIT 1",
                (payload.accounting_voucher_id,payload.accounting_voucher_id,remittance_id),
            ).fetchone()
            if used:
                raise HTTPException(409, "This Accounting payment voucher is already linked to another payroll obligation")
            row = conn.execute(
                "UPDATE hr_statutory_remittances SET status='paid',payment_voucher_id=%s,paid_at=now(),updated_at=now() "
                "WHERE id=%s AND status='pending' RETURNING *",
                (payload.accounting_voucher_id,remittance_id),
            ).fetchone()
            conn.execute(
                "INSERT INTO hr_statutory_audit_events(establishment_id,payroll_run_id,event_type,reason,after_state,actor_user_id) "
                "VALUES(%s,%s,'remittance_paid','Statutory remittance linked to posted payment voucher',%s::jsonb,%s)",
                (item["establishment_id"],item["payroll_run_id"],__import__("json").dumps({"remittance_id":remittance_id,"voucher_id":payload.accounting_voucher_id}),actor),
            )
            return row
    except HTTPException:
        raise
    except psycopg.Error as exc:
        raise _db_error(exc) from exc

@router.post("/statutory/remittances/{remittance_id}/file")
def file_statutory_remittance(remittance_id: int, payload: RemittanceFileInput, request: Request):
    actor = _manager(request)
    try:
        with _hr_connection() as conn:
            item = conn.execute("SELECT * FROM hr_statutory_remittances WHERE id=%s FOR UPDATE", (remittance_id,)).fetchone()
            if item is None:
                raise HTTPException(404, "Statutory remittance not found")
            if item["status"] != "paid":
                raise HTTPException(409, "Pay the statutory remittance before recording the challan filing")
            row = conn.execute(
                "UPDATE hr_statutory_remittances SET status='filed',challan_reference=%s,filed_at=now(),updated_at=now() "
                "WHERE id=%s AND status='paid' RETURNING *",
                (payload.challan_reference.strip(),remittance_id),
            ).fetchone()
            conn.execute(
                "INSERT INTO hr_statutory_audit_events(establishment_id,payroll_run_id,event_type,reason,after_state,actor_user_id) "
                "VALUES(%s,%s,'remittance_filed','Statutory challan filing recorded',%s::jsonb,%s)",
                (item["establishment_id"],item["payroll_run_id"],__import__("json").dumps({"remittance_id":remittance_id,"challan_reference":payload.challan_reference.strip()}),actor),
            )
            return row
    except HTTPException:
        raise
    except psycopg.Error as exc:
        raise _db_error(exc) from exc


# Additive HR workforce planning, leave ledger and employee lifecycle workflows.
class AttendancePolicyInput(BaseModel):
    establishment_id: int = Field(gt=0)
    grace_minutes: int = Field(default=0, ge=0, le=240)
    break_minutes: int = Field(default=0, ge=0, le=720)
    geofence_enabled: bool = False
    geofence_enforced: bool = False
    require_location_on_clock_in: bool = False
    require_location_on_clock_out: bool = False
    effective_from: date
    effective_to: date | None = None

    @model_validator(mode="after")
    def validate_policy(self):
        if self.effective_to and self.effective_to < self.effective_from:
            raise ValueError("Attendance policy end date cannot precede its start date")
        if self.geofence_enforced and not self.geofence_enabled:
            raise ValueError("Geofence enforcement requires geofencing to be enabled")
        if (self.require_location_on_clock_in or self.require_location_on_clock_out) and not self.geofence_enabled:
            raise ValueError("Required GPS capture needs geofencing to be enabled")
        return self


class AttendanceWorkLocationInput(BaseModel):
    establishment_id: int = Field(gt=0)
    code: str = Field(min_length=2, max_length=32)
    name: str = Field(min_length=2, max_length=120)
    latitude: float = Field(ge=-90, le=90)
    longitude: float = Field(ge=-180, le=180)
    radius_meters: int = Field(ge=10, le=10000)

    @field_validator("code", "name")
    @classmethod
    def trim_location_text(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Work location code and name cannot be blank")
        return value


class AttendanceWorkLocationStatusInput(BaseModel):
    is_active: bool


class ShiftDefinitionInput(BaseModel):
    establishment_id: int = Field(gt=0)
    code: str = Field(min_length=2, max_length=32)
    name: str = Field(min_length=2, max_length=120)
    local_start_time: str
    local_end_time: str
    break_minutes: int = Field(default=0, ge=0, le=720)
    timezone: str = Field(default="Asia/Kolkata", min_length=3, max_length=64)
    effective_from: date
    effective_to: date | None = None

    @field_validator("timezone")
    @classmethod
    def valid_timezone(cls, value: str) -> str:
        try:
            ZoneInfo(value)
        except (ZoneInfoNotFoundError, ValueError) as exc:
            raise ValueError("Timezone must be a valid IANA timezone") from exc
        return value

    @field_validator("code", "name")
    @classmethod
    def trim_shift_text(cls, value: str) -> str:
        value=value.strip()
        if not value:
            raise ValueError("Shift code and name cannot be blank")
        return value

    @model_validator(mode="after")
    def validate_period(self):
        if self.effective_to and self.effective_to < self.effective_from:
            raise ValueError("Shift end date cannot precede its start date")
        return self


class ShiftAssignmentInput(BaseModel):
    employee_id: int = Field(gt=0)
    shift_definition_id: int = Field(gt=0)
    work_date: date
    planned_start_at: datetime
    planned_end_at: datetime

    @model_validator(mode="after")
    def ordered_shift_timestamps(self):
        if self.planned_start_at.tzinfo is None or self.planned_end_at.tzinfo is None:
            raise ValueError("Planned shift timestamps must include a timezone offset")
        if self.planned_end_at <= self.planned_start_at:
            raise ValueError("Planned shift end must be after its start")
        if self.planned_start_at.date() != self.work_date:
            raise ValueError("Planned shift start date must match the roster work date")
        return self


class HolidayCalendarInput(BaseModel):
    establishment_id: int = Field(gt=0)
    name: str = Field(min_length=2, max_length=120)
    region_code: str | None = Field(default=None, max_length=32)
    effective_year: int = Field(ge=2000, le=2200)

    @field_validator("region_code")
    @classmethod
    def normalise_region(cls, value):
        return value.strip().upper() if value else None


class HolidayInput(BaseModel):
    holiday_date: date
    name: str = Field(min_length=2, max_length=160)
    holiday_type: str = Field(default="public", pattern="^(public|national|regional|optional|company)$")
    location_code: str | None = Field(default=None, max_length=32)
    is_paid: bool = True


class LeavePolicyInput(BaseModel):
    establishment_id: int = Field(gt=0)
    leave_type: str = Field(pattern="^(annual|sick|casual|unpaid|other)$")
    version_label: str = Field(min_length=2, max_length=80)
    effective_from: date
    effective_to: date | None = None
    entitlement_days: Decimal = Field(default=Decimal("0"), ge=0, max_digits=7, decimal_places=2)
    accrual_frequency: str = Field(default="none", pattern="^(none|monthly|quarterly|yearly)$")
    carry_forward_cap: Decimal = Field(default=Decimal("0"), ge=0, max_digits=7, decimal_places=2)
    allow_negative_balance: bool = False
    encashment_allowed: bool = False
    probation_eligible: bool = False
    day_count_basis: str = Field(default="calendar", pattern="^(calendar|working)$")
    policy_notes: str | None = Field(default=None, max_length=1000)

    @model_validator(mode="after")
    def validate_period(self):
        if self.effective_to and self.effective_to < self.effective_from:
            raise ValueError("Leave policy end date cannot precede its start date")
        return self


class LeaveBalanceAdjustmentInput(BaseModel):
    employee_id: int = Field(gt=0)
    leave_type: str = Field(pattern="^(annual|sick|casual|unpaid|other)$")
    quantity_days: Decimal
    effective_date: date
    reason: str = Field(min_length=5, max_length=500)


class LeaveOpeningBalanceInput(BaseModel):
    employee_id: int = Field(gt=0)
    leave_type: str = Field(pattern="^(annual|sick|casual|unpaid|other)$")
    policy_id: int = Field(gt=0)
    quantity_days: Decimal = Field(gt=0, max_digits=9, decimal_places=2)
    effective_date: date
    reason: str = Field(min_length=5, max_length=500)


class LifecycleTemplateInput(BaseModel):
    establishment_id: int | None = Field(default=None, gt=0)
    name: str = Field(min_length=2, max_length=120)
    lifecycle_type: str = Field(pattern="^(onboarding|offboarding)$")


class LifecycleTemplateItemInput(BaseModel):
    task_key: str = Field(min_length=2, max_length=64)
    label: str = Field(min_length=2, max_length=180)
    description: str | None = Field(default=None, max_length=1000)
    owner_role: str = Field(default="manager", pattern="^(employee|manager|hr|finance|it|admin)$")
    due_days_offset: int = Field(default=0, ge=-365, le=3650)
    sequence: int = Field(default=1, ge=1, le=1000)
    is_required: bool = True


class LeaveAccrualInput(BaseModel):
    period_start: date
    period_end: date

    @model_validator(mode="after")
    def ordered_period(self):
        if self.period_end < self.period_start:
            raise ValueError("Accrual period end must not precede its start")
        month_end = date(self.period_start.year,self.period_start.month,
                         monthrange(self.period_start.year,self.period_start.month)[1])
        quarter_start_month = ((self.period_start.month-1)//3)*3+1
        quarter_start = date(self.period_start.year,quarter_start_month,1)
        quarter_end_month = quarter_start_month+2
        quarter_end = date(self.period_start.year,quarter_end_month,
                           monthrange(self.period_start.year,quarter_end_month)[1])
        year_start = date(self.period_start.year,1,1)
        year_end = date(self.period_start.year,12,31)
        is_month = self.period_start.day==1 and self.period_end==month_end
        is_quarter = self.period_start==quarter_start and self.period_end==quarter_end
        is_year = self.period_start==year_start and self.period_end==year_end
        if not (is_month or is_quarter or is_year):
            raise ValueError("Accrual must cover one full calendar month, quarter or year")
        return self


class LifecycleGenerateInput(BaseModel):
    template_id: int = Field(gt=0)
    start_date: date


class LifecycleTaskUpdateInput(BaseModel):
    status: str = Field(pattern="^(pending|in_progress|completed|waived|cancelled)$")
    owner_user_id: int | None = Field(default=None, gt=0)
    owner_role: str | None = Field(default=None, pattern="^(employee|manager|hr|finance|it|admin)$")
    due_date: date | None = None
    evidence_reference: str | None = Field(default=None, max_length=500)
    completion_note: str | None = Field(default=None, max_length=1000)


@router.get("/attendance/policies")
def list_attendance_policies(request: Request, establishment_id: int | None = Query(default=None, gt=0)):
    _manager(request)
    with _hr_connection() as conn:
        rows = conn.execute(
            "SELECT * FROM hr_attendance_policies WHERE (%s::bigint IS NULL OR establishment_id=%s) "
            "ORDER BY establishment_id,effective_from DESC",
            (establishment_id,establishment_id),
        ).fetchall()
        return {"items": rows}


@router.post("/attendance/policies", status_code=201)
def create_attendance_policy(payload: AttendancePolicyInput, request: Request):
    actor = _manager(request)
    with _hr_connection() as conn:
        overlap = conn.execute(
            "SELECT id FROM hr_attendance_policies WHERE establishment_id=%s "
            "AND daterange(effective_from,COALESCE(effective_to,'infinity'::date),'[]') "
            "&& daterange(%s,COALESCE(%s,'infinity'::date),'[]')",
            (payload.establishment_id,payload.effective_from,payload.effective_to),
        ).fetchone()
        if overlap:
            raise HTTPException(409, "An attendance policy already covers part of this effective period")
        return conn.execute(
            "INSERT INTO hr_attendance_policies(establishment_id,grace_minutes,break_minutes,geofence_enabled,"
            "geofence_enforced,require_location_on_clock_in,require_location_on_clock_out,effective_from,effective_to,"
            "created_by_user_id,updated_by_user_id) VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING *",
            (payload.establishment_id,payload.grace_minutes,payload.break_minutes,payload.geofence_enabled,
             payload.geofence_enforced,payload.require_location_on_clock_in,payload.require_location_on_clock_out,
             payload.effective_from,payload.effective_to,actor,actor),
        ).fetchone()


@router.get("/attendance/work-locations")
def list_attendance_work_locations(request: Request, establishment_id: int | None = Query(default=None, gt=0)):
    _manager(request)
    with _hr_connection() as conn:
        return {"items": conn.execute(
            "SELECT * FROM hr_attendance_work_locations WHERE (%s::bigint IS NULL OR establishment_id=%s) "
            "ORDER BY establishment_id,name",
            (establishment_id,establishment_id),
        ).fetchall()}


@router.post("/attendance/work-locations", status_code=201)
def create_attendance_work_location(payload: AttendanceWorkLocationInput, request: Request):
    actor = _manager(request)
    with _hr_connection() as conn:
        return conn.execute(
            "INSERT INTO hr_attendance_work_locations(establishment_id,code,name,latitude,longitude,radius_meters,created_by_user_id) "
            "VALUES(%s,%s,%s,%s,%s,%s,%s) RETURNING *",
            (payload.establishment_id,payload.code,payload.name,payload.latitude,payload.longitude,
             payload.radius_meters,actor),
        ).fetchone()


@router.patch("/attendance/work-locations/{location_id}")
def update_attendance_work_location(location_id: int, payload: AttendanceWorkLocationStatusInput, request: Request):
    _manager(request)
    with _hr_connection() as conn:
        row = conn.execute(
            "UPDATE hr_attendance_work_locations SET is_active=%s,updated_at=now() "
            "WHERE id=%s RETURNING *",
            (payload.is_active,location_id),
        ).fetchone()
        if row is None:
            raise HTTPException(404, "Attendance work location not found")
        return row


@router.get("/shifts")
def list_shift_definitions(request: Request, establishment_id: int | None = Query(default=None, gt=0)):
    _manager(request)
    with _hr_connection() as conn:
        return {"items": conn.execute(
            "SELECT * FROM hr_shift_definitions WHERE (%s::bigint IS NULL OR establishment_id=%s) "
            "ORDER BY establishment_id,name,effective_from DESC", (establishment_id,establishment_id)
        ).fetchall()}


@router.post("/shifts", status_code=201)
def create_shift_definition(payload: ShiftDefinitionInput, request: Request):
    actor = _manager(request)
    try:
        with _hr_connection() as conn:
            return conn.execute(
                "INSERT INTO hr_shift_definitions(establishment_id,code,name,local_start_time,local_end_time,"
                "break_minutes,timezone,effective_from,effective_to,created_by_user_id) "
                "VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING *",
                (payload.establishment_id,payload.code.strip(),payload.name.strip(),payload.local_start_time,
                 payload.local_end_time,payload.break_minutes,payload.timezone,payload.effective_from,
                 payload.effective_to,actor)
            ).fetchone()
    except psycopg.Error as exc:
        raise _db_error(exc) from exc


@router.get("/shift-assignments")
def list_shift_assignments(request: Request, start_date: date, end_date: date):
    actor = _actor(request)
    if end_date < start_date or (end_date-start_date).days > 92:
        raise HTTPException(422,"Roster range must be ordered and no longer than 93 days")
    role = getattr(request.state,"role","")
    with _hr_connection() as conn:
        if role in {"super_admin","owner","admin","manager"}:
            rows = conn.execute(
                "SELECT a.*,e.employee_code,e.first_name,e.last_name,s.name AS shift_name "
                "FROM hr_shift_assignments a JOIN hr_employees e ON e.id=a.employee_id "
                "JOIN hr_shift_definitions s ON s.id=a.shift_definition_id "
                "WHERE a.work_date BETWEEN %s AND %s ORDER BY a.work_date,e.employee_code",
                (start_date,end_date)
            ).fetchall()
        else:
            employee = _employee(conn,actor)
            rows = conn.execute(
                "SELECT a.*,e.employee_code,e.first_name,e.last_name,s.name AS shift_name "
                "FROM hr_shift_assignments a JOIN hr_employees e ON e.id=a.employee_id "
                "JOIN hr_shift_definitions s ON s.id=a.shift_definition_id "
                "WHERE a.employee_id=%s AND a.work_date BETWEEN %s AND %s ORDER BY a.work_date",
                (employee["id"],start_date,end_date)
            ).fetchall()
        return {"items":rows}


@router.post("/shift-assignments", status_code=201)
def create_shift_assignment(payload: ShiftAssignmentInput, request: Request):
    actor = _manager(request)
    try:
        with _hr_connection() as conn:
            shift = conn.execute(
                "SELECT * FROM hr_shift_definitions WHERE id=%s AND is_active=true "
                "AND effective_from<=%s AND (effective_to IS NULL OR effective_to>=%s)",
                (payload.shift_definition_id,payload.work_date,payload.work_date)
            ).fetchone()
            if not shift:
                raise HTTPException(422,"Shift definition is not active for the selected work date")
            employee = conn.execute("SELECT id FROM hr_employees WHERE id=%s AND status<>'terminated'",(payload.employee_id,)).fetchone()
            if not employee:
                raise HTTPException(404,"Active employee not found")
            return conn.execute(
                "INSERT INTO hr_shift_assignments(employee_id,shift_definition_id,work_date,planned_start_at,"
                "planned_end_at,assigned_by_user_id) VALUES(%s,%s,%s,%s,%s,%s) RETURNING *",
                (payload.employee_id,payload.shift_definition_id,payload.work_date,payload.planned_start_at,
                 payload.planned_end_at,actor)
            ).fetchone()
    except HTTPException:
        raise
    except psycopg.Error as exc:
        raise _db_error(exc) from exc


@router.post("/shift-assignments/{assignment_id}/publish")
def publish_shift_assignment(assignment_id: int, request: Request):
    actor = _manager(request)
    with _hr_connection() as conn:
        row = conn.execute(
            "UPDATE hr_shift_assignments SET status='published',published_by_user_id=%s,published_at=now(),updated_at=now() "
            "WHERE id=%s AND status='draft' RETURNING *",(actor,assignment_id)
        ).fetchone()
        if row is None:
            raise HTTPException(409,"Only a draft shift assignment can be published")
        return row


@router.post("/shift-assignments/{assignment_id}/cancel")
def cancel_shift_assignment(assignment_id: int, payload: ReviewInput, request: Request):
    _manager(request)
    if not payload.note or not payload.note.strip():
        raise HTTPException(422,"A cancellation reason is required")
    with _hr_connection() as conn:
        row = conn.execute(
            "UPDATE hr_shift_assignments SET status='cancelled',cancellation_reason=%s,updated_at=now() "
            "WHERE id=%s AND status IN ('draft','published') RETURNING *",
            (payload.note.strip(),assignment_id)
        ).fetchone()
        if row is None:
            raise HTTPException(409,"Shift assignment is not cancellable")
        return row


@router.get("/holiday-calendars")
def list_holiday_calendars(request: Request, establishment_id: int | None = Query(default=None, gt=0)):
    _manager(request)
    with _hr_connection() as conn:
        return {"items":conn.execute(
            "SELECT c.*,count(h.id) AS holiday_count FROM hr_holiday_calendars c "
            "LEFT JOIN hr_holidays h ON h.calendar_id=c.id "
            "WHERE (%s::bigint IS NULL OR c.establishment_id=%s) "
            "GROUP BY c.id ORDER BY c.effective_year DESC,c.name",
            (establishment_id,establishment_id)
        ).fetchall()}


@router.post("/holiday-calendars", status_code=201)
def create_holiday_calendar(payload: HolidayCalendarInput, request: Request):
    actor = _manager(request)
    with _hr_connection() as conn:
        return conn.execute(
            "INSERT INTO hr_holiday_calendars(establishment_id,name,region_code,effective_year,created_by_user_id) "
            "VALUES(%s,%s,%s,%s,%s) RETURNING *",
            (payload.establishment_id,payload.name.strip(),payload.region_code,payload.effective_year,actor)
        ).fetchone()


@router.post("/holiday-calendars/{calendar_id}/holidays", status_code=201)
def add_holiday(calendar_id: int, payload: HolidayInput, request: Request):
    _manager(request)
    with _hr_connection() as conn:
        calendar = conn.execute("SELECT status,effective_year FROM hr_holiday_calendars WHERE id=%s FOR UPDATE",(calendar_id,)).fetchone()
        if not calendar:
            raise HTTPException(404,"Holiday calendar not found")
        if payload.holiday_date.year != calendar["effective_year"]:
            raise HTTPException(422,"Holiday date must fall within the calendar year")
        if calendar["status"] != "draft":
            raise HTTPException(409,"Approved or retired holiday calendars are locked; create a new calendar version")
        return conn.execute(
            "INSERT INTO hr_holidays(calendar_id,holiday_date,name,holiday_type,location_code,is_paid) "
            "VALUES(%s,%s,%s,%s,%s,%s) RETURNING *",
            (calendar_id,payload.holiday_date,payload.name.strip(),payload.holiday_type,payload.location_code,payload.is_paid)
        ).fetchone()


@router.get("/holiday-calendars/{calendar_id}/holidays")
def get_holidays(calendar_id: int, request: Request):
    _manager(request)
    with _hr_connection() as conn:
        return {"items":conn.execute(
            "SELECT * FROM hr_holidays WHERE calendar_id=%s ORDER BY holiday_date,name",(calendar_id,)
        ).fetchall()}


@router.post("/holiday-calendars/{calendar_id}/approve")
def approve_holiday_calendar(calendar_id: int, request: Request):
    actor = _manager(request)
    with _hr_connection() as conn:
        row = conn.execute(
            "UPDATE hr_holiday_calendars SET status='approved',approved_by_user_id=%s,approved_at=now(),updated_at=now() "
            "WHERE id=%s AND status='draft' RETURNING *",(actor,calendar_id)
        ).fetchone()
        if row is None:
            raise HTTPException(409,"Only a draft holiday calendar can be approved")
        return row


@router.get("/leave-policies")
def list_leave_policies(request: Request, establishment_id: int | None = Query(default=None, gt=0)):
    _manager(request)
    with _hr_connection() as conn:
        return {"items":conn.execute(
            "SELECT * FROM hr_leave_policies WHERE (%s::bigint IS NULL OR establishment_id=%s) "
            "ORDER BY establishment_id,leave_type,effective_from DESC",(establishment_id,establishment_id)
        ).fetchall()}


@router.post("/leave-policies", status_code=201)
def create_leave_policy(payload: LeavePolicyInput, request: Request):
    actor = _manager(request)
    try:
        with _hr_connection() as conn:
            return conn.execute(
                "INSERT INTO hr_leave_policies(establishment_id,leave_type,version_label,effective_from,effective_to,"
                "entitlement_days,accrual_frequency,carry_forward_cap,allow_negative_balance,encashment_allowed,"
                "probation_eligible,day_count_basis,policy_notes,created_by_user_id) "
                "VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING *",
                (payload.establishment_id,payload.leave_type,payload.version_label.strip(),payload.effective_from,
                 payload.effective_to,payload.entitlement_days,payload.accrual_frequency,payload.carry_forward_cap,
                 payload.allow_negative_balance,payload.encashment_allowed,payload.probation_eligible,
                 payload.day_count_basis,payload.policy_notes,actor)
            ).fetchone()
    except psycopg.Error as exc:
        raise _db_error(exc) from exc


@router.post("/leave-policies/{policy_id}/approve")
def approve_leave_policy(policy_id: int, request: Request):
    actor = _manager(request)
    with _hr_connection() as conn:
        policy = conn.execute("SELECT * FROM hr_leave_policies WHERE id=%s FOR UPDATE",(policy_id,)).fetchone()
        if not policy or policy["status"] != "draft":
            raise HTTPException(409,"Only a draft leave policy can be approved")
        overlap = conn.execute(
            "SELECT id FROM hr_leave_policies WHERE establishment_id=%s AND leave_type=%s AND status='approved' "
            "AND id<>%s AND daterange(effective_from,COALESCE(effective_to,'infinity'::date),'[]') "
            "&& daterange(%s,COALESCE(%s,'infinity'::date),'[]') LIMIT 1",
            (policy["establishment_id"],policy["leave_type"],policy_id,policy["effective_from"],policy["effective_to"])
        ).fetchone()
        if overlap:
            raise HTTPException(409,"An approved leave policy already overlaps this effective period")
        return conn.execute(
            "UPDATE hr_leave_policies SET status='approved',approved_by_user_id=%s,approved_at=now(),updated_at=now() "
            "WHERE id=%s RETURNING *",(actor,policy_id)
        ).fetchone()


@router.get("/leave-balances")
def list_leave_balances(request: Request, employee_id: int | None = Query(default=None, gt=0)):
    actor = _actor(request)
    role = getattr(request.state,"role","")
    with _hr_connection() as conn:
        if role in {"super_admin","owner","admin","manager"}:
            rows = conn.execute(
                "SELECT b.*,b.closing_days+COALESCE((SELECT sum(l.quantity_days) FROM hr_leave_ledger l "
                "WHERE l.employee_id=b.employee_id AND l.leave_type=b.leave_type AND l.created_at>b.calculated_at),0) "
                "AS live_closing_days,b.accrued_days+COALESCE((SELECT sum(l.quantity_days) FROM hr_leave_ledger l "
                "WHERE l.employee_id=b.employee_id AND l.leave_type=b.leave_type AND l.transaction_type='accrual' "
                "AND l.created_at>b.calculated_at),0) AS live_accrued_days,"
                "b.used_days-COALESCE((SELECT sum(l.quantity_days) FROM hr_leave_ledger l "
                "WHERE l.employee_id=b.employee_id AND l.leave_type=b.leave_type "
                "AND l.transaction_type IN ('consumption','reversal') AND l.created_at>b.calculated_at),0) "
                "AS live_used_days,"
                "b.adjusted_days+COALESCE((SELECT sum(l.quantity_days) FROM hr_leave_ledger l "
                "WHERE l.employee_id=b.employee_id AND l.leave_type=b.leave_type AND l.transaction_type IN ('adjustment','reversal','carry_forward') "
                "AND l.created_at>b.calculated_at),0) AS live_adjusted_days,"
                "e.employee_code,e.first_name,e.last_name FROM hr_leave_balances b "
                "JOIN hr_employees e ON e.id=b.employee_id "
                "WHERE (%s::bigint IS NULL OR b.employee_id=%s) ORDER BY e.employee_code,b.leave_type,b.period_start DESC",
                (employee_id,employee_id)
            ).fetchall()
        else:
            employee = _employee(conn,actor)
            rows = conn.execute(
                "SELECT b.*,b.closing_days+COALESCE((SELECT sum(l.quantity_days) FROM hr_leave_ledger l "
                "WHERE l.employee_id=b.employee_id AND l.leave_type=b.leave_type AND l.created_at>b.calculated_at),0) "
                "AS live_closing_days,b.accrued_days+COALESCE((SELECT sum(l.quantity_days) FROM hr_leave_ledger l "
                "WHERE l.employee_id=b.employee_id AND l.leave_type=b.leave_type AND l.transaction_type='accrual' "
                "AND l.created_at>b.calculated_at),0) AS live_accrued_days,"
                "b.used_days-COALESCE((SELECT sum(l.quantity_days) FROM hr_leave_ledger l "
                "WHERE l.employee_id=b.employee_id AND l.leave_type=b.leave_type "
                "AND l.transaction_type IN ('consumption','reversal') AND l.created_at>b.calculated_at),0) "
                "AS live_used_days,"
                "b.adjusted_days+COALESCE((SELECT sum(l.quantity_days) FROM hr_leave_ledger l "
                "WHERE l.employee_id=b.employee_id AND l.leave_type=b.leave_type AND l.transaction_type IN ('adjustment','reversal','carry_forward') "
                "AND l.created_at>b.calculated_at),0) AS live_adjusted_days FROM hr_leave_balances b "
                "WHERE b.employee_id=%s ORDER BY b.leave_type,b.period_start DESC",
                (employee["id"],)
            ).fetchall()
        return {"items":rows}


@router.post("/leave/accruals")
def accrue_leave(payload: LeaveAccrualInput, request: Request):
    actor = _manager(request)
    period_start = payload.period_start
    period_end = payload.period_end
    with _hr_connection() as conn:
        policies = conn.execute(
            "SELECT * FROM hr_leave_policies WHERE status='approved' AND effective_from<=%s "
            "AND (effective_to IS NULL OR effective_to>=%s) ORDER BY establishment_id,leave_type",
            (period_end,period_start)
        ).fetchall()
        created = 0
        for policy in policies:
            employees = conn.execute(
                "SELECT e.id,e.status,sp.establishment_id FROM hr_employees e "
                "JOIN hr_employee_statutory_profiles sp ON sp.employee_id=e.id "
                "WHERE sp.establishment_id=%s AND e.status IN ('active','probation','notice_period') "
                "AND e.joining_date<=%s AND (e.exit_date IS NULL OR e.exit_date>=%s) FOR SHARE",
                (policy["establishment_id"],period_end,period_start)
            ).fetchall()
            for employee in employees:
                if employee["status"] == "probation" and not policy["probation_eligible"]:
                    continue
                frequency = policy["accrual_frequency"]
                if frequency == "monthly" and not (
                    period_start.day == 1 and period_end == date(period_start.year,period_start.month,
                    monthrange(period_start.year,period_start.month)[1])
                ):
                    continue
                if frequency == "quarterly":
                    quarter_month = ((period_start.month-1)//3)*3+1
                    quarter_end_month = quarter_month+2
                    expected_quarter_end = date(period_start.year,quarter_end_month,
                        monthrange(period_start.year,quarter_end_month)[1])
                    if period_start != date(period_start.year,quarter_month,1) or period_end != expected_quarter_end:
                        continue
                if frequency == "yearly" and not (
                    period_start == date(period_start.year,1,1) and period_end == date(period_start.year,12,31)
                ):
                    continue
                if period_start == date(period_start.year,1,1) and policy["carry_forward_cap"] >= 0:
                    prior_balance = conn.execute(
                        "SELECT COALESCE(sum(quantity_days),0) AS days FROM hr_leave_ledger "
                        "WHERE employee_id=%s AND leave_type=%s AND effective_date<%s",
                        (employee["id"],policy["leave_type"],period_start)
                    ).fetchone()["days"]
                    excess = max(Decimal("0"),prior_balance-policy["carry_forward_cap"])
                    if excess > 0:
                        carry_source_id = int(period_start.strftime("%Y%m")) * 1000000 + int(policy["id"])
                        conn.execute(
                            "INSERT INTO hr_leave_ledger(employee_id,leave_type,policy_id,transaction_type,source_type,"
                            "source_id,effective_date,quantity_days,reason,actor_user_id) "
                            "VALUES(%s,%s,%s,'carry_forward','carry_forward',%s,%s,%s,%s,%s) "
                            "ON CONFLICT DO NOTHING",
                            (employee["id"],policy["leave_type"],policy["id"],carry_source_id,period_start,
                             -excess,"Carry-forward cap applied for "+str(period_start.year),actor)
                        )
                if policy["leave_type"] == "unpaid" or frequency == "none":
                    quantity = Decimal("0")
                elif frequency == "monthly":
                    quantity = policy["entitlement_days"] / Decimal("12")
                elif frequency == "quarterly":
                    quantity = policy["entitlement_days"] / Decimal("4")
                else:
                    quantity = policy["entitlement_days"]
                quantity = quantity.quantize(Decimal("0.01"))
                source_id = int(period_start.strftime("%Y%m")) * 1000000 + int(policy["id"])
                if quantity > 0:
                    inserted = conn.execute(
                        "INSERT INTO hr_leave_ledger(employee_id,leave_type,policy_id,transaction_type,source_type,"
                        "source_id,effective_date,quantity_days,reason,actor_user_id) "
                        "VALUES(%s,%s,%s,'accrual','policy_accrual',%s,%s,%s,%s,%s) "
                        "ON CONFLICT DO NOTHING RETURNING id",
                        (employee["id"],policy["leave_type"],policy["id"],source_id,period_end,quantity,
                         "Policy accrual "+period_start.isoformat()+" to "+period_end.isoformat(),actor)
                    ).fetchone()
                    if inserted:
                        created += 1
                balance = conn.execute(
                    "SELECT COALESCE(sum(quantity_days),0) AS closing FROM hr_leave_ledger "
                    "WHERE employee_id=%s AND leave_type=%s AND effective_date<=%s",
                    (employee["id"],policy["leave_type"],period_end)
                ).fetchone()["closing"]
                conn.execute(
                    "INSERT INTO hr_leave_balances(employee_id,leave_type,policy_id,period_start,period_end,"
                    "opening_days,accrued_days,used_days,adjusted_days,closing_days) "
                    "VALUES(%s,%s,%s,%s,%s,%s,%s,0,0,%s) "
                    "ON CONFLICT(employee_id,leave_type,policy_id,period_start,period_end) DO UPDATE SET "
                    "closing_days=EXCLUDED.closing_days,accrued_days=EXCLUDED.accrued_days,calculated_at=now()",
                    (employee["id"],policy["leave_type"],policy["id"],period_start,period_end,
                     balance-quantity,quantity,balance)
                )
        return {"created_ledger_entries":created,"period_start":period_start,"period_end":period_end}


@router.post("/leave-balances/opening")
def create_leave_opening_balance(payload: LeaveOpeningBalanceInput, request: Request):
    actor = _manager(request)
    with _hr_connection() as conn:
        policy = conn.execute(
            "SELECT * FROM hr_leave_policies WHERE id=%s AND leave_type=%s AND status='approved' "
            "AND effective_from<=%s AND (effective_to IS NULL OR effective_to>=%s)",
            (payload.policy_id,payload.leave_type,payload.effective_date,payload.effective_date)
        ).fetchone()
        if not policy:
            raise HTTPException(409,"An approved effective leave policy is required for the opening balance")
        employee = conn.execute(
            "SELECT sp.establishment_id FROM hr_employees e "
            "JOIN hr_employee_statutory_profiles sp ON sp.employee_id=e.id WHERE e.id=%s",
            (payload.employee_id,)
        ).fetchone()
        if not employee or employee["establishment_id"] != policy["establishment_id"]:
            raise HTTPException(422,"Employee and leave policy must belong to the same establishment")
        row = conn.execute(
            "INSERT INTO hr_leave_ledger(employee_id,leave_type,policy_id,transaction_type,source_type,"
            "source_id,effective_date,quantity_days,reason,actor_user_id) "
            "VALUES(%s,%s,%s,'opening','opening_balance',%s,%s,%s,%s,%s) "
            "ON CONFLICT DO NOTHING RETURNING *",
            (payload.employee_id,payload.leave_type,payload.policy_id,payload.policy_id,
             payload.effective_date,payload.quantity_days,payload.reason.strip(),actor)
        ).fetchone()
        if row is None:
            row = conn.execute(
                "SELECT * FROM hr_leave_ledger WHERE employee_id=%s AND leave_type=%s "
                "AND transaction_type='opening' AND source_type='opening_balance' AND source_id=%s",
                (payload.employee_id,payload.leave_type,payload.policy_id)
            ).fetchone()
        conn.execute(
            "INSERT INTO hr_leave_balances(employee_id,leave_type,policy_id,period_start,period_end,"
            "opening_days,accrued_days,used_days,adjusted_days,closing_days) "
            "VALUES(%s,%s,%s,%s,%s,0,0,0,%s,%s) "
            "ON CONFLICT(employee_id,leave_type,policy_id,period_start,period_end) DO UPDATE SET "
            "adjusted_days=EXCLUDED.adjusted_days,closing_days=EXCLUDED.closing_days,calculated_at=now()",
            (payload.employee_id,payload.leave_type,payload.policy_id,payload.effective_date,
             payload.effective_date,payload.quantity_days,payload.quantity_days)
        )
        return row


@router.post("/leave-balances/adjust")
def adjust_leave_balance(payload: LeaveBalanceAdjustmentInput, request: Request):
    actor = _manager(request)
    if payload.quantity_days == 0:
        raise HTTPException(422,"Adjustment quantity cannot be zero")
    with _hr_connection() as conn:
        employee = conn.execute("SELECT id FROM hr_employees WHERE id=%s",(payload.employee_id,)).fetchone()
        if not employee:
            raise HTTPException(404,"Employee not found")
        policy = conn.execute(
            "SELECT id,allow_negative_balance FROM hr_leave_policies WHERE leave_type=%s AND status='approved' "
            "AND effective_from<=%s AND (effective_to IS NULL OR effective_to>=%s) "
            "AND establishment_id=(SELECT establishment_id FROM hr_employee_statutory_profiles WHERE employee_id=%s)",
            (payload.leave_type,payload.effective_date,payload.effective_date,payload.employee_id)
        ).fetchone()
        if not policy:
            raise HTTPException(409,"No approved effective leave policy exists for this employee and leave type")
        current_balance = conn.execute(
            "SELECT COALESCE(sum(quantity_days),0) AS days FROM hr_leave_ledger "
            "WHERE employee_id=%s AND leave_type=%s AND effective_date<=%s",
            (payload.employee_id,payload.leave_type,payload.effective_date)
        ).fetchone()["days"]
        if not policy["allow_negative_balance"] and current_balance+payload.quantity_days < 0:
            raise HTTPException(409,"This adjustment would create a negative leave balance")
        return conn.execute(
            "INSERT INTO hr_leave_ledger(employee_id,leave_type,policy_id,transaction_type,source_type,"
            "effective_date,quantity_days,reason,actor_user_id) "
            "VALUES(%s,%s,%s,'adjustment','manual_adjustment',%s,%s,%s,%s) RETURNING *",
            (payload.employee_id,payload.leave_type,policy["id"],payload.effective_date,
             payload.quantity_days,payload.reason.strip(),actor)
        ).fetchone()


@router.get("/leave-ledger")
def list_leave_ledger(request: Request, employee_id: int | None = Query(default=None, gt=0)):
    actor = _actor(request)
    role = getattr(request.state,"role","")
    with _hr_connection() as conn:
        if role in {"super_admin","owner","admin","manager"}:
            rows = conn.execute(
                "SELECT l.*,e.employee_code,e.first_name,e.last_name FROM hr_leave_ledger l "
                "JOIN hr_employees e ON e.id=l.employee_id WHERE (%s::bigint IS NULL OR l.employee_id=%s) "
                "ORDER BY l.effective_date DESC,l.id DESC",(employee_id,employee_id)
            ).fetchall()
        else:
            employee = _employee(conn,actor)
            rows = conn.execute("SELECT * FROM hr_leave_ledger WHERE employee_id=%s ORDER BY effective_date DESC,id DESC",(employee["id"],)).fetchall()
        return {"items":rows}


@router.get("/lifecycle/templates")
def list_lifecycle_templates(request: Request):
    _manager(request)
    with _hr_connection() as conn:
        return {"items":conn.execute(
            "SELECT t.*,count(i.id) AS task_count FROM hr_employee_lifecycle_templates t "
            "LEFT JOIN hr_employee_lifecycle_template_items i ON i.template_id=t.id "
            "WHERE t.is_active=true GROUP BY t.id ORDER BY t.lifecycle_type,t.name"
        ).fetchall()}


@router.post("/lifecycle/templates", status_code=201)
def create_lifecycle_template(payload: LifecycleTemplateInput, request: Request):
    actor = _manager(request)
    with _hr_connection() as conn:
        version = conn.execute(
            "SELECT COALESCE(MAX(version),0)+1 AS next_version FROM hr_employee_lifecycle_templates "
            "WHERE establishment_id IS NOT DISTINCT FROM %s AND name=%s AND lifecycle_type=%s",
            (payload.establishment_id,payload.name.strip(),payload.lifecycle_type)
        ).fetchone()["next_version"]
        return conn.execute(
            "INSERT INTO hr_employee_lifecycle_templates(establishment_id,name,lifecycle_type,version,created_by_user_id) "
            "VALUES(%s,%s,%s,%s,%s) RETURNING *",
            (payload.establishment_id,payload.name.strip(),payload.lifecycle_type,version,actor)
        ).fetchone()


@router.post("/lifecycle/templates/{template_id}/items", status_code=201)
def add_lifecycle_template_item(template_id: int, payload: LifecycleTemplateItemInput, request: Request):
    _manager(request)
    with _hr_connection() as conn:
        return conn.execute(
            "INSERT INTO hr_employee_lifecycle_template_items(template_id,task_key,label,description,owner_role,"
            "due_days_offset,sequence,is_required) VALUES(%s,%s,%s,%s,%s,%s,%s,%s) RETURNING *",
            (template_id,payload.task_key.strip(),payload.label.strip(),payload.description,payload.owner_role,
             payload.due_days_offset,payload.sequence,payload.is_required)
        ).fetchone()


@router.post("/lifecycle/employees/{employee_id}/generate")
def generate_lifecycle_tasks(employee_id: int, payload: LifecycleGenerateInput, request: Request):
    actor = _manager(request)
    template_id = payload.template_id
    start_date = payload.start_date
    with _hr_connection() as conn:
        employee = conn.execute(
            "SELECT e.id,sp.establishment_id FROM hr_employees e "
            "LEFT JOIN hr_employee_statutory_profiles sp ON sp.employee_id=e.id WHERE e.id=%s",
            (employee_id,)
        ).fetchone()
        template = conn.execute("SELECT * FROM hr_employee_lifecycle_templates WHERE id=%s AND is_active=true",(template_id,)).fetchone()
        if not employee or not template:
            raise HTTPException(404,"Employee or active lifecycle template not found")
        if template["establishment_id"] is not None and template["establishment_id"] != employee["establishment_id"]:
            raise HTTPException(422,"Lifecycle template is not applicable to the employee's establishment")
        items = conn.execute(
            "SELECT * FROM hr_employee_lifecycle_template_items WHERE template_id=%s ORDER BY sequence,id",
            (template_id,)
        ).fetchall()
        if not items:
            raise HTTPException(409,"Lifecycle template has no tasks")
        generated = []
        for item in items:
            due = start_date + __import__("datetime").timedelta(days=item["due_days_offset"]) if item["due_days_offset"] else start_date
            row = conn.execute(
                "INSERT INTO hr_employee_lifecycle_tasks(employee_id,template_id,template_item_id,task_key,label,"
                "description,owner_role,due_date,created_by_user_id) VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s) "
                "ON CONFLICT(employee_id,template_item_id) WHERE template_item_id IS NOT NULL DO NOTHING RETURNING *",
                (employee_id,template_id,item["id"],item["task_key"],item["label"],item["description"],item["owner_role"],due,actor)
            ).fetchone()
            if row:
                generated.append(row)
                conn.execute(
                    "INSERT INTO hr_employee_lifecycle_task_events(task_id,event_type,after_state,actor_user_id) "
                    "VALUES(%s,'created',%s::jsonb,%s)",
                    (row["id"],__import__("json").dumps({"status":"pending","label":row["label"]}),actor)
                )
        return {"items":generated,"created_count":len(generated)}


@router.get("/lifecycle/tasks")
def list_lifecycle_tasks(request: Request, employee_id: int | None = Query(default=None, gt=0)):
    actor = _actor(request)
    role = getattr(request.state,"role","")
    with _hr_connection() as conn:
        if role in {"super_admin","owner","admin","manager"}:
            rows = conn.execute(
                "SELECT t.*,e.employee_code,e.first_name,e.last_name FROM hr_employee_lifecycle_tasks t "
                "JOIN hr_employees e ON e.id=t.employee_id WHERE (%s::bigint IS NULL OR t.employee_id=%s) "
                "ORDER BY t.due_date NULLS LAST,e.employee_code,t.created_at",
                (employee_id,employee_id)
            ).fetchall()
        else:
            employee = _employee(conn,actor)
            rows = conn.execute(
                "SELECT t.* FROM hr_employee_lifecycle_tasks t "
                "WHERE ((t.employee_id=%s AND t.owner_role='employee') OR t.owner_user_id=%s) "
                "ORDER BY t.due_date NULLS LAST,t.created_at",
                (employee["id"],actor)
            ).fetchall()
        return {"items":rows}


@router.patch("/lifecycle/tasks/{task_id}")
def update_lifecycle_task(task_id: int, payload: LifecycleTaskUpdateInput, request: Request):
    actor = _actor(request)
    role = getattr(request.state,"role","")
    with _hr_connection() as conn:
        task = conn.execute("SELECT * FROM hr_employee_lifecycle_tasks WHERE id=%s FOR UPDATE",(task_id,)).fetchone()
        if not task:
            raise HTTPException(404,"Lifecycle task not found")
        if role not in {"super_admin","owner","admin","manager"}:
            employee = _employee(conn,actor)
            if not (task["owner_user_id"] == actor or (task["employee_id"] == employee["id"] and task["owner_role"] == "employee")):
                raise HTTPException(403,"You cannot update this lifecycle task")
            if payload.status not in {"in_progress","completed"}:
                raise HTTPException(403,"Employees may only start or complete their own tasks")
            if task["status"] == "completed" and payload.status != "completed":
                raise HTTPException(409,"Only a manager may reopen a completed lifecycle task")
        if payload.status == "completed" and not (payload.completion_note or payload.evidence_reference):
            raise HTTPException(422,"A completion note or evidence reference is required")
        is_manager = role in {"super_admin","owner","admin","manager"}
        owner_user_id = (
            payload.owner_user_id if is_manager and "owner_user_id" in payload.model_fields_set
            else task["owner_user_id"]
        )
        owner_role = (
            payload.owner_role if is_manager and "owner_role" in payload.model_fields_set
            else task["owner_role"]
        )
        due_date = (
            payload.due_date if is_manager and "due_date" in payload.model_fields_set
            else task["due_date"]
        )
        evidence_reference = (
            payload.evidence_reference if "evidence_reference" in payload.model_fields_set
            else task["evidence_reference"]
        )
        completion_note = (
            payload.completion_note if "completion_note" in payload.model_fields_set
            else task["completion_note"]
        )
        row = conn.execute(
            "UPDATE hr_employee_lifecycle_tasks SET status=%s,owner_user_id=%s,owner_role=%s,due_date=%s,"
            "evidence_reference=%s,completion_note=%s,completed_at=%s,completed_by_user_id=%s,updated_at=now() "
            "WHERE id=%s RETURNING *",
            (payload.status,owner_user_id,owner_role,due_date,evidence_reference,completion_note,
             __import__("datetime").datetime.now(__import__("datetime").timezone.utc) if payload.status=="completed" else None,
             actor if payload.status=="completed" else None,task_id)
        ).fetchone()
        if payload.status == "completed":
            event_type = "completed"
        elif task["status"] == "completed" and payload.status in {"pending","in_progress"}:
            event_type = "reopened"
        elif payload.status == "in_progress":
            event_type = "started"
        elif payload.status in {"waived","cancelled"}:
            event_type = payload.status
        elif owner_user_id != task["owner_user_id"] or owner_role != task["owner_role"]:
            event_type = "assigned"
        else:
            event_type = "updated"
        conn.execute(
            "INSERT INTO hr_employee_lifecycle_task_events(task_id,event_type,before_state,after_state,reason,actor_user_id) "
            "VALUES(%s,%s,%s::jsonb,%s::jsonb,%s,%s)",
            (task_id,event_type,
             __import__("json").dumps({"status":task["status"],"owner_user_id":task["owner_user_id"],"owner_role":task["owner_role"]}),
             __import__("json").dumps({"status":row["status"],"owner_user_id":row["owner_user_id"],"owner_role":row["owner_role"]}),
             payload.completion_note,actor)
        )
        return row


class LeaveCancellationInput(BaseModel):
    reason: str = Field(min_length=5,max_length=500)


@router.post("/leave/{leave_id}/cancel")
def cancel_leave_request(leave_id: int, payload: LeaveCancellationInput, request: Request):
    actor = _actor(request)
    with _hr_connection() as conn:
        employee = _employee(conn,actor)
        row = conn.execute(
            "SELECT * FROM hr_leave_requests WHERE id=%s AND employee_id=%s FOR UPDATE",
            (leave_id,employee["id"])
        ).fetchone()
        if not row:
            raise HTTPException(404,"Leave request not found")
        if row["status"] not in {"pending","approved"}:
            raise HTTPException(409,"Only pending or approved leave can be cancelled")
        if row["status"] == "approved":
            consumed = conn.execute(
                "SELECT * FROM hr_leave_ledger WHERE employee_id=%s AND leave_type=%s "
                "AND transaction_type='consumption' AND source_type='leave_request' AND source_id=%s",
                (employee["id"],row["leave_type"],leave_id)
            ).fetchone()
            if consumed:
                conn.execute(
                    "INSERT INTO hr_leave_ledger(employee_id,leave_type,policy_id,transaction_type,source_type,"
                    "source_id,effective_date,quantity_days,reason,actor_user_id) "
                    "VALUES(%s,%s,%s,'reversal','leave_request',%s,%s,%s,%s,%s) ON CONFLICT DO NOTHING",
                    (employee["id"],row["leave_type"],consumed["policy_id"],leave_id,row["start_date"],
                     abs(consumed["quantity_days"]),payload.reason.strip(),actor)
                )
        return conn.execute(
            "UPDATE hr_leave_requests SET status='cancelled',review_note=%s,reviewed_by_user_id=%s,reviewed_at=now() "
            "WHERE id=%s RETURNING *",(payload.reason.strip(),actor,leave_id)
        ).fetchone()


@router.get("/lifecycle/tasks/{task_id}/events")
def list_lifecycle_task_events(task_id: int, request: Request):
    actor = _actor(request)
    role = getattr(request.state,"role","")
    with _hr_connection() as conn:
        task = conn.execute("SELECT employee_id,owner_user_id,owner_role FROM hr_employee_lifecycle_tasks WHERE id=%s",(task_id,)).fetchone()
        if not task:
            raise HTTPException(404,"Lifecycle task not found")
        if role not in {"super_admin","owner","admin","manager"}:
            employee = _employee(conn,actor)
            if not (task["owner_user_id"] == actor or (task["employee_id"] == employee["id"] and task["owner_role"] == "employee")):
                raise HTTPException(403,"You cannot view this lifecycle task history")
        return {"items":conn.execute(
            "SELECT * FROM hr_employee_lifecycle_task_events WHERE task_id=%s ORDER BY created_at,id",(task_id,)
        ).fetchall()}


@router.get("/holidays/me")
def list_my_holidays(request: Request, year: int = Query(default=date.today().year, ge=2000, le=2200)):
    actor = _actor(request)
    with _hr_connection() as conn:
        employee = _employee(conn,actor)
        return {"items":conn.execute(
            "SELECT h.*,c.name AS calendar_name,c.effective_year,c.region_code "
            "FROM hr_holidays h JOIN hr_holiday_calendars c ON c.id=h.calendar_id "
            "JOIN hr_establishments est ON est.id=c.establishment_id "
            "JOIN hr_employee_statutory_profiles sp ON sp.establishment_id=c.establishment_id "
            "WHERE sp.employee_id=%s AND c.effective_year=%s AND c.status='approved' "
            "AND (c.region_code IS NULL OR c.region_code=est.state_code) AND h.location_code IS NULL "
            "ORDER BY h.holiday_date,h.name",
            (employee["id"],year)
        ).fetchall()}
