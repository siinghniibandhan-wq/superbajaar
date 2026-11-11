"""HR end-to-end tests against a disposable PostgreSQL database only."""
import os
import uuid
from datetime import date
from decimal import Decimal

import psycopg
import pytest
from fastapi import Request
from fastapi.testclient import TestClient

from app.core.auth_middleware import require_active_session
from app.main import app

TEST_DB=os.environ.get("SB_TEST_DATABASE_URL","")
pytestmark=pytest.mark.skipif(not TEST_DB,reason="SB_TEST_DATABASE_URL is not set")
if TEST_DB and ("sb_app" in TEST_DB or "amazonaws" in TEST_DB):
    raise RuntimeError("Refusing to run HR integration tests against a production-like database")


@pytest.fixture()
def api(monkeypatch):
    suffix=uuid.uuid4().hex[:10]
    with psycopg.connect(TEST_DB) as conn:
        user_id=conn.execute(
            "INSERT INTO app_users(email,full_name,password_hash,role) VALUES(%s,%s,%s,'super_admin') RETURNING id",
            (f"hr-{suffix}@test.local","HR Integration Test","test-hash"),
        ).fetchone()[0]
    role={"value":"super_admin"}
    async def fake_session(request:Request):
        request.state.role=role["value"]
        request.state.user_id=user_id
        request.state.user_email=f"hr-{suffix}@test.local"
    from app.api import hr
    monkeypatch.setattr(hr.settings,"database_url",TEST_DB)
    app.dependency_overrides[require_active_session]=fake_session
    client=TestClient(app)
    client.role=role
    client.user_id=user_id
    client.suffix=suffix
    yield client
    app.dependency_overrides.pop(require_active_session,None)


def ok(response,status=200):
    assert response.status_code==status,response.text
    return response.json()


def test_hr_employee_attendance_expense_payroll_accounting_cycle(api):
    dept=ok(api.post("/api/hr/departments",json={"code":"HR"+api.suffix[:4],"name":"HR Test "+api.suffix}),201)
    employee=ok(api.post("/api/hr/employees",json={
        "user_id":api.user_id,"employee_code":"SB-"+api.suffix,
        "first_name":"Test","last_name":"Employee","email":"employee-"+api.suffix+"@test.local",
        "phone":"9000000000","department_id":dept["id"],"designation":"Tester",
        "joining_date":"2026-01-01","basic_salary":"30000","hra":"10000",
        "special_allowance":"5000","other_allowance":"0"
    }),201)
    assert employee["user_id"]==api.user_id

    establishment=ok(api.post("/api/hr/establishments",json={
        "code":"EST-"+api.suffix,"legal_name":"Test Legal Entity "+api.suffix,
        "display_name":"Test Establishment "+api.suffix,"state_code":"KA"
    }),201)
    # Optional filters omitted: both list endpoints must still return successfully.
    assert ok(api.get("/api/hr/statutory/policies"))["items"] == []
    assert ok(api.get("/api/hr/statutory/remittances"))["items"] == []
    ok(api.put("/api/hr/employees/"+str(employee["id"])+"/statutory-profile",json={
        "establishment_id":establishment["id"],"effective_from":"2026-01-01",
        "tds_regime":"new"
    }))
    for component in ("pf","esi","pt","tds"):
        policy=ok(api.post("/api/hr/statutory/policies",json={
            "establishment_id":establishment["id"],"component":component,
            "version_label":"Test "+component,"effective_from":"2026-01-01",
            "policy_config":{"enabled":False}
        }),201)
        ok(api.post("/api/hr/statutory/policies/"+str(policy["id"])+"/submit"))
        ok(api.post("/api/hr/statutory/policies/"+str(policy["id"])+"/approve"))

    api.role["value"]="staff"
    punch_in=ok(api.post("/api/hr/attendance/punch",json={"punch_type":"clock_in"}),201)
    assert punch_in["employee_id"]==employee["id"]
    duplicate_punch=api.post("/api/hr/attendance/punch",json={"punch_type":"clock_in"})
    assert duplicate_punch.status_code==409
    punch_out=ok(api.post("/api/hr/attendance/punch",json={"punch_type":"clock_out"}),201)
    assert punch_out["clock_out_at"] is not None
    leave=ok(api.post("/api/hr/leave",json={
        "leave_type":"annual","start_date":"2026-10-12","end_date":"2026-10-12","days":"1","reason":"Personal leave"
    }),201)
    expense=ok(api.post("/api/hr/expenses",json={
        "category":"travel","amount":"1250","expense_date":"2026-10-15",
        "description":"Approved local travel reimbursement"
    }),201)
    api.role["value"]="super_admin"
    ok(api.patch("/api/hr/leave/"+str(leave["id"])+"/review",json={"decision":"approved"}))
    ok(api.patch("/api/hr/expenses/"+str(expense["id"])+"/review",json={"decision":"approved"}))

    payroll=ok(api.post("/api/hr/payroll/runs",json={
        "period_start":"2026-10-01","period_end":"2026-10-31","deductions_by_employee":{}
    }),201)
    assert Decimal(str(payroll["total_gross"]))==Decimal("45000.00")
    assert Decimal(str(payroll["total_reimbursements"]))==Decimal("1250.00")
    assert Decimal(str(payroll["total_net"]))==Decimal("46250.00")
    recalculated=ok(api.post("/api/hr/payroll/runs",json={
        "period_start":"2026-10-01","period_end":"2026-10-31","deductions_by_employee":{}
    }),201)
    assert recalculated["id"]==payroll["id"]
    assert Decimal(str(recalculated["total_reimbursements"]))==Decimal("1250.00")
    assert Decimal(str(recalculated["total_net"]))==Decimal("46250.00")
    payroll=recalculated
    slips=ok(api.get("/api/hr/payroll/runs/"+str(payroll["id"])+"/payslips"))
    assert len(slips["items"])==1
    assert Decimal(str(slips["items"][0]["net_pay"]))==Decimal("46250.00")
    ok(api.post("/api/hr/payroll/runs/"+str(payroll["id"])+"/approve",json={"decision":"approved"}))
    remittances=ok(api.post("/api/hr/payroll/runs/"+str(payroll["id"])+"/statutory-remittances",json={}),201)
    assert len(remittances["items"])==4
    assert {item["component"] for item in remittances["items"]}=={"pf","esi","pt","tds"}
    remittances_again=ok(api.post("/api/hr/payroll/runs/"+str(payroll["id"])+"/statutory-remittances",json={}),201)
    assert {item["id"] for item in remittances_again["items"]}=={item["id"] for item in remittances["items"]}

    accounts=ok(api.get("/api/accounting/accounts"))["items"]
    bank=next(x["id"] for x in accounts if x["code"]=="1010")
    payable=next(x["id"] for x in accounts if x["code"]=="2000")
    voucher=ok(api.post("/api/accounting/vouchers",json={
        "voucher_type":"payment","voucher_date":"2026-11-02","party_type":"employee",
        "party_name":"Payroll Run "+str(payroll["id"]),"narration":"HR payroll disbursement",
        "lines":[{"account_id":payable,"debit":"46250"},{"account_id":bank,"credit":"46250"}]
    }),201)
    paid=ok(api.post("/api/hr/payroll/runs/"+str(payroll["id"])+"/pay",json={
        "accounting_voucher_id":voucher["id"]
    }))
    assert paid["status"]=="paid"
    assert paid["accounting_voucher_id"]==voucher["id"]
    paid_again=ok(api.post("/api/hr/payroll/runs/"+str(payroll["id"])+"/pay",json={
        "accounting_voucher_id":voucher["id"]
    }))
    assert paid_again["status"]=="paid"
    assert paid_again["accounting_voucher_id"]==voucher["id"]

