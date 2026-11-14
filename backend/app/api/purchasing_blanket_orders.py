"""Blanket purchase agreements with controlled releases into standard purchase orders."""
import uuid
from datetime import date
from decimal import Decimal

import psycopg
from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel, Field, field_validator, model_validator

from app.api.purchasing import _connect, _db_error
from app.api.purchasing_lifecycle import _actor, _purchase_policy_for_po, _record_purchase_approval_stage
from app.api.organisation_policies import load_active_policy

router = APIRouter(prefix="/purchasing", tags=["purchasing-blanket-orders"])


class BlanketLine(BaseModel):
    variant_id: int = Field(gt=0)
    agreed_unit_cost: Decimal = Field(ge=0, max_digits=12, decimal_places=2)
    agreed_quantity: Decimal | None = Field(default=None, gt=0, max_digits=14, decimal_places=3)


class BlanketCreate(BaseModel):
    supplier_id: int = Field(gt=0)
    location_id: int = Field(gt=0)
    title: str = Field(min_length=3, max_length=200)
    start_date: date
    end_date: date
    currency: str = Field(default="INR", min_length=3, max_length=3)
    max_contract_value: Decimal | None = Field(default=None, gt=0, max_digits=14, decimal_places=2)
    lines: list[BlanketLine] = Field(min_length=1, max_length=200)

    @field_validator("title")
    @classmethod
    def clean_title(cls, value):
        value = value.strip()
        if len(value) < 3:
            raise ValueError("Agreement title must contain at least 3 characters")
        return value

    @field_validator("currency")
    @classmethod
    def clean_currency(cls, value):
        value = value.strip().upper()
        if not value.isalpha():
            raise ValueError("Currency must be a three-letter code")
        return value

    @model_validator(mode="after")
    def valid_dates_and_lines(self):
        if self.end_date < self.start_date:
            raise ValueError("End date cannot be before start date")
        ids = [line.variant_id for line in self.lines]
        if len(ids) != len(set(ids)):
            raise ValueError("Each catalogue variant may appear once")
        if self.max_contract_value is None and any(line.agreed_quantity is None for line in self.lines):
            raise ValueError("Set a maximum contract value when any item has no quantity limit")
        return self


class BlanketReleaseLine(BaseModel):
    blanket_line_id: int = Field(gt=0)
    quantity: Decimal = Field(gt=0, max_digits=14, decimal_places=3)


class BlanketRelease(BaseModel):
    lines: list[BlanketReleaseLine] = Field(min_length=1, max_length=200)


@router.get("/blanket-orders")
def list_blanket_orders(status: str | None = None, limit: int = Query(100, ge=1, le=500), offset: int = Query(0, ge=0)):
    allowed = {"draft", "submitted", "active", "rejected", "closed", "cancelled", "expired"}
    if status and status not in allowed:
        raise HTTPException(422, "Unsupported blanket-order status")
    try:
        with _connect() as conn:
            rows = conn.execute(
                "SELECT b.id,b.blanket_number,b.title,b.supplier_id,s.name AS supplier_name,"
                "b.location_id,l.name AS location_name,b.start_date,b.end_date,b.currency,"
                "b.max_contract_value,b.status,b.created_at,"
                "(SELECT count(*) FROM purchase_blanket_order_lines bl WHERE bl.blanket_order_id=b.id) AS line_count,"
                "(SELECT count(*) FROM purchase_blanket_order_releases r WHERE r.blanket_order_id=b.id) AS release_count "
                "FROM purchase_blanket_orders b JOIN suppliers s ON s.id=b.supplier_id "
                "JOIN stock_locations l ON l.id=b.location_id "
                + ("WHERE b.status=%s " if status else "")
                + "ORDER BY b.created_at DESC,b.id DESC LIMIT %s OFFSET %s",
                (status,limit,offset) if status else (limit,offset),
            ).fetchall()
        return {"items": rows, "limit": limit, "offset": offset}
    except psycopg.Error as exc:
        raise _db_error(exc) from exc


