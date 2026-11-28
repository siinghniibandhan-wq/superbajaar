import { useCallback, useEffect, useState } from "react";
import { apiRequest } from "../../services/api.js";

const blankContact = { contact_name:"", relationship:"", phone:"", alternate_phone:"", email:"", address:"", is_primary:false };
const blankHistory = { employer_name:"", job_title:"", employment_type:"full_time", location:"", start_date:"", end_date:"", description:"" };

export default function HREmployeeRecords({ employee }) {
  const [contacts,setContacts]=useState([]);
  const [history,setHistory]=useState([]);
  const [events,setEvents]=useState([]);
  const [contact,setContact]=useState(blankContact);
  const [prior,setPrior]=useState(blankHistory);
  const [busy,setBusy]=useState(false);
  const [error,setError]=useState("");
  const [notice,setNotice]=useState("");

  const load=useCallback(async()=>{
    if(!employee?.id)return;
    setError("");
    try{
      const [contactResult,historyResult,argumentsResult]=await Promise.all([
        apiRequest("/hr/employees/"+employee.id+"/emergency-contacts"),
        apiRequest("/hr/employees/"+employee.id+"/employment-history"),
        apiRequest("/hr/employees/"+employee.id+"/record-events")
      ]);
      setContacts(contactResult.items||[]);
      setHistory(historyResult.items||[]);
      setEvents((argumentsResult.items||[]));
    }catch(e){setError(e.message||"Unable to load employee records.");}
  },[employee?.id]);
  useEffect(()=>{load();},[load]);

  async function submit(path,body,message){
    setBusy(true);setError("");setNotice("");
    try{
      await apiRequest(path,{method:"POST",body:JSON.stringify(body)});
      setNotice(message);
      await load();
      return true;
    }catch(e){setError(e.message||"Unable to save employee record.");return false;}
    finally{setBusy(false);}
  }
  async function deactivate(item){
    if(!window.confirm("Deactivate this emergency contact? The record will be retained in the audit history."))return;
    setBusy(true);setError("");setNotice("");
    try{
      await apiRequest("/hr/employees/"+employee.id+"/emergency-contacts/"+item.id+"/deactivate",{method:"POST",body:"{}"});
      setNotice("Emergency contact deactivated.");
      await load();
    }catch(e){setError(e.message||"Unable to deactivate emergency contact.");}
    finally{setBusy(false);}
  }

  if(!employee?.id)return null;
  return <div className="hr-employee-records">
    <section className="hr-panel" aria-labelledby="hr-emergency-contacts-heading">
      <div className="hr-directory-heading"><div><h3 id="hr-emergency-contacts-heading">Emergency contacts</h3><p>Keep a current contact for urgent situations. Access is restricted to HR managers.</p></div><span className="hr-directory-count">{contacts.filter(x=>x.is_active).length} active</span></div>
      <form className="hr-form hr-grid" onSubmit={async e=>{e.preventDefault();if(await submit("/hr/employees/"+employee.id+"/emergency-contacts",contact,"Emergency contact saved."))setContact(blankContact);}}>
        <label>Contact name<input maxLength="160" required value={contact.contact_name} onChange={e=>setContact({...contact,contact_name:e.target.value})}/></label>
        <label>Relationship<input maxLength="80" placeholder="e.g. Spouse, parent, sibling" required value={contact.relationship} onChange={e=>setContact({...contact,relationship:e.target.value})}/></label>
        <label>Primary phone<input type="tel" maxLength="32" required value={contact.phone} onChange={e=>setContact({...contact,phone:e.target.value})}/></label>
        <label>Alternate phone<input type="tel" maxLength="32" value={contact.alternate_phone} onChange={e=>setContact({...contact,alternate_phone:e.target.value})}/></label>
        <label>Email<input type="email" maxLength="254" value={contact.email} onChange={e=>setContact({...contact,email:e.target.value})}/></label>
        <label>Address<input maxLength="500" value={contact.address} onChange={e=>setContact({...contact,address:e.target.value})}/></label>
        <label className="hr-check"><input type="checkbox" checked={contact.is_primary} onChange={e=>setContact({...contact,is_primary:e.target.checked})}/> Set as primary emergency contact</label>
        <button type="submit" disabled={busy}>Add emergency contact</button>
      </form>
      <div className="hr-table-wrap"><table><thead><tr><th>Contact</th><th>Relationship</th><th>Phone</th><th>Other details</th><th>Status</th><th>Action</th></tr></thead><tbody>
        {contacts.map(item=><tr key={item.id}><td>{item.contact_name}{item.is_primary&&<small>Primary contact</small>}</td><td>{item.relationship}</td><td>{item.phone}{item.alternate_phone&&<small>Alt: {item.alternate_phone}</small>}</td><td>{item.email||"—"}{item.address&&<small>{item.address}</small>}</td><td>{item.is_active?"Active":"Inactive"}</td><td>{item.is_active&&<button type="button" disabled={busy} onClick={()=>deactivate(item)}>Deactivate</button>}</td></tr>)}
        {!contacts.length&&<tr><td colSpan="6">No emergency contacts have been added.</td></tr>}
      </tbody></table></div>
    </section>
    <section className="hr-panel" aria-labelledby="hr-employment-history-heading">
      <div className="hr-directory-heading"><div><h3 id="hr-employment-history-heading">Previous employment</h3><p>Record prior employers and roles. Submitted history is retained as an immutable record; add a corrected entry rather than overwriting it.</p></div><span className="hr-directory-count">{history.length} records</span></div>
      <form className="hr-form hr-grid" onSubmit={async e=>{e.preventDefault();if(await submit("/hr/employees/"+employee.id+"/employment-history",prior,"Previous employment recorded."))setPrior(blankHistory);}}>
        <label>Previous employer<input maxLength="180" required value={prior.employer_name} onChange={e=>setPrior({...prior,employer_name:e.target.value})}/></label>
        <label>Job title<input maxLength="160" required value={prior.job_title} onChange={e=>setPrior({...prior,job_title:e.target.value})}/></label>
        <label>Employment type<select value={prior.employment_type} onChange={e=>setPrior({...prior,employment_type:e.target.value})}><option value="full_time">Full-time</option><option value="part_time">Part-time</option><option value="contract">Contract</option><option value="intern">Internship</option><option value="self_employed">Self-employed</option><option value="other">Other</option></select></label>
        <label>Location<input maxLength="180" value={prior.location} onChange={e=>setPrior({...prior,location:e.target.value})}/></label>
        <label>Start date<input type="date" required value={prior.start_date} max={prior.end_date||undefined} onChange={e=>setPrior({...prior,start_date:e.target.value})}/></label>
        <label>End date<input type="date" value={prior.end_date} min={prior.start_date||undefined} onChange={e=>setPrior({...prior,end_date:e.target.value})}/></label>
        <label className="hr-span-all">Role summary / notes<textarea maxLength="1000" value={prior.description} onChange={e=>setPrior({...prior,description:e.target.value})}/></label>
        <button type="submit" disabled={busy||!prior.start_date||(prior.end_date&&prior.end_date<prior.start_date)}>Add employment history</button>
      </form>
      <div className="hr-table-wrap"><table><thead><tr><th>Employer</th><th>Role</th><th>Employment type</th><th>Location</th><th>Period</th><th>Notes</th></tr></thead><tbody>
        {history.map(item=><tr key={item.id}><td>{item.employer_name}</td><td>{item.job_title}</td><td>{String(item.employment_type||"").replaceAll("_"," ")}</td><td>{item.location||"—"}</td><td>{String(item.start_date).slice(0,10)} – {item.end_date?String(item.end_date).slice(0,10):"Present"}</td><td>{item.description||"—"}</td></tr>)}
        {!history.length&&<tr><td colSpan="6">No previous employment has been recorded.</td></tr>}
      </tbody></table></div>
    </section>
    <section className="hr-panel" aria-labelledby="hr-employee-record-audit-heading">
      <h3 id="hr-employee-record-audit-heading">Employee record audit</h3>
      <p>Changes to emergency contacts and additions to previous employment are recorded with the acting HR user and timestamp.</p>
      <div className="hr-table-wrap"><table><thead><tr><th>When</th><th>Record</th><th>Event</th><th>Actor user</th><th>Details</th></tr></thead><tbody>
        {events.map(item=><tr key={item.id}><td>{new Date(item.created_at).toLocaleString()}</td><td>{String(item.record_type).replaceAll("_"," ")} #{item.record_id}</td><td>{item.event_type}</td><td>{item.actor_user_id||"System"}</td><td><details><summary>View change</summary><pre>{JSON.stringify({before:item.before_state,after:item.after_state},null,2)}</pre></details></td></tr>)}
        {!events.length&&<tr><td colSpan="5">No employee record changes have been recorded.</td></tr>}
      </tbody></table></div>
    </section>
    {error&&<p className="sb-alert" role="alert">{error}</p>
    {notice&&<p className="sb-success" role="status">{notice}</p>}
  </div>;
}
