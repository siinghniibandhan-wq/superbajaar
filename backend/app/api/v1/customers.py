"""Customer directory and support case management."""
import psycopg
from fastapi import APIRouter, HTTPException, Query
from psycopg.rows import dict_row
from pydantic import BaseModel, Field, field_validator
from app.core.config import settings

router=APIRouter(prefix="/customers",tags=["customers"])
CASE_STATUSES={"open","in_progress","waiting_customer","resolved","closed"}
CASE_PRIORITIES={"low","normal","high","urgent"}

def _connect():
    if not settings.database_url: raise HTTPException(503,"Customer database is not configured")
    try:return psycopg.connect(settings.database_url,row_factory=dict_row)
    except psycopg.Error as exc: raise HTTPException(503,"Customer database unavailable") from exc

def _error(exc):
    if getattr(exc,"sqlstate",None)=="23505":return HTTPException(409,"Customer phone or email already exists")
    return HTTPException(503,"Customer storage unavailable; verify customer migration")

class CustomerIn(BaseModel):
    name:str=Field(min_length=1,max_length=200)
    phone:str|None=Field(default=None,max_length=20)
    email:str|None=Field(default=None,max_length=254)
    pin_code:str|None=Field(default=None,pattern=r"^[0-9]{6}$")
    address:str|None=Field(default=None,max_length=1000)
    notes:str|None=Field(default=None,max_length=2000)
    @field_validator("name")
    @classmethod
    def nonblank(cls,v):
        if not v.strip():raise ValueError("Name cannot be blank")
        return v.strip()
    @field_validator("phone","email","address","notes")
    @classmethod
    def trim_optional(cls,v):
        return v.strip() if v else v

class CustomerUpdate(CustomerIn): is_active:bool=True
class CaseIn(BaseModel):
    subject:str=Field(min_length=3,max_length=200)
    description:str=Field(min_length=1,max_length=5000)
    priority:str="normal"
    customer_id:int|None=Field(default=None,gt=0)
    order_id:int|None=Field(default=None,gt=0)
    @field_validator("priority")
    @classmethod
    def priority_valid(cls,v):
        if v not in CASE_PRIORITIES:raise ValueError("Invalid support priority")
        return v

class CaseUpdate(BaseModel):
    status:str
    assigned_to:str|None=Field(default=None,max_length=200)
    resolution:str|None=Field(default=None,max_length=5000)
    @field_validator("status")
    @classmethod
    def status_valid(cls,v):
        if v not in CASE_STATUSES:raise ValueError("Invalid support case status")
        return v

@router.get("")
def list_customers(search:str|None=Query(default=None,max_length=200),limit:int=Query(default=100,ge=1,le=500),offset:int=Query(default=0,ge=0)):
    where="";params=[]
    if search and search.strip():
        term="%"+search.strip()+"%";where=" WHERE name ILIKE %s OR COALESCE(phone,'') ILIKE %s OR COALESCE(email,'') ILIKE %s";params=[term,term,term]
    try:
        with _connect() as c:
            items=c.execute("SELECT id,name,phone,email,pin_code,address,notes,is_active,created_at,updated_at FROM customers"+where+" ORDER BY created_at DESC LIMIT %s OFFSET %s",(*params,limit,offset)).fetchall()
            total=c.execute("SELECT count(*) AS total FROM customers"+where,params).fetchone()["total"]
        return {"items":items,"total":total,"limit":limit,"offset":offset}
    except psycopg.Error as e:raise _error(e) from e

@router.post("",status_code=201)
def create_customer(p:CustomerIn):
    try:
        with _connect() as c:
            return c.execute("INSERT INTO customers(name,phone,email,pin_code,address,notes) VALUES(%s,%s,%s,%s,%s,%s) RETURNING id,name,phone,email,pin_code,address,notes,is_active,created_at,updated_at",(p.name,p.phone,p.email.lower() if p.email else None,p.pin_code,p.address,p.notes)).fetchone()
    except psycopg.Error as e:raise _error(e) from e

@router.patch("/{customer_id}")
def update_customer(customer_id:int,p:CustomerUpdate):
    try:
        with _connect() as c:
            row=c.execute("UPDATE customers SET name=%s,phone=%s,email=%s,pin_code=%s,address=%s,notes=%s,is_active=%s,updated_at=now() WHERE id=%s RETURNING id,name,phone,email,pin_code,address,notes,is_active,created_at,updated_at",(p.name,p.phone,p.email.lower() if p.email else None,p.pin_code,p.address,p.notes,p.is_active,customer_id)).fetchone()
            if not row:raise HTTPException(404,"Customer not found")
            return row
    except HTTPException:raise
    except psycopg.Error as e:raise _error(e) from e

@router.get("/support-cases")
def list_cases(status:str|None=None,limit:int=Query(default=100,ge=1,le=500),offset:int=Query(default=0,ge=0)):
    if status and status not in CASE_STATUSES:raise HTTPException(422,"Invalid support case status")
    where=" WHERE s.status=%s" if status else "";params=[status] if status else []
    try:
        with _connect() as c:
            rows=c.execute("SELECT s.id,s.case_number,s.customer_id,cu.name AS customer_name,s.order_id,s.subject,s.description,s.priority,s.status,s.assigned_to,s.resolution,s.created_at,s.updated_at FROM support_cases s LEFT JOIN customers cu ON cu.id=s.customer_id"+where+" ORDER BY s.created_at DESC LIMIT %s OFFSET %s",(*params,limit,offset)).fetchall()
        return {"items":rows,"limit":limit,"offset":offset}
    except psycopg.Error as e:raise _error(e) from e

@router.post("/support-cases",status_code=201)
def create_case(p:CaseIn):
    import uuid
    try:
        with _connect() as c:
            return c.execute("INSERT INTO support_cases(case_number,customer_id,order_id,subject,description,priority) VALUES(%s,%s,%s,%s,%s,%s) RETURNING id,case_number,customer_id,order_id,subject,description,priority,status,created_at,updated_at",("SUP-"+uuid.uuid4().hex[:10].upper(),p.customer_id,p.order_id,p.subject.strip(),p.description.strip(),p.priority)).fetchone()
    except psycopg.Error as e:raise _error(e) from e

@router.patch("/support-cases/{case_id}")
def update_case(case_id:int,p:CaseUpdate):
    try:
        with _connect() as c:
            row=c.execute("UPDATE support_cases SET status=%s,assigned_to=COALESCE(%s,assigned_to),resolution=COALESCE(%s,resolution),updated_at=now() WHERE id=%s RETURNING id,case_number,status,assigned_to,resolution,updated_at",(p.status,p.assigned_to,p.resolution,case_id)).fetchone()
            if not row:raise HTTPException(404,"Support case not found")
            return row
    except HTTPException:raise
    except psycopg.Error as e:raise _error(e) from e
