"""Integrated HR enterprise workflows.

All eight HR domains share audited, versioned records while retaining explicit
domain validation and controlled state transitions. Employee self-service is
bound to the authenticated user's linked employee record.
"""
from datetime import date
from decimal import Decimal, InvalidOperation
import json

import psycopg
from fastapi import APIRouter, File, Form, HTTPException, Query, Request, UploadFile
from pydantic import BaseModel, Field, field_validator
from app.api.hr import _actor, _manager, _employee, _hr_connection, _db_error
from app.services.hr_employee_documents import (
    EmployeeDocumentConfigurationError, EmployeeDocumentError,
    upload_employee_document, employee_document_download_url,
)

router = APIRouter(prefix="/hr/enterprise", tags=["hr-enterprise"])

DOMAINS = {"recruitment","documents","performance","learning","assets","travel","exit","analytics"}
MANAGER_ROLES = {"super_admin","owner","admin","manager"}
EMPLOYEE_DOMAINS = {"documents","performance","learning","assets","travel","exit"}
STATUSES = {
 "recruitment":{"draft","open","screening","shortlisted","interview","offered","hired","rejected","withdrawn","archived"},
 "documents":{"pending","uploaded","under_review","verified","rejected","expired","archived"},
 "performance":{"draft","active","self_review","manager_review","calibration","acknowledged","closed","cancelled"},
 "learning":{"planned","enrolled","in_progress","completed","failed","cancelled"},
 "assets":{"available","requested","approved","assigned","returned","maintenance","written_off","rejected"},
 "travel":{"draft","submitted","approved","rejected","booked","in_progress","completed","claimed","reimbursed","cancelled"},
 "exit":{"initiated","notice_period","handover","clearance","settlement_review","completed","withdrawn"},
 "analytics":{"saved","scheduled","archived"}
}
TRANSITIONS = {
 "recruitment":{"draft":{"open","archived"},"open":{"screening","archived"},"screening":{"shortlisted","rejected","withdrawn"},"shortlisted":{"interview","rejected","withdrawn"},"interview":{"offered","rejected","withdrawn"},"offered":{"hired","rejected","withdrawn"}},
 "documents":{"pending":{"uploaded","archived"},"uploaded":{"under_review","rejected"},"under_review":{"verified","rejected","expired"},"verified":{"expired","archived"},"rejected":{"uploaded","archived"},"expired":{"uploaded","archived"}},
 "performance":{"draft":{"active","cancelled"},"active":{"self_review","cancelled"},"self_review":{"manager_review"},"manager_review":{"calibration","acknowledged"},"calibration":{"acknowledged"},"acknowledged":{"closed"}},
 "learning":{"planned":{"enrolled","cancelled"},"enrolled":{"in_progress","cancelled"},"in_progress":{"completed","failed"},"failed":{"enrolled"}},
 "assets":{"available":{"assigned","maintenance","written_off"},"requested":{"approved","rejected"},"approved":{"assigned","rejected"},"assigned":{"returned","maintenance","written_off"},"maintenance":{"assigned","written_off"},"returned":{"maintenance","written_off"}},
 "travel":{"draft":{"submitted","cancelled"},"submitted":{"approved","rejected"},"approved":{"booked","cancelled"},"booked":{"in_progress","cancelled"},"in_progress":{"completed"},"completed":{"claimed"},"claimed":{"reimbursed"}},
 "exit":{"initiated":{"notice_period","withdrawn"},"notice_period":{"handover","withdrawn"},"handover":{"clearance"},"clearance":{"settlement_review"},"settlement_review":{"completed"}},
 "analytics":{"saved":{"scheduled","archived"},"scheduled":{"saved","archived"}}
}
MANAGER_ONLY_TYPES = {
 "recruitment":{"job_opening","candidate","application","interview","offer"},
 "assets":{"asset","allocation","maintenance"},
 "performance":{"review_cycle","review"},
 "learning":{"course","assessment","certificate"},
 "travel":{"booking","advance"},
 "exit":{"clearance","settlement"},
 "analytics":{"report"}
}
EMPLOYEE_TRANSITIONS = {
    ("travel", "draft", "submitted"),
    ("travel", "draft", "cancelled"),
    ("performance", "active", "self_review"),
    ("learning", "enrolled", "in_progress"),
    ("learning", "in_progress", "completed"),
    ("exit", "initiated", "withdrawn"),
}

