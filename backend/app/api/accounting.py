"""Accounting & Tax API: double-entry ledger, vouchers, GST invoices, reports,
bank reconciliation, period lock and automatic posting of operational records.

Requires backend/schema/015_accounting_ledger.sql. Posted vouchers are immutable;
corrections are made with reversal vouchers. Read access: owner, admin, manager.
Write access: owner and admin (enforced by the auth middleware). Changing the
period lock date is owner-only.

GST figures are bookkeeping aids for return preparation. They are not a filed
GSTR-1/GSTR-3B and must be reviewed by the business's tax professional.
"""
from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime
from decimal import ROUND_HALF_UP, Decimal
from zoneinfo import ZoneInfo

import psycopg
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from psycopg.rows import dict_row
from pydantic import BaseModel, Field, field_validator, model_validator

from app.core.auth_middleware import require_active_session
from app.core.config import settings

IST = ZoneInfo("Asia/Kolkata")
ZERO = Decimal("0.00")
CENT = Decimal("0.01")
READ_ROLES = {"owner", "admin", "manager"}

ACCOUNT_TYPES = {"asset", "liability", "equity", "income", "expense"}
SUB_TYPES = {
    "asset": {"cash", "bank", "receivable", "inventory", "tax_input", "current_asset", "fixed_asset", "general"},
    "liability": {"payable", "tax_output", "statutory", "current_liability", "loan", "general"},
    "equity": {"capital", "drawings", "retained_earnings", "opening", "general"},
    "income": {"sales", "sales_return", "other_income", "general"},
    "expense": {"cogs", "direct", "operating", "general"},
}
DEBIT_NORMAL = {"asset", "expense"}
VOUCHER_PREFIX = {
    "journal": "JV", "sales": "SI", "purchase": "PI", "receipt": "RV", "payment": "PV",
    "contra": "CT", "expense": "EX", "credit_note": "CN", "debit_note": "DN",
    "opening": "OB", "reversal": "RJ",
}
MANUAL_TYPES = {"journal", "receipt", "payment", "contra", "expense", "opening"}
INVOICE_TYPES = {"sales", "purchase", "credit_note", "debit_note"}
GST_RATES = {Decimal(x) for x in ("0", "0.1", "0.25", "1", "1.5", "3", "5", "6", "7.5", "12", "18", "28", "40")}
PARTY_TYPES = {"customer", "supplier", "employee", "other"}

# System account codes seeded by migration 015.
A_CASH, A_BANK, A_UPI, A_CARD = "1000", "1010", "1020", "1030"
A_AR, A_INVENTORY = "1100", "1200"
A_IN_CGST, A_IN_SGST, A_IN_IGST = "1300", "1301", "1302"
A_AP, A_GRNI = "2000", "2050"
A_OUT_CGST, A_OUT_SGST, A_OUT_IGST = "2100", "2101", "2102"
A_OPENING = "3900"
A_SALES, A_SALES_RETURN, A_OTHER_CHARGES, A_ROUND_OFF = "4000", "4010", "4100", "4900"
A_COGS, A_DISCOUNT = "5000", "5100"
SETTLEMENT_ACCOUNTS = {"cash": A_CASH, "bank": A_BANK, "upi": A_UPI, "card": A_CARD}
PAYMENT_METHOD_ACCOUNTS = {
    "cod": A_CASH, "other": A_CASH, "upi": A_UPI, "wallet": A_UPI,
    "card": A_CARD, "netbanking": A_BANK, "bank_transfer": A_BANK,
}
ORDER_POSTABLE = ("placed", "confirmed", "processing", "ready_for_dispatch", "dispatched", "delivered")


def require_accounting_reader(request: Request, _session: None = Depends(require_active_session)) -> None:
    """Accounting data is financial; restrict reads to owner/admin/manager.

    Depends on the session dependency explicitly so the role is always resolved first
    (FastAPI caches it, so the session check still runs once per request).
    """
    if not settings.database_url:
        return  # handlers return their explicit 503 when storage is not configured
    role = getattr(request.state, "role", None)
    if role not in READ_ROLES:
        raise HTTPException(403, "Accounting is restricted to owner, admin and manager roles")


router = APIRouter(prefix="/accounting", tags=["accounting"], dependencies=[Depends(require_accounting_reader)])


# ---------------------------------------------------------------------------
# Infrastructure helpers
# ---------------------------------------------------------------------------

def _connect():
    if not settings.database_url:
        raise HTTPException(503, "Accounting database is not configured")
    try:
        return psycopg.connect(settings.database_url, row_factory=dict_row, connect_timeout=3)
    except psycopg.Error as exc:
        raise HTTPException(503, "Accounting database is unavailable") from exc


def _db_error(exc: psycopg.Error) -> HTTPException:
    state = getattr(exc, "sqlstate", None)
    if state == "23505":
        return HTTPException(409, "An accounting record with this code, number or reference already exists")
    if state == "23503":
        return HTTPException(422, "A referenced account or voucher does not exist")
    if state == "23514":
        return HTTPException(422, "The entry violates an accounting rule (balanced, immutable, positive amounts)")
    if state in {"42P01", "42703"}:
        return HTTPException(503, "Accounting storage is not ready; apply migration 015_accounting_ledger.sql")
    return HTTPException(503, "Accounting storage unavailable; verify migration 015")


def _money(value) -> Decimal:
    return Decimal(value or 0).quantize(CENT, rounding=ROUND_HALF_UP)


def _today() -> date:
    return datetime.now(IST).date()


def fiscal_year(day: date) -> str:
    """Indian financial year label, April-March, e.g. 2026-27."""
    start = day.year if day.month >= 4 else day.year - 1
    return f"{start}-{(start + 1) % 100:02d}"


def fiscal_year_start(day: date) -> date:
    return date(day.year if day.month >= 4 else day.year - 1, 4, 1)


def split_gst(taxable: Decimal, rate: Decimal, supply: str) -> dict[str, Decimal]:
    """Return GST components for a taxable value; intra-state splits CGST/SGST equally."""
    tax = _money(taxable * rate / Decimal(100))
    if supply == "inter":
        return {"igst": tax}
    cgst = _money(tax / 2)
    return {"cgst": cgst, "sgst": tax - cgst}


def inclusive_split(gross: Decimal, rate: Decimal) -> tuple[Decimal, Decimal]:
    """Split a tax-inclusive amount into (taxable value, tax)."""
    gross = _money(gross)
    if rate <= 0:
        return gross, ZERO
    taxable = _money(gross * Decimal(100) / (Decimal(100) + rate))
    return taxable, gross - taxable


def _actor(request: Request) -> tuple[int | None, str | None]:
    return getattr(request.state, "user_id", None), getattr(request.state, "user_email", None)


def _settings_row(conn) -> dict:
    row = conn.execute(
        "SELECT business_name, gstin, state_code, default_supply, lock_date, updated_by_email, updated_at "
        "FROM accounting_settings WHERE id=1"
    ).fetchone()
    return row or {"business_name": "Super Bajaar", "gstin": None, "state_code": None, "default_supply": "intra", "lock_date": None}


def _accounts_by_code(conn, codes) -> dict[str, dict]:
    rows = conn.execute(
        "SELECT id, code, name, account_type, sub_type, is_active FROM accounting_accounts WHERE code = ANY(%s)",
        (list(codes),),
    ).fetchall()
    found = {row["code"]: row for row in rows}
    missing = set(codes) - set(found)
    if missing:
        raise HTTPException(503, "System accounts are missing (" + ", ".join(sorted(missing)) + "); verify migration 015")
    return found


def _check_unlocked(conn, voucher_date: date) -> None:
    lock = _settings_row(conn).get("lock_date")
    if lock and voucher_date <= lock:
        raise HTTPException(409, f"Books are locked up to {lock.isoformat()}; choose a later date or ask the owner to change the lock date")


def _next_number(conn, voucher_type: str, voucher_date: date) -> str:
    fy = fiscal_year(voucher_date)
    row = conn.execute(
        "INSERT INTO accounting_voucher_sequences (voucher_type, fiscal_year, last_number) VALUES (%s, %s, 1) "
        "ON CONFLICT (voucher_type, fiscal_year) DO UPDATE SET last_number = accounting_voucher_sequences.last_number + 1 "
        "RETURNING last_number",
        (voucher_type, fy),
    ).fetchone()
    return f"{VOUCHER_PREFIX[voucher_type]}/{fy}/{row['last_number']:05d}"


def _find_idempotent(conn, key: str | None):
    if not key:
        return None
    return conn.execute("SELECT id FROM accounting_vouchers WHERE idempotency_key=%s", (key,)).fetchone()


