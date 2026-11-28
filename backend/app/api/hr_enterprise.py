"""Integrated HR enterprise workflows.

All eight HR domains share audited, versioned records while retaining explicit
domain validation and controlled state transitions. Employee self-service is
bound to the authenticated user's linked employee record.
"""
from datetime import date, timedelta
from decimal import Decimal, InvalidOperation
import json

import psycopg
from fastapi import APIRouter, File, Form, HTTPException, Query, Request, UploadFile
from pydantic import BaseModel, Field, field_validator
from app.api.hr import EmployeeInput, _actor, _manager, _employee, _hr_connection, _db_error, _link_employee_login_identity
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
 "assets":{"available","requested","approved","assigned","acknowledged","returned","maintenance","written_off","rejected"},
 "travel":{"draft","submitted","approved","rejected","booked","in_progress","completed","claimed","reimbursed","cancelled"},
 "exit":{"initiated","notice_period","handover","clearance","settlement_review","completed","withdrawn"},
 "analytics":{"saved","scheduled","archived"}
}
TRANSITIONS = {
 "recruitment":{"draft":{"open","archived"},"open":{"screening","archived"},"screening":{"shortlisted","rejected","withdrawn"},"shortlisted":{"interview","rejected","withdrawn"},"interview":{"offered","rejected","withdrawn"},"offered":{"rejected","withdrawn"}},
 "documents":{"pending":{"uploaded","archived"},"uploaded":{"under_review","rejected"},"under_review":{"verified","rejected","expired"},"verified":{"expired","archived"},"rejected":{"uploaded","archived"},"expired":{"uploaded","archived"}},
 "performance":{"draft":{"active","cancelled"},"active":{"self_review","cancelled"},"self_review":{"manager_review"},"manager_review":{"calibration","acknowledged"},"calibration":{"acknowledged"},"acknowledged":{"closed"}},
 "learning":{"planned":{"enrolled","cancelled"},"enrolled":{"in_progress","cancelled"},"in_progress":{"completed","failed"},"failed":{"enrolled"}},
 "assets":{"available":{"assigned","maintenance","written_off"},"requested":{"approved","rejected"},"approved":{"assigned","rejected"},"assigned":{"acknowledged","returned","maintenance","written_off"},"acknowledged":{"returned","maintenance","written_off"},"maintenance":{"assigned","written_off"},"returned":{"available","maintenance","written_off"}},
 "travel":{"draft":{"submitted","cancelled"},"submitted":{"approved","rejected"},"approved":{"booked","cancelled"},"booked":{"in_progress","cancelled"},"in_progress":{"completed"},"completed":{"claimed"},"claimed":{"reimbursed"}},
 "exit":{"initiated":{"notice_period","withdrawn"},"notice_period":{"handover","withdrawn"},"handover":{"clearance"},"clearance":{"settlement_review"},"settlement_review":{"completed"}},
 "analytics":{"saved":{"scheduled","archived"},"scheduled":{"saved","archived"}}
}
MANAGER_ONLY_TYPES = {
 "recruitment":{"job_opening","candidate","application","interview","offer"},
 "assets":{"asset","allocation","maintenance"},
 "performance":{"review_template","review_cycle","review","calibration"},
 "learning":{"course","assessment","certificate"},
 "travel":{"travel_policy","booking","advance"},
 "exit":{"clearance","settlement"},
 "analytics":{"report"}
}
EMPLOYEE_TRANSITIONS = {
    ("travel", "draft", "submitted"),
    ("travel", "draft", "cancelled"),
    ("performance", "active", "self_review"),
    ("learning", "enrolled", "in_progress"),
    ("learning", "in_progress", "completed"),
    ("assets", "assigned", "acknowledged"),
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
        ("performance", "self_review"): "self_review",
        ("performance", "review"): "manager_review",
        ("performance", "calibration"): "calibration",
        ("performance", "acknowledgement"): "acknowledged",
        ("learning", "assessment"): "completed",
        ("learning", "certificate"): "completed",
        ("learning", "progress"): "in_progress",
        ("assets", "maintenance"): "maintenance",
        ("travel", "travel_policy"): "approved",
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
  "review_template":["name","sections","rating_scale"],
  "review_cycle":["period_start","period_end"],
  "review":["cycle_id","reviewer_employee_id","template_id"],
  "self_review":["cycle_id","summary","rating","achievements","development_areas"],
  "goal":["description","measure","target"],
  "feedback":["review_id","feedback"],
  "calibration":["review_id","calibrated_rating","rationale"],
  "acknowledgement":["review_id","acknowledgement"]
 },
 "learning":{
  "course":["provider","course_type"],
  "enrollment":["course_id"],
  "progress":["enrollment_id","progress_percent"],
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
  "travel_policy":["name","employment_type","max_trip_cost","per_diem_limit","currency"],
  "request":["destination","purpose","start_date","end_date","estimated_cost","estimated_per_diem","policy_id"],
  "booking":["travel_record_id","booking_reference","provider","booked_cost"],
  "advance":["travel_record_id","requested_amount"],
  "claim":["travel_record_id","actual_cost","receipt_reference"]
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
    expected_version: int | None = Field(default=None,ge=1)

class RecruitmentHireInput(BaseModel):
    application_id: int = Field(gt=0)
    candidate_accepted: bool
    acceptance_reference: str | None = Field(default=None,max_length=500)
    employee: EmployeeInput

def _role(request):
    return getattr(request.state,"role","")

def _validate_references(conn, domain, record_type, data):
    references = {
        ("recruitment","application"): {
            "candidate_id": ("recruitment","candidate"),
            "job_id": ("recruitment","job_opening"),
        },
        ("recruitment","interview"): {"application_id": ("recruitment","application")},
        ("recruitment","offer"): {"application_id": ("recruitment","application")},
        ("performance","review"): {"template_id": ("performance","review_template"),"cycle_id": ("performance","review_cycle")},
        ("performance","self_review"): {"cycle_id": ("performance","review_cycle")},
        ("performance","feedback"): {"review_id": ("performance","review")},
        ("performance","calibration"): {"review_id": ("performance","review")},
        ("performance","acknowledgement"): {"review_id": ("performance","review")},
        ("learning","enrollment"): {"course_id": ("learning","course")},
        ("learning","progress"): {"enrollment_id": ("learning","enrollment")},
        ("learning","assessment"): {"enrollment_id": ("learning","enrollment")},
        ("learning","certificate"): {"enrollment_id": ("learning","enrollment")},
        ("assets","allocation"): {"asset_id": ("assets","asset")},
        ("assets","maintenance"): {"asset_id": ("assets","asset")},
        ("travel","request"): {"policy_id": ("travel","travel_policy")},
        ("travel","booking"): {"travel_record_id": ("travel","request")},
        ("travel","advance"): {"travel_record_id": ("travel","request")},
        ("travel","claim"): {"travel_record_id": ("travel","request")},
        ("exit","clearance"): {"exit_record_id": ("exit","case")},
        ("exit","settlement"): {"exit_record_id": ("exit","case")},
    }
    for field, (target_domain, target_type) in references.get((domain,record_type), {}).items():
        try: target_id=int(data[field])
        except (ValueError,TypeError): raise HTTPException(422,f"{field} must be a valid record ID")
        if target_id<=0 or not conn.execute(
            "SELECT id FROM hr_enterprise_records WHERE id=%s AND domain=%s AND payload->>'record_type'=%s",
            (target_id,target_domain,target_type),
        ).fetchone():
            raise HTTPException(422,f"{field} must reference an existing {target_type.replace('_',' ')} record")
        data[field]=target_id
    employee_fields = {
        "interviewer_employee_id", "reviewer_employee_id", "owner_employee_id", "employee_id"
    }
    for field in employee_fields:
        if field in data and data[field] not in (None,""):
            try: employee_id=int(data[field])
            except (ValueError,TypeError): raise HTTPException(422,f"{field} must be a valid employee ID")
            if employee_id<=0 or not conn.execute("SELECT id FROM hr_employees WHERE id=%s",(employee_id,)).fetchone():
                raise HTTPException(422,f"{field} must reference an existing employee")
            data[field]=employee_id
    if domain=="recruitment" and record_type=="application":
        job=conn.execute("SELECT status FROM hr_enterprise_records WHERE id=%s",(data["job_id"],)).fetchone()
        if job["status"]!="open":
            raise HTTPException(409,"Applications can be created only for open job openings")
    if domain=="recruitment" and record_type in {"interview","offer"}:
        application=conn.execute("SELECT status FROM hr_enterprise_records WHERE id=%s",(data["application_id"],)).fetchone()
        allowed={"interview":{"shortlisted","interview"},"offer":{"interview"}}
        if application["status"] not in allowed[record_type]:
            raise HTTPException(409,"The application must reach the required recruitment stage first")
    if domain=="performance" and record_type=="self_review":
        cycle=conn.execute("SELECT status FROM hr_enterprise_records WHERE id=%s",(data["cycle_id"],)).fetchone()
        if cycle["status"]!="self_review":
            raise HTTPException(409,"The review cycle must be open for employee self-review")
    if domain=="performance" and record_type=="review":
        cycle=conn.execute("SELECT status FROM hr_enterprise_records WHERE id=%s",(data["cycle_id"],)).fetchone()
        if cycle["status"] not in {"manager_review","calibration"}:
            raise HTTPException(409,"The review cycle must reach manager review before appraisals are created")
    if domain=="performance" and record_type=="calibration":
        review=conn.execute("SELECT status FROM hr_enterprise_records WHERE id=%s",(data["review_id"],)).fetchone()
        if review["status"]!="calibration":
            raise HTTPException(409,"A review must enter calibration before a calibration record can be added")
    if domain=="performance" and record_type=="acknowledgement":
        review=conn.execute("SELECT status FROM hr_enterprise_records WHERE id=%s",(data["review_id"],)).fetchone()
        if review["status"] not in {"acknowledged","closed"}:
            raise HTTPException(409,"Employees can acknowledge only a manager-finalized review")
    if domain=="performance" and record_type=="feedback":
        review=conn.execute("SELECT status FROM hr_enterprise_records WHERE id=%s",(data["review_id"],)).fetchone()
        if review["status"] not in {"manager_review","calibration","acknowledged","closed"}:
            raise HTTPException(409,"Feedback can be added only after manager review begins")
    if domain=="learning" and record_type=="enrollment":
        course=conn.execute("SELECT status FROM hr_enterprise_records WHERE id=%s",(data["course_id"],)).fetchone()
        if course["status"]!="enrolled":
            raise HTTPException(409,"The course must be published for enrollment before employees can enroll")
    if domain=="learning" and record_type=="progress":
        enrollment=conn.execute("SELECT status,employee_id FROM hr_enterprise_records WHERE id=%s",(data["enrollment_id"],)).fetchone()
        if enrollment["status"]!="in_progress":
            raise HTTPException(409,"Progress evidence can be recorded only for an in-progress enrollment")
    if domain=="learning" and record_type=="assessment":
        enrollment=conn.execute("SELECT status FROM hr_enterprise_records WHERE id=%s",(data["enrollment_id"],)).fetchone()
        if enrollment["status"] not in {"in_progress","completed"}:
            raise HTTPException(409,"The enrollment must be in progress before assessment")
    if domain=="learning" and record_type=="certificate":
        enrollment=conn.execute("SELECT status FROM hr_enterprise_records WHERE id=%s",(data["enrollment_id"],)).fetchone()
        passed=conn.execute(
            "SELECT EXISTS(SELECT 1 FROM hr_enterprise_records WHERE domain='learning' "
            "AND payload->>'record_type'='assessment' AND payload->>'enrollment_id'=%s "
            "AND (payload->>'score')::numeric >= (payload->>'pass_score')::numeric) AS passed",
            (str(data["enrollment_id"]),),
        ).fetchone()["passed"]
        if enrollment["status"]!="completed" or not passed:
            raise HTTPException(409,"A certificate requires a completed enrollment and a passing assessment")
    if domain=="assets" and record_type=="allocation":
        asset=conn.execute("SELECT status FROM hr_enterprise_records WHERE id=%s",(data["asset_id"],)).fetchone()
        if asset["status"] not in {"available","approved"}:
            raise HTTPException(409,"Only available or approved assets can be allocated")
    if domain=="travel" and record_type=="request":
        policy=conn.execute("SELECT status,payload FROM hr_enterprise_records WHERE id=%s",(data["policy_id"],)).fetchone()
        if policy["status"]!="approved":
            raise HTTPException(409,"The selected travel policy is not active")
        days=(date.fromisoformat(str(data["end_date"]))-date.fromisoformat(str(data["start_date"]))).days+1
        if Decimal(data["estimated_cost"])>Decimal(policy["payload"]["max_trip_cost"]):
            raise HTTPException(422,"Estimated trip cost exceeds the selected travel policy limit")
        if Decimal(data["estimated_per_diem"])>Decimal(policy["payload"]["per_diem_limit"])*days:
            raise HTTPException(422,"Estimated per diem exceeds the selected travel policy limit")
    if domain=="travel" and record_type in {"booking","advance"}:
        travel=conn.execute("SELECT status FROM hr_enterprise_records WHERE id=%s",(data["travel_record_id"],)).fetchone()
        if travel["status"] not in {"approved","booked","in_progress"}:
            raise HTTPException(409,"Travel must be approved before booking or advance processing")
    if domain=="travel" and record_type=="claim":
        travel=conn.execute("SELECT status FROM hr_enterprise_records WHERE id=%s",(data["travel_record_id"],)).fetchone()
        if travel["status"]!="completed":
            raise HTTPException(409,"Travel must be completed before a claim can be submitted")
    if domain=="exit" and record_type=="clearance":
        exit_case=conn.execute("SELECT status FROM hr_enterprise_records WHERE id=%s",(data["exit_record_id"],)).fetchone()
        if exit_case["status"]!="clearance":
            raise HTTPException(409,"Department clearances can be created only during the exit clearance stage")
    if domain=="exit" and record_type=="settlement":
        exit_case=conn.execute("SELECT status FROM hr_enterprise_records WHERE id=%s",(data["exit_record_id"],)).fetchone()
        if exit_case["status"]!="settlement_review":
            raise HTTPException(409,"Exit clearance must reach settlement review before settlement creation")


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
    if domain=="travel" and record_type=="travel_policy":
        try: trip_cap=Decimal(str(data["max_trip_cost"])); per_diem=Decimal(str(data["per_diem_limit"]))
        except InvalidOperation: raise HTTPException(422,"Travel policy limits must be numeric")
        if trip_cap<=0 or per_diem<=0: raise HTTPException(422,"Travel policy limits must be greater than zero")
        if data["employment_type"] not in {"all","full_time","part_time","contract","intern","shift_worker"}:
            raise HTTPException(422,"Travel policy employment type is invalid")
        if len(str(data["currency"]))!=3: raise HTTPException(422,"Travel policy currency must be a 3-letter code")
        data["max_trip_cost"]=str(trip_cap);data["per_diem_limit"]=str(per_diem);data["currency"]=str(data["currency"]).upper()
    if domain=="travel" and record_type=="request":
        try:
            start=date.fromisoformat(str(data["start_date"]))
            end=date.fromisoformat(str(data["end_date"]))
            cost=Decimal(str(data["estimated_cost"]))
            per_diem=Decimal(str(data["estimated_per_diem"]))
            policy_id=int(data["policy_id"])
        except (ValueError,InvalidOperation,TypeError): raise HTTPException(422,"Travel dates, policy ID or estimated costs are invalid")
        if end<start or cost<=0 or per_diem<0 or policy_id<=0: raise HTTPException(422,"Travel dates and cost values are invalid")
        data["estimated_cost"]=str(cost);data["estimated_per_diem"]=str(per_diem);data["policy_id"]=policy_id
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
    if domain=="performance" and record_type=="self_review":
        try: rating=Decimal(str(data["rating"]))
        except InvalidOperation: raise HTTPException(422,"Self-review rating must be numeric")
        if rating<1 or rating>5: raise HTTPException(422,"Self-review rating must be between 1 and 5")
        data["rating"]=str(rating)
    if domain=="performance" and record_type=="goal" and data.get("weight") not in (None,""):
        try: weight=Decimal(str(data["weight"]))
        except InvalidOperation: raise HTTPException(422,"Goal weight must be numeric")
        if weight<=0 or weight>100: raise HTTPException(422,"Goal weight must be greater than zero and no more than 100")
        data["weight"]=str(weight)
    if domain=="performance" and record_type=="review_template":
        try: sections=json.loads(data["sections"]) if isinstance(data["sections"],str) else data["sections"]
        except (ValueError,TypeError): raise HTTPException(422,"Review template sections must be valid JSON")
        if not isinstance(sections,list) or not sections:
            raise HTTPException(422,"Review template must contain at least one section")
        try: scale=int(data["rating_scale"])
        except (ValueError,TypeError): raise HTTPException(422,"Rating scale must be an integer")
        if scale<2 or scale>10: raise HTTPException(422,"Rating scale must be between 2 and 10")
        data["sections"]=sections; data["rating_scale"]=scale
    if domain=="performance" and record_type=="calibration":
        try: rating=Decimal(str(data["calibrated_rating"]))
        except InvalidOperation: raise HTTPException(422,"Calibrated rating must be numeric")
        if rating<1 or rating>5: raise HTTPException(422,"Calibrated rating must be between 1 and 5")
        data["calibrated_rating"]=str(rating)
    if domain=="performance" and record_type=="acknowledgement":
        accepted=str(data["acknowledgement"]).strip().lower()
        if accepted not in {"true","false"}: raise HTTPException(422,"Acknowledgement must be true or false")
        data["acknowledgement"]=accepted=="true"
    if domain=="learning" and record_type=="progress":
        try: progress=Decimal(str(data["progress_percent"]))
        except InvalidOperation: raise HTTPException(422,"Course progress must be numeric")
        if progress<0 or progress>100: raise HTTPException(422,"Course progress must be between 0 and 100")
        data["progress_percent"]=str(progress)
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
    if domain=="assets" and record_type=="asset":
        if data.get("purchase_value") not in (None,""):
            try: purchase_value=Decimal(str(data["purchase_value"]))
            except InvalidOperation: raise HTTPException(422,"Asset purchase value must be numeric")
            if purchase_value<0: raise HTTPException(422,"Asset purchase value cannot be negative")
            data["purchase_value"]=str(purchase_value)
        for field in ("purchase_date","warranty_expiry"):
            if data.get(field):
                try: data[field]=date.fromisoformat(str(data[field])).isoformat()
                except ValueError: raise HTTPException(422,f"Asset {field.replace('_',' ')} must be an ISO date")
        if data.get("purchase_date") and data.get("warranty_expiry") and data["warranty_expiry"]<data["purchase_date"]:
            raise HTTPException(422,"Asset warranty expiry cannot precede purchase date")
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
            if row["status"] not in {"under_review","verified"}:
                raise HTTPException(409,"This document must enter HR review before it can be downloaded")
            if _role(request) not in MANAGER_ROLES and row["status"]!="verified":
                raise HTTPException(403,"Employees may download only HR-verified documents")
            url=employee_document_download_url(employee_id=row["employee_id"],object_key=row["payload"]["object_key"])
            conn.execute("INSERT INTO hr_enterprise_events(record_id,event_type,actor_user_id) VALUES(%s,'download_link_issued',%s)",(record_id,actor))
        return {"url":url,"expires_in_seconds":300}
    except HTTPException: raise
    except EmployeeDocumentConfigurationError as exc: raise HTTPException(503,str(exc)) from exc
    except EmployeeDocumentError as exc: raise HTTPException(422,str(exc)) from exc
    except psycopg.Error as exc: raise _db_error(exc) from exc

@router.post("/recruitment/{offer_id}/hire",status_code=201)
def hire_recruitment_candidate(offer_id:int,payload:RecruitmentHireInput,request:Request):
    actor=_manager(request)
    if not payload.candidate_accepted:
        raise HTTPException(422,"Candidate acceptance must be confirmed before hiring")
    try:
        with _hr_connection() as conn:
            with conn.transaction():
                offer=conn.execute(
                    "SELECT * FROM hr_enterprise_records WHERE id=%s AND domain='recruitment' "
                    "AND payload->>'record_type'='offer' FOR UPDATE",(offer_id,)
                ).fetchone()
                if not offer: raise HTTPException(404,"Recruitment offer not found")
                if offer["status"]!="offered": raise HTTPException(409,"Only an active offer can be converted into an employee")
                offer_data=dict(offer["payload"])
                if int(offer_data.get("application_id") or 0)!=payload.application_id:
                    raise HTTPException(422,"Application does not match the selected offer")
                application=conn.execute(
                    "SELECT * FROM hr_enterprise_records WHERE id=%s AND domain='recruitment' "
                    "AND payload->>'record_type'='application' FOR UPDATE",(payload.application_id,)
                ).fetchone()
                if not application or application["status"] not in {"interview","offered"}:
                    raise HTTPException(409,"The application must be at the interview/offer stage before hiring")
                candidate_id=int(application["payload"]["candidate_id"])
                candidate=conn.execute(
                    "SELECT * FROM hr_enterprise_records WHERE id=%s AND domain='recruitment' "
                    "AND payload->>'record_type'='candidate' FOR UPDATE",(candidate_id,)
                ).fetchone()
                if not candidate: raise HTTPException(409,"The linked candidate record is missing")
                candidate_email=str(candidate["payload"].get("email","")).strip().lower()
                if candidate_email!=payload.employee.email.strip().lower():
                    raise HTTPException(422,"Employee email must match the accepted candidate's email")
                employee=payload.employee
                if employee.status not in {"active","probation"}:
                    raise HTTPException(422,"A newly hired employee must start as active or probationary")
                row=conn.execute(
                    "INSERT INTO hr_employees(user_id,employee_code,first_name,last_name,email,phone,department_id,"
                    "designation,reports_to_employee_id,employment_type,status,joining_date,exit_date,basic_salary,"
                    "hra,special_allowance,other_allowance,created_by_user_id) "
                    "VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) "
                    "RETURNING id,user_id,employee_code,first_name,last_name,email,phone,department_id,designation,"
                    "employment_type,status,joining_date,basic_salary,hra,special_allowance,other_allowance,created_at",
                    (employee.user_id,employee.employee_code.strip(),employee.first_name.strip(),employee.last_name.strip(),
                     employee.email,employee.phone.strip(),employee.department_id,employee.designation.strip(),
                     employee.reports_to_employee_id,employee.employment_type,employee.status,employee.joining_date,
                     employee.exit_date,employee.basic_salary,employee.hra,employee.special_allowance,
                     employee.other_allowance,actor),
                ).fetchone()
                conn.execute(
                    "INSERT INTO hr_employee_salary_versions(employee_id,effective_from,basic_salary,hra,"
                    "special_allowance,other_allowance,status,reason,created_by_user_id,reviewed_by_user_id,reviewed_at) "
                    "VALUES(%s,%s,%s,%s,%s,%s,'approved','Opening salary profile created from accepted recruitment offer',%s,%s,now())",
                    (row["id"],employee.joining_date,employee.basic_salary,employee.hra,
                     employee.special_allowance,employee.other_allowance,actor,actor),
                )
                from app.services.identity import IdentityService
                identity=IdentityService(conn)
                party=identity.create_party(
                    party_type="individual",
                    display_name=(row["first_name"]+" "+row["last_name"]).strip(),
                    actor_user_id=actor,reason="Candidate hired through recruitment workflow",
                )
                party_id=party["id"]
                identity.link_profile(
                    party_id=party_id,profile_type="employee",source_id=row["id"],
                    link_method="admin_verified",actor_user_id=actor,
                    reason="Candidate converted to employee",
                )
                for contact_type,value in (("email",row["email"]),("phone",row["phone"])):
                    if value:
                        try: identity.add_contact(party_id=party_id,contact_type=contact_type,value=value,source="hr_recruitment_hire")
                        except ValueError: pass
                if row["user_id"]:
                    _link_employee_login_identity(conn,identity,party_id,row["user_id"],actor)
                onboarding=conn.execute(
                    "SELECT id FROM hr_employee_lifecycle_templates WHERE lifecycle_type='onboarding' "
                    "AND is_active=true AND establishment_id IS NULL ORDER BY version DESC,id DESC LIMIT 1"
                ).fetchone()
                onboarding_count=0
                if onboarding:
                    items=conn.execute(
                        "SELECT * FROM hr_employee_lifecycle_template_items WHERE template_id=%s ORDER BY sequence,id",
                        (onboarding["id"],),
                    ).fetchall()
                    for item in items:
                        due=employee.joining_date+timedelta(days=item["due_days_offset"] or 0)
                        task=conn.execute(
                            "INSERT INTO hr_employee_lifecycle_tasks(employee_id,template_id,template_item_id,task_key,label,"
                            "description,owner_role,due_date,created_by_user_id) VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s) "
                            "ON CONFLICT(employee_id,template_item_id) WHERE template_item_id IS NOT NULL DO NOTHING RETURNING *",
                            (row["id"],onboarding["id"],item["id"],item["task_key"],item["label"],item["description"],
                             item["owner_role"],due,actor),
                        ).fetchone()
                        if task:
                            onboarding_count+=1
                            conn.execute(
                                "INSERT INTO hr_employee_lifecycle_task_events(task_id,event_type,after_state,actor_user_id) "
                                "VALUES(%s,'created',%s::jsonb,%s)",
                                (task["id"],json.dumps({"status":"pending","label":task["label"]}),actor),
                            )
                hired_offer=conn.execute(
                    "UPDATE hr_enterprise_records SET status='hired',employee_id=%s,payload=%s::jsonb,"
                    "version=version+1,updated_by_user_id=%s,updated_at=now() WHERE id=%s RETURNING *",
                    (row["id"],json.dumps({**offer_data,"employee_id":row["id"],"candidate_accepted":True,
                     "acceptance_reference":payload.acceptance_reference},default=str),actor,offer_id),
                ).fetchone()
                conn.execute(
                    "INSERT INTO hr_enterprise_events(record_id,event_type,from_status,to_status,before_state,after_state,note,actor_user_id) "
                    "VALUES(%s,'candidate_hired','offered','hired',%s::jsonb,%s::jsonb,%s,%s)",
                    (offer_id,json.dumps(dict(offer),default=str),json.dumps(dict(hired_offer),default=str),
                     payload.acceptance_reference,actor),
                )
                app_offered=application
                if application["status"]=="interview":
                    app_offered=conn.execute(
                        "UPDATE hr_enterprise_records SET status='offered',version=version+1,updated_by_user_id=%s,updated_at=now() "
                        "WHERE id=%s RETURNING *",(actor,payload.application_id),
                    ).fetchone()
                    conn.execute(
                        "INSERT INTO hr_enterprise_events(record_id,event_type,from_status,to_status,before_state,after_state,actor_user_id) "
                        "VALUES(%s,'offer_issued','interview','offered',%s::jsonb,%s::jsonb,%s)",
                        (payload.application_id,json.dumps(dict(application),default=str),json.dumps(dict(app_offered),default=str),actor),
                    )
                app_hired=conn.execute(
                    "UPDATE hr_enterprise_records SET status='hired',employee_id=%s,version=version+1,updated_by_user_id=%s,updated_at=now() "
                    "WHERE id=%s RETURNING *",(row["id"],actor,payload.application_id),
                ).fetchone()
                conn.execute(
                    "INSERT INTO hr_enterprise_events(record_id,event_type,from_status,to_status,before_state,after_state,actor_user_id) "
                    "VALUES(%s,'candidate_hired','offered','hired',%s::jsonb,%s::jsonb,%s)",
                    (payload.application_id,json.dumps(dict(app_offered),default=str),json.dumps(dict(app_hired),default=str),actor),
                )
                hired_candidate=conn.execute(
                    "UPDATE hr_enterprise_records SET status='hired',employee_id=%s,version=version+1,updated_by_user_id=%s,updated_at=now() "
                    "WHERE id=%s RETURNING *",(row["id"],actor,candidate_id),
                ).fetchone()
                conn.execute(
                    "INSERT INTO hr_enterprise_events(record_id,event_type,from_status,to_status,before_state,after_state,actor_user_id) "
                    "VALUES(%s,'candidate_hired',%s,'hired',%s::jsonb,%s::jsonb,%s)",
                    (candidate_id,candidate["status"],json.dumps(dict(candidate),default=str),json.dumps(dict(hired_candidate),default=str),actor),
                )
                result=dict(row)
                result["sbid"]=conn.execute("SELECT sbid FROM identity_parties WHERE id=%s",(party_id,)).fetchone()["sbid"]
                result["onboarding_tasks_created"]=onboarding_count
                result["onboarding_template_applied"]=bool(onboarding)
                return result
    except HTTPException: raise
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
              "AND (%s IS NULL OR r.status=%s) AND (%s IS NULL OR r.employee_id=%s "
              "OR (r.domain='learning' AND r.payload->>'record_type'='course' AND r.status='enrolled') "
              "OR (r.domain='travel' AND r.payload->>'record_type'='travel_policy' AND r.status='approved') "
              "OR (r.domain='performance' AND r.payload->>'record_type'='review_cycle' AND r.status IN ('self_review','manager_review'))) "
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
                _validate_references(conn,domain,payload.record_type,data)
                if domain=="learning" and payload.record_type=="progress":
                    enrollment=conn.execute("SELECT employee_id FROM hr_enterprise_records WHERE id=%s",(int(data["enrollment_id"]),)).fetchone()
                    if employee_id is None or enrollment["employee_id"] is None or int(employee_id)!=int(enrollment["employee_id"]):
                        raise HTTPException(403,"Learning progress must be recorded by the enrolled employee")
                if domain=="assets" and payload.record_type=="allocation":
                    allocation_employee_id=int(data["employee_id"])
                    if employee_id is None:
                        employee_id=allocation_employee_id
                    elif int(employee_id)!=allocation_employee_id:
                        raise HTTPException(422,"Allocation employee must match the linked employee profile")
                if domain=="travel" and payload.record_type=="request":
                    if employee_id is None:
                        raise HTTPException(422,"A travel request must be linked to an employee")
                    employee_row=conn.execute("SELECT employment_type FROM hr_employees WHERE id=%s",(employee_id,)).fetchone()
                    policy=conn.execute("SELECT status,payload FROM hr_enterprise_records WHERE id=%s",(int(data["policy_id"]),)).fetchone()
                    if policy["status"]!="approved":
                        raise HTTPException(409,"The selected travel policy is not active")
                    if policy["payload"]["employment_type"] not in {"all",employee_row["employment_type"]}:
                        raise HTTPException(403,"The selected travel policy does not apply to this employee type")
                if domain=="travel" and payload.record_type=="claim":
                    travel=conn.execute("SELECT employee_id,payload FROM hr_enterprise_records WHERE id=%s AND domain='travel'",(int(data["travel_record_id"]),)).fetchone()
                    if not travel or travel["employee_id"] is None:
                        raise HTTPException(409,"Travel request must be linked to an employee before a claim can be submitted")
                    if employee_id is None:
                        employee_id=travel["employee_id"]
                    if int(employee_id)!=int(travel["employee_id"]):
                        raise HTTPException(403,"A travel claim must belong to the employee who submitted the travel request")
                    expense=conn.execute(
                        "INSERT INTO hr_expenses(employee_id,category,amount,expense_date,description,receipt_reference) "
                        "VALUES(%s,'travel',%s,%s,%s,%s) RETURNING id",
                        (employee_id,data["actual_cost"],travel["payload"]["end_date"],
                         (payload.title+": "+str(travel["payload"].get("purpose","Travel claim")))[:1000],
                         data["receipt_reference"]),
                    ).fetchone()
                    data["expense_id"]=expense["id"]
                data["record_type"]=payload.record_type
                status=_initial_status(domain,payload.record_type)
                due_date=payload.due_date
                if due_date is None:
                    if domain=="learning" and payload.record_type=="certificate":
                        due_date=date.fromisoformat(str(data["valid_until"]))
                    elif domain=="exit" and payload.record_type=="case":
                        due_date=date.fromisoformat(str(data["last_working_date"]))
                    elif domain=="travel" and payload.record_type=="request":
                        due_date=date.fromisoformat(str(data["end_date"]))
                    elif domain=="assets" and payload.record_type=="asset_request":
                        due_date=date.fromisoformat(str(data["needed_by"]))
                    elif domain=="assets" and payload.record_type=="asset" and data.get("warranty_expiry"):
                        due_date=date.fromisoformat(str(data["warranty_expiry"]))
                row=conn.execute(
                  "INSERT INTO hr_enterprise_records(domain,employee_id,parent_id,title,status,payload,effective_date,due_date,created_by_user_id,updated_by_user_id) "
                  "VALUES(%s,%s,%s,%s,%s,%s::jsonb,%s,%s,%s,%s) RETURNING *",
                  (domain,employee_id,payload.parent_id,payload.title,status,json.dumps(data,default=str),payload.effective_date,due_date,actor,actor)
                ).fetchone()
                conn.execute("INSERT INTO hr_enterprise_events(record_id,event_type,to_status,after_state,actor_user_id) VALUES(%s,'created',%s,%s::jsonb,%s)",
                  (row["id"],status,json.dumps(dict(row),default=str),actor))
                if domain=="travel" and payload.record_type=="claim":
                    travel_id=int(data["travel_record_id"])
                    travel=conn.execute("SELECT * FROM hr_enterprise_records WHERE id=%s AND domain='travel' FOR UPDATE",(travel_id,)).fetchone()
                    updated_travel=conn.execute("UPDATE hr_enterprise_records SET status='claimed',version=version+1,updated_by_user_id=%s,updated_at=now() WHERE id=%s RETURNING *",
                        (actor,travel_id)).fetchone()
                    conn.execute("INSERT INTO hr_enterprise_events(record_id,event_type,from_status,to_status,before_state,after_state,actor_user_id) VALUES(%s,'claim_submitted','completed','claimed',%s::jsonb,%s::jsonb,%s)",
                        (travel_id,json.dumps(dict(travel),default=str),json.dumps(dict(updated_travel),default=str),actor))
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
                    data=_validate(domain,record_type,payload.payload)
                    _validate_references(conn,domain,record_type,data)
                    data["record_type"]=record_type
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
                if payload.expected_version is not None and old["version"]!=payload.expected_version:
                    raise HTTPException(409,"Record changed since it was loaded; refresh before changing its workflow")
                if not manager:
                    own=_employee(conn,actor)
                    if old["employee_id"] is None or int(old["employee_id"])!=int(own["id"]):
                        raise HTTPException(403,"Employees may change only their own HR records")
                    if not _employee_transition_allowed(domain,old["status"],payload.status):
                        raise HTTPException(403,"This workflow action requires HR manager permission")
                if payload.status not in TRANSITIONS[domain].get(old["status"],set()):
                    raise HTTPException(409,f"Transition from {old['status']} to {payload.status} is not allowed")
                record_type=old["payload"].get("record_type")
                if domain=="travel" and record_type=="travel_policy":
                    raise HTTPException(409,"Travel policies are managed by archiving the old version and creating a new version")
                if domain=="documents" and payload.status in {"verified","rejected"} and not (payload.note and payload.note.strip()):
                    raise HTTPException(422,"A verification or rejection note is required for employee documents")
                if domain=="recruitment" and payload.status=="rejected" and not (payload.note and payload.note.strip()):
                    raise HTTPException(422,"A rejection reason is required for recruitment decisions")
                if domain=="travel" and record_type=="claim" and payload.status=="reimbursed":
                    travel_id=int(old["payload"]["travel_record_id"])
                    expense_id=int(old["payload"].get("expense_id") or 0)
                    expense=conn.execute("SELECT status FROM hr_expenses WHERE id=%s",(expense_id,)).fetchone()
                    if not expense or expense["status"]!="reimbursed":
                        raise HTTPException(409,"The linked travel expense must be approved and paid through payroll before marking the claim reimbursed")
                    travel=conn.execute("SELECT * FROM hr_enterprise_records WHERE id=%s AND domain='travel' FOR UPDATE",(travel_id,)).fetchone()
                    if not travel or travel["status"]!="claimed":
                        raise HTTPException(409,"The linked travel request is not awaiting reimbursement")
                    updated_travel=conn.execute("UPDATE hr_enterprise_records SET status='reimbursed',version=version+1,updated_by_user_id=%s,updated_at=now() WHERE id=%s RETURNING *",
                        (actor,travel_id)).fetchone()
                    conn.execute("INSERT INTO hr_enterprise_events(record_id,event_type,from_status,to_status,before_state,after_state,note,actor_user_id) VALUES(%s,'claim_reimbursed','claimed','reimbursed',%s::jsonb,%s::jsonb,%s,%s)",
                        (travel_id,json.dumps(dict(travel),default=str),json.dumps(dict(updated_travel),default=str),payload.note,actor))
                if domain=="exit" and record_type=="case" and payload.status=="completed":
                    if old["employee_id"] is None:
                        raise HTTPException(409,"An exit case must be linked to an employee before completion")
                    clearance=conn.execute(
                        "SELECT count(*)::int AS total,count(*) FILTER (WHERE status NOT IN ('settlement_review','completed'))::int AS pending "
                        "FROM hr_enterprise_records WHERE domain='exit' AND payload->>'record_type'='clearance' AND payload->>'exit_record_id'=%s",
                        (str(record_id),),
                    ).fetchone()
                    settlement=conn.execute(
                        "SELECT id FROM hr_enterprise_records WHERE domain='exit' AND payload->>'record_type'='settlement' "
                        "AND payload->>'exit_record_id'=%s AND status='completed' LIMIT 1",
                        (str(record_id),),
                    ).fetchone()
                    if clearance["total"]==0 or clearance["pending"]>0 or not settlement:
                        raise HTTPException(409,"Complete every department clearance and the full-and-final settlement before closing the exit case")
                row=conn.execute("UPDATE hr_enterprise_records SET status=%s,version=version+1,updated_by_user_id=%s,updated_at=now() WHERE id=%s RETURNING *",
                  (payload.status,actor,record_id)).fetchone()
                if domain=="assets" and record_type=="allocation":
                    asset_id=int(old["payload"]["asset_id"])
                    linked_status={"assigned":"assigned","returned":"available","maintenance":"maintenance","written_off":"written_off"}.get(payload.status)
                    if linked_status:
                        asset=conn.execute("SELECT * FROM hr_enterprise_records WHERE id=%s AND domain='assets' AND payload->>'record_type'='asset' FOR UPDATE",(asset_id,)).fetchone()
                        if not asset: raise HTTPException(409,"The allocated asset record no longer exists")
                        if linked_status not in TRANSITIONS["assets"].get(asset["status"],set()):
                            raise HTTPException(409,f"Asset cannot move from {asset['status']} to {linked_status}")
                        updated_asset=conn.execute("UPDATE hr_enterprise_records SET status=%s,version=version+1,updated_by_user_id=%s,updated_at=now() WHERE id=%s RETURNING *",
                            (linked_status,actor,asset_id)).fetchone()
                        conn.execute("INSERT INTO hr_enterprise_events(record_id,event_type,from_status,to_status,before_state,after_state,note,actor_user_id) VALUES(%s,'custody_sync',%s,%s,%s::jsonb,%s::jsonb,%s,%s)",
                            (asset_id,asset["status"],linked_status,json.dumps(dict(asset),default=str),json.dumps(dict(updated_asset),default=str),payload.note,actor))
                if domain=="exit" and record_type=="case" and payload.status=="completed":
                    employee_id=int(old["employee_id"])
                    conn.execute("UPDATE hr_employees SET status='terminated',exit_date=%s,updated_at=now() WHERE id=%s",
                        (old["payload"]["last_working_date"],employee_id))
                    conn.execute("UPDATE app_users SET is_active=FALSE WHERE id=(SELECT user_id FROM hr_employees WHERE id=%s) AND role='staff'",
                        (employee_id,))
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