def _employee_transition_allowed(domain, from_status, to_status):
    return (domain, from_status, to_status) in EMPLOYEE_TRANSITIONS

def _initial_status(domain, record_type):
    typed = {
        ("recruitment", "interview"): "interview",
        ("recruitment", "offer"): "offered",
        ("documents", "employee_document"): "pending",
        ("performance", "feedback"): "acknowledged",
        ("learning", "assessment"): "completed",
        ("learning", "certificate"): "completed",
        ("assets", "maintenance"): "maintenance",
        ("travel", "booking"): "booked",
        ("travel", "advance"): "approved",
        ("travel", "claim"): "claimed",
        ("exit", "clearance"): "clearance",
        ("exit", "settlement"): "settlement_review",
    }
    if (domain, record_type) in typed:
        return typed[(domain, record_type)]
    defaults = {
        "recruitment": "draft", "documents": "pending", "performance": "draft",
        "learning": "planned", "assets": "available" if record_type == "asset" else "requested",
        "travel": "draft", "exit": "initiated", "analytics": "saved",
    }
    return defaults[domain]

REQUIRED = {
 "recruitment":{
  "job_opening":["department","employment_type","location"],
  "candidate":["email"],
  "application":["candidate_id","job_id"],
  "interview":["application_id","scheduled_at","interviewer_employee_id","interview_type"],
  "offer":["application_id","offered_salary","currency","expires_on"]
 },
 "documents":{"employee_document":["document_type","file_name","object_key","content_type","sha256"]},
 "performance":{
  "review_cycle":["period_start","period_end"],
  "review":["cycle","reviewer_employee_id"],
  "goal":["description","measure","target"],
  "feedback":["review_id","feedback"]
 },
 "learning":{
  "course":["provider","course_type"],
  "enrollment":["course_id"],
  "assessment":["enrollment_id","score","pass_score"],
  "certificate":["enrollment_id","certificate_number","valid_until"]
 },
 "assets":{
  "asset":["asset_type","asset_tag"],
  "asset_request":["asset_type","purpose","needed_by"],
  "allocation":["asset_id","employee_id","condition_out"],
  "maintenance":["asset_id","maintenance_type","reported_at","description"]
 },
 "travel":{
  "request":["destination","purpose","start_date","end_date","estimated_cost"],
  "booking":["travel_record_id","booking_reference","provider","booked_cost"],
  "advance":["travel_record_id","requested_amount"],
  "claim":["travel_record_id","actual_cost"]
 },
 "exit":{
  "case":["reason","last_working_date"],
  "clearance":["exit_record_id","department","owner_employee_id"],
  "settlement":["exit_record_id","gross_due","deductions","net_due","payable_on"]
 },
 "analytics":{"report":["report_type","filters"]}
}

class RecordInput(BaseModel):
    record_type: str = Field(min_length=2,max_length=48)
    title: str = Field(min_length=2,max_length=200)
    employee_id: int | None = None
    parent_id: int | None = None
    effective_date: date | None = None
    due_date: date | None = None
    payload: dict = Field(default_factory=dict)

    @field_validator("record_type","title")
    @classmethod
    def clean_text(cls,v):
        v=v.strip()
        if not v: raise ValueError("Value cannot be blank")
        return v

class RecordUpdate(BaseModel):
    title: str | None = Field(default=None,min_length=2,max_length=200)
    employee_id: int | None = None
    parent_id: int | None = None
    effective_date: date | None = None
    due_date: date | None = None
    payload: dict | None = None
    expected_version: int = Field(ge=1)

class TransitionInput(BaseModel):
    status: str
    note: str | None = Field(default=None,max_length=2000)