def test_payroll_approval_is_blocked_without_employee_statutory_setup(api):
    employee=ok(api.post("/api/hr/employees",json={
        "employee_code":"SB-"+api.suffix,"first_name":"Missing","last_name":"Profile",
        "email":"missing-"+api.suffix+"@test.local","designation":"Tester",
        "joining_date":"2026-01-01","basic_salary":"30000"
    }),201)
    payroll=ok(api.post("/api/hr/payroll/runs",json={
        "period_start":"2026-11-01","period_end":"2026-11-30"
    }),201)
    assert payroll["statutory_readiness"]=="incomplete"
    assert payroll["approval_blocked"] is True
    assert payroll["incomplete_employees"][0]["employee_id"]==employee["id"]
    blocked=api.post("/api/hr/payroll/runs/"+str(payroll["id"])+"/approve",json={"decision":"approved"})
    assert blocked.status_code==409
    assert "statutory profiles" in blocked.text

def test_hr_admin_can_manage_departments_establishments_and_attendance(api):
    dept=ok(api.post("/api/hr/departments",json={"code":"OPS"+api.suffix[:3],"name":"Ops "+api.suffix}),201)
    changed=ok(api.put("/api/hr/departments/"+str(dept["id"]),json={
        "code":dept["code"],"name":"Operations "+api.suffix,"description":"Updated department"
    }))
    assert changed["name"]=="Operations "+api.suffix

    establishment=ok(api.post("/api/hr/establishments",json={
        "code":"EST"+api.suffix[:4],"legal_name":"Legal "+api.suffix,
        "display_name":"Office "+api.suffix,"state_code":"JH",
        "address":{"city":"Daltonganj"},"registrations":{"gstin":"TEST"}
    }),201)
    changed_est=ok(api.put("/api/hr/establishments/"+str(establishment["id"]),json={
        "code":establishment["code"],"legal_name":"Updated Legal "+api.suffix,
        "display_name":"Updated Office "+api.suffix,"state_code":"BR",
        "address":{"city":"Patna"},"registrations":{"gstin":"UPDATED"}
    }))
    assert changed_est["state_code"]=="BR"
    assert changed_est["address"]["city"]=="Patna"

    employee=ok(api.post("/api/hr/employees",json={
        "user_id":api.user_id,"employee_code":"EDIT-"+api.suffix,
        "first_name":"Editable","last_name":"Employee","email":"edit-"+api.suffix+"@test.local",
        "department_id":dept["id"],"designation":"Associate","joining_date":"2026-01-01",
        "basic_salary":"25000"
    }),201)
    updated=ok(api.put("/api/hr/employees/"+str(employee["id"]),json={
        "user_id":api.user_id,"employee_code":employee["employee_code"],
        "first_name":"Edited","last_name":"Employee","email":"edit-"+api.suffix+"@test.local",
        "department_id":dept["id"],"designation":"Senior Associate","joining_date":"2026-01-01",
        "basic_salary":"30000","hra":"5000","special_allowance":"1000","other_allowance":"0"
    }))
    assert updated["first_name"]=="Edited"
    salary_profile=next(x for x in ok(api.get("/api/hr/employees"))["items"] if x["id"]==employee["id"])
    assert Decimal(str(salary_profile["basic_salary"]))==Decimal("25000.00")

    api.role["value"]="staff"
    punch=ok(api.post("/api/hr/attendance/punch",json={"punch_type":"clock_in"}),201)
    api.role["value"]="super_admin"
    adjusted=ok(api.patch("/api/hr/attendance/sessions/"+str(punch["id"]),json={
        "clock_in_at":"2026-11-02T09:00:00+05:30",
        "clock_out_at":"2026-11-02T18:00:00+05:30",
        "reason":"Corrected missed attendance punch"
    }))
    assert adjusted["status"]=="pending_review"
    assert adjusted["request"]["status"]=="pending"
    assert adjusted["request"]["requested_by_user_id"]==api.user_id
    invalid_adjustment=api.patch("/api/hr/attendance/sessions/"+str(punch["id"]),json={
        "clock_in_at":"2026-11-02T18:00:00+05:30",
        "clock_out_at":"2026-11-02T09:00:00+05:30",
        "reason":"Invalid reversed attendance correction"
    })
    assert invalid_adjustment.status_code==422

    ok(api.post("/api/hr/departments/"+str(dept["id"])+"/deactivate",json={}))
    assert ok(api.get("/api/hr/departments"))["items"]

