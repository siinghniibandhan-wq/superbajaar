import { useCallback, useEffect, useState } from "react";
import { apiRequest } from "../../services/api.js";
import "../catalogue/catalogue.css";
import "./HRWorkspace.css";
import HRStatutoryPolicies from "./HRStatutoryPolicies.jsx";
import HROverview from "./HROverview.jsx";
import HRAdvancedWorkflows from "./HRAdvancedWorkflows.jsx";
import OrganisationChart from "./OrganisationChart.jsx";
import { formatHRDateTime, toLocalDateTimeInput, todayHRDate } from "./hrDateTime.js";
import { exportPayslipsCsv } from "./hrPayslipExport.js";

const today = todayHRDate;
const money = v => new Intl.NumberFormat("en-IN",{style:"currency",currency:"INR"}).format(Number(v||0));

function downloadAttendanceCsv(rows) {
  const columns = [
    ["Employee code","employee_code"],["Employee","first_name"],["Last name","last_name"],
    ["Department","department_name"],["Clock in","clock_in_at"],["Clock out","clock_out_at"],
    ["Hours","hours"],["Late minutes","late_minutes"],["Early departure minutes","early_departure_minutes"],
    ["Overtime minutes","overtime_minutes"]
  ];
  const quote = value => '"' + String(value ?? "").replace(/"/g,'""') + '"';
  const csv = [columns.map(([label])=>quote(label)).join(","),...rows.filter(row=>row.id).map(row=>columns.map(([,key])=>quote(row[key])).join(","))].join("\r\n");
  const blob = new Blob(["\uFEFF",csv],{type:"text/csv;charset=utf-8;"});
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = "hr-attendance-register.csv";
  document.body.appendChild(link);
  link.click();
  link.remove();
  URL.revokeObjectURL(url);
}

function downloadPayslips(payslips, includeEmployee) {
  const csv = exportPayslipsCsv(payslips, { includeEmployee });
  const blob = new Blob([csv], { type: "text/csv;charset=utf-8;" });
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = includeEmployee ? "hr-payslip-register.csv" : "my-payslips.csv";
  document.body.appendChild(link);
  link.click();
  link.remove();
  URL.revokeObjectURL(url);
}

export default function HRWorkspace({onBack,currentUser}) {
  const manager=["super_admin","owner","admin","manager"].includes(currentUser?.role);
  const [tab,setTab]=useState("overview"),[employees,setEmployees]=useState([]),[departments,setDepartments]=useState([]),[employeeQuery,setEmployeeQuery]=useState("");
  const [attendance,setAttendance]=useState([]),[attendanceCorrections,setAttendanceCorrections]=useState([]),[leaves,setLeaves]=useState([]),[expenses,setExpenses]=useState([]);
  const [runs,setRuns]=useState([]),[payslips,setPayslips]=useState([]),[month,setMonth]=useState(today().slice(0,7));
  const [error,setError]=useState(""),[notice,setNotice]=useState(""),[busy,setBusy]=useState(false);
  const [overviewData,setOverviewData]=useState(null),[overviewError,setOverviewError]=useState(""),[overviewLoading,setOverviewLoading]=useState(false);
  const [dept,setDept]=useState({code:"",name:"",description:""});
  const [editingDepartment,setEditingDepartment]=useState(null);
  const [editingEmployee,setEditingEmployee]=useState(null);
  const [attendanceEdit,setAttendanceEdit]=useState({});
  const [attendanceEmployeeFilter,setAttendanceEmployeeFilter]=useState("");
  const [attendanceDepartmentFilter,setAttendanceDepartmentFilter]=useState("");
  const [salaryEmployeeId,setSalaryEmployeeId]=useState(null),[salaryRevisions,setSalaryRevisions]=useState([]);
  const [salaryDraft,setSalaryDraft]=useState({effective_from:today(),effective_to:"",basic_salary:"0",hra:"0",special_allowance:"0",other_allowance:"0",reason:""});
  const [earningAdjustments,setEarningAdjustments]=useState([]);
  const [earningDraft,setEarningDraft]=useState({employee_id:"",earning_type:"overtime",amount:"",hours:"",hourly_rate:"",reason:""});
  const [printingPayslip,setPrintingPayslip]=useState(null);
  const [emp,setEmp]=useState({user_id:"",employee_code:"",first_name:"",last_name:"",email:"",phone:"",department_id:"",designation:"",employment_type:"full_time",status:"active",joining_date:today(),exit_date:"",basic_salary:"0",hra:"0",special_allowance:"0",other_allowance:"0"});
  const [leave,setLeave]=useState({leave_type:"annual",start_date:today(),end_date:today(),days:"1",reason:""});
  const [expense,setExpense]=useState({category:"travel",amount:"",expense_date:today(),description:"",receipt_reference:""});
  const [period,setPeriod]=useState({period_start:today().slice(0,7)+"-01",period_end:today().slice(0,7)+"-"+new Date(new Date().getFullYear(),new Date().getMonth()+1,0).getDate(),notes:""});
  const [voucher,setVoucher]=useState({});
  const [deductionsJson,setDeductionsJson]=useState("{}"),[deductionNotesJson,setDeductionNotesJson]=useState("{}");

  const load=useCallback(async()=>{
    setBusy(true);setError("");
    try{
      const results=await Promise.all([apiRequest("/hr/employees"),apiRequest("/hr/departments"),apiRequest("/hr/leave"),apiRequest("/hr/expenses")]);
      setEmployees(results[0].items||[]);setDepartments(results[1].items||[]);setLeaves(results[2].items||[]);setExpenses(results[3].items||[]);
      if(manager){
        const last=new Date(Number(month.slice(0,4)),Number(month.slice(5,7)),0).getDate();
        const [a,r,earnings]=await Promise.all([
          apiRequest("/hr/attendance/register?start_date="+month+"-01&end_date="+month+"-"+String(last).padStart(2,"0")),
          apiRequest("/hr/payroll/runs"),
          apiRequest("/hr/payroll/earning-adjustments"),
        ]);
        setAttendance(a.items||[]);setRuns(r.items||[]);setEarningAdjustments(earnings.items||[]);
        setOverviewLoading(true);
        try{
          const overview=await apiRequest("/hr/overview?month="+month);
          setOverviewData(overview);setOverviewError("");
        }catch(overviewFailure){
          setOverviewError(overviewFailure.message||"Unable to load management overview.");
        }finally{setOverviewLoading(false);}
      }else{
        setOverviewData(null);setOverviewError("");
        const a=await apiRequest("/hr/attendance/me?month="+month);const p=await apiRequest("/hr/payroll/me/payslips");
        setAttendance(a.items||[]);setAttendanceCorrections([]);setPayslips(p.items||[]);
      }
    }catch(e){setError(e.message||"Unable to load HR records.");}finally{setBusy(false);}
  },[manager,month]);
  useEffect(()=>{load();},[load]);

  async function getAttendancePunchLocation(){
    if(!navigator.geolocation) return {};
    return new Promise(resolve=>navigator.geolocation.getCurrentPosition(
      position=>resolve({latitude:position.coords.latitude,longitude:position.coords.longitude,accuracy_meters:position.coords.accuracy}),
      ()=>resolve({}),
      {enableHighAccuracy:true,timeout:10000,maximumAge:0}
    ));
  }

  async function act(fn,message){
    setBusy(true);setError("");setNotice("");
    try{await fn();setNotice(message);await load();}
    catch(e){setError(e.message||"Operation failed.");}finally{setBusy(false);}
  }
  const post=(path,body)=>apiRequest(path,{method:"POST",body:JSON.stringify(body)});
  const patch=(path,body)=>apiRequest(path,{method:"PATCH",body:JSON.stringify(body)});
  const put=(path,body)=>apiRequest(path,{method:"PUT",body:JSON.stringify(body)});
  const salaryGross=Number(emp.basic_salary||0)+Number(emp.hra||0)+Number(emp.special_allowance||0)+Number(emp.other_allowance||0);
  const review=(path,decision)=>{
    const note=decision==="rejected"?window.prompt("Enter the reason for rejection:"):null;
    if(decision==="rejected"&&(!note||!note.trim())) return;
    return act(()=>patch(path,{decision,note:note?.trim()||null}),"Request "+decision+".");
  };
  const tabs=[{group:"Overview",items:[["overview","Overview"]]},...(manager?[{group:"Workforce",items:[["organisation","Organisation chart"],["people","People directory"]]}]:[]),{group:"Time & attendance",items:[["attendance","Attendance"],["leave","Leave"],["advanced","Planning & lifecycle"]]},{group:"Compensation",items:[["expenses","Expenses"],["payroll","Payroll"],["payslips","Payslips"]]},...(manager?[{group:"Compliance & insights",items:[["statutory","Statutory policies"]]}]:[])];
  const filteredEmployees=employees.filter(e=>[e.employee_code,e.first_name,e.last_name,e.email,e.department_name,e.designation].some(v=>String(v||"").toLowerCase().includes(employeeQuery.toLowerCase())));
  const open=attendance.find(x=>!x.clock_out_at);
  const visibleAttendance=attendance.filter(x=>(!attendanceEmployeeFilter||String(x.employee_id)===attendanceEmployeeFilter)&&(!attendanceDepartmentFilter||String(x.department_id)===attendanceDepartmentFilter));

  return <section className="sb-workspace hr-workspace">
    <button className="sb-back" onClick={onBack} type="button">← All workspaces</button>
    <p className="sb-eyebrow">PEOPLE · WORKFORCE · PAYROLL</p><h1>HR & Payroll</h1>
    <p>Employee records, self-service attendance, leave, reimbursements and controlled payroll.</p>
    {error&&<p className="sb-alert" role="alert">{error}</p>}{notice&&<p className="sb-success" role="status">{notice}</p>}
    <div className="hr-toolbar"><label>Month <input type="month" value={month} onChange={e=>setMonth(e.target.value)}/></label><button type="button" onClick={load} disabled={busy}>Refresh</button></div>
    <nav className="hr-nav" aria-label="HR sections">{tabs.map(group=><div className="hr-nav-group" key={group.group}><span>{group.group}</span><div className="hr-tabs">{group.items.map(([key,label])=><button key={key} type="button" className={tab===key?"active":""} aria-current={tab===key?"page":undefined} onClick={()=>setTab(key)}>{label}</button>)}</div></div>)}</nav>
    {tab==="overview"&&manager&&<HROverview data={overviewData} loading={overviewLoading} error={overviewError} onRefresh={load} onNavigate={setTab}/>}
    {tab==="overview"&&!manager&&<div className="hr-overview"><article><span>My attendance sessions</span><strong>{attendance.length}</strong><small>Selected month</small></article><article><span>My pending leave</span><strong>{leaves.filter(x=>x.status==="pending").length}</strong><small>Requests awaiting review</small></article><article><span>My pending expenses</span><strong>{expenses.filter(x=>x.status==="pending").length}</strong><small>Claims awaiting review</small></article><article><span>My payslips</span><strong>{payslips.length}</strong><small>Available salary statements</small></article><div className="hr-overview-note"><strong>Employee self-service</strong><p>View your attendance, leave requests, reimbursements and payslips using the sections above.</p></div></div>}
    {tab==="organisation"&&manager&&<OrganisationChart departments={departments}/>}
    {tab==="people"&&<div className="hr-panel">
      {manager&&<><h2>Department management</h2>
      <div className="hr-table-wrap"><table><thead><tr><th>Department</th><th>Description</th><th>Employees</th><th>Status</th><th>Actions</th></tr></thead><tbody>{departments.map(d=><tr key={d.id}><td>{d.name}<small>{d.code}</small></td><td>{d.description||"—"}</td><td>{d.employee_count||0}</td><td>{d.is_active?"Active":"Inactive"}</td><td><button type="button" disabled={busy||!d.is_active} onClick={()=>{setEditingDepartment(d.id);setDept({code:d.code,name:d.name,description:d.description||""});}}>Edit</button> {d.is_active&&<button type="button" disabled={busy} onClick={()=>{if(window.confirm("Deactivate this department? Existing employee records will be retained."))act(()=>post("/hr/departments/"+d.id+"/deactivate",{}),"Department deactivated.");}}>Deactivate</button>}</td></tr>)}</tbody></table></div>
      <form className="hr-form" onSubmit={e=>{e.preventDefault();act(async()=>{if(editingDepartment) await put("/hr/departments/"+editingDepartment,dept);else await post("/hr/departments",dept);},"Department "+(editingDepartment?"updated.":"created."));setDept({code:"",name:"",description:""});setEditingDepartment(null);}}>
        <h3>{editingDepartment?"Edit department":"Create department"}</h3>
        <label>Department code<input placeholder="e.g. HR" value={dept.code} onChange={e=>setDept({...dept,code:e.target.value})} required/></label>
        <label>Department name<input placeholder="e.g. Human Resources" value={dept.name} onChange={e=>setDept({...dept,name:e.target.value})} required/></label>
        <label>Description<input placeholder="What this department does" value={dept.description} onChange={e=>setDept({...dept,description:e.target.value})}/></label>
        <button disabled={busy}>{editingDepartment?"Save department":"Add department"}</button>{editingDepartment&&<button type="button" onClick={()=>{setEditingDepartment(null);setDept({code:"",name:"",description:""});}}>Cancel</button>}
      </form>
      <h2>{editingEmployee?"Edit employee":"Add employee"}</h2><details className="hr-disclosure" open={Boolean(editingEmployee)}><summary>{editingEmployee?"Edit employee":"Add employee"}</summary><form className="hr-form hr-grid" onSubmit={e=>{e.preventDefault();const body={...emp,user_id:emp.user_id?Number(emp.user_id):null,department_id:emp.department_id?Number(emp.department_id):null,exit_date:emp.exit_date||null,reports_to_employee_id:emp.reports_to_employee_id?Number(emp.reports_to_employee_id):null,basic_salary:Number(emp.basic_salary),hra:Number(emp.hra),special_allowance:Number(emp.special_allowance),other_allowance:Number(emp.other_allowance)};act(async()=>{if(editingEmployee) await put("/hr/employees/"+editingEmployee,body);else await post("/hr/employees",body);},"Employee "+(editingEmployee?"updated.":"created."));setEditingEmployee(null);setEmp({user_id:"",employee_code:"",first_name:"",last_name:"",email:"",phone:"",department_id:"",designation:"",employment_type:"full_time",status:"active",joining_date:today(),exit_date:"",basic_salary:"0",hra:"0",special_allowance:"0",other_allowance:"0"});}}>
        <label>Employee code<input placeholder="e.g. SB-0001" value={emp.employee_code} onChange={e=>setEmp({...emp,employee_code:e.target.value})} required/></label>
        <label>Linked staff user ID (optional)<input placeholder="Existing login account ID" type="number" value={emp.user_id} onChange={e=>setEmp({...emp,user_id:e.target.value})}/></label>
        <label>First name<input placeholder="First name" value={emp.first_name} onChange={e=>setEmp({...emp,first_name:e.target.value})} required/></label>
        <label>Last name<input placeholder="Last name" value={emp.last_name} onChange={e=>setEmp({...emp,last_name:e.target.value})}/></label>
        <label>Email<input placeholder="Work email" type="email" value={emp.email} onChange={e=>setEmp({...emp,email:e.target.value})} required/></label>
        <label>Phone<input placeholder="Mobile number" value={emp.phone} onChange={e=>setEmp({...emp,phone:e.target.value})}/></label>
        <label>Department<select value={emp.department_id} onChange={e=>setEmp({...emp,department_id:e.target.value})}><option value="">No department</option>{departments.filter(d=>d.is_active).map(d=><option key={d.id} value={d.id}>{d.name}</option>)}</select></label>
        <label>Designation / job title<input placeholder="e.g. Accounts Executive" value={emp.designation} onChange={e=>setEmp({...emp,designation:e.target.value})} required/></label>
        <label>Reporting manager<select value={emp.reports_to_employee_id||""} onChange={e=>setEmp({...emp,reports_to_employee_id:e.target.value})}><option value="">No reporting manager</option>{employees.filter(x=>x.id!==editingEmployee&&x.status!=="terminated").map(x=><option key={x.id} value={x.id}>{x.employee_code} — {x.first_name} {x.last_name||""}</option>)}</select></label>
        <label>Employment type<select value={emp.employment_type} onChange={e=>setEmp({...emp,employment_type:e.target.value})}><option value="full_time">Full-time</option><option value="part_time">Part-time</option><option value="contract">Contract</option><option value="intern">Intern</option><option value="shift_worker">Shift worker</option></select></label>
        <label>Employment status<select value={emp.status} onChange={e=>setEmp({...emp,status:e.target.value})}><option value="active">Active</option><option value="probation">Probation</option><option value="on_leave">On leave</option><option value="notice_period">Notice period</option><option value="terminated">Terminated</option></select></label>
        <label>Joining date<input type="date" value={emp.joining_date} onChange={e=>setEmp({...emp,joining_date:e.target.value})}/></label>
        <label>Last working date / exit date<input type="date" value={emp.exit_date||""} min={emp.joining_date} onChange={e=>setEmp({...emp,exit_date:e.target.value})}/><small>Leave blank while the employee is active.</small></label>
        <h3>Salary & compensation (₹ per month)</h3>
        <label>Basic salary<input type="number" min="0" step=".01" value={emp.basic_salary} disabled={Boolean(editingEmployee)} onChange={e=>setEmp({...emp,basic_salary:e.target.value})}/><small>{editingEmployee?"Use Salary history to submit an approved revision.":"Fixed basic pay used in salary calculations."}</small></label>
        <label>HRA — House Rent Allowance<input type="number" min="0" step=".01" value={emp.hra} disabled={Boolean(editingEmployee)} onChange={e=>setEmp({...emp,hra:e.target.value})}/><small>Monthly house rent allowance.</small></label>
        <label>Special allowance<input type="number" min="0" step=".01" value={emp.special_allowance} disabled={Boolean(editingEmployee)} onChange={e=>setEmp({...emp,special_allowance:e.target.value})}/><small>Additional fixed monthly allowance.</small></label>
        <label>Other allowance<input type="number" min="0" step=".01" value={emp.other_allowance} disabled={Boolean(editingEmployee)} onChange={e=>setEmp({...emp,other_allowance:e.target.value})}/><small>Other monthly earnings.</small></label>
        <div className="hr-gross-preview"><strong>Monthly gross salary: {money(salaryGross)}</strong><small>Before employee deductions and employer contributions.</small></div>
        <button disabled={busy}>{editingEmployee?"Save employee changes":"Create employee"}</button>
        {editingEmployee&&<button type="button" onClick={()=>{setEditingEmployee(null);setEmp({user_id:"",employee_code:"",first_name:"",last_name:"",email:"",phone:"",department_id:"",designation:"",employment_type:"full_time",status:"active",joining_date:today(),exit_date:"",basic_salary:"0",hra:"0",special_allowance:"0",other_allowance:"0"});}}>Cancel edit</button>}
      </form></details>
      <h2>Employee directory</h2><label className="hr-search">Search employees<input type="search" placeholder="Search name, code, email, department or role" value={employeeQuery} onChange={e=>setEmployeeQuery(e.target.value)}/></label><div className="hr-table-wrap"><table><thead><tr><th>Code</th><th>Employee</th><th>Department</th><th>Designation</th><th>Status</th>{manager&&<><th>Monthly gross</th><th>Actions</th></>}</tr></thead><tbody>{filteredEmployees.map(e=><tr key={e.id}><td>{e.employee_code}</td><td>{e.first_name} {e.last_name}<small>{e.email}</small></td><td>{e.department_name||"—"}</td><td>{e.designation}</td><td>{e.status}</td>{manager&&<td>{money(Number(e.basic_salary||0)+Number(e.hra||0)+Number(e.special_allowance||0)+Number(e.other_allowance||0))}</td>}{manager&&<td><button type="button" onClick={()=>{setEditingEmployee(e.id);setEmp({user_id:e.user_id||"",employee_code:e.employee_code,first_name:e.first_name,last_name:e.last_name||"",email:e.email,phone:e.phone||"",department_id:e.department_id||"",designation:e.designation,reports_to_employee_id:e.reports_to_employee_id||"",employment_type:e.employment_type,status:e.status,joining_date:String(e.joining_date).slice(0,10),exit_date:e.exit_date||"",basic_salary:e.basic_salary||0,hra:e.hra||0,special_allowance:e.special_allowance||0,other_allowance:e.other_allowance||0});window.scrollTo({top:0,behavior:"smooth"});}}>Edit</button> <button type="button" onClick={async()=>{setError("");try{const result=await apiRequest("/hr/employees/"+e.id+"/salary-revisions");setSalaryRevisions(result.items||[]);setSalaryEmployeeId(e.id);setSalaryDraft({effective_from:today(),effective_to:"",basic_salary:String(e.basic_salary||0),hra:String(e.hra||0),special_allowance:String(e.special_allowance||0),other_allowance:String(e.other_allowance||0),reason:""});}catch(err){setError(err.message||"Unable to load salary history.");}}}>Salary history</button></td>}</tr>)}</tbody></table></div>
      {salaryEmployeeId&&<section className="hr-panel hr-salary-history" aria-label="Salary revision history">
        <div className="hr-payslips-heading"><h2>Salary history — {employees.find(e=>e.id===salaryEmployeeId)?.employee_code||"Employee"}</h2><button type="button" className="secondary" onClick={()=>setSalaryEmployeeId(null)}>Close</button></div>
        <p>Salary revisions are effective-dated. Draft revisions do not affect payroll until approved. Approved periods cannot overlap.</p>
        <form className="hr-form hr-grid" onSubmit={e=>{e.preventDefault();act(async()=>{const created=await post("/hr/employees/"+salaryEmployeeId+"/salary-revisions",{...salaryDraft,effective_to:salaryDraft.effective_to||null,basic_salary:Number(salaryDraft.basic_salary),hra:Number(salaryDraft.hra),special_allowance:Number(salaryDraft.special_allowance),other_allowance:Number(salaryDraft.other_allowance)});setSalaryRevisions(current=>[created,...current]);setSalaryDraft({...salaryDraft,reason:""});},"Salary revision submitted for approval.");}}>
          <label>Effective from<input type="date" value={salaryDraft.effective_from} onChange={e=>setSalaryDraft({...salaryDraft,effective_from:e.target.value})} required/></label>
          <label>Effective to (optional)<input type="date" min={salaryDraft.effective_from} value={salaryDraft.effective_to} onChange={e=>setSalaryDraft({...salaryDraft,effective_to:e.target.value})}/></label>
          <label>Basic salary (₹ / month)<input type="number" min="0" step=".01" value={salaryDraft.basic_salary} onChange={e=>setSalaryDraft({...salaryDraft,basic_salary:e.target.value})} required/></label>
          <label>HRA (₹ / month)<input type="number" min="0" step=".01" value={salaryDraft.hra} onChange={e=>setSalaryDraft({...salaryDraft,hra:e.target.value})} required/></label>
          <label>Special allowance (₹ / month)<input type="number" min="0" step=".01" value={salaryDraft.special_allowance} onChange={e=>setSalaryDraft({...salaryDraft,special_allowance:e.target.value})} required/></label>
          <label>Other allowance (₹ / month)<input type="number" min="0" step=".01" value={salaryDraft.other_allowance} onChange={e=>setSalaryDraft({...salaryDraft,other_allowance:e.target.value})} required/></label>
          <label className="hr-span-all">Reason for revision<textarea value={salaryDraft.reason} minLength={5} maxLength={500} onChange={e=>setSalaryDraft({...salaryDraft,reason:e.target.value})} required/></label>
          <button type="submit" disabled={busy}>Submit salary revision</button>
        </form>
        <div className="hr-table-wrap"><table><thead><tr><th>Effective period</th><th>Monthly gross</th><th>Status</th><th>Reason / review</th><th>Action</th></tr></thead><tbody>
          {salaryRevisions.map(v=><tr key={v.id}><td>{String(v.effective_from).slice(0,10)} — {v.effective_to?String(v.effective_to).slice(0,10):"Ongoing"}</td><td>{money(Number(v.basic_salary)+Number(v.hra)+Number(v.special_allowance)+Number(v.other_allowance))}</td><td>{v.status}</td><td>{v.reason}{v.review_note&&<small>{v.review_note}</small>}</td><td>{v.status==="draft"&&<><button type="button" disabled={busy} onClick={()=>act(async()=>{const updated=await post("/hr/employees/"+salaryEmployeeId+"/salary-revisions/"+v.id+"/review",{decision:"approved",note:null});setSalaryRevisions(current=>current.map(item=>item.id===updated.id?{...item,...updated}:item));},"Salary revision approved.")}>Approve</button> <button type="button" disabled={busy} onClick={()=>{const note=window.prompt("Reason for rejecting this salary revision:");if(note&&note.trim())act(async()=>{const updated=await post("/hr/employees/"+salaryEmployeeId+"/salary-revisions/"+v.id+"/review",{decision:"rejected",note:note.trim()});setSalaryRevisions(current=>current.map(item=>item.id===updated.id?{...item,...updated}:item));},"Salary revision rejected.");}}>Reject</button></>}</td></tr>)}
          {!salaryRevisions.length&&<tr><td colSpan={5}>No salary history available.</td></tr>}
        </tbody></table></div>
      </section>}
       </>}
    </div>}
    {tab==="attendance"&&<div className="hr-panel">
      {!manager&&<div className="hr-punch-card"><h2>My attendance</h2><p>{open?"Currently clocked in":"Not currently clocked in"}</p><button disabled={busy} onClick={()=>act(async()=>{const location=await getAttendancePunchLocation();await post("/hr/attendance/punch",{punch_type:open?"clock_out":"clock_in",...location});},open?"Clocked out.":"Clocked in.")}>{open?"Clock out":"Clock in"}</button></div>}
      <h2>{manager?"Attendance register":"My attendance log"}</h2>{manager&&<div className="hr-toolbar"><label>Employee <select value={attendanceEmployeeFilter} onChange={e=>setAttendanceEmployeeFilter(e.target.value)}><option value="">All employees</option>{employees.filter(e=>e.status!=="terminated").map(e=><option key={e.id} value={e.id}>{e.employee_code} — {e.first_name} {e.last_name||""}</option>)}</select></label><label>Department <select value={attendanceDepartmentFilter} onChange={e=>setAttendanceDepartmentFilter(e.target.value)}><option value="">All departments</option>{departments.map(d=><option key={d.id} value={d.id}>{d.name}</option>)}</select></label><button type="button" onClick={()=>downloadAttendanceCsv(visibleAttendance)}>Export CSV / Excel</button><button type="button" onClick={()=>window.print()}>Print / Save PDF</button></div>}<div className="hr-overview">{manager&&<><article><span>Sessions</span><strong>{visibleAttendance.filter(x=>x.id).length}</strong><small>Selected month</small></article><article><span>Late minutes</span><strong>{visibleAttendance.reduce((n,x)=>n+Number(x.late_minutes||0),0)}</strong><small>Published shifts only</small></article><article><span>Overtime minutes</span><strong>{visibleAttendance.reduce((n,x)=>n+Number(x.overtime_minutes||0),0)}</strong><small>Before payroll approval</small></article></>}</div><div className="hr-table-wrap"><table><thead><tr><th>Employee / session</th><th>Clock in</th><th>Clock out</th><th>Hours</th>{manager&&<><th>Late</th><th>Early</th><th>Overtime</th><th>HR action</th></>}</tr></thead><tbody>{visibleAttendance.map((a,i)=><tr key={a.id||i}><td>{a.employee_code||"Session"} {a.first_name||""} {a.last_name||""}</td><td>{formatHRDateTime(a.clock_in_at)}</td><td>{a.clock_out_at?formatHRDateTime(a.clock_out_at):"Open"}</td><td>{a.hours??"—"}</td>{manager&&<><td>{a.late_minutes==null?"—":a.late_minutes+" min"}</td><td>{a.early_departure_minutes==null?"—":a.early_departure_minutes+" min"}</td><td>{a.overtime_minutes==null?"—":a.overtime_minutes+" min"}</td><td>{a.id&&<button type="button" onClick={()=>setAttendanceEdit({id:a.id,clock_in_at:toLocalDateTimeInput(a.clock_in_at),clock_out_at:toLocalDateTimeInput(a.clock_out_at),reason:""})}>Request correction</button>}</td></>}</tr>)}{!visibleAttendance.filter(x=>x.id).length&&<tr><td colSpan={manager?8:4}>No attendance sessions recorded for this period.</td></tr>}</tbody></table></div>{manager&&<section className="hr-panel"><h3>Correction requests awaiting independent review</h3><div className="hr-table-wrap"><table><thead><tr><th>Employee</th><th>Requested check-in</th><th>Requested check-out</th><th>Reason</th><th>Review</th></tr></thead><tbody>{attendanceCorrections.map(x=><tr key={x.id}><td>{x.employee_code} {x.first_name} {x.last_name}</td><td>{formatHRDateTime(x.requested_clock_in_at)}</td><td>{x.requested_clock_out_at?formatHRDateTime(x.requested_clock_out_at):"Open"}</td><td>{x.reason}</td><td><button type="button" disabled={Number(x.requested_by_user_id)===Number(currentUser?.id)} onClick={()=>review("/hr/attendance/corrections/"+x.id+"/review","approved")}>Approve</button> <button type="button" disabled={Number(x.requested_by_user_id)===Number(currentUser?.id)} onClick={()=>review("/hr/attendance/corrections/"+x.id+"/review","rejected")}>Reject</button></td></tr>)}{!attendanceCorrections.length&&<tr><td colSpan="5">No pending corrections.</td></tr>}</tbody></table></div></section>}
      {manager&&attendanceEdit.id&&<form className="hr-form" onSubmit={e=>{e.preventDefault();act(()=>patch("/hr/attendance/sessions/"+attendanceEdit.id,{clock_in_at:new Date(attendanceEdit.clock_in_at).toISOString(),clock_out_at:attendanceEdit.clock_out_at?new Date(attendanceEdit.clock_out_at).toISOString():null,reason:attendanceEdit.reason}),"Correction submitted for independent approval.");setAttendanceEdit({});}}>
        <h3>Correct attendance session #{attendanceEdit.id}</h3>
        <label>Check-in<input type="datetime-local" value={attendanceEdit.clock_in_at} onChange={e=>setAttendanceEdit({...attendanceEdit,clock_in_at:e.target.value})} required/></label>
        <label>Check-out (optional)<input type="datetime-local" value={attendanceEdit.clock_out_at} onChange={e=>setAttendanceEdit({...attendanceEdit,clock_out_at:e.target.value})}/></label>
        <label>Reason for correction<input value={attendanceEdit.reason} onChange={e=>setAttendanceEdit({...attendanceEdit,reason:e.target.value})} minLength="5" required/></label>
        <button disabled={busy}>Save correction</button><button type="button" onClick={()=>setAttendanceEdit({})}>Cancel</button>
      </form>}
    </div>}
    {tab==="leave"&&<div className="hr-panel"><h2>Leave requests</h2>{!manager&&<form className="hr-form" onSubmit={e=>{e.preventDefault();act(()=>post("/hr/leave",{...leave,days:Number(leave.days)}),"Leave request submitted.");}}><select value={leave.leave_type} onChange={e=>setLeave({...leave,leave_type:e.target.value})}><option value="annual">Annual</option><option value="sick">Sick</option><option value="casual">Casual</option><option value="unpaid">Unpaid</option><option value="other">Other</option></select><input type="date" value={leave.start_date} onChange={e=>setLeave({...leave,start_date:e.target.value})}/><input type="date" value={leave.end_date} onChange={e=>setLeave({...leave,end_date:e.target.value})}/><input type="number" min=".5" step=".5" value={leave.days} onChange={e=>setLeave({...leave,days:e.target.value})}/><input placeholder="Reason" value={leave.reason} onChange={e=>setLeave({...leave,reason:e.target.value})} required/><button>Submit leave</button></form>}<div className="hr-table-wrap"><table><thead><tr><th>Employee</th><th>Type</th><th>Dates</th><th>Days</th><th>Status</th><th>Review note</th>{manager&&<th>Review</th>}{!manager&&<th>Action</th>}</tr></thead><tbody>{leaves.map(x=><tr key={x.id}><td>{x.employee_code||"My request"} {x.first_name||""} {x.last_name||""}</td><td>{x.leave_type}</td><td>{x.start_date} – {x.end_date}</td><td>{x.days}</td><td>{x.status}</td><td>{x.review_note||"—"}</td>{manager&&<td>{x.status==="pending"&&<><button onClick={()=>review("/hr/leave/"+x.id+"/review","approved")}>Approve</button> <button onClick={()=>review("/hr/leave/"+x.id+"/review","rejected")}>Reject</button></>}</td>}{!manager&&<td>{["pending","approved"].includes(x.status)&&<button onClick={()=>{const reason=window.prompt("Reason for cancelling this leave request:");if(reason?.trim())act(()=>post("/hr/leave/"+x.id+"/cancel",{reason:reason.trim()}),"Leave request cancelled.");}}>Cancel</button>}</td>}</tr>)}{!leaves.length&&<tr><td colSpan={7}>No leave requests for this period.</td></tr>}</tbody></table></div></div>}
    {tab==="expenses"&&<div className="hr-panel"><h2>Expense claims</h2>{!manager&&<form className="hr-form" onSubmit={e=>{e.preventDefault();act(()=>post("/hr/expenses",{...expense,amount:Number(expense.amount)}),"Expense claim submitted.");}}><input placeholder="Category" value={expense.category} onChange={e=>setExpense({...expense,category:e.target.value})}/><input type="number" min=".01" step=".01" placeholder="Amount INR" value={expense.amount} onChange={e=>setExpense({...expense,amount:e.target.value})} required/><input type="date" value={expense.expense_date} onChange={e=>setExpense({...expense,expense_date:e.target.value})}/><input placeholder="Description" value={expense.description} onChange={e=>setExpense({...expense,description:e.target.value})} required/><input placeholder="Receipt reference" value={expense.receipt_reference} onChange={e=>setExpense({...expense,receipt_reference:e.target.value})}/><button>Submit claim</button></form>}<div className="hr-table-wrap"><table><thead><tr><th>Employee</th><th>Date</th><th>Category</th><th>Amount</th><th>Receipt reference</th><th>Status</th><th>Review note</th>{manager&&<th>Review</th>}</tr></thead><tbody>{expenses.map(x=><tr key={x.id}><td>{x.employee_code||"My claim"} {x.first_name||""} {x.last_name||""}</td><td>{x.expense_date}</td><td>{x.category}</td><td>{money(x.amount)}</td><td>{x.receipt_reference||"—"}</td><td>{x.status}</td><td>{x.review_note||"—"}</td>{manager&&<td>{x.status==="pending"&&<><button onClick={()=>review("/hr/expenses/"+x.id+"/review","approved")}>Approve</button> <button onClick={()=>review("/hr/expenses/"+x.id+"/review","rejected")}>Reject</button></>}</td>}</tr>)}{!expenses.length&&<tr><td colSpan={manager?8:7}>No expense claims submitted for this period.</td></tr>}</tbody></table></div></div>}
    {tab==="payroll"&&<div className="hr-panel">{manager?<><h2>Payroll</h2><p>Monthly salary components, approved reimbursements and approved statutory policy calculations are included. Runs with missing employee profiles or statutory policies remain unapprovable until corrected and recalculated.</p>
      <section className="hr-variable-pay">
        <h3>Overtime & variable earnings</h3>
        <p>Submit overtime, incentives, bonuses, arrears or final-settlement components for review. Only approved items are included in the selected payroll month.</p>
        <form className="hr-form hr-grid" onSubmit={e=>{e.preventDefault();const overtime=earningDraft.earning_type==="overtime";const employeeId=Number(earningDraft.employee_id);const body={earning_type:earningDraft.earning_type,period_start:period.period_start,period_end:period.period_end,amount:overtime?(Number(earningDraft.hours)*Number(earningDraft.hourly_rate)).toFixed(2):Number(earningDraft.amount).toFixed(2),hours:overtime?Number(earningDraft.hours):null,hourly_rate:overtime?Number(earningDraft.hourly_rate):null,reason:earningDraft.reason};act(async()=>{await post("/hr/employees/"+employeeId+"/earning-adjustments",body);const result=await apiRequest("/hr/payroll/earning-adjustments");setEarningAdjustments(result.items||[]);setEarningDraft({...earningDraft,amount:"",hours:"",hourly_rate:"",reason:""});},"Variable earning submitted for review.");}}>
          <label>Employee<select value={earningDraft.employee_id} onChange={e=>setEarningDraft({...earningDraft,employee_id:e.target.value})} required><option value="">Select employee</option>{employees.filter(e=>e.status!=="terminated").map(e=><option key={e.id} value={e.id}>{e.employee_code} — {e.first_name} {e.last_name||""}</option>)}</select></label>
          <label>Earning type<select value={earningDraft.earning_type} onChange={e=>setEarningDraft({...earningDraft,earning_type:e.target.value,amount:"",hours:"",hourly_rate:""})}><option value="overtime">Overtime</option><option value="incentive">Incentive</option><option value="bonus">Bonus</option><option value="arrears">Salary arrears</option><option value="leave_encashment">Leave encashment</option><option value="gratuity">Gratuity</option><option value="notice_pay">Notice pay</option><option value="final_settlement">Other final settlement</option></select></label>
          <label>Payroll period<output>{period.period_start} – {period.period_end}</output></label>
          {earningDraft.earning_type==="overtime"?<>
            <label>Overtime hours<input type="number" min=".01" step=".01" value={earningDraft.hours} onChange={e=>setEarningDraft({...earningDraft,hours:e.target.value})} required/></label>
            <label>Hourly rate (₹)<input type="number" min=".01" step=".01" value={earningDraft.hourly_rate} onChange={e=>setEarningDraft({...earningDraft,hourly_rate:e.target.value})} required/></label>
            <label>Calculated overtime (₹)<output>{money(Number(earningDraft.hours||0)*Number(earningDraft.hourly_rate||0))}</output></label>
          </>:<label>Amount (₹)<input type="number" min=".01" step=".01" value={earningDraft.amount} onChange={e=>setEarningDraft({...earningDraft,amount:e.target.value})} required/></label>}
          <label className="hr-span-all">Reason<textarea value={earningDraft.reason} minLength={5} maxLength={500} onChange={e=>setEarningDraft({...earningDraft,reason:e.target.value})} required/></label>
          <button type="submit" disabled={busy||!employees.length}>Submit for review</button>
        </form>
        <div className="hr-table-wrap"><table><thead><tr><th>Employee</th><th>Type</th><th>Amount</th><th>Period</th><th>Status</th><th>Reason</th><th>Review</th></tr></thead><tbody>
          {earningAdjustments.filter(a=>a.period_start===period.period_start).map(a=><tr key={a.id}><td>{a.employee_code} — {a.first_name} {a.last_name||""}</td><td>{a.earning_type}</td><td>{money(a.amount)}</td><td>{a.period_start}</td><td>{a.status}</td><td>{a.reason}{a.review_note&&<small>{a.review_note}</small>}</td><td>{a.status==="pending"&&<><button type="button" disabled={busy} onClick={()=>act(async()=>{await post("/hr/payroll/earning-adjustments/"+a.id+"/review",{decision:"approved",note:null});const result=await apiRequest("/hr/payroll/earning-adjustments");setEarningAdjustments(result.items||[]);},"Variable earning approved.")}>Approve</button> <button type="button" disabled={busy} onClick={()=>{const note=window.prompt("Reason for rejecting this earning:");if(note&&note.trim())act(async()=>{await post("/hr/payroll/earning-adjustments/"+a.id+"/review",{decision:"rejected",note:note.trim()});const result=await apiRequest("/hr/payroll/earning-adjustments");setEarningAdjustments(result.items||[]);},"Variable earning rejected.");}}>Reject</button></>}</td></tr>)}
          {!earningAdjustments.some(a=>a.period_start===period.period_start)&&<tr><td colSpan={7}>No variable earnings for this payroll period.</td></tr>}
        </tbody></table></div>
      </section>
      <form className="hr-form" onSubmit={e=>{e.preventDefault();act(()=>post("/hr/payroll/runs",{...period,deductions_by_employee:JSON.parse(deductionsJson||"{}"),deduction_notes:JSON.parse(deductionNotesJson||"{}")}),"Payroll calculated for review.");}}><label>Period start<input type="date" value={period.period_start} onChange={e=>setPeriod({...period,period_start:e.target.value})}/></label><label>Period end<input type="date" value={period.period_end} onChange={e=>setPeriod({...period,period_end:e.target.value})}/></label><input placeholder="Notes" value={period.notes} onChange={e=>setPeriod({...period,notes:e.target.value})}/><textarea aria-label="Manual payroll deductions by employee ID" placeholder='Manual deductions JSON, e.g. {"123": 1500}' value={deductionsJson} onChange={e=>setDeductionsJson(e.target.value)}/><textarea aria-label="Manual deduction notes by employee ID" placeholder='Reason JSON, e.g. {"123": "Approved salary advance recovery"}' value={deductionNotesJson} onChange={e=>setDeductionNotesJson(e.target.value)}/><button disabled={busy}>Calculate payroll</button></form><div className="hr-table-wrap"><table><thead><tr><th>Period</th><th>Status</th><th>Gross</th><th>Employee deductions</th><th>Employer contributions</th><th>Accrual journals</th><th>Net</th><th>Payment voucher</th><th>Action</th></tr></thead><tbody>{runs.map(r=><tr key={r.id}><td>{r.period_start} – {r.period_end}</td><td>{r.status}</td><td>{money(r.total_gross)}</td><td>{money(r.total_deductions)}</td><td>{money(r.total_employer_contributions||0)}</td><td>{(r.accounting_accrual_postings||[]).map(p=>p.legal_entity_code+": #"+p.voucher_id).join(", ")||r.accounting_accrual_voucher_id||"—"}</td><td>{money(r.total_net)}</td><td>{r.accounting_voucher_id||"—"}</td><td>{r.status==="calculated"&&<button disabled={!r.statutory_ready} title={!r.statutory_ready?"Complete statutory profiles and all four policy snapshots before approval":""} onClick={()=>act(()=>post("/hr/payroll/runs/"+r.id+"/approve",{decision:"approved"}),"Payroll approved.")}>Approve</button>}{r.status==="approved"&&<><input type="number" placeholder="Posted voucher ID" value={voucher[r.id]||""} onChange={e=>setVoucher({...voucher,[r.id]:e.target.value})}/><button onClick={()=>act(()=>post("/hr/payroll/runs/"+r.id+"/pay",{accounting_voucher_id:Number(voucher[r.id])}),"Payroll linked to Accounting payment.")}>Link payment</button></>}</td></tr>)}</tbody></table></div>{runs.map(r=><button className="hr-secondary" key={r.id} onClick={()=>act(async()=>{const p=await apiRequest("/hr/payroll/runs/"+r.id+"/payslips");setPayslips(p.items||[]);setTab("payslips");},"Payslips loaded.")}>View payslips #{r.id}</button>)}</>:<><h2>My payslips</h2><div className="hr-table-wrap"><table><thead><tr><th>Period</th><th>Gross</th><th>Reimbursements</th><th>Employee deductions</th><th>Employer contributions</th><th>Net pay</th></tr></thead><tbody>{payslips.map(p=><tr key={p.id}><td>{p.period_start} – {p.period_end}</td><td>{money(p.gross_earnings)}</td><td>{money(p.reimbursements)}</td><td>{money(p.deductions)}</td><td>{money(p.employer_contributions||0)}</td><td>{money(p.net_pay)}</td></tr>)}</tbody></table></div></>}</div>}
    {tab==="statutory"&&manager&&<HRStatutoryPolicies/>}
    {tab==="advanced"&&<HRAdvancedWorkflows manager={manager}/>}
    {tab==="payslips"&&<div className="hr-panel"><div className="hr-payslips-heading"><h2>{manager?"Payslips":"My payslips"}</h2><button type="button" className="secondary" onClick={()=>downloadPayslips(payslips,manager)} disabled={!payslips.length}>Export CSV</button></div><div className="hr-table-wrap"><table><thead><tr>{manager&&<th>Employee</th>}<th>Pay period</th><th>Gross</th><th>Reimbursements</th><th>Employee deductions</th><th>Employer contributions</th><th>Net pay</th><th>Breakdown</th><th>PDF</th></tr></thead><tbody>{payslips.map(p=><tr key={p.id}>{manager&&<td>{p.employee_code} {p.first_name} {p.last_name}</td>}<td>{p.period_start} – {p.period_end}</td><td>{money(p.gross_earnings)}</td><td>{money(p.reimbursements)}</td><td>{money(p.deductions)}</td><td>{money(p.employer_contributions||0)}</td><td>{money(p.net_pay)}</td><td><details className="hr-payslip-breakdown"><summary>View breakdown</summary><div><strong>Earnings</strong>{Object.entries(p.earnings_breakdown||{}).filter(([,value])=>value===null||typeof value!=="object").map(([key,value])=><p key={key}>{key.replaceAll("_"," ").replace(/^./,letter=>letter.toUpperCase())}: {money(value)}</p>)}{(p.earnings_breakdown?.variable_earnings||[]).map((item,index)=><p key={item.id||index}>{item.type}: {money(item.amount)}{item.hours? " ("+item.hours+" hours × "+money(item.hourly_rate)+")":""} — {item.reason}</p>)}<strong>Deductions</strong><p>Manual deduction: {money(p.deduction_breakdown?.manual_deduction)}</p>{p.deduction_breakdown?.manual_note&&<p>Reason: {p.deduction_breakdown.manual_note}</p>}{Object.entries(p.deduction_breakdown?.statutory||{}).map(([component,value])=><p key={component}>{component.toUpperCase()}: Employee {money(value.employee_amount)} · Employer {money(value.employer_amount)}</p>)}</div></details></td><td><button type="button" className="secondary" onClick={()=>{setPrintingPayslip(p);window.setTimeout(()=>window.print(),150);}}>Print / Save PDF</button></td></tr>)}{!payslips.length&&<tr><td colSpan={manager?9:8}>No approved payslips are available for this period.</td></tr>}</tbody></table></div>
      {printingPayslip&&<article className="hr-print-payslip">
        <header><h1>Super Bajaar</h1><p>Employee salary statement</p></header>
        <h2>Payslip — {String(printingPayslip.period_start).slice(0,7)}</h2>
        <p><strong>Employee:</strong> {printingPayslip.employee_code||""} {printingPayslip.first_name||""} {printingPayslip.last_name||""}</p>
        <p><strong>Pay period:</strong> {printingPayslip.period_start} to {printingPayslip.period_end}</p>
        <h3>Earnings</h3>
        <table><tbody>{Object.entries(printingPayslip.earnings_breakdown||{}).filter(([,value])=>value===null||typeof value!=="object").map(([key,value])=><tr key={key}><td>{key.replaceAll("_"," ").replace(/^./,letter=>letter.toUpperCase())}</td><td>{money(value)}</td></tr>)}
          {(printingPayslip.earnings_breakdown?.variable_earnings||[]).map((item,index)=><tr key={item.id||index}><td>{item.type} — {item.reason}</td><td>{money(item.amount)}</td></tr>)}
          <tr><th>Gross earnings</th><th>{money(printingPayslip.gross_earnings)}</th></tr>
          <tr><td>Reimbursements</td><td>{money(printingPayslip.reimbursements)}</td></tr>
        </tbody></table>
        <h3>Deductions & contributions</h3>
        <table><tbody><tr><td>Employee deductions</td><td>{money(printingPayslip.deductions)}</td></tr>
          <tr><td>Manual deduction</td><td>{money(printingPayslip.deduction_breakdown?.manual_deduction)}</td></tr>
          {Object.entries(printingPayslip.deduction_breakdown?.statutory||{}).map(([key,value])=><tr key={key}><td>{key.toUpperCase()} — employee</td><td>{money(value.employee_amount)}</td></tr>)}
          {Object.entries(printingPayslip.deduction_breakdown?.statutory||{}).map(([key,value])=><tr key={key+"-employer"}><td>{key.toUpperCase()} — employer</td><td>{money(value.employer_amount)}</td></tr>)}
          <tr><th>Net pay</th><th>{money(printingPayslip.net_pay)}</th></tr>
        </tbody></table>
        {printingPayslip.deduction_breakdown?.manual_note&&<p><strong>Manual deduction reason:</strong> {printingPayslip.deduction_breakdown.manual_note}</p>}
        <footer><small>Generated from the approved Super Bajaar payroll record. This statement is not a bank payment confirmation.</small></footer>
      </article>}
    </div>}
    {busy&&<p role="status">Working…</p>}
  </section>;
}