def _role(request):
    return getattr(request.state,"role","")

def _validate(domain, record_type, payload):
    if domain not in DOMAINS: raise HTTPException(404,"Unknown HR domain")
    if record_type not in REQUIRED[domain]: raise HTTPException(422,"Unsupported record type for this HR domain")
    data=dict(payload)
    missing=[key for key in REQUIRED[domain][record_type] if data.get(key) in (None,"")]
    if missing: raise HTTPException(422,"Missing required fields: "+", ".join(missing))
    if domain=="recruitment" and record_type=="candidate":
        email=str(data["email"]).strip().lower()
        if "@" not in email or email.startswith("@") or email.endswith("@"): raise HTTPException(422,"Candidate email is invalid")
        data["email"]=email
    if domain=="travel" and record_type=="request":
        try:
            start=date.fromisoformat(str(data["start_date"]))
            end=date.fromisoformat(str(data["end_date"]))
            cost=Decimal(str(data["estimated_cost"]))
        except (ValueError,InvalidOperation): raise HTTPException(422,"Travel dates or estimated cost are invalid")
        if end<start or cost<=0: raise HTTPException(422,"Travel end date must follow start date and cost must be positive")
    if domain=="documents":
        digest=str(data.get("sha256",""))
        if len(digest)!=64 or any(ch not in "0123456789abcdef" for ch in digest.lower()):
            raise HTTPException(422,"Document SHA-256 checksum is invalid")
        if data.get("content_type") not in {"application/pdf","image/jpeg","image/png"}:
            raise HTTPException(422,"Only PDF, JPEG and PNG employee documents are supported")
    if domain=="exit" and record_type=="case":
        try: last=date.fromisoformat(str(data["last_working_date"]))
        except ValueError: raise HTTPException(422,"Last working date must be an ISO date")
        if last<date.today(): raise HTTPException(422,"Last working date cannot be in the past when initiating an exit case")
    if domain=="recruitment" and record_type=="interview":
        try:
            application_id=int(data["application_id"]); interviewer_id=int(data["interviewer_employee_id"])
            date.fromisoformat(str(data["scheduled_at"])[:10])
        except (ValueError,TypeError): raise HTTPException(422,"Interview IDs and scheduled date are invalid")
        if application_id<=0 or interviewer_id<=0: raise HTTPException(422,"Interview application and interviewer IDs must be positive")
    if domain=="recruitment" and record_type=="offer":
        try: salary=Decimal(str(data["offered_salary"])); expiry=date.fromisoformat(str(data["expires_on"])); application_id=int(data["application_id"])
        except (ValueError,InvalidOperation,TypeError): raise HTTPException(422,"Offer application, salary or expiry date is invalid")
        if application_id<=0 or salary<=0 or len(str(data["currency"]))!=3: raise HTTPException(422,"Offer application and salary must be positive and currency must be a 3-letter code")
        data["application_id"]=application_id; data["offered_salary"]=str(salary); data["currency"]=str(data["currency"]).upper(); data["expires_on"]=expiry.isoformat()
    if domain=="performance" and record_type=="review_cycle":
        try: start=date.fromisoformat(str(data["period_start"])); end=date.fromisoformat(str(data["period_end"]))
        except ValueError: raise HTTPException(422,"Performance cycle dates are invalid")
        if end<start: raise HTTPException(422,"Performance cycle end cannot precede start")
    if domain=="learning" and record_type=="assessment":
        try: score=Decimal(str(data["score"])); passing=Decimal(str(data["pass_score"])); enrollment_id=int(data["enrollment_id"])
        except (InvalidOperation,ValueError,TypeError): raise HTTPException(422,"Assessment enrollment and scores must be valid")
        if enrollment_id<=0 or score<0 or passing<0 or score>100 or passing>100: raise HTTPException(422,"Enrollment ID must be positive and scores must be between 0 and 100")
        data["enrollment_id"]=enrollment_id; data["score"]=str(score); data["pass_score"]=str(passing)
    if domain=="learning" and record_type=="certificate":
        try: enrollment_id=int(data["enrollment_id"]); valid_until=date.fromisoformat(str(data["valid_until"]))
        except (ValueError,TypeError): raise HTTPException(422,"Certificate enrollment ID or validity date is invalid")
        if enrollment_id<=0: raise HTTPException(422,"Certificate enrollment ID must be positive")
        data["enrollment_id"]=enrollment_id; data["valid_until"]=valid_until.isoformat()
    if domain=="assets" and record_type=="asset_request":
        try: needed_by=date.fromisoformat(str(data["needed_by"]))
        except ValueError: raise HTTPException(422,"Asset needed-by date is invalid")
        data["needed_by"]=needed_by.isoformat()
    if domain=="assets" and record_type=="maintenance":
        if int(data["asset_id"])<=0: raise HTTPException(422,"Asset ID must be positive")
        try: date.fromisoformat(str(data["reported_at"])[:10])
        except ValueError: raise HTTPException(422,"Maintenance reported_at date is invalid")
    if domain=="travel" and record_type in {"booking","advance","claim"}:
        amount_key={"booking":"booked_cost","advance":"requested_amount","claim":"actual_cost"}[record_type]
        try: amount=Decimal(str(data[amount_key]))
        except InvalidOperation: raise HTTPException(422,"Travel amount must be numeric")
        if amount<=0: raise HTTPException(422,"Travel amount must be greater than zero")
        data[amount_key]=str(amount)
    if domain=="exit" and record_type=="settlement":
        try: gross=Decimal(str(data["gross_due"])); deductions=Decimal(str(data["deductions"])); net=Decimal(str(data["net_due"])); payable=date.fromisoformat(str(data["payable_on"]))
        except (ValueError,InvalidOperation): raise HTTPException(422,"Exit settlement amounts or payable date are invalid")
        if min(gross,deductions,net)<0 or gross-deductions!=net: raise HTTPException(422,"Exit settlement net due must equal gross due less deductions")
        data.update({"gross_due":str(gross),"deductions":str(deductions),"net_due":str(net),"payable_on":payable.isoformat()})
    return data

