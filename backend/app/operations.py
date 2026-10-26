"""Operational APIs for shared customers/vendors, POS, purchasing, inventory, logistics and HR/payroll.

The module uses isolated operational tables and references the existing catalogue by product/variant IDs.
No catalogue migration/import or deployment configuration is performed.
"""
from datetime import date
from decimal import Decimal
from typing import Any

import psycopg
from fastapi import APIRouter, Header, HTTPException, Query
from pydantic import BaseModel, Field
from psycopg.rows import dict_row

from .auth import _require, _db, _current
from .schema_guard import tolerate_missing_ddl_permission

router = APIRouter(prefix="/api/operations", tags=["operations"])

def _admin(authorization: str | None) -> dict[str, Any]:
    return _require(authorization, {"super_admin", "admin"})

def _current_user_id(authorization: str | None) -> int:
    return int(_admin(authorization)["id"])

@tolerate_missing_ddl_permission
def _ensure(conn: Any) -> None:
    conn.execute("""CREATE TABLE IF NOT EXISTS sb_customers (
        id BIGSERIAL PRIMARY KEY, name TEXT NOT NULL, phone TEXT, email TEXT, gstin TEXT,
        billing_address JSONB NOT NULL DEFAULT '{}'::jsonb, created_at TIMESTAMPTZ NOT NULL DEFAULT now())""")
    conn.execute("""CREATE UNIQUE INDEX IF NOT EXISTS sb_customers_email_uq ON sb_customers(lower(email)) WHERE email IS NOT NULL AND email<>''""")
    conn.execute("""CREATE TABLE IF NOT EXISTS sb_vendors (
        id BIGSERIAL PRIMARY KEY, name TEXT NOT NULL, phone TEXT, email TEXT, gstin TEXT,
        address JSONB NOT NULL DEFAULT '{}'::jsonb, payment_terms_days INTEGER NOT NULL DEFAULT 0,
        created_at TIMESTAMPTZ NOT NULL DEFAULT now())""")
    conn.execute("""CREATE UNIQUE INDEX IF NOT EXISTS sb_vendors_email_uq ON sb_vendors(lower(email)) WHERE email IS NOT NULL AND email<>''""")
    conn.execute("""CREATE TABLE IF NOT EXISTS sb_stock (
        variant_id BIGINT NOT NULL, warehouse TEXT NOT NULL DEFAULT 'Main', quantity NUMERIC(14,3) NOT NULL DEFAULT 0 CHECK(quantity>=0),
        updated_at TIMESTAMPTZ NOT NULL DEFAULT now(), PRIMARY KEY(variant_id,warehouse))""")
    conn.execute("""CREATE TABLE IF NOT EXISTS sb_product_tax (
        variant_id BIGINT PRIMARY KEY, hsn_sac TEXT, gst_rate NUMERIC(5,2) NOT NULL DEFAULT 0 CHECK(gst_rate>=0 AND gst_rate<=100),
        classification TEXT NOT NULL DEFAULT 'taxable' CHECK(classification IN ('taxable','nil_rated','exempt','non_gst')),
        updated_at TIMESTAMPTZ NOT NULL DEFAULT now(), updated_by BIGINT)""")
    conn.execute("""CREATE TABLE IF NOT EXISTS sb_stock_movements (
        id BIGSERIAL PRIMARY KEY, variant_id BIGINT NOT NULL, warehouse TEXT NOT NULL DEFAULT 'Main',
        movement_type TEXT NOT NULL, quantity NUMERIC(14,3) NOT NULL CHECK(quantity>0),
        reference_type TEXT, reference_id BIGINT, note TEXT, created_by BIGINT, created_at TIMESTAMPTZ NOT NULL DEFAULT now())""")
    conn.execute("""CREATE TABLE IF NOT EXISTS sb_purchase_orders (
        id BIGSERIAL PRIMARY KEY, vendor_id BIGINT NOT NULL REFERENCES sb_vendors(id), status TEXT NOT NULL DEFAULT 'draft'
        CHECK(status IN ('draft','ordered','part_received','received','cancelled')), order_date DATE NOT NULL DEFAULT CURRENT_DATE,
        total NUMERIC(14,2) NOT NULL DEFAULT 0, note TEXT, created_by BIGINT, created_at TIMESTAMPTZ NOT NULL DEFAULT now())""")
    conn.execute("""CREATE TABLE IF NOT EXISTS sb_purchase_lines (
        id BIGSERIAL PRIMARY KEY, purchase_id BIGINT NOT NULL REFERENCES sb_purchase_orders(id) ON DELETE CASCADE,
        variant_id BIGINT NOT NULL, quantity NUMERIC(14,3) NOT NULL CHECK(quantity>0),
        unit_cost NUMERIC(14,2) NOT NULL CHECK(unit_cost>=0), received_qty NUMERIC(14,3) NOT NULL DEFAULT 0 CHECK(received_qty>=0))""")
    conn.execute("""CREATE TABLE IF NOT EXISTS sb_supplier_payments (
        id BIGSERIAL PRIMARY KEY, purchase_id BIGINT NOT NULL UNIQUE REFERENCES sb_purchase_orders(id),
        amount NUMERIC(14,2) NOT NULL CHECK(amount>0), payment_account TEXT NOT NULL CHECK(payment_account IN ('bank','cash')),
        reference TEXT, paid_by BIGINT, paid_at TIMESTAMPTZ NOT NULL DEFAULT now())""")
    conn.execute("""CREATE TABLE IF NOT EXISTS sb_purchase_receipts (
        id BIGSERIAL PRIMARY KEY, purchase_id BIGINT NOT NULL REFERENCES sb_purchase_orders(id),
        received_value NUMERIC(14,2) NOT NULL CHECK(received_value>=0), received_by BIGINT,
        created_at TIMESTAMPTZ NOT NULL DEFAULT now())""")
    conn.execute("""CREATE TABLE IF NOT EXISTS sb_pos_sales (
        id BIGSERIAL PRIMARY KEY, receipt_number TEXT NOT NULL UNIQUE, customer_id BIGINT REFERENCES sb_customers(id),
        status TEXT NOT NULL DEFAULT 'completed', subtotal NUMERIC(14,2) NOT NULL, tax_total NUMERIC(14,2) NOT NULL DEFAULT 0,
        total NUMERIC(14,2) NOT NULL, payment_method TEXT NOT NULL, sale_date TIMESTAMPTZ NOT NULL DEFAULT now(),
        created_by BIGINT)""")
    conn.execute("""CREATE TABLE IF NOT EXISTS sb_pos_sale_lines (
        id BIGSERIAL PRIMARY KEY, sale_id BIGINT NOT NULL REFERENCES sb_pos_sales(id) ON DELETE CASCADE,
        variant_id BIGINT NOT NULL, quantity NUMERIC(14,3) NOT NULL CHECK(quantity>0),
        unit_price NUMERIC(14,2) NOT NULL CHECK(unit_price>=0), tax_rate NUMERIC(5,2) NOT NULL DEFAULT 0,
        line_total NUMERIC(14,2) NOT NULL)""")
    conn.execute("""CREATE TABLE IF NOT EXISTS sb_shipments (
        id BIGSERIAL PRIMARY KEY, order_type TEXT NOT NULL, order_id BIGINT NOT NULL, carrier TEXT,
        tracking_number TEXT, status TEXT NOT NULL DEFAULT 'created' CHECK(status IN ('created','packed','in_transit','out_for_delivery','delivered','exception','cancelled')),
        estimated_delivery DATE, delivered_at TIMESTAMPTZ, note TEXT, created_at TIMESTAMPTZ NOT NULL DEFAULT now())""")
    conn.execute("ALTER TABLE sb_shipments ADD COLUMN IF NOT EXISTS tracking_url TEXT")
    conn.execute("ALTER TABLE sb_shipments ADD COLUMN IF NOT EXISTS dispatched_at TIMESTAMPTZ")
    conn.execute("""CREATE TABLE IF NOT EXISTS sb_employees (
        id BIGSERIAL PRIMARY KEY, employee_code TEXT NOT NULL UNIQUE, full_name TEXT NOT NULL, email TEXT,
        department TEXT, designation TEXT, joining_date DATE, status TEXT NOT NULL DEFAULT 'active'
        CHECK(status IN ('active','inactive')), monthly_gross NUMERIC(14,2) NOT NULL DEFAULT 0 CHECK(monthly_gross>=0),
        created_at TIMESTAMPTZ NOT NULL DEFAULT now())""")
    conn.execute("""CREATE TABLE IF NOT EXISTS sb_payroll_runs (
        id BIGSERIAL PRIMARY KEY, period_start DATE NOT NULL, period_end DATE NOT NULL,
        status TEXT NOT NULL DEFAULT 'draft' CHECK(status IN ('draft','approved','paid')),
        created_by BIGINT, created_at TIMESTAMPTZ NOT NULL DEFAULT now(), UNIQUE(period_start,period_end))""")
    conn.execute("""CREATE TABLE IF NOT EXISTS sb_attendance (
        id BIGSERIAL PRIMARY KEY, employee_id BIGINT NOT NULL REFERENCES sb_employees(id), work_date DATE NOT NULL,
        status TEXT NOT NULL CHECK(status IN ('present','absent','half_day','leave','holiday','weekly_off')),
        hours_worked NUMERIC(5,2) NOT NULL DEFAULT 0 CHECK(hours_worked>=0 AND hours_worked<=24),
        note TEXT, created_by BIGINT, created_at TIMESTAMPTZ NOT NULL DEFAULT now(), UNIQUE(employee_id,work_date))""")
    conn.execute("""CREATE TABLE IF NOT EXISTS sb_leave_requests (
        id BIGSERIAL PRIMARY KEY, employee_id BIGINT NOT NULL REFERENCES sb_employees(id),
        start_date DATE NOT NULL, end_date DATE NOT NULL, leave_type TEXT NOT NULL,
        days NUMERIC(5,2) NOT NULL CHECK(days>0), paid BOOLEAN NOT NULL DEFAULT TRUE,
        reason TEXT, status TEXT NOT NULL DEFAULT 'pending' CHECK(status IN ('pending','approved','rejected')),
        reviewed_by BIGINT, reviewed_at TIMESTAMPTZ, created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
        CHECK(end_date>=start_date))""")
    conn.execute("""CREATE TABLE IF NOT EXISTS sb_payroll_lines (
        id BIGSERIAL PRIMARY KEY, run_id BIGINT NOT NULL REFERENCES sb_payroll_runs(id) ON DELETE CASCADE,
        employee_id BIGINT NOT NULL REFERENCES sb_employees(id), gross NUMERIC(14,2) NOT NULL,
        deductions NUMERIC(14,2) NOT NULL DEFAULT 0, net_pay NUMERIC(14,2) NOT NULL,
        UNIQUE(run_id,employee_id))""")

