import { useEffect, useState } from "react";
import { apiRequest } from "../../services/api.js";
import "./IdentityWorkspace.css";

const PAGE_SIZE = 50;

export default function IdentityWorkspace() {
  const [items, setItems] = useState([]);
  const [total, setTotal] = useState(0);
  const [offset, setOffset] = useState(0);
  const [selected, setSelected] = useState(null);
  const [detail, setDetail] = useState(null);
  const [queue, setQueue] = useState([]);
  const [reconciliation, setReconciliation] = useState([]);
  const [reconciliationBusy, setReconciliationBusy] = useState(false);
  const [search, setSearch] = useState("");
  const [partyType, setPartyType] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [tab, setTab] = useState("register");
  const [proof, setProof] = useState({});
  const [mergeTarget, setMergeTarget] = useState("");
  const [mergeProof, setMergeProof] = useState("document_review");
  const [actionReason, setActionReason] = useState("");
  const [splitProfileId, setSplitProfileId] = useState("");
  const [requestTarget, setRequestTarget] = useState("");
  const [requestProfileType, setRequestProfileType] = useState("customer_account");
  const [requestSourceId, setRequestSourceId] = useState("");
  const [requestReason, setRequestReason] = useState("");
  const [relationshipPerson, setRelationshipPerson] = useState("");
  const [relationshipOrganisation, setRelationshipOrganisation] = useState("");
  const [relationshipType, setRelationshipType] = useState("owner");
  const [relationshipReason, setRelationshipReason] = useState("");
  const [contactVerifyId, setContactVerifyId] = useState("");
  const [contactProofMethod, setContactProofMethod] = useState("document_review");
  const [contactProofReason, setContactProofReason] = useState("");
  const [relationshipRevokeId, setRelationshipRevokeId] = useState("");
  const [relationshipRevokeReason, setRelationshipRevokeReason] = useState("");

  async function loadReconciliation() {
    setReconciliationBusy(true);
    setError("");
    try {
      const result = await apiRequest("/identity/reconciliation/preview?limit=200");
      setReconciliation(result.items || []);
    } catch (e) {
      setError(e.message || "Unable to generate the legacy reconciliation preview.");
    } finally {
      setReconciliationBusy(false);
    }
  }

  async function refresh(nextOffset = offset) {
    setError("");
    try {
      const params = new URLSearchParams({ limit: String(PAGE_SIZE), offset: String(nextOffset) });
      if (search.trim()) params.set("search", search.trim());
      if (partyType) params.set("party_type", partyType);
      const [register, review] = await Promise.all([
        apiRequest(`/identity?${params.toString()}`),
        apiRequest("/identity/review-queue/requests"),
      ]);
      setItems(register.items || []);
      setTotal(register.total || 0);
      setOffset(nextOffset);
      setQueue(review.items || []);
      if (selected && !(register.items || []).some(x => x.id === selected.id)) {
        setSelected(null); setDetail(null);
      }
    } catch (e) { setError(e.message || "Unable to load identity records."); }
  }
  useEffect(() => { refresh(0); }, [search, partyType]);
  async function openParty(item) {
    setSelected(item); setDetail(null); setError("");
    try { setDetail(await apiRequest(`/identity/parties/${item.id}`)); }
    catch (e) { setError(e.message || "Unable to load identity profile."); }
  }
  async function review(id, decision) {
    const p = proof[id] || {};
    if (decision === "approve" && (!p.verified || !p.method)) { setError("Record proof verification and method before approving."); return; }
    const reason = (p.reason || "").trim();
    if (decision === "reject" && reason.length < 5) { setError("Enter a reason of at least five characters before rejecting."); return; }
    setBusy(true); setError("");
    try {
      await apiRequest(`/identity/review-queue/requests/${id}`, { method: "POST", body: JSON.stringify({ decision, proof_verified: !!p.verified, proof_method: p.method || null, reason: reason || "Evidence reviewed and verified by administrator" }) });
      await refresh();
    } catch (e) { setError(e.message || "Unable to review identity request."); }
    finally { setBusy(false); }
  }
  async function submitProfileLink() {
    if (!requestTarget || !/^\d+$/.test(requestSourceId) || requestReason.trim().length < 5) {
      setError("Select a target SBID, enter a numeric source record ID and provide a reason."); return;
    }
    setBusy(true); setError("");
    try {
      await apiRequest("/identity/link-requests", { method: "POST", body: JSON.stringify({
        target_party_id: Number(requestTarget), request_type: "link_profile",
        requested_profile_type: requestProfileType, requested_source_id: requestSourceId.trim(),
        idempotency_key: crypto.randomUUID(), reason: requestReason.trim(),
      }) });
      setRequestTarget(""); setRequestSourceId(""); setRequestReason("");
      setError("Identity-link request submitted to the review queue.");
      setTab("review"); await refresh();
    } catch (e) { setError(e.message || "Unable to submit identity-link request."); }
    finally { setBusy(false); }
  }
  async function submitOrganisationRelationship() {
    if (!relationshipPerson || !relationshipOrganisation || relationshipReason.trim().length < 5) {
      setError("Select an individual and organisation, then provide the evidence reason.");
      return;
    }
    if (relationshipPerson === relationshipOrganisation) {
      setError("The individual and organisation identities must be different.");
      return;
    }
    setBusy(true); setError("");
    try {
      await apiRequest("/identity/link-requests", {
        method: "POST",
        body: JSON.stringify({
          target_party_id: Number(relationshipOrganisation),
          requester_party_id: Number(relationshipPerson),
          request_type: "organisation_relationship",
          relationship_type: relationshipType,
          relationship_scope: {},
          idempotency_key: crypto.randomUUID(),
          reason: relationshipReason.trim(),
        }),
      });
      setRelationshipPerson(""); setRelationshipOrganisation(""); setRelationshipReason("");
      setError("Organisation relationship submitted for evidence review.");
      setTab("review"); await refresh();
    } catch (e) { setError(e.message || "Unable to submit organisation relationship."); }
    finally { setBusy(false); }
  }
  async function revokeSelectedRelationship() {
    if (!relationshipRevokeId || relationshipRevokeReason.trim().length < 5) {
      setError("Select an active relationship and provide the revocation reason.");
      return;
    }
    if (!window.confirm("Revoke this organisation relationship? Its audit history will be retained.")) return;
    setBusy(true); setError("");
    try {
      await apiRequest(`/identity/relationships/${relationshipRevokeId}/revoke`, {
        method: "POST",
        body: JSON.stringify({ reason: relationshipRevokeReason.trim() }),
      });
      const refreshed = await apiRequest(`/identity/parties/${selected.id}`);
      setDetail(refreshed);
      setRelationshipRevokeId(""); setRelationshipRevokeReason("");
      setError("Organisation relationship revoked and recorded in the audit trail.");
    } catch (e) { setError(e.message || "Unable to revoke this organisation relationship."); }
    finally { setBusy(false); }
  }
  async function verifySelectedContact() {
    if (!contactVerifyId || contactProofReason.trim().length < 5) {
      setError("Select a current contact and provide the evidence reviewed.");
      return;
    }
    setBusy(true); setError("");
    try {
      await apiRequest(`/identity/contacts/${contactVerifyId}/verify`, {
        method: "POST",
        body: JSON.stringify({ proof_method: contactProofMethod, reason: contactProofReason.trim() }),
      });
      const refreshed = await apiRequest(`/identity/parties/${selected.id}`);
      setDetail(refreshed);
      setContactVerifyId(""); setContactProofReason("");
      setError("Contact verification recorded with an audit event.");
    } catch (e) { setError(e.message || "Unable to verify this contact."); }
    finally { setBusy(false); }
  }
  async function mergeSelected() {
    if (!selected || !mergeTarget || !actionReason.trim()) { setError("Select a target SBID and enter the documented reason."); return; }
    const target = items.find(item => item.sbid.toUpperCase() === mergeTarget.trim().toUpperCase());
    if (!target) { setError("Target SBID must be selected from the current filtered page."); return; }
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
  return <section className="identity-workspace">
    <header className="identity-head"><div><span>MASTER DATA · ACCESS GOVERNANCE</span><h1>Unified Identity Register</h1><p>Permanent SBIDs, linked business profiles, relationships and controlled identity review.</p></div><button onClick={() => refresh(0)}>Refresh</button></header>
    <nav className="identity-tabs"><button className={tab==="register"?"active":""} onClick={()=>setTab("register")}>Identity register</button><button className={tab==="review"?"active":""} onClick={()=>setTab("review")}>Review queue <b>{queue.length}</b></button><button className={tab==="reconciliation"?"active":""} onClick={()=>{setTab("reconciliation");loadReconciliation();}}>Legacy reconciliation</button></nav>
    {error && <p className={(error.startsWith("Identity-link request submitted") || error.startsWith("Organisation relationship submitted") || (error.startsWith("Contact verification recorded") || error.startsWith("Organisation relationship revoked"))) ? "" : "identity-error"} role="status">{error}</p>}
    {tab === "register" ? <>
      <div className="identity-list">
        <div className="identity-filters">
          <input value={search} onChange={e=>setSearch(e.target.value)} placeholder="Search SBID or name" aria-label="Search identities" />
          <select value={partyType} onChange={e=>setPartyType(e.target.value)} aria-label="Filter identity type"><option value="">All identity types</option><option value="individual">Individual</option><option value="organisation">Organisation</option></select>
        </div>
        <div className="identity-table-wrap"><table><thead><tr><th>SBID</th><th>Identity</th><th>Type</th><th>Profiles</th><th/></tr></thead><tbody>{items.map(item=><tr key={item.id} className={selected?.id===item.id?"selected":""}><td>{item.sbid}</td><td>{item.display_name}</td><td>{item.party_type}</td><td>{item.profiles?.length || 0}</td><td><button onClick={()=>openParty(item)}>View</button></td></tr>)}{!items.length&&<tr><td colSpan="5">No identities found.</td></tr>}</tbody></table></div>
        <div className="identity-pagination"><span>{total ? `${offset+1}–${Math.min(offset+items.length,total)} of ${total}` : "0 identities"}</span><button disabled={offset===0} onClick={()=>refresh(Math.max(0,offset-PAGE_SIZE))}>Previous</button><button disabled={offset+PAGE_SIZE>=total} onClick={()=>refresh(offset+PAGE_SIZE)}>Next</button></div>
      </div>
      <div className="identity-link-request">
        <h3>Request a verified profile link</h3>
        <p>Requests remain pending until an authorised reviewer verifies the evidence.</p>
        <label>Target SBID<select value={requestTarget} onChange={e=>setRequestTarget(e.target.value)}><option value="">Select identity</option>{items.map(item=><option key={item.id} value={item.id}>{item.sbid} · {item.display_name}</option>)}</select></label>
        <label>Profile type<select value={requestProfileType} onChange={e=>setRequestProfileType(e.target.value)}><option value="customer_account">Customer account</option><option value="crm_customer">CRM customer</option><option value="employee">Employee</option><option value="vendor_organisation">Vendor organisation</option></select></label>
        <label>Existing record ID<input inputMode="numeric" value={requestSourceId} onChange={e=>setRequestSourceId(e.target.value)} placeholder="Numeric source record ID" /></label>
        <label>Reason<input value={requestReason} onChange={e=>setRequestReason(e.target.value)} minLength={5} maxLength={500} placeholder="Why should this record be linked?" /></label>
        <button disabled={busy || !requestTarget || !/^\d+$/.test(requestSourceId) || requestReason.trim().length<5} onClick={submitProfileLink}>Submit for review</button>
      </div>
      <div className="identity-link-request">
        <h3>Request an organisation relationship</h3>
        <p>Link an identified individual to an organisation as an owner, director, representative or authorised vendor user. Every request requires evidence review.</p>
        <label>Individual identity<select value={relationshipPerson} onChange={e=>setRelationshipPerson(e.target.value)}><option value="">Select individual</option>{items.filter(item=>item.party_type==="individual").map(item=><option key={item.id} value={item.id}>{item.sbid} · {item.display_name}</option>)}</select></label>
        <label>Organisation identity<select value={relationshipOrganisation} onChange={e=>setRelationshipOrganisation(e.target.value)}><option value="">Select organisation</option>{items.filter(item=>item.party_type==="organisation").map(item=><option key={item.id} value={item.id}>{item.sbid} · {item.display_name}</option>)}</select></label>
        <label>Relationship type<select value={relationshipType} onChange={e=>setRelationshipType(e.target.value)}><option value="owner">Owner</option><option value="director">Director</option><option value="representative">Representative</option><option value="authorised_vendor_user">Authorised vendor user</option></select></label>
        <label>Evidence / reason<input value={relationshipReason} onChange={e=>setRelationshipReason(e.target.value)} minLength={5} maxLength={500} placeholder="Describe the documents or authorisation reviewed" /></label>
        <button disabled={busy || !relationshipPerson || !relationshipOrganisation || relationshipReason.trim().length<5} onClick={submitOrganisationRelationship}>Submit relationship for review</button>
      </div>
      <div className="identity-layout"><aside className="identity-detail">{!detail ? <p>Select an identity to inspect its linked profiles and relationships.</p> : <><span className="identity-eyebrow">IDENTITY PROFILE</span><h2>{detail.party.sbid}</h2><h3>{detail.party.display_name}</h3><p>{detail.party.party_type} · {detail.party.status}</p><h4>Business profiles</h4>{detail.profiles.map(p=><p key={p.id}>{p.profile_type} · #{p.customer_account_id || p.crm_customer_id || p.employee_id || p.supplier_id} · {p.status}</p>)}<h4>Verified / unverified contacts</h4>{detail.contacts.map(c=><p key={c.id}>{c.contact_type}: {c.masked_value} · {c.verification_status}</p>)}{detail.contacts.some(c=>c.verification_status!=="verified") && <div className="identity-link-request"><h5>Verify a contact after evidence review</h5><label>Current contact<select value={contactVerifyId} onChange={e=>setContactVerifyId(e.target.value)}><option value="">Select contact</option>{detail.contacts.filter(c=>c.verification_status!=="verified").map(c=><option key={c.id} value={c.id}>{c.contact_type} · {c.masked_value} · {c.verification_status}</option>)}</select></label><label>Evidence method<select value={contactProofMethod} onChange={e=>setContactProofMethod(e.target.value)}><option value="document_review">Document review</option><option value="in_person">In person</option><option value="verified_account">Verified account evidence</option><option value="business_registry">Business registry</option></select></label><label>Review reason<input value={contactProofReason} onChange={e=>setContactProofReason(e.target.value)} minLength={5} maxLength={500} placeholder="Describe the evidence reviewed" /></label><button disabled={busy || !contactVerifyId || contactProofReason.trim().length<5} onClick={verifySelectedContact}>Record contact verification</button></div>}<h4>Login accounts</h4>{detail.auth_accounts.map(a=><p key={a.id}>{a.account_type} · {a.status} · {a.link_method}</p>)}<h4>Loyalty cards</h4>{detail.loyalty_accounts.map(a=><p key={a.id}>{a.masked_card_number} · {a.link_method}</p>)}<h4>Referrals</h4>{detail.referrals.map(r=><p key={r.id}>{r.referrer_sbid} → {r.referred_sbid} · referral #{r.referral_id}</p>)}<h4>Relationships</h4>{detail.relationships.map(r=><p key={r.id}>{r.from_sbid} → {r.to_sbid} · {r.relationship_type} · {r.status}</p>)}{detail.relationships.some(r=>r.status==="active") && <div className="identity-link-request"><h5>Revoke organisation authority</h5><label>Active relationship<select value={relationshipRevokeId} onChange={e=>setRelationshipRevokeId(e.target.value)}><option value="">Select relationship</option>{detail.relationships.filter(r=>r.status==="active").map(r=><option key={r.id} value={r.id}>{r.relationship_type} · {r.from_sbid} → {r.to_sbid}</option>)}</select></label><label>Reason<input value={relationshipRevokeReason} onChange={e=>setRelationshipRevokeReason(e.target.value)} minLength={5} maxLength={500} placeholder="Why is this authority being withdrawn?" /></label><button disabled={busy || !relationshipRevokeId || relationshipRevokeReason.trim().length<5} onClick={revokeSelectedRelationship}>Revoke relationship</button></div>}<h4>Controlled identity actions</h4><label>Merge into canonical SBID<input value={mergeTarget} onChange={e=>setMergeTarget(e.target.value)} placeholder="Target SBID from current page" /></label><label>Proof method<select value={mergeProof} onChange={e=>setMergeProof(e.target.value)}><option value="document_review">Document review</option><option value="in_person">In person</option><option value="verified_account">Verified account evidence</option></select></label><label>Reason<input value={actionReason} onChange={e=>setActionReason(e.target.value)} minLength={5} maxLength={500} placeholder="Document evidence and business reason" /></label><button disabled={busy || !mergeTarget || actionReason.trim().length<5} onClick={mergeSelected}>Merge identities</button><label>Split profile into a new SBID<select value={splitProfileId} onChange={e=>setSplitProfileId(e.target.value)}><option value="">Select profile</option>{detail.profiles.filter(p=>p.status==="active").map(p=><option key={p.id} value={p.id}>{p.profile_type} · #{p.customer_account_id || p.crm_customer_id || p.employee_id || p.supplier_id}</option>)}</select></label><button disabled={busy || !splitProfileId || actionReason.trim().length<5} onClick={splitSelectedProfile}>Split selected profile</button><h4>Audit trail</h4>{detail.events.map(e=><p key={e.id}>{e.event_type} · {new Date(e.created_at).toLocaleString("en-IN")}{e.reason ? " · " + e.reason : ""}{e.event_data?.proof_method ? " · " + e.event_data.proof_method : ""}</p>)}</>}</aside></div>
    </> : tab === "review" ? <div className="identity-review">{queue.map(item=><article key={item.id}><div><strong>Request #{item.id} · {item.request_type}</strong><p>{item.requester_sbid || "Admin initiated"} → {item.target_sbid || item.requested_sbid || "Unresolved SBID"} · {item.status}</p><small>{item.reason || "No additional reason supplied"}</small>{item.request_type === "claim_existing_identity" && !item.target_sbid && <small role="note">The requested SBID did not resolve to an existing identity. Approval is disabled until a valid target can be reviewed.</small>}</div><label><input type="checkbox" checked={!!proof[item.id]?.verified} onChange={e=>setProof(old=>({...old,[item.id]:{...old[item.id],verified:e.target.checked}}))}/> Evidence verified</label><select value={proof[item.id]?.method || ""} onChange={e=>setProof(old=>({...old,[item.id]:{...old[item.id],method:e.target.value}}))}><option value="">Proof method</option><option value="email_otp">Email OTP</option><option value="phone_otp">Phone OTP</option><option value="in_person">In person</option><option value="document_review">Document review</option></select><input value={proof[item.id]?.reason || ""} onChange={e=>setProof(old=>({...old,[item.id]:{...old[item.id],reason:e.target.value}}))} placeholder="Review reason (required to reject)" /><button disabled={busy || (item.request_type === "claim_existing_identity" && !item.target_sbid)} onClick={()=>review(item.id,"approve")}>Approve</button><button disabled={busy} className="identity-reject" onClick={()=>review(item.id,"reject")}>Reject</button></article>)}{!queue.length&&<p>No pending identity reviews.</p>}</div> : <div className="identity-reconciliation">
      <div><h2>Legacy record reconciliation</h2><p>Read-only exact-contact candidate scan across customer accounts, CRM customers, employees and supplier organisations. A match is not proof of shared identity.</p><button disabled={reconciliationBusy} onClick={loadReconciliation}>{reconciliationBusy ? "Scanning…" : "Refresh candidate report"}</button></div>
      {reconciliationBusy ? <p>Scanning legacy records…</p> : reconciliation.length ? <div className="identity-review">{reconciliation.map((candidate,index)=><article key={candidate.contact_type+"-"+candidate.masked_contact+"-"+index}><div><strong>{candidate.contact_type.toUpperCase()} · {candidate.masked_contact}</strong><p>{candidate.match_count} records across {candidate.profile_type_count} profile types · Manual review required</p><small>{candidate.review_note}</small><ul>{(candidate.records||[]).map(record=><li key={record.profile_type+"-"+record.source_id}>{record.profile_type} #{record.source_id}{record.sbid ? " · "+record.sbid : " · No SBID link"}{record.profile_status ? " · "+record.profile_status : ""}</li>)}</ul></div></article>)}</div> : <p>No exact-contact candidate groups were found in the scanned records.</p>}
      <p className="identity-reconciliation-safety">This report does not create identities, link profiles, change contact verification, or merge records. Every candidate requires evidence and an authorised review.</p>
    </div>}
  </section>;
}