def _visible_employee(conn,request,employee_id):
    if _role(request) in MANAGER_ROLES: return
    own=_employee(conn,_actor(request))
    if employee_id is not None and int(own["id"])!=int(employee_id):
        raise HTTPException(403,"Employees may access only their own HR records")


@router.post("/documents/upload",status_code=201)
async def upload_document(
    request:Request,
    file:UploadFile=File(...),
    document_type:str=Form(...),
    employee_id:int|None=Form(default=None),
    expiry_date:date|None=Form(default=None),
):
    actor=_actor(request)
    manager=_role(request) in MANAGER_ROLES
    try:
        with _hr_connection() as conn:
            if not manager:
                own=_employee(conn,actor)
                if employee_id is not None and employee_id!=own["id"]:
                    raise HTTPException(403,"Employees may upload documents only to their own profile")
                employee_id=own["id"]
            if employee_id is None or not conn.execute("SELECT id FROM hr_employees WHERE id=%s",(employee_id,)).fetchone():
                raise HTTPException(404,"Employee not found")
        content=await file.read(10*1024*1024+1)
        stored=upload_employee_document(employee_id=employee_id,uploader_id=actor,
            document_type=document_type,file_name=file.filename or "document",
            content_type=file.content_type or "",content=content)
        payload={**stored,"record_type":"employee_document"}
        with _hr_connection() as conn:
            with conn.transaction():
                row=conn.execute(
                  "INSERT INTO hr_enterprise_records(domain,employee_id,title,status,payload,due_date,created_by_user_id,updated_by_user_id) "
                  "VALUES('documents',%s,%s,'pending',%s::jsonb,%s,%s,%s) RETURNING *",
                  (employee_id,stored["file_name"],json.dumps({**payload,"expiry_date":expiry_date.isoformat() if expiry_date else None}),expiry_date,actor,actor)
                ).fetchone()
                conn.execute("INSERT INTO hr_enterprise_events(record_id,event_type,to_status,after_state,actor_user_id) "
                  "VALUES(%s,'document_uploaded','pending',%s::jsonb,%s)",
                  (row["id"],json.dumps(dict(row),default=str),actor))
        return row
    except HTTPException: raise
    except EmployeeDocumentConfigurationError as exc: raise HTTPException(503,str(exc)) from exc
    except EmployeeDocumentError as exc: raise HTTPException(422,str(exc)) from exc
    except psycopg.Error as exc: raise _db_error(exc) from exc
    finally:
        await file.close()

