"""Customer directory and support case management."""
import logging

import psycopg
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
from fastapi import APIRouter, HTTPException, Query, Request
from psycopg.rows import dict_row
from pydantic import BaseModel, Field, field_validator
from app.core.config import settings

logger = logging.getLogger(__name__)

router=APIRouter(prefix="/customers",tags=["customers"])
CASE_STATUSES={"open","in_progress","waiting_customer","resolved","closed"}
CASE_PRIORITIES={"low","normal","high","urgent"}

CASE_TERMINAL_STATUSES = {"resolved", "closed"}


def _build_customer_360(customer, orders, cases):
    """Build a read-only CRM summary from existing customer, order and case rows."""
    latest_order_at = max((order["created_at"] for order in orders), default=None)
    open_case_count = sum(1 for case in cases if case["status"] not in CASE_TERMINAL_STATUSES)
    return {
        "customer": customer,
        "orders": orders,
        "support_cases": cases,
        "summary": {
            "order_count": len(orders),
            "open_case_count": open_case_count,
            "total_case_count": len(cases),
            "latest_order_at": latest_order_at,
        },
    }

def _connect():
    if not settings.database_url: raise HTTPException(503,"Customer database is not configured")
    try:return psycopg.connect(settings.database_url,row_factory=dict_row)
    except psycopg.Error as exc: raise HTTPException(503,"Customer database unavailable") from exc

def _error(exc):
    logger.exception(
        "Customer storage operation failed (SQLSTATE: %s)",
        getattr(exc, "sqlstate", None),
    )
    if getattr(exc,"sqlstate",None)=="23505":return HTTPException(409,"Customer phone or email already exists")
    return HTTPException(503,"Customer storage unavailable; verify customer migration")

def _require_crm_admin(request: Request):
    if getattr(request.state, "role", None) not in {"owner", "admin"}:
        raise HTTPException(403, "Only an owner or admin can manage support SLA policies")

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
    @field_validator("phone","address","notes")
    @classmethod
    def trim_optional(cls,v):
        return v.strip() if v else v

    @field_validator("email")
    @classmethod
    def valid_email(cls, v):
        if v:
            v = v.strip().lower()
            if "@" not in v or "." not in v.rsplit("@", 1)[-1] or " " in v:
                raise ValueError("Enter a valid email address")
            return v
        return v

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
    priority:str|None= None
    assigned_to:str|None=Field(default=None,max_length=200)
    resolution:str|None=Field(default=None,max_length=5000)
    @field_validator("status")
    @classmethod
    def status_valid(cls,v):
        if v not in CASE_STATUSES:raise ValueError("Invalid support case status")
        return v
    @field_validator("priority")
    @classmethod
    def update_priority_valid(cls,v):
        if v is not None and v not in CASE_PRIORITIES:raise ValueError("Invalid support priority")
        return v

class CustomerSupportTicketIn(BaseModel):
    subject:str=Field(min_length=3,max_length=200)
    description:str=Field(min_length=1,max_length=5000)
    @field_validator("subject","description")
    @classmethod
    def clean_support_text(cls,v):
        value=v.strip()
        if not value:raise ValueError("This field cannot be blank")
        return value

class SupportMessageIn(BaseModel):
    body:str=Field(min_length=1,max_length=10000)
    visibility:str="public"
    @field_validator("body")
    @classmethod
    def clean_message(cls,v):
        value=v.strip()
        if not value:raise ValueError("Message cannot be blank")
        return value
    @field_validator("visibility")
    @classmethod
    def valid_visibility(cls,v):
        if v not in {"public","internal"}:raise ValueError("Invalid message visibility")
        return v

class CustomerAccountLinkIn(BaseModel):
    customer_account_id:int=Field(gt=0)
    verification_confirmed:bool
    verification_method:str=Field(min_length=1,max_length=24)
    @field_validator("verification_method")
    @classmethod
    def valid_verification_method(cls,v):
        if v not in {"email_otp","phone_otp","in_person","other"}:raise ValueError("Invalid verification method")
        return v

