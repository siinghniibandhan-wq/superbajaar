"""Accounting foundation: chart of accounts, GST setup, journals and Profit & Loss.

Tables are created lazily by this module; no external migration or deployment changes.
Reports use posted journal lines only and never fabricate transactions.
"""
from datetime import date
from decimal import Decimal
from typing import Any

import psycopg
from fastapi import APIRouter, Header, HTTPException, Query
from pydantic import BaseModel, Field
from psycopg.rows import dict_row

from .auth import _require, _db

router = APIRouter(prefix="/api/accounting", tags=["accounting"])

ACCOUNT_TYPES = {
    "asset": ["cash", "bank", "accounts_receivable", "inventory", "input_gst", "fixed_asset", "deposit", "other_asset"],
    "liability": ["accounts_payable", "output_gst", "tds_payable", "loan", "accrual", "other_liability"],
    "equity": ["capital", "reserves", "retained_earnings"],
    "income": ["sales", "service_income", "other_income", "sales_returns", "discounts"],
    "expense": ["purchases", "cost_of_goods_sold", "freight", "salary", "rent", "utilities", "marketing", "depreciation", "bank_charges", "tax_expense", "other_expense"],
}
GST_RATES = [
    {"rate": 0, "label": "0%", "classification": "nil_rated"},
    {"rate": 5, "label": "5%", "classification": "taxable"},
    {"rate": 12, "label": "12%", "classification": "taxable"},
    {"rate": 18, "label": "18%", "classification": "taxable"},
    {"rate": 28, "label": "28%", "classification": "taxable"},
    {"rate": 0, "label": "Exempt", "classification": "exempt"},
    {"rate": 0, "label": "Non-GST", "classification": "non_gst"},
]

def _ensure(conn: Any) -> None:
    conn.execute("""
        CREATE TABLE IF NOT EXISTS sb_accounts (
            id BIGSERIAL PRIMARY KEY, code TEXT NOT NULL UNIQUE, name TEXT NOT NULL,
            account_type TEXT NOT NULL CHECK (account_type IN ('asset','liability','equity','income','expense')),
            detail_type TEXT NOT NULL, parent_id BIGINT REFERENCES sb_accounts(id),
            is_system BOOLEAN NOT NULL DEFAULT FALSE, is_active BOOLEAN NOT NULL DEFAULT TRUE,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS sb_gst_rates (
            id BIGSERIAL PRIMARY KEY, label TEXT NOT NULL, rate NUMERIC(5,2) NOT NULL,
            classification TEXT NOT NULL, is_active BOOLEAN NOT NULL DEFAULT TRUE,
            UNIQUE(label, classification)
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS sb_journals (
            id BIGSERIAL PRIMARY KEY, entry_date DATE NOT NULL, reference TEXT,
            description TEXT NOT NULL, source_module TEXT NOT NULL DEFAULT 'manual',
            source_id TEXT, status TEXT NOT NULL DEFAULT 'draft' CHECK (status IN ('draft','posted','void')),
            created_by BIGINT, created_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS sb_journal_lines (
            id BIGSERIAL PRIMARY KEY, journal_id BIGINT NOT NULL REFERENCES sb_journals(id) ON DELETE CASCADE,
            account_id BIGINT NOT NULL REFERENCES sb_accounts(id), debit NUMERIC(14,2) NOT NULL DEFAULT 0 CHECK (debit >= 0),
            credit NUMERIC(14,2) NOT NULL DEFAULT 0 CHECK (credit >= 0),
            description TEXT, CHECK (NOT (debit > 0 AND credit > 0))
        )
    """)
    for label, detail_types in ACCOUNT_TYPES.items():
        for detail in detail_types:
            code = f"{label[:3].upper()}-{detail.upper()}"
            conn.execute(
                """INSERT INTO sb_accounts(code,name,account_type,detail_type,is_system)
                   VALUES (%s,%s,%s,%s,TRUE) ON CONFLICT(code) DO NOTHING""",
                (code, detail.replace("_", " ").title(), label, detail),
            )
    for rate in GST_RATES:
        conn.execute(
            """INSERT INTO sb_gst_rates(label,rate,classification)
               VALUES (%s,%s,%s) ON CONFLICT(label,classification) DO NOTHING""",
            (rate["label"], rate["rate"], rate["classification"]),
        )

def _admin(authorization: str | None) -> dict[str, Any]:
    return _require(authorization, {"super_admin", "admin"})

class AccountInput(BaseModel):
    code: str = Field(min_length=1, max_length=30, pattern=r"^[A-Za-z0-9_-]+$")
    name: str = Field(min_length=1, max_length=120)
    account_type: str
    detail_type: str
    parent_id: int | None = None

class JournalLineInput(BaseModel):
    account_id: int = Field(gt=0)
    debit: Decimal = Field(default=Decimal("0"), ge=0)
    credit: Decimal = Field(default=Decimal("0"), ge=0)
    description: str = Field(default="", max_length=240)