def test_hr_employee_reporting_hierarchy_rejects_self_reference_and_cycles(api):
    first=ok(api.post("/api/hr/employees",json={
        "employee_code":"MGR1-"+api.suffix,"first_name":"First","last_name":"Manager",
        "email":"mgr1-"+api.suffix+"@test.local","designation":"Manager",
        "joining_date":"2026-01-01"
    }),201)
    second=ok(api.post("/api/hr/employees",json={
        "employee_code":"MGR2-"+api.suffix,"first_name":"Second","last_name":"Manager",
        "email":"mgr2-"+api.suffix+"@test.local","designation":"Associate",
        "joining_date":"2026-01-01","reports_to_employee_id":first["id"]
    }),201)

    self_reference=api.put("/api/hr/employees/"+str(first["id"]),json={
        "employee_code":first["employee_code"],"first_name":"First","last_name":"Manager",
        "email":"mgr1-"+api.suffix+"@test.local","designation":"Manager",
        "joining_date":"2026-01-01","reports_to_employee_id":first["id"]
    })
    assert self_reference.status_code==422

    cycle=api.put("/api/hr/employees/"+str(first["id"]),json={
        "employee_code":first["employee_code"],"first_name":"First","last_name":"Manager",
        "email":"mgr1-"+api.suffix+"@test.local","designation":"Manager",
        "joining_date":"2026-01-01","reports_to_employee_id":second["id"]
    })
    assert cycle.status_code==422


def test_hr_staff_cannot_use_manager_payroll_or_department_actions(api):
    api.role["value"]="staff"
    payroll=api.get("/api/hr/payroll/runs")
    department=api.post("/api/hr/departments",json={
        "code":"NO"+api.suffix[:4],"name":"Must Not Be Created"
    })
    assert payroll.status_code==403
    assert department.status_code==403


def test_hr_self_service_leave_and_expense_rejections_require_reason(api):
    employee=ok(api.post("/api/hr/employees",json={
        "user_id":api.user_id,"employee_code":"SELF-"+api.suffix,
        "first_name":"Self","last_name":"Service",
        "email":"self-"+api.suffix+"@test.local","designation":"Associate",
        "joining_date":"2026-01-01"
    }),201)
    api.role["value"]="staff"
    leave=ok(api.post("/api/hr/leave",json={
        "leave_type":"annual","start_date":"2026-11-12","end_date":"2026-11-12",
        "days":"1","reason":"Personal leave"
    }),201)
    expense=ok(api.post("/api/hr/expenses",json={
        "category":"travel","amount":"250","expense_date":"2026-11-12",
        "description":"Local travel"
    }),201)
    api.role["value"]="super_admin"
    leave_rejected=api.patch("/api/hr/leave/"+str(leave["id"])+"/review",json={"decision":"rejected"})
    expense_rejected=api.patch("/api/hr/expenses/"+str(expense["id"])+"/review",json={"decision":"rejected","note":" "})
    assert leave_rejected.status_code==422
    assert expense_rejected.status_code==422
    ok(api.patch("/api/hr/leave/"+str(leave["id"])+"/review",json={
        "decision":"rejected","note":"Insufficient notice for this leave period"
    }))
    ok(api.patch("/api/hr/expenses/"+str(expense["id"])+"/review",json={
        "decision":"rejected","note":"Receipt is missing"
    }))