@router.post("/documents/{record_id}/download")
def download_document(record_id:int,request:Request):
    actor=_actor(request)
    try:
        with _hr_connection() as conn:
            row=conn.execute("SELECT * FROM hr_enterprise_records WHERE id=%s AND domain='documents'",(record_id,)).fetchone()
            if not row: raise HTTPException(404,"Employee document not found")
            if _role(request) not in MANAGER_ROLES:
                own=_employee(conn,actor)
                if own["id"]!=row["employee_id"]: raise HTTPException(403,"Employees may download only their own documents")
            if row["status"] not in {"uploaded","under_review","verified"}:
                raise HTTPException(409,"This document is not available for download")
            url=employee_document_download_url(employee_id=row["employee_id"],object_key=row["payload"]["object_key"])
            conn.execute("INSERT INTO hr_enterprise_events(record_id,event_type,actor_user_id) VALUES(%s,'download_link_issued',%s)",(record_id,actor))
        return {"url":url,"expires_in_seconds":300}
    except HTTPException: raise
    except EmployeeDocumentConfigurationError as exc: raise HTTPException(503,str(exc)) from exc
    except EmployeeDocumentError as exc: raise HTTPException(422,str(exc)) from exc
    except psycopg.Error as exc: raise _db_error(exc) from exc

@router.get("/{domain}")
def list_records(domain:str,request:Request,status:str|None=None,employee_id:int|None=None,record_type:str|None=None,limit:int=Query(100,ge=1,le=500)):
    if domain not in DOMAINS: raise HTTPException(404,"Unknown HR domain")
    try:
        with _hr_connection() as conn:
            _visible_employee(conn,request,employee_id)
            if _role(request) not in MANAGER_ROLES:
                own=_employee(conn,_actor(request)); employee_id=own["id"]
                if domain not in EMPLOYEE_DOMAINS: raise HTTPException(403,"This HR domain is manager-only")
            rows=conn.execute(
              "SELECT r.*,u.email AS creator_email FROM hr_enterprise_records r "
              "LEFT JOIN app_users u ON u.id=r.created_by_user_id WHERE r.domain=%s "
              "AND (%s IS NULL OR r.status=%s) AND (%s IS NULL OR r.employee_id=%s) "
              "AND (%s IS NULL OR r.payload->>'record_type'=%s) "
              "ORDER BY r.updated_at DESC,r.id DESC LIMIT %s",
              (domain,status,status,employee_id,employee_id,record_type,record_type,limit)
            ).fetchall()
        return {"items":rows}
    except HTTPException: raise
    except psycopg.Error as exc: raise _db_error(exc) from exc