def _post_voucher(conn, header: dict, lines: list[dict], actor: tuple[int | None, str | None]) -> int:
    """Insert one balanced voucher with its lines inside the caller's transaction."""
    lines = [line for line in lines if _money(line.get("debit")) > 0 or _money(line.get("credit")) > 0]
    debit = sum((_money(line.get("debit")) for line in lines), ZERO)
    credit = sum((_money(line.get("credit")) for line in lines), ZERO)
    if len(lines) < 2 or debit != credit or debit <= 0:
        raise HTTPException(422, f"Voucher must balance with at least two lines (debit {debit}, credit {credit})")
    _check_unlocked(conn, header["voucher_date"])
    account_ids = sorted({int(line["account_id"]) for line in lines})
    accounts = conn.execute(
        "SELECT id, is_active FROM accounting_accounts WHERE id = ANY(%s) FOR SHARE", (account_ids,)
    ).fetchall()
    active = {row["id"] for row in accounts if row["is_active"]}
    if len(active) != len(account_ids):
        raise HTTPException(422, "One or more accounts are missing or inactive")
    number = _next_number(conn, header["voucher_type"], header["voucher_date"])
    conn.execute("SET CONSTRAINTS accounting_vouchers_balance_trg, accounting_voucher_lines_balance_trg DEFERRED")
    row = conn.execute(
        "INSERT INTO accounting_vouchers (voucher_number, voucher_type, voucher_date, narration, reference, party_type, "
        "party_name, party_gstin, place_of_supply, due_date, taxable_total, tax_total, total_amount, source_type, source_id, "
        "idempotency_key, reversal_of_id, created_by_user_id, created_by_email) "
        "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING id",
        (
            number, header["voucher_type"], header["voucher_date"], header.get("narration"), header.get("reference"),
            header.get("party_type"), header.get("party_name"), header.get("party_gstin"), header.get("place_of_supply"),
            header.get("due_date"), _money(header.get("taxable_total")), _money(header.get("tax_total")),
            _money(header["total_amount"]) if header.get("total_amount") else debit,
            header.get("source_type"), header.get("source_id"), header.get("idempotency_key"), header.get("reversal_of_id"),
            actor[0], actor[1],
        ),
    ).fetchone()
    for index, line in enumerate(lines, start=1):
        conn.execute(
            "INSERT INTO accounting_voucher_lines (voucher_id, line_no, account_id, debit, credit, narration, hsn_sac, "
            "quantity, unit_rate, gst_rate, tax_component) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
            (
                row["id"], index, int(line["account_id"]), _money(line.get("debit")), _money(line.get("credit")),
                line.get("narration"), line.get("hsn_sac"), line.get("quantity"), line.get("unit_rate"),
                line.get("gst_rate"), line.get("tax_component"),
            ),
        )
    # Run the database balance check now so a failure is attributed to this voucher.
    conn.execute("SET CONSTRAINTS accounting_vouchers_balance_trg, accounting_voucher_lines_balance_trg IMMEDIATE")
    return row["id"]


def _voucher_detail(conn, voucher_id: int) -> dict:
    voucher = conn.execute("SELECT * FROM accounting_vouchers WHERE id=%s", (voucher_id,)).fetchone()
    if not voucher:
        raise HTTPException(404, "Voucher not found")
    voucher["lines"] = conn.execute(
        "SELECT l.id, l.line_no, l.account_id, a.code AS account_code, a.name AS account_name, a.account_type, a.sub_type, "
        "l.debit, l.credit, l.narration, l.hsn_sac, l.quantity, l.unit_rate, l.gst_rate, l.tax_component, "
        "l.reconciled_on, l.bank_reference FROM accounting_voucher_lines l JOIN accounting_accounts a ON a.id=l.account_id "
        "WHERE l.voucher_id=%s ORDER BY l.line_no",
        (voucher_id,),
    ).fetchall()
    return voucher


def _signed(row: dict) -> Decimal:
    """Balance in the account's natural direction (positive = normal side)."""
    net = _money(row["debit"]) - _money(row["credit"])
    return net if row["account_type"] in DEBIT_NORMAL else -net


def _balances(conn, to_date: date, from_date: date | None = None, only_active: bool = False) -> list[dict]:
    params: list = []
    date_clause = "v.voucher_date <= %s"
    params.append(to_date)
    if from_date:
        date_clause += " AND v.voucher_date >= %s"
        params.append(from_date)
    where = " WHERE a.is_active" if only_active else ""
    return conn.execute(
        "SELECT a.id, a.code, a.name, a.account_type, a.sub_type, a.is_active, a.is_system, "
        "COALESCE(sum(x.debit), 0) AS debit, COALESCE(sum(x.credit), 0) AS credit FROM accounting_accounts a "
        "LEFT JOIN (SELECT l.account_id, l.debit, l.credit FROM accounting_voucher_lines l JOIN accounting_vouchers v "
        "ON v.id=l.voucher_id WHERE " + date_clause + ") x ON x.account_id=a.id" + where +
        " GROUP BY a.id ORDER BY a.code",
        params,
    ).fetchall()


def _period(from_date: date | None, to_date: date | None) -> tuple[date, date]:
    end = to_date or _today()
    start = from_date or fiscal_year_start(end)
    if start > end:
        raise HTTPException(422, "From date must be on or before the to date")
    if (end - start).days > 3660:
        raise HTTPException(422, "Reporting period cannot exceed 10 years")
    return start, end


# ---------------------------------------------------------------------------
# Request models
# ---------------------------------------------------------------------------

def _clean(value: str | None) -> str | None:
    if value is None:
        return None
    value = value.strip()
    return value or None


def _valid_gstin(value: str | None) -> str | None:
    value = _clean(value)
    if value is None:
        return None
    value = value.upper()
    if (len(value) != 15 or not value[:2].isdigit() or not value[2:7].isalpha() or not value[7:11].isdigit()
            or not value[11].isalpha() or not value[12].isalnum() or not value[13].isalnum() or not value[14].isalnum()):
        raise ValueError("Enter a GSTIN in the expected 15-character format")
    return value


class AccountCreate(BaseModel):
    code: str = Field(min_length=1, max_length=20)
    name: str = Field(min_length=1, max_length=160)
    account_type: str
    sub_type: str = "general"
    parent_id: int | None = Field(default=None, gt=0)
    description: str | None = Field(default=None, max_length=500)

    @field_validator("code")
    @classmethod
    def valid_code(cls, value):
        value = value.strip().upper()
        if not value or not all(ch.isalnum() or ch == "-" for ch in value) or not value[0].isalnum():
            raise ValueError("Account code may contain letters, digits and hyphens only")
        return value

    @field_validator("name")
    @classmethod
    def valid_name(cls, value):
        if not value.strip():
            raise ValueError("Account name cannot be blank")
        return value.strip()

    @model_validator(mode="after")
    def valid_type(self):
        if self.account_type not in ACCOUNT_TYPES:
            raise ValueError("Account type must be asset, liability, equity, income or expense")
        if self.sub_type not in SUB_TYPES[self.account_type]:
            raise ValueError("Unsupported sub-type for this account type")
        return self


class AccountUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=160)
    description: str | None = Field(default=None, max_length=500)
    is_active: bool | None = None


class VoucherLineIn(BaseModel):
    account_id: int = Field(gt=0)
    debit: Decimal = Field(default=ZERO, ge=0, max_digits=16, decimal_places=2)
    credit: Decimal = Field(default=ZERO, ge=0, max_digits=16, decimal_places=2)
    narration: str | None = Field(default=None, max_length=300)

    @model_validator(mode="after")
    def one_side(self):
        if (self.debit > 0) == (self.credit > 0):
            raise ValueError("Each line needs either a debit or a credit amount, not both")
        return self


class VoucherCreate(BaseModel):
    voucher_type: str
    voucher_date: date
    narration: str | None = Field(default=None, max_length=1000)
    reference: str | None = Field(default=None, max_length=100)
    party_type: str | None = None
    party_name: str | None = Field(default=None, max_length=200)
    due_date: date | None = None
    idempotency_key: str | None = Field(default=None, min_length=8, max_length=100)
    lines: list[VoucherLineIn] = Field(min_length=2, max_length=200)

    @field_validator("voucher_type")
    @classmethod
    def valid_type(cls, value):
        if value not in MANUAL_TYPES:
            raise ValueError("Use journal, receipt, payment, contra, expense or opening; invoices use /accounting/invoices")
        return value

    @field_validator("party_type")
    @classmethod
    def valid_party_type(cls, value):
        if value is not None and value not in PARTY_TYPES:
            raise ValueError("Unsupported party type")
        return value

    @model_validator(mode="after")
    def balanced(self):
        debit = sum((line.debit for line in self.lines), ZERO)
        credit = sum((line.credit for line in self.lines), ZERO)
        if debit != credit:
            raise ValueError(f"Total debit {debit} must equal total credit {credit}")
        if self.due_date and self.due_date < self.voucher_date:
            raise ValueError("Due date cannot be before the voucher date")
        return self


class InvoiceLineIn(BaseModel):
    description: str = Field(min_length=1, max_length=300)
    account_id: int | None = Field(default=None, gt=0)
    hsn_sac: str | None = Field(default=None, max_length=8)
    quantity: Decimal = Field(default=Decimal("1"), gt=0, max_digits=14, decimal_places=3)
    rate: Decimal = Field(ge=0, max_digits=14, decimal_places=2)
    discount: Decimal = Field(default=ZERO, ge=0, max_digits=14, decimal_places=2)
    gst_rate: Decimal = Field(default=ZERO, ge=0, le=40)

    @field_validator("hsn_sac")
    @classmethod
    def valid_hsn(cls, value):
        value = _clean(value)
        if value and (not value.isdigit() or len(value) not in {4, 6, 8}):
            raise ValueError("HSN/SAC must be 4, 6 or 8 digits")
        return value

    @field_validator("gst_rate")
    @classmethod
    def valid_rate(cls, value):
        if value.normalize() not in {r.normalize() for r in GST_RATES}:
            raise ValueError("Unsupported GST rate")
        return value

    @model_validator(mode="after")
    def positive_value(self):
        if _money(self.quantity * self.rate) - self.discount < 0:
            raise ValueError("Discount cannot exceed the line value")
        return self


