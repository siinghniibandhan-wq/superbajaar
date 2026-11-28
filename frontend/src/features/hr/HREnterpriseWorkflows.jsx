import { useCallback,useEffect,useMemo,useState } from "react";
import { apiRequest } from "../../services/api.js";

const domains=[
 {id:"recruitment",label:"Recruitment",types:[["job_opening","Job opening",[["department","Department"],["employment_type","Employment type"],["location","Location"],["headcount","Headcount","number"],["description","Job description","textarea"]]],["candidate","Candidate",[["first_name","First name"],["last_name","Last name"],["email","Email","email"],["phone","Phone"],["source","Source"],["resume_reference","Resume reference"]]],["application","Application",[["candidate_id","Candidate record ID","number"],["job_id","Job opening record ID","number"],["cover_note","Cover note","textarea"]]],["interview","Interview",[["application_id","Application record ID","number"],["scheduled_at","Scheduled date","date"],["interviewer_employee_id","Interviewer employee ID","number"],["interview_type","Interview type"]]],["offer","Offer",[["application_id","Application record ID","number"],["offered_salary","Offered salary","number"],["currency","Currency (e.g. INR)"],["expires_on","Offer expiry","date"]]]]},
 {id:"documents",label:"Employee documents",types:[["employee_document","Employee document",[["document_type","Document type","select"],["expiry_date","Expiry date (optional)","date"]]]]},
 {id:"performance",label:"Performance",types:[["review","Performance review",[["cycle","Review cycle"],["reviewer_employee_id","Reviewer employee ID","number"],["summary","Summary","textarea"],["rating","Rating","number"]]],["goal","Performance goal",[["description","Description","textarea"],["measure","Measurement"],["target","Target"],["due_date","Due date","date"]]],["review_cycle","Review cycle",[["period_start","Period start","date"],["period_end","Period end","date"]]],["feedback","Review feedback",[["review_id","Review record ID","number"],["feedback","Feedback","textarea"]]]]},
 {id:"learning",label:"Learning & development",types:[["course","Course",[["provider","Provider"],["course_type","Course type"],["description","Description","textarea"],["duration_hours","Duration (hours)","number"]]],["enrollment","Course enrollment",[["course_id","Course record ID","number"],["completion_due","Completion due","date"]]],["assessment","Course assessment",[["enrollment_id","Enrollment record ID","number"],["score","Score (0–100)","number"],["pass_score","Pass score (0–100)","number"]]],["certificate","Certificate",[["enrollment_id","Enrollment record ID","number"],["certificate_number","Certificate number"],["valid_until","Valid until","date"]]]]},
 {id:"assets",label:"Assets",types:[["asset","Asset register item",[["asset_type","Asset type"],["asset_tag","Asset tag"],["serial_number","Serial number"],["purchase_value","Purchase value","number"],["condition","Condition"]]],["asset_request","Asset request",[["asset_type","Requested asset type"],["purpose","Business need","textarea"],["needed_by","Needed by","date"]]],["allocation","Asset allocation",[["asset_id","Asset record ID","number"],["employee_id","Employee ID","number"],["condition_out","Condition at issue"]]],["maintenance","Maintenance record",[["asset_id","Asset record ID","number"],["maintenance_type","Maintenance type"],["reported_at","Reported date","date"],["description","Issue / work description","textarea"]]]]},
 {id:"travel",label:"Travel & claims",types:[["request","Travel request",[["destination","Destination"],["purpose","Purpose","textarea"],["start_date","Start date","date"],["end_date","End date","date"],["estimated_cost","Estimated cost","number"]]],["booking","Travel booking",[["travel_record_id","Travel request record ID","number"],["booking_reference","Booking reference"],["provider","Travel provider"],["booked_cost","Booked cost","number"]]],["advance","Travel advance",[["travel_record_id","Travel request record ID","number"],["requested_amount","Requested amount","number"]]],["claim","Travel claim",[["travel_record_id","Travel request record ID","number"],["actual_cost","Actual cost","number"],["receipt_reference","Receipt reference"]]]]},
 {id:"exit",label:"Resignation & exit",types:[["case","Exit case",[["reason","Reason","textarea"],["last_working_date","Last working date","date"],["notice_days","Notice days","number"],["handover_owner","Handover owner"]]],["clearance","Department clearance",[["exit_record_id","Exit case record ID","number"],["department","Department"],["owner_employee_id","Clearance owner employee ID","number"]]],["settlement","Full-and-final settlement",[["exit_record_id","Exit case record ID","number"],["gross_due","Gross due","number"],["deductions","Deductions","number"],["net_due","Net due","number"],["payable_on","Payable date","date"]]]]},
 {id:"analytics",label:"HR analytics",types:[["report","Saved report",[["report_type","Report type"],["filters","Filters (JSON)","textarea"],["description","Description","textarea"]]]]}
];
const transitions={
 recruitment:{draft:["open","archived"],open:["screening","archived"],screening:["shortlisted","rejected","withdrawn"],shortlisted:["interview","rejected","withdrawn"],interview:["offered","rejected","withdrawn"],offered:["rejected","withdrawn"]},
 documents:{pending:["uploaded","archived"],uploaded:["under_review","rejected"],under_review:["verified","rejected","expired"],verified:["expired","archived"],rejected:["uploaded","archived"],expired:["uploaded","archived"]},
 performance:{draft:["active","cancelled"],active:["self_review","cancelled"],self_review:["manager_review"],manager_review:["calibration","acknowledged"],calibration:["acknowledged"],acknowledged:["closed"]},
 learning:{planned:["enrolled","cancelled"],enrolled:["in_progress","cancelled"],in_progress:["completed","failed"],failed:["enrolled"]},
 assets:{available:["assigned","maintenance","written_off"],requested:["approved","rejected"],approved:["assigned","rejected"],assigned:["returned","maintenance","written_off"],maintenance:["assigned","written_off"],returned:["maintenance","written_off"]},
 travel:{draft:["submitted","cancelled"],submitted:["approved","rejected"],approved:["booked","cancelled"],booked:["in_progress","cancelled"],in_progress:["completed"],completed:["claimed"],claimed:["reimbursed"]},
 exit:{initiated:["notice_period","withdrawn"],notice_period:["handover","withdrawn"],handover:["clearance"],clearance:["settlement_review"],settlement_review:["completed"]},
 analytics:{saved:["scheduled","archived"],scheduled:["saved","archived"]}
};
const employeeTransitions={
 travel:{draft:["submitted","cancelled"]},
 performance:{active:["self_review"]},
 learning:{enrolled:["in_progress"],in_progress:["completed"]},
 exit:{initiated:["withdrawn"]}
};
const managerOnlyTypes={
 recruitment:["job_opening","candidate","application","interview","offer"],
 performance:["review_cycle","review"],
 learning:["course","assessment","certificate"],
 assets:["asset","allocation","maintenance"],
 travel:["booking","advance"],
 exit:["clearance","settlement"],
 analytics:["report"]
};
const blank={};

