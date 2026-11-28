import { useCallback,useEffect,useMemo,useState } from "react";
import { apiRequest } from "../../services/api.js";

const domains=[
 {id:"recruitment",label:"Recruitment",types:[["job_opening","Job opening",[["department","Department"],["employment_type","Employment type"],["location","Location"],["headcount","Headcount","number"],["description","Job description","textarea"]]],["candidate","Candidate",[["email","Email","email"],["phone","Phone"],["source","Source"],["resume_reference","Resume reference"]]],["application","Application",[["candidate_id","Candidate record ID","number"],["job_id","Job opening record ID","number"],["cover_note","Cover note","textarea"]]],["interview","Interview",[["application_id","Application record ID","number"],["scheduled_at","Scheduled date","date"],["interviewer_employee_id","Interviewer employee ID","number"],["interview_type","Interview type"]]],["offer","Offer",[["application_id","Application record ID","number"],["offered_salary","Offered salary","number"],["currency","Currency (e.g. INR)"],["expires_on","Offer expiry","date"]]]]},
 {id:"documents",label:"Employee documents",types:[["employee_document","Employee document",[["document_type","Document type","select"]]]]},
 {id:"performance",label:"Performance",types:[["review","Performance review",[["cycle","Review cycle"],["reviewer_employee_id","Reviewer employee ID","number"],["summary","Summary","textarea"],["rating","Rating","number"]]],["goal","Performance goal",[["description","Description","textarea"],["measure","Measurement"],["target","Target"],["due_date","Due date","date"]]],["review_cycle","Review cycle",[["period_start","Period start","date"],["period_end","Period end","date"]]],["feedback","Review feedback",[["review_id","Review record ID","number"],["feedback","Feedback","textarea"]]]]},
 {id:"learning",label:"Learning & development",types:[["course","Course",[["provider","Provider"],["course_type","Course type"],["description","Description","textarea"],["duration_hours","Duration (hours)","number"]]],["enrollment","Course enrollment",[["course_id","Course record ID","number"],["completion_due","Completion due","date"]]],["assessment","Course assessment",[["enrollment_id","Enrollment record ID","number"],["score","Score (0–100)","number"],["pass_score","Pass score (0–100)","number"]]],["certificate","Certificate",[["enrollment_id","Enrollment record ID","number"],["certificate_number","Certificate number"],["valid_until","Valid until","date"]]]]},
 {id:"assets",label:"Assets",types:[["asset","Asset register item",[["asset_type","Asset type"],["asset_tag","Asset tag"],["serial_number","Serial number"],["purchase_value","Purchase value","number"],["condition","Condition"]]],["allocation","Asset allocation",[["asset_id","Asset record ID","number"],["employee_id","Employee ID","number"],["condition_out","Condition at issue"]]],["maintenance","Maintenance record",[["asset_id","Asset record ID","number"],["maintenance_type","Maintenance type"],["reported_at","Reported date","date"],["description","Issue / work description","textarea"]]]]},
 {id:"travel",label:"Travel & claims",types:[["request","Travel request",[["destination","Destination"],["purpose","Purpose","textarea"],["start_date","Start date","date"],["end_date","End date","date"],["estimated_cost","Estimated cost","number"]]],["booking","Travel booking",[["travel_record_id","Travel request record ID","number"],["booking_reference","Booking reference"],["provider","Travel provider"],["booked_cost","Booked cost","number"]]],["advance","Travel advance",[["travel_record_id","Travel request record ID","number"],["requested_amount","Requested amount","number"]]],["claim","Travel claim",[["travel_record_id","Travel request record ID","number"],["actual_cost","Actual cost","number"],["receipt_reference","Receipt reference"]]]]},
 {id:"exit",label:"Resignation & exit",types:[["case","Exit case",[["reason","Reason","textarea"],["last_working_date","Last working date","date"],["notice_days","Notice days","number"],["handover_owner","Handover owner"]]],["clearance","Department clearance",[["exit_record_id","Exit case record ID","number"],["department","Department"],["owner_employee_id","Clearance owner employee ID","number"]]],["settlement","Full-and-final settlement",[["exit_record_id","Exit case record ID","number"],["gross_due","Gross due","number"],["deductions","Deductions","number"],["net_due","Net due","number"],["payable_on","Payable date","date"]]]]},
 {id:"analytics",label:"HR analytics",types:[["report","Saved report",[["report_type","Report type"],["filters","Filters (JSON)","textarea"],["description","Description","textarea"]]]]}
];
const transitions={
 recruitment:{draft:["open","archived"],open:["screening","archived"],screening:["shortlisted","rejected","withdrawn"],shortlisted:["interview","rejected","withdrawn"],interview:["offered","rejected","withdrawn"],offered:["hired","rejected","withdrawn"]},
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
const blank={};

export default function HREnterpriseWorkflows({manager,employees=[]}) {
 const [domain,setDomain]=useState("recruitment"),[items,setItems]=useState([]),[recordType,setRecordType]=useState("job_opening");
 const [title,setTitle]=useState(""),[employeeId,setEmployeeId]=useState(""),[fields,setFields]=useState(blank),[documentFile,setDocumentFile]=useState(null);
 const [busy,setBusy]=useState(false),[error,setError]=useState(""),[notice,setNotice]=useState("");
 const current=domains.find(x=>x.id===domain);
 const type=current.types.find(x=>x[0]===recordType)||current.types[0];
 const load=useCallback(async()=>{
   setBusy(true);setError("");
   try{const result=await apiRequest("/hr/enterprise/"+domain);setItems(result.items||[]);}
   catch(e){setError(e.message||"Unable to load HR records.");}
   finally{setBusy(false);}
 },[domain]);
 useEffect(()=>{setRecordType(domains.find(x=>x.id===domain).types[0][0]);setFields({});setTitle("");setDocumentFile(null);},[domain]);
 useEffect(()=>{load();},[load]);
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
   try{await apiRequest("/hr/enterprise/"+domain+"/"+item.id+"/transition",{method:"POST",body:JSON.stringify({status,note})});setNotice("Workflow updated.");await load();}
   catch(e){setError(e.message||"Unable to update workflow.");}
   finally{setBusy(false);}
 }
 const employeeNames=useMemo(()=>Object.fromEntries(employees.map(x=>[x.id,x.employee_code+" — "+x.first_name+" "+(x.last_name||"")])),[employees]);
 return <section className="hr-enterprise">
  <div className="hr-panel">
   <div className="hr-directory-heading"><div><h2>Integrated HR operations</h2><p>Recruitment, employee records, performance, training, assets, travel, exits and workforce reporting.</p></div><span className="hr-directory-count">8 domains</span></div>
   <nav className="hr-advanced-nav" aria-label="HR enterprise domains">{domains.map(x=><button type="button" key={x.id} className={domain===x.id?"active":""} aria-pressed={domain===x.id} onClick={()=>setDomain(x.id)}>{x.label}</button>)}</nav>
   {error&&<p className="sb-alert" role="alert">{error}</p>}{notice&&<p className="sb-success" role="status">{notice}</p>}
   <h3>{current.label}</h3>
   <form className="hr-form hr-grid" onSubmit={create}>
    <label>Record type<select value={recordType} onChange={e=>{setRecordType(e.target.value);setFields({});}}>{current.types.map(x=><option key={x[0]} value={x[0]}>{x[1]}</option>)}</select></label>
    {domain!=="documents"&&<label>Title<input required maxLength="200" value={title} onChange={e=>setTitle(e.target.value)}/></label>}
    {manager&&<label>Employee (optional)<select value={employeeId} onChange={e=>setEmployeeId(e.target.value)}><option value="">Not employee-linked</option>{employees.map(x=><option key={x.id} value={x.id}>{employeeNames[x.id]}</option>)}</select></label>}
    {type[2].map(([key,label,inputType])=><label key={key}>{label}{inputType==="select"?<select required value={fields[key]||"identity"} onChange={e=>update(key,e.target.value)}><option value="identity">Identity</option><option value="address">Address</option><option value="qualification">Qualification</option><option value="employment">Employment</option><option value="contract">Contract</option><option value="policy_acknowledgement">Policy acknowledgement</option><option value="other">Other</option></select>:inputType==="textarea"?<textarea rows="2" value={fields[key]||""} onChange={e=>update(key,e.target.value)}/>:<input type={inputType||"text"} required value={fields[key]||""} onChange={e=>update(key,e.target.value)}/>}</label>)}\n    {domain==="documents"&&<label>Document file<input type="file" accept="application/pdf,image/jpeg,image/png" required onChange={e=>setDocumentFile(e.target.files?.[0]||null)}/><small>Private encrypted storage · PDF/JPEG/PNG · maximum 10 MB</small></label>}
    <button disabled={busy}>Create {type[1].toLowerCase()}</button>
   </form>
   <div className="hr-directory-heading"><h3>Records</h3><span className="hr-directory-count">{items.length} shown</span></div>
   <div className="hr-table-wrap"><table><thead><tr><th>Record</th><th>Employee</th><th>Status</th><th>Updated</th><th>Workflow actions</th></tr></thead><tbody>
    {items.map(item=><tr key={item.id}><td><strong>{item.title}</strong><small>#{item.id} · {item.payload?.record_type||"Record"}</small></td><td>{employeeNames[item.employee_id]||"—"}</td><td>{item.status}</td><td>{item.updated_at?new Date(item.updated_at).toLocaleString():"—"}</td><td>{domain==="documents"&&["uploaded","under_review","verified"].includes(item.status)&&<button type="button" disabled={busy} onClick={async()=>{try{const result=await apiRequest("/hr/enterprise/documents/"+item.id+"/download",{method:"POST",body:"{}"});window.open(result.url,"_blank","noopener,noreferrer");}catch(e){setError(e.message||"Unable to download document.");}}}>Secure download</button>}{(manager?(transitions[domain]?.[item.status]||[]):(employeeTransitions[domain]?.[item.status]||[])).map(next=><button type="button" key={next} disabled={busy} onClick={()=>transition(item,next)}>{next.replaceAll("_"," ")}</button>)}</td></tr>)}
    {!items.length&&<tr><td colSpan="5">{busy?"Loading…":"No records in this domain yet."}</td></tr>}
   </tbody></table></div>
   {domain==="documents"&&<p className="hr-enterprise-note">Files are stored in the configured private S3 bucket with server-side encryption and short-lived, access-checked download links. Configure bucket access and retention policy before production use.</p>}
  </div>
 </section>;
}