def _post_journal(conn: Any, entry_date: date, reference: str, description: str, source_module: str, source_id: int, lines: list[tuple[str, Decimal, Decimal]], user_id: int) -> int:
    """Post a balanced journal once per source module/source ID."""
    from .accounting import _ensure as ensure_accounting
    ensure_accounting(conn)
    existing = conn.execute(
        "SELECT id FROM sb_journals WHERE source_module=%s AND source_id=%s ORDER BY id LIMIT 1",
        (source_module, str(source_id)),
    ).fetchone()
    if existing:
        return int(existing["id"])
    resolved=[]
    for detail_type,debit,credit in lines:
        if debit == 0 and credit == 0:
            continue
        account=conn.execute("SELECT id FROM sb_accounts WHERE detail_type=%s AND is_active=TRUE ORDER BY id LIMIT 1",(detail_type,)).fetchone()
        if not account:
            raise HTTPException(status_code=503,detail=f"Accounting account is missing: {detail_type}")
        resolved.append((account["id"],debit,credit,detail_type))
    if sum((x[1] for x in resolved),Decimal("0")) != sum((x[2] for x in resolved),Decimal("0")):
        raise HTTPException(status_code=422,detail="Generated accounting journal is not balanced")
    journal=conn.execute("""INSERT INTO sb_journals(entry_date,reference,description,source_module,source_id,status,created_by)
        VALUES(%s,%s,%s,%s,%s,'posted',%s) RETURNING id""",(entry_date,reference,description,source_module,str(source_id),user_id)).fetchone()
    for account_id,debit,credit,detail in resolved:
        conn.execute("""INSERT INTO sb_journal_lines(journal_id,account_id,debit,credit,description)
            VALUES(%s,%s,%s,%s,%s)""",(journal["id"],account_id,debit,credit,detail.replace("_"," ")))
    return journal["id"]