def test_hr_shift_roster_publish_cancel_and_staff_visibility(api):
    establishment=ok(api.post("/api/hr/establishments",json={
        "code":"SHIFT-"+api.suffix,"legal_name":"Shift Legal "+api.suffix,
        "display_name":"Shift Office "+api.suffix,"state_code":"KA"
    }),201)
    employee=ok(api.post("/api/hr/employees",json={
        "user_id":api.user_id,"employee_code":"SHIFT-EMP-"+api.suffix,
        "first_name":"Shift","last_name":"Worker","email":"shift-"+api.suffix+"@test.local",
        "designation":"Associate","joining_date":"2026-01-01"
    }),201)
    shift=ok(api.post("/api/hr/shifts",json={
        "establishment_id":establishment["id"],"code":"DAY","name":"Day shift",
        "local_start_time":"09:00","local_end_time":"18:00","break_minutes":60,
        "effective_from":"2026-01-01"
    }),201)
    assignment=ok(api.post("/api/hr/shift-assignments",json={
        "employee_id":employee["id"],"shift_definition_id":shift["id"],
        "work_date":"2026-11-10","planned_start_at":"2026-11-10T09:00:00+05:30",
        "planned_end_at":"2026-11-10T18:00:00+05:30"
    }),201)
    duplicate=api.post("/api/hr/shift-assignments",json={
        "employee_id":employee["id"],"shift_definition_id":shift["id"],
        "work_date":"2026-11-10","planned_start_at":"2026-11-10T10:00:00+05:30",
        "planned_end_at":"2026-11-10T19:00:00+05:30"
    })
    assert duplicate.status_code==409
    published=ok(api.post("/api/hr/shift-assignments/"+str(assignment["id"])+"/publish",json={}))
    assert published["status"]=="published"
    api.role["value"]="staff"
    schedule=ok(api.get("/api/hr/shift-assignments?start_date=2026-11-01&end_date=2026-11-30"))
    assert [x["id"] for x in schedule["items"]]==[assignment["id"]]
    api.role["value"]="super_admin"
    cancelled=ok(api.post("/api/hr/shift-assignments/"+str(assignment["id"])+"/cancel",json={
        "decision":"rejected","note":"Store opening hours changed"
    }))
    assert cancelled["status"]=="cancelled"


def test_hr_holiday_calendar_approval_locks_its_holidays(api):
    establishment=ok(api.post("/api/hr/establishments",json={
        "code":"HOL-"+api.suffix,"legal_name":"Holiday Legal "+api.suffix,
        "display_name":"Holiday Office "+api.suffix,"state_code":"JH"
    }),201)
    calendar=ok(api.post("/api/hr/holiday-calendars",json={
        "establishment_id":establishment["id"],"name":"Jharkhand 2027","effective_year":2027
    }),201)
    holiday=ok(api.post("/api/hr/holiday-calendars/"+str(calendar["id"])+"/holidays",json={
        "holiday_date":"2027-01-26","name":"Republic Day","holiday_type":"national","is_paid":True
    }),201)
    approved=ok(api.post("/api/hr/holiday-calendars/"+str(calendar["id"])+"/approve",json={}))
    assert approved["status"]=="approved"
    blocked=api.post("/api/hr/holiday-calendars/"+str(calendar["id"])+"/holidays",json={
        "holiday_date":"2027-08-15","name":"Independence Day","holiday_type":"national"
    })
    assert blocked.status_code==409
    with psycopg.connect(TEST_DB) as conn:
        with pytest.raises(psycopg.errors.RaiseException):
            conn.execute("UPDATE hr_holidays SET name='Changed' WHERE id=%s",(holiday["id"],))


