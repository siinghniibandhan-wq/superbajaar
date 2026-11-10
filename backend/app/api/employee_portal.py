"""Employee self-service portal APIs bound exclusively to the signed-in employee."""
from datetime import date
from decimal import Decimal

import psycopg
from fastapi import APIRouter, HTTPException, Request
from psycopg.rows import dict_row
from pydantic import BaseModel, Field, model_validator

from app.core.config import settings

router = APIRouter(prefix="/employee-portal", tags=["employee portal"])


def _connect():
    if not settings.database_url:
        raise HTTPException(503, "Employee portal database is not configured")
    try:
        return psycopg.connect(settings.database_url, row_factory=dict_row, connect_timeout=3)
    except psycopg.Error as exc:
        raise HTTPException(503, "Employee portal database is unavailable") from exc


def _employee(conn, request: Request):
    user_id = getattr(request.state, "user_id", None)
    if not user_id:
        raise HTTPException(401, "Sign in to the Employee Portal")
    row = conn.execute(
        "SELECT e.id,e.employee_code,e.first_name,e.last_name,e.email,e.phone,e.designation,"
        "e.status,d.name AS department,e.joining_date "
        "FROM hr_employees e LEFT JOIN hr_departments d ON d.id=e.department_id "
        "JOIN app_users u ON u.id=e.user_id AND u.is_active=TRUE "
        "WHERE e.user_id=%s AND e.status<>'terminated'",
        (user_id,),
    ).fetchone()
    if not row:
        raise HTTPException(403, "This account is not linked to an active employee profile")
    return row


class PunchInput(BaseModel):
    punch_type: str = Field(pattern="^(clock_in|clock_out)$")
    note: str | None = Field(default=None, max_length=500)


class LeaveInput(BaseModel):
    leave_type: str = Field(pattern="^(annual|sick|casual|unpaid|other)$")
    start_date: date
    end_date: date
    days: Decimal = Field(gt=0, max_digits=6, decimal_places=2)
    reason: str = Field(min_length=3, max_length=1000)

    @model_validator(mode="after")
    def valid_dates(self):
        if self.end_date < self.start_date:
            raise ValueError("Leave end date cannot precede start date")
        return self


class ExpenseInput(BaseModel):
    category: str = Field(min_length=2, max_length=64)
    amount: Decimal = Field(gt=0, max_digits=14, decimal_places=2)
    expense_date: date
    description: str = Field(min_length=3, max_length=1000)
    receipt_reference: str | None = Field(default=None, max_length=500)


@router.get("/me")
def employee_me(request: Request):
    try:
        with _connect() as conn:
            return {"portal": "employee", "employee": _employee(conn, request)}
    except HTTPException:
        raise
    except psycopg.Error as exc:
        raise HTTPException(503, "Unable to load employee profile") from exc


@router.get("/dashboard")
def employee_dashboard(request: Request):
    try:
        with _connect() as conn:
            employee = _employee(conn, request)
            employee_id = employee["id"]
            attendance = conn.execute(
                "SELECT count(*) FILTER (WHERE clock_in_at::date=current_date) AS today_sessions,"
                "max(clock_in_at) FILTER (WHERE clock_out_at IS NULL) AS open_clock_in "
                "FROM hr_attendance_sessions WHERE employee_id=%s",
                (employee_id,),
            ).fetchone()
            leave = conn.execute(
                "SELECT count(*) FILTER (WHERE status='pending') AS pending,"
                "count(*) FILTER (WHERE status='approved' AND end_date>=current_date) AS upcoming "
                "FROM hr_leave_requests WHERE employee_id=%s",
                (employee_id,),
            ).fetchone()
            expenses = conn.execute(
                "SELECT count(*) FILTER (WHERE status='pending') AS pending,"
                "COALESCE(sum(amount) FILTER (WHERE status IN ('approved','reimbursed')),0) AS approved_value "
                "FROM hr_expenses WHERE employee_id=%s",
                (employee_id,),
            ).fetchone()
        return {"employee": employee, "attendance": attendance, "leave": leave, "expenses": expenses}
    except HTTPException:
        raise
    except psycopg.Error as exc:
        raise HTTPException(503, "Unable to load employee dashboard") from exc


@router.get("/attendance")
def employee_attendance(request: Request, limit: int = 60):
    if limit < 1 or limit > 180:
        raise HTTPException(422, "Attendance history limit must be between 1 and 180")
    try:
        with _connect() as conn:
            employee = _employee(conn, request)
            rows = conn.execute(
                "SELECT id,clock_in_at,clock_out_at,clock_in_note,clock_out_note,source "
                "FROM hr_attendance_sessions WHERE employee_id=%s ORDER BY clock_in_at DESC LIMIT %s",
                (employee["id"], limit),
            ).fetchall()
        return {"items": rows}
    except HTTPException:
        raise
    except psycopg.Error as exc:
        raise HTTPException(503, "Unable to load attendance history") from exc


