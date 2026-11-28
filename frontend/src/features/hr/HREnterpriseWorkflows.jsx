import { useCallback,useEffect,useMemo,useState } from "react";
import { apiRequest, apiDownload } from "../../services/api.js";

const domains=[
 {id:"recruitment",label:"Recruitment",types:[["job_opening","Job opening",[["department","Department"],["employment_type","Employment type"],["location","Location"],["headcount","Headcount","number"],["description","Job description","textarea"]]],["candidate","Candidate",[["first_name","First name"],["last_name","Last name"],["email","Email","email"],["phone","Phone"],["source","Source"],["resume_reference","Resume reference"]]],["application","Application",[["candidate_id","Candidate record ID","record_select"],["job_id","Job opening record ID","record_select"],["cover_note","Cover note","textarea"]]],["interview","Interview",[["application_id","Application record ID","record_select"],["scheduled_at","Scheduled date","datetime-local"],["interviewer_employee_id","Interviewer employee ID","number"],["interview_type","Interview type"]]],["interview_feedback","Interview evaluation",[["interview_id","Interview record ID","record_select"],["interviewer_employee_id","Interviewer employee ID","number"],["rating","Rating (1–5)","number"],["decision","Decision (pass/hold/reject)"],["feedback","Feedback","textarea"]]],["offer","Offer",[["application_id","Application record ID","record_select"],["offered_salary","Offered salary","number"],["currency","Currency (e.g. INR)"],["expires_on","Offer expiry","date"]]],["communication","Candidate communication log",[["candidate_id","Candidate record ID","record_select"],["channel","Channel (email/phone/sms/in_person/other)"],["direction","Direction (inbound/outbound)"],["subject","Subject"],["message","Message","textarea"],["occurred_at","Date and time","datetime-local"]]]]},
 {id:"documents",label:"Employee documents",types:[["employee_document","Employee document",[["document_type","Document type","select"],["expiry_date","Expiry date (optional)","date"],["retention_until","Retention deletion date (optional)","date"]]]]},
 {id:"performance",label:"Performance",types:[["review_template","Review template",[["name","Template name"],["sections","Sections (JSON)","textarea"],["rating_scale","Rating scale (2–10)","number"]]],["review","Performance review",[["cycle_id","Review cycle record ID","record_select"],["reviewer_employee_id","Reviewer employee ID","number"],["template_id","Review template record ID","record_select"],["summary","Summary","textarea"],["rating","Rating","number"]]],["self_review","Employee self-review",[["cycle_id","Review cycle record ID","record_select"],["summary","Summary","textarea"],["rating","Self rating (1–5)","number"],["achievements","Key achievements","textarea"],["development_areas","Development areas","textarea"]]],["goal","Performance goal",[["cycle_id","Performance cycle record ID","record_select"],["description","Description","textarea"],["measure","Measurement"],["target","Target"],["weight","Weight (%)","number"],["due_date","Due date","date"]]],["review_cycle","Review cycle",[["period_start","Period start","date"],["period_end","Period end","date"]]],["feedback","Review feedback",[["review_id","Review record ID","record_select"],["feedback","Feedback","textarea"]]],["calibration","Review calibration",[["review_id","Review record ID","record_select"],["calibrated_rating","Calibrated rating (1–5)","number"],["rationale","Calibration rationale","textarea"]]],["acknowledgement","Employee review acknowledgement",[["review_id","Review record ID","record_select"],["acknowledgement","Acknowledgement (true/false)"],["comment","Employee comment","textarea"]]]]},
 {id:"learning",label:"Learning & development",types:[["course","Course",[["provider","Provider"],["course_type","Course type"],["description","Description","textarea"],["duration_hours","Duration (hours)","number"],["max_attempts","Maximum assessment attempts (default 3)","number"]]],["enrollment","Course enrollment",[["course_id","Course record ID","record_select"],["completion_due","Completion due","date"]]],["progress","Learning progress evidence",[["enrollment_id","Enrollment record ID","record_select"],["progress_percent","Progress (%)","number"],["evidence_reference","Evidence / completion reference"]]],["assessment","Course assessment",[["enrollment_id","Enrollment record ID","record_select"],["score","Score (0–100)","number"],["pass_score","Pass score (0–100)","number"]]],["certificate","Certificate",[["enrollment_id","Enrollment record ID","record_select"],["certificate_number","Certificate number"],["valid_until","Valid until","date"]]]]},
 {id:"assets",label:"Assets",types:[["asset","Asset register item",[["asset_type","Asset type"],["asset_tag","Asset tag"],["serial_number","Serial number"],["purchase_value","Purchase value","number"],["condition","Condition"],["vendor","Vendor"],["purchase_date","Purchase date","date"],["warranty_expiry","Warranty expiry","date"],["purchase_order_reference","Purchase order reference"],["location","Asset location"],["depreciation_method","Depreciation method (straight_line/reducing_balance)"],["useful_life_months","Useful life (months)","number"],["salvage_value","Salvage value","number"],["depreciation_as_of","Depreciation as of","date"],["annual_depreciation_rate","Annual reducing-balance rate (%)","number"]]],["asset_request","Asset request",[["asset_type","Requested asset type"],["purpose","Business need","textarea"],["needed_by","Needed by","date"]]],["allocation","Asset allocation",[["asset_id","Asset record ID","record_select"],["employee_id","Employee ID","number"],["condition_out","Condition at issue"]]],["maintenance","Maintenance record",[["asset_id","Asset record ID","record_select"],["maintenance_type","Maintenance type"],["reported_at","Reported date","date"],["description","Issue / work description","textarea"]]],["procurement","Asset procurement",[["vendor","Vendor"],["requested_by","Requested by"],["items","Items JSON (description, quantity, unit_cost)","textarea"],["estimated_total","Estimated total","number"]]],["stock_receipt","Stock receipt",[["procurement_id","Approved procurement","record_select"],["received_at","Received date","date"],["items","Received items JSON (description, quantity)","textarea"],["received_by","Received by"]]],["stock_reconciliation","Physical stock reconciliation",[["location","Location"],["counted_at","Counted date","date"],["expected_count","Expected count","number"],["physical_count","Physical count","number"],["variance_reason","Variance explanation","textarea"]]],["asset_loss","Asset loss investigation",[["asset_id","Asset record ID","record_select"],["reported_at","Reported date","date"],["description","Investigation details","textarea"],["investigation_reference","Investigation reference"]]]]},
 {id:"travel",label:"Travel & claims",types:[["travel_policy","Travel policy",[["name","Policy name"],["employment_type","Applicable employment type (or all)"],["job_grade","Applicable job grade (or all)"],["max_trip_cost","Maximum trip cost","number"],["per_diem_limit","Per-day allowance limit","number"],["currency","Currency (e.g. INR)"]]],["request","Travel request",[["destination","Destination"],["purpose","Purpose","textarea"],["start_date","Start date","date"],["end_date","End date","date"],["estimated_cost","Estimated cost","number"],["estimated_per_diem","Estimated per diem total","number"],["policy_id","Travel policy","record_select"]]],["booking","Travel booking",[["travel_record_id","Travel request record ID","record_select"],["booking_reference","Booking reference"],["provider","Travel provider"],["booked_cost","Booked cost","number"]]],["advance","Travel advance",[["travel_record_id","Travel request record ID","record_select"],["requested_amount","Requested amount","number"]]],["claim","Travel claim",[["travel_record_id","Travel request record ID","record_select"],["actual_cost","Actual cost","number"],["receipt_reference","Receipt reference"]]]]},
 {id:"exit",label:"Resignation & exit",types:[["case","Exit case",[["reason","Reason","textarea"],["last_working_date","Last working date","date"],["notice_days","Notice days","number"],["handover_owner","Handover owner"]]],["clearance","Department clearance",[["exit_record_id","Exit case record ID","record_select"],["department","Department"],["owner_employee_id","Clearance owner employee ID","number"]]],["settlement","Full-and-final settlement",[["exit_record_id","Exit case record ID","record_select"],["gross_due","Gross due","number"],["deductions","Deductions","number"],["net_due","Net due","number"],["payable_on","Payable date","date"]]]]},
 {id:"analytics",label:"HR analytics",types:[["report","Saved report",[["report_type","Report type (enterprise/workforce)"],["frequency","Frequency (weekly/monthly)"],["filters","Filters (JSON)","textarea"],["description","Description","textarea"]]]]}
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
const recruitmentRecordTransitions={
 job_opening:{draft:["open","archived"],open:["closed","archived"],closed:["archived"]},
 candidate:{draft:["withdrawn","archived"],withdrawn:["archived"]},
 application:{screening:["shortlisted","rejected","withdrawn"],shortlisted:["interview","rejected","withdrawn"],interview:["offered","rejected","withdrawn"],offered:["rejected","withdrawn"]},
 interview:{interview:["completed"]},
 offer:{offered:["rejected","withdrawn"]},
 interview_feedback:{},communication:{}
};
const domainRecordTransitions={
 documents:{employee_document:{pending:["under_review","archived"],under_review:["verified","rejected","expired"],verified:["expired","archived"],rejected:["archived"],expired:["archived"]}},
 performance:{
  review_template:{draft:["active","cancelled"],active:["cancelled"]},
  review_cycle:{draft:["active","cancelled"],active:["self_review","cancelled"],self_review:["manager_review"],manager_review:["calibration","closed"],calibration:["closed"]},
  review:{manager_review:["calibration","acknowledged"],calibration:["acknowledged"],acknowledged:["closed"]},
  self_review:{self_review:["manager_review"]},goal:{draft:["active","cancelled"],active:["cancelled"]},
  feedback:{},calibration:{calibration:["acknowledged"]},acknowledgement:{acknowledged:["closed"]}
 },
 learning:{
  course:{planned:["enrolled","cancelled"],enrolled:["cancelled"]},
  enrollment:{planned:["enrolled","cancelled"],enrolled:["in_progress","cancelled"],in_progress:["completed","failed"],failed:["enrolled"]},
  progress:{},assessment:{},certificate:{completed:["expired","archived"],expired:["archived"]}
 },
 assets:{
  asset:{available:["assigned","maintenance","written_off"],assigned:["acknowledged","returned","maintenance","written_off"],acknowledged:["returned","maintenance","written_off"],maintenance:["assigned","written_off"],returned:["available","maintenance","written_off"]},
  asset_request:{requested:["approved","rejected"],approved:["assigned","rejected"]},
  allocation:{requested:["approved","rejected"],approved:["assigned","rejected"],assigned:["acknowledged","returned","maintenance","written_off"],acknowledged:["returned","maintenance","written_off"]},
  maintenance:{},
  procurement:{requested:["approved","rejected","archived"],approved:["received","partially_received","archived"],partially_received:["received","archived"],received:["archived"]},
  stock_receipt:{received:["archived"]},
  stock_reconciliation:{requested:["reconciled","investigating"],investigating:["reconciled","closed"],reconciled:["closed"]},
  asset_loss:{investigating:["closed","written_off"]}
 },
 travel:{
  travel_policy:{},request:{draft:["submitted","cancelled"],submitted:["approved","rejected"],approved:["booked","cancelled"],booked:["in_progress","cancelled"],in_progress:["completed"],completed:["claimed"]},
  booking:{},advance:{},claim:{claimed:["reimbursed"]}
 },
 exit:{
  case:{initiated:["notice_period","withdrawn"],notice_period:["handover","withdrawn"],handover:["clearance"],clearance:["settlement_review"],settlement_review:["completed"]},
  clearance:{clearance:["completed","rejected"]},settlement:{settlement_review:["completed"]}
 }
};
const employeeTransitions={
 travel:{draft:["submitted","cancelled"]},
 performance:{active:["self_review"]},
 learning:{enrolled:["in_progress"],in_progress:["completed"]},
 exit:{initiated:["withdrawn"]},
 assets:{assigned:["acknowledged"]}
};
const managerOnlyTypes={
 recruitment:["job_opening","candidate","application","interview","interview_feedback","offer","communication"],
 performance:["review_template","review_cycle","review","calibration"],
 learning:["course","assessment","certificate"],
 assets:["asset","allocation","maintenance","procurement","stock_receipt","stock_reconciliation","asset_loss"],
 travel:["travel_policy","booking","advance"],
 exit:["clearance","settlement"],
 analytics:["report"]
};
const optionalFields=new Set(["last_name","phone","source","resume_reference","description","serial_number","purchase_value","condition","completion_due","due_date","expiry_date","handover_owner","weight","department_id","reports_to_employee_id","acceptance_reference","evidence_reference","vendor","purchase_date","warranty_expiry","purchase_order_reference","location","max_attempts"]);
const referenceTypeByField={policy_id:"travel_policy",candidate_id:"candidate",job_id:"job_opening",application_id:"application",interview_id:"interview",cycle_id:"review_cycle",template_id:"review_template",review_id:"review",course_id:"course",enrollment_id:"enrollment",asset_id:"asset",travel_record_id:"request",exit_record_id:"case"};
const blank={};

export default function HREnterpriseWorkflows({manager,employees=[],onEmployeeCreated}) {
 const [domain,setDomain]=useState("recruitment"),[items,setItems]=useState([]),[recordType,setRecordType]=useState("job_opening");
 const [title,setTitle]=useState(""),[employeeId,setEmployeeId]=useState(""),[fields,setFields]=useState(blank),[documentFile,setDocumentFile]=useState(null);
 const [busy,setBusy]=useState(false),[error,setError]=useState(""),[notice,setNotice]=useState("");
 const [analyticsMonth,setAnalyticsMonth]=useState(()=>{const d=new Date();return d.getFullYear()+"-"+String(d.getMonth()+1).padStart(2,"0");});
 const [analyticsDomainFilter,setAnalyticsDomainFilter]=useState("");
 const [analyticsDepartmentFilter,setAnalyticsDepartmentFilter]=useState("");
 const [analyticsData,setAnalyticsData]=useState(null),[analyticsError,setAnalyticsError]=useState(""),[analyticsLoading,setAnalyticsLoading]=useState(false);
 const [enterpriseAnalytics,setEnterpriseAnalytics]=useState(null),[enterpriseAnalyticsError,setEnterpriseAnalyticsError]=useState("");
 const [eventRecord,setEventRecord]=useState(null),[recordEvents,setRecordEvents]=useState([]),[eventsBusy,setEventsBusy]=useState(false);
 const [recordSearch,setRecordSearch]=useState(""),[statusFilter,setStatusFilter]=useState("");
 const [hireOffer,setHireOffer]=useState(null),[hireAccepted,setHireAccepted]=useState(false);
 const [emailCandidate,setEmailCandidate]=useState(null),[emailForm,setEmailForm]=useState({subject:"",message:""});
 const [expiringItems,setExpiringItems]=useState([]),[expiringLoading,setExpiringLoading]=useState(false),[expiringError,setExpiringError]=useState("");
 const [hireForm,setHireForm]=useState({employee_code:"",first_name:"",last_name:"",email:"",phone:"",department_id:"",designation:"",job_grade:"ungraded",employment_type:"full_time",status:"active",joining_date:new Date().toISOString().slice(0,10),reports_to_employee_id:"",basic_salary:"0",hra:"0",special_allowance:"0",other_allowance:"0",acceptance_reference:""});
 const current=domains.find(x=>x.id===domain);
 const availableTypes=current.types.filter(x=>manager||!managerOnlyTypes[domain]?.includes(x[0]));
 const type=availableTypes.find(x=>x[0]===recordType)||availableTypes[0]||current.types[0];
 const load=useCallback(async()=>{
   setBusy(true);setError("");
   try{const result=await apiRequest("/hr/enterprise/"+domain+"?limit=500");setItems(result.items||[]);}
   catch(e){setError(e.message||"Unable to load HR records.");}
   finally{setBusy(false);}
 },[domain]);
 useEffect(()=>{const selected=domains.find(x=>x.id===domain);const first=selected.types.find(x=>manager||!managerOnlyTypes[domain]?.includes(x[0]));setRecordType(first?.[0]||selected.types[0][0]);setFields({});setTitle("");setDocumentFile(null);},[domain,manager]);
 useEffect(()=>{load();},[load]);
 useEffect(()=>{
   if(domain!=="documents"||!manager)return;
   let active=true;setExpiringLoading(true);setExpiringError("");
   apiRequest("/hr/enterprise/expiring?within_days=30")
     .then(result=>{if(active)setExpiringItems(result.items||[]);})
     .catch(e=>{if(active)setExpiringError(e.message||"Unable to load expiry queue.");})
     .finally(()=>{if(active)setExpiringLoading(false);});
   return()=>{active=false;};
 },[domain,manager]);
 useEffect(()=>{
   if(domain!=="analytics"||!manager)return;
   let active=true;setAnalyticsLoading(true);setAnalyticsError("");
   apiRequest("/hr/overview?month="+analyticsMonth)
     .then(result=>{if(active)setAnalyticsData(result);})
     .catch(e=>{if(active)setAnalyticsError(e.message||"Unable to load HR analytics.");})
     .finally(()=>{if(active)setAnalyticsLoading(false);});
   return()=>{active=false;};
 },[domain,manager,analyticsMonth]);
 useEffect(()=>{
   if(domain!=="analytics"||!manager)return;
   let active=true;
   const [year,month]=analyticsMonth.split("-").map(Number);
   const fromDate=analyticsMonth+"-01";
   const toDate=analyticsMonth+"-"+String(new Date(year,month,0).getDate()).padStart(2,"0");
   setEnterpriseAnalyticsError("");
   apiRequest("/hr/enterprise/analytics/enterprise?from_date="+fromDate+"&to_date="+toDate
     +(analyticsDomainFilter?"&domain="+encodeURIComponent(analyticsDomainFilter):"")
     +(analyticsDepartmentFilter?"&department_id="+encodeURIComponent(analyticsDepartmentFilter):""))
     .then(result=>{if(active)setEnterpriseAnalytics(result.domains||{});})
     .catch(e=>{if(active)setEnterpriseAnalyticsError(e.message||"Unable to load enterprise workflow metrics.");});
   return()=>{active=false;};
 },[domain,manager,analyticsMonth,analyticsDomainFilter,analyticsDepartmentFilter]);
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
       if(fields.retention_until)form.append("retention_until",fields.retention_until);
       if(manager&&employeeId)form.append("employee_id",employeeId);
       await apiRequest("/hr/enterprise/documents/upload",{method:"POST",body:form});
       setDocumentFile(null);
       setNotice("Document uploaded to private storage.");
     }else{
       const recordPayload={...fields};
       const payload={record_type:recordType,title:title.trim(),payload:recordPayload};
       if(manager&&employeeId){
         payload.employee_id=Number(employeeId);
         if(domain==="assets"&&recordType==="allocation")recordPayload.employee_id=Number(employeeId);
       }
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
 function allowedTransitionsForRecord(item){
   const recordType=item.payload?.record_type;
   if(domain==="recruitment")return recruitmentRecordTransitions[recordType]?.[item.status]||[];
   const rules=domainRecordTransitions[domain];
   if(rules)return rules[recordType]?.[item.status]||[];
   return transitions[domain]?.[item.status]||[];
 }
 function selectableRecords(key){
   const type=referenceTypeByField[key];
   let rows=items.filter(x=>x.payload?.record_type===type);
   if(key==="policy_id")rows=rows.filter(x=>x.status==="approved");
   if(key==="course_id")rows=rows.filter(x=>x.status==="enrolled");
   if(key==="cycle_id")rows=rows.filter(x=>recordType==="goal"?x.status==="active":recordType==="self_review"?x.status==="self_review":x.status==="manager_review");
   if(key==="template_id")rows=rows.filter(x=>x.status==="active");
   if(key==="application_id")rows=rows.filter(x=>recordType==="interview"?["shortlisted","interview"].includes(x.status):x.status==="interview");
   if(key==="job_id")rows=rows.filter(x=>x.status==="open");
   if(key==="asset_id")rows=rows.filter(x=>["available","approved"].includes(x.status));
   if(key==="travel_record_id")rows=rows.filter(x=>recordType==="claim"?x.status==="completed":["approved","booked","in_progress"].includes(x.status));
   if(key==="exit_record_id")rows=rows.filter(x=>recordType==="clearance"?x.status==="clearance":x.status==="settlement_review");
   if(key==="enrollment_id")rows=rows.filter(x=>recordType==="progress"?x.status==="in_progress":recordType==="certificate"?x.status==="completed":["in_progress","completed"].includes(x.status));
   if(key==="review_id")rows=rows.filter(x=>recordType==="calibration"?x.status==="calibration":recordType==="acknowledgement"?["acknowledged","closed"].includes(x.status):["manager_review","calibration","acknowledged","closed"].includes(x.status));
   return rows;
 }
 function startHire(item){
   const application=items.find(x=>x.id===item.payload?.application_id&&x.payload?.record_type==="application");
   const candidate=items.find(x=>x.id===application?.payload?.candidate_id&&x.payload?.record_type==="candidate");
   const data=candidate?.payload||{};
   setHireOffer(item);setHireAccepted(false);
   setHireForm(old=>({...old,first_name:data.first_name||"",last_name:data.last_name||"",email:data.email||"",phone:data.phone||"",acceptance_reference:""}));
 }
 async function runScheduledReports(){
   setBusy(true);setError("");setNotice("");
   try{
     const result=await apiRequest("/hr/enterprise/analytics/scheduled/run",{method:"POST",body:"{}"});
     setNotice("Generated "+(result.processed||0)+" scheduled report snapshot(s).");
     await load();
   }catch(e){setError(e.message||"Unable to run scheduled analytics reports.");}
   finally{setBusy(false);}
 }
 async function exportAnalyticsFile(format){
   const [year,month]=analyticsMonth.split("-").map(Number);
   const fromDate=analyticsMonth+"-01";
   const toDate=analyticsMonth+"-"+String(new Date(year,month,0).getDate()).padStart(2,"0");
   const query="?from_date="+fromDate+"&to_date="+toDate
     +(analyticsDomainFilter?"&domain="+encodeURIComponent(analyticsDomainFilter):"")
     +(analyticsDepartmentFilter?"&department_id="+encodeURIComponent(analyticsDepartmentFilter):"");
   try{
     setError("");
     await apiDownload("/hr/enterprise/analytics/enterprise/export"+query+"&format="+format,
       "hr-enterprise-"+fromDate+"-"+toDate+"."+format);
   }catch(e){setError(e.message||"Unable to export analytics.");}
 }
 function exportAnalyticsCsv(){
   if(!analyticsData&&!enterpriseAnalytics)return;
   const rows=[
    ["Metric","Value"],
    ["Month",analyticsData.period?.month],
    ["Total workforce",analyticsData.workforce?.total],
    ["Active workforce",analyticsData.workforce?.active],
    ["Inactive workforce",analyticsData.workforce?.inactive],
    ["Joiners",analyticsData.workforce?.joiners],
    ["Exits",analyticsData.workforce?.exits],
    ["Present employees",analyticsData.attendance?.present],
    ["Absent employees",analyticsData.attendance?.absent],
    ["Attendance rate",analyticsData.attendance?.rate],
    ["Approved payroll gross",analyticsData.payroll?.gross],
    ["Approved payroll net",analyticsData.payroll?.net]
   ];
   if(analyticsData)rows.push([],["Department","Headcount"],...(analyticsData.workforce?.departments||[]).map(d=>[d.name,d.headcount]));
   if(enterpriseAnalytics){
    rows.push([],["HR domain","Records","Overdue","Due in 30 days"]);
    Object.entries(enterpriseAnalytics).forEach(([name,value])=>rows.push([name,value.records,value.overdue,value.due_soon]));
   }
   const quote=v=>'"'+String(v??"").replace(/"/g,'""')+'"';
   const csv=rows.map(row=>row.map(quote).join(",")).join("\r\n");
   const url=URL.createObjectURL(new Blob(["\\uFEFF",csv],{type:"text/csv;charset=utf-8"}));
   const link=document.createElement("a");link.href=url;link.download="hr-workforce-"+analyticsMonth+".csv";
   document.body.appendChild(link);link.click();link.remove();URL.revokeObjectURL(url);
 }
 async function sendCandidateEmail(e){
  e.preventDefault();if(!emailCandidate)return;
  setBusy(true);setError("");setNotice("");
  try{
   const result=await apiRequest("/hr/enterprise/recruitment/"+emailCandidate.id+"/email",{method:"POST",body:JSON.stringify(emailForm)});
   setNotice("Email delivered to "+result.recipient+". The sent message was added to the candidate communication history.");
   setEmailCandidate(null);setEmailForm({subject:"",message:""});await load();
  }catch(e){setError(e.message||"Unable to send candidate email.");}
  finally{setBusy(false);}
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
 const recruitmentView=useMemo(()=>{
  const records=items.filter(x=>x.domain==="recruitment");
  const ofType=name=>records.filter(x=>x.payload?.record_type===name);
  const candidates=ofType("candidate"),jobs=ofType("job_opening"),applications=ofType("application");
  const candidateById=Object.fromEntries(candidates.map(x=>[x.id,x]));
  const jobById=Object.fromEntries(jobs.map(x=>[x.id,x]));
  return {jobs,candidates,applications,interviews:ofType("interview"),offers:ofType("offer"),
   hired:ofType("offer").filter(x=>x.status==="hired").length,
   active:applications.filter(x=>!["rejected","withdrawn","hired","archived"].includes(x.status)),
   candidateById,jobById};
 },[items]);
 return <section className="hr-enterprise">
  <div className="hr-panel">
   <div className="hr-directory-heading"><div><h2>Integrated HR operations</h2><p>Recruitment, employee records, performance, training, assets, travel, exits and workforce reporting.</p></div><span className="hr-directory-count">8 domains</span></div>
   <nav className="hr-advanced-nav" aria-label="HR enterprise domains">{domains.filter(x=>manager||!["recruitment","analytics"].includes(x.id)).map(x=><button type="button" key={x.id} className={domain===x.id?"active":""} aria-pressed={domain===x.id} onClick={()=>setDomain(x.id)}>{x.label}</button>)}</nav>
   {error&&<p className="sb-alert" role="alert">{error}</p>}{notice&&<p className="sb-success" role="status">{notice}</p>}
   <h3>{current.label}</h3>
   {domain==="recruitment"&&manager&&<section className="hr-panel" aria-label="Recruitment pipeline">
    <div className="hr-directory-heading"><div><h3>Recruitment pipeline</h3><p>Live hiring funnel from open roles through candidate applications, interviews, offers and completed hires.</p></div><span className="hr-directory-count">{recruitmentView.jobs.filter(x=>x.status==="open").length} open roles</span></div>
    <div className="hr-overview">
     <article><span>Open roles</span><strong>{recruitmentView.jobs.filter(x=>x.status==="open").length}</strong><small>Approved headcount being recruited</small></article>
     <article><span>Candidate profiles</span><strong>{recruitmentView.candidates.length}</strong><small>Unique candidate records</small></article>
     <article><span>Active applications</span><strong>{recruitmentView.active.length}</strong><small>Not rejected, withdrawn or hired</small></article>
     <article><span>Interviews</span><strong>{recruitmentView.interviews.length}</strong><small>Scheduled interview records</small></article>
     <article><span>Open offers</span><strong>{recruitmentView.offers.filter(x=>x.status==="offered").length}</strong><small>Awaiting acceptance or decision</small></article>
     <article><span>Hires completed</span><strong>{recruitmentView.hired}</strong><small>Converted into employee profiles</small></article>
    </div>
    <div className="hr-directory-heading"><h3>Candidate directory</h3><span className="hr-directory-count">{recruitmentView.candidates.length} candidates</span></div>
    <div className="hr-table-wrap"><table><thead><tr><th>Candidate</th><th>Email</th><th>Source</th><th>Action</th></tr></thead><tbody>
     {recruitmentView.candidates.map(candidate=><tr key={candidate.id}><td>{[candidate.payload?.first_name,candidate.payload?.last_name].filter(Boolean).join(" ")||candidate.title}</td><td>{candidate.payload?.email||"—"}</td><td>{candidate.payload?.source||"—"}</td><td>{candidate.payload?.email&&<button type="button" disabled={busy} onClick={()=>{setEmailCandidate(candidate);setEmailForm({subject:"",message:""});}}>Email candidate</button>}</td></tr>)}
     {!recruitmentView.candidates.length&&<tr><td colSpan="4">No candidate profiles yet.</td></tr>}
    </tbody></table></div>
    <div className="hr-directory-heading"><h3>Application pipeline</h3><span className="hr-directory-count">{recruitmentView.applications.length} applications</span></div>
    <div className="hr-table-wrap"><table><thead><tr><th>Candidate</th><th>Position</th><th>Stage</th><th>Last updated</th></tr></thead><tbody>
     {recruitmentView.applications.map(app=>{const candidate=recruitmentView.candidateById[app.payload?.candidate_id];const job=recruitmentView.jobById[app.payload?.job_id];return <tr key={app.id}><td><strong>{candidate?[candidate.payload?.first_name,candidate.payload?.last_name].filter(Boolean).join(" "):"Candidate record #"+app.payload?.candidate_id}</strong><small>{candidate?.payload?.email||"Candidate details unavailable"}</small></td><td>{job?.title||"Job #"+app.payload?.job_id}</td><td>{app.status.replaceAll("_"," ")}</td><td>{app.updated_at?new Date(app.updated_at).toLocaleDateString():"—"}</td></tr>;})}
     {!recruitmentView.applications.length&&<tr><td colSpan="4">No applications yet. Create a job opening and candidate profile, then link them with an application.</td></tr>}
    </tbody></table></div>
   </section>}
   {domain==="documents"&&manager&&<section className="hr-panel" aria-label="Document and asset expiry queue">
    <div className="hr-directory-heading"><div><h3>Expiring records</h3><p>Offers, employee documents, learning certificates and asset warranties due within 30 days or already expired.</p></div><span className="hr-directory-count">{expiringItems.length} due</span></div>
    {expiringError&&<p role="alert" className="sb-alert">{expiringError}</p>}
    {expiringLoading?<p role="status">Loading expiry queue…</p>:<div className="hr-table-wrap"><table><thead><tr><th>Record</th><th>Employee</th><th>Due date</th><th>Status</th></tr></thead><tbody>{expiringItems.map(x=><tr key={x.id}><td>{x.title}<small>{x.domain} · #{x.id}</small></td><td>{x.employee_code?x.employee_code+" — "+x.first_name+" "+(x.last_name||""):"—"}</td><td>{x.due_date}</td><td>{x.status}</td></tr>)}{!expiringItems.length&&<tr><td colSpan="4">No expiring records in this window.</td></tr>}</tbody></table></div>}
   </section>}
   {domain==="analytics"&&manager&&<section className="hr-panel" aria-label="Computed workforce analytics">
    <div className="hr-directory-heading"><div><h3>Workforce analytics</h3><p>Live metrics from the existing HR, attendance, leave and approved payroll records.</p></div><label>Reporting month<input type="month" value={analyticsMonth} onChange={e=>setAnalyticsMonth(e.target.value)}/></label>
     <label>Domain filter<select value={analyticsDomainFilter} onChange={e=>setAnalyticsDomainFilter(e.target.value)}><option value="">All seven domains</option>{domains.filter(x=>x.id!=="recruitment").map(x=><option key={x.id} value={x.id}>{x.label}</option>)}</select></label>
     <label>Department filter<select value={analyticsDepartmentFilter} onChange={e=>setAnalyticsDepartmentFilter(e.target.value)}><option value="">All departments</option>{[...new Map(employees.filter(x=>x.department_id).map(x=>[String(x.department_id),x.department_name||("Department "+x.department_id)])).entries()].map(([id,name])=><option key={id} value={id}>{name}</option>)}</select></label><button type="button" className="hr-secondary" disabled={!analyticsData&&!enterpriseAnalytics} onClick={exportAnalyticsCsv}>Export CSV</button>
     <button type="button" className="hr-secondary" disabled={busy} onClick={runScheduledReports}>Run due scheduled reports</button>
     <button type="button" className="hr-secondary" disabled={!enterpriseAnalytics} onClick={()=>exportAnalyticsFile("xlsx")}>Export XLSX</button>
     <button type="button" className="hr-secondary" disabled={!enterpriseAnalytics} onClick={()=>exportAnalyticsFile("pdf")}>Export PDF</button></div>
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

    <section aria-label="Enterprise HR workflow KPIs">
     <div className="hr-directory-heading"><div><h3>Seven-domain operations</h3><p>Operational record volumes, overdue work and items due within 30 days for the selected creation period.</p></div></div>
     {enterpriseAnalyticsError&&<p role="alert" className="sb-alert">{enterpriseAnalyticsError}</p>}
     <div className="hr-table-wrap"><table><thead><tr><th>Domain</th><th>Records</th><th>Overdue</th><th>Due in 30 days</th></tr></thead><tbody>
      {Object.entries(enterpriseAnalytics||{}).map(([name,value])=><tr key={name}><td>{name.replaceAll("_"," ")}</td><td>{value.records}</td><td>{value.overdue}</td><td>{value.due_soon}</td></tr>)}
      {!Object.keys(enterpriseAnalytics||{}).length&&<tr><td colSpan="4">No enterprise workflow records in this reporting period.</td></tr>}
     </tbody></table></div>
    </section>
    <p className="hr-enterprise-note">Metrics are calculated from recorded data. Attendance absence and rate are unavailable when there is no published shift schedule; late-arrival and attendance trend metrics are not currently calculated.</p></>}
   </section>}
   <form className="hr-form hr-grid" onSubmit={create}>
    <label>Record type<select value={recordType} onChange={e=>{setRecordType(e.target.value);setFields({});}}>{availableTypes.map(x=><option key={x[0]} value={x[0]}>{x[1]}</option>)}</select></label>
    {domain!=="documents"&&<label>Title<input required maxLength="200" value={title} onChange={e=>setTitle(e.target.value)}/></label>}
    {manager&&<label>{domain==="travel"&&recordType==="request"||domain==="exit"&&recordType==="case"||domain==="performance"&&(recordType==="review"||recordType==="self_review")?"Employee (required)":"Employee (optional)"}<select required={domain==="travel"&&recordType==="request"||domain==="exit"&&recordType==="case"||domain==="performance"&&(recordType==="review"||recordType==="self_review")} value={employeeId} onChange={e=>setEmployeeId(e.target.value)}><option value="">Not employee-linked</option>{employees.map(x=><option key={x.id} value={x.id}>{employeeNames[x.id]}</option>)}</select></label>}
    {type[2].map(([key,label,inputType])=><label key={key}>{label}{inputType==="select"?<select required value={fields[key]||"identity"} onChange={e=>update(key,e.target.value)}><option value="identity">Identity</option><option value="address">Address</option><option value="qualification">Qualification</option><option value="employment">Employment</option><option value="contract">Contract</option><option value="policy_acknowledgement">Policy acknowledgement</option><option value="other">Other</option></select>:inputType==="record_select"?<select required value={fields[key]||""} onChange={e=>update(key,e.target.value)}><option value="">Select a record</option>{selectableRecords(key).map(x=><option key={x.id} value={x.id}>{x.title} · #{x.id}</option>)}</select>:inputType==="textarea"?<textarea rows="2" value={fields[key]||""} onChange={e=>update(key,e.target.value)}/>:<input type={inputType||"text"} required={!optionalFields.has(key)} value={fields[key]||""} onChange={e=>update(key,e.target.value)}/>}</label>)}\n    {domain==="documents"&&<label>Document file<input type="file" accept="application/pdf,image/jpeg,image/png" required onChange={e=>setDocumentFile(e.target.files?.[0]||null)}/><small>Private encrypted storage · PDF/JPEG/PNG · maximum 10 MB</small></label>}
    <button disabled={busy}>Create {type[1].toLowerCase()}</button>
   </form>
   {emailCandidate&&manager&&<section className="hr-panel" aria-label="Send candidate email">
    <div className="hr-directory-heading"><div><h3>Email candidate · {[emailCandidate.payload?.first_name,emailCandidate.payload?.last_name].filter(Boolean).join(" ")}</h3><p>To: {emailCandidate.payload?.email}</p></div><button type="button" className="hr-secondary" onClick={()=>setEmailCandidate(null)}>Cancel</button></div>
    <form className="hr-form hr-grid" onSubmit={sendCandidateEmail}>
     <label>Subject<input required maxLength="200" value={emailForm.subject} onChange={e=>setEmailForm({...emailForm,subject:e.target.value})}/></label>
     <label className="hr-full">Message<textarea required rows="5" maxLength="10000" value={emailForm.message} onChange={e=>setEmailForm({...emailForm,message:e.target.value})}/></label>
     <button disabled={busy}>Send email</button>
    </form>
   </section>}
   {hireOffer&&manager&&<section className="hr-panel"><div className="hr-directory-heading"><div><h3>Convert accepted offer to employee</h3><p>This creates the employee identity, opening salary profile and any configured onboarding checklist tasks.</p></div><button type="button" className="hr-secondary" onClick={()=>setHireOffer(null)}>Cancel</button></div>
    <form className="hr-form hr-grid" onSubmit={submitHire}>
     <label>Employee code<input required value={hireForm.employee_code} onChange={e=>setHireForm({...hireForm,employee_code:e.target.value})}/></label>
     <label>First name<input required value={hireForm.first_name} onChange={e=>setHireForm({...hireForm,first_name:e.target.value})}/></label>
     <label>Last name<input value={hireForm.last_name} onChange={e=>setHireForm({...hireForm,last_name:e.target.value})}/></label>
     <label>Email<input required type="email" value={hireForm.email} onChange={e=>setHireForm({...hireForm,email:e.target.value})}/></label>
     <label>Phone<input value={hireForm.phone} onChange={e=>setHireForm({...hireForm,phone:e.target.value})}/></label>
     <label>Department ID<input type="number" min="1" value={hireForm.department_id} onChange={e=>setHireForm({...hireForm,department_id:e.target.value})}/></label>
     <label>Designation<input required value={hireForm.designation} onChange={e=>setHireForm({...hireForm,designation:e.target.value})}/></label>
     <label>Job grade<input required maxLength="32" value={hireForm.job_grade} onChange={e=>setHireForm({...hireForm,job_grade:e.target.value})}/></label>
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
   <div className="hr-table-wrap"><table><thead><tr><th>Record</th><th>Employee</th><th>Status</th><th>Due / expiry</th><th>Updated</th><th>Workflow actions</th></tr></thead><tbody>
    {items.filter(item=>(!statusFilter||item.status===statusFilter)&&(!recordSearch||[item.title,employeeNames[item.employee_id]||""].join(" ").toLowerCase().includes(recordSearch.toLowerCase()))).map(item=><tr key={item.id}><td><strong>{item.title}</strong><small>#{item.id} · {item.payload?.record_type||"Record"}</small></td><td>{employeeNames[item.employee_id]||"—"}</td><td>{item.status}</td><td>{item.due_date||"—"}</td><td>{item.updated_at?new Date(item.updated_at).toLocaleString():"—"}</td><td>{domain==="documents"&&(manager?["under_review","verified"]:["verified"]).includes(item.status)&&<button type="button" disabled={busy} onClick={async()=>{try{const result=await apiRequest("/hr/enterprise/documents/"+item.id+"/download",{method:"POST",body:"{}"});window.open(result.url,"_blank","noopener,noreferrer");}catch(e){setError(e.message||"Unable to download document.");}}}>Secure download</button>}{manager&&domain==="recruitment"&&item.payload?.record_type==="offer"&&item.status==="offered"&&<button type="button" disabled={busy} onClick={()=>startHire(item)}>Convert to employee</button>}{(manager?allowedTransitionsForRecord(item):(employeeTransitions[domain]?.[item.status]||[])).map(next=><button type="button" key={next} disabled={busy} onClick={()=>transition(item,next)}>{next.replaceAll("_"," ")}</button>)}{manager&&<button type="button" className="hr-secondary" disabled={busy} onClick={()=>showEvents(item)}>Audit trail</button>}</td></tr>)}
    {!items.filter(item=>(!statusFilter||item.status===statusFilter)&&(!recordSearch||[item.title,employeeNames[item.employee_id]||""].join(" ").toLowerCase().includes(recordSearch.toLowerCase()))).length&&<tr><td colSpan="6">{busy?"Loading…":"No records match these filters."}</td></tr>}
   </tbody></table></div>
   {eventRecord&&manager&&<section className="hr-panel"><div className="hr-directory-heading"><h3>Audit trail · {eventRecord.title}</h3><button type="button" className="hr-secondary" onClick={()=>{setEventRecord(null);setRecordEvents([]);}}>Close</button></div>{eventsBusy?<p role="status">Loading audit events…</p>:<ol>{recordEvents.map(ev=><li key={ev.id}><strong>{ev.event_type}</strong> · {ev.from_status||"—"} → {ev.to_status||"—"} · {ev.created_at?new Date(ev.created_at).toLocaleString():""}{ev.note&&<p>{ev.note}</p>}</li>)}{!recordEvents.length&&<li>No audit events found.</li>}</ol>}</section>}
   {domain==="documents"&&<p className="hr-enterprise-note">Files are stored in the configured private S3 bucket with server-side encryption and short-lived, access-checked download links. Configure bucket access and retention policy before production use.</p>}
  </div>
 </section>;
}