class SupportSlaPolicyIn(BaseModel):
    priority:str
    first_response_minutes:int=Field(gt=0,le=525600)
    resolution_minutes:int=Field(gt=0,le=525600)
    calendar_minutes:bool=True
    timezone:str=Field(default="Asia/Kolkata",min_length=1,max_length=64)
    is_active:bool=True
    @field_validator("priority")
    @classmethod
    def valid_sla_priority(cls,v):
        if v not in CASE_PRIORITIES:raise ValueError("Invalid support priority")
        return v
    @field_validator("calendar_minutes")
    @classmethod
    def calendar_time_only(cls,v):
        if not v:raise ValueError("Only calendar-minute SLAs are supported until business hours are configured")
        return True
    @field_validator("timezone")
    @classmethod
    def valid_timezone(cls,v):
        try:
            ZoneInfo(v)
        except (ZoneInfoNotFoundError, ValueError):
            raise ValueError("Timezone must be a valid IANA timezone")
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
def list_cases(
    status:str|None=None,
    priority:str|None=None,
    assigned_to:str|None=Query(default=None,max_length=200),
    search:str|None=Query(default=None,max_length=200),
    limit:int=Query(default=100,ge=1,le=500),
    offset:int=Query(default=0,ge=0),
):
    if status and status not in CASE_STATUSES:raise HTTPException(422,"Invalid support case status")
    if priority and priority not in CASE_PRIORITIES:raise HTTPException(422,"Invalid support priority")
    clauses=[];params=[]
    if status: clauses.append("s.status=%s");params.append(status)
    if priority: clauses.append("s.priority=%s");params.append(priority)
    if assigned_to and assigned_to.strip(): clauses.append("s.assigned_to ILIKE %s");params.append("%"+assigned_to.strip()+"%")
    if search and search.strip():
        term="%"+search.strip()+"%"
        clauses.append("(s.case_number ILIKE %s OR s.subject ILIKE %s OR COALESCE(cu.name,'') ILIKE %s)")
        params.extend([term,term,term])
    where=" WHERE "+" AND ".join(clauses) if clauses else ""
    try:
        with _connect() as conn:
            rows=conn.execute(
                "SELECT s.id,s.case_number,s.customer_id,cu.name AS customer_name,s.order_id,s.subject,s.description,s.priority,s.status,s.assigned_to,s.resolution,s.created_at,s.updated_at,s.first_response_due_at,s.resolution_due_at,s.first_response_at,s.resolved_at "
                "FROM support_cases s LEFT JOIN customers cu ON cu.id=s.customer_id"+where+
                " ORDER BY CASE s.priority WHEN 'urgent' THEN 1 WHEN 'high' THEN 2 WHEN 'normal' THEN 3 ELSE 4 END,s.created_at DESC LIMIT %s OFFSET %s",
                (*params,limit,offset),
            ).fetchall()
            total=conn.execute(
                "SELECT count(*) AS total FROM support_cases s LEFT JOIN customers cu ON cu.id=s.customer_id"+where,
                params,
            ).fetchone()["total"]
        return {"items":rows,"total":total,"limit":limit,"offset":offset}
    except psycopg.Error as exc:raise _error(exc) from exc

@router.post("/support-cases",status_code=201)
def create_case(p:CaseIn,request:Request):
    import uuid
    try:
        with _connect() as conn:
            with conn.transaction():
                policy=_active_sla(conn,p.priority)
                row=conn.execute(
                    "INSERT INTO support_cases(case_number,customer_id,order_id,subject,description,priority,sla_policy_id,first_response_due_at,resolution_due_at) "
                    "VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s) "
                    "RETURNING id,case_number,customer_id,order_id,subject,description,priority,status,assigned_to,resolution,created_at,updated_at,first_response_due_at,resolution_due_at,first_response_at",
                    ("SUP-"+uuid.uuid4().hex[:16].upper(),p.customer_id,p.order_id,p.subject.strip(),p.description.strip(),p.priority,
                     policy["id"] if policy else None,policy["first_response_due_at"] if policy else None,policy["resolution_due_at"] if policy else None),
                ).fetchone()
                conn.execute(
                    "INSERT INTO support_case_messages(case_id,author_type,author_staff_user_id,visibility,body) "
                    "VALUES(%s,'staff',%s,'public',%s)",
                    (row["id"],request.state.user_id,p.description.strip()),
                )
                conn.execute(
                    "INSERT INTO support_case_events(case_id,actor_type,actor_staff_user_id,event_type,after_values) "
                    "VALUES(%s,'staff',%s,'ticket_created',jsonb_build_object('status',%s,'priority',%s))",
                    (row["id"],request.state.user_id,row["status"],row["priority"]),
                )
        return row
    except psycopg.Error as exc:raise _error(exc) from exc