@router.post("/blanket-orders", status_code=201)
def create_blanket_order(payload: BlanketCreate, request: Request):
    actor_id, actor_email, _ = _actor(request)
    try:
        with _connect() as conn:
            with conn.transaction():
                if not conn.execute("SELECT id FROM suppliers WHERE id=%s AND is_active=TRUE FOR SHARE",(payload.supplier_id,)).fetchone():
                    raise HTTPException(404,"Active supplier not found")
                location = conn.execute("SELECT id FROM stock_locations WHERE id=%s AND is_active=TRUE FOR SHARE",(payload.location_id,)).fetchone()
                if not location:
                    raise HTTPException(404,"Active stock location not found")
                ids=[line.variant_id for line in payload.lines]
                found=conn.execute("SELECT id FROM product_variants WHERE id=ANY(%s) AND is_active=TRUE FOR SHARE",(ids,)).fetchall()
                if len(found)!=len(ids):
                    raise HTTPException(422,"One or more variants are missing or inactive")
                number="BO-"+uuid.uuid4().hex[:12].upper()
                row=conn.execute(
                    "INSERT INTO purchase_blanket_orders(blanket_number,supplier_id,location_id,title,start_date,end_date,currency,max_contract_value,created_by_user_id,created_by_email) "
                    "VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING id,blanket_number,status,created_at",
                    (number,payload.supplier_id,payload.location_id,payload.title,payload.start_date,payload.end_date,payload.currency,payload.max_contract_value,actor_id,actor_email),
                ).fetchone()
                for line in payload.lines:
                    conn.execute("INSERT INTO purchase_blanket_order_lines(blanket_order_id,variant_id,agreed_quantity,agreed_unit_cost) VALUES(%s,%s,%s,%s)",
                                 (row["id"],line.variant_id,line.agreed_quantity,line.agreed_unit_cost))
        return {**row,"line_count":len(payload.lines)}
    except HTTPException:
        raise
    except psycopg.Error as exc:
        raise _db_error(exc) from exc


@router.get("/blanket-orders/{blanket_id}")
def get_blanket_order(blanket_id: int):
    try:
        with _connect() as conn:
            row=conn.execute(
                "SELECT b.*,s.name AS supplier_name,l.name AS location_name FROM purchase_blanket_orders b "
                "JOIN suppliers s ON s.id=b.supplier_id JOIN stock_locations l ON l.id=b.location_id WHERE b.id=%s",(blanket_id,)
            ).fetchone()
            if not row:
                raise HTTPException(404,"Blanket order not found")
            lines=conn.execute(
                "SELECT bl.id AS blanket_line_id,bl.variant_id,v.sku,p.name AS product_name,bl.agreed_quantity,bl.agreed_unit_cost,"
                "COALESCE((SELECT sum(rl.quantity) FROM purchase_blanket_order_release_lines rl "
                "JOIN purchase_blanket_order_releases r ON r.id=rl.release_id JOIN purchase_orders po ON po.id=r.purchase_order_id "
                "WHERE rl.blanket_line_id=bl.id AND po.status<>'cancelled'),0) AS released_quantity "
                "FROM purchase_blanket_order_lines bl JOIN product_variants v ON v.id=bl.variant_id "
                "JOIN products p ON p.id=v.product_id WHERE bl.blanket_order_id=%s ORDER BY bl.id",(blanket_id,)
            ).fetchall()
            releases=conn.execute(
                "SELECT r.id,r.release_number,r.purchase_order_id,po.purchase_number,po.status,po.subtotal,r.created_at "
                "FROM purchase_blanket_order_releases r JOIN purchase_orders po ON po.id=r.purchase_order_id "
                "WHERE r.blanket_order_id=%s ORDER BY r.created_at DESC",(blanket_id,)
            ).fetchall()
        return {**row,"lines":lines,"releases":releases}
    except HTTPException:
        raise
    except psycopg.Error as exc:
        raise _db_error(exc) from exc


