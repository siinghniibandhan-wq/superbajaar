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

from .auth import _require, _db

router = APIRouter(prefix="/api/operations", tags=["operations"])

def _admin(authorization: str | None) -> dict[str, Any]:
    return _require(authorization, {"super_admin", "admin"})

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
    conn.execute("""CREATE TABLE IF NOT EXISTS sb_employees (
        id BIGSERIAL PRIMARY KEY, employee_code TEXT NOT NULL UNIQUE, full_name TEXT NOT NULL, email TEXT,
        department TEXT, designation TEXT, joining_date DATE, status TEXT NOT NULL DEFAULT 'active'
        CHECK(status IN ('active','inactive')), monthly_gross NUMERIC(14,2) NOT NULL DEFAULT 0 CHECK(monthly_gross>=0),
        created_at TIMESTAMPTZ NOT NULL DEFAULT now())""")
    conn.execute("""CREATE TABLE IF NOT EXISTS sb_payroll_runs (
        id BIGSERIAL PRIMARY KEY, period_start DATE NOT NULL, period_end DATE NOT NULL,
        status TEXT NOT NULL DEFAULT 'draft' CHECK(status IN ('draft','approved','paid')),
        created_by BIGINT, created_at TIMESTAMPTZ NOT NULL DEFAULT now(), UNIQUE(period_start,period_end))""")
    conn.execute("""CREATE TABLE IF NOT EXISTS sb_payroll_lines (
        id BIGSERIAL PRIMARY KEY, run_id BIGINT NOT NULL REFERENCES sb_payroll_runs(id) ON DELETE CASCADE,
        employee_id BIGINT NOT NULL REFERENCES sb_employees(id), gross NUMERIC(14,2) NOT NULL,
        deductions NUMERIC(14,2) NOT NULL DEFAULT 0, net_pay NUMERIC(14,2) NOT NULL,
        UNIQUE(run_id,employee_id))""")