@router.post("/{domain}",status_code=201)
def create_record(domain:str,payload:RecordInput,request:Request):
    if domain not in DOMAINS: raise HTTPException(404,"Unknown HR domain")
    if domain=="documents":
        raise HTTPException(422,"Employee documents must be uploaded through the private document upload endpoint")
    if record_type := payload.record_type:
        if record_type in MANAGER_ONLY_TYPES.get(domain,set()) and _role(request) not in MANAGER_ROLES:
            raise HTTPException(403,"This HR record type requires HR manager permission")
    actor=_manager(request) if domain in {"recruitment","analytics"} or _role(request) in MANAGER_ROLES else _actor(request)
    try:
        with _hr_connection() as conn:
            with conn.transaction():
                employee_id=payload.employee_id
                if _role(request) not in MANAGER_ROLES:
                    own=_employee(conn,actor); employee_id=own["id"]
                if employee_id is not None and not conn.execute("SELECT id FROM hr_employees WHERE id=%s",(employee_id,)).fetchone():
                    raise HTTPException(404,"Employee not found")
                if payload.parent_id is not None and not conn.execute("SELECT id FROM hr_enterprise_records WHERE id=%s AND domain=%s",(payload.parent_id,domain)).fetchone():
                    raise HTTPException(422,"Parent record must belong to the same HR domain")
                data=_validate(domain,payload.record_type,payload.payload)
                data["record_type"]=payload.record_type
                status=_initial_status(domain,payload.record_type)
                row=conn.execute(
                  "INSERT INTO hr_enterprise_records(domain,employee_id,parent_id,title,status,payload,effective_date,due_date,created_by_user_id,updated_by_user_id) "
                  "VALUES(%s,%s,%s,%s,%s,%s::jsonb,%s,%s,%s,%s) RETURNING *",
                  (domain,employee_id,payload.parent_id,payload.title,status,json.dumps(data,default=str),payload.effective_date,payload.due_date,actor,actor)
                ).fetchone()
                conn.execute("INSERT INTO hr_enterprise_events(record_id,event_type,to_status,after_state,actor_user_id) VALUES(%s,'created',%s,%s::jsonb,%s)",
                  (row["id"],status,json.dumps(dict(row),default=str),actor))
        return row
    except HTTPException: raise
    except psycopg.Error as exc: raise _db_error(exc) from exc

@router.get("/{domain}/{record_id}")
def get_record(domain:str,record_id:int,request:Request):
    if domain not in DOMAINS: raise HTTPException(404,"Unknown HR domain")
    try:
        with _hr_connection() as conn:
            row=conn.execute("SELECT * FROM hr_enterprise_records WHERE id=%s AND domain=%s",(record_id,domain)).fetchone()
            if not row: raise HTTPException(404,"HR record not found")
            _visible_employee(conn,request,row["employee_id"])
            if _role(request) not in MANAGER_ROLES and domain not in EMPLOYEE_DOMAINS: raise HTTPException(403,"This HR domain is manager-only")
            return row
    except HTTPException: raise
    except psycopg.Error as exc: raise _db_error(exc) from exc

@router.patch("/{domain}/{record_id}")
def update_record(domain:str,record_id:int,payload:RecordUpdate,request:Request):
    actor=_manager(request)
    try:
        with _hr_connection() as conn:
            with conn.transaction():
                old=conn.execute("SELECT * FROM hr_enterprise_records WHERE id=%s AND domain=%s FOR UPDATE",(record_id,domain)).fetchone()
                if not old: raise HTTPException(404,"HR record not found")
                if old["version"]!=payload.expected_version: raise HTTPException(409,"Record changed since it was loaded; refresh before editing")
                data=dict(old["payload"])
                if payload.payload is not None:
                    record_type=data.get("record_type")
                    data=_validate(domain,record_type,payload.payload); data["record_type"]=record_type
                row=conn.execute(
                  "UPDATE hr_enterprise_records SET title=COALESCE(%s,title),employee_id=%s,parent_id=%s,effective_date=%s,due_date=%s,payload=%s::jsonb,version=version+1,updated_by_user_id=%s,updated_at=now() "
                  "WHERE id=%s RETURNING *",
                  (payload.title,payload.employee_id if payload.employee_id is not None else old["employee_id"],payload.parent_id if payload.parent_id is not None else old["parent_id"],payload.effective_date if payload.effective_date is not None else old["effective_date"],payload.due_date if payload.due_date is not None else old["due_date"],json.dumps(data,default=str),actor,record_id)
                ).fetchone()
                conn.execute("INSERT INTO hr_enterprise_events(record_id,event_type,before_state,after_state,actor_user_id) VALUES(%s,'updated',%s::jsonb,%s::jsonb,%s)",
                  (record_id,json.dumps(dict(old),default=str),json.dumps(dict(row),default=str),actor))
        return row
    except HTTPException: raise
    except psycopg.Error as exc: raise _db_error(exc) from exc