@router.post("/attendance/punch")
def employee_punch(payload: PunchInput, request: Request):
    user_id = getattr(request.state, "user_id", None)
    try:
        with _connect() as conn:
            with conn.transaction():
                employee = _employee(conn, request)
                if payload.punch_type == "clock_in":
                    open_session = conn.execute(
                        "SELECT id FROM hr_attendance_sessions WHERE employee_id=%s AND clock_out_at IS NULL FOR UPDATE",
                        (employee["id"],),
                    ).fetchone()
                    if open_session:
                        raise HTTPException(409, "You are already clocked in")
                    row = conn.execute(
                        "INSERT INTO hr_attendance_sessions(employee_id,clock_in_note,source,created_by_user_id) "
                        "VALUES(%s,%s,'self_service',%s) RETURNING id,clock_in_at,clock_out_at",
                        (employee["id"],payload.note,user_id),
                    ).fetchone()
                else:
                    open_session = conn.execute(
                        "SELECT id FROM hr_attendance_sessions WHERE employee_id=%s AND clock_out_at IS NULL FOR UPDATE",
                        (employee["id"],),
                    ).fetchone()
                    if not open_session:
                        raise HTTPException(409, "You are not currently clocked in")
                    row = conn.execute(
                        "UPDATE hr_attendance_sessions SET clock_out_at=now(),clock_out_note=%s,closed_by_user_id=%s "
                        "WHERE id=%s RETURNING id,clock_in_at,clock_out_at",
                        (payload.note,user_id,open_session["id"]),
                    ).fetchone()
        return row
    except HTTPException:
        raise
    except psycopg.Error as exc:
        raise HTTPException(503, "Unable to record attendance punch") from exc


@router.get("/leave")
def employee_leave(request: Request):
    try:
        with _connect() as conn:
            employee = _employee(conn, request)
            rows = conn.execute(
                "SELECT id,leave_type,start_date,end_date,days,reason,status,review_note,reviewed_at,created_at "
                "FROM hr_leave_requests WHERE employee_id=%s ORDER BY created_at DESC",
                (employee["id"],),
            ).fetchall()
        return {"items": rows}
    except HTTPException:
        raise
    except psycopg.Error as exc:
        raise HTTPException(503, "Unable to load leave requests") from exc


@router.post("/leave", status_code=201)
def employee_apply_leave(payload: LeaveInput, request: Request):
    try:
        with _connect() as conn:
            with conn.transaction():
                employee = _employee(conn, request)
                overlap = conn.execute(
                    "SELECT id FROM hr_leave_requests WHERE employee_id=%s AND status IN ('pending','approved') "
                    "AND start_date<=%s AND end_date>=%s FOR SHARE",
                    (employee["id"],payload.end_date,payload.start_date),
                ).fetchone()
                if overlap:
                    raise HTTPException(409, "A pending or approved leave request already overlaps these dates")
                row = conn.execute(
                    "INSERT INTO hr_leave_requests(employee_id,leave_type,start_date,end_date,days,reason) "
                    "VALUES(%s,%s,%s,%s,%s,%s) RETURNING id,leave_type,start_date,end_date,days,reason,status,created_at",
                    (employee["id"],payload.leave_type,payload.start_date,payload.end_date,payload.days,payload.reason.strip()),
                ).fetchone()
        return row
    except HTTPException:
        raise
    except psycopg.Error as exc:
        raise HTTPException(503, "Unable to submit leave request") from exc


@router.get("/expenses")
def employee_expenses(request: Request):
    try:
        with _connect() as conn:
            employee = _employee(conn, request)
            rows = conn.execute(
                "SELECT id,category,amount,expense_date,description,receipt_reference,status,review_note,reviewed_at,created_at "
                "FROM hr_expenses WHERE employee_id=%s ORDER BY expense_date DESC,created_at DESC",
                (employee["id"],),
            ).fetchall()
        return {"items": rows}
    except HTTPException:
        raise
    except psycopg.Error as exc:
        raise HTTPException(503, "Unable to load reimbursement requests") from exc


@router.post("/expenses", status_code=201)
def employee_submit_expense(payload: ExpenseInput, request: Request):
    try:
        with _connect() as conn:
            with conn.transaction():
                employee = _employee(conn, request)
                row = conn.execute(
                    "INSERT INTO hr_expenses(employee_id,category,amount,expense_date,description,receipt_reference) "
                    "VALUES(%s,%s,%s,%s,%s,%s) RETURNING id,category,amount,expense_date,description,receipt_reference,status,created_at",
                    (employee["id"],payload.category.strip(),payload.amount,payload.expense_date,payload.description.strip(),payload.receipt_reference),
                ).fetchone()
        return row
    except HTTPException:
        raise
    except psycopg.Error as exc:
        raise HTTPException(503, "Unable to submit reimbursement request") from exc


@router.get("/payslips")
def employee_payslips(request: Request):
    try:
        with _connect() as conn:
            employee = _employee(conn, request)
            rows = conn.execute(
                "SELECT ps.id,pr.period_start,pr.period_end,pr.status AS payroll_status,ps.basic_salary,ps.hra,"
                "ps.special_allowance,ps.other_allowance,ps.reimbursements,ps.gross_earnings,ps.deductions,"
                "ps.net_pay,ps.deduction_breakdown,ps.earnings_breakdown,ps.created_at "
                "FROM hr_payslips ps JOIN hr_payroll_runs pr ON pr.id=ps.payroll_run_id "
                "WHERE ps.employee_id=%s AND pr.status IN ('approved','paid') "
                "ORDER BY pr.period_start DESC",
                (employee["id"],),
            ).fetchall()
        return {"items": rows}
    except HTTPException:
        raise
    except psycopg.Error as exc:
        raise HTTPException(503, "Unable to load payslips") from exc
