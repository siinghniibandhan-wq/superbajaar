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
    """CREATE TABLE IF NOT EXISTS catalog_product_tax(
      product_id BIGINT PRIMARY KEY, hsn_code TEXT NOT NULL, updated_by BIGINT,
      updated_at TIMESTAMPTZ NOT NULL DEFAULT now())""",
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
      reference TEXT NOT NULL, location TEXT NOT NULL DEFAULT '', note TEXT NOT NULL DEFAULT '', actor_id BIGINT,
      created_at TIMESTAMPTZ NOT NULL DEFAULT now())""",
    """CREATE TABLE IF NOT EXISTS sb_vendors(
      id BIGSERIAL PRIMARY KEY, name TEXT NOT NULL, email TEXT NOT NULL UNIQUE, phone TEXT NOT NULL DEFAULT '',
      status TEXT NOT NULL DEFAULT 'active', created_at TIMESTAMPTZ NOT NULL DEFAULT now())""",
    """CREATE TABLE IF NOT EXISTS sb_procurements(
      id BIGSERIAL PRIMARY KEY, reference TEXT NOT NULL UNIQUE, purchase_order_reference TEXT UNIQUE, vendor_id BIGINT NOT NULL REFERENCES sb_vendors(id),
      status TEXT NOT NULL DEFAULT 'draft', items JSONB NOT NULL DEFAULT '[]', expected_date DATE,
      created_by BIGINT, created_at TIMESTAMPTZ NOT NULL DEFAULT now(), updated_at TIMESTAMPTZ NOT NULL DEFAULT now())""",
    """CREATE TABLE IF NOT EXISTS sb_vendor_dispatches(
      id BIGSERIAL PRIMARY KEY, reference TEXT NOT NULL UNIQUE, procurement_id BIGINT NOT NULL REFERENCES sb_procurements(id),
      vendor_id BIGINT NOT NULL REFERENCES sb_vendors(id), items JSONB NOT NULL, carrier TEXT NOT NULL DEFAULT '',
      tracking_reference TEXT NOT NULL DEFAULT '', status TEXT NOT NULL DEFAULT 'dispatched',
      created_at TIMESTAMPTZ NOT NULL DEFAULT now())""",
    """CREATE TABLE IF NOT EXISTS sb_receipts(
      id BIGSERIAL PRIMARY KEY, reference TEXT NOT NULL UNIQUE, procurement_id BIGINT NOT NULL REFERENCES sb_procurements(id),
      warehouse_id BIGINT NOT NULL REFERENCES sb_warehouses(id), status TEXT NOT NULL DEFAULT 'inspection',
      items JSONB NOT NULL DEFAULT '[]', note TEXT NOT NULL DEFAULT '', received_by BIGINT,
      created_at TIMESTAMPTZ NOT NULL DEFAULT now())""",
    """CREATE TABLE IF NOT EXISTS sb_invoices(
      id BIGSERIAL PRIMARY KEY, reference TEXT NOT NULL UNIQUE, source_channel TEXT NOT NULL,
      source_id BIGINT, customer_name TEXT NOT NULL DEFAULT '', status TEXT NOT NULL DEFAULT 'issued',
      subtotal NUMERIC(14,2) NOT NULL DEFAULT 0, discount_total NUMERIC(14,2) NOT NULL DEFAULT 0, tax_total NUMERIC(14,2) NOT NULL DEFAULT 0,
      total NUMERIC(14,2) NOT NULL DEFAULT 0, paid_total NUMERIC(14,2) NOT NULL DEFAULT 0,
      items JSONB NOT NULL DEFAULT '[]', created_by BIGINT, created_at TIMESTAMPTZ NOT NULL DEFAULT now())""",
    """CREATE TABLE IF NOT EXISTS sb_supplier_bills(
      id BIGSERIAL PRIMARY KEY, reference TEXT NOT NULL UNIQUE, vendor_id BIGINT NOT NULL REFERENCES sb_vendors(id),
      procurement_id BIGINT REFERENCES sb_procurements(id), vendor_invoice_number TEXT NOT NULL,
      amount NUMERIC(14,2) NOT NULL CHECK(amount>=0), tax_total NUMERIC(14,2) NOT NULL DEFAULT 0,
      paid_total NUMERIC(14,2) NOT NULL DEFAULT 0, due_date DATE, status TEXT NOT NULL DEFAULT 'submitted',
      created_at TIMESTAMPTZ NOT NULL DEFAULT now(), UNIQUE(vendor_id,vendor_invoice_number))""",
    """CREATE TABLE IF NOT EXISTS sb_payments(
      id BIGSERIAL PRIMARY KEY, reference TEXT NOT NULL UNIQUE, invoice_id BIGINT NOT NULL REFERENCES sb_invoices(id),
      amount NUMERIC(14,2) NOT NULL CHECK(amount>0), method TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'posted',
      recorded_by BIGINT, created_at TIMESTAMPTZ NOT NULL DEFAULT now())""",
    """CREATE TABLE IF NOT EXISTS sb_returns(
      id BIGSERIAL PRIMARY KEY, reference TEXT NOT NULL UNIQUE, invoice_reference TEXT NOT NULL,
      status TEXT NOT NULL DEFAULT 'requested', reason TEXT NOT NULL DEFAULT '', items JSONB NOT NULL DEFAULT '[]',
      origin_warehouse_id BIGINT, refund_amount NUMERIC(14,2) NOT NULL DEFAULT 0,
      created_by BIGINT, created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
      updated_at TIMESTAMPTZ NOT NULL DEFAULT now())""",
    """CREATE TABLE IF NOT EXISTS sb_credit_notes(
      id BIGSERIAL PRIMARY KEY, reference TEXT NOT NULL UNIQUE, invoice_reference TEXT NOT NULL,
      return_reference TEXT NOT NULL UNIQUE, amount NUMERIC(14,2) NOT NULL CHECK(amount>=0),
      status TEXT NOT NULL DEFAULT 'posted', created_by BIGINT, created_at TIMESTAMPTZ NOT NULL DEFAULT now())""",
    """CREATE TABLE IF NOT EXISTS sb_tax_config(
      id SMALLINT PRIMARY KEY CHECK(id=1), seller_gstin TEXT NOT NULL DEFAULT '',
      seller_state_code TEXT NOT NULL DEFAULT '', rates_json JSONB NOT NULL DEFAULT '{}',
      updated_by BIGINT, updated_at TIMESTAMPTZ NOT NULL DEFAULT now())""",
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
      created_at TIMESTAMPTZ NOT NULL DEFAULT now())""",
    """CREATE TABLE IF NOT EXISTS sb_document_registry(
      reference TEXT PRIMARY KEY, document_type TEXT NOT NULL, document_id BIGINT NOT NULL,
      created_at TIMESTAMPTZ NOT NULL DEFAULT now())"""
    ]
    for sql in statements: conn.execute(sql)
    conn.execute("ALTER TABLE catalog_attributes ADD COLUMN IF NOT EXISTS display_type TEXT NOT NULL DEFAULT 'text' CHECK (display_type IN ('text','color','image','dropdown','button'))")
    conn.execute("ALTER TABLE sb_inventory_ledger ADD COLUMN IF NOT EXISTS location TEXT NOT NULL DEFAULT ''")
    conn.execute("ALTER TABLE sb_procurements ADD COLUMN IF NOT EXISTS purchase_order_reference TEXT")
    conn.execute("ALTER TABLE sb_returns ADD COLUMN IF NOT EXISTS refund_amount NUMERIC(14,2) NOT NULL DEFAULT 0")
    conn.execute("ALTER TABLE sb_invoices ADD COLUMN IF NOT EXISTS discount_total NUMERIC(14,2) NOT NULL DEFAULT 0")
    conn.execute("CREATE UNIQUE INDEX IF NOT EXISTS sb_procurements_po_ref_uidx ON sb_procurements(purchase_order_reference) WHERE purchase_order_reference IS NOT NULL")
    conn.execute("CREATE INDEX IF NOT EXISTS sb_events_ref_idx ON sb_document_events(reference,created_at)")
    conn.execute("CREATE INDEX IF NOT EXISTS sb_inventory_variant_idx ON sb_inventory_ledger(variant_id,warehouse_id,created_at)")
    conn.execute("""INSERT INTO sb_accounts(code,name,account_type) VALUES
      ('1000','Cash and bank','asset'),('1100','Accounts receivable','asset'),('1200','GST input credit','asset'),
      ('2000','Accounts payable','liability'),('2100','GST payable','liability'),
      ('2110','CGST payable','liability'),('2120','SGST payable','liability'),('2130','IGST payable','liability'),('3000','Retained earnings','equity'),('4000','Sales revenue','income'),('5000','Cost of goods sold','expense')
      ON CONFLICT(code) DO NOTHING""")


