import { useCallback, useEffect, useState } from "react";
import { apiRequest } from "../../services/api.js";
import { todayHRDate } from "./hrDateTime.js";

const today = todayHRDate;
const monthStart = () => today().slice(0,7)+"-01";
const monthEnd = () => { const [year,month]=today().split("-").map(Number); const day=new Date(year,month,0).getDate(); return `${year}-${String(month).padStart(2,"0")}-${String(day).padStart(2,"0")}`; };
const json = value => JSON.stringify(value);

export default function HRAdvancedWorkflows({manager}) {
  const [section,setSection]=useState("shifts");
  const [rosterStart,setRosterStart]=useState(monthStart());
  const [rosterEnd,setRosterEnd]=useState(monthEnd());
  const [establishments,setEstablishments]=useState([]);
  const [employees,setEmployees]=useState([]);
  const [shifts,setShifts]=useState([]);
  const [assignments,setAssignments]=useState([]);
  const [calendars,setCalendars]=useState([]);
  const [holidays,setHolidays]=useState([]);
  const [policies,setPolicies]=useState([]);
  const [balances,setBalances]=useState([]);
  const [ledger,setLedger]=useState([]);
  const [templates,setTemplates]=useState([]);
  const [tasks,setTasks]=useState([]);
  const [calendarId,setCalendarId]=useState("");
  const [error,setError]=useState("");
  const [notice,setNotice]=useState("");
  const [busy,setBusy]=useState(false);
  const [shift,setShift]=useState({establishment_id:"",code:"DAY",name:"Day shift",local_start_time:"09:00",local_end_time:"18:00",break_minutes:60,timezone:"Asia/Kolkata",effective_from:today()});
  const [assignment,setAssignment]=useState({employee_id:"",shift_definition_id:"",work_date:today(),planned_start_at:today()+"T09:00",planned_end_at:today()+"T18:00"});
  const [calendar,setCalendar]=useState({establishment_id:"",name:"",region_code:"",effective_year:Number(today().slice(0,4))});
  const [holiday,setHoliday]=useState({holiday_date:today(),name:"",holiday_type:"public",location_code:"",is_paid:true});
  const [policy,setPolicy]=useState({establishment_id:"",leave_type:"annual",version_label:"Annual leave policy",effective_from:today(),entitlement_days:"12",accrual_frequency:"monthly",carry_forward_cap:"0",day_count_basis:"working",allow_negative_balance:false,encashment_allowed:false,probation_eligible:false});
  const [accrual,setAccrual]=useState({period_start:monthStart(),period_end:monthEnd()});
  const [adjustment,setAdjustment]=useState({employee_id:"",leave_type:"annual",quantity_days:"1",effective_date:today(),reason:""});
  const [opening,setOpening]=useState({employee_id:"",leave_type:"annual",policy_id:"",quantity_days:"",effective_date:today(),reason:""});
  const [template,setTemplate]=useState({establishment_id:"",name:"Standard onboarding",lifecycle_type:"onboarding"});
  const [templateItem,setTemplateItem]=useState({task_key:"",label:"",owner_role:"manager",due_days_offset:0,sequence:1});
  const [generate,setGenerate]=useState({employee_id:"",template_id:"",start_date:today()});

  const load=useCallback(async()=>{
    setBusy(true);setError("");
    try{
      const [e,emp,sh,as,bal,led,tsk]=await Promise.all([
        manager?apiRequest("/hr/establishments"):Promise.resolve({items:[]}),
        apiRequest("/hr/employees"),
        apiRequest("/hr/shifts"),
        apiRequest("/hr/shift-assignments?start_date="+rosterStart+"&end_date="+rosterEnd),
        apiRequest("/hr/leave-balances"),
        apiRequest("/hr/leave-ledger"),
        apiRequest("/hr/lifecycle/tasks"),
      ]);
      setEstablishments(e.items||[]);setEmployees(emp.items||[]);setShifts(sh.items||[]);setAssignments(as.items||[]);
      setBalances(bal.items||[]);setLedger(led.items||[]);setTasks(tsk.items||[]);
      if(manager){
        const [cal,pol,tmp]=await Promise.all([apiRequest("/hr/holiday-calendars"),apiRequest("/hr/leave-policies"),apiRequest("/hr/lifecycle/templates")]);
        setCalendars(cal.items||[]);setPolicies(pol.items||[]);setTemplates(tmp.items||[]);
      }else{
        const h=await apiRequest("/hr/holidays/me?year="+Number(today().slice(0,4)));
        setHolidays(h.items||[]);
      }
    }catch(err){setError(err.message||"Unable to load HR workflows.");}
    finally{setBusy(false);}
  },[manager,rosterStart,rosterEnd]);
  useEffect(()=>{load();},[load]);
  const post=(path,body)=>apiRequest(path,{method:"POST",body:json(body)});
  const patch=(path,body)=>apiRequest(path,{method:"PATCH",body:json(body)});
  async function act(fn,message){
    setBusy(true);setError("");setNotice("");
    try{await fn();setNotice(message);await load();}
    catch(err){setError(err.message||"Operation failed.");}
    finally{setBusy(false);}
  }
  const nav=[["shifts","Shifts & roster"],["holidays","Holiday calendar"],["leave","Leave policy & balances"],["lifecycle","Onboarding & offboarding"]];
  return <section className="hr-advanced">
    <nav className="hr-advanced-nav" aria-label="Workforce planning sections">{nav.map(([key,label])=><button type="button" key={key} className={section===key?"active":""} onClick={()=>setSection(key)}>{label}</button>)}</nav>
    {error&&<p className="sb-alert" role="alert">{error}</p>}{notice&&<p className="sb-success" role="status">{notice}</p>}
    {section==="shifts"&&<div className="hr-panel">
      <h2>Shift definitions & roster</h2>
      <div className="hr-form">
        <label>Roster from<input type="date" value={rosterStart} onChange={e=>setRosterStart(e.target.value)}/></label>
        <label>Roster to<input type="date" value={rosterEnd} onChange={e=>setRosterEnd(e.target.value)}/></label>
      </div>
      {manager&&<><form className="hr-form" onSubmit={e=>{e.preventDefault();act(()=>post("/hr/shifts",{...shift,establishment_id:Number(shift.establishment_id),break_minutes:Number(shift.break_minutes)}),"Shift definition created.");}}>
        <h3>Create shift definition</h3>
        <label>Establishment<select required value={shift.establishment_id} onChange={e=>setShift({...shift,establishment_id:e.target.value})}><option value="">Select establishment</option>{establishments.map(x=><option key={x.id} value={x.id}>{x.display_name}</option>)}</select></label>
        <label>Code<input required value={shift.code} onChange={e=>setShift({...shift,code:e.target.value})}/></label>
        <label>Name<input required value={shift.name} onChange={e=>setShift({...shift,name:e.target.value})}/></label>
        <label>Start<input type="time" required value={shift.local_start_time} onChange={e=>setShift({...shift,local_start_time:e.target.value})}/></label>
        <label>End<input type="time" required value={shift.local_end_time} onChange={e=>setShift({...shift,local_end_time:e.target.value})}/></label>
        <label>Break (minutes)<input type="number" min="0" max="720" value={shift.break_minutes} onChange={e=>setShift({...shift,break_minutes:e.target.value})}/></label>
        <label>Effective from<input type="date" required value={shift.effective_from} onChange={e=>setShift({...shift,effective_from:e.target.value})}/></label>
        <button disabled={busy}>Save shift</button>
      </form>
      <form className="hr-form" onSubmit={e=>{e.preventDefault();act(()=>post("/hr/shift-assignments",{...assignment,employee_id:Number(assignment.employee_id),shift_definition_id:Number(assignment.shift_definition_id),planned_start_at:new Date(assignment.planned_start_at).toISOString(),planned_end_at:new Date(assignment.planned_end_at).toISOString()}),"Roster assignment created.");}}>
        <h3>Assign shift</h3>
        <label>Employee<select required value={assignment.employee_id} onChange={e=>setAssignment({...assignment,employee_id:e.target.value})}><option value="">Select employee</option>{employees.map(x=><option key={x.id} value={x.id}>{x.employee_code} — {x.first_name} {x.last_name}</option>)}</select></label>
        <label>Shift<select required value={assignment.shift_definition_id} onChange={e=>setAssignment({...assignment,shift_definition_id:e.target.value})}><option value="">Select shift</option>{shifts.filter(x=>x.is_active).map(x=><option key={x.id} value={x.id}>{x.name} ({x.code})</option>)}</select></label>
        <label>Work date<input type="date" required value={assignment.work_date} onChange={e=>setAssignment({...assignment,work_date:e.target.value})}/></label>
        <label>Planned start<input type="datetime-local" required value={assignment.planned_start_at} onChange={e=>setAssignment({...assignment,planned_start_at:e.target.value})}/></label>
        <label>Planned end<input type="datetime-local" required value={assignment.planned_end_at} onChange={e=>setAssignment({...assignment,planned_end_at:e.target.value})}/></label>
        <button disabled={busy}>Assign shift</button>
      </form></>}
      <div className="hr-table-wrap"><table><thead><tr><th>Date</th><th>Employee</th><th>Shift</th><th>Planned</th><th>Status</th>{manager&&<th>Action</th>}</tr></thead><tbody>{assignments.map(x=><tr key={x.id}><td>{x.work_date}</td><td>{x.employee_code||"My roster"}</td><td>{x.shift_name||"Shift"}</td><td>{new Date(x.planned_start_at).toLocaleTimeString("en-IN",{hour:"2-digit",minute:"2-digit"})} – {new Date(x.planned_end_at).toLocaleTimeString("en-IN",{hour:"2-digit",minute:"2-digit"})}</td><td>{x.status}</td>{manager&&<td>{x.status==="draft"&&<button onClick={()=>act(()=>post("/hr/shift-assignments/"+x.id+"/publish",{}),"Shift published.")}>Publish</button>}{x.status!=="cancelled"&&<button onClick={()=>{const reason=window.prompt("Reason for cancelling this shift:");if(reason?.trim())act(()=>post("/hr/shift-assignments/"+x.id+"/cancel",{decision:"rejected",note:reason.trim()}),"Shift cancelled.");}}>Cancel</button>}</td>}</tr>)}</tbody></table></div>
    </div>}
    {section==="holidays"&&<div className="hr-panel"><h2>Holiday calendars</h2>{!manager&&<div className="hr-table-wrap"><table><thead><tr><th>Date</th><th>Holiday</th><th>Type</th><th>Calendar</th></tr></thead><tbody>{holidays.map(x=><tr key={x.id}><td>{x.holiday_date}</td><td>{x.name}</td><td>{x.holiday_type}</td><td>{x.calendar_name}</td></tr>)}</tbody></table></div>}{manager&&<>
      <form className="hr-form" onSubmit={e=>{e.preventDefault();act(()=>post("/hr/holiday-calendars",{...calendar,establishment_id:Number(calendar.establishment_id),effective_year:Number(calendar.effective_year)}),"Holiday calendar created.");}}>
        <label>Establishment<select required value={calendar.establishment_id} onChange={e=>setCalendar({...calendar,establishment_id:e.target.value})}><option value="">Select establishment</option>{establishments.map(x=><option key={x.id} value={x.id}>{x.display_name}</option>)}</select></label>
        <label>Calendar name<input required value={calendar.name} onChange={e=>setCalendar({...calendar,name:e.target.value})}/></label>
        <label>Region / state code<input value={calendar.region_code} onChange={e=>setCalendar({...calendar,region_code:e.target.value})}/></label>
        <label>Year<input type="number" min="2000" max="2200" value={calendar.effective_year} onChange={e=>setCalendar({...calendar,effective_year:e.target.value})}/></label>
        <button disabled={busy}>Create calendar</button>
      </form>
      <form className="hr-form" onSubmit={e=>{e.preventDefault();if(!calendarId){setError("Select a draft calendar first.");return;}act(()=>post("/hr/holiday-calendars/"+calendarId+"/holidays",{...holiday,location_code:holiday.location_code||null}),"Holiday added.");}}>
        <h3>Add holiday</h3>
        <label>Draft calendar<select value={calendarId} onChange={e=>setCalendarId(e.target.value)}><option value="">Select calendar</option>{calendars.filter(x=>x.status==="draft").map(x=><option key={x.id} value={x.id}>{x.name} · {x.effective_year}</option>)}</select></label>
        <label>Date<input type="date" required value={holiday.holiday_date} onChange={e=>setHoliday({...holiday,holiday_date:e.target.value})}/></label>
        <label>Name<input required value={holiday.name} onChange={e=>setHoliday({...holiday,name:e.target.value})}/></label>
        <label>Type<select value={holiday.holiday_type} onChange={e=>setHoliday({...holiday,holiday_type:e.target.value})}><option value="public">Public</option><option value="national">National</option><option value="regional">Regional</option><option value="optional">Optional</option><option value="company">Company</option></select></label>
        <label>Location code (optional)<input value={holiday.location_code} onChange={e=>setHoliday({...holiday,location_code:e.target.value})}/></label>
        <button disabled={busy}>Add holiday</button>
      </form>
    </>}
    <div className="hr-table-wrap"><table><thead><tr><th>Calendar</th><th>Year</th><th>Establishment</th><th>Holidays</th><th>Status</th>{manager&&<th>Action</th>}</tr></thead><tbody>{calendars.map(x=><tr key={x.id}><td>{x.name}</td><td>{x.effective_year}</td><td>{x.establishment_id}</td><td>{x.holiday_count||0}</td><td>{x.status}</td>{manager&&<td>{x.status==="draft"&&<button onClick={()=>act(()=>post("/hr/holiday-calendars/"+x.id+"/approve",{}),"Holiday calendar approved and locked.")}>Approve & lock</button>}</td>}</tr>)}</tbody></table></div>
    {manager&&calendarId&&<button onClick={()=>act(async()=>{const h=await apiRequest("/hr/holiday-calendars/"+calendarId+"/holidays");setHolidays(h.items||[]);},"Holiday list loaded.")}>Load selected calendar holidays</button>}
    {holidays.length>0&&<div className="hr-table-wrap"><table><thead><tr><th>Date</th><th>Holiday</th><th>Type</th><th>Paid</th></tr></thead><tbody>{holidays.map(x=><tr key={x.id}><td>{x.holiday_date}</td><td>{x.name}</td><td>{x.holiday_type}</td><td>{x.is_paid?"Yes":"No"}</td></tr>)}</tbody></table></div>}
    </div>}
    {section==="leave"&&<div className="hr-panel"><h2>Leave policies & balances</h2>{manager&&<>
      <form className="hr-form" onSubmit={e=>{e.preventDefault();act(()=>post("/hr/leave-policies",{...policy,establishment_id:Number(policy.establishment_id),entitlement_days:Number(policy.entitlement_days),carry_forward_cap:Number(policy.carry_forward_cap)}),"Leave policy created for review.");}}>
        <label>Establishment<select required value={policy.establishment_id} onChange={e=>setPolicy({...policy,establishment_id:e.target.value})}><option value="">Select establishment</option>{establishments.map(x=><option key={x.id} value={x.id}>{x.display_name}</option>)}</select></label>
        <label>Leave type<select value={policy.leave_type} onChange={e=>setPolicy({...policy,leave_type:e.target.value})}><option value="annual">Annual</option><option value="sick">Sick</option><option value="casual">Casual</option><option value="unpaid">Unpaid</option><option value="other">Other</option></select></label>
        <label>Policy version<input required value={policy.version_label} onChange={e=>setPolicy({...policy,version_label:e.target.value})}/></label>
        <label>Effective from<input type="date" required value={policy.effective_from} onChange={e=>setPolicy({...policy,effective_from:e.target.value})}/></label>
        <label>Effective to (optional)<input type="date" value={policy.effective_to||""} onChange={e=>setPolicy({...policy,effective_to:e.target.value||null})}/></label>
        <label>Annual entitlement (days)<input type="number" min="0" step=".01" value={policy.entitlement_days} onChange={e=>setPolicy({...policy,entitlement_days:e.target.value})}/></label>
        <label>Accrual frequency<select value={policy.accrual_frequency} onChange={e=>setPolicy({...policy,accrual_frequency:e.target.value})}><option value="none">No automatic accrual</option><option value="monthly">Monthly</option><option value="quarterly">Quarterly</option><option value="yearly">Yearly</option></select></label>
        <label>Carry-forward cap<input type="number" min="0" step=".01" value={policy.carry_forward_cap} onChange={e=>setPolicy({...policy,carry_forward_cap:e.target.value})}/></label>
        <label>Day count<select value={policy.day_count_basis} onChange={e=>setPolicy({...policy,day_count_basis:e.target.value})}><option value="working">Working days</option><option value="calendar">Calendar days</option></select></label>
        <label className="hr-check"><input type="checkbox" checked={policy.allow_negative_balance} onChange={e=>setPolicy({...policy,allow_negative_balance:e.target.checked})}/> Allow negative leave balance</label>
        <label className="hr-check"><input type="checkbox" checked={policy.encashment_allowed} onChange={e=>setPolicy({...policy,encashment_allowed:e.target.checked})}/> Encashment permitted (policy flag only)</label>
        <label className="hr-check"><input type="checkbox" checked={policy.probation_eligible} onChange={e=>setPolicy({...policy,probation_eligible:e.target.checked})}/> Probation employees accrue leave</label>
        <button disabled={busy}>Save draft policy</button>
      </form>
      <div className="hr-table-wrap"><table><thead><tr><th>Type</th><th>Version</th><th>Entitlement</th><th>Accrual</th><th>Status</th><th>Action</th></tr></thead><tbody>{policies.map(x=><tr key={x.id}><td>{x.leave_type}</td><td>{x.version_label}</td><td>{x.entitlement_days}</td><td>{x.accrual_frequency}</td><td>{x.status}</td><td>{x.status==="draft"&&<button onClick={()=>act(()=>post("/hr/leave-policies/"+x.id+"/approve",{}),"Leave policy approved.")}>Approve</button>}</td></tr>)}</tbody></table></div>
      <form className="hr-form" onSubmit={e=>{e.preventDefault();act(()=>post("/hr/leave/accruals",accrual),"Leave accrual processed idempotently.");}}>
        <h3>Run leave accrual</h3><label>Period start<input type="date" required value={accrual.period_start} onChange={e=>setAccrual({...accrual,period_start:e.target.value})}/></label><label>Period end<input type="date" required value={accrual.period_end} onChange={e=>setAccrual({...accrual,period_end:e.target.value})}/></label><button disabled={busy}>Calculate accrual</button>
      </form>
      <form className="hr-form" onSubmit={e=>{e.preventDefault();act(()=>post("/hr/leave-balances/opening",{...opening,employee_id:Number(opening.employee_id),policy_id:Number(opening.policy_id),quantity_days:Number(opening.quantity_days)}),"Opening leave balance recorded idempotently.");}}>
        <h3>Verified opening balance</h3>
        <label>Employee<select required value={opening.employee_id} onChange={e=>setOpening({...opening,employee_id:e.target.value})}><option value="">Select employee</option>{employees.map(x=><option key={x.id} value={x.id}>{x.employee_code} — {x.first_name}</option>)}</select></label>
        <label>Approved leave policy<select required value={opening.policy_id} onChange={e=>setOpening({...opening,policy_id:e.target.value})}><option value="">Select policy</option>{policies.filter(x=>x.status==="approved"&&x.leave_type===opening.leave_type).map(x=><option key={x.id} value={x.id}>{x.version_label} · {x.establishment_id}</option>)}</select></label>
        <label>Leave type<select value={opening.leave_type} onChange={e=>setOpening({...opening,leave_type:e.target.value,policy_id:""})}><option value="annual">Annual</option><option value="sick">Sick</option><option value="casual">Casual</option><option value="unpaid">Unpaid</option><option value="other">Other</option></select></label>
        <label>Opening days<input type="number" min=".01" step=".01" required value={opening.quantity_days} onChange={e=>setOpening({...opening,quantity_days:e.target.value})}/></label>
        <label>Effective date<input type="date" required value={opening.effective_date} onChange={e=>setOpening({...opening,effective_date:e.target.value})}/></label>
        <label>Evidence / reason<input required minLength="5" value={opening.reason} onChange={e=>setOpening({...opening,reason:e.target.value})}/></label>
        <button disabled={busy}>Record opening balance</button>
      </form>
      <form className="hr-form" onSubmit={e=>{e.preventDefault();act(()=>post("/hr/leave-balances/adjust",{...adjustment,employee_id:Number(adjustment.employee_id),quantity_days:Number(adjustment.quantity_days)}),"Leave adjustment recorded in immutable ledger.");}}>
        <h3>Authorised balance adjustment</h3><label>Employee<select required value={adjustment.employee_id} onChange={e=>setAdjustment({...adjustment,employee_id:e.target.value})}><option value="">Select employee</option>{employees.map(x=><option key={x.id} value={x.id}>{x.employee_code} — {x.first_name}</option>)}</select></label><label>Leave type<select value={adjustment.leave_type} onChange={e=>setAdjustment({...adjustment,leave_type:e.target.value})}><option value="annual">Annual</option><option value="sick">Sick</option><option value="casual">Casual</option><option value="unpaid">Unpaid</option><option value="other">Other</option></select></label><label>Days (+/-)<input type="number" step=".01" required value={adjustment.quantity_days} onChange={e=>setAdjustment({...adjustment,quantity_days:e.target.value})}/></label><label>Effective date<input type="date" required value={adjustment.effective_date} onChange={e=>setAdjustment({...adjustment,effective_date:e.target.value})}/></label><label>Reason<input required minLength="5" value={adjustment.reason} onChange={e=>setAdjustment({...adjustment,reason:e.target.value})}/></label><button disabled={busy}>Record adjustment</button>
      </form>
    </>}
    <div className="hr-table-wrap"><table><thead><tr><th>Employee</th><th>Leave type</th><th>Period</th><th>Opening</th><th>Accrued</th><th>Used</th><th>Adjusted</th><th>Closing</th></tr></thead><tbody>{balances.map(x=><tr key={x.id}><td>{x.employee_code||"My balance"}</td><td>{x.leave_type}</td><td>{x.period_start} – {x.period_end}</td><td>{x.opening_days}</td><td>{x.live_accrued_days??x.accrued_days}</td><td>{x.live_used_days??x.used_days}</td><td>{x.live_adjusted_days??x.adjusted_days}</td><td>{x.live_closing_days??x.closing_days}</td></tr>)}</tbody></table></div>
    <h3>Immutable leave ledger</h3><div className="hr-table-wrap"><table><thead><tr><th>Date</th><th>Employee</th><th>Type</th><th>Transaction</th><th>Days</th><th>Reason</th></tr></thead><tbody>{ledger.map(x=><tr key={x.id}><td>{x.effective_date}</td><td>{x.employee_code||"Me"}</td><td>{x.leave_type}</td><td>{x.transaction_type}</td><td>{x.quantity_days}</td><td>{x.reason}</td></tr>)}</tbody></table></div>
    </div>}
    {section==="lifecycle"&&<div className="hr-panel"><h2>Employee onboarding & offboarding</h2>{manager&&<>
      <form className="hr-form" onSubmit={e=>{e.preventDefault();act(()=>post("/hr/lifecycle/templates",{...template,establishment_id:template.establishment_id?Number(template.establishment_id):null}),"Lifecycle template created.");}}>
        <h3>Create checklist template</h3><label>Establishment<select value={template.establishment_id} onChange={e=>setTemplate({...template,establishment_id:e.target.value})}><option value="">All establishments</option>{establishments.map(x=><option key={x.id} value={x.id}>{x.display_name}</option>)}</select></label><label>Name<input required value={template.name} onChange={e=>setTemplate({...template,name:e.target.value})}/></label><label>Lifecycle type<select value={template.lifecycle_type} onChange={e=>setTemplate({...template,lifecycle_type:e.target.value})}><option value="onboarding">Onboarding</option><option value="offboarding">Offboarding</option></select></label><button disabled={busy}>Create template</button>
      </form>
      <form className="hr-form" onSubmit={e=>{e.preventDefault();if(!generate.template_id){setError("Select a lifecycle template.");return;}act(()=>post("/hr/lifecycle/employees/"+generate.employee_id+"/generate",{template_id:Number(generate.template_id),start_date:generate.start_date}),"Lifecycle checklist generated.");}}>
        <h3>Generate employee checklist</h3><label>Employee<select required value={generate.employee_id} onChange={e=>setGenerate({...generate,employee_id:e.target.value})}><option value="">Select employee</option>{employees.map(x=><option key={x.id} value={x.id}>{x.employee_code} — {x.first_name}</option>)}</select></label><label>Template<select required value={generate.template_id} onChange={e=>setGenerate({...generate,template_id:e.target.value})}><option value="">Select template</option>{templates.map(x=><option key={x.id} value={x.id}>{x.name} v{x.version} ({x.lifecycle_type})</option>)}</select></label><label>Start date<input type="date" value={generate.start_date} onChange={e=>setGenerate({...generate,start_date:e.target.value})}/></label><button disabled={busy}>Generate tasks</button>
      </form>
      {templates.map(x=><form className="hr-form" key={x.id} onSubmit={e=>{e.preventDefault();act(()=>post("/hr/lifecycle/templates/"+x.id+"/items",templateItem),"Checklist task added.");}}>
        <h3>Add task to {x.name} v{x.version}</h3><label>Task key<input required value={templateItem.task_key} onChange={e=>setTemplateItem({...templateItem,task_key:e.target.value})}/></label><label>Task label<input required value={templateItem.label} onChange={e=>setTemplateItem({...templateItem,label:e.target.value})}/></label><label>Owner role<select value={templateItem.owner_role} onChange={e=>setTemplateItem({...templateItem,owner_role:e.target.value})}>{["employee","manager","hr","finance","it","admin"].map(v=><option key={v}>{v}</option>)}</select></label><label>Due days from start<input type="number" value={templateItem.due_days_offset} onChange={e=>setTemplateItem({...templateItem,due_days_offset:e.target.value})}/></label><button disabled={busy}>Add template task</button>
      </form>)}
    </>}
    <div className="hr-table-wrap"><table><thead><tr><th>Employee</th><th>Task</th><th>Due</th><th>Owner</th><th>Status</th><th>Action</th></tr></thead><tbody>{tasks.map(x=><tr key={x.id}><td>{x.employee_code||"My task"}</td><td>{x.label}<small>{x.task_key}</small></td><td>{x.due_date||"—"}</td><td>{x.owner_user_id||x.owner_role||"Unassigned"}</td><td>{x.status}</td><td>{manager&&<select aria-label={"Assign "+x.label} value={x.owner_user_id||""} disabled={busy} onChange={e=>act(()=>patch("/hr/lifecycle/tasks/"+x.id,{status:x.status,owner_user_id:e.target.value?Number(e.target.value):null}),"Task assignment updated and audited.")}><option value="">Role queue</option>{employees.filter(emp=>emp.user_id).map(emp=><option key={emp.user_id} value={emp.user_id}>{emp.employee_code} · {emp.first_name} {emp.last_name}</option>)}</select>}{["pending","in_progress"].includes(x.status)&&<button disabled={busy} onClick={()=>{const note=window.prompt("Add completion note or evidence reference:");if(note?.trim())act(()=>patch("/hr/lifecycle/tasks/"+x.id,{status:"completed",completion_note:note.trim()}),"Task completed and audit event recorded.");}}>Complete</button>}</td></tr>)}</tbody></table></div>
    </div>}
    {busy&&<p role="status">Saving and refreshing…</p>}
  </section>;
}