@router.patch("/support-cases/{case_id}")
def update_case(case_id:int,p:CaseUpdate,request:Request):
    try:
        with _connect() as conn:
            with conn.transaction():
                before=conn.execute(
                    "SELECT status,priority,assigned_to,resolution,first_response_at FROM support_cases WHERE id=%s FOR UPDATE",
                    (case_id,),
                ).fetchone()
                if before is None:raise HTTPException(404,"Support case not found")
                assigned_to=p.assigned_to if "assigned_to" in p.model_fields_set else before["assigned_to"]
                resolution=p.resolution if "resolution" in p.model_fields_set else before["resolution"]
                next_priority=p.priority or before["priority"]
                is_reopening = before["status"] in CASE_TERMINAL_STATUSES and p.status not in CASE_TERMINAL_STATUSES
                if next_priority != before["priority"] or is_reopening:
                    policy=_active_sla(conn,next_priority)
                    sla_policy_id=policy["id"] if policy else None
                    first_response_due=policy["first_response_due_at"] if policy and not before["first_response_at"] else None
                    resolution_due=policy["resolution_due_at"] if policy else None
                    row=conn.execute(
                        "UPDATE support_cases SET status=%s,priority=%s,assigned_to=%s,resolution=%s,sla_policy_id=%s,"
                        "first_response_due_at=CASE WHEN first_response_at IS NULL THEN %s ELSE first_response_due_at END,"
                        "resolution_due_at=%s,"
                        "resolved_at=CASE WHEN %s IN ('resolved','closed') THEN COALESCE(resolved_at,now()) ELSE NULL END,"
                        "updated_at=now() WHERE id=%s "
                        "RETURNING id,case_number,status,priority,assigned_to,resolution,updated_at,resolved_at",
                        (p.status,next_priority,assigned_to,resolution,sla_policy_id,first_response_due,resolution_due,p.status,case_id),
                    ).fetchone()
                else:
                    row=conn.execute(
                        "UPDATE support_cases SET status=%s,priority=%s,assigned_to=%s,resolution=%s,"
                        "resolved_at=CASE WHEN %s IN ('resolved','closed') THEN COALESCE(resolved_at,now()) ELSE NULL END,"
                        "updated_at=now() WHERE id=%s "
                        "RETURNING id,case_number,status,priority,assigned_to,resolution,updated_at,resolved_at",
                        (p.status,next_priority,assigned_to,resolution,p.status,case_id),
                    ).fetchone()
                conn.execute(
                    "INSERT INTO support_case_events(case_id,actor_type,actor_staff_user_id,event_type,before_values,after_values) "
                    "VALUES(%s,'staff',%s,'case_updated',"
                    "jsonb_build_object('status',%s,'priority',%s,'assigned_to',%s,'resolution',%s),"
                    "jsonb_build_object('status',%s,'priority',%s,'assigned_to',%s,'resolution',%s))",
                    (case_id,request.state.user_id,before["status"],before["priority"],before["assigned_to"],before["resolution"],
                     row["status"],row["priority"],row["assigned_to"],row["resolution"]),
                )
            return row
    except HTTPException:raise
    except psycopg.Error as exc:raise _error(exc) from exc