class InvoiceCreate(BaseModel):
    invoice_type: str
    voucher_date: date
    party_name: str = Field(min_length=1, max_length=200)
    party_gstin: str | None = None
    place_of_supply: str = "intra"
    settlement: str = "credit"
    against_receipt: bool = False
    round_off: bool = True
    reference: str | None = Field(default=None, max_length=100)
    due_date: date | None = None
    narration: str | None = Field(default=None, max_length=1000)
    idempotency_key: str | None = Field(default=None, min_length=8, max_length=100)
    lines: list[InvoiceLineIn] = Field(min_length=1, max_length=200)

    @field_validator("invoice_type")
    @classmethod
    def valid_type(cls, value):
        if value not in INVOICE_TYPES:
            raise ValueError("Invoice type must be sales, purchase, credit_note or debit_note")
        return value

    @field_validator("party_name")
    @classmethod
    def valid_party(cls, value):
        if not value.strip():
            raise ValueError("Party name cannot be blank")
        return value.strip()

    @field_validator("party_gstin")
    @classmethod
    def valid_gstin(cls, value):
        return _valid_gstin(value)

    @field_validator("place_of_supply")
    @classmethod
    def valid_supply(cls, value):
        if value not in {"intra", "inter"}:
            raise ValueError("Place of supply must be intra (CGST+SGST) or inter (IGST)")
        return value

    @field_validator("settlement")
    @classmethod
    def valid_settlement(cls, value):
        if value not in {"credit", *SETTLEMENT_ACCOUNTS}:
            raise ValueError("Settlement must be credit, cash, bank, upi or card")
        return value

    @model_validator(mode="after")
    def consistent(self):
        if self.against_receipt and self.invoice_type != "purchase":
            raise ValueError("Goods-received clearing applies to purchase bills only")
        if self.due_date and self.due_date < self.voucher_date:
            raise ValueError("Due date cannot be before the invoice date")
        return self


class ReverseRequest(BaseModel):
    reason: str = Field(min_length=5, max_length=500)
    reversal_date: date | None = None

    @field_validator("reason")
    @classmethod
    def valid_reason(cls, value):
        if len(value.strip()) < 5:
            raise ValueError("Give a reason of at least five characters")
        return value.strip()


class ReconcileRequest(BaseModel):
    reconciled_on: date | None = None
    bank_reference: str | None = Field(default=None, max_length=100)


class SettingsUpdate(BaseModel):
    business_name: str = Field(min_length=1, max_length=200)
    gstin: str | None = None
    state_code: str | None = Field(default=None, max_length=2)
    default_supply: str = "intra"
    lock_date: date | None = None

    @field_validator("gstin")
    @classmethod
    def valid_gstin(cls, value):
        return _valid_gstin(value)

    @field_validator("state_code")
    @classmethod
    def valid_state(cls, value):
        value = _clean(value)
        if value and (len(value) != 2 or not value.isdigit()):
            raise ValueError("State code must be the two-digit GST state code")
        return value

    @field_validator("default_supply")
    @classmethod
    def valid_supply(cls, value):
        if value not in {"intra", "inter"}:
            raise ValueError("Default supply must be intra or inter")
        return value

    @model_validator(mode="after")
    def gstin_matches_state(self):
        if self.gstin and self.state_code and self.gstin[:2] != self.state_code:
            raise ValueError("The first two digits of the GSTIN must match the state code")
        return self


# ---------------------------------------------------------------------------
# Settings
# ---------------------------------------------------------------------------

@router.get("/settings")
def get_settings():
    try:
        with _connect() as conn:
            return _settings_row(conn)
    except psycopg.Error as exc:
        raise _db_error(exc) from exc


@router.put("/settings")
def update_settings(payload: SettingsUpdate, request: Request):
    try:
        with _connect() as conn:
            with conn.transaction():
                current = conn.execute("SELECT lock_date FROM accounting_settings WHERE id=1 FOR UPDATE").fetchone()
                if current is None:
                    raise HTTPException(503, "Accounting settings row is missing; verify migration 015")
                if current["lock_date"] != payload.lock_date and getattr(request.state, "role", None) != "owner":
                    raise HTTPException(403, "Only the owner can change the books lock date")
                return conn.execute(
                    "UPDATE accounting_settings SET business_name=%s, gstin=%s, state_code=%s, default_supply=%s, lock_date=%s, "
                    "updated_by_email=%s, updated_at=now() WHERE id=1 RETURNING business_name, gstin, state_code, default_supply, "
                    "lock_date, updated_by_email, updated_at",
                    (payload.business_name.strip(), payload.gstin, payload.state_code, payload.default_supply, payload.lock_date,
                     _actor(request)[1]),
                ).fetchone()
    except HTTPException:
        raise
    except psycopg.Error as exc:
        raise _db_error(exc) from exc


# ---------------------------------------------------------------------------
# Chart of accounts
# ---------------------------------------------------------------------------

@router.get("/accounts")
def list_accounts(include_inactive: bool = False, as_of: date | None = None):
    try:
        with _connect() as conn:
            rows = _balances(conn, as_of or _today(), only_active=not include_inactive)
            meta = {r["id"]: r for r in conn.execute("SELECT id, parent_id, description FROM accounting_accounts").fetchall()}
            items = [{**row, "balance": _signed(row), "parent_id": meta.get(row["id"], {}).get("parent_id"),
                      "description": meta.get(row["id"], {}).get("description")} for row in rows]
            return {"items": items, "sub_types": {k: sorted(v) for k, v in SUB_TYPES.items()}}
    except psycopg.Error as exc:
        raise _db_error(exc) from exc


@router.post("/accounts", status_code=201)
def create_account(payload: AccountCreate):
    try:
        with _connect() as conn:
            with conn.transaction():
                if payload.parent_id:
                    parent = conn.execute("SELECT account_type FROM accounting_accounts WHERE id=%s", (payload.parent_id,)).fetchone()
                    if not parent:
                        raise HTTPException(422, "Parent account does not exist")
                    if parent["account_type"] != payload.account_type:
                        raise HTTPException(422, "A sub-account must have the same type as its parent")
                return conn.execute(
                    "INSERT INTO accounting_accounts (code, name, account_type, sub_type, parent_id, description) "
                    "VALUES (%s,%s,%s,%s,%s,%s) RETURNING id, code, name, account_type, sub_type, parent_id, description, "
                    "is_system, is_active, created_at",
                    (payload.code, payload.name, payload.account_type, payload.sub_type, payload.parent_id, _clean(payload.description)),
                ).fetchone()
    except HTTPException:
        raise
    except psycopg.Error as exc:
        raise _db_error(exc) from exc


@router.patch("/accounts/{account_id}")
def update_account(account_id: int, payload: AccountUpdate):
    try:
        with _connect() as conn:
            with conn.transaction():
                account = conn.execute("SELECT * FROM accounting_accounts WHERE id=%s FOR UPDATE", (account_id,)).fetchone()
                if not account:
                    raise HTTPException(404, "Account not found")
                if payload.is_active is False and account["is_system"]:
                    raise HTTPException(409, "System accounts are used by automatic postings and cannot be deactivated")
                name = payload.name.strip() if payload.name and payload.name.strip() else account["name"]
                description = _clean(payload.description) if payload.description is not None else account["description"]
                active = account["is_active"] if payload.is_active is None else payload.is_active
                return conn.execute(
                    "UPDATE accounting_accounts SET name=%s, description=%s, is_active=%s, updated_at=now() WHERE id=%s "
                    "RETURNING id, code, name, account_type, sub_type, parent_id, description, is_system, is_active, updated_at",
                    (name, description, active, account_id),
                ).fetchone()
    except HTTPException:
        raise
    except psycopg.Error as exc:
        raise _db_error(exc) from exc


# ---------------------------------------------------------------------------
# Vouchers
# ---------------------------------------------------------------------------

