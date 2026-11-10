import { useEffect, useMemo, useState } from "react";
import { apiRequest } from "../../services/api.js";

const emptyConfig = domain => domain === "purchase" ? { approval_bands: [] } : { event_policies: {} };

export default function OrganisationPolicyPanel({ domain }) {
  const [establishments, setEstablishments] = useState([]);
  const [policies, setPolicies] = useState([]);
  const [establishmentId, setEstablishmentId] = useState("");
  const [versionLabel, setVersionLabel] = useState("");
  const [effectiveFrom, setEffectiveFrom] = useState(new Date().toISOString().slice(0, 10));
  const [configText, setConfigText] = useState(JSON.stringify(emptyConfig(domain), null, 2));
  const [selectedPolicyId, setSelectedPolicyId] = useState("");
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [busy, setBusy] = useState(false);
  const [history, setHistory] = useState({ audit_events: [], decisions: [] });

  const selected = useMemo(() => policies.find(item => String(item.id) === String(selectedPolicyId)), [policies, selectedPolicyId]);

  async function load() {
    const [e, p] = await Promise.all([apiRequest("/hr/establishments"), apiRequest("/organisation-policies?domain=" + domain)]);
    setEstablishments(e.items || []);
    setPolicies(p.items || []);
    if (!establishmentId && e.items?.length) setEstablishmentId(String(e.items[0].id));
  }

  useEffect(() => {
    load().catch(e => setError(e.message || "Unable to load organisation policy settings."));
  }, [domain]);

  useEffect(() => {
    if (!selectedPolicyId) { setHistory({ audit_events: [], decisions: [] }); return; }
    let cancelled = false;
    apiRequest("/organisation-policies/" + selectedPolicyId + "/history")
      .then(result => { if (!cancelled) setHistory({ audit_events: result.audit_events || [], decisions: result.decisions || [] }); })
      .catch(e => { if (!cancelled) setError(e.message || "Unable to load policy audit history."); });
    return () => { cancelled = true; };
  }, [selectedPolicyId]);

  async function saveDraft(event) {
    event.preventDefault(); setBusy(true); setError(""); setNotice("");
    try {
      const policyConfig = JSON.parse(configText);
      const result = await apiRequest("/organisation-policies", { method: "POST", body: JSON.stringify({
        establishment_id: Number(establishmentId), domain, version_label: versionLabel,
        effective_from: effectiveFrom, policy_config: policyConfig,
      }) });
      setSelectedPolicyId(String(result.id));
      setNotice("Draft policy saved. Validate it before activation.");
      setVersionLabel("");
      await load();
    } catch (e) {
      setError(e instanceof SyntaxError ? "Policy configuration must be valid JSON." : (e.message || "Unable to save policy."));
    } finally { setBusy(false); }
  }

  async function validate() {
    if (!selectedPolicyId) return;
    setBusy(true); setError(""); setNotice("");
    try {
      const result = await apiRequest("/organisation-policies/" + selectedPolicyId + "/validate", { method: "POST" });
      setNotice(result.message || "Policy validation passed.");
    } catch (e) { setError(e.message || "Policy validation failed."); }
    finally { setBusy(false); }
  }

  async function activate() {
    if (!selectedPolicyId) return;
    setBusy(true); setError(""); setNotice("");
    try {
      await apiRequest("/organisation-policies/" + selectedPolicyId + "/activate", { method: "POST" });
      setNotice("Policy activated for this establishment and domain.");
      await load();
    } catch (e) { setError(e.message || "Unable to activate policy."); }
    finally { setBusy(false); }
  }

  function loadSelected() {
    if (!selected) return;
    setEstablishmentId(String(selected.establishment_id));
    setVersionLabel(selected.version_label + " (copy)");
    setEffectiveFrom(new Date().toISOString().slice(0, 10));
    setConfigText(JSON.stringify(selected.policy_config, null, 2));
  }

  return (
    <section className="sb-form" aria-label={domain + " organisation policy"}>
      <p className="sb-eyebrow">ORGANISATION CONTROLS</p>
      <h2>{domain === "purchase" ? "Purchase approval policy" : "Inventory control policy"}</h2>
      <p className="sb-muted">Policy values are stored against a legal establishment. No approval bands, authority rules or shelf-life values are assumed by the application.</p>
      {error && <p className="sb-alert" role="alert">{error}</p>}
      {notice && <p className="sb-success" role="status">{notice}</p>}
      <div className="sb-form-grid">
        <label>Legal establishment
          <select value={establishmentId} onChange={e=>setEstablishmentId(e.target.value)}>
            <option value="">Choose establishment</option>
            {establishments.map(item=><option key={item.id} value={item.id}>{item.display_name} ({item.code})</option>)}
          </select>
        </label>
        <label>Existing policy version
          <select value={selectedPolicyId} onChange={e=>setSelectedPolicyId(e.target.value)}>
            <option value="">Choose draft to validate / activate</option>
            {policies.map(item=><option key={item.id} value={item.id}>{item.establishment_name} · {item.version_label} · {item.status}</option>)}
          </select>
        </label>
      </div>
      {selected && <div className="sb-actions">
        <button type="button" className="sb-secondary" disabled={busy} onClick={loadSelected}>Load selected version as a new draft</button>
        <button type="button" className="sb-secondary" disabled={busy || selected.status !== "draft"} onClick={validate}>Validate draft</button>
        <button type="button" className="sb-primary" disabled={busy || selected.status !== "draft"} onClick={activate}>Activate policy</button>
      </div>}
      <form onSubmit={saveDraft}>
        <div className="sb-form-grid">
          <label>Version label<input required maxLength="120" value={versionLabel} onChange={e=>setVersionLabel(e.target.value)}/></label>
          <label>Effective from<input required type="date" value={effectiveFrom} onChange={e=>setEffectiveFrom(e.target.value)}/></label>
        </div>
        <p className="sb-muted">{domain === "purchase"
          ? "Purchase JSON format: approval_bands[] with min_amount, optional max_amount, and ordered stages[] containing sequence and approver_roles. Bands must not overlap and must cover the amounts you intend to approve. Optional supplier_invoice_variance_tolerance: { amount: \"25.00\" } sets the maximum permitted aggregate INR variance; omit it for exact matching only."
          : "Inventory JSON format: event_policies keyed by event name, each with explicit approval_required. If true, configure stages[] with sequence and approver_roles. shelf_life must include default_minimum_remaining_days (integer or null); optional category_overrides, product_overrides and location_overrides are keyed by record ID. Approval-required events use the Inventory approval queue. Optional approval_thresholds can contain quantity and/or value_inr limits; crossing either limit requires the configured stages. For value limits, stock reductions/transfers use a conservative maximum remaining unit cost to avoid understating exposure. After all stages approve, the original requester must submit the unchanged operation again to post it."}</p>
        <label>Policy configuration (JSON)
          <textarea required rows={10} spellCheck="false" value={configText} onChange={e=>setConfigText(e.target.value)} />
        </label>
        <button className="sb-primary" type="submit" disabled={busy || !establishmentId}>{busy ? "Saving…" : "Save new draft"}</button>
      </form>
      {selected && <div className="sb-data-card">
        <h3>Policy audit history</h3>
        <p className="sb-muted">Append-only events and approval decisions recorded against this exact policy version.</p>
        {history.audit_events?.length ? history.audit_events.map(item=><p key={"a-"+item.id}>{new Date(item.created_at).toLocaleString()} · {item.event_type} · {item.actor_email} ({item.actor_role}) {item.reason ? "· "+item.reason : ""}</p>) : <p className="sb-empty">No policy lifecycle events recorded.</p>}
        {history.decisions?.length ? history.decisions.map(item=><p key={"d-"+item.id}>{new Date(item.created_at).toLocaleString()} · {item.document_type} #{item.document_id} · stage {item.stage_sequence} · {item.decision} · {item.actor_email} ({item.actor_role})</p>) : <p className="sb-empty">No approval decisions recorded against this policy version.</p>}
      </div>}
      <p className="sb-muted">Only owner/admin accounts can create, validate or activate policies. Activation replaces the currently active policy for the same establishment and domain. Existing decisions retain their recorded policy version.</p>
    </section>
  );
}