def _linked_customer_id(conn, customer_account_id:int):
    row=conn.execute(
        "SELECT l.customer_id FROM customer_account_customer_links l "
        "JOIN customer_accounts a ON a.id=l.customer_account_id AND a.is_active=TRUE "
        "JOIN customers c ON c.id=l.customer_id AND c.is_active=TRUE "
        "WHERE l.customer_account_id=%s",
        (customer_account_id,),
    ).fetchone()
    if row is None:
        raise HTTPException(403,"Your website account is not linked to a CRM customer record. Contact customer support to verify and link your account.")
    return row["customer_id"]


def _active_sla(conn, priority:str):
    return conn.execute(
        "SELECT id, first_response_minutes, resolution_minutes, "
        "now() + make_interval(mins => first_response_minutes) AS first_response_due_at, "
        "now() + make_interval(mins => resolution_minutes) AS resolution_due_at "
        "FROM support_sla_policies WHERE priority=%s AND is_active=TRUE",
        (priority,),
    ).fetchone()


@router.get("/support-portal/tickets")
def list_customer_support_tickets(request:Request):
    try:
        with _connect() as conn:
            customer_id=_linked_customer_id(conn,request.state.customer_id)
            rows=conn.execute(
                "SELECT case_number,subject,priority,status,resolution,created_at,updated_at,first_response_due_at,resolution_due_at,first_response_at,resolved_at "
                "FROM support_cases WHERE customer_id=%s ORDER BY created_at DESC LIMIT 100",
                (customer_id,),
            ).fetchall()
        return {"items":rows}
    except HTTPException: raise
    except psycopg.Error as exc: raise _error(exc) from exc


@router.post("/support-portal/tickets",status_code=201)
def create_customer_support_ticket(payload:CustomerSupportTicketIn,request:Request):
    import uuid
    try:
        with _connect() as conn:
            with conn.transaction():
                customer_id=_linked_customer_id(conn,request.state.customer_id)
                policy=_active_sla(conn,"normal")
                case_number="SUP-"+uuid.uuid4().hex[:16].upper()
                row=conn.execute(
                    "INSERT INTO support_cases(case_number,customer_id,subject,description,priority,sla_policy_id,first_response_due_at,resolution_due_at) "
                    "VALUES(%s,%s,%s,%s,'normal',%s,%s,%s) "
                    "RETURNING id,case_number,subject,priority,status,created_at,updated_at,first_response_due_at,resolution_due_at",
                    (case_number,customer_id,payload.subject,payload.description,policy["id"] if policy else None,
                     policy["first_response_due_at"] if policy else None,policy["resolution_due_at"] if policy else None),
                ).fetchone()
                conn.execute(
                    "INSERT INTO support_case_messages(case_id,author_type,author_customer_account_id,visibility,body) "
                    "VALUES(%s,'customer',%s,'public',%s)",
                    (row["id"],request.state.customer_id,payload.description),
                )
                conn.execute(
                    "INSERT INTO support_case_events(case_id,actor_type,actor_customer_account_id,event_type,after_values) "
                    "VALUES(%s,'customer',%s,'ticket_created',jsonb_build_object('status',%s,'priority','normal'))",
                    (row["id"],request.state.customer_id,row["status"]),
                )
        return {"ticket":row}
    except HTTPException: raise
    except psycopg.Error as exc: raise _error(exc) from exc


@router.get("/support-portal/tickets/{case_number}")
def get_customer_support_ticket(case_number:str,request:Request):
    try:
        with _connect() as conn:
            customer_id=_linked_customer_id(conn,request.state.customer_id)
            ticket=conn.execute(
                "SELECT id,case_number,subject,description,priority,status,resolution,created_at,updated_at,first_response_due_at,resolution_due_at,first_response_at,resolved_at "
                "FROM support_cases WHERE upper(case_number)=upper(%s) AND customer_id=%s",
                (case_number.strip(),customer_id),
            ).fetchone()
            if ticket is None: raise HTTPException(404,"Ticket not found")
            messages=conn.execute(
                "SELECT id,author_type,visibility,body,created_at FROM support_case_messages "
                "WHERE case_id=%s AND visibility='public' ORDER BY created_at,id",
                (ticket["id"],),
            ).fetchall()
        return {"ticket":ticket,"messages":messages}
    except HTTPException: raise
    except psycopg.Error as exc: raise _error(exc) from exc