export default function HREnterpriseWorkflows({manager,employees=[],onEmployeeCreated}) {
 const [domain,setDomain]=useState("recruitment"),[items,setItems]=useState([]),[recordType,setRecordType]=useState("job_opening");
 const [title,setTitle]=useState(""),[employeeId,setEmployeeId]=useState(""),[fields,setFields]=useState(blank),[documentFile,setDocumentFile]=useState(null);
 const [busy,setBusy]=useState(false),[error,setError]=useState(""),[notice,setNotice]=useState("");
 const [analyticsMonth,setAnalyticsMonth]=useState(()=>{const d=new Date();return d.getFullYear()+"-"+String(d.getMonth()+1).padStart(2,"0");});
 const [analyticsData,setAnalyticsData]=useState(null),[analyticsError,setAnalyticsError]=useState(""),[analyticsLoading,setAnalyticsLoading]=useState(false);
 const [eventRecord,setEventRecord]=useState(null),[recordEvents,setRecordEvents]=useState([]),[eventsBusy,setEventsBusy]=useState(false);
 const [recordSearch,setRecordSearch]=useState(""),[statusFilter,setStatusFilter]=useState("");
 const [hireOffer,setHireOffer]=useState(null),[hireAccepted,setHireAccepted]=useState(false);
 const [hireForm,setHireForm]=useState({employee_code:"",first_name:"",last_name:"",email:"",phone:"",department_id:"",designation:"",employment_type:"full_time",status:"active",joining_date:new Date().toISOString().slice(0,10),reports_to_employee_id:"",basic_salary:"0",hra:"0",special_allowance:"0",other_allowance:"0",acceptance_reference:""});
 const current=domains.find(x=>x.id===domain);
 const availableTypes=current.types.filter(x=>manager||!managerOnlyTypes[domain]?.includes(x[0]));
 const type=availableTypes.find(x=>x[0]===recordType)||availableTypes[0]||current.types[0];
 const load=useCallback(async()=>{
   setBusy(true);setError("");
   try{const result=await apiRequest("/hr/enterprise/"+domain);setItems(result.items||[]);}
   catch(e){setError(e.message||"Unable to load HR records.");}
   finally{setBusy(false);}
 },[domain]);
 useEffect(()=>{const selected=domains.find(x=>x.id===domain);const first=selected.types.find(x=>manager||!managerOnlyTypes[domain]?.includes(x[0]));setRecordType(first?.[0]||selected.types[0][0]);setFields({});setTitle("");setDocumentFile(null);},[domain,manager]);
 useEffect(()=>{load();},[load]);
 useEffect(()=>{
   if(domain!=="analytics"||!manager)return;
   let active=true;setAnalyticsLoading(true);setAnalyticsError("");
   apiRequest("/hr/overview?month="+analyticsMonth)
     .then(result=>{if(active)setAnalyticsData(result);})
     .catch(e=>{if(active)setAnalyticsError(e.message||"Unable to load HR analytics.");})
     .finally(()=>{if(active)setAnalyticsLoading(false);});
   return()=>{active=false;};
 },[domain,manager,analyticsMonth]);
 const update=(key,value)=>setFields(old=>({...old,[key]:value}));
 async function create(e){
   e.preventDefault();setBusy(true);setError("");setNotice("");
   try{
     if(domain==="documents"){
       if(!documentFile)throw new Error("Choose a document file to upload.");
       if(manager&&!employeeId)throw new Error("Select the employee whose profile will own this document.");
       const form=new FormData();
       form.append("file",documentFile);
       form.append("document_type",fields.document_type||"identity");
       if(fields.expiry_date)form.append("expiry_date",fields.expiry_date);
       if(manager&&employeeId)form.append("employee_id",employeeId);
       await apiRequest("/hr/enterprise/documents/upload",{method:"POST",body:form});
       setDocumentFile(null);
       setNotice("Document uploaded to private storage.");
     }else{
       const payload={record_type:recordType,title:title.trim(),payload:fields};
       if(manager&&employeeId)payload.employee_id=Number(employeeId);
       await apiRequest("/hr/enterprise/"+domain,{method:"POST",body:JSON.stringify(payload)});
       setNotice("Record created.");
     }
     setTitle("");setFields({});await load();
   }catch(e){setError(e.message||"Unable to create HR record.");}
   finally{setBusy(false);}
 }
 async function transition(item,status){
   const note=window.prompt("Add a note for this workflow change (optional):")||null;
   setBusy(true);setError("");setNotice("");
   try{await apiRequest("/hr/enterprise/"+domain+"/"+item.id+"/transition",{method:"POST",body:JSON.stringify({status,note,expected_version:item.version})});setNotice("Workflow updated.");await load();}
   catch(e){setError(e.message||"Unable to update workflow.");}
   finally{setBusy(false);}
 }
 async function showEvents(item){
   setEventRecord(item);setEventsBusy(true);setRecordEvents([]);setError("");
   try{const result=await apiRequest("/hr/enterprise/"+domain+"/"+item.id+"/events");setRecordEvents(result.items||[]);}
   catch(e){setError(e.message||"Unable to load audit history.");}
   finally{setEventsBusy(false);}
 }
 function startHire(item){
   const application=items.find(x=>x.id===item.payload?.application_id&&x.payload?.record_type==="application");
   const candidate=items.find(x=>x.id===application?.payload?.candidate_id&&x.payload?.record_type==="candidate");
   const data=candidate?.payload||{};
   setHireOffer(item);setHireAccepted(false);
   setHireForm(old=>({...old,first_name:data.first_name||"",last_name:data.last_name||"",email:data.email||"",phone:data.phone||"",acceptance_reference:""}));
 }
 async function submitHire(e){
   e.preventDefault();if(!hireOffer)return;
   if(!hireAccepted){setError("Confirm that the candidate accepted this offer.");return;}
   setBusy(true);setError("");setNotice("");
   try{
     const employee={...hireForm,user_id:null,department_id:hireForm.department_id?Number(hireForm.department_id):null,
       reports_to_employee_id:hireForm.reports_to_employee_id?Number(hireForm.reports_to_employee_id):null};
     delete employee.acceptance_reference;
     const result=await apiRequest("/hr/enterprise/recruitment/"+hireOffer.id+"/hire",{method:"POST",body:JSON.stringify({
       application_id:Number(hireOffer.payload.application_id),candidate_accepted:true,
       acceptance_reference:hireForm.acceptance_reference||null,employee
     })});
     setNotice("Candidate hired as "+result.employee_code+". Onboarding tasks created: "+(result.onboarding_tasks_created||0)+".");
     setHireOffer(null);setHireAccepted(false);await load();await onEmployeeCreated?.();
   }catch(e){setError(e.message||"Unable to convert candidate into an employee.");}
   finally{setBusy(false);}
 }
 const employeeNames=useMemo(()=>Object.fromEntries(employees.map(x=>[x.id,x.employee_code+" — "+x.first_name+" "+(x.last_name||"")])),[employees]);
 return <section className="hr-enterprise">
  <div className="hr-panel">
   <div className="hr-directory-heading"><div><h2>Integrated HR operations</h2><p>Recruitment, employee records, performance, training, assets, travel, exits and workforce reporting.</p></div><span className="hr-directory-count">8 domains</span></div>
   <nav className="hr-advanced-nav" aria-label="HR enterprise domains">{domains.filter(x=>manager||!["recruitment","analytics"].includes(x.id)).map(x=><button type="button" key={x.id} className={domain===x.id?"active":""} aria-pressed={domain===x.id} onClick={()=>setDomain(x.id)}>{x.label}</button>)}</nav>
   {error&&<p className="sb-alert" role="alert">{error}</p>}{notice&&<p className="sb-success" role="status">{notice}</p>}
   <h3>{current.label}</h3>
   {domain==="analytics"&&manager&&<section className="hr-panel" aria-label="Computed workforce analytics">
    <div className="hr-directory-heading"><div><h3>Workforce analytics</h3><p>Live metrics from the existing HR, attendance, leave and approved payroll records.</p></div><label>Reporting month<input type="month" value={analyticsMonth} onChange={e=>setAnalyticsMonth(e.target.value)}/></label></div>
    {analyticsError&&<p role="alert" className="sb-alert">{analyticsError}</p>}
    {analyticsLoading&&<p role="status">Loading workforce metrics…</p>}
    {analyticsData&&<><div className="hr-overview">
     <article><span>Total workforce</span><strong>{analyticsData.workforce?.total??0}</strong><small>Active {analyticsData.workforce?.active??0} · Inactive {analyticsData.workforce?.inactive??0}</small></article>
     <article><span>Joiners</span><strong>{analyticsData.workforce?.joiners??0}</strong><small>During selected month</small></article>
     <article><span>Exits</span><strong>{analyticsData.workforce?.exits??0}</strong><small>During selected month</small></article>
     <article><span>Present employees</span><strong>{analyticsData.attendance?.present??"—"}</strong><small>Absent {analyticsData.attendance?.absent??"Not available"}</small></article>
     <article><span>Attendance rate</span><strong>{analyticsData.attendance?.rate==null?"—":analyticsData.attendance.rate+"%"}</strong><small>{analyticsData.attendance?.reason||"Based on published shifts"}</small></article>
     <article><span>Approved payroll gross</span><strong>{new Intl.NumberFormat("en-IN",{style:"currency",currency:"INR",maximumFractionDigits:0}).format(Number(analyticsData.payroll?.gross||0))}</strong><small>Net {new Intl.NumberFormat("en-IN",{style:"currency",currency:"INR",maximumFractionDigits:0}).format(Number(analyticsData.payroll?.net||0))}</small></article>
    </div>
    <div className="hr-table-wrap"><table><thead><tr><th>Department</th><th>Headcount</th></tr></thead><tbody>{(analyticsData.workforce?.departments||[]).map(d=><tr key={d.id}><td>{d.name}</td><td>{d.headcount}</td></tr>)}{!analyticsData.workforce?.departments?.length&&<tr><td colSpan="2">No active departments.</td></tr>}</tbody></table></div>
    <p className="hr-enterprise-note">Metrics are calculated from recorded data. Attendance absence and rate are unavailable when there is no published shift schedule; late-arrival and attendance trend metrics are not currently calculated.</p></>}
   </section>}
   <form className="hr-form hr-grid" onSubmit={create}>
    <label>Record type<select value={recordType} onChange={e=>{setRecordType(e.target.value);setFields({});}}>{availableTypes.map(x=><option key={x[0]} value={x[0]}>{x[1]}</option>)}</select></label>
    {domain!=="documents"&&<label>Title<input required maxLength="200" value={title} onChange={e=>setTitle(e.target.value)}/></label>}
    {manager&&<label>Employee (optional)<select value={employeeId} onChange={e=>setEmployeeId(e.target.value)}><option value="">Not employee-linked</option>{employees.map(x=><option key={x.id} value={x.id}>{employeeNames[x.id]}</option>)}</select></label>}
    {type[2].map(([key,label,inputType])=><label key={key}>{label}{inputType==="select"?<select required value={fields[key]||"identity"} onChange={e=>update(key,e.target.value)}><option value="identity">Identity</option><option value="address">Address</option><option value="qualification">Qualification</option><option value="employment">Employment</option><option value="contract">Contract</option><option value="policy_acknowledgement">Policy acknowledgement</option><option value="other">Other</option></select>:inputType==="textarea"?<textarea rows="2" value={fields[key]||""} onChange={e=>update(key,e.target.value)}/>:<input type={inputType||"text"} required value={fields[key]||""} onChange={e=>update(key,e.target.value)}/>}</label>)}\n    {domain==="documents"&&<label>Document file<input type="file" accept="application/pdf,image/jpeg,image/png" required onChange={e=>setDocumentFile(e.target.files?.[0]||null)}/><small>Private encrypted storage · PDF/JPEG/PNG · maximum 10 MB</small></label>}
    <button disabled={busy}>Create {type[1].toLowerCase()}</button>
   </form>
   {hireOffer&&manager&&<section className="hr-panel"><div className="hr-directory-heading"><div><h3>Convert accepted offer to employee</h3><p>This creates the employee identity, opening salary profile and any configured onboarding checklist tasks.</p></div><button type="button" className="hr-secondary" onClick={()=>setHireOffer(null)}>Cancel</button></div>
    <form className="hr-form hr-grid" onSubmit={submitHire}>
     <label>Employee code<input required value={hireForm.employee_code} onChange={e=>setHireForm({...hireForm,employee_code:e.target.value})}/></label>
     <label>First name<input required value={hireForm.first_name} onChange={e=>setHireForm({...hireForm,first_name:e.target.value})}/></label>
     <label>Last name<input value={hireForm.last_name} onChange={e=>setHireForm({...hireForm,last_name:e.target.value})}/></label>
     <label>Email<input required type="email" value={hireForm.email} onChange={e=>setHireForm({...hireForm,email:e.target.value})}/></label>
     <label>Phone<input value={hireForm.phone} onChange={e=>setHireForm({...hireForm,phone:e.target.value})}/></label>
     <label>Department ID<input type="number" min="1" value={hireForm.department_id} onChange={e=>setHireForm({...hireForm,department_id:e.target.value})}/></label>
     <label>Designation<input required value={hireForm.designation} onChange={e=>setHireForm({...hireForm,designation:e.target.value})}/></label>
     <label>Employment type<select value={hireForm.employment_type} onChange={e=>setHireForm({...hireForm,employment_type:e.target.value})}><option value="full_time">Full time</option><option value="part_time">Part time</option><option value="contract">Contract</option><option value="intern">Intern</option><option value="shift_worker">Shift worker</option></select></label>
     <label>Employment status<select value={hireForm.status} onChange={e=>setHireForm({...hireForm,status:e.target.value})}><option value="active">Active</option><option value="probation">Probation</option></select></label>
     <label>Joining date<input required type="date" value={hireForm.joining_date} onChange={e=>setHireForm({...hireForm,joining_date:e.target.value})}/></label>
     <label>Reporting manager employee ID<input type="number" min="1" value={hireForm.reports_to_employee_id} onChange={e=>setHireForm({...hireForm,reports_to_employee_id:e.target.value})}/></label>
     <label>Basic salary (monthly)<input required type="number" min="0" step="0.01" value={hireForm.basic_salary} onChange={e=>setHireForm({...hireForm,basic_salary:e.target.value})}/></label>
     <label>HRA<input required type="number" min="0" step="0.01" value={hireForm.hra} onChange={e=>setHireForm({...hireForm,hra:e.target.value})}/></label>
     <label>Special allowance<input required type="number" min="0" step="0.01" value={hireForm.special_allowance} onChange={e=>setHireForm({...hireForm,special_allowance:e.target.value})}/></label>
     <label>Other allowance<input required type="number" min="0" step="0.01" value={hireForm.other_allowance} onChange={e=>setHireForm({...hireForm,other_allowance:e.target.value})}/></label>
     <label>Offer acceptance reference<input value={hireForm.acceptance_reference} onChange={e=>setHireForm({...hireForm,acceptance_reference:e.target.value})} placeholder="Signed offer / email reference"/></label>
     <label className="hr-check"><input type="checkbox" checked={hireAccepted} onChange={e=>setHireAccepted(e.target.checked)}/> Candidate acceptance has been confirmed</label>
     <button disabled={busy||!hireAccepted}>Create employee and start onboarding</button>
    </form>
   </section>}
   <div className="hr-directory-heading"><h3>Records</h3><span className="hr-directory-count">{items.length} shown</span></div>
   <div className="hr-toolbar"><label>Search records<input value={recordSearch} onChange={e=>setRecordSearch(e.target.value)} placeholder="Search title or employee"/></label><label>Status<select value={statusFilter} onChange={e=>setStatusFilter(e.target.value)}><option value="">All statuses</option>{[...new Set(items.map(x=>x.status))].sort().map(s=><option key={s} value={s}>{s.replaceAll("_"," ")}</option>)}</select></label><button type="button" className="hr-secondary" onClick={()=>{setRecordSearch("");setStatusFilter("");}}>Reset filters</button></div>
   <div className="hr-table-wrap"><table><thead><tr><th>Record</th><th>Employee</th><th>Status</th><th>Updated</th><th>Workflow actions</th></tr></thead><tbody>
    {items.filter(item=>(!statusFilter||item.status===statusFilter)&&(!recordSearch||[item.title,employeeNames[item.employee_id]||""].join(" ").toLowerCase().includes(recordSearch.toLowerCase()))).map(item=><tr key={item.id}><td><strong>{item.title}</strong><small>#{item.id} · {item.payload?.record_type||"Record"}</small></td><td>{employeeNames[item.employee_id]||"—"}</td><td>{item.status}</td><td>{item.updated_at?new Date(item.updated_at).toLocaleString():"—"}</td><td>{domain==="documents"&&["uploaded","under_review","verified"].includes(item.status)&&<button type="button" disabled={busy} onClick={async()=>{try{const result=await apiRequest("/hr/enterprise/documents/"+item.id+"/download",{method:"POST",body:"{}"});window.open(result.url,"_blank","noopener,noreferrer");}catch(e){setError(e.message||"Unable to download document.");}}}>Secure download</button>}{manager&&domain==="recruitment"&&item.payload?.record_type==="offer"&&item.status==="offered"&&<button type="button" disabled={busy} onClick={()=>startHire(item)}>Convert to employee</button>}{(manager?(transitions[domain]?.[item.status]||[]):(employeeTransitions[domain]?.[item.status]||[])).map(next=><button type="button" key={next} disabled={busy} onClick={()=>transition(item,next)}>{next.replaceAll("_"," ")}</button>)}{manager&&<button type="button" className="hr-secondary" disabled={busy} onClick={()=>showEvents(item)}>Audit trail</button>}</td></tr>)}
    {!items.filter(item=>(!statusFilter||item.status===statusFilter)&&(!recordSearch||[item.title,employeeNames[item.employee_id]||""].join(" ").toLowerCase().includes(recordSearch.toLowerCase()))).length&&<tr><td colSpan="5">{busy?"Loading…":"No records match these filters."}</td></tr>}
   </tbody></table></div>
   {eventRecord&&manager&&<section className="hr-panel"><div className="hr-directory-heading"><h3>Audit trail · {eventRecord.title}</h3><button type="button" className="hr-secondary" onClick={()=>{setEventRecord(null);setRecordEvents([]);}}>Close</button></div>{eventsBusy?<p role="status">Loading audit events…</p>:<ol>{recordEvents.map(ev=><li key={ev.id}><strong>{ev.event_type}</strong> · {ev.from_status||"—"} → {ev.to_status||"—"} · {ev.created_at?new Date(ev.created_at).toLocaleString():""}{ev.note&&<p>{ev.note}</p>}</li>)}{!recordEvents.length&&<li>No audit events found.</li>}</ol>}</section>}
   {domain==="documents"&&<p className="hr-enterprise-note">Files are stored in the configured private S3 bucket with server-side encryption and short-lived, access-checked download links. Configure bucket access and retention policy before production use.</p>}
  </div>
 </section>;
}
