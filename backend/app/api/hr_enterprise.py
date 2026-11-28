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
from app.api.hr import _actor, _manager, _employee, _hr_connection, _db_error\nfrom app.services.hr_employee_documents import (\n    EmployeeDocumentConfigurationError, EmployeeDocumentError,\n    upload_employee_document, employee_document_download_url,\n)

router = APIRouter(prefix="/hr/enterprise", tags=["hr-enterprise"])

DOMAINS = {"recruitment","documents","performance","learning","assets","travel","exit","analytics"}
MANAGER_ROLES = {"super_admin","owner","admin","manager"}
EMPLOYEE_DOMAINS = {"documents","performance","learning","assets","travel","exit"}
STATUSES = {
 "recruitment":{"draft","open","screening","shortlisted","interview","offered","hired","rejected","withdrawn","archived"},
 "documents":{"pending","uploaded","under_review","verified","rejected","expired","archived"},
 "performance":{"draft","active","self_review","manager_review","calibration","acknowledged","closed","cancelled"},
 "learning":{"planned","enrolled","in_progress","completed","failed","cancelled"},
 "assets":{"requested","approved","assigned","returned","maintenance","written_off","rejected"},
 "travel":{"draft","submitted","approved","rejected","booked","in_progress","completed","claimed","reimbursed","cancelled"},
 "exit":{"initiated","notice_period","handover","clearance","settlement_review","completed","withdrawn"},
 "analytics":{"saved","scheduled","archived"}
}
TRANSITIONS = {
 "recruitment":{"draft":{"open","archived"},"open":{"screening","archived"},"screening":{"shortlisted","rejected","withdrawn"},"shortlisted":{"interview","rejected","withdrawn"},"interview":{"offered","rejected","withdrawn"},"offered":{"hired","rejected","withdrawn"}},
 "documents":{"pending":{"uploaded","archived"},"uploaded":{"under_review","rejected"},"under_review":{"verified","rejected","expired"},"verified":{"expired","archived"},"rejected":{"uploaded","archived"},"expired":{"uploaded","archived"}},
 "performance":{"draft":{"active","cancelled"},"active":{"self_review","cancelled"},"self_review":{"manager_review"},"manager_review":{"calibration","acknowledged"},"calibration":{"acknowledged"},"acknowledged":{"closed"}},
 "learning":{"planned":{"enrolled","cancelled"},"enrolled":{"in_progress","cancelled"},"in_progress":{"completed","failed"},"failed":{"enrolled"}},
 "assets":{"requested":{"approved","rejected"},"approved":{"assigned","rejected"},"assigned":{"returned","maintenance","written_off"},"maintenance":{"assigned","written_off"},"returned":{"maintenance","written_off"}},
 "travel":{"draft":{"submitted","cancelled"},"submitted":{"approved","rejected"},"approved":{"booked","cancelled"},"booked":{"in_progress","cancelled"},"in_progress":{"completed"},"completed":{"claimed"},"claimed":{"reimbursed"}},
 "exit":{"initiated":{"notice_period","withdrawn"},"notice_period":{"handover","withdrawn"},"handover":{"clearance"},"clearance":{"settlement_review"},"settlement_review":{"completed"}},
 "analytics":{"saved":{"scheduled","archived"},"scheduled":{"saved","archived"}}
}
MANAGER_ONLY_TYPES = {"recruitment":{"job_opening","candidate","application"},"assets":{"asset","allocation"},"analytics":{"report"}}
REQUIRED = {
 "recruitment":{"job_opening":["department","employment_type","location"],"candidate":["email"],"application":["candidate_id","job_id"]},
 "documents":{"employee_document":["document_type","file_name","object_key","content_type","sha256"]},
 "performance":{"review":["cycle","reviewer_employee_id"],"goal":["description","measure","target"]},
 "learning":{"course":["provider","course_type"],"enrollment":["course_id"]},
 "assets":{"asset":["asset_type","asset_tag"],"allocation":["asset_id","employee_id","condition_out"]},
 "travel":{"request":["destination","purpose","start_date","end_date","estimated_cost"],"claim":["travel_record_id","actual_cost"]},
 "exit":{"case":["reason","last_working_date"]},
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
        last=date.fromisoformat(str(data["last_working_date"]))
        if last<date.today(): raise HTTPException(422,"Last working date cannot be in the past when initiating an exit case")
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
                  "INSERT INTO hr_enterprise_records(domain,employee_id,title,status,payload,created_by_user_id,updated_by_user_id) "
                  "VALUES('documents',%s,%s,'uploaded',%s::jsonb,%s,%s) RETURNING *",
                  (employee_id,stored["file_name"],json.dumps(payload),actor,actor)
                ).fetchone()
                conn.execute("INSERT INTO hr_enterprise_events(record_id,event_type,to_status,after_state,actor_user_id) "
                  "VALUES(%s,'document_uploaded','uploaded',%s::jsonb,%s)",
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
                status="draft" if domain in {"recruitment","performance","travel","analytics"} else ("pending" if domain=="documents" else ("requested" if domain=="assets" else ("planned" if domain=="learning" else "initiated")))
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
    actor=_manager(request)
    if domain not in DOMAINS: raise HTTPException(404,"Unknown HR domain")
    if payload.status not in STATUSES[domain]: raise HTTPException(422,"Invalid status for this HR domain")
    try:
        with _hr_connection() as conn:
            with conn.transaction():
                old=conn.execute("SELECT * FROM hr_enterprise_records WHERE id=%s AND domain=%s FOR UPDATE",(record_id,domain)).fetchone()
                if not old: raise HTTPException(404,"HR record not found")
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