class PartyInput(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    phone: str = Field(default="", max_length=40)
    email: str = Field(default="", max_length=254)
    gstin: str = Field(default="", max_length=15)

class VendorInput(PartyInput):
    address: dict[str, Any] = Field(default_factory=dict)
    payment_terms_days: int = Field(default=0, ge=0, le=365)


class ProductTaxInput(BaseModel):
    hsn_sac: str = Field(default="", max_length=20)
    gst_rate: Decimal = Field(default=Decimal("0"), ge=0, le=100)
    classification: str = Field(default="taxable", pattern="^(taxable|nil_rated|exempt|non_gst)$")

@router.get("/product-tax")
def list_product_tax(authorization: str | None = Header(default=None)) -> dict[str, Any]:
    _admin(authorization)
    try:
        with psycopg.connect(_db(), row_factory=dict_row, connect_timeout=8) as conn:
            _ensure(conn)
            return {"items": conn.execute("SELECT * FROM sb_product_tax ORDER BY variant_id").fetchall()}
    except Exception as exc:
        raise HTTPException(status_code=503, detail="Product GST mapping unavailable") from exc

@router.put("/product-tax/{variant_id}")
def set_product_tax(variant_id: int, body: ProductTaxInput, authorization: str | None = Header(default=None)) -> dict[str, Any]:
    _admin(authorization)
    try:
        with psycopg.connect(_db(), row_factory=dict_row, connect_timeout=8) as conn:
            _ensure(conn)
            exists=conn.execute("SELECT id FROM product_variants WHERE id=%s",(variant_id,)).fetchone()
            if not exists:
                raise HTTPException(status_code=404, detail="Product variant not found in catalogue")
            row=conn.execute("""INSERT INTO sb_product_tax(variant_id,hsn_sac,gst_rate,classification,updated_by)
                VALUES(%s,%s,%s,%s,%s) ON CONFLICT(variant_id) DO UPDATE SET hsn_sac=EXCLUDED.hsn_sac,
                gst_rate=EXCLUDED.gst_rate,classification=EXCLUDED.classification,updated_by=EXCLUDED.updated_by,updated_at=now()
                RETURNING *""",(variant_id,body.hsn_sac.strip() or None,body.gst_rate,body.classification,_current_user_id(authorization)))
            return {"item":row}
    except HTTPException: raise
    except Exception as exc:
        raise HTTPException(status_code=503, detail="Product GST mapping could not be saved") from exc

class StockInput(BaseModel):
    variant_id: int = Field(gt=0)
    warehouse: str = Field(default="Main", min_length=1, max_length=100)
    quantity: Decimal = Field(gt=0)
    movement_type: str = Field(pattern="^(opening|adjustment_in|adjustment_out|return_in|damage_out|transfer_in|transfer_out)$")
    note: str = Field(default="", max_length=500)

class PurchaseLineInput(BaseModel):
    variant_id: int = Field(gt=0)
    quantity: Decimal = Field(gt=0)
    unit_cost: Decimal = Field(ge=0)

class PurchaseInput(BaseModel):
    vendor_id: int = Field(gt=0)
    order_date: date = Field(default_factory=date.today)
    note: str = Field(default="", max_length=1000)
    lines: list[PurchaseLineInput] = Field(min_length=1, max_length=200)

class PurchaseReceiptLineInput(BaseModel):
    line_id: int = Field(gt=0)
    quantity: Decimal = Field(gt=0, le=1000000000)


class PurchaseReceiptInput(BaseModel):
    lines: list[PurchaseReceiptLineInput] = Field(min_length=1, max_length=200)


class POSLineInput(BaseModel):
    variant_id: int = Field(gt=0)
    quantity: Decimal = Field(gt=0)
    unit_price: Decimal | None = Field(default=None, ge=0)
    tax_rate: Decimal = Field(default=Decimal("0"), ge=0, le=100)

class POSInput(BaseModel):
    customer_id: int | None = Field(default=None, gt=0)
    payment_method: str = Field(pattern="^(cash|card|upi|other)$")
    lines: list[POSLineInput] = Field(min_length=1, max_length=100)

class ShipmentInput(BaseModel):
    order_type: str = Field(pattern="^(website|pos|purchase)$")
    order_id: int = Field(gt=0)
    carrier: str = Field(default="", max_length=120)
    tracking_number: str = Field(default="", max_length=160)
    tracking_url: str = Field(default="", max_length=1000)
    estimated_delivery: date | None = None
    note: str = Field(default="", max_length=1000)

class ShipmentUpdate(BaseModel):
    status: str = Field(pattern="^(created|packed|in_transit|out_for_delivery|delivered|exception|cancelled)$")
    note: str = Field(default="", max_length=1000)
    carrier: str = Field(default="", max_length=120)
    tracking_number: str = Field(default="", max_length=160)
    tracking_url: str = Field(default="", max_length=1000)
    estimated_delivery: date | None = None

class EmployeeInput(BaseModel):
    employee_code: str = Field(min_length=1, max_length=60)
    full_name: str = Field(min_length=1, max_length=200)
    email: str = Field(default="", max_length=254)
    department: str = Field(default="", max_length=100)
    designation: str = Field(default="", max_length=100)
    joining_date: date | None = None
    monthly_gross: Decimal = Field(default=Decimal("0"), ge=0)


class AttendanceInput(BaseModel):
    employee_id: int = Field(gt=0)
    work_date: date
    status: str = Field(pattern="^(present|absent|half_day|leave|holiday|weekly_off)$")
    hours_worked: Decimal = Field(default=Decimal("0"), ge=0, le=24)
    note: str = Field(default="", max_length=500)

class LeaveInput(BaseModel):
    employee_id: int = Field(gt=0)
    start_date: date
    end_date: date
    leave_type: str = Field(min_length=1, max_length=60)
    days: Decimal = Field(gt=0, le=366)
    paid: bool = True
    reason: str = Field(default="", max_length=1000)

@router.get("/attendance")
def list_attendance(authorization: str | None = Header(default=None), start_date: date | None = None, end_date: date | None = None) -> dict[str, Any]:
    _admin(authorization)
    try:
        with psycopg.connect(_db(),row_factory=dict_row,connect_timeout=8) as conn:
            _ensure(conn)
            return {"items":conn.execute("""SELECT a.*,e.employee_code,e.full_name FROM sb_attendance a JOIN sb_employees e ON e.id=a.employee_id
                WHERE (%s::date IS NULL OR a.work_date >= %s) AND (%s::date IS NULL OR a.work_date <= %s)
                ORDER BY a.work_date DESC,e.full_name LIMIT 1000""",(start_date,start_date,end_date,end_date)).fetchall()}
    except Exception as exc: raise HTTPException(status_code=503,detail="Attendance records unavailable") from exc

@router.post("/attendance",status_code=201)
def save_attendance(body:AttendanceInput,authorization:str|None=Header(default=None))->dict[str,Any]:
    user=_admin(authorization)
    try:
        with psycopg.connect(_db(),row_factory=dict_row,connect_timeout=8) as conn:
            _ensure(conn)
            row=conn.execute("""INSERT INTO sb_attendance(employee_id,work_date,status,hours_worked,note,created_by)
                VALUES(%s,%s,%s,%s,%s,%s) ON CONFLICT(employee_id,work_date) DO UPDATE SET status=EXCLUDED.status,
                hours_worked=EXCLUDED.hours_worked,note=EXCLUDED.note,created_by=EXCLUDED.created_by
                RETURNING *""",(body.employee_id,body.work_date,body.status,body.hours_worked,body.note.strip() or None,user["id"])).fetchone()
            return {"attendance":row}
    except Exception as exc: raise HTTPException(status_code=503,detail="Attendance could not be saved") from exc

@router.get("/leave")
def list_leave(authorization:str|None=Header(default=None))->dict[str,Any]:
    _admin(authorization)
    try:
        with psycopg.connect(_db(),row_factory=dict_row,connect_timeout=8) as conn:
            _ensure(conn)
            return {"items":conn.execute("""SELECT l.*,e.employee_code,e.full_name FROM sb_leave_requests l JOIN sb_employees e ON e.id=l.employee_id
                ORDER BY l.created_at DESC LIMIT 1000""").fetchall()}
    except Exception as exc: raise HTTPException(status_code=503,detail="Leave requests unavailable") from exc

@router.post("/leave",status_code=201)
def create_leave(body:LeaveInput,authorization:str|None=Header(default=None))->dict[str,Any]:
    _admin(authorization)
    if body.end_date<body.start_date: raise HTTPException(status_code=422,detail="Leave end date must not precede start date")
    try:
        with psycopg.connect(_db(),row_factory=dict_row,connect_timeout=8) as conn:
            _ensure(conn)
            with conn.transaction():
                employee=conn.execute("SELECT id FROM sb_employees WHERE id=%s",(body.employee_id,)).fetchone()
                if not employee:
                    raise HTTPException(status_code=404,detail="Employee not found")
                overlap=conn.execute("""SELECT id FROM sb_leave_requests
                    WHERE employee_id=%s AND status IN ('pending','approved')
                    AND start_date<=%s AND end_date>=%s
                    LIMIT 1""",(body.employee_id,body.end_date,body.start_date)).fetchone()
                if overlap:
                    raise HTTPException(status_code=409,detail=f"Leave dates overlap with existing request {overlap['id']}.")
                row=conn.execute("""INSERT INTO sb_leave_requests(employee_id,start_date,end_date,leave_type,days,paid,reason)
                    VALUES(%s,%s,%s,%s,%s,%s,%s) RETURNING *""",(body.employee_id,body.start_date,body.end_date,body.leave_type.strip(),body.days,body.paid,body.reason.strip() or None)).fetchone()
                return {"leave":row}
    except Exception as exc: raise HTTPException(status_code=503,detail="Leave request could not be saved") from exc

@router.patch("/leave/{leave_id}")
def review_leave(leave_id:int,status:str=Query(...,pattern="^(approved|rejected)$"),authorization:str|None=Header(default=None))->dict[str,Any]:
    user=_admin(authorization)
    try:
        with psycopg.connect(_db(),row_factory=dict_row,connect_timeout=8) as conn:
            _ensure(conn)
            row=conn.execute("""UPDATE sb_leave_requests SET status=%s,reviewed_by=%s,reviewed_at=now()
                WHERE id=%s AND status='pending' RETURNING *""",(status,user["id"],leave_id)).fetchone()
            if not row: raise HTTPException(status_code=404,detail="Pending leave request not found")
            return {"leave":row}
    except HTTPException: raise
    except Exception as exc: raise HTTPException(status_code=503,detail="Leave request could not be reviewed") from exc

class PayrollInput(BaseModel):
    period_start: date
    period_end: date
    deductions: dict[int, Decimal] = Field(default_factory=dict)

@router.get("/customers")
def customers(authorization: str | None = Header(default=None), search: str = "", limit: int = Query(100, ge=1, le=500)) -> dict[str, Any]:
    _admin(authorization)
    try:
        with psycopg.connect(_db(), row_factory=dict_row, connect_timeout=8) as conn:
            _ensure(conn)
            rows=conn.execute("""SELECT * FROM sb_customers WHERE (%s='' OR name ILIKE %s OR email ILIKE %s OR phone ILIKE %s)
                ORDER BY name LIMIT %s""",(search,f"%{search}%",f"%{search}%",f"%{search}%",limit)).fetchall()
            return {"items":rows}
    except Exception as exc: raise HTTPException(status_code=503,detail="Customer records unavailable") from exc

@router.post("/customers",status_code=201)
def add_customer(body: PartyInput, authorization: str | None = Header(default=None)) -> dict[str,Any]:
    _admin(authorization)
    try:
        with psycopg.connect(_db(),row_factory=dict_row,connect_timeout=8) as conn:
            _ensure(conn)
            row=conn.execute("""INSERT INTO sb_customers(name,phone,email,gstin) VALUES(%s,%s,%s,%s)
                RETURNING id,name,phone,email,gstin,created_at""",(body.name.strip(),body.phone.strip() or None,body.email.strip().lower() or None,body.gstin.strip().upper() or None)).fetchone()
            return {"customer":row}
    except psycopg.errors.UniqueViolation as exc: raise HTTPException(status_code=409,detail="A customer with this email already exists") from exc
    except Exception as exc: raise HTTPException(status_code=503,detail="Customer could not be saved") from exc

@router.get("/vendors")
def vendors(authorization: str | None = Header(default=None), search: str = "", limit: int = Query(100, ge=1, le=500)) -> dict[str,Any]:
    _admin(authorization)
    try:
        with psycopg.connect(_db(),row_factory=dict_row,connect_timeout=8) as conn:
            _ensure(conn)
            return {"items":conn.execute("""SELECT * FROM sb_vendors WHERE (%s='' OR name ILIKE %s OR email ILIKE %s OR phone ILIKE %s)
                ORDER BY name LIMIT %s""",(search,f"%{search}%",f"%{search}%",f"%{search}%",limit)).fetchall()}
    except Exception as exc: raise HTTPException(status_code=503,detail="Vendor records unavailable") from exc

@router.post("/vendors",status_code=201)
def add_vendor(body: VendorInput, authorization: str | None = Header(default=None)) -> dict[str,Any]:
    _admin(authorization)
    try:
        with psycopg.connect(_db(),row_factory=dict_row,connect_timeout=8) as conn:
            _ensure(conn)
            row=conn.execute("""INSERT INTO sb_vendors(name,phone,email,gstin,address,payment_terms_days) VALUES(%s,%s,%s,%s,%s,%s)
                RETURNING *""",(body.name.strip(),body.phone.strip() or None,body.email.strip().lower() or None,body.gstin.strip().upper() or None,psycopg.types.json.Jsonb(body.address),body.payment_terms_days)).fetchone()
            return {"vendor":row}
    except psycopg.errors.UniqueViolation as exc: raise HTTPException(status_code=409,detail="A vendor with this email already exists") from exc
    except Exception as exc: raise HTTPException(status_code=503,detail="Vendor could not be saved") from exc

@router.get("/inventory")
def inventory(authorization: str | None = Header(default=None), warehouse: str | None = None) -> dict[str,Any]:
    _admin(authorization)
    try:
        with psycopg.connect(_db(),row_factory=dict_row,connect_timeout=8) as conn:
            _ensure(conn)
            rows=conn.execute("SELECT variant_id,warehouse,quantity,updated_at FROM sb_stock WHERE (%s::text IS NULL OR warehouse=%s) ORDER BY warehouse,variant_id",(warehouse,warehouse)).fetchall()
            return {"items":rows,"source":"stock_ledger"}
    except Exception as exc: raise HTTPException(status_code=503,detail="Inventory unavailable") from exc

@router.post("/inventory/movements",status_code=201)
def stock_movement(body: StockInput, authorization: str | None = Header(default=None)) -> dict[str,Any]:
    user=_admin(authorization)
    try:
        with psycopg.connect(_db(),row_factory=dict_row,connect_timeout=8) as conn:
            _ensure(conn)
            with conn.transaction():
                if not conn.execute("SELECT id FROM product_variants WHERE id=%s",(body.variant_id,)).fetchone():
                    raise HTTPException(status_code=404,detail="Product variant not found")
                # Ensure a row exists before locking it. SELECT ... FOR UPDATE does not
                # lock a missing row, so concurrent first movements could otherwise
                # both read zero and overwrite each other's stock balance.
                conn.execute("""INSERT INTO sb_stock(variant_id,warehouse,quantity)
                    VALUES(%s,%s,0) ON CONFLICT(variant_id,warehouse) DO NOTHING""",
                    (body.variant_id,body.warehouse))
                current=conn.execute("SELECT quantity FROM sb_stock WHERE variant_id=%s AND warehouse=%s FOR UPDATE",(body.variant_id,body.warehouse)).fetchone()
                old=Decimal(str(current["quantity"]))
                delta=body.quantity if body.movement_type in {"opening","adjustment_in","return_in","transfer_in"} else -body.quantity
                if old+delta<0: raise HTTPException(status_code=422,detail="Insufficient stock for this movement")
                conn.execute("""UPDATE sb_stock SET quantity=%s,updated_at=now()
                    WHERE variant_id=%s AND warehouse=%s""",(old+delta,body.variant_id,body.warehouse))
                row=conn.execute("""INSERT INTO sb_stock_movements(variant_id,warehouse,movement_type,quantity,note,created_by)
                    VALUES(%s,%s,%s,%s,%s,%s) RETURNING *""",(body.variant_id,body.warehouse,body.movement_type,body.quantity,body.note.strip() or None,user["id"])).fetchone()
                return {"movement":row,"balance":old+delta}
    except HTTPException: raise
    except Exception as exc: raise HTTPException(status_code=503,detail="Stock movement could not be saved") from exc

@router.get("/inventory/movements")
def stock_movements(authorization: str | None = Header(default=None), variant_id: int | None = None, limit: int = Query(100,ge=1,le=500)) -> dict[str,Any]:
    _admin(authorization)
    try:
        with psycopg.connect(_db(),row_factory=dict_row,connect_timeout=8) as conn:
            _ensure(conn)
            return {"items":conn.execute("""SELECT * FROM sb_stock_movements WHERE (%s::bigint IS NULL OR variant_id=%s)
                ORDER BY id DESC LIMIT %s""",(variant_id,variant_id,limit)).fetchall()}
    except Exception as exc: raise HTTPException(status_code=503,detail="Stock movement history unavailable") from exc

@router.post("/purchases",status_code=201)
def create_purchase(body: PurchaseInput,authorization: str | None = Header(default=None))->dict[str,Any]:
    user=_admin(authorization)
    try:
        with psycopg.connect(_db(),row_factory=dict_row,connect_timeout=8) as conn:
            _ensure(conn)
            with conn.transaction():
                if not conn.execute("SELECT id FROM sb_vendors WHERE id=%s",(body.vendor_id,)).fetchone(): raise HTTPException(status_code=404,detail="Vendor not found")
                variant_ids={line.variant_id for line in body.lines}
                found_ids={int(row["id"]) for row in conn.execute(
                    "SELECT id FROM product_variants WHERE id = ANY(%s)",(list(variant_ids),)
                ).fetchall()}
                missing_ids=sorted(variant_ids-found_ids)
                if missing_ids:
                    raise HTTPException(status_code=422,detail=f"Unknown product variant ID(s): {', '.join(map(str,missing_ids))}.")
                total=sum((x.quantity*x.unit_cost for x in body.lines),Decimal("0"))
                po=conn.execute("""INSERT INTO sb_purchase_orders(vendor_id,order_date,total,note,created_by)
                    VALUES(%s,%s,%s,%s,%s) RETURNING *""",(body.vendor_id,body.order_date,total,body.note.strip() or None,user["id"])).fetchone()
                lines=[]
                for line in body.lines:
                    row=conn.execute("""INSERT INTO sb_purchase_lines(purchase_id,variant_id,quantity,unit_cost)
                        VALUES(%s,%s,%s,%s) RETURNING *""",(po["id"],line.variant_id,line.quantity,line.unit_cost)).fetchone()
                    lines.append(row)
                return {"purchase":po,"lines":lines}
    except HTTPException: raise
    except Exception as exc: raise HTTPException(status_code=503,detail="Purchase order could not be saved") from exc

@router.get("/purchases")
def purchases(authorization: str | None = Header(default=None),limit:int=Query(100,ge=1,le=500))->dict[str,Any]:
    _admin(authorization)
    try:
        with psycopg.connect(_db(),row_factory=dict_row,connect_timeout=8) as conn:
            _ensure(conn)
            return {"items":conn.execute("""SELECT p.*,v.name AS vendor_name FROM sb_purchase_orders p JOIN sb_vendors v ON v.id=p.vendor_id ORDER BY p.id DESC LIMIT %s""",(limit,)).fetchall()}
    except Exception as exc: raise HTTPException(status_code=503,detail="Purchase orders unavailable") from exc

@router.get("/purchases/{purchase_id}")
def purchase_detail(purchase_id:int,authorization:str|None=Header(default=None))->dict[str,Any]:
    _admin(authorization)
    try:
        with psycopg.connect(_db(),row_factory=dict_row,connect_timeout=8) as conn:
            _ensure(conn)
            purchase=conn.execute("""SELECT p.*,v.name AS vendor_name FROM sb_purchase_orders p
                JOIN sb_vendors v ON v.id=p.vendor_id WHERE p.id=%s""",(purchase_id,)).fetchone()
            if not purchase: raise HTTPException(status_code=404,detail="Purchase order not found")
            lines=conn.execute("""SELECT id,purchase_id,variant_id,quantity,received_qty,
                quantity-received_qty AS outstanding_quantity,unit_cost,
                (quantity-received_qty)*unit_cost AS outstanding_value
                FROM sb_purchase_lines WHERE purchase_id=%s ORDER BY id""",(purchase_id,)).fetchall()
            receipts=conn.execute("""SELECT id,purchase_id,received_value,received_by,created_at
                FROM sb_purchase_receipts WHERE purchase_id=%s ORDER BY id DESC""",(purchase_id,)).fetchall()
            return {"purchase":purchase,"lines":lines,"receipts":receipts}
    except HTTPException: raise
    except Exception as exc: raise HTTPException(status_code=503,detail="Purchase order details unavailable") from exc


@router.post("/purchases/{purchase_id}/receive")
def receive_purchase(
    purchase_id:int, body:PurchaseReceiptInput|None=None,
    authorization:str|None=Header(default=None)
)->dict[str,Any]:
    user=_admin(authorization)
    try:
        with psycopg.connect(_db(),row_factory=dict_row,connect_timeout=8) as conn:
            _ensure(conn)
            with conn.transaction():
                po=conn.execute("SELECT * FROM sb_purchase_orders WHERE id=%s FOR UPDATE",(purchase_id,)).fetchone()
                if not po: raise HTTPException(status_code=404,detail="Purchase order not found")
                if po["status"] in ("received","cancelled"): raise HTTPException(status_code=409,detail="Purchase order is already closed")
                lines=conn.execute("SELECT * FROM sb_purchase_lines WHERE purchase_id=%s ORDER BY id FOR UPDATE",(purchase_id,)).fetchall()
                if not lines: raise HTTPException(status_code=409,detail="Purchase order has no lines to receive")
                remaining_by_id={int(line["id"]):Decimal(str(line["quantity"]))-Decimal(str(line["received_qty"])) for line in lines}
                if body is None:
                    requested={line_id:qty for line_id,qty in remaining_by_id.items() if qty>0}
                else:
                    requested={}
                    for item in body.lines:
                        if item.line_id in requested:
                            raise HTTPException(status_code=422,detail="A purchase line can appear only once per receipt.")
                        if item.line_id not in remaining_by_id:
                            raise HTTPException(status_code=422,detail=f"Purchase line {item.line_id} does not belong to this purchase order.")
                        if item.quantity>remaining_by_id[item.line_id]:
                            raise HTTPException(status_code=422,detail=f"Receipt quantity exceeds the outstanding quantity for line {item.line_id}.")
                        requested[item.line_id]=item.quantity
                if not requested or any(qty<=0 for qty in requested.values()):
                    raise HTTPException(status_code=422,detail="Enter at least one positive receipt quantity.")
                received_value=Decimal("0")
                received_lines=[]
                by_id={int(line["id"]):line for line in lines}
                for line_id,qty in requested.items():
                    line=by_id[line_id]
                    received_value+=(qty*Decimal(str(line["unit_cost"]))).quantize(Decimal("0.01"))
                    conn.execute("""INSERT INTO sb_stock(variant_id,warehouse,quantity) VALUES(%s,'Main',%s)
                        ON CONFLICT(variant_id,warehouse) DO UPDATE SET quantity=sb_stock.quantity+EXCLUDED.quantity,updated_at=now()""",
                        (line["variant_id"],qty))
                    conn.execute("""INSERT INTO sb_stock_movements(variant_id,warehouse,movement_type,quantity,reference_type,reference_id,created_by)
                        VALUES(%s,'Main','purchase_receipt',%s,'purchase',%s,%s)""",
                        (line["variant_id"],qty,purchase_id,user["id"]))
                    conn.execute("UPDATE sb_purchase_lines SET received_qty=received_qty+%s WHERE id=%s",(qty,line_id))
                    received_lines.append({"line_id":line_id,"variant_id":int(line["variant_id"]),"received_quantity":qty})
                updated=conn.execute("""SELECT COUNT(*) FILTER(WHERE received_qty<quantity) AS outstanding
                    FROM sb_purchase_lines WHERE purchase_id=%s""",(purchase_id,)).fetchone()
                status="part_received" if int(updated["outstanding"])>0 else "received"
                conn.execute("UPDATE sb_purchase_orders SET status=%s WHERE id=%s",(status,purchase_id))
                receipt=conn.execute("""INSERT INTO sb_purchase_receipts(purchase_id,received_value,received_by)
                    VALUES(%s,%s,%s) RETURNING id""",(purchase_id,received_value,user["id"])).fetchone()
                journal_id=None
                if received_value>0:
                    journal_id=_post_journal(conn,date.today(),f"PO-{purchase_id}-GR-{receipt['id']}",
                        f"Goods receipt {receipt['id']} for purchase order {purchase_id}","purchase_receipt",int(receipt["id"]),
                        [("inventory",received_value,Decimal("0")),("accounts_payable",Decimal("0"),received_value)],user["id"])
                return {"purchase_id":purchase_id,"receipt_id":receipt["id"],"status":status,
                    "received_value":received_value,"lines":received_lines,"journal_id":journal_id,
                    "message":"Received quantities posted to inventory and accounting."}
    except HTTPException: raise
    except Exception as exc: raise HTTPException(status_code=503,detail="Purchase receipt could not be posted") from exc

@router.post("/pos/sales",status_code=201)
def pos_sale(body:POSInput,authorization:str|None=Header(default=None))->dict[str,Any]:
    user=_admin(authorization)
    try:
        with psycopg.connect(_db(),row_factory=dict_row,connect_timeout=8) as conn:
            _ensure(conn)
            with conn.transaction():
                if body.customer_id and not conn.execute("SELECT id FROM sb_customers WHERE id=%s",(body.customer_id,)).fetchone(): raise HTTPException(status_code=404,detail="Customer not found")
                variant_ids=[line.variant_id for line in body.lines]
                if len(variant_ids)!=len(set(variant_ids)): raise HTTPException(status_code=422,detail="Each product variant can appear only once per POS sale; combine its quantity.")
                subtotal=Decimal("0"); tax_total=Decimal("0"); cogs_total=Decimal("0"); resolved=[]
                for line in body.lines:
                    stock=conn.execute("SELECT quantity FROM sb_stock WHERE variant_id=%s AND warehouse='Main' FOR UPDATE",(line.variant_id,)).fetchone()
                    available=Decimal(str(stock["quantity"])) if stock else Decimal("0")
                    if available<line.quantity: raise HTTPException(status_code=422,detail=f"Insufficient stock for variant {line.variant_id}; available {available}")
                    product=conn.execute("""SELECT selling_price FROM product_variants WHERE id=%s""",(line.variant_id,)).fetchone()
                    if not product: raise HTTPException(status_code=404,detail=f"Product variant {line.variant_id} not found")
                    price=Decimal(str(product["selling_price"])) if line.unit_price is None else line.unit_price
                    tax_mapping=conn.execute("SELECT gst_rate,classification FROM sb_product_tax WHERE variant_id=%s",(line.variant_id,)).fetchone()
                    applied_rate=Decimal(str(tax_mapping["gst_rate"])) if tax_mapping and tax_mapping["classification"]=="taxable" else (Decimal("0") if tax_mapping else line.tax_rate)
                    base=price*line.quantity; tax=(base*applied_rate/Decimal("100")).quantize(Decimal("0.01"))
                    cost_row=conn.execute("""SELECT COALESCE(SUM(pl.unit_cost*pl.received_qty)/NULLIF(SUM(pl.received_qty),0),0) AS avg_cost
                        FROM sb_purchase_lines pl JOIN sb_purchase_orders po ON po.id=pl.purchase_id
                        WHERE pl.variant_id=%s AND po.status IN ('part_received','received')""",(line.variant_id,)).fetchone()
                    avg_cost=Decimal(str(cost_row["avg_cost"] or 0))
                    cogs_total+=(avg_cost*line.quantity).quantize(Decimal("0.01"))
                    subtotal+=base; tax_total+=tax; resolved.append((line,price,applied_rate,base+tax))
                total=subtotal+tax_total
                receipt="POS-"+__import__("secrets").token_hex(6).upper()
                sale=conn.execute("""INSERT INTO sb_pos_sales(receipt_number,customer_id,subtotal,tax_total,total,payment_method,created_by)
                    VALUES(%s,%s,%s,%s,%s,%s,%s) RETURNING *""",(receipt,body.customer_id,subtotal,tax_total,total,body.payment_method,user["id"])).fetchone()
                for line,price,applied_rate,line_total in resolved:
                    conn.execute("""INSERT INTO sb_pos_sale_lines(sale_id,variant_id,quantity,unit_price,tax_rate,line_total)
                        VALUES(%s,%s,%s,%s,%s,%s)""",(sale["id"],line.variant_id,line.quantity,price,applied_rate,line_total))
                    conn.execute("UPDATE sb_stock SET quantity=quantity-%s,updated_at=now() WHERE variant_id=%s AND warehouse='Main'",(line.quantity,line.variant_id))
                    conn.execute("""INSERT INTO sb_stock_movements(variant_id,warehouse,movement_type,quantity,reference_type,reference_id,created_by)
                        VALUES(%s,'Main','pos_sale',%s,'pos',%s,%s)""",(line.variant_id,line.quantity,sale["id"],user["id"]))
                from .invoices import create_invoice
                customer=conn.execute("SELECT name,email,phone FROM sb_customers WHERE id=%s",(body.customer_id,)).fetchone() if body.customer_id else None
                invoice_lines=[]
                for line,price,applied_rate,line_total in resolved:
                    line_subtotal=(price*line.quantity).quantize(Decimal("0.01"))
                    invoice_lines.append({"description":"Product variant "+str(line.variant_id),"variant_id":line.variant_id,
                        "quantity":line.quantity,"unit_price":price,"tax_rate":applied_rate,
                        "line_subtotal":line_subtotal,"line_tax":line_total-line_subtotal,"line_total":line_total})
                create_invoice(conn,source_type="pos",source_id=int(sale["id"]),
                    customer_name=(customer["name"] if customer else "Walk-in customer"),
                    customer_email=(customer["email"] if customer else None),customer_phone=(customer["phone"] if customer else None),
                    subtotal=subtotal,tax_total=tax_total,total=total,lines=invoice_lines)
                conn.execute("UPDATE sb_sales_invoices SET amount_received=%s,payment_status='paid' WHERE source_type='pos' AND source_id=%s",(total,sale["id"]))
                journal_lines=[("cash",total,Decimal("0")),("sales",Decimal("0"),subtotal)]
                if tax_total:
                    journal_lines.append(("output_gst",Decimal("0"),tax_total))
                if cogs_total:
                    journal_lines.extend([("cost_of_goods_sold",cogs_total,Decimal("0")),("inventory",Decimal("0"),cogs_total)])
                journal_id=_post_journal(conn,date.today(),receipt,"POS sale "+receipt,"pos",sale["id"],journal_lines,user["id"])
                loyalty_award=None
                if body.customer_id:
                    loyalty_customer=conn.execute("SELECT u.id FROM sb_customers c JOIN app_users u ON lower(u.email)=lower(c.email) WHERE c.id=%s AND c.email IS NOT NULL AND c.email<>'' LIMIT 1",(body.customer_id,)).fetchone()
                    if loyalty_customer:
                        loyalty_user_id=int(loyalty_customer["id"])
                        from .loyalty import _ensure as ensure_loyalty, _program as loyalty_program, _wallet as loyalty_wallet, _tier as loyalty_tier, _post as post_loyalty
                        ensure_loyalty(conn)
                        program=loyalty_program(conn)
                        if program["enabled"] and Decimal(str(program["earn_rate"]))>0:
                            wallet=loyalty_wallet(conn,loyalty_user_id)
                            tier=loyalty_tier(conn,int(wallet["lifetime_earned"]))
                            basis=total if program["earn_basis"]=="total" else subtotal
                            coins=int(basis*Decimal(str(program["earn_rate"]))*Decimal(str(tier["earn_multiplier"])))
                            if coins>0:
                                expiry=None
                                if program["expiry_days"] is not None:
                                    expiry=conn.execute("SELECT now() + (%s * interval '1 day') AS value",(program["expiry_days"],)).fetchone()["value"]
                                loyalty_award=post_loyalty(conn,loyalty_user_id,"earn",coins,"Super Coins earned for POS receipt "+receipt,order_id=int(sale["id"]),key="pos:"+str(sale["id"])+":earn",expires_at=expiry)
                return {"sale":sale,"receipt_number":receipt,"journal_id":journal_id,"loyalty_award":loyalty_award,"message":"POS sale saved, inventory deducted and accounting journal posted atomically."}
    except HTTPException: raise
    except Exception as exc: raise HTTPException(status_code=503,detail="POS sale could not be completed") from exc

@router.get("/pos/sales")
def pos_sales(authorization:str|None=Header(default=None),limit:int=Query(100,ge=1,le=500))->dict[str,Any]:
    _admin(authorization)
    try:
        with psycopg.connect(_db(),row_factory=dict_row,connect_timeout=8) as conn:
            _ensure(conn)
            return {"items":conn.execute("SELECT * FROM sb_pos_sales ORDER BY id DESC LIMIT %s",(limit,)).fetchall()}
    except Exception as exc: raise HTTPException(status_code=503,detail="POS sales unavailable") from exc

@router.get("/pos/sales/{sale_id}")
def pos_sale_detail(sale_id:int,authorization:str|None=Header(default=None))->dict[str,Any]:
    _admin(authorization)
    try:
        with psycopg.connect(_db(),row_factory=dict_row,connect_timeout=8) as conn:
            _ensure(conn)
            sale=conn.execute("""SELECT s.*,c.name AS customer_name,c.email AS customer_email
                FROM sb_pos_sales s LEFT JOIN sb_customers c ON c.id=s.customer_id
                WHERE s.id=%s""",(sale_id,)).fetchone()
            if not sale:
                raise HTTPException(status_code=404,detail="POS sale not found")
            lines=conn.execute("""SELECT id,sale_id,variant_id,quantity,unit_price,tax_rate,line_total
                FROM sb_pos_sale_lines WHERE sale_id=%s ORDER BY id""",(sale_id,)).fetchall()
            return {"sale":sale,"lines":lines}
    except HTTPException: raise
    except Exception as exc: raise HTTPException(status_code=503,detail="POS sale details unavailable") from exc

@router.post("/shipments",status_code=201)
def create_shipment(body:ShipmentInput,authorization:str|None=Header(default=None))->dict[str,Any]:
    _admin(authorization)
    try:
        with psycopg.connect(_db(),row_factory=dict_row,connect_timeout=8) as conn:
            _ensure(conn)
            tracking_url = body.tracking_url.strip()
            if tracking_url and not tracking_url.startswith(("https://", "http://")):
                raise HTTPException(status_code=422, detail="Tracking URL must start with http:// or https://")
            if body.order_type == "website":
                order = conn.execute("SELECT id,status FROM store_orders WHERE id=%s FOR UPDATE", (body.order_id,)).fetchone()
                if not order:
                    raise HTTPException(status_code=404, detail="Website order not found")
                if order["status"] not in ("confirmed", "processing", "packed", "shipped"):
                    raise HTTPException(status_code=409, detail="Confirm the website order before dispatching it")
            row=conn.execute("""INSERT INTO sb_shipments(order_type,order_id,carrier,tracking_number,tracking_url,estimated_delivery,note,status,dispatched_at)
                VALUES(%s,%s,%s,%s,%s,%s,%s,%s,CASE WHEN %s='website' THEN now() ELSE NULL END) RETURNING *""",
                (body.order_type,body.order_id,body.carrier.strip() or None,body.tracking_number.strip() or None,tracking_url or None,
                 body.estimated_delivery,body.note.strip() or None,"in_transit" if body.order_type == "website" else "created",body.order_type)).fetchone()
            if body.order_type == "website":
                conn.execute("UPDATE store_orders SET status='shipped',updated_at=now() WHERE id=%s AND status IN ('confirmed','processing','packed')", (body.order_id,))
            return {"shipment":row}
    except HTTPException:
        raise
    except Exception as exc: raise HTTPException(status_code=503,detail="Shipment could not be created") from exc

@router.get("/shipments")
def shipments(authorization:str|None=Header(default=None),limit:int=Query(100,ge=1,le=500))->dict[str,Any]:
    _admin(authorization)
    try:
        with psycopg.connect(_db(),row_factory=dict_row,connect_timeout=8) as conn:
            _ensure(conn)
            return {"items":conn.execute("SELECT * FROM sb_shipments ORDER BY id DESC LIMIT %s",(limit,)).fetchall()}
    except Exception as exc: raise HTTPException(status_code=503,detail="Shipments unavailable") from exc

@router.patch("/shipments/{shipment_id}")
def update_shipment(shipment_id:int,body:ShipmentUpdate,authorization:str|None=Header(default=None))->dict[str,Any]:
    user=_admin(authorization)
    try:
        with psycopg.connect(_db(),row_factory=dict_row,connect_timeout=8) as conn:
            _ensure(conn)
            with conn.transaction():
                shipment=conn.execute("SELECT * FROM sb_shipments WHERE id=%s FOR UPDATE",(shipment_id,)).fetchone()
                if not shipment: raise HTTPException(status_code=404,detail="Shipment not found")
                if shipment["status"] in ("delivered","cancelled") and body.status != shipment["status"]:
                    raise HTTPException(status_code=409,detail=f"A {shipment['status']} shipment is closed and cannot change status.")
                tracking_url = body.tracking_url.strip()
                if tracking_url and not tracking_url.startswith(("https://", "http://")):
                    raise HTTPException(status_code=422, detail="Tracking URL must start with http:// or https://")
                row=conn.execute("""UPDATE sb_shipments SET status=%s,note=COALESCE(NULLIF(%s,''),note),
                    carrier=COALESCE(NULLIF(%s,''),carrier),tracking_number=COALESCE(NULLIF(%s,''),tracking_number),
                    tracking_url=COALESCE(NULLIF(%s,''),tracking_url),estimated_delivery=COALESCE(%s,estimated_delivery),
                    dispatched_at=CASE WHEN %s='in_transit' AND dispatched_at IS NULL THEN now() ELSE dispatched_at END,
                    delivered_at=CASE WHEN %s='delivered' AND delivered_at IS NULL THEN now() ELSE delivered_at END WHERE id=%s RETURNING *""",
                    (body.status,body.note,body.carrier.strip(),body.tracking_number.strip(),tracking_url,body.estimated_delivery,body.status,body.status,shipment_id)).fetchone()
                journal_id=None
                target=None
                if shipment["order_type"]=="website" and conn.execute("SELECT to_regclass('public.store_orders') AS name").fetchone()["name"]:
                    order=conn.execute("SELECT * FROM store_orders WHERE id=%s FOR UPDATE",(shipment["order_id"],)).fetchone()
                    mapped={"packed":"packed","in_transit":"shipped","out_for_delivery":"shipped","delivered":"delivered","cancelled":"cancelled"}
                    target=mapped.get(body.status)
                    if order and target and order["status"] not in ("delivered","cancelled"):
                        if target=="cancelled":
                            order_lines=conn.execute("SELECT variant_id,quantity FROM store_order_items WHERE order_id=%s",(order["id"],)).fetchall()
                            for line in order_lines:
                                reserved=conn.execute("""SELECT warehouse FROM sb_stock_movements WHERE variant_id=%s AND reference_type='website_order'
                                    AND reference_id=%s AND movement_type='website_sale' ORDER BY id LIMIT 1""",(line["variant_id"],order["id"])).fetchone()
                                stock=conn.execute("SELECT quantity FROM sb_stock WHERE variant_id=%s AND warehouse=%s FOR UPDATE",(line["variant_id"],reserved["warehouse"] if reserved else "Main")).fetchone()
                                if reserved and stock:
                                    conn.execute("UPDATE sb_stock SET quantity=quantity+%s,updated_at=now() WHERE variant_id=%s AND warehouse=%s",(line["quantity"],line["variant_id"],reserved["warehouse"]))
                                    conn.execute("""INSERT INTO sb_stock_movements(variant_id,warehouse,movement_type,quantity,reference_type,reference_id,created_by,note)
                                        VALUES(%s,%s,'return_in',%s,'website_order_cancel',%s,%s,'Restore order-placement reservation')""",(line["variant_id"],reserved["warehouse"],line["quantity"],order["id"],user["id"]))
                        conn.execute("UPDATE store_orders SET status=%s,updated_at=now() WHERE id=%s",(target,order["id"]))
                        if target=="delivered":
                            from .accounting import _ensure as ensure_accounting
                            ensure_accounting(conn)
                            subtotal=Decimal(str(order["subtotal"])); total=Decimal(str(order["total"])); shipping=Decimal(str(order["shipping_fee"]))
                            discount=Decimal(str(order.get("loyalty_discount") or 0))
                            journal_lines=[("accounts_receivable",total,Decimal("0")),("sales",Decimal("0"),subtotal-discount)]
                            if shipping: journal_lines.append(("other_income",Decimal("0"),shipping))
                            cost_rows=conn.execute("""SELECT oi.variant_id,oi.quantity,
                                COALESCE(SUM(CASE WHEN po.id IS NOT NULL THEN pl.unit_cost*pl.received_qty ELSE 0 END)/
                                NULLIF(SUM(CASE WHEN po.id IS NOT NULL THEN pl.received_qty ELSE 0 END),0),0) AS avg_cost
                                FROM store_order_items oi LEFT JOIN sb_purchase_lines pl ON pl.variant_id=oi.variant_id
                                LEFT JOIN sb_purchase_orders po ON po.id=pl.purchase_id AND po.status IN ('part_received','received')
                                WHERE oi.order_id=%s GROUP BY oi.variant_id,oi.quantity""",(order["id"],)).fetchall()
                            cogs=sum((Decimal(str(x["avg_cost"] or 0))*Decimal(str(x["quantity"])) for x in cost_rows),Decimal("0")).quantize(Decimal("0.01"))
                            if cogs: journal_lines.extend([("cost_of_goods_sold",cogs,Decimal("0")),("inventory",Decimal("0"),cogs)])
                            journal_id=_post_journal(conn,date.today(),order["order_number"],"Website sale "+order["order_number"],"website",order["id"],journal_lines,user["id"])
                            from .loyalty import award_order_coins
                            award_order_coins(conn,int(order["user_id"]),int(order["id"]),subtotal-discount,total)
                return {"shipment":row,"linked_order_status":target if shipment["order_type"]=="website" else None,"journal_id":journal_id}
    except HTTPException: raise
    except Exception as exc: raise HTTPException(status_code=503,detail="Shipment could not be updated") from exc

@router.post("/employees",status_code=201)
def add_employee(body:EmployeeInput,authorization:str|None=Header(default=None))->dict[str,Any]:
    _admin(authorization)
    try:
        with psycopg.connect(_db(),row_factory=dict_row,connect_timeout=8) as conn:
            _ensure(conn)
            row=conn.execute("""INSERT INTO sb_employees(employee_code,full_name,email,department,designation,joining_date,monthly_gross)
                VALUES(%s,%s,%s,%s,%s,%s,%s) RETURNING *""",(body.employee_code.strip(),body.full_name.strip(),body.email.strip().lower() or None,body.department.strip() or None,body.designation.strip() or None,body.joining_date,body.monthly_gross)).fetchone()
            return {"employee":row}
    except psycopg.errors.UniqueViolation as exc: raise HTTPException(status_code=409,detail="Employee code already exists") from exc
    except Exception as exc: raise HTTPException(status_code=503,detail="Employee could not be saved") from exc

@router.get("/employees")
def employees(authorization:str|None=Header(default=None))->dict[str,Any]:
    _admin(authorization)
    try:
        with psycopg.connect(_db(),row_factory=dict_row,connect_timeout=8) as conn:
            _ensure(conn)
            return {"items":conn.execute("SELECT * FROM sb_employees ORDER BY full_name").fetchall()}
    except Exception as exc: raise HTTPException(status_code=503,detail="Employee records unavailable") from exc

@router.post("/payroll/runs",status_code=201)
def payroll_run(body:PayrollInput,authorization:str|None=Header(default=None))->dict[str,Any]:
    user=_admin(authorization)
    if body.period_end<body.period_start: raise HTTPException(status_code=422,detail="Period end must be on or after period start")
    if any(v<0 for v in body.deductions.values()): raise HTTPException(status_code=422,detail="Deductions cannot be negative")
    try:
        with psycopg.connect(_db(),row_factory=dict_row,connect_timeout=8) as conn:
            _ensure(conn)
            with conn.transaction():
                run=conn.execute("""INSERT INTO sb_payroll_runs(period_start,period_end,created_by) VALUES(%s,%s,%s)
                    ON CONFLICT(period_start,period_end) DO UPDATE SET period_start=EXCLUDED.period_start
                    RETURNING *""",(body.period_start,body.period_end,user["id"])).fetchone()
                if run["status"]!="draft": raise HTTPException(status_code=409,detail="Payroll run already approved or paid")
                # Rebuild draft lines from the current active employee set so employees
                # deactivated since the previous calculation are not left on the run.
                conn.execute("DELETE FROM sb_payroll_lines WHERE run_id=%s",(run["id"],))
                staff=conn.execute("SELECT id,monthly_gross FROM sb_employees WHERE status='active' ORDER BY id").fetchall()
                lines=[]
                for employee in staff:
                    gross=Decimal(str(employee["monthly_gross"]))
                    custom_deduction=body.deductions.get(employee["id"],Decimal("0"))
                    leave_row=conn.execute("""SELECT COALESCE(SUM(days *
                        (LEAST(end_date,%s)-GREATEST(start_date,%s)+1)::numeric/(end_date-start_date+1)),0) AS days
                        FROM sb_leave_requests WHERE employee_id=%s AND status='approved' AND paid=FALSE
                        AND start_date<=%s AND end_date>=%s""",
                        (body.period_end,body.period_start,employee["id"],body.period_end,body.period_start)).fetchone()
                    unpaid_days=Decimal(str(leave_row["days"] or 0))
                    attendance_row=conn.execute("""SELECT COALESCE(SUM(CASE WHEN a.status='absent' THEN 1
                        WHEN a.status='half_day' THEN 0.5 ELSE 0 END),0) AS days
                        FROM sb_attendance a WHERE a.employee_id=%s AND a.work_date BETWEEN %s AND %s
                        AND NOT EXISTS (SELECT 1 FROM sb_leave_requests l WHERE l.employee_id=a.employee_id
                            AND l.status='approved' AND a.work_date BETWEEN l.start_date AND l.end_date)""",
                        (employee["id"],body.period_start,body.period_end)).fetchone()
                    unpaid_days += Decimal(str(attendance_row["days"] or 0))
                    absence_deduction=(gross/Decimal("30")*unpaid_days).quantize(Decimal("0.01"))
                    deduction=custom_deduction+absence_deduction
                    if deduction>gross: raise HTTPException(status_code=422,detail=f"Total deductions exceed gross salary for employee {employee['id']}")
                    line=conn.execute("""INSERT INTO sb_payroll_lines(run_id,employee_id,gross,deductions,net_pay) VALUES(%s,%s,%s,%s,%s)
                        ON CONFLICT(run_id,employee_id) DO UPDATE SET gross=EXCLUDED.gross,deductions=EXCLUDED.deductions,net_pay=EXCLUDED.net_pay
                        RETURNING *""",(run["id"],employee["id"],gross,deduction,gross-deduction)).fetchone()
                    lines.append(line)
                return {"run":run,"lines":lines,"total_gross":sum((Decimal(str(x["gross"])) for x in lines),Decimal("0")),
                        "total_deductions":sum((Decimal(str(x["deductions"])) for x in lines),Decimal("0")),
                        "total_net":sum((Decimal(str(x["net_pay"])) for x in lines),Decimal("0"))}
    except HTTPException: raise
    except Exception as exc: raise HTTPException(status_code=503,detail="Payroll could not be calculated") from exc

@router.get("/payroll/runs")
def payroll_runs(authorization:str|None=Header(default=None))->dict[str,Any]:
    _admin(authorization)
    try:
        with psycopg.connect(_db(),row_factory=dict_row,connect_timeout=8) as conn:
            _ensure(conn)
            return {"items":conn.execute("SELECT * FROM sb_payroll_runs ORDER BY period_start DESC").fetchall()}
    except Exception as exc: raise HTTPException(status_code=503,detail="Payroll runs unavailable") from exc

@router.post("/payroll/runs/{run_id}/approve")
def approve_payroll(run_id:int,authorization:str|None=Header(default=None))->dict[str,Any]:
    user=_admin(authorization)
    try:
        with psycopg.connect(_db(),row_factory=dict_row,connect_timeout=8) as conn:
            _ensure(conn)
            with conn.transaction():
                run=conn.execute("SELECT * FROM sb_payroll_runs WHERE id=%s FOR UPDATE",(run_id,)).fetchone()
                if not run: raise HTTPException(status_code=404,detail="Payroll run not found")
                if run["status"]!="draft": raise HTTPException(status_code=409,detail="Payroll run is not in draft status")
                totals=conn.execute("SELECT COALESCE(SUM(gross),0) AS gross,COALESCE(SUM(deductions),0) AS deductions,COALESCE(SUM(net_pay),0) AS net FROM sb_payroll_lines WHERE run_id=%s",(run_id,)).fetchone()
                gross=Decimal(str(totals["gross"])); net=Decimal(str(totals["net"])); deductions=Decimal(str(totals["deductions"]))
                if gross<=0: raise HTTPException(status_code=422,detail="Payroll run has no salary lines")
                journal_id=_post_journal(conn,run["period_end"],f"PAYROLL-{run_id}",f"Payroll for {run['period_start']} to {run['period_end']}","payroll",run_id,
                    [("salary",gross,Decimal("0")),("payroll_deductions_payable",Decimal("0"),deductions),("accounts_payable",Decimal("0"),net)],user["id"])
                conn.execute("UPDATE sb_payroll_runs SET status='approved' WHERE id=%s",(run_id,))
                return {"run_id":run_id,"status":"approved","journal_id":journal_id,"gross":gross,"deductions":deductions,"net_pay":net}
    except HTTPException: raise
    except Exception as exc: raise HTTPException(status_code=503,detail="Payroll approval and accounting posting failed") from exc

@router.post("/payroll/runs/{run_id}/pay")
def mark_payroll_paid(run_id:int,payment_account:str=Query(default="bank",pattern="^(bank|cash)$"),authorization:str|None=Header(default=None))->dict[str,Any]:
    user=_admin(authorization)
    try:
        with psycopg.connect(_db(),row_factory=dict_row,connect_timeout=8) as conn:
            _ensure(conn)
            with conn.transaction():
                run=conn.execute("SELECT * FROM sb_payroll_runs WHERE id=%s FOR UPDATE",(run_id,)).fetchone()
                if not run: raise HTTPException(status_code=404,detail="Payroll run not found")
                if run["status"]!="approved": raise HTTPException(status_code=409,detail="Only approved payroll can be marked paid")
                totals=conn.execute("SELECT COALESCE(SUM(net_pay),0) AS net FROM sb_payroll_lines WHERE run_id=%s",(run_id,)).fetchone()
                net=Decimal(str(totals["net"]))
                if net<=0: raise HTTPException(status_code=422,detail="Payroll net pay must be greater than zero")
                journal_id=_post_journal(conn,run["period_end"],f"PAYROLL-PAY-{run_id}",f"Payroll payment for run {run_id}","payroll_payment",run_id,
                    [("accounts_payable",net,Decimal("0")),(payment_account,Decimal("0"),net)],user["id"])
                conn.execute("UPDATE sb_payroll_runs SET status='paid' WHERE id=%s",(run_id,))
                return {"run_id":run_id,"status":"paid","journal_id":journal_id,"net_pay":net,"payment_account":payment_account}
    except HTTPException: raise
    except Exception as exc: raise HTTPException(status_code=503,detail="Payroll payment posting failed") from exc

@router.post("/purchases/{purchase_id}/pay")
def pay_supplier_purchase(purchase_id:int,payment_account:str=Query(default="bank",pattern="^(bank|cash)$"),reference:str=Query(default="",max_length=120),authorization:str|None=Header(default=None))->dict[str,Any]:
    user=_admin(authorization)
    try:
        with psycopg.connect(_db(),row_factory=dict_row,connect_timeout=8) as conn:
            _ensure(conn)
            with conn.transaction():
                po=conn.execute("SELECT * FROM sb_purchase_orders WHERE id=%s FOR UPDATE",(purchase_id,)).fetchone()
                if not po: raise HTTPException(status_code=404,detail="Purchase order not found")
                if po["status"]!="received": raise HTTPException(status_code=409,detail="Only received purchase orders can be paid")
                if conn.execute("SELECT id FROM sb_supplier_payments WHERE purchase_id=%s",(purchase_id,)).fetchone():
                    raise HTTPException(status_code=409,detail="This purchase order is already marked paid")
                amount=Decimal(str(po["total"]))
                if amount<=0: raise HTTPException(status_code=422,detail="Purchase total must be greater than zero")
                journal_id=_post_journal(conn,date.today(),f"PO-PAY-{purchase_id}",f"Supplier payment for purchase order {purchase_id}","supplier_payment",purchase_id,
                    [("accounts_payable",amount,Decimal("0")),(payment_account,Decimal("0"),amount)],user["id"])
                payment=conn.execute("""INSERT INTO sb_supplier_payments(purchase_id,amount,payment_account,reference,paid_by)
                    VALUES(%s,%s,%s,%s,%s) RETURNING *""",(purchase_id,amount,payment_account,reference.strip() or None,user["id"])).fetchone()
                return {"payment":payment,"journal_id":journal_id,"message":"Supplier payment recorded and accounting updated."}
    except HTTPException: raise
    except Exception as exc: raise HTTPException(status_code=503,detail="Supplier payment could not be recorded") from exc
