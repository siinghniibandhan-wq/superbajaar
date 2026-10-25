"""Integrated configurable commerce operations for Super Bajaar.

All operational records use stable IDs and document references; schemas are created
idempotently and do not require an Odoo migration or payment gateway.
"""
import json
import secrets
from decimal import Decimal
from typing import Any

import psycopg
from fastapi import APIRouter, Header, HTTPException, Query
from pydantic import BaseModel, Field
from psycopg.rows import dict_row
from .auth import _current, _require, _db

router = APIRouter(prefix="/api", tags=["integrated-operations"])


def _schema(conn):
    statements = [
    """CREATE TABLE IF NOT EXISTS catalog_attributes(
      id BIGSERIAL PRIMARY KEY, name TEXT NOT NULL UNIQUE, values_json JSONB NOT NULL DEFAULT '[]',
      created_at TIMESTAMPTZ NOT NULL DEFAULT now())""",
    """CREATE TABLE IF NOT EXISTS product_attribute_assignments(
      product_id BIGINT NOT NULL, attribute_id BIGINT NOT NULL REFERENCES catalog_attributes(id) ON DELETE CASCADE,
      PRIMARY KEY(product_id,attribute_id))""",
    """CREATE TABLE IF NOT EXISTS variant_attribute_values(
      variant_id BIGINT NOT NULL, attribute_id BIGINT NOT NULL REFERENCES catalog_attributes(id),
      value TEXT NOT NULL, PRIMARY KEY(variant_id,attribute_id))""",
    """CREATE TABLE IF NOT EXISTS sb_warehouses(
      id BIGSERIAL PRIMARY KEY, name TEXT NOT NULL, code TEXT NOT NULL UNIQUE, address TEXT NOT NULL DEFAULT '',
      pincode TEXT NOT NULL DEFAULT '', serviceable_pincodes JSONB NOT NULL DEFAULT '[]',
      locations JSONB NOT NULL DEFAULT '[]', active BOOLEAN NOT NULL DEFAULT TRUE, created_at TIMESTAMPTZ NOT NULL DEFAULT now())""",
    """CREATE TABLE IF NOT EXISTS sb_inventory_ledger(
      id BIGSERIAL PRIMARY KEY, warehouse_id BIGINT NOT NULL REFERENCES sb_warehouses(id),
      variant_id BIGINT NOT NULL, quantity_delta INTEGER NOT NULL, movement_type TEXT NOT NULL,
      reference TEXT NOT NULL, note TEXT NOT NULL DEFAULT '', actor_id BIGINT,
      created_at TIMESTAMPTZ NOT NULL DEFAULT now())""",
    """CREATE TABLE IF NOT EXISTS sb_vendors(
      id BIGSERIAL PRIMARY KEY, name TEXT NOT NULL, email TEXT NOT NULL UNIQUE, phone TEXT NOT NULL DEFAULT '',
      status TEXT NOT NULL DEFAULT 'active', created_at TIMESTAMPTZ NOT NULL DEFAULT now())""",
    """CREATE TABLE IF NOT EXISTS sb_procurements(
      id BIGSERIAL PRIMARY KEY, reference TEXT NOT NULL UNIQUE, vendor_id BIGINT NOT NULL REFERENCES sb_vendors(id),
      status TEXT NOT NULL DEFAULT 'draft', items JSONB NOT NULL DEFAULT '[]', expected_date DATE,
      created_by BIGINT, created_at TIMESTAMPTZ NOT NULL DEFAULT now(), updated_at TIMESTAMPTZ NOT NULL DEFAULT now())""",
    """CREATE TABLE IF NOT EXISTS sb_receipts(
      id BIGSERIAL PRIMARY KEY, reference TEXT NOT NULL UNIQUE, procurement_id BIGINT NOT NULL REFERENCES sb_procurements(id),
      warehouse_id BIGINT NOT NULL REFERENCES sb_warehouses(id), status TEXT NOT NULL DEFAULT 'inspection',
      items JSONB NOT NULL DEFAULT '[]', note TEXT NOT NULL DEFAULT '', received_by BIGINT,
      created_at TIMESTAMPTZ NOT NULL DEFAULT now())""",
    """CREATE TABLE IF NOT EXISTS sb_invoices(
      id BIGSERIAL PRIMARY KEY, reference TEXT NOT NULL UNIQUE, source_channel TEXT NOT NULL,
      source_id BIGINT, customer_name TEXT NOT NULL DEFAULT '', status TEXT NOT NULL DEFAULT 'issued',
      subtotal NUMERIC(14,2) NOT NULL DEFAULT 0, tax_total NUMERIC(14,2) NOT NULL DEFAULT 0,
      total NUMERIC(14,2) NOT NULL DEFAULT 0, paid_total NUMERIC(14,2) NOT NULL DEFAULT 0,
      items JSONB NOT NULL DEFAULT '[]', created_by BIGINT, created_at TIMESTAMPTZ NOT NULL DEFAULT now())""",
    """CREATE TABLE IF NOT EXISTS sb_payments(
      id BIGSERIAL PRIMARY KEY, reference TEXT NOT NULL UNIQUE, invoice_id BIGINT NOT NULL REFERENCES sb_invoices(id),
      amount NUMERIC(14,2) NOT NULL CHECK(amount>0), method TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'posted',
      recorded_by BIGINT, created_at TIMESTAMPTZ NOT NULL DEFAULT now())""",
    """CREATE TABLE IF NOT EXISTS sb_returns(
      id BIGSERIAL PRIMARY KEY, reference TEXT NOT NULL UNIQUE, invoice_reference TEXT NOT NULL,
      status TEXT NOT NULL DEFAULT 'requested', reason TEXT NOT NULL DEFAULT '', items JSONB NOT NULL DEFAULT '[]',
      origin_warehouse_id BIGINT, created_by BIGINT, created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
      updated_at TIMESTAMPTZ NOT NULL DEFAULT now())""",
    """CREATE TABLE IF NOT EXISTS sb_accounts(
      id BIGSERIAL PRIMARY KEY, code TEXT NOT NULL UNIQUE, name TEXT NOT NULL, account_type TEXT NOT NULL,
      active BOOLEAN NOT NULL DEFAULT TRUE)""",
    """CREATE TABLE IF NOT EXISTS sb_journal_entries(
      id BIGSERIAL PRIMARY KEY, reference TEXT NOT NULL UNIQUE, source_reference TEXT NOT NULL,
      entry_date DATE NOT NULL DEFAULT CURRENT_DATE, memo TEXT NOT NULL DEFAULT '', lines JSONB NOT NULL,
      posted BOOLEAN NOT NULL DEFAULT TRUE, created_at TIMESTAMPTZ NOT NULL DEFAULT now())""",
    """CREATE TABLE IF NOT EXISTS sb_document_events(
      id BIGSERIAL PRIMARY KEY, reference TEXT NOT NULL, event_type TEXT NOT NULL,
      from_status TEXT, to_status TEXT, actor_id BIGINT, details JSONB NOT NULL DEFAULT '{}',
      created_at TIMESTAMPTZ NOT NULL DEFAULT now())"""
    ]
    for sql in statements: conn.execute(sql)
    conn.execute("CREATE INDEX IF NOT EXISTS sb_events_ref_idx ON sb_document_events(reference,created_at)")
    conn.execute("CREATE INDEX IF NOT EXISTS sb_inventory_variant_idx ON sb_inventory_ledger(variant_id,warehouse_id,created_at)")
    conn.execute("""INSERT INTO sb_accounts(code,name,account_type) VALUES
      ('1000','Cash and bank','asset'),('1100','Accounts receivable','asset'),
      ('2000','Accounts payable','liability'),('2100','GST payable','liability'),
      ('4000','Sales revenue','income'),('5000','Cost of goods sold','expense')
      ON CONFLICT(code) DO NOTHING""")