@router.post("/blanket-orders/{blanket_id}/submit")
def submit_blanket_order(blanket_id: int, request: Request):
    actor_id,actor_email,actor_role=_actor(request)
    try:
        with _connect() as conn:
            with conn.transaction():
                row=conn.execute("SELECT * FROM purchase_blanket_orders WHERE id=%s FOR UPDATE",(blanket_id,)).fetchone()
                if not row: raise HTTPException(404,"Blanket order not found")
                if row["status"]!="draft": raise HTTPException(409,"Only draft blanket orders can be submitted")
                if row["end_date"]<date.today(): raise HTTPException(409,"Expired agreement cannot be submitted")
                location=conn.execute("SELECT establishment_id FROM stock_locations WHERE id=%s",(row["location_id"],)).fetchone()
                if not location or location["establishment_id"] is None:
                    raise HTTPException(409,"Assign the agreement location to an active establishment before submission")
                policy=load_active_policy(conn,int(location["establishment_id"]),"purchase")
                conn.execute("UPDATE purchase_blanket_orders SET status='submitted',policy_version_id=%s,updated_at=now() WHERE id=%s",(policy["id"],blanket_id))
                conn.execute("INSERT INTO purchasing_approval_events(document_type,document_id,action,actor_user_id,actor_email,actor_role) VALUES('blanket_order',%s,'submitted',%s,%s,%s)",(blanket_id,actor_id,actor_email,actor_role))
        return {"id":blanket_id,"status":"submitted","policy_version_id":policy["id"]}
    except HTTPException: raise
    except psycopg.Error as exc: raise _db_error(exc) from exc


@router.post("/blanket-orders/{blanket_id}/approve")
def approve_blanket_order(blanket_id: int, request: Request):
    actor_id,actor_email,actor_role=_actor(request)
    try:
        with _connect() as conn:
            with conn.transaction():
                row=conn.execute("SELECT * FROM purchase_blanket_orders WHERE id=%s FOR UPDATE",(blanket_id,)).fetchone()
                if not row: raise HTTPException(404,"Blanket order not found")
                if row["status"]!="submitted": raise HTTPException(409,"Only submitted blanket orders can be approved")
                if row["end_date"]<date.today(): raise HTTPException(409,"Expired agreement cannot be approved")
                location=conn.execute("SELECT establishment_id FROM stock_locations WHERE id=%s",(row["location_id"],)).fetchone()
                if not location or location["establishment_id"] is None: raise HTTPException(409,"Agreement location has no active establishment")
                policy=conn.execute("SELECT * FROM organisation_policy_versions WHERE id=%s AND establishment_id=%s AND domain='purchase' FOR SHARE",(row["policy_version_id"],location["establishment_id"])).fetchone()
                if policy is None: raise HTTPException(409,"The agreement's bound Purchase policy is unavailable")
                lines=conn.execute("SELECT agreed_quantity,agreed_unit_cost FROM purchase_blanket_order_lines WHERE blanket_order_id=%s",(blanket_id,)).fetchall()
                amount=(Decimal(str(row["max_contract_value"])) if row["max_contract_value"] is not None
                        else sum((Decimal(str(x["agreed_quantity"]))*Decimal(str(x["agreed_unit_cost"])) for x in lines),Decimal("0")))
                evaluation,next_stage,complete=_record_purchase_approval_stage(
                    conn,policy=policy,document_type="blanket_order",document_id=blanket_id,
                    revision=row["approval_revision"],amount=amount,creator_user_id=row["created_by_user_id"],
                    actor_id=actor_id,actor_email=actor_email,actor_role=actor_role,reason="Blanket purchase agreement approval",
                )
                if complete:
                    conn.execute("UPDATE purchase_blanket_orders SET status='active',updated_at=now() WHERE id=%s",(blanket_id,))
                return {"id":blanket_id,"status":"active" if complete else "submitted","approved_stage":next_stage["sequence"],"required_stages":len(evaluation["stages"])}
    except HTTPException: raise
    except psycopg.Error as exc: raise _db_error(exc) from exc