def _ref(prefix):
    return prefix + "-" + secrets.token_hex(5).upper()


def _register_document(conn, reference, document_type, document_id):
    conn.execute("INSERT INTO sb_document_registry(reference,document_type,document_id) VALUES(%s,%s,%s)",
      (reference,document_type,document_id))


def _event(conn, ref, kind, actor, old=None, new=None, details=None):
    conn.execute("""INSERT INTO sb_document_events(reference,event_type,from_status,to_status,actor_id,details)
      VALUES(%s,%s,%s,%s,%s,%s::jsonb)""",
      (ref,kind,old,new,actor,json.dumps(details or {})))


class ProductTaxInput(BaseModel):
    hsn_code: str = Field(min_length=1, max_length=20)

class AttributeInput(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    values: list[str] = Field(min_length=1, max_length=100)
    display_type: str = Field(default="text", pattern="^(text|color|image|dropdown|button)$")

class AssignAttributesInput(BaseModel):
    attribute_ids: list[int] = Field(max_length=100)

class VariantValuesInput(BaseModel):
    values: dict[int, str]

class GenerateVariantsInput(BaseModel):
    combinations: list[dict[str, str]] = Field(min_length=1, max_length=500)
    sku_prefix: str = Field(min_length=1, max_length=50)
    selling_price: Decimal = Field(gt=0)
    mrp: Decimal | None = None

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

class VendorDispatchInput(BaseModel):
    items: list[dict[str, Any]] = Field(min_length=1)
    carrier: str = ""
    tracking_reference: str = ""

class ReceiptInspectionInput(BaseModel):
    accepted_items: list[dict[str, Any]] = Field(min_length=1)
    rejected_items: list[dict[str, Any]] = []
    note: str = ""

class InvoiceInput(BaseModel):
    source_channel: str = "pos"
    customer_name: str = ""
    items: list[dict[str, Any]] = Field(min_length=1)
    tax_total: Decimal = Decimal("0")
    place_of_supply_state_code: str | None = None
    discount_total: Decimal = Decimal("0")
    warehouse_id: int | None = None

class GSTSettingsInput(BaseModel):
    seller_gstin: str = ""
    seller_state_code: str = Field(pattern=r"^[0-9]{2}$")
    rates: dict[str, Decimal] = {}

class AccountInput(BaseModel):
    code: str = Field(min_length=1, max_length=30)
    name: str = Field(min_length=1, max_length=120)
    account_type: str

class SupplierBillInput(BaseModel):
    vendor_invoice_number: str = Field(min_length=1, max_length=100)
    amount: Decimal = Field(ge=0)
    tax_total: Decimal = Field(default=Decimal("0"), ge=0)
    due_date: str | None = None

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
    location: str = ""
    accepted_items: list[dict[str, Any]] = []


@router.put("/admin/catalogue/products/{product_id}/tax")
def set_product_tax(product_id: int, body: ProductTaxInput, authorization: str | None = Header(default=None)):
    actor=_require(authorization, {"super_admin","admin"})
    with psycopg.connect(_db(), row_factory=dict_row) as c:
        _schema(c)
        if not c.execute("SELECT id FROM products WHERE id=%s",(product_id,)).fetchone():
            raise HTTPException(404,"Product not found.")
        return c.execute("""INSERT INTO catalog_product_tax(product_id,hsn_code,updated_by,updated_at)
          VALUES(%s,%s,%s,now()) ON CONFLICT(product_id) DO UPDATE SET
          hsn_code=EXCLUDED.hsn_code,updated_by=EXCLUDED.updated_by,updated_at=now() RETURNING *""",
          (product_id,body.hsn_code.strip(),actor["id"])).fetchone()


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
            row = c.execute("INSERT INTO catalog_attributes(name,values_json,display_type) VALUES(%s,%s::jsonb,%s) RETURNING *",
              (body.name.strip(),json.dumps(values),body.display_type)).fetchone()
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


@router.post("/admin/catalogue/products/{product_id}/generate-variants", status_code=201)
def generate_variants(product_id: int, body: GenerateVariantsInput, authorization: str | None = Header(default=None)):
    actor=_require(authorization, {"super_admin","admin"})
    if body.mrp is not None and body.mrp < body.selling_price:
        raise HTTPException(422,"MRP cannot be lower than the selling price.")
    with psycopg.connect(_db(), row_factory=dict_row) as c:
        _schema(c)
        if not c.execute("SELECT id FROM products WHERE id=%s",(product_id,)).fetchone():
            raise HTTPException(404,"Parent product not found.")
        assigned={str(r["id"]):r for r in c.execute("""SELECT a.id,a.name,a.values_json FROM catalog_attributes a
          JOIN product_attribute_assignments p ON p.attribute_id=a.id WHERE p.product_id=%s""",(product_id,)).fetchall()}
        if not assigned: raise HTTPException(422,"Assign product-specific attributes before generating variants.")
        columns={r["column_name"] for r in c.execute("SELECT column_name FROM information_schema.columns WHERE table_schema=current_schema() AND table_name='product_variants'").fetchall()}
        required={"product_id","selling_price","sku"}
        if not required.issubset(columns): raise HTTPException(503,"The current variant schema cannot create variants safely.")
        canonical=[tuple(sorted(combo.items())) for combo in body.combinations]
        if len(set(canonical)) != len(canonical):
            raise HTTPException(422,"Duplicate variant combinations are not allowed.")
        made=[]
        for index,combo in enumerate(body.combinations,1):
            if set(combo)!=set(assigned):
                raise HTTPException(422,"Every combination must specify exactly the attributes assigned to this product.")
            for aid,value in combo.items():
                if value not in assigned[aid]["values_json"]:
                    raise HTTPException(422,f"Invalid value for attribute {assigned[aid]['name']}.")
            sku=(body.sku_prefix.strip().upper()+"-"+str(index).zfill(3))
            if "sku" in columns and c.execute("SELECT id FROM product_variants WHERE sku=%s",(sku,)).fetchone():
                raise HTTPException(409,f"SKU {sku} already exists; choose another prefix.")
            names=["product_id","selling_price"]; vals=[product_id,body.selling_price]
            if "sku" in columns: names.append("sku"); vals.append(sku)
            if "mrp" in columns and body.mrp is not None: names.append("mrp"); vals.append(body.mrp)
            if "currency" in columns: names.append("currency"); vals.append("INR")
            if "status" in columns: names.append("status"); vals.append("active")
            placeholders=",".join(["%s"]*len(names))
            variant=c.execute(f"INSERT INTO product_variants({','.join(names)}) VALUES({placeholders}) RETURNING id",vals).fetchone()
            for aid,value in combo.items():
                c.execute("INSERT INTO variant_attribute_values(variant_id,attribute_id,value) VALUES(%s,%s,%s)",(variant["id"],int(aid),value))
            made.append({"variant_id":variant["id"],"sku":sku,"attributes":combo})
        _event(c,"PRODUCT-"+str(product_id),"variants_generated",actor["id"],details={"variant_ids":[x["variant_id"] for x in made]})
        return {"product_id":product_id,"created":len(made),"variants":made}


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
        dispatches=c.execute("SELECT * FROM sb_vendor_dispatches WHERE vendor_id=%s ORDER BY created_at DESC LIMIT 200",(vendor["id"],)).fetchall()
        bills=c.execute("SELECT * FROM sb_supplier_bills WHERE vendor_id=%s ORDER BY created_at DESC LIMIT 200",(vendor["id"],)).fetchall()
        return {"vendor":{"id":vendor["id"],"name":vendor["name"]},"procurements":quotes,"receipts":receipts,"dispatches":dispatches,"bills":bills}


@router.post("/admin/procurements", status_code=201)
def create_procurement(body: ProcurementInput, authorization: str | None = Header(default=None)):
    actor=_require(authorization, {"super_admin","admin","staff"})
    if any(not isinstance(x,dict) or int(x.get("quantity",0))<1 or not x.get("variant_id") for x in body.items):
        raise HTTPException(422,"Each purchase line needs a valid variant_id and positive quantity.")
    ref=_ref("RFQ")
    with psycopg.connect(_db(), row_factory=dict_row) as c:
        _schema(c)
        if not c.execute("SELECT id FROM sb_vendors WHERE id=%s AND status='active'",(body.vendor_id,)).fetchone(): raise HTTPException(404,"Active vendor not found.")
        for item in body.items:
            if not c.execute("SELECT id FROM product_variants WHERE id=%s",(int(item["variant_id"]),)).fetchone():
                raise HTTPException(404,f"Purchase variant {item['variant_id']} not found.")
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
        if body.status=="quoted":
            if not body.items: raise HTTPException(422,"Submit quoted line items with unit_price.")
            original={int(x["variant_id"]):int(x["quantity"]) for x in p["items"]}
            quoted={}
            for line in body.items:
                if "unit_price" not in line or Decimal(str(line["unit_price"]))<0:
                    raise HTTPException(422,"Every quoted line needs a non-negative unit_price.")
                vid=int(line.get("variant_id",0)); qty=int(line.get("quantity",0))
                if vid not in original or qty!=original[vid]: raise HTTPException(422,"Quoted variants and quantities must match the requested quotation.")
                quoted[vid]=qty
            if quoted!=original: raise HTTPException(422,"The quote must include every requested variant.")
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
        c.execute("UPDATE sb_procurements SET purchase_order_reference=%s,status='purchase_order',updated_at=now() WHERE id=%s",(ref,procurement_id))
        _event(c,p["reference"],"purchase_order_created",actor["id"],p["status"],"purchase_order",{"quotation_reference":p["reference"],"purchase_order_reference":ref})
        return {"id":procurement_id,"reference":p["reference"],"purchase_order_reference":ref,"status":"purchase_order","vendor_id":p["vendor_id"],"items":p["items"]}


@router.post("/vendor/procurements/{procurement_id}/bills", status_code=201)
def vendor_submit_bill(procurement_id: int, body: SupplierBillInput, authorization: str | None = Header(default=None)):
    user=_current(authorization)
    with psycopg.connect(_db(), row_factory=dict_row) as c:
        _schema(c)
        p=c.execute("""SELECT p.*,v.id vendor_id FROM sb_procurements p JOIN sb_vendors v ON v.id=p.vendor_id
          WHERE p.id=%s AND lower(v.email)=lower(%s) AND v.status='active'""",(procurement_id,user["email"])).fetchone()
        if not p: raise HTTPException(404,"Purchase order not found for this supplier.")
        if p["status"] not in {"purchase_order","partially_received","received"}: raise HTTPException(409,"Bills can only be submitted against an issued purchase order.")
        if body.amount<0 or body.tax_total<0: raise HTTPException(422,"Bill amounts cannot be negative.")
        ref=_ref("BILL")
        row=c.execute("""INSERT INTO sb_supplier_bills(reference,vendor_id,procurement_id,vendor_invoice_number,amount,tax_total,due_date)
          VALUES(%s,%s,%s,%s,%s,%s,%s) RETURNING *""",(ref,p["vendor_id"],procurement_id,body.vendor_invoice_number,body.amount,body.tax_total,body.due_date)).fetchone()
        _event(c,p["reference"],"supplier_bill_submitted",user["id"],new="submitted",details={"bill_reference":ref})
        return row


@router.get("/admin/supplier-bills")
def list_supplier_bills(authorization: str | None = Header(default=None)):
    _require(authorization, {"super_admin","admin","staff"})
    with psycopg.connect(_db(), row_factory=dict_row) as c:
        _schema(c)
        return {"items":c.execute("""SELECT b.*,v.name vendor_name,p.reference quotation_reference,p.purchase_order_reference
          FROM sb_supplier_bills b JOIN sb_vendors v ON v.id=b.vendor_id
          LEFT JOIN sb_procurements p ON p.id=b.procurement_id ORDER BY b.created_at DESC LIMIT 500""").fetchall()}


@router.patch("/admin/supplier-bills/{bill_id}")
def update_supplier_bill(bill_id: int, status: str = Query(pattern="^(approved|rejected)$"), authorization: str | None = Header(default=None)):
    actor=_require(authorization, {"super_admin","admin"})
    with psycopg.connect(_db(), row_factory=dict_row) as c:
        _schema(c)
        b=c.execute("SELECT * FROM sb_supplier_bills WHERE id=%s FOR UPDATE",(bill_id,)).fetchone()
        if not b or b["status"]!="submitted": raise HTTPException(409,"Only a submitted bill can be approved or rejected.")
        c.execute("UPDATE sb_supplier_bills SET status=%s WHERE id=%s",(status,bill_id))
        if status=="approved":
            total=Decimal(str(b["amount"]))+Decimal(str(b["tax_total"]))
            lines=[{"account_code":"5000","debit":str(b["amount"]),"credit":"0"},{"account_code":"2000","debit":"0","credit":str(total)}]
            if b["tax_total"]: lines.append({"account_code":"1200","debit":str(b["tax_total"]),"credit":"0"})
            c.execute("INSERT INTO sb_journal_entries(reference,source_reference,memo,lines) VALUES(%s,%s,%s,%s::jsonb)",
              (_ref("JE"),b["reference"],"Approved supplier bill",json.dumps(lines)))
        _event(c,b["reference"],"supplier_bill_reviewed",actor["id"],b["status"],status)
        return {"reference":b["reference"],"status":status}


@router.post("/admin/supplier-bills/{bill_id}/payments", status_code=201)
def pay_supplier_bill(bill_id: int, body: PaymentInput, authorization: str | None = Header(default=None)):
    actor=_require(authorization, {"super_admin","admin"})
    with psycopg.connect(_db(), row_factory=dict_row) as c:
        _schema(c)
        b=c.execute("SELECT * FROM sb_supplier_bills WHERE id=%s FOR UPDATE",(bill_id,)).fetchone()
        if not b or b["status"] not in {"approved","partially_paid"}: raise HTTPException(409,"Supplier bill is not payable.")
        total=Decimal(str(b["amount"]))+Decimal(str(b["tax_total"])); paid=Decimal(str(b["paid_total"]))+body.amount
        if paid>total: raise HTTPException(422,"Payment exceeds the supplier bill balance.")
        status="paid" if paid==total else "partially_paid"
        ref=_ref("BPAY")
        c.execute("UPDATE sb_supplier_bills SET paid_total=%s,status=%s WHERE id=%s",(paid,status,bill_id))
        c.execute("INSERT INTO sb_journal_entries(reference,source_reference,memo,lines) VALUES(%s,%s,%s,%s::jsonb)",
          (_ref("JE"),b["reference"],"Supplier bill payment",json.dumps([{"account_code":"2000","debit":str(body.amount),"credit":"0"},{"account_code":"1000","debit":"0","credit":str(body.amount)}])))
        _event(c,b["reference"],"supplier_bill_payment",actor["id"],b["status"],status,{"payment_reference":ref,"amount":str(body.amount)})
        return {"payment_reference":ref,"bill_reference":b["reference"],"status":status,"paid_total":str(paid)}


@router.post("/vendor/procurements/{procurement_id}/dispatches", status_code=201)
def vendor_dispatch(procurement_id: int, body: VendorDispatchInput, authorization: str | None = Header(default=None)):
    user=_current(authorization)
    if not body.items: raise HTTPException(422,"Dispatch at least one purchase order line.")
    with psycopg.connect(_db(), row_factory=dict_row) as c:
        _schema(c)
        p=c.execute("""SELECT p.*,v.id AS verified_vendor_id FROM sb_procurements p JOIN sb_vendors v ON v.id=p.vendor_id
          WHERE p.id=%s AND lower(v.email)=lower(%s) AND v.status='active' FOR UPDATE""",(procurement_id,user["email"])).fetchone()
        if not p: raise HTTPException(404,"Purchase order not found for this supplier.")
        if p["status"] not in {"purchase_order","partially_received"}: raise HTTPException(409,"Only an open purchase order can be dispatched.")
        expected={int(x["variant_id"]):int(x["quantity"]) for x in p["items"]}
        dispatched={}
        for prev in c.execute("SELECT items FROM sb_vendor_dispatches WHERE procurement_id=%s AND status<>'cancelled'",(procurement_id,)).fetchall():
            for line in prev["items"]:
                vid=int(line["variant_id"]); dispatched[vid]=dispatched.get(vid,0)+int(line["quantity"])
        incoming={}
        for line in body.items:
            vid=int(line.get("variant_id",0)); qty=int(line.get("quantity",0))
            if vid not in expected or qty<1: raise HTTPException(422,"Dispatch lines must match PO variants and positive quantities.")
            incoming[vid]=incoming.get(vid,0)+qty
        for vid,qty in incoming.items():
            if dispatched.get(vid,0)+qty>expected[vid]: raise HTTPException(422,"Dispatch quantity exceeds the outstanding PO quantity.")
        ref=_ref("DSP")
        row=c.execute("""INSERT INTO sb_vendor_dispatches(reference,procurement_id,vendor_id,items,carrier,tracking_reference)
          VALUES(%s,%s,%s,%s::jsonb,%s,%s) RETURNING *""",(ref,procurement_id,p["vendor_id"],json.dumps(body.items),body.carrier,body.tracking_reference)).fetchone()
        _event(c,p["reference"],"vendor_dispatched",user["id"],p["status"],"purchase_order",{"dispatch_reference":ref,"items":body.items})
        return row


@router.get("/admin/dispatches")
def list_dispatches(authorization: str | None = Header(default=None)):
    _require(authorization, {"super_admin","admin","staff"})
    with psycopg.connect(_db(), row_factory=dict_row) as c:
        _schema(c)
        return {"items":c.execute("""SELECT d.*,v.name vendor_name,p.reference quotation_reference,p.purchase_order_reference
          FROM sb_vendor_dispatches d JOIN sb_vendors v ON v.id=d.vendor_id
          JOIN sb_procurements p ON p.id=d.procurement_id ORDER BY d.created_at DESC LIMIT 500""").fetchall()}


@router.post("/admin/procurements/{procurement_id}/receipts", status_code=201)
def create_receipt(procurement_id: int, body: ReceiptInput, authorization: str | None = Header(default=None)):
    actor=_require(authorization, {"super_admin","admin","staff"})
    ref=_ref("GRN")
    with psycopg.connect(_db(), row_factory=dict_row) as c:
        _schema(c)
        p=c.execute("SELECT * FROM sb_procurements WHERE id=%s FOR UPDATE",(procurement_id,)).fetchone()
        if not p or p["status"] not in {"purchase_order","partially_received"}: raise HTTPException(409,"Only an open purchase order can receive goods.")
        warehouse=c.execute("SELECT id,locations FROM sb_warehouses WHERE id=%s AND active",(body.warehouse_id,)).fetchone()
        if not warehouse: raise HTTPException(404,"Active warehouse not found.")
        allowed_locations=warehouse["locations"] if isinstance(warehouse["locations"],list) else []
        pending=c.execute("SELECT id FROM sb_receipts WHERE procurement_id=%s AND status='inspection' LIMIT 1",(procurement_id,)).fetchone()
        if pending: raise HTTPException(409,"Finish quality inspection for the pending GRN before recording another receipt.")
        expected={int(i["variant_id"]):int(i["quantity"]) for i in p["items"]}
        already=c.execute("SELECT COALESCE(jsonb_agg(items),'[]'::jsonb) x FROM sb_receipts WHERE procurement_id=%s AND status='accepted'",(procurement_id,)).fetchone()["x"]
        received={}
        for receipt in already:
            for line in receipt:
                received[int(line["variant_id"])]=received.get(int(line["variant_id"]),0)+int(line.get("accepted_quantity",line.get("quantity",0)))
        incoming={}
        for line in body.items:
            vid=int(line.get("variant_id",0)); qty=int(line.get("quantity",0))
            if vid not in expected or qty<1: raise HTTPException(422,"Receipt lines must match PO variants and have positive quantities.")
            if vid in incoming: raise HTTPException(422,"Use one line per variant per GRN; create separate GRNs for separate bins.")
            location=str(line.get("location","")).strip()
            if allowed_locations and location not in allowed_locations: raise HTTPException(422,"Choose a configured warehouse bin/location for every receipt line.")
            incoming[vid]=qty
        dispatched={}
        dispatch_rows=c.execute("SELECT items FROM sb_vendor_dispatches WHERE procurement_id=%s AND status<>'cancelled'",(procurement_id,)).fetchall()
        for dispatch in dispatch_rows:
            for line in dispatch["items"]:
                vid=int(line["variant_id"]); dispatched[vid]=dispatched.get(vid,0)+int(line["quantity"])
        for vid,qty in incoming.items():
            if qty+received.get(vid,0)>expected[vid]: raise HTTPException(422,"Receipt quantities must not exceed outstanding PO quantities.")
            if qty+received.get(vid,0)>dispatched.get(vid,0): raise HTTPException(409,"Goods receipt cannot exceed quantities dispatched by the vendor.")
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
        if (set(accepted)|set(rejected)) != set(received):
            raise HTTPException(422,"Inspection must account for every received variant as accepted or rejected.")
        for vid in set(accepted)|set(rejected):
            if accepted.get(vid,0)<0 or rejected.get(vid,0)<0 or accepted.get(vid,0)+rejected.get(vid,0)!=received.get(vid,0):
                raise HTTPException(422,"Accepted plus rejected quantity must equal the received quantity for each variant.")
        for vid,qty in accepted.items():
            if qty:
                line=next(x for x in r["items"] if int(x["variant_id"])==vid)
                c.execute("""INSERT INTO sb_inventory_ledger(warehouse_id,variant_id,quantity_delta,movement_type,reference,location,note,actor_id)
                  VALUES(%s,%s,%s,'goods_receipt',%s,%s,%s,%s)""",(r["warehouse_id"],vid,qty,r["reference"],line.get("location",""),body.note,actor["id"]))
        final=[{"variant_id":vid,"quantity":received[vid],"accepted_quantity":accepted.get(vid,0),"rejected_quantity":rejected.get(vid,0),"location":next((x.get("location","") for x in r["items"] if int(x["variant_id"])==vid),"")} for vid in received]
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


@router.get("/admin/accounting/accounts")
def list_accounts(authorization: str | None = Header(default=None)):
    _require(authorization, {"super_admin","admin","staff"})
    with psycopg.connect(_db(), row_factory=dict_row) as c:
        _schema(c)
        return {"items":c.execute("SELECT * FROM sb_accounts ORDER BY code").fetchall()}

@router.post("/admin/accounting/accounts", status_code=201)
def create_account(body: AccountInput, authorization: str | None = Header(default=None)):
    _require(authorization, {"super_admin","admin"})
    if body.account_type not in {"asset","liability","equity","income","expense"}:
        raise HTTPException(422,"Account type must be asset, liability, equity, income or expense.")
    with psycopg.connect(_db(), row_factory=dict_row) as c:
        _schema(c)
        return c.execute("INSERT INTO sb_accounts(code,name,account_type) VALUES(%s,%s,%s) RETURNING *",
          (body.code.strip(),body.name.strip(),body.account_type)).fetchone()


@router.get("/admin/accounting/gst-settings")
def get_gst_settings(authorization: str | None = Header(default=None)):
    _require(authorization, {"super_admin","admin","staff"})
    with psycopg.connect(_db(), row_factory=dict_row) as c:
        _schema(c)
        row=c.execute("SELECT seller_gstin,seller_state_code,rates_json,updated_at FROM sb_tax_config WHERE id=1").fetchone()
        return {"configured":bool(row),"settings":row}

@router.put("/admin/accounting/gst-settings")
def update_gst_settings(body: GSTSettingsInput, authorization: str | None = Header(default=None)):
    actor=_require(authorization, {"super_admin","admin"})
    if any(rate<0 or rate>Decimal("100") for rate in body.rates.values()):
        raise HTTPException(422,"GST rates must be between 0 and 100 percent.")
    with psycopg.connect(_db(), row_factory=dict_row) as c:
        _schema(c)
        row=c.execute("""INSERT INTO sb_tax_config(id,seller_gstin,seller_state_code,rates_json,updated_by,updated_at)
          VALUES(1,%s,%s,%s::jsonb,%s,now()) ON CONFLICT(id) DO UPDATE SET
          seller_gstin=EXCLUDED.seller_gstin,seller_state_code=EXCLUDED.seller_state_code,
          rates_json=EXCLUDED.rates_json,updated_by=EXCLUDED.updated_by,updated_at=now()
          RETURNING seller_gstin,seller_state_code,rates_json,updated_at""",
          (body.seller_gstin.strip(),body.seller_state_code,json.dumps({k:str(v) for k,v in body.rates.items()}),actor["id"])).fetchone()
        return {"configured":True,"settings":row}

@router.get("/admin/invoices")
def list_invoices(authorization: str | None = Header(default=None)):
    _require(authorization, {"super_admin","admin","staff"})
    with psycopg.connect(_db(), row_factory=dict_row) as c:
        _schema(c)
        from .commerce import _ensure_commerce_schema
        _ensure_commerce_schema(c)
        items=c.execute("""SELECT id,reference,source_channel,source_id,customer_name,status,subtotal,discount_total,tax_total,total,paid_total,items,created_at,'operational_invoice' AS record_type
          FROM sb_invoices
          UNION ALL
          SELECT o.id,o.invoice_number AS reference,o.source_channel,o.id AS source_id,
            COALESCE(o.shipping_address->>'full_name','Website customer') AS customer_name,
            CASE WHEN o.status='cancelled' THEN 'cancelled' WHEN o.payment_status='paid' THEN 'paid' WHEN o.payment_status='partially_paid' THEN 'partially_paid' ELSE 'issued' END AS status,
            o.subtotal,0::numeric AS discount_total,0::numeric AS tax_total,o.total,
            o.paid_total,
            COALESCE((SELECT jsonb_agg(jsonb_build_object('variant_id',i.variant_id,'product_id',i.product_id,'sku',i.sku,'name',i.product_name,'quantity',i.quantity,'unit_price',i.unit_price,'line_total',i.line_total))
              FROM store_order_items i WHERE i.order_id=o.id),'[]'::jsonb) AS items,
            o.created_at,'website_order' AS record_type
          FROM store_orders o
          ORDER BY created_at DESC LIMIT 500""").fetchall()
        return {"items":items}


@router.post("/admin/invoices", status_code=201)
def create_invoice(body: InvoiceInput, authorization: str | None = Header(default=None)):
    actor=_require(authorization, {"super_admin","admin","staff"})
    if body.source_channel not in {"pos","website"}: raise HTTPException(422,"Channel must be website or pos.")
    subtotal=Decimal("0")
    for item in body.items:
        qty=Decimal(str(item.get("quantity",0))); price=Decimal(str(item.get("unit_price",0)))
        if qty<=0 or price<0: raise HTTPException(422,"Invoice quantities must be positive and prices non-negative.")
        if body.source_channel=="pos" and (not item.get("variant_id") or qty != qty.to_integral_value()):
            raise HTTPException(422,"POS inventory lines require a variant_id and whole-unit quantity.")
        subtotal+=(qty*price)
    tax=body.tax_total
    discount=body.discount_total
    if tax<0 or discount<0: raise HTTPException(422,"Tax and discount cannot be negative.")
    if discount>subtotal: raise HTTPException(422,"Discount cannot exceed the invoice subtotal.")
    total=(subtotal-discount+tax).quantize(Decimal("0.01")); ref=_ref("INV")
    with psycopg.connect(_db(), row_factory=dict_row) as c:
        _schema(c)
        gst_split={"cgst":Decimal("0"),"sgst":Decimal("0"),"igst":Decimal("0")}
        tax_config=c.execute("SELECT seller_state_code,rates_json FROM sb_tax_config WHERE id=1").fetchone()
        if tax==0 and tax_config and any(item.get("hsn_code") or item.get("gst_rate") for item in body.items) and not body.place_of_supply_state_code:
            raise HTTPException(422,"Place of supply is required to calculate GST from configured HSN rates.")
        if tax==0 and tax_config and body.place_of_supply_state_code:
            seller_state=str(tax_config["seller_state_code"])
            place_state=str(body.place_of_supply_state_code)
            if len(place_state)!=2 or not place_state.isdigit(): raise HTTPException(422,"Place of supply must be a valid two-digit Indian state code.")
            for item in body.items:
                hsn=str(item.get("hsn_code",""))
                rate=Decimal(str(item.get("gst_rate") or tax_config["rates_json"].get(hsn,0)))
                if rate<0 or rate>100: raise HTTPException(422,"GST rate must be between 0 and 100 percent.")
                if rate==0: continue
                if not seller_state: raise HTTPException(422,"Configure the seller GST state before calculating GST.")
                gross=Decimal(str(item["quantity"]))*Decimal(str(item["unit_price"]))
                line_discount=(discount*gross/subtotal) if subtotal else Decimal("0")
                taxable=max(Decimal("0"),gross-line_discount)
                line_tax=(taxable*rate/Decimal("100")).quantize(Decimal("0.01"))
                if seller_state==place_state:
                    cgst=(line_tax/2).quantize(Decimal("0.01")); sgst=line_tax-cgst
                    gst_split["cgst"]+=cgst; gst_split["sgst"]+=sgst
                    item["gst_breakdown"]={"rate":str(rate),"taxable_value":str(taxable),"cgst":str(cgst),"sgst":str(sgst),"igst":"0.00"}
                else:
                    gst_split["igst"]+=line_tax
                    item["gst_breakdown"]={"rate":str(rate),"taxable_value":str(taxable),"cgst":"0.00","sgst":"0.00","igst":str(line_tax)}
            computed=sum(gst_split.values(),Decimal("0"))
            if computed>0: tax=computed
        total=(subtotal-discount+tax).quantize(Decimal("0.01"))
        if body.source_channel=="pos":
            if body.warehouse_id is None: raise HTTPException(422,"Select a warehouse for POS stock deduction.")
            if not c.execute("SELECT id FROM sb_warehouses WHERE id=%s AND active FOR UPDATE",(body.warehouse_id,)).fetchone():
                raise HTTPException(404,"Active POS warehouse not found.")
            for line in body.items:
                vid=int(line["variant_id"]); qty=int(line["quantity"])
                if not c.execute("SELECT id FROM product_variants WHERE id=%s",(vid,)).fetchone():
                    raise HTTPException(404,f"Variant {vid} not found.")
                balance=c.execute("SELECT COALESCE(SUM(quantity_delta),0) qty FROM sb_inventory_ledger WHERE warehouse_id=%s AND variant_id=%s",(body.warehouse_id,vid)).fetchone()["qty"]
                if balance<qty: raise HTTPException(409,f"Insufficient stock for variant {vid} at selected warehouse.")
        row=c.execute("""INSERT INTO sb_invoices(reference,source_channel,customer_name,status,subtotal,discount_total,tax_total,total,items,created_by)
          VALUES(%s,%s,%s,'issued',%s,%s,%s,%s,%s::jsonb,%s) RETURNING *""",
          (ref,body.source_channel,body.customer_name,subtotal,discount,tax,total,json.dumps(body.items),actor["id"])).fetchone()
        _register_document(c,ref,"sale_invoice",row["id"])
        if body.source_channel=="pos":
            for line in body.items:
                c.execute("""INSERT INTO sb_inventory_ledger(warehouse_id,variant_id,quantity_delta,movement_type,reference,note,actor_id)
                  VALUES(%s,%s,%s,'sale',%s,'POS invoice sale',%s)""",(body.warehouse_id,int(line["variant_id"]),-int(line["quantity"]),ref,actor["id"]))
        _event(c,ref,"invoice_issued",actor["id"],new="issued",details={"channel":body.source_channel,"warehouse_id":body.warehouse_id})
        # One balanced sales posting per invoice; subsequent payments do not repost revenue.
        lines=[{"account_code":"1100","debit":str(total),"credit":"0"},{"account_code":"4000","debit":"0","credit":str(subtotal-discount)}]
        if gst_split["cgst"] or gst_split["sgst"] or gst_split["igst"]:
            if gst_split["cgst"]: lines.append({"account_code":"2110","debit":"0","credit":str(gst_split["cgst"])})
            if gst_split["sgst"]: lines.append({"account_code":"2120","debit":"0","credit":str(gst_split["sgst"])})
            if gst_split["igst"]: lines.append({"account_code":"2130","debit":"0","credit":str(gst_split["igst"])})
        elif tax: lines.append({"account_code":"2100","debit":"0","credit":str(tax)})
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
        from .commerce import _ensure_commerce_schema
        _ensure_commerce_schema(c)
        invoice=c.execute("SELECT * FROM sb_invoices WHERE reference=%s",(body.invoice_reference,)).fetchone()
        website_order=c.execute("SELECT * FROM store_orders WHERE invoice_number=%s",(body.invoice_reference,)).fetchone() if not invoice else None
        if not invoice and not website_order: raise HTTPException(404,"Invoice reference not found.")
        if invoice:
            sold={int(x["variant_id"]):int(x["quantity"]) for x in invoice["items"] if x.get("variant_id")}
        else:
            sold={int(x["variant_id"]):int(x["quantity"]) for x in c.execute("SELECT variant_id,quantity FROM store_order_items WHERE order_id=%s",(website_order["id"],)).fetchall()}
        requested={}
        for line in body.items:
            vid=int(line.get("variant_id",0)); qty=int(line.get("quantity",0))
            if vid not in sold or qty<1: raise HTTPException(422,"Return lines must match sold variants and have positive quantities.")
            requested[vid]=requested.get(vid,0)+qty
        previous=c.execute("SELECT items FROM sb_returns WHERE invoice_reference=%s AND status<>'cancelled'",(body.invoice_reference,)).fetchall()
        returned={}
        for prev in previous:
            for line in prev["items"]:
                vid=int(line["variant_id"]); returned[vid]=returned.get(vid,0)+int(line.get("quantity",0))
        for vid,qty in requested.items():
            if returned.get(vid,0)+qty>sold[vid]: raise HTTPException(409,f"Return quantity exceeds sold quantity for variant {vid}.")
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
        items=list(r["items"])
        if body.status=="inspected":
            if r["origin_warehouse_id"] is None: raise HTTPException(409,"Set an origin warehouse before inspection.")
            origin=c.execute("SELECT locations FROM sb_warehouses WHERE id=%s AND active",(r["origin_warehouse_id"],)).fetchone()
            allowed_locations=origin["locations"] if origin and isinstance(origin["locations"],list) else []
            if allowed_locations and body.location not in allowed_locations: raise HTTPException(422,"Choose a configured origin warehouse bin/location before inspection.")
            accepted={int(x.get("variant_id",0)):int(x.get("quantity",0)) for x in body.accepted_items}
            returned={int(x["variant_id"]):int(x["quantity"]) for x in items}
            if set(accepted)-set(returned) or any(q<0 or q>returned[vid] for vid,q in accepted.items()):
                raise HTTPException(422,"Accepted quantities must be valid quantities from this return.")
            for line in items:
                vid=int(line["variant_id"]); good=accepted.get(vid,0)
                line["accepted_quantity"]=good; line["rejected_quantity"]=int(line["quantity"])-good
                if good:
                    c.execute("""INSERT INTO sb_inventory_ledger(warehouse_id,variant_id,quantity_delta,movement_type,reference,location,note,actor_id)
                      VALUES(%s,%s,%s,'return',%s,%s,'Accepted customer return',%s)""",(r["origin_warehouse_id"],vid,good,r["reference"],body.location,actor["id"]))
        if body.status=="received_at_origin":
            if body.origin_warehouse_id is None: raise HTTPException(422,"Select the origin warehouse when the return arrives.")
            if not c.execute("SELECT id FROM sb_warehouses WHERE id=%s AND active",(body.origin_warehouse_id,)).fetchone(): raise HTTPException(404,"Active origin warehouse not found.")
        refund=Decimal("0.00")
        if body.status=="refunded":
            invoice=c.execute("SELECT * FROM sb_invoices WHERE reference=%s",(r["invoice_reference"],)).fetchone()
            if invoice:
                prices={int(x["variant_id"]):Decimal(str(x.get("unit_price",0))) for x in invoice["items"] if x.get("variant_id")}
            else:
                order=c.execute("SELECT id FROM store_orders WHERE invoice_number=%s",(r["invoice_reference"],)).fetchone()
                prices={int(x["variant_id"]):Decimal(str(x["unit_price"])) for x in c.execute("SELECT variant_id,unit_price FROM store_order_items WHERE order_id=%s",(order["id"],)).fetchall()} if order else {}
            refund=sum((prices.get(int(x["variant_id"]),Decimal("0"))*int(x.get("accepted_quantity",0)) for x in items),Decimal("0")).quantize(Decimal("0.01"))
            credit_ref=_ref("CN")
            c.execute("INSERT INTO sb_credit_notes(reference,invoice_reference,return_reference,amount,created_by) VALUES(%s,%s,%s,%s,%s)",
              (credit_ref,r["invoice_reference"],r["reference"],refund,actor["id"]))
            if refund>0:
                c.execute("INSERT INTO sb_journal_entries(reference,source_reference,memo,lines) VALUES(%s,%s,%s,%s::jsonb)",
                  (_ref("JE"),credit_ref,"Customer return credit note",json.dumps([{"account_code":"4000","debit":str(refund),"credit":"0"},{"account_code":"1100","debit":"0","credit":str(refund)}])))
            _event(c,r["reference"],"credit_note_posted",actor["id"],r["status"],"refunded",{"credit_note_reference":credit_ref,"amount":str(refund)})
        c.execute("UPDATE sb_returns SET status=%s,items=%s::jsonb,refund_amount=%s,origin_warehouse_id=COALESCE(%s,origin_warehouse_id),updated_at=now() WHERE id=%s",(body.status,json.dumps(items),refund,body.origin_warehouse_id,return_id))
        _event(c,r["reference"],"reverse_logistics_status",actor["id"],r["status"],body.status,{"invoice_reference":r["invoice_reference"],"refund_amount":str(refund)})
        return {"reference":r["reference"],"invoice_reference":r["invoice_reference"],"status":body.status,"refund_amount":str(refund)}


@router.get("/admin/accounting/overview")
def accounting_overview(authorization: str | None = Header(default=None)):
    _require(authorization, {"super_admin","admin","staff"})
    with psycopg.connect(_db(), row_factory=dict_row) as c:
        _schema(c)
        from .commerce import _ensure_commerce_schema
        _ensure_commerce_schema(c)
        operational=c.execute("SELECT COUNT(*)::int count,COALESCE(SUM(total),0) total,COALESCE(SUM(paid_total),0) paid FROM sb_invoices WHERE status NOT IN ('cancelled','draft')").fetchone()
        website=c.execute("""SELECT COUNT(*)::int count,COALESCE(SUM(total),0) total,
          COALESCE(SUM(paid_total),0) paid
          FROM store_orders WHERE status NOT IN ('cancelled')""").fetchone()
        credit_total=c.execute("SELECT COALESCE(SUM(amount),0) amount FROM sb_credit_notes WHERE status='posted'").fetchone()["amount"]
        gross_sales=operational["total"]+website["total"]
        return {
          "sales_invoices":{"count":operational["count"]+website["count"],"total":gross_sales,"paid":operational["paid"]+website["paid"]},
          "credit_notes":credit_total,
          "net_sales":gross_sales-credit_total,
          "receivables":c.execute("SELECT COALESCE(SUM(total-paid_total),0) amount FROM sb_invoices WHERE status IN ('issued','partially_paid','overdue')").fetchone()["amount"] + c.execute("SELECT COALESCE(SUM(CASE WHEN payment_status='paid' THEN 0 ELSE total END),0) amount FROM store_orders WHERE status NOT IN ('cancelled')").fetchone()["amount"],
          "payables":c.execute("SELECT COALESCE(SUM(amount+tax_total-paid_total),0) amount FROM sb_supplier_bills WHERE status IN ('approved','partially_paid')").fetchone()["amount"],
          "cash_collected":c.execute("SELECT COALESCE(SUM(amount),0) amount FROM sb_payments WHERE status='posted'").fetchone()["amount"] + c.execute("SELECT COALESCE(SUM(paid_total),0) amount FROM store_orders").fetchone()["amount"],
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
    location: str = ""

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

@router.get("/admin/accounting/reports")
def accounting_reports(authorization: str | None = Header(default=None)):
    _require(authorization, {"super_admin","admin","staff"})
    with psycopg.connect(_db(), row_factory=dict_row) as c:
        _schema(c)
        balances=c.execute("""SELECT a.code,a.name,a.account_type,
          COALESCE(SUM((x->>'debit')::numeric),0) AS debits,
          COALESCE(SUM((x->>'credit')::numeric),0) AS credits
          FROM sb_accounts a LEFT JOIN sb_journal_entries j ON j.posted
          LEFT JOIN LATERAL jsonb_array_elements(j.lines) x ON x->>'account_code'=a.code
          WHERE a.active GROUP BY a.code,a.name,a.account_type ORDER BY a.code""").fetchall()
        for row in balances:
            row["balance"]=row["debits"]-row["credits"] if row["account_type"] in {"asset","expense"} else row["credits"]-row["debits"]
        pnl=[x for x in balances if x["account_type"] in {"income","expense"}]
        balance_sheet=[x for x in balances if x["account_type"] in {"asset","liability","equity"}]
        cash=c.execute("""SELECT COALESCE(SUM((x->>'debit')::numeric-(x->>'credit')::numeric),0) amount
          FROM sb_journal_entries j CROSS JOIN LATERAL jsonb_array_elements(j.lines) x
          WHERE j.posted AND x->>'account_code'='1000'""").fetchone()["amount"]
        return {"trial_balance":balances,"profit_and_loss":pnl,
          "net_profit":sum((x["balance"] if x["account_type"]=="income" else -x["balance"] for x in pnl),Decimal("0")),
          "balance_sheet":balance_sheet,"cash_flow":{"cash_and_bank_movement":cash}}


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
        warehouse=c.execute("SELECT id,locations FROM sb_warehouses WHERE id=%s AND active FOR UPDATE",(body.warehouse_id,)).fetchone()
        if not warehouse: raise HTTPException(404,"Active warehouse not found.")
        allowed_locations=warehouse["locations"] if isinstance(warehouse["locations"],list) else []
        if allowed_locations and body.location not in allowed_locations: raise HTTPException(422,"Select a configured warehouse bin/location.")
        if not c.execute("SELECT id FROM product_variants WHERE id=%s",(body.variant_id,)).fetchone():
            raise HTTPException(404,"Product variant not found.")
        balance=c.execute("SELECT COALESCE(SUM(quantity_delta),0) qty FROM sb_inventory_ledger WHERE warehouse_id=%s AND variant_id=%s",
          (body.warehouse_id,body.variant_id)).fetchone()["qty"]
        if balance+body.quantity_delta<0: raise HTTPException(409,"Movement would make available stock negative.")
        row=c.execute("""INSERT INTO sb_inventory_ledger(warehouse_id,variant_id,quantity_delta,movement_type,reference,location,note,actor_id)
          VALUES(%s,%s,%s,%s,%s,%s,%s,%s) RETURNING *""",
          (body.warehouse_id,body.variant_id,body.quantity_delta,body.movement_type,ref,body.location,body.note,actor["id"])).fetchone()
        _event(c,ref,"stock_movement",actor["id"],details={"warehouse_id":body.warehouse_id,"variant_id":body.variant_id,"quantity_delta":body.quantity_delta})
        return {"movement":row,"balance":balance+body.quantity_delta}


class ReorderLevelInput(BaseModel):
    warehouse_id: int = Field(gt=0)
    variant_id: int = Field(gt=0)
    minimum_quantity: int = Field(ge=0)


@router.get("/admin/inventory/stock-levels")
def list_stock_levels(authorization: str | None = Header(default=None)):
    _require(authorization, {"super_admin", "admin", "staff"})
    with psycopg.connect(_db(), row_factory=dict_row) as c:
        _schema(c)
        return {"items": c.execute("""SELECT v.id AS variant_id, v.sku, v.selling_price,
            p.name, p.brand, w.id AS warehouse_id, w.name AS warehouse_name,
            COALESCE(SUM(l.quantity_delta),0)::int AS quantity,
            COALESCE(r.minimum_quantity,0)::int AS minimum_quantity
          FROM product_variants v
          JOIN products p ON p.id=v.product_id
          CROSS JOIN sb_warehouses w
          LEFT JOIN sb_inventory_ledger l ON l.variant_id=v.id AND l.warehouse_id=w.id
          LEFT JOIN sb_inventory_reorder_levels r ON r.variant_id=v.id AND r.warehouse_id=w.id
          WHERE w.active AND COALESCE(v.status,'active')='active'
          GROUP BY v.id,v.sku,v.selling_price,p.name,p.brand,w.id,w.name,r.minimum_quantity
          ORDER BY p.name,v.id,w.name""").fetchall()}


@router.put("/admin/inventory/reorder-level")
def save_reorder_level(body: ReorderLevelInput, authorization: str | None = Header(default=None)):
    _require(authorization, {"super_admin", "admin"})
    with psycopg.connect(_db(), row_factory=dict_row) as c:
        _schema(c)
        if not c.execute("SELECT id FROM product_variants WHERE id=%s", (body.variant_id,)).fetchone():
            raise HTTPException(404, "Product variant not found.")
        if not c.execute("SELECT id FROM sb_warehouses WHERE id=%s AND active", (body.warehouse_id,)).fetchone():
            raise HTTPException(404, "Active warehouse not found.")
        return {"item": c.execute("""INSERT INTO sb_inventory_reorder_levels(warehouse_id,variant_id,minimum_quantity)
          VALUES(%s,%s,%s) ON CONFLICT(warehouse_id,variant_id) DO UPDATE
          SET minimum_quantity=EXCLUDED.minimum_quantity,updated_at=now() RETURNING *""",
          (body.warehouse_id,body.variant_id,body.minimum_quantity)).fetchone()}