def _ref(prefix):
    return prefix + "-" + secrets.token_hex(5).upper()


def _event(conn, ref, kind, actor, old=None, new=None, details=None):
    conn.execute("""INSERT INTO sb_document_events(reference,event_type,from_status,to_status,actor_id,details)
      VALUES(%s,%s,%s,%s,%s,%s::jsonb)""",
      (ref,kind,old,new,actor,json.dumps(details or {})))


class AttributeInput(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    values: list[str] = Field(min_length=1, max_length=100)

class AssignAttributesInput(BaseModel):
    attribute_ids: list[int] = Field(max_length=100)

class VariantValuesInput(BaseModel):
    values: dict[int, str]

class WarehouseInput(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    code: str = Field(min_length=1, max_length=40)
    address: str = ""
    pincode: str = ""
    serviceable_pincodes: list[str] = []
    locations: list[str] = []

class VendorInput(BaseModel):
    name: str = Field(min_length=1, max_length=160)
    email: str
    phone: str = ""

class ProcurementInput(BaseModel):
    vendor_id: int
    items: list[dict[str, Any]] = Field(min_length=1)
    expected_date: str | None = None

class QuoteResponseInput(BaseModel):
    status: str
    items: list[dict[str, Any]] | None = None

class ReceiptInput(BaseModel):
    warehouse_id: int
    items: list[dict[str, Any]] = Field(min_length=1)
    note: str = ""

class ReceiptInspectionInput(BaseModel):
    accepted_items: list[dict[str, Any]] = Field(min_length=1)
    rejected_items: list[dict[str, Any]] = []
    note: str = ""

class InvoiceInput(BaseModel):
    source_channel: str = "pos"
    customer_name: str = ""
    items: list[dict[str, Any]] = Field(min_length=1)
    tax_total: Decimal = Decimal("0")

class PaymentInput(BaseModel):
    amount: Decimal = Field(gt=0)
    method: str = "cash"

class ReturnInput(BaseModel):
    invoice_reference: str
    reason: str = ""
    items: list[dict[str, Any]] = Field(min_length=1)

class ReturnStatusInput(BaseModel):
    status: str
    origin_warehouse_id: int | None = None


@router.get("/admin/catalogue/attributes")
def list_attributes(authorization: str | None = Header(default=None)):
    _require(authorization, {"super_admin","admin","staff"})
    with psycopg.connect(_db(), row_factory=dict_row) as c:
        _schema(c)
        return {"items": c.execute("SELECT * FROM catalog_attributes ORDER BY name").fetchall()}


@router.post("/admin/catalogue/attributes", status_code=201)
def create_attribute(body: AttributeInput, authorization: str | None = Header(default=None)):
    actor = _require(authorization, {"super_admin","admin"})
    values = list(dict.fromkeys(v.strip() for v in body.values if v.strip()))
    if not values: raise HTTPException(422, "At least one non-empty attribute value is required.")
    with psycopg.connect(_db(), row_factory=dict_row) as c:
        _schema(c)
        try:
            row = c.execute("INSERT INTO catalog_attributes(name,values_json) VALUES(%s,%s::jsonb) RETURNING *",
              (body.name.strip(),json.dumps(values))).fetchone()
        except psycopg.errors.UniqueViolation:
            raise HTTPException(409, "An attribute with this name already exists.")
        return row


@router.put("/admin/catalogue/products/{product_id}/attributes")
def assign_attributes(product_id: int, body: AssignAttributesInput, authorization: str | None = Header(default=None)):
    _require(authorization, {"super_admin","admin"})
    with psycopg.connect(_db(), row_factory=dict_row) as c:
        _schema(c)
        c.execute("DELETE FROM product_attribute_assignments WHERE product_id=%s",(product_id,))
        for aid in set(body.attribute_ids):
            if not c.execute("SELECT id FROM catalog_attributes WHERE id=%s",(aid,)).fetchone():
                raise HTTPException(404, f"Attribute {aid} not found.")
            c.execute("INSERT INTO product_attribute_assignments(product_id,attribute_id) VALUES(%s,%s)",(product_id,aid))
        return {"product_id":product_id,"attributes":c.execute("""SELECT a.id,a.name,a.values_json
          FROM catalog_attributes a JOIN product_attribute_assignments p ON p.attribute_id=a.id
          WHERE p.product_id=%s ORDER BY a.name""",(product_id,)).fetchall()}


@router.get("/products/{product_id}/configuration")
def product_configuration(product_id: int):
    with psycopg.connect(_db(), row_factory=dict_row) as c:
        _schema(c)
        product = c.execute("SELECT id,name FROM products WHERE id=%s",(product_id,)).fetchone()
        if not product: raise HTTPException(404,"Product not found.")
        attrs = c.execute("""SELECT a.id,a.name,a.values_json FROM catalog_attributes a
          JOIN product_attribute_assignments p ON p.attribute_id=a.id WHERE p.product_id=%s ORDER BY a.name""",(product_id,)).fetchall()
        variants = c.execute("""SELECT v.id AS variant_id,v.sku,v.selling_price,
          COALESCE((SELECT jsonb_object_agg(a.name,x.value) FROM variant_attribute_values x
            JOIN catalog_attributes a ON a.id=x.attribute_id WHERE x.variant_id=v.id),'{}'::jsonb) AS attributes
          FROM product_variants v WHERE v.product_id=%s ORDER BY v.id""",(product_id,)).fetchall()
        return {"product":product,"attributes":attrs,"variants":variants}


@router.put("/admin/catalogue/variants/{variant_id}/attributes")
def set_variant_values(variant_id: int, body: VariantValuesInput, authorization: str | None = Header(default=None)):
    _require(authorization, {"super_admin","admin"})
    with psycopg.connect(_db(), row_factory=dict_row) as c:
        _schema(c)
        v=c.execute("SELECT id,product_id FROM product_variants WHERE id=%s",(variant_id,)).fetchone()
        if not v: raise HTTPException(404,"Variant not found.")
        assigned={r["id"]:r for r in c.execute("""SELECT a.id,a.name,a.values_json FROM catalog_attributes a
          JOIN product_attribute_assignments p ON p.attribute_id=a.id WHERE p.product_id=%s""",(v["product_id"],)).fetchall()}
        if set(body.values)-set(assigned): raise HTTPException(422,"Variant includes an attribute not assigned to this product.")
        for aid,val in body.values.items():
            if val not in assigned[aid]["values_json"]: raise HTTPException(422,f"Invalid value for {assigned[aid]['name']}.")
        c.execute("DELETE FROM variant_attribute_values WHERE variant_id=%s",(variant_id,))
        for aid,val in body.values.items():
            c.execute("INSERT INTO variant_attribute_values(variant_id,attribute_id,value) VALUES(%s,%s,%s)",(variant_id,aid,val))
        return {"variant_id":variant_id,"attributes":body.values}


@router.get("/admin/warehouses")
def list_warehouses(authorization: str | None = Header(default=None)):
    _require(authorization, {"super_admin","admin","staff"})
    with psycopg.connect(_db(), row_factory=dict_row) as c:
        _schema(c)
        rows=c.execute("""SELECT w.*,
          COALESCE((SELECT jsonb_agg(jsonb_build_object('variant_id',variant_id,'quantity',qty))
          FROM (SELECT variant_id,SUM(quantity_delta)::int qty FROM sb_inventory_ledger
            WHERE warehouse_id=w.id GROUP BY variant_id) s), '[]'::jsonb) stock
          FROM sb_warehouses w ORDER BY w.name""").fetchall()
        return {"items":rows}


@router.post("/admin/warehouses", status_code=201)
def create_warehouse(body: WarehouseInput, authorization: str | None = Header(default=None)):
    _require(authorization, {"super_admin","admin"})
    if body.pincode and len(body.pincode)!=6: raise HTTPException(422,"Warehouse PIN must contain six digits.")
    if any(len(p)!=6 or not p.isdigit() for p in body.serviceable_pincodes): raise HTTPException(422,"Serviceable PINs must contain six digits.")
    with psycopg.connect(_db(), row_factory=dict_row) as c:
        _schema(c)
        return c.execute("""INSERT INTO sb_warehouses(name,code,address,pincode,serviceable_pincodes,locations)
          VALUES(%s,%s,%s,%s,%s::jsonb,%s::jsonb) RETURNING *""",
          (body.name.strip(),body.code.strip().upper(),body.address,body.pincode,json.dumps(list(dict.fromkeys(body.serviceable_pincodes))),json.dumps(list(dict.fromkeys(body.locations))))).fetchone()


@router.get("/admin/warehouses/allocate")
def allocate_warehouse(pincode: str = Query(pattern=r"^[0-9]{6}$"), variant_id: int | None = None, quantity: int = Query(default=1,ge=1)):
    with psycopg.connect(_db(), row_factory=dict_row) as c:
        _schema(c)
        rows=c.execute("""SELECT w.id,w.name,w.code,w.pincode,w.serviceable_pincodes,
          COALESCE((SELECT SUM(quantity_delta) FROM sb_inventory_ledger l WHERE l.warehouse_id=w.id AND (%s IS NULL OR l.variant_id=%s)),0) stock
          FROM sb_warehouses w WHERE w.active AND (w.pincode=%s OR w.serviceable_pincodes ? %s)
          ORDER BY CASE WHEN w.pincode=%s THEN 0 ELSE 1 END,w.id""",(variant_id,variant_id,pincode,pincode,pincode)).fetchall()
        eligible=[r for r in rows if variant_id is None or r["stock"]>=quantity]
        if not eligible: raise HTTPException(404,"No active warehouse can service this PIN with the requested stock.")
        return {"warehouse":eligible[0]}


@router.post("/admin/vendors", status_code=201)
def create_vendor(body: VendorInput, authorization: str | None = Header(default=None)):
    _require(authorization, {"super_admin","admin","staff"})
    with psycopg.connect(_db(), row_factory=dict_row) as c:
        _schema(c)
        return c.execute("INSERT INTO sb_vendors(name,email,phone) VALUES(%s,%s,%s) RETURNING id,name,email,phone,status,created_at",
          (body.name.strip(),body.email.lower().strip(),body.phone.strip())).fetchone()


@router.get("/vendor/dashboard")
def vendor_dashboard(authorization: str | None = Header(default=None)):
    user=_current(authorization)
    with psycopg.connect(_db(), row_factory=dict_row) as c:
        _schema(c)
        vendor=c.execute("SELECT * FROM sb_vendors WHERE lower(email)=lower(%s) AND status='active'",(user["email"],)).fetchone()
        if not vendor: raise HTTPException(403,"This account is not linked to an active supplier.")
        quotes=c.execute("SELECT * FROM sb_procurements WHERE vendor_id=%s ORDER BY created_at DESC LIMIT 200",(vendor["id"],)).fetchall()
        receipts=c.execute("""SELECT r.* FROM sb_receipts r JOIN sb_procurements p ON p.id=r.procurement_id
          WHERE p.vendor_id=%s ORDER BY r.created_at DESC LIMIT 200""",(vendor["id"],)).fetchall()
        return {"vendor":{"id":vendor["id"],"name":vendor["name"]},"procurements":quotes,"receipts":receipts}


@router.post("/admin/procurements", status_code=201)
def create_procurement(body: ProcurementInput, authorization: str | None = Header(default=None)):
    actor=_require(authorization, {"super_admin","admin","staff"})
    if any(not isinstance(x,dict) or int(x.get("quantity",0))<1 or not x.get("variant_id") for x in body.items):
        raise HTTPException(422,"Each purchase line needs a valid variant_id and positive quantity.")
    ref=_ref("RFQ")
    with psycopg.connect(_db(), row_factory=dict_row) as c:
        _schema(c)
        if not c.execute("SELECT id FROM sb_vendors WHERE id=%s AND status='active'",(body.vendor_id,)).fetchone(): raise HTTPException(404,"Active vendor not found.")
        row=c.execute("""INSERT INTO sb_procurements(reference,vendor_id,status,items,expected_date,created_by)
          VALUES(%s,%s,'quotation_requested',%s::jsonb,%s,%s) RETURNING *""",(ref,body.vendor_id,json.dumps(body.items),body.expected_date,actor["id"])).fetchone()
        _event(c,ref,"quotation_requested",actor["id"],new="quotation_requested",details={"vendor_id":body.vendor_id})
        return row


@router.patch("/vendor/procurements/{procurement_id}")
def vendor_quote_response(procurement_id: int, body: QuoteResponseInput, authorization: str | None = Header(default=None)):
    user=_current(authorization)
    if body.status not in {"accepted","rejected","quoted"}: raise HTTPException(422,"Status must be accepted, rejected or quoted.")
    with psycopg.connect(_db(), row_factory=dict_row) as c:
        _schema(c)
        p=c.execute("""SELECT p.* FROM sb_procurements p JOIN sb_vendors v ON v.id=p.vendor_id
          WHERE p.id=%s AND lower(v.email)=lower(%s) AND v.status='active' FOR UPDATE""",(procurement_id,user["email"])).fetchone()
        if not p: raise HTTPException(404,"Supplier quotation not found.")
        if p["status"] not in {"quotation_requested","quoted"}: raise HTTPException(409,"This quotation is no longer editable.")
        c.execute("UPDATE sb_procurements SET status=%s,items=COALESCE(%s::jsonb,items),updated_at=now() WHERE id=%s",
          (body.status,json.dumps(body.items) if body.items is not None else None,procurement_id))
        _event(c,p["reference"],"vendor_response",user["id"],p["status"],body.status)
        return {"id":procurement_id,"reference":p["reference"],"status":body.status}


@router.post("/admin/procurements/{procurement_id}/purchase-order")
def convert_to_po(procurement_id: int, authorization: str | None = Header(default=None)):
    actor=_require(authorization, {"super_admin","admin"})
    with psycopg.connect(_db(), row_factory=dict_row) as c:
        _schema(c)
        p=c.execute("SELECT * FROM sb_procurements WHERE id=%s FOR UPDATE",(procurement_id,)).fetchone()
        if not p: raise HTTPException(404,"Procurement record not found.")
        if p["status"] not in {"accepted","quoted"}: raise HTTPException(409,"Vendor must accept or quote before PO conversion.")
        ref=_ref("PO")
        c.execute("UPDATE sb_procurements SET reference=%s,status='purchase_order',updated_at=now() WHERE id=%s",(ref,procurement_id))
        _event(c,ref,"purchase_order_created",actor["id"],p["status"],"purchase_order",{"quotation_reference":p["reference"]})
        return {"id":procurement_id,"reference":ref,"status":"purchase_order","vendor_id":p["vendor_id"],"items":p["items"]}


@router.post("/admin/procurements/{procurement_id}/receipts", status_code=201)
def create_receipt(procurement_id: int, body: ReceiptInput, authorization: str | None = Header(default=None)):
    actor=_require(authorization, {"super_admin","admin","staff"})
    ref=_ref("GRN")
    with psycopg.connect(_db(), row_factory=dict_row) as c:
        _schema(c)
        p=c.execute("SELECT * FROM sb_procurements WHERE id=%s FOR UPDATE",(procurement_id,)).fetchone()
        if not p or p["status"] not in {"purchase_order","partially_received"}: raise HTTPException(409,"Only an open purchase order can receive goods.")
        if not c.execute("SELECT id FROM sb_warehouses WHERE id=%s AND active",(body.warehouse_id,)).fetchone(): raise HTTPException(404,"Active warehouse not found.")
        expected={int(i["variant_id"]):int(i["quantity"]) for i in p["items"]}
        already=c.execute("SELECT COALESCE(jsonb_agg(items),'[]'::jsonb) x FROM sb_receipts WHERE procurement_id=%s AND status='accepted'",(procurement_id,)).fetchone()["x"]
        received={}
        for receipt in already:
            for line in receipt:
                received[int(line["variant_id"])]=received.get(int(line["variant_id"]),0)+int(line.get("accepted_quantity",line.get("quantity",0)))
        for line in body.items:
            vid=int(line.get("variant_id",0)); qty=int(line.get("quantity",0))
            if vid not in expected or qty<1 or qty+received.get(vid,0)>expected[vid]: raise HTTPException(422,"Receipt quantities must not exceed outstanding PO quantities.")
        row=c.execute("""INSERT INTO sb_receipts(reference,procurement_id,warehouse_id,status,items,note,received_by)
          VALUES(%s,%s,%s,'inspection',%s::jsonb,%s,%s) RETURNING *""",(ref,procurement_id,body.warehouse_id,json.dumps(body.items),body.note,actor["id"])).fetchone()
        _event(c,ref,"goods_received_for_inspection",actor["id"],new="inspection",details={"po_reference":p["reference"]})
        return row


@router.post("/admin/receipts/{receipt_id}/inspect")
def inspect_receipt(receipt_id: int, body: ReceiptInspectionInput, authorization: str | None = Header(default=None)):
    actor=_require(authorization, {"super_admin","admin","staff"})
    with psycopg.connect(_db(), row_factory=dict_row) as c:
        _schema(c)
        r=c.execute("SELECT * FROM sb_receipts WHERE id=%s FOR UPDATE",(receipt_id,)).fetchone()
        if not r or r["status"]!="inspection": raise HTTPException(409,"Receipt is not awaiting inspection.")
        received={int(x["variant_id"]):int(x["quantity"]) for x in r["items"]}
        accepted={int(x["variant_id"]):int(x["quantity"]) for x in body.accepted_items}
        rejected={int(x["variant_id"]):int(x["quantity"]) for x in body.rejected_items}
        for vid in set(accepted)|set(rejected):
            if accepted.get(vid,0)<0 or rejected.get(vid,0)<0 or accepted.get(vid,0)+rejected.get(vid,0)!=received.get(vid,0):
                raise HTTPException(422,"Accepted plus rejected quantity must equal the received quantity for each variant.")
        for vid,qty in accepted.items():
            if qty:
                c.execute("""INSERT INTO sb_inventory_ledger(warehouse_id,variant_id,quantity_delta,movement_type,reference,note,actor_id)
                  VALUES(%s,%s,%s,'goods_receipt',%s,%s,%s)""",(r["warehouse_id"],vid,qty,r["reference"],body.note,actor["id"]))
        final=[{"variant_id":vid,"quantity":received[vid],"accepted_quantity":accepted.get(vid,0),"rejected_quantity":rejected.get(vid,0)} for vid in received]
        c.execute("UPDATE sb_receipts SET status='accepted',items=%s::jsonb,note=%s WHERE id=%s",(json.dumps(final),body.note,receipt_id))
        remaining=c.execute("""SELECT p.items FROM sb_procurements p WHERE p.id=%s""",(r["procurement_id"],)).fetchone()["items"]
        all_received=c.execute("""SELECT COALESCE(SUM((x->>'accepted_quantity')::int),0) n FROM sb_receipts r,
          LATERAL jsonb_array_elements(r.items) x WHERE r.procurement_id=%s AND r.status='accepted'""",(r["procurement_id"],)).fetchone()["n"]
        # Status reflects actual accepted quantities against all ordered quantities.
        expected=sum(int(x["quantity"]) for x in remaining)
        total=c.execute("""SELECT COALESCE(SUM((x->>'accepted_quantity')::int),0) n FROM sb_receipts r,
          LATERAL jsonb_array_elements(r.items) x WHERE r.procurement_id=%s AND r.status='accepted'""",(r["procurement_id"],)).fetchone()["n"]
        status="received" if total>=expected else "partially_received"
        c.execute("UPDATE sb_procurements SET status=%s,updated_at=now() WHERE id=%s",(status,r["procurement_id"]))
        _event(c,r["reference"],"quality_inspection_completed",actor["id"],"inspection","accepted",{"accepted":accepted,"rejected":rejected})
        return {"receipt_reference":r["reference"],"status":"accepted","accepted":sum(accepted.values()),"rejected":sum(rejected.values()),"purchase_status":status}


@router.get("/admin/invoices")
def list_invoices(authorization: str | None = Header(default=None)):
    _require(authorization, {"super_admin","admin","staff"})
    with psycopg.connect(_db(), row_factory=dict_row) as c:
        _schema(c)
        return {"items":c.execute("SELECT * FROM sb_invoices ORDER BY created_at DESC LIMIT 500").fetchall()}


@router.post("/admin/invoices", status_code=201)
def create_invoice(body: InvoiceInput, authorization: str | None = Header(default=None)):
    actor=_require(authorization, {"super_admin","admin","staff"})
    if body.source_channel not in {"pos","website"}: raise HTTPException(422,"Channel must be website or pos.")
    subtotal=Decimal("0")
    for item in body.items:
        qty=Decimal(str(item.get("quantity",0))); price=Decimal(str(item.get("unit_price",0)))
        if qty<=0 or price<0: raise HTTPException(422,"Invoice quantities must be positive and prices non-negative.")
        subtotal+=(qty*price)
    tax=body.tax_total
    if tax<0: raise HTTPException(422,"Tax cannot be negative.")
    total=(subtotal+tax).quantize(Decimal("0.01")); ref=_ref("INV")
    with psycopg.connect(_db(), row_factory=dict_row) as c:
        _schema(c)
        row=c.execute("""INSERT INTO sb_invoices(reference,source_channel,customer_name,status,subtotal,tax_total,total,items,created_by)
          VALUES(%s,%s,%s,'issued',%s,%s,%s,%s::jsonb,%s) RETURNING *""",
          (ref,body.source_channel,body.customer_name,subtotal,tax,total,json.dumps(body.items),actor["id"])).fetchone()
        _event(c,ref,"invoice_issued",actor["id"],new="issued",details={"channel":body.source_channel})
        # One balanced sales posting per invoice; subsequent payments do not repost revenue.
        lines=[{"account_code":"1100","debit":str(total),"credit":"0"},{"account_code":"4000","debit":"0","credit":str(subtotal)}]
        if tax: lines.append({"account_code":"2100","debit":"0","credit":str(tax)})
        c.execute("INSERT INTO sb_journal_entries(reference,source_reference,memo,lines) VALUES(%s,%s,%s,%s::jsonb)",
          (_ref("JE"),ref,"Invoice revenue and tax",json.dumps(lines)))
        return row


@router.post("/admin/invoices/{invoice_id}/payments", status_code=201)
def record_payment(invoice_id: int, body: PaymentInput, authorization: str | None = Header(default=None)):
    actor=_require(authorization, {"super_admin","admin","staff"})
    if body.method not in {"cash","card","upi","bank_transfer","other"}: raise HTTPException(422,"Unsupported payment method.")
    with psycopg.connect(_db(), row_factory=dict_row) as c:
        _schema(c)
        inv=c.execute("SELECT * FROM sb_invoices WHERE id=%s FOR UPDATE",(invoice_id,)).fetchone()
        if not inv or inv["status"] in {"cancelled","paid"}: raise HTTPException(409,"Invoice not found or already closed.")
        paid=Decimal(str(inv["paid_total"]))+body.amount
        if paid>Decimal(str(inv["total"])): raise HTTPException(422,"Payment exceeds the outstanding invoice amount.")
        ref=_ref("PAY")
        c.execute("INSERT INTO sb_payments(reference,invoice_id,amount,method,recorded_by) VALUES(%s,%s,%s,%s,%s)",(ref,invoice_id,body.amount,body.method,actor["id"]))
        status="paid" if paid==Decimal(str(inv["total"])) else "partially_paid"
        c.execute("UPDATE sb_invoices SET paid_total=%s,status=%s WHERE id=%s",(paid,status,invoice_id))
        c.execute("INSERT INTO sb_journal_entries(reference,source_reference,memo,lines) VALUES(%s,%s,%s,%s::jsonb)",
          (_ref("JE"),inv["reference"],"Invoice payment",json.dumps([{"account_code":"1000","debit":str(body.amount),"credit":"0"},{"account_code":"1100","debit":"0","credit":str(body.amount)}])))
        _event(c,inv["reference"],"payment_recorded",actor["id"],inv["status"],status,{"payment_reference":ref,"amount":str(body.amount)})
        return {"payment_reference":ref,"invoice_reference":inv["reference"],"paid_total":str(paid),"status":status}


@router.post("/admin/returns", status_code=201)
def create_return(body: ReturnInput, authorization: str | None = Header(default=None)):
    actor=_require(authorization, {"super_admin","admin","staff"})
    ref=_ref("RET")
    with psycopg.connect(_db(), row_factory=dict_row) as c:
        _schema(c)
        if not c.execute("SELECT id FROM sb_invoices WHERE reference=%s",(body.invoice_reference,)).fetchone():
            # Website checkout invoices also share this reference namespace.
            if not c.execute("SELECT id FROM store_orders WHERE invoice_number=%s",(body.invoice_reference,)).fetchone():
                raise HTTPException(404,"Invoice reference not found.")
        row=c.execute("""INSERT INTO sb_returns(reference,invoice_reference,status,reason,items,created_by)
          VALUES(%s,%s,'requested',%s,%s::jsonb,%s) RETURNING *""",(ref,body.invoice_reference,body.reason,json.dumps(body.items),actor["id"])).fetchone()
        _event(c,ref,"return_requested",actor["id"],new="requested",details={"invoice_reference":body.invoice_reference})
        return row


@router.patch("/admin/returns/{return_id}")
def update_return(return_id: int, body: ReturnStatusInput, authorization: str | None = Header(default=None)):
    actor=_require(authorization, {"super_admin","admin","staff"})
    allowed={"requested","pickup_scheduled","picked_up","in_transit","received_at_origin","inspected","refunded","cancelled"}
    if body.status not in allowed: raise HTTPException(422,"Invalid reverse-logistics status.")
    with psycopg.connect(_db(), row_factory=dict_row) as c:
        _schema(c)
        r=c.execute("SELECT * FROM sb_returns WHERE id=%s FOR UPDATE",(return_id,)).fetchone()
        if not r: raise HTTPException(404,"Return not found.")
        transitions={"requested":{"pickup_scheduled","cancelled"},"pickup_scheduled":{"picked_up","cancelled"},
          "picked_up":{"in_transit"},"in_transit":{"received_at_origin"},"received_at_origin":{"inspected"},
          "inspected":{"refunded"},"refunded":set(),"cancelled":set()}
        if body.status not in transitions.get(r["status"],set()): raise HTTPException(409,f"Cannot move return from {r['status']} to {body.status}.")
        c.execute("UPDATE sb_returns SET status=%s,origin_warehouse_id=COALESCE(%s,origin_warehouse_id),updated_at=now() WHERE id=%s",(body.status,body.origin_warehouse_id,return_id))
        if body.status=="received_at_origin" and body.origin_warehouse_id:
            if not c.execute("SELECT id FROM sb_warehouses WHERE id=%s",(body.origin_warehouse_id,)).fetchone(): raise HTTPException(404,"Origin warehouse not found.")
        _event(c,r["reference"],"reverse_logistics_status",actor["id"],r["status"],body.status,{"invoice_reference":r["invoice_reference"]})
        return {"reference":r["reference"],"invoice_reference":r["invoice_reference"],"status":body.status}


@router.get("/admin/accounting/overview")
def accounting_overview(authorization: str | None = Header(default=None)):
    _require(authorization, {"super_admin","admin","staff"})
    with psycopg.connect(_db(), row_factory=dict_row) as c:
        _schema(c)
        return {
          "sales_invoices":c.execute("SELECT COUNT(*)::int count,COALESCE(SUM(total),0) total,COALESCE(SUM(paid_total),0) paid FROM sb_invoices WHERE status NOT IN ('cancelled','draft')").fetchone(),
          "receivables":c.execute("SELECT COALESCE(SUM(total-paid_total),0) amount FROM sb_invoices WHERE status IN ('issued','partially_paid','overdue')").fetchone()["amount"],
          "payables":0,
          "cash_collected":c.execute("SELECT COALESCE(SUM(amount),0) amount FROM sb_payments WHERE status='posted'").fetchone()["amount"],
          "journal_entries":c.execute("SELECT COUNT(*)::int count FROM sb_journal_entries WHERE posted").fetchone()["count"],
          "accounts":c.execute("SELECT * FROM sb_accounts WHERE active ORDER BY code").fetchall()
        }


@router.get("/admin/documents/{reference}/timeline")
def document_timeline(reference: str, authorization: str | None = Header(default=None)):
    _require(authorization, {"super_admin","admin","staff"})
    with psycopg.connect(_db(), row_factory=dict_row) as c:
        _schema(c)
        events=c.execute("SELECT * FROM sb_document_events WHERE reference=%s ORDER BY created_at,id",(reference,)).fetchall()
        events += c.execute("SELECT * FROM document_events WHERE reference=%s ORDER BY created_at,id",(reference,)).fetchall() if c.execute("SELECT to_regclass('document_events') x").fetchone()["x"] else []
        return {"reference":reference,"events":events}


class StockMovementInput(BaseModel):
    warehouse_id: int
    variant_id: int
    quantity_delta: int
    movement_type: str = "adjustment"
    reference: str = ""
    note: str = ""

@router.get("/admin/vendors")
def list_vendors(authorization: str | None = Header(default=None)):
    _require(authorization, {"super_admin","admin","staff"})
    with psycopg.connect(_db(), row_factory=dict_row) as c:
        _schema(c)
        return {"items":c.execute("SELECT id,name,email,phone,status,created_at FROM sb_vendors ORDER BY name").fetchall()}

@router.get("/admin/procurements")
def list_procurements(authorization: str | None = Header(default=None)):
    _require(authorization, {"super_admin","admin","staff"})
    with psycopg.connect(_db(), row_factory=dict_row) as c:
        _schema(c)
        return {"items":c.execute("""SELECT p.*,v.name vendor_name,v.email vendor_email FROM sb_procurements p
          JOIN sb_vendors v ON v.id=p.vendor_id ORDER BY p.created_at DESC LIMIT 500""").fetchall()}

@router.get("/admin/receipts")
def list_receipts(authorization: str | None = Header(default=None)):
    _require(authorization, {"super_admin","admin","staff"})
    with psycopg.connect(_db(), row_factory=dict_row) as c:
        _schema(c)
        return {"items":c.execute("""SELECT r.*,p.reference purchase_reference,w.name warehouse_name
          FROM sb_receipts r JOIN sb_procurements p ON p.id=r.procurement_id
          JOIN sb_warehouses w ON w.id=r.warehouse_id ORDER BY r.created_at DESC LIMIT 500""").fetchall()}

@router.get("/admin/returns")
def list_returns(authorization: str | None = Header(default=None)):
    _require(authorization, {"super_admin","admin","staff"})
    with psycopg.connect(_db(), row_factory=dict_row) as c:
        _schema(c)
        return {"items":c.execute("SELECT * FROM sb_returns ORDER BY created_at DESC LIMIT 500").fetchall()}

@router.get("/admin/accounting/journals")
def list_journals(authorization: str | None = Header(default=None)):
    _require(authorization, {"super_admin","admin","staff"})
    with psycopg.connect(_db(), row_factory=dict_row) as c:
        _schema(c)
        return {"items":c.execute("SELECT * FROM sb_journal_entries ORDER BY created_at DESC LIMIT 500").fetchall()}

@router.post("/admin/inventory/movements", status_code=201)
def record_stock_movement(body: StockMovementInput, authorization: str | None = Header(default=None)):
    actor=_require(authorization, {"super_admin","admin"})
    if body.quantity_delta == 0: raise HTTPException(422,"Stock movement cannot be zero.")
    if body.movement_type not in {"opening_balance","adjustment","sale","return","transfer_in","transfer_out","goods_receipt"}:
        raise HTTPException(422,"Unsupported stock movement type.")
    ref=body.reference.strip() or _ref("STK")
    with psycopg.connect(_db(), row_factory=dict_row) as c:
        _schema(c)
        if not c.execute("SELECT id FROM sb_warehouses WHERE id=%s AND active",(body.warehouse_id,)).fetchone():
            raise HTTPException(404,"Active warehouse not found.")
        if not c.execute("SELECT id FROM product_variants WHERE id=%s",(body.variant_id,)).fetchone():
            raise HTTPException(404,"Product variant not found.")
        balance=c.execute("SELECT COALESCE(SUM(quantity_delta),0) qty FROM sb_inventory_ledger WHERE warehouse_id=%s AND variant_id=%s",
          (body.warehouse_id,body.variant_id)).fetchone()["qty"]
        if balance+body.quantity_delta<0: raise HTTPException(409,"Movement would make available stock negative.")
        row=c.execute("""INSERT INTO sb_inventory_ledger(warehouse_id,variant_id,quantity_delta,movement_type,reference,note,actor_id)
          VALUES(%s,%s,%s,%s,%s,%s,%s) RETURNING *""",
          (body.warehouse_id,body.variant_id,body.quantity_delta,body.movement_type,ref,body.note,actor["id"])).fetchone()
        _event(c,ref,"stock_movement",actor["id"],details={"warehouse_id":body.warehouse_id,"variant_id":body.variant_id,"quantity_delta":body.quantity_delta})
        return {"movement":row,"balance":balance+body.quantity_delta}