@router.get("/vouchers")
def list_vouchers(
    voucher_type: str | None = None,
    from_date: date | None = None,
    to_date: date | None = None,
    search: str | None = Query(default=None, max_length=200),
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
):
    if voucher_type and voucher_type not in VOUCHER_PREFIX:
        raise HTTPException(422, "Unsupported voucher type")
    clauses, params = [], []
    if voucher_type:
        clauses.append("voucher_type=%s"); params.append(voucher_type)
    if from_date:
        clauses.append("voucher_date>=%s"); params.append(from_date)
    if to_date:
        clauses.append("voucher_date<=%s"); params.append(to_date)
    if search and search.strip():
        term = "%" + search.strip() + "%"
        clauses.append("(voucher_number ILIKE %s OR COALESCE(party_name,'') ILIKE %s OR COALESCE(reference,'') ILIKE %s OR COALESCE(narration,'') ILIKE %s)")
        params.extend([term] * 4)
    where = (" WHERE " + " AND ".join(clauses)) if clauses else ""
    try:
        with _connect() as conn:
            items = conn.execute(
                "SELECT id, voucher_number, voucher_type, voucher_date, status, narration, reference, party_type, party_name, "
                "party_gstin, total_amount, taxable_total, tax_total, source_type, source_id, reversal_of_id, "
                "reversed_by_voucher_id, created_by_email, created_at FROM accounting_vouchers" + where +
                " ORDER BY voucher_date DESC, id DESC LIMIT %s OFFSET %s",
                (*params, limit, offset),
            ).fetchall()
            total = conn.execute("SELECT count(*) AS total FROM accounting_vouchers" + where, params).fetchone()["total"]
        return {"items": items, "total": total, "limit": limit, "offset": offset}
    except psycopg.Error as exc:
        raise _db_error(exc) from exc


@router.get("/vouchers/{voucher_id}")
def get_voucher(voucher_id: int):
    try:
        with _connect() as conn:
            voucher = _voucher_detail(conn, voucher_id)
            voucher["business"] = _settings_row(conn)
            return voucher
    except HTTPException:
        raise
    except psycopg.Error as exc:
        raise _db_error(exc) from exc


def _validate_manual_rules(payload: VoucherCreate, accounts: dict[int, dict]) -> None:
    subs = {aid: accounts[aid]["sub_type"] for aid in accounts}
    money = {"cash", "bank"}
    debit_money = any(subs[l.account_id] in money for l in payload.lines if l.debit > 0)
    credit_money = any(subs[l.account_id] in money for l in payload.lines if l.credit > 0)
    if payload.voucher_type == "contra" and any(subs[l.account_id] not in money for l in payload.lines):
        raise HTTPException(422, "A contra entry moves money between cash and bank accounts only")
    if payload.voucher_type == "receipt" and not debit_money:
        raise HTTPException(422, "A receipt must debit a cash or bank account")
    if payload.voucher_type == "payment" and not credit_money:
        raise HTTPException(422, "A payment must credit a cash or bank account")
    if payload.voucher_type == "expense" and not any(accounts[l.account_id]["account_type"] == "expense" for l in payload.lines if l.debit > 0):
        raise HTTPException(422, "An expense voucher must debit at least one expense account")


@router.post("/vouchers", status_code=201)
def create_voucher(payload: VoucherCreate, request: Request):
    try:
        with _connect() as conn:
            with conn.transaction():
                existing = _find_idempotent(conn, payload.idempotency_key)
                if existing:
                    return {**_voucher_detail(conn, existing["id"]), "idempotent_replay": True}
                ids = sorted({line.account_id for line in payload.lines})
                accounts = {row["id"]: row for row in conn.execute(
                    "SELECT id, account_type, sub_type, is_active FROM accounting_accounts WHERE id = ANY(%s)", (ids,)
                ).fetchall()}
                if len(accounts) != len(ids) or not all(row["is_active"] for row in accounts.values()):
                    raise HTTPException(422, "One or more accounts are missing or inactive")
                _validate_manual_rules(payload, accounts)
                voucher_id = _post_voucher(conn, {
                    "voucher_type": payload.voucher_type, "voucher_date": payload.voucher_date,
                    "narration": _clean(payload.narration), "reference": _clean(payload.reference),
                    "party_type": payload.party_type, "party_name": _clean(payload.party_name),
                    "due_date": payload.due_date, "idempotency_key": payload.idempotency_key,
                }, [line.model_dump() for line in payload.lines], _actor(request))
                return _voucher_detail(conn, voucher_id)
    except HTTPException:
        raise
    except psycopg.Error as exc:
        raise _db_error(exc) from exc


def build_invoice_lines(payload: InvoiceCreate, codes: dict[str, dict], line_accounts: dict[int, dict]) -> tuple[list[dict], Decimal, Decimal]:
    """Translate a GST invoice into balanced ledger lines. Returns (lines, taxable_total, tax_total)."""
    kind = payload.invoice_type
    is_sales_side = kind in {"sales", "credit_note"}
    # Sales and debit notes credit the item accounts; purchases and credit notes debit them.
    item_side = "credit" if kind in {"sales", "debit_note"} else "debit"
    party_side = "debit" if item_side == "credit" else "credit"
    if is_sales_side:
        default_item = A_SALES if kind == "sales" else A_SALES_RETURN
        tax_codes = {"cgst": A_OUT_CGST, "sgst": A_OUT_SGST, "igst": A_OUT_IGST}
        party_code = A_AR
    else:
        default_item = A_GRNI if payload.against_receipt else A_INVENTORY
        tax_codes = {"cgst": A_IN_CGST, "sgst": A_IN_SGST, "igst": A_IN_IGST}
        party_code = A_AP
    if payload.settlement != "credit":
        party_code = SETTLEMENT_ACCOUNTS[payload.settlement]

    lines: list[dict] = []
    taxable_total = ZERO
    tax_by_component: dict[tuple[str, Decimal], Decimal] = defaultdict(lambda: ZERO)
    for item in payload.lines:
        taxable = _money(item.quantity * item.rate) - _money(item.discount)
        if item.account_id:
            account = line_accounts[item.account_id]
            allowed = {"income"} if is_sales_side else {"asset", "expense", "liability"}
            if account["account_type"] not in allowed:
                raise HTTPException(422, f"Account {account['code']} cannot be used on this invoice type")
            account_id = item.account_id
        else:
            account_id = codes[default_item]["id"]
        taxable_total += taxable
        if taxable > 0:
            lines.append({"account_id": account_id, item_side: taxable, "narration": item.description[:300],
                          "hsn_sac": item.hsn_sac, "quantity": item.quantity, "unit_rate": item.rate,
                          "gst_rate": item.gst_rate})
        for component, amount in split_gst(taxable, item.gst_rate, payload.place_of_supply).items():
            if amount > 0:
                tax_by_component[(component, item.gst_rate)] += amount
    tax_total = ZERO
    for (component, rate), amount in sorted(tax_by_component.items(), key=lambda kv: (kv[0][0], kv[0][1])):
        tax_total += amount
        lines.append({"account_id": codes[tax_codes[component]]["id"], item_side: amount,
                      "narration": f"{component.upper()} @ {rate.normalize()}% total rate", "gst_rate": rate,
                      "tax_component": component})
    gross = taxable_total + tax_total
    grand = gross.quantize(Decimal("1"), rounding=ROUND_HALF_UP) if payload.round_off else gross
    difference = grand - gross
    if difference:
        # Round-off sits on the item side when the invoice is rounded up.
        side = item_side if difference > 0 else party_side
        lines.append({"account_id": codes[A_ROUND_OFF]["id"], side: abs(difference), "narration": "Round off"})
    if grand <= 0:
        raise HTTPException(422, "Invoice total must be greater than zero")
    lines.insert(0, {"account_id": codes[party_code]["id"], party_side: grand, "narration": payload.party_name[:300]})
    return lines, taxable_total, tax_total


@router.post("/invoices", status_code=201)
def create_invoice(payload: InvoiceCreate, request: Request):
    try:
        with _connect() as conn:
            with conn.transaction():
                existing = _find_idempotent(conn, payload.idempotency_key)
                if existing:
                    return {**_voucher_detail(conn, existing["id"]), "idempotent_replay": True}
                codes = _accounts_by_code(conn, [A_AR, A_AP, A_GRNI, A_INVENTORY, A_SALES, A_SALES_RETURN, A_ROUND_OFF,
                                                 A_IN_CGST, A_IN_SGST, A_IN_IGST, A_OUT_CGST, A_OUT_SGST, A_OUT_IGST,
                                                 *SETTLEMENT_ACCOUNTS.values()])
                ids = sorted({line.account_id for line in payload.lines if line.account_id})
                line_accounts = {row["id"]: row for row in conn.execute(
                    "SELECT id, code, account_type, sub_type, is_active FROM accounting_accounts WHERE id = ANY(%s)", (ids,)
                ).fetchall()} if ids else {}
                if len(line_accounts) != len(ids):
                    raise HTTPException(422, "One or more line accounts do not exist")
                lines, taxable, tax = build_invoice_lines(payload, codes, line_accounts)
                party_type = "customer" if payload.invoice_type in {"sales", "credit_note"} else "supplier"
                voucher_id = _post_voucher(conn, {
                    "voucher_type": payload.invoice_type, "voucher_date": payload.voucher_date,
                    "narration": _clean(payload.narration), "reference": _clean(payload.reference),
                    "party_type": party_type, "party_name": payload.party_name, "party_gstin": payload.party_gstin,
                    "place_of_supply": payload.place_of_supply, "due_date": payload.due_date,
                    "taxable_total": taxable, "tax_total": tax, "idempotency_key": payload.idempotency_key,
                    # Invoice value is the party line; a rounded-down invoice has extra debit on round-off.
                    "total_amount": _money(lines[0].get("debit") or lines[0].get("credit")),
                }, lines, _actor(request))
                return _voucher_detail(conn, voucher_id)
    except HTTPException:
        raise
    except psycopg.Error as exc:
        raise _db_error(exc) from exc