def test_hr_leave_policy_accrual_is_idempotent_and_adjustments_are_ledgered(api):
    establishment=ok(api.post("/api/hr/establishments",json={
        "code":"LEAVE-"+api.suffix,"legal_name":"Leave Legal "+api.suffix,
        "display_name":"Leave Office "+api.suffix,"state_code":"KA"
    }),201)
    employee=ok(api.post("/api/hr/employees",json={
        "user_id":api.user_id,"employee_code":"LEAVE-EMP-"+api.suffix,"first_name":"Leave","last_name":"Worker",
        "email":"leave-"+api.suffix+"@test.local","designation":"Associate",
        "joining_date":"2026-01-01"
    }),201)
    ok(api.put("/api/hr/employees/"+str(employee["id"])+"/statutory-profile",json={
        "establishment_id":establishment["id"],"effective_from":"2026-01-01","tds_regime":"new"
    }))
    policy=ok(api.post("/api/hr/leave-policies",json={
        "establishment_id":establishment["id"],"leave_type":"annual","version_label":"Annual 2026",
        "effective_from":"2026-01-01","entitlement_days":"12","accrual_frequency":"monthly",
        "carry_forward_cap":"5","day_count_basis":"working"
    }),201)
    approved=ok(api.post("/api/hr/leave-policies/"+str(policy["id"])+"/approve",json={}))
    assert approved["status"]=="approved"
    payload={"period_start":"2026-11-01","period_end":"2026-11-30"}
    first=ok(api.post("/api/hr/leave/accruals",json=payload))
    second=ok(api.post("/api/hr/leave/accruals",json=payload))
    assert first["created_ledger_entries"]==1
    assert second["created_ledger_entries"]==0
    ledger=ok(api.get("/api/hr/leave-ledger?employee_id="+str(employee["id"])))
    assert len(ledger["items"])==1
    assert Decimal(str(ledger["items"][0]["quantity_days"]))==Decimal("1.00")
    adjustment=ok(api.post("/api/hr/leave-balances/adjust",json={
        "employee_id":employee["id"],"leave_type":"annual","quantity_days":"2",
        "effective_date":"2026-11-30","reason":"Approved opening balance correction"
    }))
    assert adjustment["transaction_type"]=="adjustment"
    ledger=ok(api.get("/api/hr/leave-ledger?employee_id="+str(employee["id"])))
    assert len(ledger["items"])==2
    api.role["value"]="staff"
    request=ok(api.post("/api/hr/leave",json={
        "leave_type":"annual","start_date":"2026-11-30","end_date":"2026-11-30",
        "days":"1","reason":"Planned annual leave"
    }),201)
    api.role["value"]="super_admin"
    ok(api.patch("/api/hr/leave/"+str(request["id"])+"/review",json={"decision":"approved"}))
    api.role["value"]="staff"
    cancelled=ok(api.post("/api/hr/leave/"+str(request["id"])+"/cancel",json={
        "reason":"Leave plan changed after approval"
    }))
    assert cancelled["status"]=="cancelled"
    api.role["value"]="super_admin"
    ledger=ok(api.get("/api/hr/leave-ledger?employee_id="+str(employee["id"])))
    assert sum(Decimal(str(x["quantity_days"])) for x in ledger["items"])==Decimal("3.00")
    ok(api.post("/api/hr/leave-balances/adjust",json={
        "employee_id":employee["id"],"leave_type":"annual","quantity_days":"8",
        "effective_date":"2026-12-31","reason":"Verified prior-year leave balance"
    }))
    next_year=ok(api.post("/api/hr/leave/accruals",json={
        "period_start":"2027-01-01","period_end":"2027-01-31"
    }))
    assert next_year["created_ledger_entries"]==1
    ledger=ok(api.get("/api/hr/leave-ledger?employee_id="+str(employee["id"])))
    carry=[x for x in ledger["items"] if x["transaction_type"]=="carry_forward"]
    assert len(carry)==1
    assert Decimal(str(carry[0]["quantity_days"]))==Decimal("-6.00")
    balances=ok(api.get("/api/hr/leave-balances?employee_id="+str(employee["id"])))
    assert Decimal(str(balances["items"][0]["live_closing_days"]))==Decimal("6.00")


def test_hr_lifecycle_template_generates_tasks_once_and_audits_completion(api):
    employee=ok(api.post("/api/hr/employees",json={
        "user_id":api.user_id,"employee_code":"LIFE-"+api.suffix,
        "first_name":"Lifecycle","last_name":"Worker",
        "email":"life-"+api.suffix+"@test.local","designation":"Associate",
        "joining_date":"2026-11-01"
    }),201)
    template=ok(api.post("/api/hr/lifecycle/templates",json={
        "name":"Standard onboarding","lifecycle_type":"onboarding"
    }),201)
    ok(api.post("/api/hr/lifecycle/templates/"+str(template["id"])+"/items",json={
        "task_key":"EMPLOYEE_WELCOME","label":"Read employee handbook",
        "owner_role":"employee","due_days_offset":2,"sequence":1
    }),201)
    ok(api.post("/api/hr/lifecycle/templates/"+str(template["id"])+"/items",json={
        "task_key":"IT_ACCOUNT","label":"Create staff IT account",
        "owner_role":"it","due_days_offset":1,"sequence":2
    }),201)
    generated=ok(api.post("/api/hr/lifecycle/employees/"+str(employee["id"])+"/generate",json={
        "template_id":template["id"],"start_date":"2026-11-01"
    }))
    assert generated["created_count"]==2
    repeated=ok(api.post("/api/hr/lifecycle/employees/"+str(employee["id"])+"/generate",json={
        "template_id":template["id"],"start_date":"2026-11-01"
    }))
    assert repeated["created_count"]==0
    task=next(x for x in generated["items"] if x["owner_role"]=="employee")
    restricted_task=next(x for x in generated["items"] if x["owner_role"]=="it")
    api.role["value"]="staff"
    visible=ok(api.get("/api/hr/lifecycle/tasks"))
    assert {x["id"] for x in visible["items"]}=={task["id"]}
    denied=api.patch("/api/hr/lifecycle/tasks/"+str(restricted_task["id"]),json={
        "status":"completed","completion_note":"Should not be allowed"
    })
    assert denied.status_code==403
    started=ok(api.patch("/api/hr/lifecycle/tasks/"+str(task["id"]),json={
        "status":"in_progress","due_date":"2026-12-31"
    }))
    assert started["due_date"]=="2026-11-03"
    completed=ok(api.patch("/api/hr/lifecycle/tasks/"+str(task["id"]),json={
        "status":"completed","completion_note":"Handbook read and acknowledged"
    }))
    assert completed["status"]=="completed"
    cannot_reopen=api.patch("/api/hr/lifecycle/tasks/"+str(task["id"]),json={
        "status":"in_progress"
    })
    assert cannot_reopen.status_code==409
    api.role["value"]="super_admin"
    events=ok(api.get("/api/hr/lifecycle/tasks/"+str(task["id"])+"/events"))
    assert [x["event_type"] for x in events["items"]]==["created","started","completed"]


