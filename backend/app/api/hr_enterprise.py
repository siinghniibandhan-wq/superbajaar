"""Integrated HR enterprise workflows.

All eight HR domains share audited, versioned records while retaining explicit
domain validation and controlled state transitions. Employee self-service is
bound to the authenticated user's linked employee record.
"""
from datetime import date, datetime, timedelta
from decimal import Decimal, InvalidOperation
import json
import re
import csv
import io

import psycopg
from fastapi import APIRouter, File, Form, HTTPException, Query, Request, UploadFile
from fastapi.responses import Response
from openpyxl import Workbook
from reportlab.lib import colors
from reportlab.lib.pagesizes import landscape, A4
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
from pydantic import BaseModel, Field, field_validator
from app.api.hr import EmployeeInput, _actor, _manager, _employee, _hr_connection, _db_error, _link_employee_login_identity, hr_overview
from app.services.hr_travel_integrations import create_provider_booking, disburse_travel_advance, TravelIntegrationConfigurationError
from app.services.hr_exit_settlement import calculate_exit_settlement, validate_exit_policy
from app.services.hr_employee_documents import (
    EmployeeDocumentConfigurationError, EmployeeDocumentError,
    upload_employee_document, employee_document_download_url, delete_employee_document,
)
from app.services.hr_candidate_email import (
    CandidateEmailConfigurationError, CandidateEmailDeliveryError, send_candidate_email,
)

router = APIRouter(prefix="/hr/enterprise", tags=["hr-enterprise"])