@router.post("/vouchers/{voucher_id}/reverse", status_code=201)
def reverse_voucher(voucher_id: int, payload: ReverseRequest, request: Request):
    try:
        with _connect() as conn:
            with conn.transaction():
                original = conn.execute("SELECT * FROM accounting_vouchers WHERE id=%s FOR UPDATE", (voucher_id,)).fetchone()
                if not original:
                    raise HTTPException(404, "Voucher not found")
                if original["voucher_type"] == "reversal":
                    raise HTTPException(409, "A reversal entry cannot itself be reversed; post a new voucher instead")
                if original["status"] == "reversed":
                    raise HTTPException(409, "This voucher has already been reversed")
                reversal_date = payload.reversal_date or max(_today(), original["voucher_date"])
                if reversal_date < original["voucher_date"]:
                    raise HTTPException(422, "Reversal date cannot be before the original voucher date")
                lines = conn.execute(
                    "SELECT account_id, debit, credit, narration, hsn_sac, quantity, unit_rate, gst_rate, tax_component "
                    "FROM accounting_voucher_lines WHERE voucher_id=%s ORDER BY line_no", (voucher_id,)
                ).fetchall()
                swapped = [{**line, "debit": line["credit"], "credit": line["debit"]} for line in lines]
                new_id = _post_voucher(conn, {
                    "voucher_type": "reversal", "voucher_date": reversal_date,
                    "narration": f"Reversal of {original['voucher_number']}: {payload.reason}",
                    "reference": original["voucher_number"], "party_type": original["party_type"],
                    "party_name": original["party_name"], "party_gstin": original["party_gstin"],
                    "place_of_supply": original["place_of_supply"], "taxable_total": original["taxable_total"],
                    "tax_total": original["tax_total"], "total_amount": original["total_amount"], "reversal_of_id": voucher_id,
                }, swapped, _actor(request))
                conn.execute(
                    "UPDATE accounting_vouchers SET status='reversed', reversed_by_voucher_id=%s, reversal_reason=%s, "
                    "reversed_at=now(), reversed_by_email=%s WHERE id=%s",
                    (new_id, payload.reason, _actor(request)[1], voucher_id),
                )
                return _voucher_detail(conn, new_id)
    except HTTPException:
        raise
    except psycopg.Error as exc:
        raise _db_error(exc) from exc


# ---------------------------------------------------------------------------
# Reports
# ---------------------------------------------------------------------------

def profit_and_loss_from_rows(rows: list[dict]) -> dict:
    sections = {"revenue": [], "cogs": [], "other_income": [], "expenses": []}
    for row in rows:
        amount = _signed(row)
        if amount == 0:
            continue
        item = {"id": row["id"], "code": row["code"], "name": row["name"], "amount": amount}
        if row["account_type"] == "income":
            sections["other_income" if row["sub_type"] == "other_income" else "revenue"].append(item)
        elif row["account_type"] == "expense":
            sections["cogs" if row["sub_type"] in {"cogs", "direct"} else "expenses"].append(item)
    total = {key: sum((i["amount"] for i in items), ZERO) for key, items in sections.items()}
    gross = total["revenue"] - total["cogs"]
    net = gross + total["other_income"] - total["expenses"]
    return {"sections": sections, "totals": total, "gross_profit": gross, "net_profit": net}


@router.get("/reports/trial-balance")
def trial_balance(as_of: date | None = None):
    as_of = as_of or _today()
    try:
        with _connect() as conn:
            rows = _balances(conn, as_of)
    except psycopg.Error as exc:
        raise _db_error(exc) from exc
    items = []
    total_debit = total_credit = ZERO
    for row in rows:
        net = _money(row["debit"]) - _money(row["credit"])
        if net == 0 and row["debit"] == 0:
            continue
        debit, credit = (net, ZERO) if net > 0 else (ZERO, -net)
        total_debit += debit
        total_credit += credit
        items.append({"id": row["id"], "code": row["code"], "name": row["name"], "account_type": row["account_type"],
                      "debit": debit, "credit": credit})
    return {"as_of": as_of, "items": items, "total_debit": total_debit, "total_credit": total_credit,
            "balanced": total_debit == total_credit}


@router.get("/reports/profit-loss")
def profit_loss(from_date: date | None = None, to_date: date | None = None):
    start, end = _period(from_date, to_date)
    try:
        with _connect() as conn:
            rows = _balances(conn, end, start)
    except psycopg.Error as exc:
        raise _db_error(exc) from exc
    return {"from_date": start, "to_date": end, **profit_and_loss_from_rows(rows)}


@router.get("/reports/balance-sheet")
def balance_sheet(as_of: date | None = None):
    as_of = as_of or _today()
    try:
        with _connect() as conn:
            rows = _balances(conn, as_of)
    except psycopg.Error as exc:
        raise _db_error(exc) from exc
    groups = {"asset": [], "liability": [], "equity": []}
    for row in rows:
        if row["account_type"] in groups:
            amount = _signed(row)
            if amount != 0:
                groups[row["account_type"]].append({"id": row["id"], "code": row["code"], "name": row["name"],
                                                    "sub_type": row["sub_type"], "amount": amount})
    earnings = profit_and_loss_from_rows(rows)["net_profit"]
    if earnings != 0:
        groups["equity"].append({"id": None, "code": "P&L", "name": "Profit and loss (current, unappropriated)",
                                 "sub_type": "earnings", "amount": earnings})
    totals = {key: sum((i["amount"] for i in items), ZERO) for key, items in groups.items()}
    return {"as_of": as_of, "assets": groups["asset"], "liabilities": groups["liability"], "equity": groups["equity"],
            "total_assets": totals["asset"], "total_liabilities": totals["liability"], "total_equity": totals["equity"],
            "balanced": totals["asset"] == totals["liability"] + totals["equity"]}


@router.get("/reports/ledger/{account_id}")
def account_ledger(account_id: int, from_date: date | None = None, to_date: date | None = None,
                   limit: int = Query(default=1000, ge=1, le=5000)):
    start, end = _period(from_date, to_date)
    try:
        with _connect() as conn:
            account = conn.execute("SELECT id, code, name, account_type, sub_type FROM accounting_accounts WHERE id=%s",
                                   (account_id,)).fetchone()
            if not account:
                raise HTTPException(404, "Account not found")
            opening = conn.execute(
                "SELECT COALESCE(sum(l.debit - l.credit), 0) AS net FROM accounting_voucher_lines l "
                "JOIN accounting_vouchers v ON v.id=l.voucher_id WHERE l.account_id=%s AND v.voucher_date < %s",
                (account_id, start),
            ).fetchone()["net"]
            rows = conn.execute(
                "SELECT l.id AS line_id, v.id AS voucher_id, v.voucher_number, v.voucher_type, v.voucher_date, v.party_name, "
                "COALESCE(l.narration, v.narration) AS narration, l.debit, l.credit, l.reconciled_on FROM accounting_voucher_lines l "
                "JOIN accounting_vouchers v ON v.id=l.voucher_id WHERE l.account_id=%s AND v.voucher_date BETWEEN %s AND %s "
                "ORDER BY v.voucher_date, v.id, l.line_no LIMIT %s",
                (account_id, start, end, limit),
            ).fetchall()
    except HTTPException:
        raise
    except psycopg.Error as exc:
        raise _db_error(exc) from exc
    running = _money(opening)
    for row in rows:
        running += _money(row["debit"]) - _money(row["credit"])
        row["balance"] = running
    return {"account": account, "from_date": start, "to_date": end, "opening_balance": _money(opening),
            "closing_balance": running, "total_debit": sum((_money(r["debit"]) for r in rows), ZERO),
            "total_credit": sum((_money(r["credit"]) for r in rows), ZERO), "items": rows,
            "balance_convention": "debit minus credit; positive = Dr, negative = Cr"}


@router.get("/reports/day-book")
def day_book(from_date: date | None = None, to_date: date | None = None, limit: int = Query(default=300, ge=1, le=1000)):
    end = to_date or _today()
    start = from_date or end
    start, end = _period(start, end)
    try:
        with _connect() as conn:
            vouchers = conn.execute(
                "SELECT id, voucher_number, voucher_type, voucher_date, status, party_name, narration, total_amount "
                "FROM accounting_vouchers WHERE voucher_date BETWEEN %s AND %s ORDER BY voucher_date, id LIMIT %s",
                (start, end, limit),
            ).fetchall()
            ids = [v["id"] for v in vouchers]
            lines = conn.execute(
                "SELECT l.voucher_id, a.code, a.name, l.debit, l.credit FROM accounting_voucher_lines l "
                "JOIN accounting_accounts a ON a.id=l.account_id WHERE l.voucher_id = ANY(%s) ORDER BY l.voucher_id, l.line_no",
                (ids,),
            ).fetchall() if ids else []
    except psycopg.Error as exc:
        raise _db_error(exc) from exc
    grouped = defaultdict(list)
    for line in lines:
        grouped[line["voucher_id"]].append(line)
    for voucher in vouchers:
        voucher["lines"] = grouped[voucher["id"]]
    return {"from_date": start, "to_date": end, "items": vouchers,
            "total": sum((_money(v["total_amount"]) for v in vouchers), ZERO)}