def test_hr_opening_leave_balance_is_idempotent_and_negative_balance_is_guarded(api):
    establishment=ok(api.post("/api/hr/establishments",json={
        "code":"OPEN-"+api.suffix,"legal_name":"Opening Legal "+api.suffix,
        "display_name":"Opening Office "+api.suffix,"state_code":"JH"
    }),201)
    employee=ok(api.post("/api/hr/employees",json={
        "employee_code":"OPEN-EMP-"+api.suffix,"first_name":"Opening","last_name":"Balance",
        "email":"opening-"+api.suffix+"@test.local","designation":"Associate",
        "joining_date":"2026-01-01"
    }),201)
    ok(api.put("/api/hr/employees/"+str(employee["id"])+"/statutory-profile",json={
        "establishment_id":establishment["id"],"effective_from":"2026-01-01","tds_regime":"new"
    }))
    policy=ok(api.post("/api/hr/leave-policies",json={
        "establishment_id":establishment["id"],"leave_type":"annual","version_label":"Opening balance policy",
        "effective_from":"2026-01-01","entitlement_days":"12","accrual_frequency":"monthly",
        "carry_forward_cap":"5"
    }),201)
    ok(api.post("/api/hr/leave-policies/"+str(policy["id"])+"/approve",json={}))
    opening_payload={
        "employee_id":employee["id"],"leave_type":"annual","policy_id":policy["id"],
        "quantity_days":"4","effective_date":"2026-01-01","reason":"Verified carried opening entitlement"
    }
    first=ok(api.post("/api/hr/leave-balances/opening",json=opening_payload))
    second=ok(api.post("/api/hr/leave-balances/opening",json=opening_payload))
    assert first["id"]==second["id"]
    balances=ok(api.get("/api/hr/leave-balances?employee_id="+str(employee["id"])))
    assert Decimal(str(balances["items"][0]["live_closing_days"]))==Decimal("4.00")
    blocked=api.post("/api/hr/leave-balances/adjust",json={
        "employee_id":employee["id"],"leave_type":"annual","quantity_days":"-5",
        "effective_date":"2026-01-02","reason":"Attempt to overdraw the balance"
    })
    assert blocked.status_code==409


def test_hr_leave_overlap_blocks_pending_and_approved_but_not_rejected(api):
    employee=ok(api.post("/api/hr/employees",json={
        "user_id":api.user_id,"employee_code":"OVERLAP-"+api.suffix,
        "first_name":"Leave","last_name":"Owner",
        "email":"overlap-"+api.suffix+"@test.local","designation":"Associate",
        "joining_date":"2026-01-01"
    }),201)
    api.role["value"]="staff"
    first=ok(api.post("/api/hr/leave",json={
        "leave_type":"annual","start_date":"2026-12-10","end_date":"2026-12-12",
        "days":"3","reason":"Planned personal leave"
    }),201)
    pending_overlap=api.post("/api/hr/leave",json={
        "leave_type":"sick","start_date":"2026-12-12","end_date":"2026-12-13",
        "days":"2","reason":"Overlapping leave request"
    })
    assert pending_overlap.status_code==409
    api.role["value"]="super_admin"
    ok(api.patch("/api/hr/leave/"+str(first["id"])+"/review",json={
        "decision":"rejected","note":"Rejected for this test"
    }))
    api.role["value"]="staff"
    replacement=ok(api.post("/api/hr/leave",json={
        "leave_type":"annual","start_date":"2026-12-10","end_date":"2026-12-12",
        "days":"3","reason":"Resubmitted after rejection"
    }),201)
    api.role["value"]="super_admin"
    ok(api.patch("/api/hr/leave/"+str(replacement["id"])+"/review",json={"decision":"approved"}))
    approved_overlap=api.post("/api/hr/leave",json={
        "leave_type":"casual","start_date":"2026-12-11","end_date":"2026-12-11",
        "days":"1","reason":"Overlapping approved leave"
    })
    assert approved_overlap.status_code==409