@router.post("/support-portal/tickets/{case_number}/messages",status_code=201)
def reply_to_customer_support_ticket(case_number:str,payload:SupportMessageIn,request:Request):
    try:
        with _connect() as conn:
            with conn.transaction():
                customer_id=_linked_customer_id(conn,request.state.customer_id)
                ticket=conn.execute(
                    "SELECT id,status FROM support_cases WHERE upper(case_number)=upper(%s) AND customer_id=%s FOR UPDATE",
                    (case_number.strip(),customer_id),
                ).fetchone()
                if ticket is None: raise HTTPException(404,"Ticket not found")
                if ticket["status"] in CASE_TERMINAL_STATUSES:
                    raise HTTPException(409,"This ticket is closed; create a new ticket if you need further help")
                message=conn.execute(
                    "INSERT INTO support_case_messages(case_id,author_type,author_customer_account_id,visibility,body) "
                    "VALUES(%s,'customer',%s,'public',%s) RETURNING id,author_type,visibility,body,created_at",
                    (ticket["id"],request.state.customer_id,payload.body),
                ).fetchone()
                conn.execute(
                    "INSERT INTO support_case_events(case_id,actor_type,actor_customer_account_id,event_type,after_values) "
                    "VALUES(%s,'customer',%s,'customer_replied',jsonb_build_object('message_id',%s))",
                    (ticket["id"],request.state.customer_id,message["id"]),
                )
                conn.execute("UPDATE support_cases SET updated_at=now() WHERE id=%s",(ticket["id"],))
        return {"message":message}
    except HTTPException: raise
    except psycopg.Error as exc: raise _error(exc) from exc


@router.get("/customer-accounts")
def search_customer_accounts(request:Request,search:str=Query(min_length=3,max_length=254)):
    if getattr(request.state,"role",None) not in {"owner","admin"}:
        raise HTTPException(403,"Only an owner or admin can search website accounts for verified linking")
    term="%"+search.strip().lower()+"%"
    try:
        with _connect() as conn:
            rows=conn.execute(
                "SELECT a.id,a.email,a.full_name,a.phone,a.is_active "
                "FROM customer_accounts a LEFT JOIN customer_account_customer_links l ON l.customer_account_id=a.id "
                "WHERE a.is_active=TRUE AND l.id IS NULL AND (lower(a.email) LIKE %s OR lower(a.full_name) LIKE %s) "
                "ORDER BY a.created_at DESC LIMIT 25",
                (term,term),
            ).fetchall()
        return {"items":rows}
    except psycopg.Error as exc: raise _error(exc) from exc


@router.post("/{customer_id}/account-link",status_code=201)
def link_customer_account(customer_id:int,payload:CustomerAccountLinkIn,request:Request):
    if customer_id<=0: raise HTTPException(422,"Customer ID must be positive")
    if not payload.verification_confirmed:
        raise HTTPException(422,"Verify the customer's account ownership before linking")
    try:
        with _connect() as conn:
            with conn.transaction():
                row=conn.execute(
                    "INSERT INTO customer_account_customer_links(customer_account_id,customer_id,linked_by_staff_user_id,verification_method,verified_at) "
                    "SELECT a.id,c.id,%s,%s,now() FROM customer_accounts a CROSS JOIN customers c "
                    "WHERE a.id=%s AND a.is_active=TRUE AND c.id=%s AND c.is_active=TRUE "
                    "RETURNING id,customer_account_id,customer_id,verification_method,verified_at,linked_at",
                    (request.state.user_id,payload.verification_method,payload.customer_account_id,customer_id),
                ).fetchone()
                if row is None: raise HTTPException(404,"Active customer account or CRM customer not found")
        return {"link":row}
    except HTTPException: raise
    except psycopg.Error as exc:
        if getattr(exc,"sqlstate",None)=="23505":
            raise HTTPException(409,"This website account or CRM customer is already linked") from exc
        raise _error(exc) from exc


