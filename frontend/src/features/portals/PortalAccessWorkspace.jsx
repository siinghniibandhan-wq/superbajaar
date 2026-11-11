import { useEffect, useState } from "react";
import { apiRequest } from "../../services/api.js";
import "./PortalAccessWorkspace.css";

export default function PortalAccessWorkspace() {
  const [type, setType] = useState("vendor");
  const [records, setRecords] = useState([]);
  const [invitations, setInvitations] = useState([]);
  const [recordId, setRecordId] = useState("");
  const [representativeName, setRepresentativeName] = useState("");
  const [latestLink, setLatestLink] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");

  async function refresh() {
    setError("");
    try {
      const [eligible, history] = await Promise.all([
        apiRequest(`/portal-invitations/eligible-records?portal_type=${type}`),
        apiRequest("/portal-invitations"),
      ]);
      setRecords(eligible.items || []);
      setInvitations(history.items || []);
      setRecordId("");
    } catch (reason) { setError(reason.message || "Unable to load portal access records."); }
  }
  useEffect(() => { refresh(); }, [type]);

  async function invite(event) {
    event.preventDefault(); setBusy(true); setError(""); setNotice(""); setLatestLink("");
    try {
      const result = await apiRequest("/portal-invitations", {
        method: "POST",
        body: JSON.stringify({ portal_type: type, record_id: Number(recordId), ...(type === "vendor" ? { representative_name: representativeName.trim() } : {}) }),
      });
      setLatestLink(result.invitation_url || "");
      setNotice(result.delivery_status === "sent"
        ? `Invitation email sent to ${result.email}.`
        : `Invitation created for ${result.email}. Email is not configured; copy and share the activation link securely.`);
      await refresh();
    } catch (reason) { setError(reason.message || "Invitation could not be created."); }
    finally { setBusy(false); }
  }

  async function revoke(id) {
    setBusy(true); setError(""); setNotice("");
    try { await apiRequest(`/portal-invitations/${id}/revoke`, { method: "POST" }); setNotice("Invitation revoked."); await refresh(); }
    catch (reason) { setError(reason.message || "Unable to revoke invitation."); }
    finally { setBusy(false); }
  }

  const copy = async () => {
    try { await navigator.clipboard.writeText(latestLink); setNotice("Activation link copied. Share it only with the invited recipient."); }
    catch { setError("Clipboard access was unavailable. Select and copy the activation link manually."); }
  };
  return <section className="portal-admin">
    <header className="portal-admin-head"><div><span>ACCESS MANAGEMENT</span><h1>Vendor & employee portals</h1><p>Create secure, invitation-only access and manage outstanding invitations.</p></div><div className="portal-admin-mark">S</div></header>
    <div className="portal-admin-grid">
      <article className="portal-admin-card">
        <div className="portal-admin-card-head"><div><h2>Invite a portal user</h2><p>Choose an existing supplier or employee record. No duplicate master records are created.</p></div></div>
        <div className="portal-admin-switch"><button className={type==="vendor"?"active":""} onClick={()=>setType("vendor")}>Vendor</button><button className={type==="employee"?"active":""} onClick={()=>setType("employee")}>Employee</button></div>
        <form onSubmit={invite} className="portal-admin-form">
          <label>{type==="vendor"?"Supplier":"Employee"} record<select value={recordId} onChange={event=>setRecordId(event.target.value)} required><option value="">Select an eligible {type}</option>{records.map(record=><option key={record.id} value={record.id}>{record.display_name} · {record.email}</option>)}</select></label>
          {type === "vendor" && <label>Authorised representative full name<input value={representativeName} onChange={event => setRepresentativeName(event.target.value)} minLength={2} maxLength={200} required placeholder="Person who will activate the vendor portal" /></label>}
          {!records.length && <p className="portal-admin-hint">No eligible records found. Add an active {type} with a valid email in the existing {type==="vendor"?"Purchasing":"HR"} workspace first.</p>}
          <button className="portal-admin-primary" type="submit" disabled={busy || !recordId || (type === "vendor" && representativeName.trim().length < 2)}>{busy?"Creating invitation…":"Create invitation"}</button>
        </form>
        {latestLink && <div className="portal-invite-link"><strong>One-time activation link</strong><div><input readOnly value={latestLink} aria-label="Activation link"/><button onClick={copy}>Copy link</button></div><small>Valid for 48 hours. This is the only time the raw invitation link is displayed.</small></div>}
      </article>
      <article className="portal-admin-card portal-admin-security"><span className="portal-admin-shield">✓</span><h2>Access stays controlled</h2><ul><li>Invitations expire after 48 hours and can be used once.</li><li>Vendor accounts are linked to one supplier record.</li><li>Employee accounts are linked to existing HR employee records.</li><li>Revoked invitations cannot be activated.</li><li>Portal APIs verify record ownership on the server.</li></ul></article>
    </div>
    {error && <p className="portal-admin-alert" role="alert">{error}</p>}
    {notice && <p className="portal-admin-notice" role="status">{notice}</p>}
    <article className="portal-admin-card portal-admin-history"><div className="portal-admin-card-head"><div><h2>Invitation activity</h2><p>Recent invitations across both portals.</p></div><button onClick={refresh}>Refresh</button></div>
      <div className="portal-admin-table-wrap"><table><thead><tr><th>Portal</th><th>Email</th><th>Created</th><th>Expires</th><th>Status</th><th/></tr></thead><tbody>
      {invitations.map(item=>{const status=item.accepted_at?"Activated":item.revoked_at?"Revoked":new Date(item.expires_at)<=new Date()?"Expired":"Pending";return <tr key={item.id}><td><span className={`portal-admin-pill ${item.portal_type}`}>{item.portal_type}</span></td><td>{item.email}</td><td>{new Date(item.created_at).toLocaleDateString("en-IN")}</td><td>{new Date(item.expires_at).toLocaleDateString("en-IN")}</td><td>{status}</td><td>{status==="Pending"&&<button className="portal-admin-revoke" disabled={busy} onClick={()=>revoke(item.id)}>Revoke</button>}</td></tr>;})}
      {!invitations.length&&<tr><td colSpan="6" className="portal-admin-empty">No invitations have been created yet.</td></tr>}
      </tbody></table></div>
    </article>
  </section>;
}