class JournalInput(BaseModel):
    entry_date: date
    reference: str = Field(default="", max_length=100)
    description: str = Field(min_length=1, max_length=500)
    lines: list[JournalLineInput] = Field(min_length=2, max_length=200)

@router.get("/account-types")
def account_types() -> dict[str, Any]:
    return {"types": ACCOUNT_TYPES}

@router.get("/accounts")
def list_accounts(authorization: str | None = Header(default=None), include_inactive: bool = False) -> dict[str, Any]:
    _admin(authorization)
    try:
        with psycopg.connect(_db(), row_factory=dict_row, connect_timeout=8) as conn:
            _ensure(conn)
            where = "" if include_inactive else "WHERE is_active=TRUE"
            rows = conn.execute(f"SELECT id,code,name,account_type,detail_type,parent_id,is_system,is_active FROM sb_accounts {where} ORDER BY code").fetchall()
            return {"items": rows, "account_types": ACCOUNT_TYPES}
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=503, detail="Chart of accounts is temporarily unavailable") from exc

@router.post("/accounts", status_code=201)
def create_account(body: AccountInput, authorization: str | None = Header(default=None)) -> dict[str, Any]:
    _admin(authorization)
    if body.account_type not in ACCOUNT_TYPES or body.detail_type not in ACCOUNT_TYPES[body.account_type]:
        raise HTTPException(status_code=422, detail="Detail type does not belong to the selected account type")
    try:
        with psycopg.connect(_db(), row_factory=dict_row, connect_timeout=8) as conn:
            _ensure(conn)
            row = conn.execute(
                """INSERT INTO sb_accounts(code,name,account_type,detail_type,parent_id)
                   VALUES (%s,%s,%s,%s,%s)
                   RETURNING id,code,name,account_type,detail_type,parent_id,is_active""",
                (body.code.upper(), body.name.strip(), body.account_type, body.detail_type, body.parent_id),
            ).fetchone()
            return {"account": row}
    except psycopg.errors.UniqueViolation as exc:
        raise HTTPException(status_code=409, detail="Account code already exists") from exc
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=503, detail="Account could not be created") from exc

@router.get("/gst-rates")
def list_gst_rates(authorization: str | None = Header(default=None)) -> dict[str, Any]:
    _admin(authorization)
    try:
        with psycopg.connect(_db(), row_factory=dict_row, connect_timeout=8) as conn:
            _ensure(conn)
            return {"items": conn.execute("SELECT id,label,rate,classification,is_active FROM sb_gst_rates ORDER BY rate,label").fetchall()}
    except Exception as exc:
        raise HTTPException(status_code=503, detail="GST rate settings are temporarily unavailable") from exc

@router.post("/gst-rates", status_code=201)
def create_gst_rate(label: str, rate: Decimal = Query(ge=0, le=100), classification: str = Query(pattern="^(taxable|nil_rated|exempt|non_gst)$"), authorization: str | None = Header(default=None)) -> dict[str, Any]:
    _admin(authorization)
    try:
        with psycopg.connect(_db(), row_factory=dict_row, connect_timeout=8) as conn:
            _ensure(conn)
            row = conn.execute(
                """INSERT INTO sb_gst_rates(label,rate,classification) VALUES (%s,%s,%s)
                   ON CONFLICT(label,classification) DO UPDATE SET rate=EXCLUDED.rate,is_active=TRUE
                   RETURNING id,label,rate,classification,is_active""", (label.strip(), rate, classification)
            ).fetchone()
            return {"item": row}
    except Exception as exc:
        raise HTTPException(status_code=503, detail="GST rate could not be saved") from exc

@router.post("/journals", status_code=201)
def create_journal(body: JournalInput, authorization: str | None = Header(default=None)) -> dict[str, Any]:
    user = _admin(authorization)
    total_debit = sum((line.debit for line in body.lines), Decimal("0"))
    total_credit = sum((line.credit for line in body.lines), Decimal("0"))
    if total_debit <= 0 or total_debit != total_credit:
        raise HTTPException(status_code=422, detail="Journal must balance: total debits must equal total credits and be greater than zero")
    if any((line.debit == 0 and line.credit == 0) or (line.debit > 0 and line.credit > 0) for line in body.lines):
        raise HTTPException(status_code=422, detail="Each journal line must contain either a debit or a credit")
    try:
        with psycopg.connect(_db(), row_factory=dict_row, connect_timeout=8) as conn:
            _ensure(conn)
            journal = conn.execute(
                """INSERT INTO sb_journals(entry_date,reference,description,source_module,created_by)
                   VALUES (%s,%s,%s,'manual',%s) RETURNING id,entry_date,reference,description,status""",
                (body.entry_date, body.reference.strip() or None, body.description.strip(), user.get("id")),
            ).fetchone()
            for line in body.lines:
                exists = conn.execute("SELECT id FROM sb_accounts WHERE id=%s AND is_active=TRUE", (line.account_id,)).fetchone()
                if not exists:
                    raise HTTPException(status_code=422, detail=f"Account {line.account_id} is unavailable")
                conn.execute(
                    """INSERT INTO sb_journal_lines(journal_id,account_id,debit,credit,description)
                       VALUES (%s,%s,%s,%s,%s)""",
                    (journal["id"], line.account_id, line.debit, line.credit, line.description.strip() or None),
                )
            conn.execute("UPDATE sb_journals SET status='posted' WHERE id=%s", (journal["id"],))
            return {"journal": {**journal, "status": "posted"}, "total_debit": total_debit, "total_credit": total_credit}
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=503, detail="Journal could not be saved") from exc