@router.get("/support-sla-policies")
def list_support_sla_policies():
    try:
        with _connect() as conn:
            rows=conn.execute(
                "SELECT id,priority,first_response_minutes,resolution_minutes,calendar_minutes,timezone,is_active,created_at,updated_at "
                "FROM support_sla_policies ORDER BY CASE priority WHEN 'urgent' THEN 1 WHEN 'high' THEN 2 WHEN 'normal' THEN 3 ELSE 4 END,id"
            ).fetchall()
        return {"items":rows}
    except psycopg.Error as exc: raise _error(exc) from exc


@router.post("/support-sla-policies",status_code=201)
def create_support_sla_policy(payload:SupportSlaPolicyIn, request:Request):
    _require_crm_admin(request)
    try:
        with _connect() as conn:
            row=conn.execute(
                "INSERT INTO support_sla_policies(priority,first_response_minutes,resolution_minutes,calendar_minutes,timezone,is_active) "
                "VALUES(%s,%s,%s,%s,%s,%s) RETURNING id,priority,first_response_minutes,resolution_minutes,calendar_minutes,timezone,is_active,created_at,updated_at",
                (payload.priority,payload.first_response_minutes,payload.resolution_minutes,payload.calendar_minutes,payload.timezone,payload.is_active),
            ).fetchone()
        return row
    except psycopg.Error as exc:
        if getattr(exc,"sqlstate",None)=="23505":
            raise HTTPException(409,"An active SLA policy already exists for this priority") from exc
        raise _error(exc) from exc


@router.patch("/support-sla-policies/{policy_id}")
def update_support_sla_policy(policy_id:int,payload:SupportSlaPolicyIn,request:Request):
    _require_crm_admin(request)
    if policy_id<=0: raise HTTPException(422,"SLA policy ID must be positive")
    try:
        with _connect() as conn:
            row=conn.execute(
                "UPDATE support_sla_policies SET priority=%s,first_response_minutes=%s,resolution_minutes=%s,calendar_minutes=%s,timezone=%s,is_active=%s,updated_at=now() "
                "WHERE id=%s RETURNING id,priority,first_response_minutes,resolution_minutes,calendar_minutes,timezone,is_active,created_at,updated_at",
                (payload.priority,payload.first_response_minutes,payload.resolution_minutes,payload.calendar_minutes,payload.timezone,payload.is_active,policy_id),
            ).fetchone()
            if row is None: raise HTTPException(404,"SLA policy not found")
        return row
    except HTTPException: raise
    except psycopg.Error as exc:
        if getattr(exc,"sqlstate",None)=="23505":
            raise HTTPException(409,"An active SLA policy already exists for this priority") from exc
        raise _error(exc) from exc


@router.get("/support-cases/{case_id}")
def get_staff_support_case(case_id:int):
    try:
        with _connect() as conn:
            ticket=conn.execute(
                "SELECT s.id,s.case_number,s.customer_id,c.name AS customer_name,s.order_id,s.subject,s.description,s.priority,s.status,s.assigned_to,s.resolution,s.created_at,s.updated_at,s.sla_policy_id,s.first_response_due_at,s.resolution_due_at,s.first_response_at,s.resolved_at "
                "FROM support_cases s LEFT JOIN customers c ON c.id=s.customer_id WHERE s.id=%s",
                (case_id,),
            ).fetchone()
            if ticket is None: raise HTTPException(404,"Support case not found")
            messages=conn.execute(
                "SELECT m.id,m.author_type,m.author_customer_account_id,m.author_staff_user_id,m.visibility,m.body,m.created_at,cu.full_name AS customer_author,au.full_name AS staff_author "
                "FROM support_case_messages m LEFT JOIN customer_accounts cu ON cu.id=m.author_customer_account_id "
                "LEFT JOIN app_users au ON au.id=m.author_staff_user_id WHERE m.case_id=%s ORDER BY m.created_at,m.id",
                (case_id,),
            ).fetchall()
            events=conn.execute(
                "SELECT id,actor_type,event_type,before_values,after_values,created_at FROM support_case_events WHERE case_id=%s ORDER BY created_at,id",
                (case_id,),
            ).fetchall()
        return {"ticket":ticket,"messages":messages,"events":events}
    except HTTPException: raise
    except psycopg.Error as exc: raise _error(exc) from exc