@router.get("/reports/gst-summary")
def gst_summary(from_date: date | None = None, to_date: date | None = None):
    start, end = _period(from_date, to_date)
    try:
        with _connect() as conn:
            tax_rows = conn.execute(
                "SELECT a.sub_type, l.tax_component, l.gst_rate, v.voucher_type, sum(l.credit - l.debit) AS net "
                "FROM accounting_voucher_lines l JOIN accounting_accounts a ON a.id=l.account_id "
                "JOIN accounting_vouchers v ON v.id=l.voucher_id WHERE a.sub_type IN ('tax_output','tax_input') "
                "AND v.voucher_date BETWEEN %s AND %s GROUP BY a.sub_type, l.tax_component, l.gst_rate, v.voucher_type",
                (start, end),
            ).fetchall()
            taxable_rows = conn.execute(
                "SELECT v.voucher_type, l.gst_rate, a.account_type, (v.party_gstin IS NOT NULL) AS b2b, "
                "sum(l.credit - l.debit) AS net FROM accounting_voucher_lines l JOIN accounting_accounts a ON a.id=l.account_id "
                "JOIN accounting_vouchers v ON v.id=l.voucher_id WHERE l.gst_rate IS NOT NULL AND l.tax_component IS NULL "
                "AND v.voucher_date BETWEEN %s AND %s GROUP BY v.voucher_type, l.gst_rate, a.account_type, b2b",
                (start, end),
            ).fetchall()
    except psycopg.Error as exc:
        raise _db_error(exc) from exc
    output = {"cgst": ZERO, "sgst": ZERO, "igst": ZERO}
    input_ = {"cgst": ZERO, "sgst": ZERO, "igst": ZERO}
    for row in tax_rows:
        component = row["tax_component"] or "cgst"
        if row["sub_type"] == "tax_output":
            output[component] += _money(row["net"])
        else:
            input_[component] += -_money(row["net"])
    by_rate: dict[str, dict] = {}
    for row in taxable_rows:
        rate = str(Decimal(row["gst_rate"]).normalize())
        bucket = by_rate.setdefault(rate, {"rate": rate, "outward_taxable": ZERO, "inward_taxable": ZERO,
                                           "outward_b2b": ZERO, "outward_b2c": ZERO})
        net = _money(row["net"])
        if row["account_type"] == "income":
            bucket["outward_taxable"] += net
            bucket["outward_b2b" if row["b2b"] else "outward_b2c"] += net
        else:
            bucket["inward_taxable"] += -net
    for row in tax_rows:
        rate = str(Decimal(row["gst_rate"] or 0).normalize())
        bucket = by_rate.setdefault(rate, {"rate": rate, "outward_taxable": ZERO, "inward_taxable": ZERO,
                                           "outward_b2b": ZERO, "outward_b2c": ZERO})
        key = "output_tax" if row["sub_type"] == "tax_output" else "input_tax"
        sign = 1 if row["sub_type"] == "tax_output" else -1
        bucket[key] = bucket.get(key, ZERO) + sign * _money(row["net"])
    total_output = sum(output.values(), ZERO)
    total_input = sum(input_.values(), ZERO)
    return {
        "from_date": start, "to_date": end, "output_tax": output, "input_tax": input_,
        "total_output_tax": total_output, "total_input_tax": total_input,
        "net_payable": {k: output[k] - input_[k] for k in output}, "total_net_payable": total_output - total_input,
        "by_rate": sorted(by_rate.values(), key=lambda b: Decimal(b["rate"])),
        "disclaimer": "Bookkeeping summary to assist GSTR-1/GSTR-3B preparation. Input tax credit utilisation order "
                      "(IGST/CGST/SGST cross-utilisation) is not applied. Review with your tax professional before filing.",
    }


def age_outstanding(entries: list[dict], outstanding: Decimal, as_of: date) -> dict[str, Decimal]:
    """Allocate an outstanding balance to the newest invoices first (older items assumed settled first)."""
    buckets = {"current": ZERO, "d31_60": ZERO, "d61_90": ZERO, "d90_plus": ZERO}
    remaining = outstanding
    for entry in sorted(entries, key=lambda e: e["date"], reverse=True):
        if remaining <= 0:
            break
        portion = min(remaining, entry["amount"])
        age = (as_of - entry["date"]).days
        key = "current" if age <= 30 else "d31_60" if age <= 60 else "d61_90" if age <= 90 else "d90_plus"
        buckets[key] += portion
        remaining -= portion
    if remaining > 0:
        buckets["d90_plus"] += remaining
    return buckets


@router.get("/reports/parties")
def party_balances(kind: str = Query(default="receivable", pattern=r"^(receivable|payable)$"), as_of: date | None = None):
    as_of = as_of or _today()
    try:
        with _connect() as conn:
            rows = conn.execute(
                "SELECT COALESCE(v.party_name, 'Unassigned') AS party_name, COALESCE(v.due_date, v.voucher_date) AS due_on, "
                "l.debit, l.credit FROM accounting_voucher_lines l JOIN accounting_accounts a ON a.id=l.account_id "
                "JOIN accounting_vouchers v ON v.id=l.voucher_id WHERE a.sub_type=%s AND a.code <> %s AND v.voucher_date <= %s",
                (kind, A_GRNI, as_of),
            ).fetchall()
    except psycopg.Error as exc:
        raise _db_error(exc) from exc
    parties: dict[str, dict] = {}
    for row in rows:
        party = parties.setdefault(row["party_name"], {"party_name": row["party_name"], "debit": ZERO, "credit": ZERO, "entries": []})
        party["debit"] += _money(row["debit"])
        party["credit"] += _money(row["credit"])
        increase = _money(row["debit"]) if kind == "receivable" else _money(row["credit"])
        if increase > 0:
            party["entries"].append({"date": row["due_on"], "amount": increase})
    items = []
    for party in parties.values():
        outstanding = party["debit"] - party["credit"] if kind == "receivable" else party["credit"] - party["debit"]
        if outstanding == 0:
            continue
        aging = age_outstanding(party["entries"], outstanding, as_of) if outstanding > 0 else {
            "current": outstanding, "d31_60": ZERO, "d61_90": ZERO, "d90_plus": ZERO}
        items.append({"party_name": party["party_name"], "outstanding": outstanding, **aging})
    items.sort(key=lambda i: i["outstanding"], reverse=True)
    return {"kind": kind, "as_of": as_of, "items": items, "total": sum((i["outstanding"] for i in items), ZERO)}


@router.get("/reports/summary")
def accounting_summary(from_date: date | None = None, to_date: date | None = None):
    start, end = _period(from_date, to_date)
    try:
        with _connect() as conn:
            period_rows = _balances(conn, end, start)
            all_rows = _balances(conn, end)
            monthly = conn.execute(
                "SELECT date_trunc('month', v.voucher_date)::date AS month, a.account_type, sum(l.credit - l.debit) AS net "
                "FROM accounting_voucher_lines l JOIN accounting_accounts a ON a.id=l.account_id JOIN accounting_vouchers v "
                "ON v.id=l.voucher_id WHERE a.account_type IN ('income','expense') AND v.voucher_date BETWEEN %s AND %s "
                "GROUP BY 1, 2 ORDER BY 1",
                (start, end),
            ).fetchall()
            recent = conn.execute(
                "SELECT id, voucher_number, voucher_type, voucher_date, status, party_name, narration, total_amount "
                "FROM accounting_vouchers ORDER BY created_at DESC, id DESC LIMIT 8"
            ).fetchall()
            count = conn.execute("SELECT count(*) AS n FROM accounting_vouchers WHERE voucher_date BETWEEN %s AND %s",
                                 (start, end)).fetchone()["n"]
            settings_row = _settings_row(conn)
    except psycopg.Error as exc:
        raise _db_error(exc) from exc
    pl = profit_and_loss_from_rows(period_rows)

    def total_for(sub_types, rows=all_rows):
        return sum((_signed(r) for r in rows if r["sub_type"] in sub_types), ZERO)

    months: dict[str, dict] = {}
    for row in monthly:
        key = row["month"].isoformat()[:7]
        bucket = months.setdefault(key, {"month": key, "income": ZERO, "expense": ZERO})
        if row["account_type"] == "income":
            bucket["income"] += _money(row["net"])
        else:
            bucket["expense"] += -_money(row["net"])
    return {
        "from_date": start, "to_date": end, "fiscal_year": fiscal_year(end),
        "income": pl["totals"]["revenue"] + pl["totals"]["other_income"],
        "expenses": pl["totals"]["cogs"] + pl["totals"]["expenses"],
        "gross_profit": pl["gross_profit"], "net_profit": pl["net_profit"],
        "cash_balance": total_for({"cash"}), "bank_balance": total_for({"bank"}),
        "receivables": total_for({"receivable"}),
        "payables": sum((_signed(r) for r in all_rows if r["sub_type"] == "payable"), ZERO),
        "gst_payable": total_for({"tax_output"}) - total_for({"tax_input"}),
        "inventory_value": total_for({"inventory"}),
        "voucher_count": count, "monthly": list(months.values()), "recent": recent,
        "lock_date": settings_row.get("lock_date"),
    }