@router.get("/journals")
def list_journals(start_date: date | None = None, end_date: date | None = None, authorization: str | None = Header(default=None)) -> dict[str, Any]:
    _admin(authorization)
    if start_date and end_date and end_date < start_date:
        raise HTTPException(status_code=422, detail="End date must be on or after start date")
    try:
        with psycopg.connect(_db(), row_factory=dict_row, connect_timeout=8) as conn:
            _ensure(conn)
            rows = conn.execute(
                """SELECT j.id,j.entry_date,j.reference,j.description,j.source_module,j.source_id,j.status,
                          COALESCE(SUM(l.debit),0) AS total_debit,COALESCE(SUM(l.credit),0) AS total_credit
                   FROM sb_journals j LEFT JOIN sb_journal_lines l ON l.journal_id=j.id
                   WHERE (%s::date IS NULL OR j.entry_date >= %s)
                     AND (%s::date IS NULL OR j.entry_date <= %s)
                   GROUP BY j.id ORDER BY j.entry_date DESC,j.id DESC LIMIT 500""",
                (start_date,start_date,end_date,end_date),
            ).fetchall()
            return {"items": rows}
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=503, detail="Journal register is temporarily unavailable") from exc

@router.get("/profit-loss")
def profit_loss(start_date: date = Query(...), end_date: date = Query(...), authorization: str | None = Header(default=None)) -> dict[str, Any]:
    _admin(authorization)
    if end_date < start_date:
        raise HTTPException(status_code=422, detail="End date must be on or after start date")
    try:
        with psycopg.connect(_db(), row_factory=dict_row, connect_timeout=8) as conn:
            _ensure(conn)
            rows = conn.execute(
                """SELECT a.id,a.code,a.name,a.account_type,a.detail_type,
                          COALESCE(SUM(l.credit-l.debit),0) AS net_credit,
                          COALESCE(SUM(l.debit-l.credit),0) AS net_debit
                   FROM sb_accounts a
                   LEFT JOIN sb_journal_lines l ON l.account_id=a.id
                   LEFT JOIN sb_journals j ON j.id=l.journal_id AND j.status='posted' AND j.entry_date BETWEEN %s AND %s
                   WHERE a.account_type IN ('income','expense') AND a.is_active=TRUE
                   GROUP BY a.id ORDER BY a.account_type,a.code""", (start_date, end_date)
            ).fetchall()
            income = []
            expenses = []
            for row in rows:
                # Exclude journal lines whose parent journal was outside the requested period.
                item = dict(row)
                if row["account_type"] == "income":
                    amount = conn.execute(
                        """SELECT COALESCE(SUM(l.credit-l.debit),0) AS amount
                           FROM sb_journal_lines l JOIN sb_journals j ON j.id=l.journal_id
                           WHERE l.account_id=%s AND j.status='posted' AND j.entry_date BETWEEN %s AND %s""",
                        (row["id"], start_date, end_date),
                    ).fetchone()["amount"]
                    if amount: income.append({**item, "amount": amount})
                else:
                    amount = conn.execute(
                        """SELECT COALESCE(SUM(l.debit-l.credit),0) AS amount
                           FROM sb_journal_lines l JOIN sb_journals j ON j.id=l.journal_id
                           WHERE l.account_id=%s AND j.status='posted' AND j.entry_date BETWEEN %s AND %s""",
                        (row["id"], start_date, end_date),
                    ).fetchone()["amount"]
                    if amount: expenses.append({**item, "amount": amount})
            total_income = sum((Decimal(str(x["amount"])) for x in income), Decimal("0"))
            total_expenses = sum((Decimal(str(x["amount"])) for x in expenses), Decimal("0"))
            return {"start_date": start_date, "end_date": end_date, "income": income, "expenses": expenses,
                    "total_income": total_income, "total_expenses": total_expenses,
                    "net_profit": total_income-total_expenses,
                    "basis": "posted_journals_only", "note": "Sales, purchases and payroll appear only after their source workflows post balanced journals."}
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=503, detail="Profit & Loss report is temporarily unavailable") from exc