DOMAINS = {"recruitment","documents","performance","learning","assets","travel","exit","analytics"}
MANAGER_ROLES = {"super_admin","owner","admin","manager"}
EMPLOYEE_DOMAINS = {"documents","performance","learning","assets","travel","exit"}
STATUSES = {
 "recruitment":{"draft","open","closed","screening","shortlisted","interview","offered","hired","rejected","withdrawn","completed","archived"},
 "documents":{"pending","uploaded","under_review","verified","rejected","expired","archived"},
 "performance":{"draft","active","self_review","manager_review","calibration","acknowledged","closed","cancelled"},
 "learning":{"planned","enrolled","in_progress","completed","failed","cancelled"},
 "assets":{"available","requested","approved","assigned","acknowledged","returned","maintenance","written_off","rejected","received","partially_received","reconciled","investigating","closed"},
 "travel":{"draft","submitted","approved","rejected","booked","in_progress","completed","claimed","reimbursed","cancelled","requested","disbursed"},
 "exit":{"initiated","notice_period","handover","clearance","settlement_review","completed","withdrawn"},
 "analytics":{"saved","scheduled","archived"}
}
TRANSITIONS = {
 "recruitment":{"draft":{"open","archived"},"open":{"screening","closed","archived"},"screening":{"shortlisted","rejected","withdrawn"},"shortlisted":{"interview","rejected","withdrawn"},"interview":{"offered","rejected","withdrawn"},"offered":{"rejected","withdrawn"}},
 "documents":{"pending":{"uploaded","archived"},"uploaded":{"under_review","rejected"},"under_review":{"verified","rejected","expired"},"verified":{"expired","archived"},"rejected":{"uploaded","archived"},"expired":{"uploaded","archived"}},
 "performance":{"draft":{"active","cancelled"},"active":{"self_review","cancelled"},"self_review":{"manager_review"},"manager_review":{"calibration","acknowledged"},"calibration":{"acknowledged"},"acknowledged":{"closed"}},
 "learning":{"planned":{"enrolled","cancelled"},"enrolled":{"in_progress","cancelled"},"in_progress":{"completed","failed"},"failed":{"enrolled"}},
 "assets":{"available":{"assigned","maintenance","written_off"},"requested":{"approved","rejected"},"approved":{"assigned","rejected"},"assigned":{"acknowledged","returned","maintenance","written_off"},"acknowledged":{"returned","maintenance","written_off"},"maintenance":{"assigned","written_off"},"returned":{"available","maintenance","written_off"}},
 "travel":{"draft":{"submitted","cancelled"},"submitted":{"approved","rejected"},"approved":{"booked","cancelled"},"booked":{"in_progress","cancelled"},"in_progress":{"completed"},"completed":{"claimed"},"claimed":{"reimbursed"}},
 "exit":{"initiated":{"notice_period","withdrawn"},"notice_period":{"handover","withdrawn"},"handover":{"clearance"},"clearance":{"settlement_review"},"settlement_review":{"completed"}},
 "analytics":{"saved":{"scheduled","archived"},"scheduled":{"saved","archived"}}
}
MANAGER_ONLY_TYPES = {
 "recruitment":{"job_opening","candidate","application","interview","interview_feedback","offer","communication"},
 "assets":{"asset","allocation","maintenance","procurement","stock_receipt","stock_reconciliation","asset_loss"},
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


def _allowed_record_transitions(domain, record_type, status):
    # Transitions are scoped to the record's actual lifecycle. A shared domain
    # status vocabulary must never let (for example) a course be "reimbursed".
    per_type = {
        "recruitment": {
            "job_opening": {"draft":{"open","archived"},"open":{"closed","archived"},"closed":{"archived"}},
            "candidate": {"draft":{"withdrawn","archived"},"withdrawn":{"archived"}},
            "application": {"screening":{"shortlisted","rejected","withdrawn"},"shortlisted":{"interview","rejected","withdrawn"},"interview":{"offered","rejected","withdrawn"},"offered":{"rejected","withdrawn"}},
            "interview": {"interview":{"completed"}},
            "offer": {"offered":{"rejected","withdrawn"}},
            "interview_feedback": {}, "communication": {},
        },
        "documents": {
            "employee_document": {"pending":{"under_review","archived"},"under_review":{"verified","rejected","expired"},"verified":{"expired","archived"},"rejected":{"archived"},"expired":{"archived"}},
        },
        "performance": {
            "review_template": {"draft":{"active","cancelled"},"active":{"cancelled"}},
            "review_cycle": {"draft":{"active","cancelled"},"active":{"self_review","cancelled"},"self_review":{"manager_review"},"manager_review":{"calibration","closed"},"calibration":{"closed"}},
            "review": {"manager_review":{"calibration","acknowledged"},"calibration":{"acknowledged"},"acknowledged":{"closed"}},
            "self_review": {"self_review":{"manager_review"}},
            "goal": {"draft":{"active","cancelled"},"active":{"cancelled"}},
            "feedback": {}, "calibration": {"calibration":{"acknowledged"}}, "acknowledgement": {"acknowledged":{"closed"}},
        },
        "learning": {
            "course": {"planned":{"enrolled","cancelled"},"enrolled":{"cancelled"}},
            "enrollment": {"planned":{"enrolled","cancelled"},"enrolled":{"in_progress","cancelled"},"in_progress":{"completed","failed"},"failed":{"enrolled"}},
            "progress": {}, "assessment": {}, "certificate": {"completed":{"expired","archived"},"expired":{"archived"}},
        },
        "assets": {
            "asset": {"available":{"assigned","maintenance","written_off"},"assigned":{"acknowledged","returned","maintenance","written_off"},"acknowledged":{"returned","maintenance","written_off"},"maintenance":{"assigned","written_off"},"returned":{"available","maintenance","written_off"},"written_off":{}},
            "asset_request": {"requested":{"approved","rejected"},"approved":{"assigned","rejected"}},
            "allocation": {"requested":{"approved","rejected"},"approved":{"assigned","rejected"},"assigned":{"acknowledged","returned","maintenance","written_off"},"acknowledged":{"returned","maintenance","written_off"}},
            "maintenance": {},
            "procurement": {"requested":{"approved","rejected","archived"},"approved":{"received","partially_received","archived"},"partially_received":{"received","archived"},"received":{"archived"}},
            "stock_receipt": {"received":{"archived"}},
            "stock_reconciliation": {"requested":{"reconciled","investigating"},"investigating":{"reconciled","closed"},"reconciled":{"closed"}},
            "asset_loss": {"investigating":{"closed","written_off"},"closed":{},"written_off":{}},
        },
        "travel": {
            "travel_policy": {}, "request": {"draft":{"submitted","cancelled"},"submitted":{"approved","rejected"},"approved":{"booked","cancelled"},"booked":{"in_progress","cancelled"},"in_progress":{"completed"},"completed":{"claimed"}},
            "booking": {}, "advance": {"requested":{"approved","rejected"},"approved":{"disbursed"}}, "claim": {"claimed":{"reimbursed"}},
        },
        "exit": {
            "case": {"initiated":{"notice_period","withdrawn"},"notice_period":{"handover","withdrawn"},"handover":{"clearance"},"clearance":{"settlement_review"},"settlement_review":{"completed"}},
            "clearance": {"clearance":{"completed","rejected"}},
            "settlement": {"settlement_review":{"completed"}},
        },
    }
    domain_rules = per_type.get(domain)
    if domain_rules is None:
        return TRANSITIONS.get(domain,{}).get(status,set())
    return domain_rules.get(record_type,{}).get(status,set())


def _initial_status(domain, record_type):
    typed = {
        ("recruitment", "application"): "screening",
        ("recruitment", "interview"): "interview",
        ("recruitment", "interview_feedback"): "completed",
        ("recruitment", "communication"): "completed",
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
        ("assets", "stock_receipt"): "received",
        ("assets", "asset_loss"): "investigating",
        ("travel", "travel_policy"): "approved",
        ("travel", "booking"): "booked",
        ("travel", "advance"): "requested",
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
  "job_opening":["department","employment_type","location","headcount"],
  "candidate":["email"],
  "application":["candidate_id","job_id"],
  "interview":["application_id","scheduled_at","interviewer_employee_id","interview_type"],
  "interview_feedback":["interview_id","interviewer_employee_id","rating","decision","feedback"],
  "offer":["application_id","offered_salary","currency","expires_on"],
  "communication":["candidate_id","channel","direction","subject","message","occurred_at"]
 },
 "documents":{"employee_document":["document_type","file_name","object_key","content_type","sha256"]},
 "performance":{
  "review_template":["name","sections","rating_scale"],
  "review_cycle":["period_start","period_end"],
  "review":["cycle_id","reviewer_employee_id","template_id"],
  "self_review":["cycle_id","summary","rating","achievements","development_areas"],
  "goal":["cycle_id","description","measure","target"],
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
  "maintenance":["asset_id","maintenance_type","reported_at","description"],
  "procurement":["vendor","requested_by","items","estimated_total"],
  "stock_receipt":["procurement_id","received_at","items","received_by"],
  "stock_reconciliation":["location","counted_at","expected_count","physical_count","variance_reason"],
  "asset_loss":["asset_id","reported_at","description","investigation_reference"]
 },
 "travel":{
  "travel_policy":["name","employment_type","max_trip_cost","per_diem_limit","currency"],
  "request":["destination","purpose","start_date","end_date","estimated_cost","estimated_per_diem","policy_id"],
  "booking":["travel_record_id","booked_cost","client_reference"],
  "advance":["travel_record_id","requested_amount"],
  "claim":["travel_record_id","actual_cost","receipt_reference"]
 },
 "exit":{
  "case":["reason","last_working_date"],
  "clearance":["exit_record_id","department","owner_employee_id"],
  "settlement":["exit_record_id","payable_on"]
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

class ExitStatutoryPolicyInput(BaseModel):
    establishment_id: int = Field(gt=0)
    version_label: str = Field(min_length=2,max_length=100)
    jurisdiction_code: str = Field(min_length=2,max_length=32)
    effective_from: date
    effective_to: date | None = None
    policy_config: dict
    source_references: list[dict] = Field(min_length=1,max_length=30)

class EmployeeLoanInput(BaseModel):
    employee_id: int = Field(gt=0)
    loan_reference: str = Field(min_length=2,max_length=80)
    principal_amount: Decimal = Field(gt=0,max_digits=14,decimal_places=2)
    currency: str = Field(default="INR",min_length=3,max_length=3)

class RecruitmentHireInput(BaseModel):
    application_id: int = Field(gt=0)
    candidate_accepted: bool
    acceptance_reference: str | None = Field(default=None,max_length=500)
    employee: EmployeeInput

class CandidateEmailInput(BaseModel):
    subject: str = Field(min_length=2,max_length=200)
    message: str = Field(min_length=2,max_length=10000)

def _role(request):
    return getattr(request.state,"role","")

def _ensure_travel_claimable(status):
    if status != "completed":
        raise HTTPException(409,"Travel must be completed before a claim can be submitted")


def _ensure_asset_allocatable(status, active_allocations):
    if status not in {"available", "approved"}:
        raise HTTPException(409,"Only available or approved assets can be allocated")
    if active_allocations:
        raise HTTPException(409,"This asset already has an active allocation")


def _ensure_candidate_hireable(status):
    if status == "hired":
        raise HTTPException(409,"This candidate has already been hired")


def _ensure_offer_unexpired(expires_on, today=None):
    try:
        expiry=date.fromisoformat(str(expires_on))
    except (TypeError,ValueError):
        raise HTTPException(409,"The offer has no valid expiry date and cannot be accepted")
    if expiry < (today or date.today()):
        raise HTTPException(409,"This offer has expired and cannot be converted into an employee")


def _ensure_no_active_recruitment_duplicate(record, message):
    if record:
        raise HTTPException(409,message)


def _ensure_job_opening_closable(filled_headcount, headcount):
    if int(filled_headcount or 0) < int(headcount or 0):
        raise HTTPException(409,"A job opening can be closed only after its approved headcount has been filled")


def _ensure_travel_amount_budget(existing, requested, limit, label):
    if Decimal(str(existing)) + Decimal(str(requested)) > Decimal(str(limit)):
        raise HTTPException(422,f"Combined {label} exceeds the permitted travel amount")

def _ensure_goal_weight_limit(existing, proposed):
    if Decimal(str(existing)) + Decimal(str(proposed)) > Decimal("100"):
        raise HTTPException(422,"Active goal weights for a review cycle cannot exceed 100 percent")


def _ensure_assessment_attempt_limit(attempts, maximum):
    if maximum < 1 or maximum > 20:
        raise HTTPException(409,"The course assessment attempt limit is misconfigured")
    if attempts >= maximum:
        raise HTTPException(409,f"Assessment attempt limit reached ({maximum})")

def _calculate_asset_book_value(purchase_value, salvage_value, useful_life_months, purchase_date, as_of_date, method="straight_line", annual_rate="20"):
    try:
        cost=Decimal(str(purchase_value)); salvage=Decimal(str(salvage_value))
        life=int(useful_life_months); purchased=date.fromisoformat(str(purchase_date)); as_of=date.fromisoformat(str(as_of_date))
        rate=Decimal(str(annual_rate))
    except (ValueError,TypeError,InvalidOperation):
        raise HTTPException(422,"Asset depreciation inputs are invalid")
    if cost<0 or salvage<0 or salvage>cost or life<1 or rate<=0 or rate>100 or as_of<purchased:
        raise HTTPException(422,"Asset depreciation values, useful life or dates are outside permitted ranges")
    months=max(0,(as_of.year-purchased.year)*12+as_of.month-purchased.month-(1 if as_of.day<purchased.day else 0))
    elapsed=min(months,life)
    if method=="straight_line":
        monthly=(cost-salvage)/Decimal(life)
        book=max(salvage,cost-monthly*Decimal(elapsed))
    elif method=="reducing_balance":
        annual_factor=Decimal("1")-rate/Decimal("100")
        years=months//12
        book=max(salvage,cost*(annual_factor**years))
    else:
        raise HTTPException(422,"Depreciation method must be straight_line or reducing_balance")
    book=book.quantize(Decimal("0.01"))
    accumulated=(cost-book).quantize(Decimal("0.01"))
    return {"method":method,"purchase_value":str(cost),"salvage_value":str(salvage),"useful_life_months":life,
            "elapsed_months":elapsed,"as_of_date":as_of.isoformat(),"annual_rate_percent":str(rate),
            "accumulated_depreciation":str(accumulated),"book_value":str(book)}


def _validate_references(conn, domain, record_type, data):
    references = {
        ("recruitment","application"): {
            "candidate_id": ("recruitment","candidate"),
            "job_id": ("recruitment","job_opening"),
        },
        ("recruitment","interview"): {"application_id": ("recruitment","application")},
        ("recruitment","interview_feedback"): {"interview_id": ("recruitment","interview")},
        ("recruitment","communication"): {"candidate_id": ("recruitment","candidate")},
        ("recruitment","offer"): {"application_id": ("recruitment","application")},
        ("performance","review"): {"template_id": ("performance","review_template"),"cycle_id": ("performance","review_cycle")},
        ("performance","self_review"): {"cycle_id": ("performance","review_cycle")},
        ("performance","goal"): {"cycle_id": ("performance","review_cycle")},
        ("performance","feedback"): {"review_id": ("performance","review")},
        ("performance","calibration"): {"review_id": ("performance","review")},
        ("performance","acknowledgement"): {"review_id": ("performance","review")},
        ("learning","enrollment"): {"course_id": ("learning","course")},
        ("learning","progress"): {"enrollment_id": ("learning","enrollment")},
        ("learning","assessment"): {"enrollment_id": ("learning","enrollment")},
        ("learning","certificate"): {"enrollment_id": ("learning","enrollment")},
        ("assets","allocation"): {"asset_id": ("assets","asset")},
        ("assets","maintenance"): {"asset_id": ("assets","asset")},
        ("assets","stock_receipt"): {"procurement_id": ("assets","procurement")},
        ("assets","asset_loss"): {"asset_id": ("assets","asset")},
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
    if domain=="performance" and record_type=="review":
        template=conn.execute("SELECT status FROM hr_enterprise_records WHERE id=%s",(data["template_id"],)).fetchone()
        if template["status"]!="active":
            raise HTTPException(409,"The selected review template must be active")
    if domain=="performance" and record_type=="self_review":
        cycle=conn.execute("SELECT status FROM hr_enterprise_records WHERE id=%s",(data["cycle_id"],)).fetchone()
        if cycle["status"]!="self_review":
            raise HTTPException(409,"The review cycle must be open for employee self-review")
    if domain=="performance" and record_type=="goal":
        cycle=conn.execute("SELECT status FROM hr_enterprise_records WHERE id=%s",(data["cycle_id"],)).fetchone()
        if cycle["status"] not in {"active","self_review"}:
            raise HTTPException(409,"Goals can be added only to an active performance cycle")
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
    if domain=="travel" and record_type=="booking":
        client_ref=str(data["client_reference"]).strip()
        if not re.fullmatch(r"[A-Za-z0-9._:-]{8,100}",client_ref):
            raise HTTPException(422,"Travel booking client_reference must be 8 to 100 safe characters")
        data["client_reference"]=client_ref
        details=data.get("booking_details",{})
        if isinstance(details,str):
            try: details=json.loads(details or "{}")
            except (ValueError,TypeError): raise HTTPException(422,"Provider booking details must be valid JSON")
        if not isinstance(details,dict): raise HTTPException(422,"Provider booking details must be a JSON object")
        data["booking_details"]=details
        try: amount=Decimal(str(data["booked_cost"]))
        except (InvalidOperation,TypeError): raise HTTPException(422,"Booking cost must be numeric")
        if amount<=0: raise HTTPException(422,"Booking cost must be greater than zero")
        data["booked_cost"]=str(amount)
    if domain=="travel" and record_type=="advance":
        try: amount=Decimal(str(data["requested_amount"]))
        except (InvalidOperation,TypeError): raise HTTPException(422,"Travel advance must be numeric")
        if amount<=0: raise HTTPException(422,"Travel advance must be greater than zero")
        data["requested_amount"]=str(amount)
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
        travel=conn.execute("SELECT status,payload FROM hr_enterprise_records WHERE id=%s",(data["travel_record_id"],)).fetchone()
        if travel["status"] not in {"approved","booked","in_progress"}:
            raise HTTPException(409,"Travel must be approved before booking or advance processing")
        policy=conn.execute("SELECT payload FROM hr_enterprise_records WHERE id=%s",(int(travel["payload"]["policy_id"]),)).fetchone()
        if record_type=="booking" and Decimal(data["booked_cost"])>Decimal(policy["payload"]["max_trip_cost"]):
            raise HTTPException(422,"Booking cost exceeds the approved travel policy cap")
        if record_type=="advance" and Decimal(data["requested_amount"])>Decimal(travel["payload"]["estimated_cost"]):
            raise HTTPException(422,"Travel advance cannot exceed the approved estimated trip cost")
    if domain=="travel" and record_type=="claim":
        travel=conn.execute("SELECT status,payload FROM hr_enterprise_records WHERE id=%s",(data["travel_record_id"],)).fetchone()
        if travel["status"]!="completed":
            raise HTTPException(409,"Travel must be completed before a claim can be submitted")
        policy=conn.execute("SELECT payload FROM hr_enterprise_records WHERE id=%s",(int(travel["payload"]["policy_id"]),)).fetchone()
        if Decimal(data["actual_cost"])>Decimal(policy["payload"]["max_trip_cost"]):
            raise HTTPException(422,"Claim amount exceeds the approved travel policy cap")
    if domain=="exit" and record_type=="settlement":
        try: date.fromisoformat(str(data["payable_on"]))
        except (ValueError,TypeError): raise HTTPException(422,"Settlement payable date is invalid")
        if data.get("auto_calculate") is not True:
            missing_amounts=[k for k in ("gross_due","deductions","net_due") if data.get(k) in (None,"")]
            if missing_amounts: raise HTTPException(422,"Manual settlements require gross_due, deductions and net_due")
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
        for field in ("first_name","last_name"):
            value=str(data.get(field,"")).strip()
            if field=="first_name" and not value:
                raise HTTPException(422,"Candidate first name is required")
            if value:
                data[field]=value
        email=str(data["email"]).strip().lower()
        if len(email)>254 or not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+",email):
            raise HTTPException(422,"Candidate email is invalid")
        data["email"]=email
        if data.get("phone") not in (None,""):
            phone=str(data["phone"]).strip()
            if len(phone)<5 or len(phone)>32:
                raise HTTPException(422,"Candidate phone number must contain 5 to 32 characters")
            data["phone"]=phone
        for field in ("source","resume_reference"):
            if data.get(field) is not None:
                data[field]=str(data[field]).strip() or None
    if domain=="travel" and record_type=="travel_policy":
        try: trip_cap=Decimal(str(data["max_trip_cost"])); per_diem=Decimal(str(data["per_diem_limit"]))
        except InvalidOperation: raise HTTPException(422,"Travel policy limits must be numeric")
        if trip_cap<=0 or per_diem<=0: raise HTTPException(422,"Travel policy limits must be greater than zero")
        if data["employment_type"] not in {"all","full_time","part_time","contract","intern","shift_worker"}:
            raise HTTPException(422,"Travel policy employment type is invalid")
        if len(str(data["currency"]))!=3: raise HTTPException(422,"Travel policy currency must be a 3-letter code")
        grade=str(data.get("job_grade","all")).strip() or "all"
        if len(grade)>32: raise HTTPException(422,"Travel policy job grade cannot exceed 32 characters")
        data["job_grade"]=grade
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
    if domain=="analytics" and record_type=="report":
        report_type=str(data["report_type"]).strip()
        if report_type not in {"enterprise","workforce"}:
            raise HTTPException(422,"Analytics report type must be enterprise or workforce")
        filters=data["filters"]
        if isinstance(filters,str):
            try: filters=json.loads(filters)
            except (ValueError,TypeError): raise HTTPException(422,"Analytics report filters must be valid JSON")
        if not isinstance(filters,dict):
            raise HTTPException(422,"Analytics report filters must be a JSON object")
        allowed_domains={"documents","performance","learning","assets","travel","exit","analytics"}
        if filters.get("domain") not in (None,"") and filters["domain"] not in allowed_domains:
            raise HTTPException(422,"Analytics report domain filter is invalid")
        if filters.get("department_id") not in (None,""):
            try: filters["department_id"]=int(filters["department_id"])
            except (ValueError,TypeError): raise HTTPException(422,"Analytics report department ID must be a positive integer")
            if filters["department_id"]<=0: raise HTTPException(422,"Analytics report department ID must be a positive integer")
        if filters.get("record_type") is not None and len(str(filters["record_type"]))>48:
            raise HTTPException(422,"Analytics report record type is too long")
        if filters.get("status") is not None and len(str(filters["status"]))>32:
            raise HTTPException(422,"Analytics report status is too long")
        frequency=str(data.get("frequency","weekly")).strip().lower()
        if frequency not in {"weekly","monthly"}:
            raise HTTPException(422,"Scheduled analytics frequency must be weekly or monthly")
        data.update({"report_type":report_type,"filters":filters,"frequency":frequency,"delivery_channel":"workspace_snapshot"})
    if domain=="exit" and record_type=="case":
        try: last=date.fromisoformat(str(data["last_working_date"]))
        except ValueError: raise HTTPException(422,"Last working date must be an ISO date")
        if last<date.today(): raise HTTPException(422,"Last working date cannot be in the past when initiating an exit case")
    if domain=="recruitment" and record_type=="job_opening":
        for field in ("department","employment_type","location"):
            data[field]=str(data[field]).strip()
            if not data[field]:
                raise HTTPException(422,f"Job {field.replace('_',' ')} is required")
        if data["employment_type"] not in {"full_time","part_time","contract","intern","temporary","shift_worker"}:
            raise HTTPException(422,"Job employment type is invalid")
        try: headcount=int(data["headcount"])
        except (ValueError,TypeError): raise HTTPException(422,"Job headcount must be a positive integer")
        if headcount<=0 or str(data["headcount"]).strip() not in {str(headcount),f"+{headcount}"}:
            raise HTTPException(422,"Job headcount must be a positive integer")
        data["headcount"]=headcount;data["filled_headcount"]=0
    if domain=="recruitment" and record_type=="interview":
        try:
            application_id=int(data["application_id"]); interviewer_id=int(data["interviewer_employee_id"])
            scheduled=datetime.fromisoformat(str(data["scheduled_at"]).replace("Z","+00:00"))
        except (ValueError,TypeError): raise HTTPException(422,"Interview IDs and scheduled date/time are invalid")
        if application_id<=0 or interviewer_id<=0: raise HTTPException(422,"Interview application and interviewer IDs must be positive")
        data["application_id"]=application_id;data["interviewer_employee_id"]=interviewer_id
        data["scheduled_at"]=scheduled.isoformat()
        data["interview_type"]=str(data["interview_type"]).strip()
        if not data["interview_type"]: raise HTTPException(422,"Interview type is required")
    if domain=="recruitment" and record_type=="interview_feedback":
        try: rating=Decimal(str(data["rating"])); interviewer_id=int(data["interviewer_employee_id"])
        except (InvalidOperation,ValueError,TypeError): raise HTTPException(422,"Interview rating and interviewer ID are invalid")
        if rating<1 or rating>5 or interviewer_id<=0: raise HTTPException(422,"Interview rating must be 1–5 and interviewer ID positive")
        if data["decision"] not in {"pass","hold","reject"}: raise HTTPException(422,"Interview decision must be pass, hold or reject")
        feedback=str(data["feedback"]).strip()
        if len(feedback)<2: raise HTTPException(422,"Interview feedback must contain at least two characters")
        data["feedback"]=feedback;data["rating"]=str(rating);data["interviewer_employee_id"]=interviewer_id
    if domain=="recruitment" and record_type=="communication":
        if data["channel"] not in {"email","phone","sms","in_person","other"}: raise HTTPException(422,"Communication channel is invalid")
        if data["direction"] not in {"inbound","outbound"}: raise HTTPException(422,"Communication direction is invalid")
        subject=str(data["subject"]).strip(); message=str(data["message"]).strip()
        if len(subject)<2 or len(message)<2: raise HTTPException(422,"Communication subject and message are required")
        data["subject"]=subject;data["message"]=message
        try: data["occurred_at"]=datetime.fromisoformat(str(data["occurred_at"]).replace("Z","+00:00")).isoformat()
        except ValueError: raise HTTPException(422,"Communication date and time must be ISO formatted")
    if domain=="recruitment" and record_type=="offer":
        try: salary=Decimal(str(data["offered_salary"])); expiry=date.fromisoformat(str(data["expires_on"])); application_id=int(data["application_id"])
        except (ValueError,InvalidOperation,TypeError): raise HTTPException(422,"Offer application, salary or expiry date is invalid")
        currency=str(data["currency"]).strip().upper()
        if application_id<=0 or salary<=0 or not re.fullmatch(r"[A-Z]{3}",currency):
            raise HTTPException(422,"Offer application and salary must be positive and currency must be a 3-letter code")
        if expiry<date.today(): raise HTTPException(422,"Offer expiry date cannot be in the past")
        data["application_id"]=application_id; data["offered_salary"]=str(salary); data["currency"]=currency; data["expires_on"]=expiry.isoformat()
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
    if domain=="learning" and record_type=="course" and data.get("max_attempts") not in (None,""):
        try: maximum=int(data["max_attempts"])
        except (ValueError,TypeError): raise HTTPException(422,"Maximum assessment attempts must be an integer")
        if maximum<1 or maximum>20: raise HTTPException(422,"Maximum assessment attempts must be between 1 and 20")
        data["max_attempts"]=maximum
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
    if domain=="assets" and record_type in {"procurement","stock_receipt"} and isinstance(data.get("items"),str):
        try: data["items"]=json.loads(data["items"])
        except (ValueError,TypeError): raise HTTPException(422,"Asset item lines must be valid JSON")
    if domain=="assets" and record_type=="procurement":
        try: total=Decimal(str(data["estimated_total"]))
        except InvalidOperation: raise HTTPException(422,"Procurement estimated total must be numeric")
        if total<=0 or not isinstance(data["items"],list) or not data["items"]:
            raise HTTPException(422,"Procurement requires at least one item and a positive estimated total")
        for item in data["items"]:
            if not isinstance(item,dict) or not str(item.get("description","")).strip():
                raise HTTPException(422,"Each procurement item requires a description")
            try:
                quantity=Decimal(str(item.get("quantity",0)))
                unit_cost=Decimal(str(item.get("unit_cost",0)))
            except InvalidOperation:
                raise HTTPException(422,"Procurement item quantities and unit costs must be numeric")
            if quantity<=0 or unit_cost<0:
                raise HTTPException(422,"Procurement quantities must be positive and unit costs cannot be negative")
        data["estimated_total"]=str(total)
        data["vendor"]=str(data["vendor"]).strip()
        data["requested_by"]=str(data["requested_by"]).strip()
    if domain=="assets" and record_type=="stock_receipt":
        try: received_at=date.fromisoformat(str(data["received_at"])[:10])
        except ValueError: raise HTTPException(422,"Stock receipt date is invalid")
        if not isinstance(data["items"],list) or not data["items"]:
            raise HTTPException(422,"A stock receipt must contain at least one received item")
        for item in data["items"]:
            if not isinstance(item,dict) or not str(item.get("description","")).strip():
                raise HTTPException(422,"Each received item requires a description")
            try: quantity=Decimal(str(item.get("quantity",0)))
            except InvalidOperation: raise HTTPException(422,"Received quantities must be numeric")
            if quantity<=0: raise HTTPException(422,"Received quantities must be positive")
        data["received_at"]=received_at.isoformat()
    if domain=="assets" and record_type=="stock_reconciliation":
        try:
            expected=int(data["expected_count"]); physical=int(data["physical_count"])
            counted=date.fromisoformat(str(data["counted_at"])[:10])
        except (ValueError,TypeError): raise HTTPException(422,"Stock reconciliation counts or date are invalid")
        if min(expected,physical)<0: raise HTTPException(422,"Stock counts cannot be negative")
        if expected!=physical and len(str(data["variance_reason"]).strip())<5:
            raise HTTPException(422,"A variance reason of at least five characters is required")
        data.update({"expected_count":expected,"physical_count":physical,"counted_at":counted.isoformat(),"variance":physical-expected})
    if domain=="assets" and record_type=="asset_loss":
        try: date.fromisoformat(str(data["reported_at"])[:10])
        except ValueError: raise HTTPException(422,"Asset loss report date is invalid")
        if len(str(data["description"]).strip())<10:
            raise HTTPException(422,"Asset loss investigation requires a detailed description")
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
        if data.get("depreciation_method"):
            if not data.get("purchase_date") or data.get("purchase_value") in (None,""):
                raise HTTPException(422,"Depreciable assets require purchase date and purchase value")
            data["depreciation"]=_calculate_asset_book_value(
                data["purchase_value"],data.get("salvage_value","0"),data.get("useful_life_months",60),
                data["purchase_date"],data.get("depreciation_as_of",date.today().isoformat()),
                data["depreciation_method"],data.get("annual_depreciation_rate","20")
            )
    if domain=="travel" and record_type in {"booking","advance","claim"}:
        amount_key={"booking":"booked_cost","advance":"requested_amount","claim":"actual_cost"}[record_type]
        try: amount=Decimal(str(data[amount_key]))
        except InvalidOperation: raise HTTPException(422,"Travel amount must be numeric")
        if amount<=0: raise HTTPException(422,"Travel amount must be greater than zero")
        data[amount_key]=str(amount)
    if domain=="exit" and record_type=="settlement":
        try: payable=date.fromisoformat(str(data["payable_on"]))
        except (ValueError,TypeError): raise HTTPException(422,"Exit settlement payable date is invalid")
        if data.get("auto_calculate") is not True:
            try:
                gross=Decimal(str(data["gross_due"])); deductions=Decimal(str(data["deductions"])); net=Decimal(str(data["net_due"]))
            except (ValueError,InvalidOperation,KeyError): raise HTTPException(422,"Exit settlement amounts are invalid")
            if min(gross,deductions,net)<0 or gross-deductions!=net:
                raise HTTPException(422,"Exit settlement net due must equal gross due less deductions")
            for field,expected in (("earnings_breakdown",gross),("deductions_breakdown",deductions)):
                components=data.get(field)
                if components is not None:
                    if isinstance(components,str):
                        try: components=json.loads(components)
                        except (ValueError,TypeError): raise HTTPException(422,f"{field.replace('_',' ').title()} must be valid JSON")
                    if not isinstance(components,list):
                        raise HTTPException(422,f"{field.replace('_',' ').title()} must be a list")
                    total=Decimal("0")
                    for component in components:
                        if not isinstance(component,dict) or len(str(component.get("type","")).strip())<2:
                            raise HTTPException(422,f"Every {field.replace('_',' ')} item requires a type")
                        try: amount=Decimal(str(component.get("amount","")))
                        except InvalidOperation: raise HTTPException(422,f"Every {field.replace('_',' ')} amount must be numeric")
                        if amount<0: raise HTTPException(422,"Settlement components cannot be negative")
                        component["amount"]=str(amount)
                        total+=amount
                    if total!=expected:
                        raise HTTPException(422,f"{field.replace('_',' ').title()} components must add up to {expected}")
                    data[field]=components
            data.update({"gross_due":str(gross),"deductions":str(deductions),"net_due":str(net),"payable_on":payable.isoformat()})
        else:
            policy_id=data.get("statutory_policy_id")
            try: policy_id=int(policy_id)
            except (TypeError,ValueError): raise HTTPException(422,"Automatic settlement requires statutory_policy_id")
            if policy_id<=0: raise HTTPException(422,"Automatic settlement requires a valid statutory_policy_id")
            additional=data.get("additional_earnings",[])
            if isinstance(additional,str):
                try: additional=json.loads(additional)
                except (ValueError,TypeError): raise HTTPException(422,"Additional settlement earnings must be valid JSON")
            if not isinstance(additional,list): raise HTTPException(422,"Additional settlement earnings must be a JSON list")
            data["additional_earnings"]=additional
            data["statutory_policy_id"]=policy_id

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
    retention_until:date|None=Form(default=None),
    legal_hold:bool=Form(default=False),
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
                  (employee_id,stored["file_name"],json.dumps({**payload,"expiry_date":expiry_date.isoformat() if expiry_date else None,"retention_until":retention_until.isoformat() if retention_until else None,"legal_hold":legal_hold}),expiry_date,actor,actor)
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

@router.post("/documents/retention/execute")
def execute_document_retention(request:Request):
    actor=_manager(request)
    deleted=0
    try:
        with _hr_connection() as conn:
            with conn.transaction():
                rows=conn.execute(
                    "SELECT * FROM hr_enterprise_records WHERE domain='documents' AND status='archived' "
                    "AND payload->>'retention_until' IS NOT NULL "
                    "AND (payload->>'retention_until')::date<=CURRENT_DATE "
                    "AND COALESCE((payload->>'legal_hold')::boolean,false)=false "
                    "AND payload->>'storage_deleted_at' IS NULL FOR UPDATE"
                ).fetchall()
                for row in rows:
                    payload=dict(row["payload"])
                    try:
                        delete_employee_document(employee_id=int(row["employee_id"]),object_key=payload["object_key"])
                    except EmployeeDocumentError as exc:
                        raise HTTPException(409,f"Retention blocked for document #{row['id']}: {exc}") from exc
                    payload["storage_deleted_at"]=datetime.utcnow().isoformat()+"Z"
                    payload["retention_action"]="private_object_deleted_after_retention"
                    updated=conn.execute(
                        "UPDATE hr_enterprise_records SET payload=%s::jsonb,version=version+1,updated_by_user_id=%s,updated_at=now() "
                        "WHERE id=%s RETURNING *",(json.dumps(payload,default=str),actor,row["id"])
                    ).fetchone()
                    conn.execute(
                        "INSERT INTO hr_enterprise_events(record_id,event_type,before_state,after_state,actor_user_id) "
                        "VALUES(%s,'retention_deleted',%s::jsonb,%s::jsonb,%s)",
                        (row["id"],json.dumps(dict(row),default=str),json.dumps(dict(updated),default=str),actor)
                    )
                    deleted+=1
        return {"deleted":deleted,"message":"Expired archived documents were permanently removed from private object storage"}
    except HTTPException: raise
    except EmployeeDocumentConfigurationError as exc: raise HTTPException(503,str(exc)) from exc
    except psycopg.Error as exc: raise _db_error(exc) from exc


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

@router.post("/recruitment/{candidate_id}/email",status_code=201)
def send_recruitment_candidate_email(candidate_id:int,payload:CandidateEmailInput,request:Request):
    actor=_manager(request)
    try:
        with _hr_connection() as conn:
            candidate=conn.execute(
                "SELECT * FROM hr_enterprise_records WHERE id=%s AND domain='recruitment' "
                "AND payload->>'record_type'='candidate'",(candidate_id,),
            ).fetchone()
            if not candidate:
                raise HTTPException(404,"Recruitment candidate not found")
            recipient=str(candidate["payload"].get("email","")).strip().lower()
            if not recipient:
                raise HTTPException(422,"Candidate profile has no email address")
        send_candidate_email(recipient=recipient,subject=payload.subject,body=payload.message)
        occurred=datetime.utcnow().isoformat()+"Z"
        communication={
            "record_type":"communication","candidate_id":candidate_id,"channel":"email",
            "direction":"outbound","subject":payload.subject.strip(),"message":payload.message.strip(),
            "occurred_at":occurred,"recipient":recipient,"delivery_status":"sent",
        }
        with _hr_connection() as conn:
            with conn.transaction():
                row=conn.execute(
                    "INSERT INTO hr_enterprise_records(domain,title,status,payload,created_by_user_id,updated_by_user_id) "
                    "VALUES('recruitment',%s,'completed',%s::jsonb,%s,%s) RETURNING *",
                    ("Email to "+recipient,json.dumps(communication),actor,actor),
                ).fetchone()
                conn.execute(
                    "INSERT INTO hr_enterprise_events(record_id,event_type,to_status,after_state,actor_user_id) "
                    "VALUES(%s,'candidate_email_sent','completed',%s::jsonb,%s)",
                    (row["id"],json.dumps(dict(row),default=str),actor),
                )
        return {"communication":row,"recipient":recipient,"delivery_status":"sent"}
    except HTTPException: raise
    except CandidateEmailConfigurationError as exc: raise HTTPException(503,str(exc)) from exc
    except CandidateEmailDeliveryError as exc: raise HTTPException(502,str(exc)) from exc
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
                _ensure_offer_unexpired(offer_data.get("expires_on"))
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
                _ensure_candidate_hireable(candidate["status"])
                job_id=int(application["payload"]["job_id"])
                job=conn.execute(
                    "SELECT * FROM hr_enterprise_records WHERE id=%s AND domain='recruitment' "
                    "AND payload->>'record_type'='job_opening' FOR UPDATE",(job_id,)
                ).fetchone()
                if not job or job["status"]!="open":
                    raise HTTPException(409,"The linked job opening is no longer open")
                job_data=dict(job["payload"])
                filled=int(job_data.get("filled_headcount",0));capacity=int(job_data.get("headcount",1))
                if filled>=capacity:
                    raise HTTPException(409,"The job opening has reached its approved headcount")
                candidate_email=str(candidate["payload"].get("email","")).strip().lower()
                if candidate_email!=payload.employee.email.strip().lower():
                    raise HTTPException(422,"Employee email must match the accepted candidate's email")
                employee=payload.employee
                if employee.status not in {"active","probation"}:
                    raise HTTPException(422,"A newly hired employee must start as active or probationary")
                display_name=(employee.first_name+" "+employee.last_name).strip()
                if len(display_name)<2:
                    raise HTTPException(422,"Employee name must contain at least two characters for identity creation")
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
                job_data["filled_headcount"]=filled+1
                next_job_status="closed" if filled+1>=capacity else "open"
                updated_job=conn.execute(
                    "UPDATE hr_enterprise_records SET payload=%s::jsonb,status=%s,version=version+1,updated_by_user_id=%s,updated_at=now() "
                    "WHERE id=%s RETURNING *",
                    (json.dumps(job_data,default=str),next_job_status,actor,job_id),
                ).fetchone()
                conn.execute(
                    "INSERT INTO hr_enterprise_events(record_id,event_type,from_status,to_status,before_state,after_state,actor_user_id) "
                    "VALUES(%s,'headcount_filled',%s,%s,%s::jsonb,%s::jsonb,%s)",
                    (job_id,job["status"],next_job_status,json.dumps(dict(job),default=str),json.dumps(dict(updated_job),default=str),actor),
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


@router.get("/expiring")
def list_expiring_records(request:Request,within_days:int=Query(30,ge=0,le=365)):
    _manager(request)
    try:
        with _hr_connection() as conn:
            rows=conn.execute(
                "SELECT r.*,e.employee_code,e.first_name,e.last_name FROM hr_enterprise_records r "
                "LEFT JOIN hr_employees e ON e.id=r.employee_id "
                "WHERE r.due_date IS NOT NULL AND r.due_date<=CURRENT_DATE+(%s*INTERVAL '1 day') "
                "AND r.status NOT IN ('archived','rejected','expired') "
                "AND ((r.domain='documents' AND r.payload->>'record_type'='employee_document') "
                "OR (r.domain='learning' AND r.payload->>'record_type'='certificate') "
                "OR (r.domain='assets' AND r.payload->>'record_type'='asset') "
                "OR (r.domain='recruitment' AND r.payload->>'record_type'='offer')) "
                "ORDER BY r.due_date,r.id LIMIT 500",
                (within_days,),
            ).fetchall()
            return {"items":rows,"within_days":within_days}
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
              "OR (r.domain='performance' AND r.payload->>'record_type'='review_cycle' AND r.status IN ('active','self_review','manager_review'))) "
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
                if domain=="recruitment" and payload.record_type=="candidate":
                    email=data["email"]
                    conn.execute("SELECT pg_advisory_xact_lock(hashtextextended(%s,0))",(email,))
                    duplicate=conn.execute(
                        "SELECT id FROM hr_enterprise_records WHERE domain='recruitment' "
                        "AND payload->>'record_type'='candidate' AND lower(payload->>'email')=%s "
                        "AND status NOT IN ('archived','withdrawn') LIMIT 1",(email,),
                    ).fetchone()
                    _ensure_no_active_recruitment_duplicate(duplicate,"A candidate with this email already exists; update the existing candidate record")
                if domain=="recruitment" and payload.record_type=="offer":
                    application_id=int(data["application_id"])
                    application_for_offer=conn.execute(
                        "SELECT status FROM hr_enterprise_records WHERE id=%s AND domain='recruitment' "
                        "AND payload->>'record_type'='application' FOR UPDATE",(application_id,),
                    ).fetchone()
                    if not application_for_offer:
                        raise HTTPException(404,"Recruitment application not found")
                    active_offer=conn.execute(
                        "SELECT id FROM hr_enterprise_records WHERE domain='recruitment' "
                        "AND payload->>'record_type'='offer' AND payload->>'application_id'=%s "
                        "AND status NOT IN ('rejected','withdrawn','archived','expired') LIMIT 1",
                        (str(application_id),),
                    ).fetchone()
                    _ensure_no_active_recruitment_duplicate(active_offer,"An active offer already exists for this application")
                    if date.fromisoformat(str(data["expires_on"])) < date.today():
                        raise HTTPException(422,"Offer expiry date cannot be in the past")
                if domain=="recruitment" and payload.record_type=="application":
                    candidate=conn.execute(
                        "SELECT status FROM hr_enterprise_records WHERE id=%s AND domain='recruitment' "
                        "AND payload->>'record_type'='candidate' FOR UPDATE",(int(data["candidate_id"]),),
                    ).fetchone()
                    job=conn.execute(
                        "SELECT status FROM hr_enterprise_records WHERE id=%s AND domain='recruitment' "
                        "AND payload->>'record_type'='job_opening' FOR UPDATE",(int(data["job_id"]),),
                    ).fetchone()
                    if candidate["status"]=="hired":
                        raise HTTPException(409,"A hired candidate cannot be submitted for another application")
                    if not job or job["status"]!="open":
                        raise HTTPException(409,"Applications can be created only for open job openings")
                    duplicate=conn.execute(
                        "SELECT id FROM hr_enterprise_records WHERE domain='recruitment' "
                        "AND payload->>'record_type'='application' AND payload->>'candidate_id'=%s "
                        "AND payload->>'job_id'=%s AND status NOT IN ('rejected','withdrawn','archived') LIMIT 1",
                        (str(data["candidate_id"]),str(data["job_id"])),
                    ).fetchone()
                    _ensure_no_active_recruitment_duplicate(duplicate,"This candidate already has an active application for the selected job")
                if domain=="travel" and payload.record_type=="claim":
                    locked_travel=conn.execute(
                        "SELECT status FROM hr_enterprise_records WHERE id=%s AND domain='travel' FOR UPDATE",
                        (int(data["travel_record_id"]),),
                    ).fetchone()
                    if not locked_travel:
                        raise HTTPException(404,"Travel request not found")
                    _ensure_travel_claimable(locked_travel["status"])
                if domain=="travel" and payload.record_type in {"booking","advance"}:
                    travel_id=int(data["travel_record_id"])
                    travel=conn.execute(
                        "SELECT status,payload FROM hr_enterprise_records WHERE id=%s AND domain='travel' "
                        "AND payload->>'record_type'='request' FOR UPDATE",(travel_id,),
                    ).fetchone()
                    if not travel:
                        raise HTTPException(404,"Travel request not found")
                    if travel["status"] not in {"approved","booked","in_progress"}:
                        raise HTTPException(409,"Travel must be approved before booking or advance processing")
                    if payload.record_type=="booking":
                        booked=conn.execute(
                            "SELECT COALESCE(sum((payload->>'booked_cost')::numeric),0) AS total "
                            "FROM hr_enterprise_records WHERE domain='travel' AND payload->>'record_type'='booking' "
                            "AND payload->>'travel_record_id'=%s AND status NOT IN ('rejected','archived','cancelled')",
                            (str(travel_id),),
                        ).fetchone()["total"]
                        policy=conn.execute(
                            "SELECT payload FROM hr_enterprise_records WHERE id=%s AND domain='travel'",
                            (int(travel["payload"]["policy_id"]),),
                        ).fetchone()
                        _ensure_travel_amount_budget(booked,data["booked_cost"],policy["payload"]["max_trip_cost"],"bookings")
                    else:
                        advances=conn.execute(
                            "SELECT COALESCE(sum((payload->>'requested_amount')::numeric),0) AS total "
                            "FROM hr_enterprise_records WHERE domain='travel' AND payload->>'record_type'='advance' "
                            "AND payload->>'travel_record_id'=%s AND status NOT IN ('rejected','archived','cancelled')",
                            (str(travel_id),),
                        ).fetchone()["total"]
                        _ensure_travel_amount_budget(advances,data["requested_amount"],travel["payload"]["estimated_cost"],"travel advances")
                if domain=="assets" and payload.record_type=="stock_receipt":
                    procurement_id=int(data["procurement_id"])
                    procurement=conn.execute(
                        "SELECT status,payload FROM hr_enterprise_records WHERE id=%s AND domain='assets' "
                        "AND payload->>'record_type'='procurement' FOR UPDATE",(procurement_id,)
                    ).fetchone()
                    if not procurement or procurement["status"] not in {"approved","partially_received"}:
                        raise HTTPException(409,"Stock can be received only against an approved, open procurement")
                    ordered={str(x["description"]).strip():Decimal(str(x["quantity"])) for x in procurement["payload"]["items"]}
                    received={}
                    previous=conn.execute(
                        "SELECT payload FROM hr_enterprise_records WHERE domain='assets' AND payload->>'record_type'='stock_receipt' "
                        "AND payload->>'procurement_id'=%s AND status NOT IN ('archived','rejected') FOR UPDATE",
                        (str(procurement_id),)
                    ).fetchall()
                    for prior in previous:
                        for line in prior["payload"].get("items",[]):
                            key=str(line["description"]).strip()
                            received[key]=received.get(key,Decimal("0"))+Decimal(str(line["quantity"]))
                    for line in data["items"]:
                        key=str(line["description"]).strip()
                        if key not in ordered:
                            raise HTTPException(422,f"Received item '{key}' is not part of the approved procurement")
                        quantity=Decimal(str(line["quantity"]))
                        if received.get(key,Decimal("0"))+quantity>ordered[key]:
                            raise HTTPException(422,f"Received quantity for '{key}' exceeds the ordered quantity")
                        received[key]=received.get(key,Decimal("0"))+quantity
                if domain=="assets" and payload.record_type=="allocation":
                    asset=conn.execute(
                        "SELECT status FROM hr_enterprise_records WHERE id=%s AND domain='assets' "
                        "AND payload->>'record_type'='asset' FOR UPDATE",
                        (int(data["asset_id"]),),
                    ).fetchone()
                    if not asset:
                        raise HTTPException(404,"Asset not found")
                    active_allocation=conn.execute(
                        "SELECT EXISTS(SELECT 1 FROM hr_enterprise_records WHERE domain='assets' "
                        "AND payload->>'record_type'='allocation' AND payload->>'asset_id'=%s "
                        "AND status IN ('requested','approved','assigned','acknowledged')) AS active",
                        (str(data["asset_id"]),),
                    ).fetchone()["active"]
                    _ensure_asset_allocatable(asset["status"],active_allocation)
                if domain=="learning" and payload.record_type=="progress":
                    enrollment=conn.execute("SELECT employee_id FROM hr_enterprise_records WHERE id=%s",(int(data["enrollment_id"]),)).fetchone()
                    if employee_id is None or enrollment["employee_id"] is None or int(employee_id)!=int(enrollment["employee_id"]):
                        raise HTTPException(403,"Learning progress must be recorded by the enrolled employee")
                if domain=="performance" and payload.record_type=="goal" and data.get("weight") not in (None,""):
                    cycle_id=int(data["cycle_id"])
                    cycle=conn.execute("SELECT status FROM hr_enterprise_records WHERE id=%s AND domain='performance' AND payload->>'record_type'='review_cycle' FOR UPDATE",(cycle_id,)).fetchone()
                    if not cycle or cycle["status"] not in {"draft","active","self_review"}:
                        raise HTTPException(409,"Goals can be added only to an editable performance cycle")
                    total=conn.execute(
                        "SELECT COALESCE(sum((payload->>'weight')::numeric),0) AS weight FROM hr_enterprise_records "
                        "WHERE domain='performance' AND payload->>'record_type'='goal' AND payload->>'cycle_id'=%s "
                        "AND status NOT IN ('cancelled','archived')",(str(cycle_id),)
                    ).fetchone()["weight"]
                    _ensure_goal_weight_limit(total,data["weight"])
                if domain=="learning" and payload.record_type=="assessment":
                    enrollment_id=int(data["enrollment_id"])
                    enrollment=conn.execute(
                        "SELECT status,payload FROM hr_enterprise_records WHERE id=%s AND domain='learning' "
                        "AND payload->>'record_type'='enrollment' FOR UPDATE",(enrollment_id,)
                    ).fetchone()
                    if not enrollment or enrollment["status"]!="in_progress":
                        raise HTTPException(409,"Assessment attempts are allowed only while the enrollment is in progress")
                    course=conn.execute(
                        "SELECT payload FROM hr_enterprise_records WHERE id=%s AND domain='learning' "
                        "AND payload->>'record_type'='course'",(int(enrollment["payload"]["course_id"]),)
                    ).fetchone()
                    try:
                        max_attempts=int(course["payload"].get("max_attempts",3))
                    except (TypeError,ValueError):
                        max_attempts=3
                    _ensure_assessment_attempt_limit(0,max_attempts)
                    attempts=conn.execute(
                        "SELECT count(*)::int AS total FROM hr_enterprise_records WHERE domain='learning' "
                        "AND payload->>'record_type'='assessment' AND payload->>'enrollment_id'=%s "
                        "AND status NOT IN ('archived','cancelled')",(str(enrollment_id),)
                    ).fetchone()["total"]
                    _ensure_assessment_attempt_limit(attempts,max_attempts)
                    data["attempt_number"]=attempts+1
                if domain=="assets" and payload.record_type=="allocation":
                    allocation_employee_id=int(data["employee_id"])
                    if employee_id is None:
                        employee_id=allocation_employee_id
                    elif int(employee_id)!=allocation_employee_id:
                        raise HTTPException(422,"Allocation employee must match the linked employee profile")
                if domain=="performance" and payload.record_type in {"review","self_review"} and employee_id is None:
                    raise HTTPException(422,"A performance review must be linked to its subject employee")
                if domain=="travel" and payload.record_type=="request":
                    if employee_id is None:
                        raise HTTPException(422,"A travel request must be linked to an employee")
                    employee_row=conn.execute("SELECT employment_type,job_grade FROM hr_employees WHERE id=%s",(employee_id,)).fetchone()
                    policy=conn.execute("SELECT status,payload FROM hr_enterprise_records WHERE id=%s",(int(data["policy_id"]),)).fetchone()
                    if policy["status"]!="approved":
                        raise HTTPException(409,"The selected travel policy is not active")
                    if policy["payload"]["employment_type"] not in {"all",employee_row["employment_type"]}:
                        raise HTTPException(403,"The selected travel policy does not apply to this employee type")
                    required_grade=policy["payload"].get("job_grade","all")
                    if required_grade not in {"all",employee_row["job_grade"]}:
                        raise HTTPException(403,"The selected travel policy does not apply to this employee job grade")
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
                if domain=="exit" and payload.record_type=="settlement":
                    exit_id=int(data["exit_record_id"])
                    exit_case=conn.execute(
                        "SELECT employee_id FROM hr_enterprise_records WHERE id=%s AND domain='exit' "
                        "AND payload->>'record_type'='case' FOR UPDATE",(exit_id,)
                    ).fetchone()
                    if not exit_case or exit_case["employee_id"] is None:
                        raise HTTPException(409,"Full-and-final settlement requires an employee-linked exit case")
                    existing_settlement=conn.execute(
                        "SELECT id FROM hr_enterprise_records WHERE domain='exit' AND payload->>'record_type'='settlement' "
                        "AND payload->>'exit_record_id'=%s AND status NOT IN ('rejected','archived') LIMIT 1",(str(exit_id),)
                    ).fetchone()
                    if existing_settlement:
                        raise HTTPException(409,"A full-and-final settlement already exists for this exit case")
                    payable=date.fromisoformat(str(data["payable_on"]))
                    if data.get("auto_calculate") is True:
                        policy_id=int(data.get("statutory_policy_id") or 0)
                        if policy_id<=0: raise HTTPException(422,"Select an approved exit statutory policy to calculate final settlement")
                        employee=conn.execute(
                            "SELECT e.id,e.joining_date,sp.establishment_id,sp.pf_applicable_override,sp.esi_applicable_override,sp.pt_applicable_override "
                            "FROM hr_employees e JOIN hr_employee_statutory_profiles sp ON sp.employee_id=e.id WHERE e.id=%s FOR UPDATE",
                            (int(exit_case["employee_id"]),)
                        ).fetchone()
                        if not employee or not employee["joining_date"]:
                            raise HTTPException(409,"Employee joining date and statutory establishment profile are required for automatic settlement")
                        policy=conn.execute(
                            "SELECT * FROM hr_exit_statutory_policy_versions WHERE id=%s AND establishment_id=%s "
                            "AND status='approved' AND effective_from<=%s AND (effective_to IS NULL OR effective_to>=%s) FOR SHARE",
                            (policy_id,employee["establishment_id"],payable,payable)
                        ).fetchone()
                        if not policy: raise HTTPException(409,"No approved exit statutory policy is effective for this employee and payable date")
                        salary=conn.execute(
                            "SELECT basic_salary,hra,special_allowance,other_allowance FROM hr_employee_salary_versions "
                            "WHERE employee_id=%s AND status='approved' AND effective_from<=%s AND (effective_to IS NULL OR effective_to>=%s) "
                            "ORDER BY effective_from DESC LIMIT 1 FOR SHARE",
                            (int(exit_case["employee_id"]),payable,payable)
                        ).fetchone()
                        if not salary: raise HTTPException(409,"An approved salary version effective on the settlement date is required")
                        basic=Decimal(str(salary["basic_salary"]))
                        gross_monthly=sum((Decimal(str(salary[k])) for k in ("basic_salary","hra","special_allowance","other_allowance")),Decimal("0"))
                        leave_rows=conn.execute(
                            "SELECT DISTINCT ON (b.leave_type) b.leave_type,GREATEST(0,b.closing_days+COALESCE((SELECT sum(l.quantity_days) "
                            "FROM hr_leave_ledger l WHERE l.employee_id=b.employee_id AND l.leave_type=b.leave_type "
                            "AND l.created_at>b.calculated_at AND l.effective_date<=%s),0)) AS balance FROM hr_leave_balances b "
                            "WHERE b.employee_id=%s AND b.period_end<=%s ORDER BY b.leave_type,b.period_end DESC",
                            (payable,int(exit_case["employee_id"]),payable)
                        ).fetchall()
                        leave_balances={r["leave_type"]:Decimal(str(r["balance"])) for r in leave_rows}
                        loans=conn.execute(
                            "SELECT id,loan_reference,outstanding_amount FROM hr_employee_loans "
                            "WHERE employee_id=%s AND status IN ('approved','active') AND outstanding_amount>0 FOR UPDATE",
                            (int(exit_case["employee_id"]),)
                        ).fetchall()
                        case_payload=conn.execute("SELECT payload FROM hr_enterprise_records WHERE id=%s",(exit_id,)).fetchone()["payload"]
                        notice_total=int(case_payload.get("notice_days") or 0)
                        notice_served=int(case_payload.get("notice_days_served") or 0)
                        notice_unserved=max(0,notice_total-notice_served)
                        service_days=(payable-employee["joining_date"]).days
                        service_years=Decimal(max(0,service_days))/Decimal("365.2425")
                        calculated=calculate_exit_settlement(
                            config=policy["policy_config"],monthly_basic=basic,monthly_gross=gross_monthly,
                            service_years=service_years,leave_balances=leave_balances,
                            loan_balances=[dict(x) for x in loans],notice_days_unserved=notice_unserved,
                            additional_earnings=data.get("additional_earnings",[])
                        )
                        if Decimal(calculated["net_due"])<0:
                            raise HTTPException(409,"Configured exit deductions exceed payable earnings; review statutory and loan recovery policy before settlement")
                        data.update(calculated)
                        data["statutory_policy_id"]=policy_id
                        data["jurisdiction_code"]=policy["jurisdiction_code"]
                        data["calculation_policy_version_id"]=policy_id
                    gross=Decimal(str(data["gross_due"])); deductions=Decimal(str(data["deductions"])); net=Decimal(str(data["net_due"]))
                    if gross-deductions!=net:
                        raise HTTPException(422,"Exit settlement net due must equal gross due less deductions")
                    period_start=payable.replace(day=1)
                    next_month=(period_start.replace(day=28)+timedelta(days=4)).replace(day=1)
                    period_end=next_month-timedelta(days=1)
                    adjustment_id=None
                    if Decimal(str(data["net_due"]))>0:
                        closed_period=conn.execute(
                            "SELECT id FROM hr_payroll_runs WHERE period_start=%s AND period_end=%s "
                            "AND status IN ('approved','paid') LIMIT 1",(period_start,period_end)
                        ).fetchone()
                        if closed_period:
                            raise HTTPException(409,"The settlement payroll period is already approved or paid; choose a future payable date")
                        adjustment=conn.execute(
                            "INSERT INTO hr_payroll_earning_adjustments(employee_id,earning_type,period_start,period_end,amount,reason,created_by_user_id) "
                            "VALUES(%s,'final_settlement',%s,%s,%s,%s,%s) RETURNING id",
                            (exit_case["employee_id"],period_start,period_end,data["net_due"],
                             f"Full-and-final settlement for exit case #{exit_id}",actor)
                        ).fetchone()
                        adjustment_id=adjustment["id"]
                    data["payroll_adjustment_id"]=adjustment_id
                    for component in data.get("deductions_breakdown",[]):
                        if component.get("type")=="employee_loan_recovery":
                            loan_id=int(component["loan_id"])
                            amount=Decimal(str(component["amount"]))
                            loan=conn.execute("SELECT outstanding_amount FROM hr_employee_loans WHERE id=%s AND employee_id=%s FOR UPDATE",
                                (loan_id,int(exit_case["employee_id"]))).fetchone()
                            if not loan or amount>Decimal(str(loan["outstanding_amount"])):
                                raise HTTPException(409,"Employee loan balance changed; recalculate the settlement")
                            conn.execute("UPDATE hr_employee_loans SET outstanding_amount=outstanding_amount-%s,status=CASE WHEN outstanding_amount-%s=0 THEN 'closed' ELSE 'active' END,updated_at=now() WHERE id=%s",
                                (amount,amount,loan_id))
                            conn.execute(
                                "INSERT INTO hr_employee_loan_transactions(loan_id,transaction_type,amount,transaction_date,reference,payroll_adjustment_id,created_by_user_id) "
                                "VALUES(%s,'settlement_recovery',%s,%s,%s,%s,%s)",
                                (loan_id,amount,payable,f"Exit settlement #{exit_id}",adjustment_id,actor)
                            )
                if domain=="analytics" and payload.record_type=="report":
                    interval=7 if data.get("frequency")=="weekly" else 30
                    data["next_run_at"]=(datetime.utcnow()+timedelta(days=interval)).isoformat()+"Z"
                data["record_type"]=payload.record_type
                status=_initial_status(domain,payload.record_type)
                due_date=payload.due_date
                if due_date is None:
                    if domain=="learning" and payload.record_type=="certificate":
                        due_date=date.fromisoformat(str(data["valid_until"]))
                    elif domain=="recruitment" and payload.record_type=="offer":
                        due_date=date.fromisoformat(str(data["expires_on"]))
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
                if domain=="travel" and payload.record_type=="booking":
                    travel=conn.execute(
                        "SELECT employee_id,payload FROM hr_enterprise_records WHERE id=%s FOR UPDATE",
                        (int(data["travel_record_id"]),)
                    ).fetchone()
                    if not travel or travel["employee_id"] is None:
                        raise HTTPException(409,"Travel booking requires an employee-linked travel request")
                    policy=conn.execute("SELECT payload FROM hr_enterprise_records WHERE id=%s",(int(travel["payload"]["policy_id"]),)).fetchone()
                    data["currency"]=str(data.get("currency") or policy["payload"].get("currency","INR")).upper()
                    provider_result=create_provider_booking(travel={**travel["payload"],"employee_id":travel["employee_id"]},
                        booking=data,record_id=row["id"])
                    if Decimal(provider_result["booked_cost"])>Decimal(str(policy["payload"]["max_trip_cost"])):
                        raise HTTPException(502,"Travel provider confirmed an amount above the approved policy ceiling; contact the provider before retrying")
                    data.update(provider_result)
                    row=conn.execute(
                        "UPDATE hr_enterprise_records SET payload=%s::jsonb,updated_at=now(),version=version+1 WHERE id=%s RETURNING *",
                        (json.dumps(data,default=str),row["id"])
                    ).fetchone()
                    conn.execute(
                        "INSERT INTO hr_enterprise_events(record_id,event_type,after_state,actor_user_id) VALUES(%s,'travel_provider_booking_confirmed',%s::jsonb,%s)",
                        (row["id"],json.dumps(dict(row),default=str),actor)
                    )
                if domain=="travel" and payload.record_type=="advance":
                    travel=conn.execute("SELECT employee_id FROM hr_enterprise_records WHERE id=%s",(int(data["travel_record_id"]),)).fetchone()
                    if not travel or travel["employee_id"] is None:
                        raise HTTPException(409,"Travel advance requires an employee-linked travel request")
                    employee_id=travel["employee_id"]
                    row=conn.execute("UPDATE hr_enterprise_records SET employee_id=%s WHERE id=%s RETURNING *",(employee_id,row["id"])).fetchone()
                if domain=="assets" and payload.record_type=="stock_receipt":
                    procurement_id=int(data["procurement_id"])
                    procurement=conn.execute("SELECT * FROM hr_enterprise_records WHERE id=%s AND domain='assets' FOR UPDATE",(procurement_id,)).fetchone()
                    received_rows=conn.execute(
                        "SELECT payload FROM hr_enterprise_records WHERE domain='assets' AND payload->>'record_type'='stock_receipt' "
                        "AND payload->>'procurement_id'=%s AND status NOT IN ('archived','rejected')",(str(procurement_id),)
                    ).fetchall()
                    received_totals={}
                    for receipt in received_rows:
                        for line in receipt["payload"].get("items",[]):
                            key=str(line["description"]).strip()
                            received_totals[key]=received_totals.get(key,Decimal("0"))+Decimal(str(line["quantity"]))
                    fully_received=all(received_totals.get(str(line["description"]).strip(),Decimal("0"))>=Decimal(str(line["quantity"])) for line in procurement["payload"]["items"])
                    next_status="received" if fully_received else "partially_received"
                    if procurement["status"]!=next_status:
                        updated_procurement=conn.execute(
                            "UPDATE hr_enterprise_records SET status=%s,version=version+1,updated_by_user_id=%s,updated_at=now() WHERE id=%s RETURNING *",
                            (next_status,actor,procurement_id)
                        ).fetchone()
                        conn.execute(
                            "INSERT INTO hr_enterprise_events(record_id,event_type,from_status,to_status,before_state,after_state,actor_user_id) "
                            "VALUES(%s,'stock_received',%s,%s,%s::jsonb,%s::jsonb,%s)",
                            (procurement_id,procurement["status"],next_status,json.dumps(dict(procurement),default=str),json.dumps(dict(updated_procurement),default=str),actor)
                        )
                if domain=="travel" and payload.record_type=="claim":
                    travel_id=int(data["travel_record_id"])
                    travel=conn.execute("SELECT * FROM hr_enterprise_records WHERE id=%s AND domain='travel' FOR UPDATE",(travel_id,)).fetchone()
                    updated_travel=conn.execute("UPDATE hr_enterprise_records SET status='claimed',version=version+1,updated_by_user_id=%s,updated_at=now() WHERE id=%s RETURNING *",
                        (actor,travel_id)).fetchone()
                    conn.execute("INSERT INTO hr_enterprise_events(record_id,event_type,from_status,to_status,before_state,after_state,actor_user_id) VALUES(%s,'claim_submitted','completed','claimed',%s::jsonb,%s::jsonb,%s)",
                        (travel_id,json.dumps(dict(travel),default=str),json.dumps(dict(updated_travel),default=str),actor))
        return row
    except HTTPException: raise
    except TravelIntegrationConfigurationError as exc: raise HTTPException(503,str(exc)) from exc
    except psycopg.Error as exc: raise _db_error(exc) from exc

@router.get("/analytics/enterprise")
def enterprise_workflow_analytics(
    request:Request,
    from_date:date=Query(...),
    to_date:date=Query(...),
    domain_filter:str|None=Query(None,alias="domain",pattern="^(documents|performance|learning|assets|travel|exit|analytics)$"),
    record_type:str|None=Query(None,max_length=48),
    status:str|None=Query(None,max_length=32),
    department_id:int|None=Query(None,gt=0),
):
    """Computed operational KPIs for the seven non-recruitment HR domains."""
    _manager(request)
    if to_date < from_date:
        raise HTTPException(422,"Report end date cannot precede its start date")
    try:
        with _hr_connection() as conn:
            clauses=["domain IN ('documents','performance','learning','assets','travel','exit','analytics')","created_at::date BETWEEN %s AND %s"]
            params=[from_date,to_date]
            if domain_filter:
                clauses.append("domain=%s");params.append(domain_filter)
            if record_type:
                clauses.append("payload->>'record_type'=%s");params.append(record_type)
            if status:
                clauses.append("status=%s");params.append(status)
            if department_id:
                clauses.append("employee_id IN (SELECT id FROM hr_employees WHERE department_id=%s)");params.append(department_id)
            rows=conn.execute(
                "SELECT domain,payload->>'record_type' AS record_type,status,count(*)::int AS records,"
                "count(*) FILTER (WHERE due_date<CURRENT_DATE AND status NOT IN "
                "('archived','rejected','expired','completed','cancelled','withdrawn','written_off','reimbursed'))::int AS overdue,"
                "count(*) FILTER (WHERE due_date BETWEEN CURRENT_DATE AND CURRENT_DATE+INTERVAL '30 days' "
                "AND status NOT IN ('archived','rejected','expired','completed','cancelled','withdrawn','written_off','reimbursed'))::int AS due_soon "
                "FROM hr_enterprise_records WHERE "+" AND ".join(clauses)+" "
                "GROUP BY domain,payload->>'record_type',status ORDER BY domain,record_type,status",
                tuple(params),
            ).fetchall()
        summary={}
        for row in rows:
            domain=row["domain"]
            bucket=summary.setdefault(domain,{"records":0,"overdue":0,"due_soon":0,"by_type":{},"by_status":{}})
            count=int(row["records"] or 0)
            bucket["records"]+=count
            bucket["overdue"]+=int(row["overdue"] or 0)
            bucket["due_soon"]+=int(row["due_soon"] or 0)
            record_type=row["record_type"] or "other"
            bucket["by_type"][record_type]=bucket["by_type"].get(record_type,0)+count
            bucket["by_status"][row["status"]]=bucket["by_status"].get(row["status"],0)+count
        return {"from_date":from_date,"to_date":to_date,"domains":summary}
    except HTTPException: raise
    except psycopg.Error as exc: raise _db_error(exc) from exc


@router.post("/analytics/scheduled/run")
def run_scheduled_analytics_reports(request:Request):
    actor=_manager(request)
    processed=[]
    try:
        with _hr_connection() as conn:
            with conn.transaction():
                due=conn.execute(
                    "SELECT * FROM hr_enterprise_records WHERE domain='analytics' "
                    "AND payload->>'record_type'='report' AND status='scheduled' "
                    "AND payload->>'next_run_at' IS NOT NULL "
                    "AND (payload->>'next_run_at')::timestamptz<=now() FOR UPDATE SKIP LOCKED"
                ).fetchall()
                for row in due:
                    payload=dict(row["payload"])
                    frequency=payload.get("frequency","weekly")
                    today=date.today()
                    if frequency=="monthly":
                        first_this_month=today.replace(day=1)
                        period_end=first_this_month-timedelta(days=1)
                        period_start=period_end.replace(day=1)
                        next_run=(first_this_month.replace(day=28)+timedelta(days=4)).replace(day=1)
                    else:
                        period_end=today
                        period_start=today-timedelta(days=7)
                        next_run=today+timedelta(days=7)
                    filters=payload.get("filters",{})
                    if payload.get("report_type")=="workforce":
                        result=hr_overview(request,period_end.strftime("%Y-%m"))
                    else:
                        result=enterprise_workflow_analytics(
                            request,period_start,period_end,filters.get("domain"),
                            filters.get("record_type"),filters.get("status"),
                            int(filters["department_id"]) if filters.get("department_id") else None
                        )
                    payload["last_result"]=result
                    payload["last_run_at"]=datetime.utcnow().isoformat()+"Z"
                    payload["last_period"]={"from_date":period_start.isoformat(),"to_date":period_end.isoformat()}
                    payload["next_run_at"]=datetime.combine(next_run,datetime.min.time()).isoformat()+"Z"
                    updated=conn.execute(
                        "UPDATE hr_enterprise_records SET payload=%s::jsonb,version=version+1,updated_by_user_id=%s,updated_at=now() "
                        "WHERE id=%s RETURNING *",(json.dumps(payload,default=str),actor,row["id"])
                    ).fetchone()
                    conn.execute(
                        "INSERT INTO hr_enterprise_events(record_id,event_type,before_state,after_state,actor_user_id) "
                        "VALUES(%s,'scheduled_report_generated',%s::jsonb,%s::jsonb,%s)",
                        (row["id"],json.dumps(dict(row),default=str),json.dumps(dict(updated),default=str),actor)
                    )
                    processed.append({"report_id":row["id"],"period":payload["last_period"],"next_run_at":payload["next_run_at"]})
        return {"processed":len(processed),"reports":processed}
    except HTTPException: raise
    except psycopg.Error as exc: raise _db_error(exc) from exc


@router.get("/analytics/enterprise/export")
def export_enterprise_analytics(
    request:Request,
    from_date:date=Query(...),
    to_date:date=Query(...),
    format:str=Query("csv",pattern="^(csv|xlsx|pdf)$"),
    domain_filter:str|None=Query(None,alias="domain",pattern="^(documents|performance|learning|assets|travel|exit|analytics)$"),
    record_type:str|None=Query(None,max_length=48),
    status:str|None=Query(None,max_length=32),
    department_id:int|None=Query(None,gt=0),
):
    report=enterprise_workflow_analytics(request,from_date,to_date,domain_filter,record_type,status,department_id)
    summary=report["domains"]
    headers=["Domain","Records","Overdue","Due within 30 days","By type","By status"]
    rows=[headers]
    for domain,value in sorted(summary.items()):
        rows.append([domain,value["records"],value["overdue"],value["due_soon"],
                     json.dumps(value["by_type"],sort_keys=True),json.dumps(value["by_status"],sort_keys=True)])
    filename=f"hr-enterprise-{from_date.isoformat()}-{to_date.isoformat()}"
    if format=="csv":
        output=io.StringIO()
        writer=csv.writer(output)
        writer.writerows(rows)
        return Response(output.getvalue(),media_type="text/csv; charset=utf-8",
                        headers={"Content-Disposition":f'attachment; filename="{filename}.csv"'})
    if format=="xlsx":
        workbook=Workbook()
        sheet=workbook.active
        sheet.title="Domain summary"
        for row in rows: sheet.append(row)
        sheet.freeze_panes="A2"
        sheet.auto_filter.ref=sheet.dimensions
        for column,width in {"A":20,"B":14,"C":14,"D":22,"E":48,"F":48}.items():
            sheet.column_dimensions[column].width=width
        detail=workbook.create_sheet("Breakdown")
        detail.append(["Domain","Breakdown","Value"])
        for domain,value in sorted(summary.items()):
            for kind,counts in (("Record type",value["by_type"]),("Status",value["by_status"])):
                for name,count in sorted(counts.items()):
                    detail.append([domain,kind+":"+name,count])
        buffer=io.BytesIO()
        workbook.save(buffer)
        return Response(buffer.getvalue(),media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                        headers={"Content-Disposition":f'attachment; filename="{filename}.xlsx"'})
    buffer=io.BytesIO()
    document=SimpleDocTemplate(buffer,pagesize=landscape(A4),title="HR enterprise analytics")
    styles=getSampleStyleSheet()
    story=[Paragraph("HR enterprise analytics",styles["Title"]),
           Paragraph(f"Reporting period: {from_date.isoformat()} to {to_date.isoformat()}",styles["Normal"]),
           Spacer(1,12)]
    pdf_rows=[["Domain","Records","Overdue","Due in 30 days"]]
    for domain,value in sorted(summary.items()):
        pdf_rows.append([domain,str(value["records"]),str(value["overdue"]),str(value["due_soon"])])
    table=Table(pdf_rows,repeatRows=1)
    table.setStyle(TableStyle([
        ("BACKGROUND",(0,0),(-1,0),colors.HexColor("#24364b")),
        ("TEXTCOLOR",(0,0),(-1,0),colors.white),
        ("GRID",(0,0),(-1,-1),0.5,colors.HexColor("#b8c2cc")),
        ("PADDING",(0,0),(-1,-1),7),
        ("ROWBACKGROUNDS",(0,1),(-1,-1),[colors.white,colors.HexColor("#f2f5f8")]),
    ]))
    story.append(table)
    document.build(story)
    return Response(buffer.getvalue(),media_type="application/pdf",
                    headers={"Content-Disposition":f'attachment; filename="{filename}.pdf"'})


@router.post("/notifications/refresh")
def refresh_expiry_notifications(request:Request):
    actor=_manager(request)
    created=0
    try:
        with _hr_connection() as conn:
            with conn.transaction():
                due=conn.execute(
                    "SELECT id,employee_id,domain,title,due_date,payload->>'record_type' AS record_type "
                    "FROM hr_enterprise_records WHERE domain IN ('documents','learning','assets') "
                    "AND payload->>'record_type' IN ('employee_document','certificate','asset') "
                    "AND employee_id IS NOT NULL AND due_date IS NOT NULL "
                    "AND due_date<=CURRENT_DATE+INTERVAL '30 days' "
                    "AND status NOT IN ('archived','rejected','written_off','cancelled') "
                    "ORDER BY due_date,id"
                ).fetchall()
                for item in due:
                    kind="overdue" if item["due_date"]<date.today() else "due_soon"
                    label={"employee_document":"Employee document","certificate":"Learning certificate","asset":"Asset warranty"}.get(item["record_type"],"HR record")
                    message=f"{label} '{item['title']}' is {'overdue' if kind=='overdue' else 'due soon'} on {item['due_date'].isoformat()}."
                    result=conn.execute(
                        "INSERT INTO hr_enterprise_notifications(employee_id,record_id,notification_type,title,message,due_date) "
                        "VALUES(%s,%s,%s,%s,%s,%s) ON CONFLICT(employee_id,record_id,notification_type) "
                        "DO UPDATE SET title=EXCLUDED.title,message=EXCLUDED.message,due_date=EXCLUDED.due_date "
                        "RETURNING (xmax=0) AS inserted",
                        (item["employee_id"],item["id"],kind,label,message,item["due_date"])
                    ).fetchone()
                    if result and result["inserted"]:
                        created+=1
        return {"created":created,"message":"Expiry notifications refreshed"}
    except psycopg.Error as exc: raise _db_error(exc) from exc


@router.get("/notifications")
def list_expiry_notifications(request:Request,unread_only:bool=False,limit:int=Query(100,ge=1,le=500)):
    actor=_actor(request)
    try:
        with _hr_connection() as conn:
            if _role(request) in MANAGER_ROLES:
                rows=conn.execute(
                    "SELECT n.*,e.employee_code,e.first_name,e.last_name,r.domain,r.title AS record_title "
                    "FROM hr_enterprise_notifications n JOIN hr_employees e ON e.id=n.employee_id "
                    "JOIN hr_enterprise_records r ON r.id=n.record_id "
                    "WHERE (%s=false OR n.status='unread') ORDER BY n.due_date,n.id LIMIT %s",
                    (unread_only,limit)
                ).fetchall()
            else:
                own=_employee(conn,actor)
                rows=conn.execute(
                    "SELECT n.*,r.domain,r.title AS record_title FROM hr_enterprise_notifications n "
                    "JOIN hr_enterprise_records r ON r.id=n.record_id WHERE n.employee_id=%s "
                    "AND (%s=false OR n.status='unread') ORDER BY n.due_date,n.id LIMIT %s",
                    (own["id"],unread_only,limit)
                ).fetchall()
        return {"items":rows}
    except psycopg.Error as exc: raise _db_error(exc) from exc


@router.post("/notifications/{notification_id}/read")
def mark_expiry_notification_read(notification_id:int,request:Request):
    actor=_actor(request)
    try:
        with _hr_connection() as conn:
            with conn.transaction():
                row=conn.execute(
                    "SELECT * FROM hr_enterprise_notifications WHERE id=%s FOR UPDATE",(notification_id,)
                ).fetchone()
                if not row: raise HTTPException(404,"HR notification not found")
                if _role(request) not in MANAGER_ROLES:
                    own=_employee(conn,actor)
                    if int(row["employee_id"])!=int(own["id"]):
                        raise HTTPException(403,"Employees may update only their own HR notifications")
                return conn.execute(
                    "UPDATE hr_enterprise_notifications SET status='read',read_at=now() WHERE id=%s RETURNING *",
                    (notification_id,)
                ).fetchone()
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
                if domain=="travel" and old["payload"].get("record_type")=="travel_policy":
                    raise HTTPException(409,"Travel policies are versioned; archive the old policy and create a replacement")
                if old["version"]!=payload.expected_version: raise HTTPException(409,"Record changed since it was loaded; refresh before editing")
                data=dict(old["payload"])
                if payload.payload is not None:
                    record_type=data.get("record_type")
                    data=_validate(domain,record_type,payload.payload)
                    _validate_references(conn,domain,record_type,data)
                    if domain=="performance" and record_type=="goal" and data.get("weight") not in (None,""):
                        cycle_id=int(data["cycle_id"])
                        cycle=conn.execute(
                            "SELECT status FROM hr_enterprise_records WHERE id=%s AND domain='performance' "
                            "AND payload->>'record_type'='review_cycle' FOR UPDATE",(cycle_id,)
                        ).fetchone()
                        if not cycle or cycle["status"] not in {"draft","active","self_review"}:
                            raise HTTPException(409,"Goals can be edited only while the performance cycle is editable")
                        existing_weight=conn.execute(
                            "SELECT COALESCE(sum((payload->>'weight')::numeric),0) AS weight "
                            "FROM hr_enterprise_records WHERE domain='performance' AND payload->>'record_type'='goal' "
                            "AND payload->>'cycle_id'=%s AND id<>%s AND status NOT IN ('cancelled','archived')",
                            (str(cycle_id),record_id)
                        ).fetchone()["weight"]
                        _ensure_goal_weight_limit(existing_weight,data["weight"])
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
                if payload.status not in _allowed_record_transitions(domain,old["payload"].get("record_type"),old["status"]):
                    raise HTTPException(409,f"Transition from {old['status']} to {payload.status} is not allowed for this {old['payload'].get('record_type','record').replace('_',' ')}")
                record_type=old["payload"].get("record_type")
                if domain=="travel" and record_type=="travel_policy":
                    raise HTTPException(409,"Travel policies are managed by archiving the old version and creating a new version")
                if domain=="documents" and payload.status in {"verified","rejected"} and not (payload.note and payload.note.strip()):
                    raise HTTPException(422,"A verification or rejection note is required for employee documents")
                if domain=="performance" and record_type=="review_cycle" and payload.status=="active":
                    goal_summary=conn.execute(
                        "SELECT count(*)::int AS total,COALESCE(sum((payload->>'weight')::numeric),0) AS weight "
                        "FROM hr_enterprise_records WHERE domain='performance' AND payload->>'record_type'='goal' "
                        "AND payload->>'cycle_id'=%s AND status NOT IN ('cancelled','archived')",
                        (str(record_id),)
                    ).fetchone()
                    if goal_summary["total"]==0 or Decimal(str(goal_summary["weight"]))!=Decimal("100"):
                        raise HTTPException(409,"A performance cycle can start only when its active goals have weights totalling exactly 100 percent")
                if domain=="documents" and payload.status=="verified" and old["payload"].get("malware_scan_status")!="clean":
                    raise HTTPException(409,"Employee documents cannot be verified until a clean malware scan is recorded; re-upload after scanner configuration")
                if domain=="recruitment" and payload.status=="rejected" and not (payload.note and payload.note.strip()):
                    raise HTTPException(422,"A rejection reason is required for recruitment decisions")
                if domain=="recruitment" and record_type=="job_opening" and payload.status=="closed":
                    job_payload=dict(old["payload"])
                    _ensure_job_opening_closable(job_payload.get("filled_headcount",0),job_payload.get("headcount",0))
                if domain=="exit" and record_type=="settlement" and payload.status=="completed":
                    adjustment_id=int(old["payload"].get("payroll_adjustment_id") or 0)
                    if adjustment_id:
                        paid=conn.execute(
                            "SELECT EXISTS(SELECT 1 FROM hr_payroll_earning_adjustments a "
                            "JOIN hr_payroll_runs r ON r.id=a.payroll_run_id "
                            "WHERE a.id=%s AND a.earning_type='final_settlement' AND a.status='approved' AND r.status='paid') AS paid",
                            (adjustment_id,)
                        ).fetchone()["paid"]
                        if not paid:
                            raise HTTPException(409,"The final-settlement payroll adjustment must be approved and paid before closing the settlement")
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
                if domain=="travel" and record_type=="advance" and payload.status=="disbursed":
                    if old["employee_id"] is None:
                        raise HTTPException(409,"Travel advance must be linked to an employee before disbursement")
                    travel=conn.execute("SELECT payload FROM hr_enterprise_records WHERE id=%s AND domain='travel'",(int(old["payload"]["travel_record_id"]),)).fetchone()
                    if not travel:
                        raise HTTPException(409,"Linked travel request no longer exists")
                    already=conn.execute("SELECT accounting_voucher_id FROM hr_travel_advance_disbursements WHERE enterprise_record_id=%s",(record_id,)).fetchone()
                    if already:
                        raise HTTPException(409,"This travel advance has already been disbursed")
                    try:
                        voucher_id=disburse_travel_advance(conn,record_id=record_id,employee_id=int(old["employee_id"]),
                            amount=Decimal(str(old["payload"]["requested_amount"])),
                            currency=str(travel["payload"].get("currency","INR")),actor_user_id=actor)
                    except TravelIntegrationConfigurationError as exc:
                        raise HTTPException(503,str(exc)) from exc
                    advance_payload=dict(old["payload"])
                    advance_payload.update({"accounting_voucher_id":voucher_id,"disbursed_at":datetime.utcnow().isoformat()+"Z"})
                    old=conn.execute("UPDATE hr_enterprise_records SET payload=%s::jsonb,version=version+1,updated_by_user_id=%s,updated_at=now() WHERE id=%s RETURNING *",
                        (json.dumps(advance_payload,default=str),actor,record_id)).fetchone()
                    conn.execute("INSERT INTO hr_travel_advance_disbursements(enterprise_record_id,employee_id,accounting_voucher_id,amount,currency,disbursed_by_user_id) VALUES(%s,%s,%s,%s,%s,%s)",
                        (record_id,int(old["employee_id"]),voucher_id,advance_payload["requested_amount"],str(travel["payload"].get("currency","INR")).upper(),actor))
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
                  (record_id,old["status"],json.dumps(dict(old),default=str),json.dumps(dict(row),default=str),actor))
        return row
    except HTTPException: raise
    except psycopg.Error as exc: raise _db_error(exc) from exc

@router.post("/exit/statutory-policies",status_code=201)
def create_exit_statutory_policy(payload:ExitStatutoryPolicyInput,request:Request):
    actor=_manager(request)
    if payload.effective_to and payload.effective_to<payload.effective_from:
        raise HTTPException(422,"Policy effective_to cannot precede effective_from")
    config=validate_exit_policy(payload.policy_config)
    if not all(str(item.get("title") or item.get("url") or "").strip() for item in payload.source_references):
        raise HTTPException(422,"Every statutory policy source reference needs a title or URL")
    try:
        with _hr_connection() as conn:
            with conn.transaction():
                if not conn.execute("SELECT id FROM hr_establishments WHERE id=%s AND is_active=true",(payload.establishment_id,)).fetchone():
                    raise HTTPException(404,"Active HR establishment not found")
                return conn.execute(
                    "INSERT INTO hr_exit_statutory_policy_versions(establishment_id,version_label,jurisdiction_code,effective_from,effective_to,policy_config,source_references,created_by_user_id) "
                    "VALUES(%s,%s,%s,%s,%s,%s::jsonb,%s::jsonb,%s) RETURNING *",
                    (payload.establishment_id,payload.version_label.strip(),payload.jurisdiction_code.upper(),
                     payload.effective_from,payload.effective_to,json.dumps(config),json.dumps(payload.source_references),actor)
                ).fetchone()
    except HTTPException: raise
    except psycopg.Error as exc: raise _db_error(exc) from exc


@router.post("/exit/statutory-policies/{policy_id}/approve")
def approve_exit_statutory_policy(policy_id:int,request:Request):
    actor=_manager(request)
    try:
        with _hr_connection() as conn:
            with conn.transaction():
                policy=conn.execute("SELECT * FROM hr_exit_statutory_policy_versions WHERE id=%s FOR UPDATE",(policy_id,)).fetchone()
                if not policy: raise HTTPException(404,"Exit statutory policy not found")
                if policy["status"]!="draft": raise HTTPException(409,"Only draft exit statutory policies can be approved")
                if policy["created_by_user_id"]==actor: raise HTTPException(403,"A different authorised manager must approve the exit statutory policy")
                overlap=conn.execute(
                    "SELECT id FROM hr_exit_statutory_policy_versions WHERE establishment_id=%s AND jurisdiction_code=%s "
                    "AND status='approved' AND effective_from<=COALESCE(%s,'9999-12-31') "
                    "AND COALESCE(effective_to,'9999-12-31')>=%s LIMIT 1",
                    (policy["establishment_id"],policy["jurisdiction_code"],policy["effective_to"],policy["effective_from"])
                ).fetchone()
                if overlap: raise HTTPException(409,"An approved exit statutory policy already overlaps this effective period")
                return conn.execute(
                    "UPDATE hr_exit_statutory_policy_versions SET status='approved',approved_by_user_id=%s,approved_at=now() WHERE id=%s RETURNING *",
                    (actor,policy_id)
                ).fetchone()
    except HTTPException: raise
    except psycopg.Error as exc: raise _db_error(exc) from exc


@router.get("/exit/statutory-policies")
def list_exit_statutory_policies(request:Request,establishment_id:int|None=Query(None,gt=0)):
    _manager(request)
    with _hr_connection() as conn:
        return {"items":conn.execute(
            "SELECT p.*,e.code AS establishment_code,e.display_name FROM hr_exit_statutory_policy_versions p "
            "JOIN hr_establishments e ON e.id=p.establishment_id WHERE (%s::bigint IS NULL OR p.establishment_id=%s) "
            "ORDER BY p.effective_from DESC,p.id DESC",(establishment_id,establishment_id)
        ).fetchall()}


@router.post("/exit/loans",status_code=201)
def create_employee_loan(payload:EmployeeLoanInput,request:Request):
    actor=_manager(request)
    if payload.currency.upper()!="INR": raise HTTPException(422,"Employee loan ledger currently supports INR")
    try:
        with _hr_connection() as conn:
            with conn.transaction():
                if not conn.execute("SELECT id FROM hr_employees WHERE id=%s FOR SHARE",(payload.employee_id,)).fetchone():
                    raise HTTPException(404,"Employee not found")
                return conn.execute(
                    "INSERT INTO hr_employee_loans(employee_id,loan_reference,principal_amount,outstanding_amount,currency,created_by_user_id) "
                    "VALUES(%s,%s,%s,%s,%s,%s) RETURNING *",
                    (payload.employee_id,payload.loan_reference.strip(),payload.principal_amount,payload.principal_amount,"INR",actor)
                ).fetchone()
    except HTTPException: raise
    except psycopg.Error as exc: raise _db_error(exc) from exc


@router.post("/exit/loans/{loan_id}/approve")
def approve_employee_loan(loan_id:int,request:Request):
    actor=_manager(request)
    try:
        with _hr_connection() as conn:
            with conn.transaction():
                loan=conn.execute("SELECT * FROM hr_employee_loans WHERE id=%s FOR UPDATE",(loan_id,)).fetchone()
                if not loan: raise HTTPException(404,"Employee loan not found")
                if loan["status"]!="draft": raise HTTPException(409,"Only draft employee loans can be approved")
                if loan["created_by_user_id"]==actor: raise HTTPException(403,"A different authorised manager must approve the employee loan")
                return conn.execute(
                    "UPDATE hr_employee_loans SET status='active',approved_by_user_id=%s,approved_at=now(),updated_at=now() WHERE id=%s RETURNING *",
                    (actor,loan_id)
                ).fetchone()
    except HTTPException: raise
    except psycopg.Error as exc: raise _db_error(exc) from exc


@router.get("/exit/loans")
def list_employee_loans(request:Request,employee_id:int|None=Query(None,gt=0)):
    actor=_actor(request)
    if _role(request) not in MANAGER_ROLES:
        with _hr_connection() as conn:
            own=_employee(conn,actor)
            if employee_id is not None and employee_id!=own["id"]: raise HTTPException(403,"Employees may view only their own loans")
            employee_id=own["id"]
    with _hr_connection() as conn:
        return {"items":conn.execute(
            "SELECT * FROM hr_employee_loans WHERE (%s::bigint IS NULL OR employee_id=%s) ORDER BY created_at DESC",
            (employee_id,employee_id)
        ).fetchall()}