# ---------------------------------------------------------------------------
# Bank reconciliation
# ---------------------------------------------------------------------------

@router.get("/bank-reconciliation")
def bank_reconciliation(account_id: int, to_date: date | None = None, show: str = Query(default="unreconciled", pattern=r"^(unreconciled|all)$")):
    end = to_date or _today()
    try:
        with _connect() as conn:
            account = conn.execute("SELECT id, code, name, sub_type FROM accounting_accounts WHERE id=%s", (account_id,)).fetchone()
            if not account:
                raise HTTPException(404, "Account not found")
            if account["sub_type"] != "bank":
                raise HTTPException(422, "Bank reconciliation is available for bank and clearing accounts only")
            totals = conn.execute(
                "SELECT COALESCE(sum(l.debit - l.credit), 0) AS book, "
                "COALESCE(sum(l.debit - l.credit) FILTER (WHERE l.reconciled_on IS NOT NULL AND l.reconciled_on <= %s), 0) AS cleared "
                "FROM accounting_voucher_lines l JOIN accounting_vouchers v ON v.id=l.voucher_id "
                "WHERE l.account_id=%s AND v.voucher_date <= %s",
                (end, account_id, end),
            ).fetchone()
            filter_sql = " AND (l.reconciled_on IS NULL OR l.reconciled_on > %s)" if show == "unreconciled" else ""
            params = [account_id, end] + ([end] if show == "unreconciled" else [])
            items = conn.execute(
                "SELECT l.id AS line_id, v.id AS voucher_id, v.voucher_number, v.voucher_type, v.voucher_date, v.party_name, "
                "COALESCE(l.narration, v.narration) AS narration, l.debit, l.credit, l.reconciled_on, l.bank_reference "
                "FROM accounting_voucher_lines l JOIN accounting_vouchers v ON v.id=l.voucher_id "
                "WHERE l.account_id=%s AND v.voucher_date <= %s" + filter_sql + " ORDER BY v.voucher_date, v.id LIMIT 1000",
                params,
            ).fetchall()
    except HTTPException:
        raise
    except psycopg.Error as exc:
        raise _db_error(exc) from exc
    return {"account": account, "to_date": end, "book_balance": _money(totals["book"]),
            "cleared_balance": _money(totals["cleared"]),
            "uncleared_amount": _money(totals["book"]) - _money(totals["cleared"]), "items": items}


@router.patch("/lines/{line_id}/reconcile")
def reconcile_line(line_id: int, payload: ReconcileRequest):
    try:
        with _connect() as conn:
            with conn.transaction():
                line = conn.execute(
                    "SELECT l.id, a.sub_type, v.voucher_date FROM accounting_voucher_lines l JOIN accounting_accounts a "
                    "ON a.id=l.account_id JOIN accounting_vouchers v ON v.id=l.voucher_id WHERE l.id=%s FOR UPDATE OF l",
                    (line_id,),
                ).fetchone()
                if not line:
                    raise HTTPException(404, "Ledger line not found")
                if line["sub_type"] != "bank":
                    raise HTTPException(422, "Only bank and clearing account lines can be reconciled")
                if payload.reconciled_on and payload.reconciled_on < line["voucher_date"]:
                    raise HTTPException(422, "Bank clearing date cannot be before the voucher date")
                return conn.execute(
                    "UPDATE accounting_voucher_lines SET reconciled_on=%s, bank_reference=%s WHERE id=%s "
                    "RETURNING id AS line_id, reconciled_on, bank_reference",
                    (payload.reconciled_on, _clean(payload.bank_reference), line_id),
                ).fetchone()
    except HTTPException:
        raise
    except psycopg.Error as exc:
        raise _db_error(exc) from exc


# ---------------------------------------------------------------------------
# Automatic posting of operational records (orders, payments, goods receipts)
# ---------------------------------------------------------------------------

def _ist_date(value: datetime) -> date:
    return value.astimezone(IST).date() if value.tzinfo else value.date()


def build_order_lines(order: dict, items: list[dict], codes: dict[str, dict], supply: str) -> tuple[list[dict], Decimal, Decimal]:
    """Sales journal for an order whose prices are GST-inclusive (orders.total = sum of line totals)."""
    lines: list[dict] = []
    taxable_total = tax_total = ZERO
    tax_by_component: dict[tuple[str, Decimal], Decimal] = defaultdict(lambda: ZERO)
    sales_by_rate: dict[Decimal, Decimal] = defaultdict(lambda: ZERO)
    line_sum = cost = ZERO
    for item in items:
        gross = _money(item["line_total"])
        line_sum += gross
        rate = Decimal(item["tax_rate"] or 0)
        taxable, tax = inclusive_split(gross, rate)
        taxable_total += taxable
        sales_by_rate[rate] += taxable
        if tax > 0:
            if supply == "inter":
                tax_by_component[("igst", rate)] += tax
            else:
                half = _money(tax / 2)
                tax_by_component[("cgst", rate)] += half
                tax_by_component[("sgst", rate)] += tax - half
        if item.get("cost_price") is not None:
            cost += _money(Decimal(item["cost_price"]) * Decimal(item["quantity"]))
    for rate, amount in sorted(sales_by_rate.items()):
        lines.append({"account_id": codes[A_SALES]["id"], "credit": amount, "gst_rate": rate,
                      "narration": f"Sales @ {rate.normalize()}% GST"})
    tax_accounts = {"cgst": A_OUT_CGST, "sgst": A_OUT_SGST, "igst": A_OUT_IGST}
    for (component, rate), amount in sorted(tax_by_component.items()):
        tax_total += amount
        lines.append({"account_id": codes[tax_accounts[component]]["id"], "credit": amount, "gst_rate": rate,
                      "tax_component": component, "narration": f"{component.upper()} @ {rate.normalize()}%"})
    total = _money(order["total"])
    difference = total - line_sum
    if difference > 0:
        lines.append({"account_id": codes[A_OTHER_CHARGES]["id"], "credit": difference, "narration": "Delivery and other charges"})
    elif difference < 0:
        lines.append({"account_id": codes[A_DISCOUNT]["id"], "debit": -difference, "narration": "Order discount"})
    if total > 0:
        lines.insert(0, {"account_id": codes[A_AR]["id"], "debit": total, "narration": order["customer_name"][:300]})
    if cost > 0:
        lines.append({"account_id": codes[A_COGS]["id"], "debit": cost, "narration": "Cost of goods sold"})
        lines.append({"account_id": codes[A_INVENTORY]["id"], "credit": cost, "narration": "Stock issued"})
    return lines, taxable_total, tax_total


def _sync_status(conn) -> dict:
    orders = conn.execute(
        "SELECT count(*) AS n FROM orders o WHERE o.status = ANY(%s) AND NOT EXISTS (SELECT 1 FROM accounting_vouchers v "
        "WHERE v.source_type='order' AND v.source_id=o.id::text)", (list(ORDER_POSTABLE),)
    ).fetchone()["n"]
    cancellations = conn.execute(
        "SELECT count(*) AS n FROM orders o WHERE o.status='cancelled' AND EXISTS (SELECT 1 FROM accounting_vouchers v "
        "WHERE v.source_type='order' AND v.source_id=o.id::text) AND NOT EXISTS (SELECT 1 FROM accounting_vouchers v "
        "WHERE v.source_type='order_cancel' AND v.source_id=o.id::text)"
    ).fetchone()["n"]
    payments = conn.execute(
        "SELECT count(*) AS n FROM payments p WHERE p.status='captured' AND NOT EXISTS (SELECT 1 FROM "
        "accounting_vouchers v WHERE v.source_type='payment' AND v.source_id=p.id::text)"
    ).fetchone()["n"]
    refunds = conn.execute(
        "SELECT count(*) AS n FROM payments p WHERE p.status='refunded' AND EXISTS (SELECT 1 FROM accounting_vouchers v "
        "WHERE v.source_type='payment' AND v.source_id=p.id::text) AND NOT EXISTS (SELECT 1 FROM accounting_vouchers v "
        "WHERE v.source_type='payment_refund' AND v.source_id=p.id::text)"
    ).fetchone()["n"]
    receipts = conn.execute(
        "SELECT count(*) AS n FROM (SELECT m.reference_id, m.created_at FROM inventory_movements m WHERE m.movement_type='receipt' "
        "AND m.reference_type='purchase_order' GROUP BY m.reference_id, m.created_at) r WHERE NOT EXISTS (SELECT 1 FROM "
        "accounting_vouchers v WHERE v.source_type='goods_receipt' AND v.source_id = r.reference_id || ':' || "
        "to_char(r.created_at AT TIME ZONE 'UTC', 'YYYYMMDDHH24MISSUS'))"
    ).fetchone()["n"]
    return {"orders": orders, "order_cancellations": cancellations, "payments": payments, "refunds": refunds,
            "goods_receipts": receipts, "pending_total": orders + cancellations + payments + refunds + receipts}


@router.get("/sync/status")
def sync_status():
    try:
        with _connect() as conn:
            return _sync_status(conn)
    except psycopg.Error as exc:
        raise _db_error(exc) from exc