class PartyInput(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    phone: str = Field(default="", max_length=40)
    email: str = Field(default="", max_length=254)
    gstin: str = Field(default="", max_length=15)

class VendorInput(PartyInput):
    address: dict[str, Any] = Field(default_factory=dict)
    payment_terms_days: int = Field(default=0, ge=0, le=365)

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
    estimated_delivery: date | None = None
    note: str = Field(default="", max_length=1000)

class ShipmentUpdate(BaseModel):
    status: str = Field(pattern="^(created|packed|in_transit|out_for_delivery|delivered|exception|cancelled)$")
    note: str = Field(default="", max_length=1000)

class EmployeeInput(BaseModel):
    employee_code: str = Field(min_length=1, max_length=60)
    full_name: str = Field(min_length=1, max_length=200)
    email: str = Field(default="", max_length=254)
    department: str = Field(default="", max_length=100)
    designation: str = Field(default="", max_length=100)
    joining_date: date | None = None
    monthly_gross: Decimal = Field(default=Decimal("0"), ge=0)

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
                current=conn.execute("SELECT quantity FROM sb_stock WHERE variant_id=%s AND warehouse=%s FOR UPDATE",(body.variant_id,body.warehouse)).fetchone()
                old=Decimal(str(current["quantity"])) if current else Decimal("0")
                delta=body.quantity if body.movement_type in {"opening","adjustment_in","return_in","transfer_in"} else -body.quantity
                if old+delta<0: raise HTTPException(status_code=422,detail="Insufficient stock for this movement")
                conn.execute("""INSERT INTO sb_stock(variant_id,warehouse,quantity) VALUES(%s,%s,%s)
                    ON CONFLICT(variant_id,warehouse) DO UPDATE SET quantity=EXCLUDED.quantity,updated_at=now()""",(body.variant_id,body.warehouse,old+delta))
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

@router.post("/purchases/{purchase_id}/receive")
def receive_purchase(purchase_id:int,authorization:str|None=Header(default=None))->dict[str,Any]:
    user=_admin(authorization)
    try:
        with psycopg.connect(_db(),row_factory=dict_row,connect_timeout=8) as conn:
            _ensure(conn)
            with conn.transaction():
                po=conn.execute("SELECT * FROM sb_purchase_orders WHERE id=%s FOR UPDATE",(purchase_id,)).fetchone()
                if not po: raise HTTPException(status_code=404,detail="Purchase order not found")
                if po["status"] in ("received","cancelled"): raise HTTPException(status_code=409,detail="Purchase order is already closed")
                lines=conn.execute("SELECT * FROM sb_purchase_lines WHERE purchase_id=%s",(purchase_id,)).fetchall()
                for line in lines:
                    remaining=Decimal(str(line["quantity"]))-Decimal(str(line["received_qty"]))
                    if remaining<=0: continue
                    conn.execute("""INSERT INTO sb_stock(variant_id,warehouse,quantity) VALUES(%s,'Main',%s)
                        ON CONFLICT(variant_id,warehouse) DO UPDATE SET quantity=sb_stock.quantity+EXCLUDED.quantity,updated_at=now()""",(line["variant_id"],remaining))
                    conn.execute("""INSERT INTO sb_stock_movements(variant_id,warehouse,movement_type,quantity,reference_type,reference_id,created_by)
                        VALUES(%s,'Main','purchase_receipt',%s,'purchase',%s,%s)""",(line["variant_id"],remaining,purchase_id,user["id"]))
                    conn.execute("UPDATE sb_purchase_lines SET received_qty=quantity WHERE id=%s",(line["id"],))
                conn.execute("UPDATE sb_purchase_orders SET status='received' WHERE id=%s",(purchase_id,))
                return {"purchase_id":purchase_id,"status":"received","message":"Received quantities posted to inventory."}
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
                subtotal=Decimal("0"); tax_total=Decimal("0"); resolved=[]
                for line in body.lines:
                    stock=conn.execute("SELECT quantity FROM sb_stock WHERE variant_id=%s AND warehouse='Main' FOR UPDATE",(line.variant_id,)).fetchone()
                    available=Decimal(str(stock["quantity"])) if stock else Decimal("0")
                    if available<line.quantity: raise HTTPException(status_code=422,detail=f"Insufficient stock for variant {line.variant_id}; available {available}")
                    product=conn.execute("""SELECT selling_price FROM product_variants WHERE id=%s""",(line.variant_id,)).fetchone()
                    if not product: raise HTTPException(status_code=404,detail=f"Product variant {line.variant_id} not found")
                    price=Decimal(str(product["selling_price"])) if line.unit_price is None else line.unit_price
                    base=price*line.quantity; tax=(base*line.tax_rate/Decimal("100")).quantize(Decimal("0.01"))
                    subtotal+=base; tax_total+=tax; resolved.append((line,price,base+tax))
                total=subtotal+tax_total
                receipt="POS-"+__import__("secrets").token_hex(6).upper()
                sale=conn.execute("""INSERT INTO sb_pos_sales(receipt_number,customer_id,subtotal,tax_total,total,payment_method,created_by)
                    VALUES(%s,%s,%s,%s,%s,%s,%s) RETURNING *""",(receipt,body.customer_id,subtotal,tax_total,total,body.payment_method,user["id"])).fetchone()
                for line,price,line_total in resolved:
                    conn.execute("""INSERT INTO sb_pos_sale_lines(sale_id,variant_id,quantity,unit_price,tax_rate,line_total)
                        VALUES(%s,%s,%s,%s,%s,%s)""",(sale["id"],line.variant_id,line.quantity,price,line.tax_rate,line_total))
                    conn.execute("UPDATE sb_stock SET quantity=quantity-%s,updated_at=now() WHERE variant_id=%s AND warehouse='Main'",(line.quantity,line.variant_id))
                    conn.execute("""INSERT INTO sb_stock_movements(variant_id,warehouse,movement_type,quantity,reference_type,reference_id,created_by)
                        VALUES(%s,'Main','pos_sale',%s,'pos',%s,%s)""",(line.variant_id,line.quantity,sale["id"],user["id"]))
                return {"sale":sale,"receipt_number":receipt,"message":"POS sale saved and inventory deducted atomically."}
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

@router.post("/shipments",status_code=201)
def create_shipment(body:ShipmentInput,authorization:str|None=Header(default=None))->dict[str,Any]:
    _admin(authorization)
    try:
        with psycopg.connect(_db(),row_factory=dict_row,connect_timeout=8) as conn:
            _ensure(conn)
            row=conn.execute("""INSERT INTO sb_shipments(order_type,order_id,carrier,tracking_number,estimated_delivery,note)
                VALUES(%s,%s,%s,%s,%s,%s) RETURNING *""",(body.order_type,body.order_id,body.carrier.strip() or None,body.tracking_number.strip() or None,body.estimated_delivery,body.note.strip() or None)).fetchone()
            return {"shipment":row}
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
    _admin(authorization)
    try:
        with psycopg.connect(_db(),row_factory=dict_row,connect_timeout=8) as conn:
            _ensure(conn)
            row=conn.execute("""UPDATE sb_shipments SET status=%s,note=COALESCE(NULLIF(%s,''),note),
                delivered_at=CASE WHEN %s='delivered' THEN now() ELSE delivered_at END WHERE id=%s RETURNING *""",
                (body.status,body.note,body.status,shipment_id)).fetchone()
            if not row: raise HTTPException(status_code=404,detail="Shipment not found")
            return {"shipment":row}
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
                staff=conn.execute("SELECT id,monthly_gross FROM sb_employees WHERE status='active' ORDER BY id").fetchall()
                lines=[]
                for employee in staff:
                    gross=Decimal(str(employee["monthly_gross"]))
                    deduction=body.deductions.get(employee["id"],Decimal("0"))
                    if deduction>gross: raise HTTPException(status_code=422,detail=f"Deductions exceed gross salary for employee {employee['id']}")
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