def test_hr_payroll_rejects_partial_or_cross_month_periods(api):
    partial_month=api.post("/api/hr/payroll/runs",json={
        "period_start":"2026-11-02","period_end":"2026-11-30"
    })
    cross_month=api.post("/api/hr/payroll/runs",json={
        "period_start":"2026-11-01","period_end":"2026-12-01"
    })
    assert partial_month.status_code==422
    assert cross_month.status_code==422


def test_hr_salary_revisions_and_overtime_flow_into_payroll_once(api):
    employee=ok(api.post("/api/hr/employees",json={
        "employee_code":"SAL-"+api.suffix,"first_name":"Salary","last_name":"Revision",
        "email":"salary-"+api.suffix+"@test.local","designation":"Associate",
        "joining_date":"2026-01-01","basic_salary":"30000","hra":"12000",
        "special_allowance":"5000","other_allowance":"1000"
    }),201)
    history=ok(api.get(f"/api/hr/employees/{employee['id']}/salary-revisions"))
    assert len(history["items"])==1
    revision=ok(api.post(f"/api/hr/employees/{employee['id']}/salary-revisions",json={
        "effective_from":"2026-12-01","basic_salary":"33000","hra":"12000",
        "special_allowance":"5000","other_allowance":"1000","reason":"Annual performance revision"
    }),201)
    assert revision["status"]=="draft"
    approved=ok(api.post(
        f"/api/hr/employees/{employee['id']}/salary-revisions/{revision['id']}/review",
        json={"decision":"approved"}
    ))
    assert approved["status"]=="approved"
    history=ok(api.get(f"/api/hr/employees/{employee['id']}/salary-revisions"))
    opening=next(x for x in history["items"] if x["status"]=="approved" and str(x["effective_from"])=="2026-01-01")
    assert str(opening["effective_to"])=="2026-11-30"

    overtime=ok(api.post(f"/api/hr/employees/{employee['id']}/earning-adjustments",json={
        "earning_type":"overtime","period_start":"2026-12-01","period_end":"2026-12-31",
        "amount":"1500.00","hours":"10","hourly_rate":"150",
        "reason":"Approved weekend store coverage"
    }),201)
    ok(api.post(f"/api/hr/payroll/earning-adjustments/{overtime['id']}/review",json={"decision":"approved"}))
    payroll=ok(api.post("/api/hr/payroll/runs",json={
        "period_start":"2026-12-01","period_end":"2026-12-31"
    }),201)
    payslips=ok(api.get(f"/api/hr/payroll/runs/{payroll['id']}/payslips"))["items"]
    employee_slip=next(item for item in payslips if item["employee_id"]==employee["id"])
    assert Decimal(str(employee_slip["gross_earnings"]))==Decimal("52500.00")
    assert employee_slip["earnings_breakdown"]["variable_earnings"][0]["type"]=="overtime"
    assert employee_slip["earnings_breakdown"]["variable_earnings"][0]["reason"]=="Approved weekend store coverage"

    recalculated=ok(api.post("/api/hr/payroll/runs",json={
        "period_start":"2026-12-01","period_end":"2026-12-31"
    }),201)
    recalculated_slips=ok(api.get(f"/api/hr/payroll/runs/{payroll['id']}/payslips"))["items"]
    recalculated_employee_slip=next(item for item in recalculated_slips if item["employee_id"]==employee["id"])
    assert Decimal(str(recalculated_employee_slip["gross_earnings"]))==Decimal("52500.00")
    linked=ok(api.get("/api/hr/payroll/earning-adjustments"))["items"]
    assert next(x for x in linked if x["id"]==overtime["id"])["payroll_run_id"]==payroll["id"]

    pending=ok(api.post(f"/api/hr/employees/{employee['id']}/earning-adjustments",json={
        "earning_type":"incentive","period_start":"2026-12-01","period_end":"2026-12-31",
        "amount":"2000.00","reason":"Pending monthly sales incentive"
    }),201)
    blocked=api.post(f"/api/hr/payroll/runs/{payroll['id']}/approve",json={"decision":"approved"})
    assert blocked.status_code==409
    assert "awaiting review" in blocked.text
    ok(api.post(f"/api/hr/payroll/earning-adjustments/{pending['id']}/review",json={
        "decision":"rejected","note":"Sales target evidence was not approved"
    }))