@router.post("/blanket-orders/{blanket_id}/releases",status_code=201)
def create_blanket_release(blanket_id: int,payload: BlanketRelease,request: Request):
    actor_id,actor_email,_=_actor(request)
    try:
        with _connect() as conn:
            with conn.transaction():
                agreement=conn.execute("SELECT * FROM purchase_blanket_orders WHERE id=%s FOR UPDATE",(blanket_id,)).fetchone()
                if not agreement: raise HTTPException(404,"Blanket order not found")
                today=date.today()
                if agreement["status"]!="active": raise HTTPException(409,"Only approved active blanket orders can be released")
                if today<agreement["start_date"] or today>agreement["end_date"]: raise HTTPException(409,"Blanket agreement is outside its validity period")
                ids=[line.blanket_line_id for line in payload.lines]
                if len(ids)!=len(set(ids)): raise HTTPException(422,"Each agreement line may appear once per release")
                rows=conn.execute(
                    "SELECT bl.id,bl.variant_id,bl.agreed_quantity,bl.agreed_unit_cost,"
                    "COALESCE((SELECT sum(rl.quantity) FROM purchase_blanket_order_release_lines rl "
                    "JOIN purchase_blanket_order_releases r ON r.id=rl.release_id JOIN purchase_orders po ON po.id=r.purchase_order_id "
                    "WHERE rl.blanket_line_id=bl.id AND po.status<>'cancelled'),0) AS released_quantity "
                    "FROM purchase_blanket_order_lines bl WHERE bl.blanket_order_id=%s AND bl.id=ANY(%s) FOR UPDATE",
                    (blanket_id,ids),
                ).fetchall()
                if len(rows)!=len(ids): raise HTTPException(422,"A selected agreement line does not belong to this blanket order")
                by_id={int(x["id"]):x for x in rows}
                po_lines=[]
                for requested in payload.lines:
                    line=by_id[requested.blanket_line_id]
                    if line["agreed_quantity"] is not None and Decimal(str(line["released_quantity"]))+requested.quantity>Decimal(str(line["agreed_quantity"])):
                        raise HTTPException(409,"Release exceeds the remaining agreed quantity")
                    po_lines.append((line["variant_id"],requested.quantity,Decimal(str(line["agreed_unit_cost"]))))
                subtotal=sum((q*c for _,q,c in po_lines),Decimal("0"))
                used=conn.execute(
                    "SELECT COALESCE(sum(po.subtotal),0) AS value FROM purchase_blanket_order_releases r "
                    "JOIN purchase_orders po ON po.id=r.purchase_order_id WHERE r.blanket_order_id=%s AND po.status<>'cancelled'",(blanket_id,)
                ).fetchone()["value"]
                if agreement["max_contract_value"] is not None and Decimal(str(used))+subtotal>Decimal(str(agreement["max_contract_value"])):
                    raise HTTPException(409,"Release exceeds the remaining blanket contract value")
                po_number="PO-"+uuid.uuid4().hex[:12].upper()
                po=conn.execute(
                    "INSERT INTO purchase_orders(purchase_number,supplier_id,location_id,status,subtotal,notes,created_by_user_id,policy_version_id) "
                    "VALUES(%s,%s,%s,'draft',%s,%s,%s,%s) RETURNING id,purchase_number,status,subtotal",
                    (po_number,agreement["supplier_id"],agreement["location_id"],subtotal,
                     "Released under "+agreement["blanket_number"],actor_id,agreement["policy_version_id"]),
                ).fetchone()
                release_number="BOR-"+uuid.uuid4().hex[:10].upper()
                release=conn.execute(
                    "INSERT INTO purchase_blanket_order_releases(blanket_order_id,purchase_order_id,release_number,created_by_user_id) "
                    "VALUES(%s,%s,%s,%s) RETURNING id,release_number,purchase_order_id",
                    (blanket_id,po["id"],release_number,actor_id),
                ).fetchone()
                for requested,(variant_id,quantity,unit_cost) in zip(payload.lines,po_lines):
                    conn.execute("INSERT INTO purchase_order_lines(purchase_order_id,variant_id,quantity_ordered,unit_cost) VALUES(%s,%s,%s,%s)",(po["id"],variant_id,quantity,unit_cost))
                    conn.execute("INSERT INTO purchase_blanket_order_release_lines(release_id,blanket_line_id,variant_id,quantity,unit_cost) VALUES(%s,%s,%s,%s,%s)",(release["id"],requested.blanket_line_id,variant_id,quantity,unit_cost))
                conn.execute("INSERT INTO purchasing_approval_events(document_type,document_id,action,actor_user_id,actor_email,actor_role,reason) VALUES('purchase_order',%s,'submitted',%s,%s,%s,%s)",(po["id"],actor_id,actor_email,"Blanket release "+release_number,"Created from blanket agreement "+agreement["blanket_number"]))
        return {"release":release,"purchase_order":po,"message":"Release created as a draft purchase order. Standard PO approval is still required."}
    except HTTPException: raise
    except psycopg.Error as exc: raise _db_error(exc) from exc