@router.post("/support-cases/{case_id}/messages",status_code=201)
def add_staff_support_message(case_id:int,payload:SupportMessageIn,request:Request):
    try:
        with _connect() as conn:
            with conn.transaction():
                ticket=conn.execute("SELECT id FROM support_cases WHERE id=%s FOR UPDATE",(case_id,)).fetchone()
                if ticket is None: raise HTTPException(404,"Support case not found")
                message=conn.execute(
                    "INSERT INTO support_case_messages(case_id,author_type,author_staff_user_id,visibility,body) "
                    "VALUES(%s,'staff',%s,%s,%s) RETURNING id,author_type,visibility,body,created_at",
                    (case_id,request.state.user_id,payload.visibility,payload.body),
                ).fetchone()
                conn.execute(
                    "INSERT INTO support_case_events(case_id,actor_type,actor_staff_user_id,event_type,after_values) "
                    "VALUES(%s,'staff',%s,%s,jsonb_build_object('message_id',%s,'visibility',%s))",
                    (case_id,request.state.user_id,"staff_replied" if payload.visibility=="public" else "internal_note_added",message["id"],payload.visibility),
                )
                if payload.visibility=="public":
                    conn.execute("UPDATE support_cases SET first_response_at=COALESCE(first_response_at,now()),updated_at=now() WHERE id=%s",(case_id,))
                else:
                    conn.execute("UPDATE support_cases SET updated_at=now() WHERE id=%s",(case_id,))
        return {"message":message}
    except HTTPException: raise
    except psycopg.Error as exc: raise _error(exc) from exc


@router.get("/{customer_id}/360")
def get_customer_360(customer_id: int):
    """Return a staff-facing, read-only customer view with matched order and case history."""
    if customer_id <= 0:
        raise HTTPException(422, "Customer ID must be positive")
    try:
        with _connect() as conn:
            customer = conn.execute(
                "SELECT id,name,phone,email,pin_code,address,notes,is_active,created_at,updated_at "
                "FROM customers WHERE id=%s",
                (customer_id,),
            ).fetchone()
            if customer is None:
                raise HTTPException(404, "Customer not found")

            orders = []
            phone = customer.get("phone")
            if phone:
                digits = "".join(ch for ch in str(phone) if ch.isdigit())
                if len(digits) == 12 and digits.startswith("91"):
                    digits = digits[2:]
                elif len(digits) == 11 and digits.startswith("0"):
                    digits = digits[1:]
                orders = conn.execute(
                    "SELECT order_number,channel,status,subtotal,total,created_at "
                    "FROM orders WHERE CASE "
                    "WHEN length(regexp_replace(COALESCE(customer_phone,''),'[^0-9]','','g'))=12 "
                    "AND left(regexp_replace(COALESCE(customer_phone,''),'[^0-9]','','g'),2)='91' "
                    "THEN right(regexp_replace(COALESCE(customer_phone,''),'[^0-9]','','g'),10) "
                    "WHEN length(regexp_replace(COALESCE(customer_phone,''),'[^0-9]','','g'))=11 "
                    "AND left(regexp_replace(COALESCE(customer_phone,''),'[^0-9]','','g'),1)='0' "
                    "THEN right(regexp_replace(COALESCE(customer_phone,''),'[^0-9]','','g'),10) "
                    "ELSE regexp_replace(COALESCE(customer_phone,''),'[^0-9]','','g') END=%s "
                    "ORDER BY created_at DESC LIMIT 50",
                    (digits,),
                ).fetchall() if digits else []

            cases = conn.execute(
                "SELECT id,case_number,subject,priority,status,assigned_to,resolution,created_at,updated_at "
                "FROM support_cases WHERE customer_id=%s ORDER BY created_at DESC LIMIT 100",
                (customer_id,),
            ).fetchall()
        return _build_customer_360(customer, orders, cases)
    except HTTPException:
        raise
    except psycopg.Error as exc:
        raise _error(exc) from exc
