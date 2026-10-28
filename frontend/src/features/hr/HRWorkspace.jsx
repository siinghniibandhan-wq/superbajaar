import {useCallback,useEffect,useState} from "react";
import {apiRequest} from "../../services/api.js";
export default function HRWorkspace({onBack,currentUser}){
 const [users,setUsers]=useState([]),[loading,setLoading]=useState(true),[error,setError]=useState(""),[notice,setNotice]=useState("");
 const load=useCallback(async()=>{setLoading(true);setError("");try{const r=await apiRequest("/auth/users");setUsers(r.items||[]);}catch(e){setError(e.message||"Unable to load staff accounts.");}finally{setLoading(false);}},[]);
 useEffect(()=>{load();},[load]);
 const canManage=["owner","admin"].includes(currentUser?.role);
 async function update(id,body){setError("");setNotice("");try{await apiRequest("/auth/users/"+id,{method:"PATCH",body:JSON.stringify(body)});setNotice("Staff access updated.");await load();}catch(e){setError(e.message||"Unable to update staff access.");}}
 return <section className="sb-workspace"><button className="sb-back" onClick={onBack} type="button">← All workspaces</button><p className="sb-eyebrow">PEOPLE · ACCESS</p><h1>HR & Payroll</h1><p>Staff account directory and access status from the existing access-control API.</p>
 {error&&<p className="sb-alert" role="alert">{error}</p>}{notice&&<p className="sb-success" role="status">{notice}</p>}
 <div className="sb-data-heading"><h2>Staff directory</h2><button type="button" onClick={load} disabled={loading}>Refresh</button></div>
 {loading?<p className="sb-empty">Loading staff accounts…</p>:<div className="sb-table-wrap"><table><thead><tr><th>Name</th><th>Email</th><th>Role</th><th>Access</th><th>Action</th></tr></thead><tbody>{users.map(u=><tr key={u.id}><td>{u.full_name}</td><td>{u.email}</td><td>{u.role}</td><td>{u.is_active?"Active":"Inactive"}</td><td>{canManage&&u.id!==currentUser?.id&&u.role!=="owner"?<div className="sb-access-actions"><select aria-label={"Role for "+u.email} defaultValue={u.role} onChange={e=>update(u.id,{role:e.target.value})}><option value="manager">Manager</option><option value="staff">Staff</option><option value="viewer">Viewer</option>{currentUser?.role==="owner"&&<option value="admin">Admin</option>}</select><button type="button" onClick={()=>update(u.id,{is_active:!u.is_active})}>{u.is_active?"Deactivate":"Activate"}</button></div>:<span>—</span>}</td></tr>)}</tbody></table>{!users.length&&<p className="sb-empty">No staff accounts returned.</p>}</div>}
 <div className="sb-notice"><strong>Attendance and payroll are not enabled</strong><span>The existing database does not provide employee records, attendance, salary structures, payslips, or payroll processing. This module only manages application staff accounts and does not claim to run payroll.</span></div></section>;
}