@router.post("/{domain}/{record_id}/transition")
def transition_record(domain:str,record_id:int,payload:TransitionInput,request:Request):
    if domain not in DOMAINS: raise HTTPException(404,"Unknown HR domain")
    if payload.status not in STATUSES[domain]: raise HTTPException(422,"Invalid status for this HR domain")
    actor=_actor(request)
    manager=_role(request) in MANAGER_ROLES
    try:
        with _hr_connection() as conn:
            with conn.transaction():
                old=conn.execute("SELECT * FROM hr_enterprise_records WHERE id=%s AND domain=%s FOR UPDATE",(record_id,domain)).fetchone()
                if not old: raise HTTPException(404,"HR record not found")
                if not manager:
                    own=_employee(conn,actor)
                    if old["employee_id"] is None or int(old["employee_id"])!=int(own["id"]):
                        raise HTTPException(403,"Employees may change only their own HR records")
                    if not _employee_transition_allowed(domain,old["status"],payload.status):
                        raise HTTPException(403,"This workflow action requires HR manager permission")
                if payload.status not in TRANSITIONS[domain].get(old["status"],set()):
                    raise HTTPException(409,f"Transition from {old['status']} to {payload.status} is not allowed")
                row=conn.execute("UPDATE hr_enterprise_records SET status=%s,version=version+1,updated_by_user_id=%s,updated_at=now() WHERE id=%s RETURNING *",
                  (payload.status,actor,record_id)).fetchone()
                conn.execute("INSERT INTO hr_enterprise_events(record_id,event_type,from_status,to_status,before_state,after_state,note,actor_user_id) "
                  "VALUES(%s,'status_transition',%s,%s,%s::jsonb,%s::jsonb,%s,%s)",
                  (record_id,old["status"],payload.status,json.dumps(dict(old),default=str),json.dumps(dict(row),default=str),payload.note,actor))
        return row
    except HTTPException: raise
    except psycopg.Error as exc: raise _db_error(exc) from exc

@router.get("/{domain}/{record_id}/events")
def record_events(domain:str,record_id:int,request:Request):
    _manager(request)
    if domain not in DOMAINS: raise HTTPException(404,"Unknown HR domain")
    try:
        with _hr_connection() as conn:
            if not conn.execute("SELECT id FROM hr_enterprise_records WHERE id=%s AND domain=%s",(record_id,domain)).fetchone():
                raise HTTPException(404,"HR record not found")
            return {"items":conn.execute("SELECT * FROM hr_enterprise_events WHERE record_id=%s ORDER BY created_at DESC,id DESC LIMIT 200",(record_id,)).fetchall()}
    except HTTPException: raise
    except psycopg.Error as exc: raise _db_error(exc) from exc

@router.post("/{domain}/{record_id}/archive")
def archive_record(domain:str,record_id:int,request:Request):
    actor=_manager(request)
    if domain not in DOMAINS: raise HTTPException(404,"Unknown HR domain")
    try:
        with _hr_connection() as conn:
            with conn.transaction():
                old=conn.execute("SELECT * FROM hr_enterprise_records WHERE id=%s AND domain=%s FOR UPDATE",(record_id,domain)).fetchone()
                if not old: raise HTTPException(404,"HR record not found")
                if old["status"]=="archived": return old
                row=conn.execute("UPDATE hr_enterprise_records SET status='archived',version=version+1,updated_by_user_id=%s,updated_at=now() WHERE id=%s RETURNING *",(actor,record_id)).fetchone()
                conn.execute("INSERT INTO hr_enterprise_events(record_id,event_type,from_status,to_status,before_state,after_state,actor_user_id) VALUES(%s,'archived',%s,'archived',%s::jsonb,%s::jsonb,%s)",
                  (old["status"],json.dumps(dict(old),default=str),json.dumps(dict(row),default=str),actor))
        return row
    except HTTPException: raise
    except psycopg.Error as exc: raise _db_error(exc) from exc
