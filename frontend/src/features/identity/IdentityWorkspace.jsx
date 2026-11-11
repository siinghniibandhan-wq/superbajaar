import { useEffect, useState } from "react";
import { apiRequest } from "../../services/api.js";
import "./IdentityWorkspace.css";

export default function IdentityWorkspace() {
  const [items, setItems] = useState([]);
  const [selected, setSelected] = useState(null);
  const [detail, setDetail] = useState(null);
  const [queue, setQueue] = useState([]);
  const [search, setSearch] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [tab, setTab] = useState("register");
  const [proof, setProof] = useState({});
  const [mergeTarget, setMergeTarget] = useState("");
  const [mergeProof, setMergeProof] = useState("document_review");
  const [actionReason, setActionReason] = useState("");
  const [splitProfileId, setSplitProfileId] = useState("");

  async function refresh() {
    setError("");
    try {
      const [register, review] = await Promise.all([
        apiRequest("/identity?limit=100"),
        apiRequest("/identity/review-queue/requests"),
      ]);
      setItems(register.items || []);
      setQueue(review.items || []);
    } catch (e) { setError(e.message || "Unable to load identity records."); }
  }
  useEffect(() => { refresh(); }, []);
  async function openParty(item) {
    setSelected(item); setDetail(null); setError("");
    try { setDetail(await apiRequest(`/identity/parties/${item.id}`)); }
    catch (e) { setError(e.message || "Unable to load identity profile."); }
  }
  async function review(id, decision) {
    const p = proof[id] || {};
    if (decision === "approve" && (!p.verified || !p.method)) { setError("Record proof verification and method before approving."); return; }
    setBusy(true); setError("");
    try {
      await apiRequest(`/identity/review-queue/requests/${id}`, { method: "POST", body: JSON.stringify({ decision, proof_verified: !!p.verified, proof_method: p.method || null, reason: p.reason || (decision === "approve" ? "Evidence reviewed and verified by administrator" : "Request rejected after review") }) });
      await refresh();
    } catch (e) { setError(e.message || "Unable to review identity request."); }
    finally { setBusy(false); }
  }
  async function mergeSelected() {
    if (!selected || !mergeTarget || !actionReason.trim()) { setError("Select a target SBID and enter the documented reason."); return; }
    const target = items.find(item => item.sbid.toUpperCase() === mergeTarget.trim().toUpperCase());
    if (!target) { setError("Target SBID must be selected from the loaded identity register."); return; }
    if (target.id === selected.id) { setError("Source and target identities must differ."); return; }
    if (!window.confirm("Merge this identity into the selected canonical identity? The source SBID will remain as an alias.")) return;
    setBusy(true); setError("");
    try {
      await apiRequest(`/identity/parties/${selected.id}/merge`, { method: "POST", body: JSON.stringify({ target_party_id: target.id, proof_verified: true, proof_method: mergeProof, reason: actionReason.trim() }) });
      setMergeTarget(""); setActionReason(""); await refresh(); await openParty(target);
    } catch (e) { setError(e.message || "Identity merge was not completed."); }
    finally { setBusy(false); }
  }
  async function splitSelectedProfile() {
    if (!selected || !splitProfileId || !actionReason.trim()) { setError("Select a profile and enter the reason for splitting it."); return; }
    if (!window.confirm("Create a new SBID and move this profile to it?")) return;
    setBusy(true); setError("");
    try {
      await apiRequest(`/identity/parties/${selected.id}/split-profile`, { method: "POST", body: JSON.stringify({ profile_id: Number(splitProfileId), reason: actionReason.trim() }) });
      setSplitProfileId(""); setActionReason(""); await refresh(); await openParty(selected);
    } catch (e) { setError(e.message || "Profile split was not completed."); }
    finally { setBusy(false); }
  }
  const visible = items.filter(x => !search || x.sbid.toLowerCase().includes(search.toLowerCase()) || x.display_name.toLowerCase().includes(search.toLowerCase()));
  return <section className="identity-workspace">
    <header className="identity-head"><div><span>MASTER DATA · ACCESS GOVERNANCE</span><h1>Unified Identity Register</h1><p>Permanent SBIDs, linked business profiles, relationships and controlled identity review.</p></div><button onClick={refresh}>Refresh</button></header>
    <nav className="identity-tabs"><button className={tab==="register"?"active":""} onClick={()=>setTab("register")}>Identity register</button><button className={tab==="review"?"active":""} onClick={()=>setTab("review")}>Review queue <b>{queue.length}</b></button></nav>
    {error && <p className="identity-error" role="alert">{error}</p>}
    {tab === "register" ? <div className="identity-layout"><div className="identity-list"><input value={search} onChange={e=>setSearch(e.target.value)} placeholder="Search SBID or name" aria-label="Search identities" /><div className="identity-table-wrap"><table><thead><tr><th>SBID</th><th>Identity</th><th>Type</th><th>Profiles</th><th/></tr></thead><tbody>{visible.map(item=><tr key={item.id} className={selected?.id===item.id?"selected":""}><td>{item.sbid}</td><td>{item.display_name}</td><td>{item.party_type}</td><td>{item.profiles?.length || 0}</td><td><button onClick={()=>openParty(item)}>View</button></td></tr>)}{!visible.length&&<tr><td colSpan="5">No identities found.</td></tr>}</tbody></table></div></div>
    <aside className="identity-detail">{!detail ? <p>Select an identity to inspect its linked profiles and relationships.</p> : <><span className="identity-eyebrow">IDENTITY PROFILE</span><h2>{detail.party.sbid}</h2><h3>{detail.party.display_name}</h3><p>{detail.party.party_type} · {detail.party.status}</p><h4>Business profiles</h4>{detail.profiles.map(p=><p key={p.id}>{p.profile_type} · #{p.customer_account_id || p.crm_customer_id || p.employee_id || p.supplier_id} · {p.status}</p>)}<h4>Verified / unverified contacts</h4>{detail.contacts.map(c=><p key={c.id}>{c.contact_type}: {c.masked_value} · {c.verification_status}</p>)}<h4>Login accounts</h4>{detail.auth_accounts.map(a=><p key={a.id}>{a.account_type} · {a.status} · {a.link_method}</p>)}<h4>Loyalty cards</h4>{detail.loyalty_accounts.map(a=><p key={a.id}>{a.masked_card_number} · {a.link_method}</p>)}<h4>Referrals</h4>{detail.referrals.map(r=><p key={r.id}>{r.referrer_sbid} → {r.referred_sbid} · referral #{r.referral_id}</p>)}<h4>Relationships</h4>{detail.relationships.map(r=><p key={r.id}>{r.from_sbid} → {r.to_sbid} · {r.relationship_type} · {r.status}</p>)}<h4>Controlled identity actions</h4><label>Merge into canonical SBID<input value={mergeTarget} onChange={e=>setMergeTarget(e.target.value)} placeholder="Target SBID from register" /></label><label>Proof method<select value={mergeProof} onChange={e=>setMergeProof(e.target.value)}><option value="document_review">Document review</option><option value="in_person">In person</option><option value="verified_account">Verified account evidence</option></select></label><label>Reason<input value={actionReason} onChange={e=>setActionReason(e.target.value)} minLength={5} maxLength={500} placeholder="Document evidence and business reason" /></label><button disabled={busy || !mergeTarget || actionReason.trim().length<5} onClick={mergeSelected}>Merge identities</button><label>Split profile into a new SBID<select value={splitProfileId} onChange={e=>setSplitProfileId(e.target.value)}><option value="">Select profile</option>{detail.profiles.filter(p=>p.status==="active").map(p=><option key={p.id} value={p.id}>{p.profile_type} · #{p.customer_account_id || p.crm_customer_id || p.employee_id || p.supplier_id}</option>)}</select></label><button disabled={busy || !splitProfileId || actionReason.trim().length<5} onClick={splitSelectedProfile}>Split selected profile</button><h4>Audit trail</h4>{detail.events.map(e=><p key={e.id}>{e.event_type} · {new Date(e.created_at).toLocaleString("en-IN")}</p>)}</>}</aside></div> : <div className="identity-review">{queue.map(item=><article key={item.id}><div><strong>Request #{item.id} · {item.request_type}</strong><p>{item.requester_sbid || "Admin initiated"} → {item.target_sbid || "Target identity"} · {item.status}</p><small>{item.reason || "No additional reason supplied"}</small></div><label><input type="checkbox" checked={!!proof[item.id]?.verified} onChange={e=>setProof(old=>({...old,[item.id]:{...old[item.id],verified:e.target.checked}}))}/> Evidence verified</label><select value={proof[item.id]?.method || ""} onChange={e=>setProof(old=>({...old,[item.id]:{...old[item.id],method:e.target.value}}))}><option value="">Proof method</option><option value="email_otp">Email OTP</option><option value="phone_otp">Phone OTP</option><option value="in_person">In person</option><option value="document_review">Document review</option></select><button disabled={busy} onClick={()=>review(item.id,"approve")}>Approve</button><button disabled={busy} className="identity-reject" onClick={()=>review(item.id,"reject")}>Reject</button></article>)}{!queue.length&&<p>No pending identity reviews.</p>}</div>}
  </section>;
}