def _try_post(conn, header, lines, actor, result, key) -> None:
    """Post one automatic voucher inside a savepoint so one bad record does not block the batch."""
    lock = _settings_row(conn).get("lock_date")
    if lock and header["voucher_date"] <= lock:
        result["skipped_locked"] += 1
        return
    try:
        with conn.transaction():
            _post_voucher(conn, header, lines, actor)
        result[key] += 1
    except HTTPException as exc:
        result["errors"].append(f"{header['source_type']} {header['source_id']}: {exc.detail}")
    except psycopg.errors.UniqueViolation:
        result["already_posted"] += 1


@router.post("/sync")
def sync_operational_records(request: Request, limit: int = Query(default=200, ge=1, le=1000)):
    """Post sales, cancellations, captured payments, refunds and goods receipts that are not yet in the ledger. Idempotent."""
    actor = _actor(request)
    result = {"orders": 0, "order_cancellations": 0, "payments": 0, "refunds": 0, "goods_receipts": 0,
              "skipped_locked": 0, "already_posted": 0, "errors": []}
    try:
        with _connect() as conn:
            codes = _accounts_by_code(conn, [A_AR, A_SALES, A_OUT_CGST, A_OUT_SGST, A_OUT_IGST, A_OTHER_CHARGES, A_DISCOUNT,
                                             A_COGS, A_INVENTORY, A_GRNI, *PAYMENT_METHOD_ACCOUNTS.values()])
            supply = _settings_row(conn).get("default_supply") or "intra"
            with conn.transaction():
                orders = conn.execute(
                    "SELECT o.id, o.order_number, o.channel, o.customer_name, o.total, o.created_at FROM orders o "
                    "WHERE o.status = ANY(%s) AND NOT EXISTS (SELECT 1 FROM accounting_vouchers v WHERE v.source_type='order' "
                    "AND v.source_id=o.id::text) ORDER BY o.id LIMIT %s", (list(ORDER_POSTABLE), limit)
                ).fetchall()
                for order in orders:
                    items = conn.execute(
                        "SELECT ol.quantity, ol.line_total, p.tax_rate, v.cost_price FROM order_lines ol JOIN product_variants v "
                        "ON v.id=ol.variant_id JOIN products p ON p.id=v.product_id WHERE ol.order_id=%s ORDER BY ol.id", (order["id"],)
                    ).fetchall()
                    lines, taxable, tax = build_order_lines(order, items, codes, supply)
                    if not lines:
                        continue
                    _try_post(conn, {
                        "voucher_type": "sales", "voucher_date": _ist_date(order["created_at"]),
                        "narration": f"{order['channel'].upper()} order {order['order_number']}", "reference": order["order_number"],
                        "party_type": "customer", "party_name": order["customer_name"], "place_of_supply": supply,
                        "taxable_total": taxable, "tax_total": tax, "source_type": "order", "source_id": str(order["id"]),
                        # Show the order value, not order value + cost-of-goods debit.
                        "total_amount": _money(order["total"]),
                    }, lines, actor, result, "orders")

                cancelled = conn.execute(
                    "SELECT o.id, o.order_number, o.updated_at, v.id AS voucher_id FROM orders o JOIN accounting_vouchers v "
                    "ON v.source_type='order' AND v.source_id=o.id::text WHERE o.status='cancelled' AND v.status='posted' "
                    "AND NOT EXISTS (SELECT 1 FROM accounting_vouchers c WHERE c.source_type='order_cancel' AND c.source_id=o.id::text) "
                    "ORDER BY o.id LIMIT %s", (limit,)
                ).fetchall()
                for order in cancelled:
                    original = _voucher_detail(conn, order["voucher_id"])
                    swapped = [{"account_id": l["account_id"], "debit": l["credit"], "credit": l["debit"], "narration": l["narration"],
                                "gst_rate": l["gst_rate"], "tax_component": l["tax_component"]} for l in original["lines"]]
                    _try_post(conn, {
                        "voucher_type": "credit_note", "voucher_date": max(_ist_date(order["updated_at"]), original["voucher_date"]),
                        "narration": f"Cancellation of order {order['order_number']}", "reference": original["voucher_number"],
                        "party_type": "customer", "party_name": original["party_name"], "place_of_supply": original["place_of_supply"],
                        "taxable_total": original["taxable_total"], "tax_total": original["tax_total"],
                        "source_type": "order_cancel", "source_id": str(order["id"]), "total_amount": original["total_amount"],
                    }, swapped, actor, result, "order_cancellations")

                payments = conn.execute(
                    "SELECT p.id, p.payment_reference, p.method, p.amount, p.created_at, p.updated_at, o.order_number, o.customer_name "
                    "FROM payments p JOIN orders o ON o.id=p.order_id WHERE p.status='captured' AND NOT EXISTS (SELECT 1 FROM "
                    "accounting_vouchers v WHERE v.source_type='payment' AND v.source_id=p.id::text) ORDER BY p.id LIMIT %s", (limit,)
                ).fetchall()
                for payment in payments:
                    amount = _money(payment["amount"])
                    money_account = codes[PAYMENT_METHOD_ACCOUNTS.get(payment["method"], A_CASH)]["id"]
                    _try_post(conn, {
                        "voucher_type": "receipt", "voucher_date": _ist_date(payment["updated_at"] or payment["created_at"]),
                        "narration": f"{payment['method'].upper()} payment {payment['payment_reference']} for order {payment['order_number']}",
                        "reference": payment["payment_reference"], "party_type": "customer", "party_name": payment["customer_name"],
                        "source_type": "payment", "source_id": str(payment["id"]),
                    }, [{"account_id": money_account, "debit": amount}, {"account_id": codes[A_AR]["id"], "credit": amount}],
                        actor, result, "payments")

                refunds = conn.execute(
                    "SELECT p.id, p.payment_reference, p.method, p.amount, p.updated_at, o.customer_name FROM payments p "
                    "JOIN orders o ON o.id=p.order_id WHERE p.status='refunded' AND EXISTS (SELECT 1 FROM accounting_vouchers v "
                    "WHERE v.source_type='payment' AND v.source_id=p.id::text) AND NOT EXISTS (SELECT 1 FROM accounting_vouchers v "
                    "WHERE v.source_type='payment_refund' AND v.source_id=p.id::text) ORDER BY p.id LIMIT %s", (limit,)
                ).fetchall()
                for payment in refunds:
                    amount = _money(payment["amount"])
                    money_account = codes[PAYMENT_METHOD_ACCOUNTS.get(payment["method"], A_CASH)]["id"]
                    _try_post(conn, {
                        "voucher_type": "payment", "voucher_date": _ist_date(payment["updated_at"]),
                        "narration": f"Refund of payment {payment['payment_reference']}", "reference": payment["payment_reference"],
                        "party_type": "customer", "party_name": payment["customer_name"],
                        "source_type": "payment_refund", "source_id": str(payment["id"]),
                    }, [{"account_id": codes[A_AR]["id"], "debit": amount}, {"account_id": money_account, "credit": amount}],
                        actor, result, "refunds")

                receipts = conn.execute(
                    "SELECT m.reference_id, m.created_at, to_char(m.created_at AT TIME ZONE 'UTC', 'YYYYMMDDHH24MISSUS') AS stamp, "
                    "po.purchase_number, s.name AS supplier_name, sum(m.quantity * l.unit_cost) AS value FROM inventory_movements m "
                    "JOIN purchase_orders po ON po.id::text = m.reference_id JOIN suppliers s ON s.id=po.supplier_id "
                    "JOIN purchase_order_lines l ON l.purchase_order_id=po.id AND l.variant_id=m.variant_id "
                    "WHERE m.movement_type='receipt' AND m.reference_type='purchase_order' AND NOT EXISTS (SELECT 1 FROM "
                    "accounting_vouchers v WHERE v.source_type='goods_receipt' AND v.source_id = m.reference_id || ':' || "
                    "to_char(m.created_at AT TIME ZONE 'UTC', 'YYYYMMDDHH24MISSUS')) "
                    "GROUP BY m.reference_id, m.created_at, po.purchase_number, s.name ORDER BY m.created_at LIMIT %s", (limit,)
                ).fetchall()
                for receipt in receipts:
                    value = _money(receipt["value"])
                    if value <= 0:
                        continue
                    _try_post(conn, {
                        "voucher_type": "journal", "voucher_date": _ist_date(receipt["created_at"]),
                        "narration": f"Goods received against {receipt['purchase_number']} (awaiting supplier bill)",
                        "reference": receipt["purchase_number"], "party_type": "supplier", "party_name": receipt["supplier_name"],
                        "source_type": "goods_receipt", "source_id": f"{receipt['reference_id']}:{receipt['stamp']}",
                    }, [{"account_id": codes[A_INVENTORY]["id"], "debit": value, "narration": "Stock received at cost"},
                        {"account_id": codes[A_GRNI]["id"], "credit": value, "narration": receipt["supplier_name"][:300]}],
                        actor, result, "goods_receipts")
            result["pending"] = _sync_status(conn)
        return result
    except HTTPException:
        raise
    except psycopg.Error as exc:
        raise _db_error(exc) from exc
