import { useCallback, useEffect, useState } from "react";
import { apiRequest } from "../../services/api.js";
import { todayHRDate } from "./hrDateTime.js";
import { exportStatutoryRemittancesCsv } from "./hrStatutoryExport.js";

function downloadRemittanceRegister(items) {
  const blob = new Blob([exportStatutoryRemittancesCsv(items)], { type: "text/csv;charset=utf-8;" });
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = "hr-statutory-remittance-register.csv";
  document.body.appendChild(link);
  link.click();
  link.remove();
  URL.revokeObjectURL(url);
}

const emptyEstablishment = {code:"",legal_name:"",display_name:"",state_code:"",address:{},registrations:{}};
const emptyPolicy = {establishment_id:"",component:"pf",version_label:"",effective_from:todayHRDate(),effective_to:"",review_due_on:"",policy_config:'{"enabled":false}',source_references:"[]"};
const emptyProfile = {establishment_id:"",uan:"",esic_number:"",pan:"",tds_regime:"new",override_reason:"",pf_applicable_override:"",esi_applicable_override:"",pt_applicable_override:"",declarations:"{}",exemptions:"{}",previous_employer_income:"{}",effective_from:todayHRDate(),effective_to:""};

export default function HRStatutoryPolicies() {
  const [establishments,setEstablishments]=useState([]);
  const [policies,setPolicies]=useState([]);
  const [employees,setEmployees]=useState([]);
  const [runs,setRuns]=useState([]);
  const [remittances,setRemittances]=useState([]);
  const [voucherIds,setVoucherIds]=useState({});
  const [challans,setChallans]=useState({});
  const [employeeId,setEmployeeId]=useState("");
  const [profile,setProfile]=useState(emptyProfile);
  const [establishment,setEstablishment]=useState(emptyEstablishment);
  const [editingEstablishment,setEditingEstablishment]=useState(null);
  const [addressText,setAddressText]=useState("{}");
  const [registrationsText,setRegistrationsText]=useState("{}");
  const [policy,setPolicy]=useState(emptyPolicy);
  const [error,setError]=useState("");
  const [notice,setNotice]=useState("");
  const [busy,setBusy]=useState(false);

  const load=useCallback(async()=>{
    setError("");
    try{
      const [e,p,staff,r,rem]=await Promise.all([apiRequest("/hr/establishments"),apiRequest("/hr/statutory/policies"),apiRequest("/hr/employees"),apiRequest("/hr/payroll/runs"),apiRequest("/hr/statutory/remittances")]);
      setEstablishments(e.items||[]);
      setPolicies(p.items||[]);
      setEmployees(staff.items||[]);
      setRuns(r.items||[]);
      setRemittances(rem.items||[]);
      if(!policy.establishment_id && e.items?.length) setPolicy(x=>({...x,establishment_id:String(e.items[0].id)}));
    }catch(err){setError(err.message||"Unable to load statutory policy records.");}
  },[policy.establishment_id]);
  useEffect(()=>{load();},[load]);

  async function act(fn,message){
    setBusy(true);setError("");setNotice("");
    try{await fn();setNotice(message);await load();return true;}
    catch(err){setError(err.message||"Operation failed.");return false;}
    finally{setBusy(false);}
  }
  async function createEstablishment(event){
    event.preventDefault();
    let address,registrations;try{address=JSON.parse(addressText);registrations=JSON.parse(registrationsText);}catch{setError("Address and registration details must be valid JSON objects.");return;}
    const saved=await act(()=>apiRequest(editingEstablishment?"/hr/establishments/"+editingEstablishment:"/hr/establishments",{method:editingEstablishment?"PUT":"POST",body:JSON.stringify({...establishment,address,registrations})}),editingEstablishment?"Establishment updated.":"Establishment created.");
    if(saved){setEstablishment(emptyEstablishment);setEditingEstablishment(null);setAddressText("{}");setRegistrationsText("{}");}
  }
  async function createPolicy(event){
    event.preventDefault();
    let config,sources;
    try{config=JSON.parse(policy.policy_config);sources=JSON.parse(policy.source_references);}
    catch{setError("Policy configuration and source references must be valid JSON.");return;}
    const saved=await act(()=>apiRequest("/hr/statutory/policies",{method:"POST",body:JSON.stringify({
      establishment_id:Number(policy.establishment_id),component:policy.component,version_label:policy.version_label,
      effective_from:policy.effective_from,effective_to:policy.effective_to||null,
      review_due_on:policy.review_due_on||null,policy_config:config,source_references:sources
    })}),"Policy draft created.");
    if(saved) setPolicy(x=>({...emptyPolicy,establishment_id:x.establishment_id}));
  }
  const post=(path,body={})=>apiRequest(path,{method:"POST",body:JSON.stringify(body)});
  return <div className="hr-panel">
    <h2>Establishments & statutory policies</h2>
    <p>Configure each legal establishment independently. PF, ESI, PT and TDS remain inactive until an authorised policy version is approved. No rates or state rules are prefilled as legal defaults.</p>
    <nav className="hr-compliance-nav" aria-label="Compliance sections"><a href="#hr-compliance-establishments">Establishments</a><a href="#hr-compliance-policies">Policy versions</a><a href="#hr-compliance-employees">Employee profiles</a><a href="#hr-compliance-remittances">Remittances</a><a href="#hr-compliance-register">Policy register</a></nav>
    {error&&<p className="sb-alert" role="alert">{error}</p>}
    {notice&&<p className="sb-success" role="status">{notice}</p>}
    <details id="hr-compliance-establishments" className="hr-compliance-section" open><summary>Establishments</summary>
    <form className="hr-form" onSubmit={createEstablishment}>
      <h3>{editingEstablishment?"Edit establishment":"Add establishment"}</h3>
      <label>Establishment code<input aria-label="Establishment code" placeholder="e.g. KPMC-HO" value={establishment.code} onChange={e=>setEstablishment({...establishment,code:e.target.value})} required/></label>
      <label>Legal entity name<input aria-label="Legal name" placeholder="Registered legal name" value={establishment.legal_name} onChange={e=>setEstablishment({...establishment,legal_name:e.target.value})} required/></label>
      <label>Display name<input aria-label="Display name" placeholder="Name shown in HR" value={establishment.display_name} onChange={e=>setEstablishment({...establishment,display_name:e.target.value})} required/></label>
      <label>State / UT<select aria-label="State code" required value={establishment.state_code} onChange={e=>setEstablishment({...establishment,state_code:e.target.value})}>
        <option value="">Select state / UT</option>{["AN","AP","AR","AS","BR","CH","CT","DN","DD","DL","GA","GJ","HR","HP","JH","KA","KL","LA","LD","MP","MH","MN","ML","MZ","NL","OD","PB","PY","RJ","SK","TN","TS","TR","UP","UK","WB"].map(code=><option key={code} value={code}>{code}</option>)}
      </select></label>
      <label>Address (JSON)<textarea rows="2" placeholder='{"line1":"...","city":"...","pincode":"..."}' value={addressText} onChange={e=>setAddressText(e.target.value)}/></label>
      <label>Registrations (JSON)<textarea rows="2" placeholder='{"gstin":"...","pf_code":"...","esi_code":"..."}' value={registrationsText} onChange={e=>setRegistrationsText(e.target.value)}/></label>
      <button disabled={busy}>{editingEstablishment?"Save establishment":"Add establishment"}</button>
      {editingEstablishment&&<button type="button" onClick={()=>{setEditingEstablishment(null);setEstablishment(emptyEstablishment);setAddressText("{}");setRegistrationsText("{}");}}>Cancel</button>}
    </form>
    <div className="hr-table-wrap"><table><thead><tr><th>Code</th><th>Establishment</th><th>State</th><th>Registrations</th><th>Status</th><th>Actions</th></tr></thead><tbody>
      {establishments.map(e=><tr key={e.id}><td>{e.code}</td><td>{e.display_name}<small>{e.legal_name}</small></td><td>{e.state_code}</td><td>{Object.keys(e.registrations||{}).join(", ")||"Not recorded"}</td><td>{e.is_active?"Active":"Inactive"}</td><td><button type="button" disabled={busy||!e.is_active} onClick={()=>{setEditingEstablishment(e.id);setEstablishment({code:e.code,legal_name:e.legal_name,display_name:e.display_name,state_code:e.state_code,address:e.address||{},registrations:e.registrations||{}});setAddressText(JSON.stringify(e.address||{},null,2));setRegistrationsText(JSON.stringify(e.registrations||{},null,2));}}>Edit</button> {e.is_active&&<button type="button" disabled={busy} onClick={()=>act(()=>post("/hr/establishments/"+e.id+"/deactivate"),"Establishment deactivated.")}>Deactivate</button>}</td></tr>)}
      {!establishments.length&&<tr><td colSpan="6">No establishment configured.</td></tr>}
    </tbody></table></div>
    </details>
    <details id="hr-compliance-policies" className="hr-compliance-section"><summary>Policy versions</summary>
    <form className="hr-form" onSubmit={createPolicy}>
      <select aria-label="Establishment" value={policy.establishment_id} onChange={e=>setPolicy({...policy,establishment_id:e.target.value})} required>
        <option value="">Select establishment</option>{establishments.map(e=><option key={e.id} value={e.id}>{e.display_name} · {e.state_code}</option>)}
      </select>
      <select aria-label="Statutory component" value={policy.component} onChange={e=>setPolicy({...policy,component:e.target.value})}>
        <option value="pf">PF / EPF</option><option value="esi">ESI</option><option value="pt">Professional Tax</option><option value="tds">Salary TDS</option>
      </select>
      <input aria-label="Policy version label" placeholder="Version label" value={policy.version_label} onChange={e=>setPolicy({...policy,version_label:e.target.value})} required/>
      <label>Effective from<input type="date" value={policy.effective_from} onChange={e=>setPolicy({...policy,effective_from:e.target.value})} required/></label>
      <label>Effective to<input type="date" value={policy.effective_to} onChange={e=>setPolicy({...policy,effective_to:e.target.value})}/></label>
      <label>Review due<input type="date" value={policy.review_due_on} onChange={e=>setPolicy({...policy,review_due_on:e.target.value})}/></label>
      <textarea aria-label="Policy configuration JSON" rows="5" value={policy.policy_config} onChange={e=>setPolicy({...policy,policy_config:e.target.value})}/>
      <textarea aria-label="Source references JSON" rows="3" value={policy.source_references} onChange={e=>setPolicy({...policy,source_references:e.target.value})}/>
      <button disabled={busy||!establishments.length}>Save policy draft</button>
    </form>
    <p>Policy configuration must contain the reviewed rates, wage basis, caps, slabs or TDS projection inputs applicable to the selected establishment and period. Keep source notification references in the source JSON.</p>
    </details>
    <details id="hr-compliance-employees" className="hr-compliance-section"><summary>Employee compliance profiles</summary>
    <form className="hr-form" onSubmit={async event=>{
      event.preventDefault();
      let declarations,exemptions,previous;
      try{declarations=JSON.parse(profile.declarations);exemptions=JSON.parse(profile.exemptions);previous=JSON.parse(profile.previous_employer_income);}
      catch{setError("Declarations, exemptions and previous-employer income must be valid JSON.");return;}
      if(!employeeId){setError("Select an employee.");return;}
      await act(()=>apiRequest("/hr/employees/"+employeeId+"/statutory-profile",{method:"PUT",body:JSON.stringify({...profile,establishment_id:Number(profile.establishment_id),tds_regime:profile.tds_regime||null,pf_applicable_override:profile.pf_applicable_override===""?null:profile.pf_applicable_override==="true",esi_applicable_override:profile.esi_applicable_override===""?null:profile.esi_applicable_override==="true",pt_applicable_override:profile.pt_applicable_override===""?null:profile.pt_applicable_override==="true",declarations,exemptions,previous_employer_income:previous,effective_to:profile.effective_to||null})}),"Employee statutory profile saved.");
    }}>
      <select aria-label="Employee" value={employeeId} onChange={async e=>{
        const id=e.target.value;setEmployeeId(id);setProfile(x=>({...emptyProfile,establishment_id:establishments[0]?String(establishments[0].id):""}));
        if(id){try{const existing=await apiRequest("/hr/employees/"+id+"/statutory-profile");setProfile({...emptyProfile,...existing,establishment_id:String(existing.establishment_id),pf_applicable_override:existing.pf_applicable_override===null?"":String(existing.pf_applicable_override),esi_applicable_override:existing.esi_applicable_override===null?"":String(existing.esi_applicable_override),pt_applicable_override:existing.pt_applicable_override===null?"":String(existing.pt_applicable_override),declarations:JSON.stringify(existing.declarations||{},null,2),exemptions:JSON.stringify(existing.exemptions||{},null,2),previous_employer_income:JSON.stringify(existing.previous_employer_income||{},null,2),effective_from:existing.effective_from?.slice(0,10)||emptyProfile.effective_from,effective_to:existing.effective_to?.slice(0,10)||""});}catch{}}
      }} required><option value="">Select employee</option>{employees.map(e=><option key={e.id} value={e.id}>{e.employee_code} · {e.first_name} {e.last_name}</option>)}</select>
      <select aria-label="Employee establishment" value={profile.establishment_id} onChange={e=>setProfile({...profile,establishment_id:e.target.value})} required><option value="">Select establishment</option>{establishments.map(e=><option key={e.id} value={e.id}>{e.display_name} · {e.state_code}</option>)}</select>
      <input aria-label="UAN" placeholder="UAN" value={profile.uan||""} onChange={e=>setProfile({...profile,uan:e.target.value})}/>
      <input aria-label="ESIC number" placeholder="ESIC number" value={profile.esic_number||""} onChange={e=>setProfile({...profile,esic_number:e.target.value})}/>
      <input aria-label="PAN" placeholder="PAN" maxLength="10" value={profile.pan||""} onChange={e=>setProfile({...profile,pan:e.target.value.toUpperCase()})}/>
      <select aria-label="TDS tax regime" value={profile.tds_regime||""} onChange={e=>setProfile({...profile,tds_regime:e.target.value})}><option value="">Select tax regime</option><option value="new">New regime</option><option value="old">Old regime</option></select>
      {["pf","esi","pt"].map(key=><label key={key}>{key.toUpperCase()} applicability override<select aria-label={key.toUpperCase()+" applicability override"} value={profile[key+"_applicable_override"]??""} onChange={e=>setProfile({...profile,[key+"_applicable_override"]:e.target.value})}><option value="">Use approved policy</option><option value="true">Applicable</option><option value="false">Not applicable</option></select></label>)}
      <input aria-label="Applicability override reason" placeholder="Reason for any applicability override" value={profile.override_reason||""} onChange={e=>setProfile({...profile,override_reason:e.target.value})}/>
      <label>Profile effective from<input type="date" value={profile.effective_from} onChange={e=>setProfile({...profile,effective_from:e.target.value})}/></label>
      <label>Profile effective to<input type="date" value={profile.effective_to} onChange={e=>setProfile({...profile,effective_to:e.target.value})}/></label>
      <textarea aria-label="Employee tax declarations JSON" rows="3" value={profile.declarations} onChange={e=>setProfile({...profile,declarations:e.target.value})}/>
      <textarea aria-label="Employee statutory exemptions JSON" rows="3" value={profile.exemptions} onChange={e=>setProfile({...profile,exemptions:e.target.value})}/>
      <textarea aria-label="Previous employer income JSON" rows="3" value={profile.previous_employer_income} onChange={e=>setProfile({...profile,previous_employer_income:e.target.value})}/>
      <button disabled={busy||!establishments.length||!employees.length}>Save employee compliance profile</button>
    </form>
    <p>Employee-level applicability overrides are explicit and audited. Keep declarations and previous-employer figures current for the applicable tax year; only fields supported by the approved policy calculation are used in payroll.</p>
    </details>
    <details id="hr-compliance-remittances" className="hr-compliance-section" open><summary>Remittances & challans</summary>
    <p>Generate remittance obligations from approved payroll snapshots, link the exact posted payment voucher, then record the challan reference after filing. This register is a reconciliation aid, not a substitute for the prescribed portal return or challan.</p>
    <button type="button" className="secondary" disabled={!remittances.length} onClick={()=>downloadRemittanceRegister(remittances)}>Export remittance register CSV</button>
    <div className="hr-table-wrap"><table><thead><tr><th>Payroll period</th><th>Component</th><th>Establishment</th><th>Employee / employer</th><th>Total</th><th>Status</th><th>Action</th></tr></thead><tbody>
      {remittances.map(r=><tr key={r.id}><td>{r.period_start} – {r.period_end}</td><td>{r.component.toUpperCase()}</td><td>{r.display_name} · {r.state_code}</td><td>{r.employee_amount} / {r.employer_amount}</td><td>{r.total_amount}</td><td>{r.status}{r.challan_reference&&<small>Challan: {r.challan_reference}</small>}</td><td>
        {r.status==="pending"&&<><input aria-label={"Payment voucher for remittance "+r.id} type="number" placeholder="Posted payment voucher ID" value={voucherIds[r.id]||""} onChange={e=>setVoucherIds({...voucherIds,[r.id]:e.target.value})}/><button disabled={busy||!voucherIds[r.id]} onClick={()=>act(()=>post("/hr/statutory/remittances/"+r.id+"/pay",{accounting_voucher_id:Number(voucherIds[r.id])}),"Remittance payment linked.")}>Mark paid</button></>}
        {r.status==="paid"&&<><input aria-label={"Challan reference for remittance "+r.id} placeholder="Challan reference" value={challans[r.id]||""} onChange={e=>setChallans({...challans,[r.id]:e.target.value})}/><button disabled={busy||!challans[r.id]} onClick={()=>act(()=>post("/hr/statutory/remittances/"+r.id+"/file",{challan_reference:challans[r.id]}),"Challan filing recorded.")}>Record filing</button></>}
        {r.status==="filed"&&"Filed"}
      </td></tr>)}
      {!remittances.length&&<tr><td colSpan="7">No statutory remittances generated.</td></tr>}
    </tbody></table></div>
    <h3>Generate remittances from approved payroll</h3>
    <div className="hr-department-list">{runs.filter(r=>["approved","paid"].includes(r.status)).map(r=><button key={r.id} disabled={busy} onClick={()=>act(()=>post("/hr/payroll/runs/"+r.id+"/statutory-remittances",{}),"Remittance rows generated or already exist for payroll run #"+r.id+".")}>Generate for {r.period_start} · Run #{r.id}</button>)}</div>
    </details>
    <details id="hr-compliance-register" className="hr-compliance-section"><summary>Policy register</summary>
    <div className="hr-table-wrap"><table><thead><tr><th>Component</th><th>Establishment</th><th>Version / effective period</th><th>Status</th><th>Approval</th></tr></thead><tbody>
      {policies.map(p=><tr key={p.id}><td>{p.component.toUpperCase()}</td><td>{p.display_name} · {p.state_code}</td><td>{p.version_label}<small>{p.effective_from} – {p.effective_to||"Open-ended"}</small></td><td>{p.status}</td><td>{p.status==="draft"&&<button disabled={busy} onClick={()=>act(()=>post("/hr/statutory/policies/"+p.id+"/submit"),"Policy submitted for approval.")}>Submit</button>}{p.status==="in_review"&&<button disabled={busy} onClick={()=>act(()=>post("/hr/statutory/policies/"+p.id+"/approve"),"Policy approved and effective period reserved.")}>Approve</button>}{p.status==="approved"&&"Approved"}</td></tr>)}
      {!policies.length&&<tr><td colSpan="5">No statutory policy versions created.</td></tr>}
    </tbody></table></div>
</details>
      </div>;
}