def test_hr_multi_establishment_payroll_accruals_are_tracked_per_entity(api):
    employees=[]
    for index,state in enumerate(("BR","JH"),start=1):
        employee=ok(api.post("/api/hr/employees",json={
            "employee_code":f"MULTI-{index}-"+api.suffix,
            "first_name":f"Entity{index}","last_name":"Worker",
            "email":f"multi{index}-"+api.suffix+"@test.local","designation":"Associate",
            "joining_date":"2026-01-01","basic_salary":"20000"
        }),201)
        establishment=ok(api.post("/api/hr/establishments",json={
            "code":f"MULTI-{index}-"+api.suffix,
            "legal_name":f"Multi Legal {index} "+api.suffix,
            "display_name":f"Multi Office {index} "+api.suffix,
            "state_code":state
        }),201)
        ok(api.put(f"/api/hr/employees/{employee['id']}/statutory-profile",json={
            "establishment_id":establishment["id"],"effective_from":"2026-01-01","tds_regime":"new"
        }))
        for component in ("pf","esi","pt","tds"):
            policy=ok(api.post("/api/hr/statutory/policies",json={
                "establishment_id":establishment["id"],"component":component,
                "version_label":f"Multi {index} {component}","effective_from":"2026-01-01",
                "policy_config":{"enabled":False}
            }),201)
            ok(api.post(f"/api/hr/statutory/policies/{policy['id']}/submit"))
            ok(api.post(f"/api/hr/statutory/policies/{policy['id']}/approve"))
        employees.append((employee,establishment))

    # The integration database is shared across HR tests; isolate this payroll
    # to the two deliberately configured establishments.
    with psycopg.connect(TEST_DB) as conn:
        conn.execute(
            "UPDATE hr_employees SET status='terminated',exit_date='2026-12-31' "
            "WHERE id NOT IN (%s,%s)",
            (employees[0][0]["id"],employees[1][0]["id"]),
        )

    payroll=ok(api.post("/api/hr/payroll/runs",json={
        "period_start":"2027-01-01","period_end":"2027-01-31"
    }),201)
    assert payroll["employee_count"]>=2
    approved=ok(api.post(f"/api/hr/payroll/runs/{payroll['id']}/approve",json={"decision":"approved"}))
    posting=approved["accounting_accrual"]
    assert posting["status"]=="exception"
    failed_entities={item["legal_entity_code"] for item in posting["errors"]}
    assert {employees[0][1]["code"],employees[1][1]["code"]}.issubset(failed_entities)



def test_hr_manager_overview_aggregates_real_schema_without_inventing_attendance(api):
    department=ok(api.post("/api/hr/departments",json={
        "code":"OV"+api.suffix[:5],"name":"Overview "+api.suffix
    }),201)
    employee=ok(api.post("/api/hr/employees",json={
        "employee_code":"OV-"+api.suffix,"first_name":"Overview","last_name":"Employee",
        "email":"overview-"+api.suffix+"@test.local","department_id":department["id"],
        "designation":"Analyst","joining_date":"2099-01-01","basic_salary":"25000"
    }),201)

    overview=ok(api.get("/api/hr/overview?month=2099-12"))
    assert overview["period"] == {
        "month":"2099-12","start_date":"2099-12-01","end_date":"2099-12-31"
    }
    assert overview["workforce"]["total"] >= 1
    assert overview["workforce"]["active"] >= 1
    assert any(item["id"] == department["id"] for item in overview["workforce"]["departments"])
    assert overview["attendance"]["available"] is False
    assert overview["attendance"]["absent"] is None
    assert overview["attendance"]["rate"] is None
    assert overview["payroll"]["run_count"] == 0
    assert "employees_without_portal_user" in overview["controls"]
    assert len(overview["trends"]["headcount"]) == 7



def test_hr_termination_deactivates_employee_portal_login(api):
    with psycopg.connect(TEST_DB) as conn:
        staff_user_id=conn.execute(
            "INSERT INTO app_users(email,full_name,password_hash,role,is_active) "
            "VALUES(%s,'Termination Test Employee','test-hash','staff',TRUE) RETURNING id",
            ("termination-"+api.suffix+"@test.local",),
        ).fetchone()[0]
    department=ok(api.post("/api/hr/departments",json={
        "code":"TM"+api.suffix[:5],"name":"Termination "+api.suffix
    }),201)
    employee=ok(api.post("/api/hr/employees",json={
        "user_id":staff_user_id,"employee_code":"TM-"+api.suffix,
        "first_name":"Termination","last_name":"Employee",
        "email":"termination-"+api.suffix+"@test.local","phone":"9000000000",
        "department_id":department["id"],"designation":"Operator",
        "joining_date":"2026-01-01","basic_salary":"25000"
    }),201)
    terminated=ok(api.put(f"/api/hr/employees/{employee['id']}",json={
        "user_id":staff_user_id,"employee_code":employee["employee_code"],
        "first_name":"Termination","last_name":"Employee",
        "email":"termination-"+api.suffix+"@test.local","phone":"9000000000",
        "department_id":department["id"],"designation":"Operator",
        "employment_type":"full_time","status":"terminated",
        "joining_date":"2026-01-01","exit_date":"2026-11-11",
        "basic_salary":"25000","hra":"0","special_allowance":"0","other_allowance":"0"
    }))
    assert terminated["status"] == "terminated"
    with psycopg.connect(TEST_DB) as conn:
        active=conn.execute("SELECT is_active FROM app_users WHERE id=%s",(staff_user_id,)).fetchone()[0]
    assert active is False
