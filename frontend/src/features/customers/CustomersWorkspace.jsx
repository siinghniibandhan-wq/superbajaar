import { useCallback, useEffect, useState } from "react";
import { apiRequest } from "../../services/api.js";

const priorities = ["low", "normal", "high", "urgent"];
const statuses = ["open", "in_progress", "waiting_customer", "resolved", "closed"];
const label = value => String(value || "").replaceAll("_", " ").replace(/\b\w/g, c => c.toUpperCase());
const blankCustomer = { name: "", phone: "", email: "", pin_code: "", address: "", notes: "" };
const blankCase = { customer_id: "", order_id: "", subject: "", description: "", priority: "normal" };
const blankSla = { priority: "normal", first_response_minutes: "", resolution_minutes: "", calendar_minutes: true, timezone: "Asia/Kolkata", is_active: true };

export default function CustomersWorkspace({ onBack }) {
  const [tab, setTab] = useState("customers");
  const [customers, setCustomers] = useState([]);
  const [cases, setCases] = useState([]);
  const [search, setSearch] = useState("");
  const [caseStatus, setCaseStatus] = useState("");
  const [casePriority, setCasePriority] = useState("");
  const [caseSearch, setCaseSearch] = useState("");
  const [form, setForm] = useState(blankCustomer);
  const [caseForm, setCaseForm] = useState(blankCase);
  const [editing, setEditing] = useState(null);
  const [caseEdits, setCaseEdits] = useState({});
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [customer360, setCustomer360] = useState(null);
  const [customer360Loading, setCustomer360Loading] = useState(false);
  const [caseDetail, setCaseDetail] = useState(null);
  const [caseDetailLoading, setCaseDetailLoading] = useState(false);
  const [messageDraft, setMessageDraft] = useState("");
  const [messageVisibility, setMessageVisibility] = useState("public");
  const [slaPolicies, setSlaPolicies] = useState([]);
  const [slaForm, setSlaForm] = useState(blankSla);
  const [slaEditing, setSlaEditing] = useState(null);
  const [accountSearch, setAccountSearch] = useState("");
  const [accountMatches, setAccountMatches] = useState([]);
  const [selectedAccountId, setSelectedAccountId] = useState("");
  const [verificationMethod, setVerificationMethod] = useState("email_otp");
  const [verificationConfirmed, setVerificationConfirmed] = useState(false);

  const load = useCallback(async () => {
    setLoading(true); setError("");
    try {
      const q = new URLSearchParams({ limit: "200" });
      if (search.trim()) q.set("search", search.trim());
      const cq = new URLSearchParams({ limit: "200" });
      if (caseStatus) cq.set("status", caseStatus);
      if (casePriority) cq.set("priority", casePriority);
      if (caseSearch.trim()) cq.set("search", caseSearch.trim());
      const [customerResult, caseResult] = await Promise.allSettled([
        apiRequest("/customers?" + q),
        apiRequest("/customers/support-cases?" + cq),
      ]);
      if (customerResult.status === "fulfilled") {
        setCustomers(customerResult.value.items || []);
      } else {
        setError(customerResult.reason?.message || "Unable to load customer records.");
      }
      if (caseResult.status === "fulfilled") {
        setCases(caseResult.value.items || []);
      } else {
        setError(old => old || (caseResult.reason?.message || "Support cases are unavailable. The CRM support schema may need its approved migration."));
      }
    } finally { setLoading(false); }
  }, [search, caseStatus, casePriority, caseSearch]);

  useEffect(() => { load(); }, [load]);
  const loadSlaPolicies = useCallback(async () => {
    try {
      const data = await apiRequest("/customers/support-sla-policies");
      setSlaPolicies(data.items || []);
    } catch (e) { setError(e.message || "Unable to load SLA policies."); }
  }, []);

  useEffect(() => { if (tab === "sla") loadSlaPolicies(); }, [tab, loadSlaPolicies]);

  async function saveSlaPolicy(e) {
    e.preventDefault(); setSaving(true); setError(""); setNotice("");
    try {
      const payload = {
        ...slaForm,
        first_response_minutes: Number(slaForm.first_response_minutes),
        resolution_minutes: Number(slaForm.resolution_minutes),
      };
      await apiRequest("/customers/support-sla-policies" + (slaEditing ? "/" + slaEditing : ""), {
        method: slaEditing ? "PATCH" : "POST",
        body: JSON.stringify(payload),
      });
      setSlaForm(blankSla); setSlaEditing(null); setNotice("SLA policy saved.");
      await loadSlaPolicies();
    } catch (e) { setError(e.message || "Unable to save SLA policy."); }
    finally { setSaving(false); }
  }

  async function toggleSlaPolicy(policy) {
    setSaving(true); setError(""); setNotice("");
    try {
      await apiRequest("/customers/support-sla-policies/" + policy.id, {
        method: "PATCH",
        body: JSON.stringify({
          priority: policy.priority,
          first_response_minutes: policy.first_response_minutes,
          resolution_minutes: policy.resolution_minutes,
          calendar_minutes: policy.calendar_minutes,
          timezone: policy.timezone,
          is_active: !policy.is_active,
        }),
      });
      setNotice("SLA policy updated."); await loadSlaPolicies();
    } catch (e) { setError(e.message || "Unable to update SLA policy."); }
    finally { setSaving(false); }
  }

  const setCustomerField = (key, value) => setForm(old => ({ ...old, [key]: value }));
  const setCaseField = (key, value) => setCaseForm(old => ({ ...old, [key]: value }));

  function startEdit(c) {
    setEditing(c.id);
    setForm({ name: c.name || "", phone: c.phone || "", email: c.email || "", pin_code: c.pin_code || "", address: c.address || "", notes: c.notes || "", is_active: c.is_active });
    setError(""); setNotice("");
  }
  function cancelEdit() { setEditing(null); setForm(blankCustomer); }

  async function saveCustomer(e) {
    e.preventDefault(); setSaving(true); setError(""); setNotice("");
    try {
      const payload = { ...form, phone: form.phone || null, email: form.email || null, pin_code: form.pin_code || null, address: form.address || null, notes: form.notes || null };
      if (editing) await apiRequest("/customers/" + editing, { method: "PATCH", body: JSON.stringify(payload) });
      else await apiRequest("/customers", { method: "POST", body: JSON.stringify(payload) });
      setNotice(editing ? "Customer updated." : "Customer created."); cancelEdit(); await load();
    } catch (e) { setError(e.message || "Unable to save customer."); }
    finally { setSaving(false); }
  }

  async function saveCase(e) {
    e.preventDefault(); setSaving(true); setError(""); setNotice("");
    try {
      await apiRequest("/customers/support-cases", { method: "POST", body: JSON.stringify({ ...caseForm, customer_id: caseForm.customer_id ? Number(caseForm.customer_id) : null, order_id: caseForm.order_id ? Number(caseForm.order_id) : null }) });
      setCaseForm(blankCase); setNotice("Support case created."); await load();
    } catch (e) { setError(e.message || "Unable to create support case."); }
    finally { setSaving(false); }
  }

  async function updateCase(item) {
    const edit = caseEdits[item.id] || {}; setSaving(true); setError(""); setNotice("");
    try {
      await apiRequest("/customers/support-cases/" + item.id, { method: "PATCH", body: JSON.stringify({ status: edit.status || item.status, priority: edit.priority || item.priority, assigned_to: (edit.assigned_to ?? item.assigned_to ?? "").trim() || null, resolution: (edit.resolution ?? item.resolution ?? "").trim() || null }) });
      setNotice(item.case_number + " updated."); await load();
    } catch (e) { setError(e.message || "Unable to update support case."); }
    finally { setSaving(false); }
  }

  async function viewCustomer360(c) {
    setCustomer360Loading(true); setCustomer360(null); setError("");
    try {
      const data = await apiRequest("/customers/" + c.id + "/360");
      setCustomer360(data);
    } catch (e) {
      setError(e.message || "Unable to load customer history.");
    } finally {
      setCustomer360Loading(false);
    }
  }

  async function openCaseConversation(item) {
    setCaseDetailLoading(true); setCaseDetail(null); setError("");
    try {
      const data = await apiRequest("/customers/support-cases/" + item.id);
      setCaseDetail(data);
    } catch (e) { setError(e.message || "Unable to load case conversation."); }
    finally { setCaseDetailLoading(false); }
  }

  async function sendCaseMessage(e) {
    e.preventDefault();
    if (!caseDetail || !messageDraft.trim()) return;
    setSaving(true); setError(""); setNotice("");
    try {
      await apiRequest("/customers/support-cases/" + caseDetail.ticket.id + "/messages", {
        method: "POST",
        body: JSON.stringify({ body: messageDraft.trim(), visibility: messageVisibility }),
      });
      setMessageDraft("");
      const data = await apiRequest("/customers/support-cases/" + caseDetail.ticket.id);
      setCaseDetail(data);
      setNotice(messageVisibility === "internal" ? "Internal note added." : "Customer reply sent.");
    } catch (e) { setError(e.message || "Unable to send case message."); }
    finally { setSaving(false); }
  }

  async function searchCustomerAccounts() {
    if (accountSearch.trim().length < 3) return;
    setSaving(true); setError("");
    try {
      const data = await apiRequest("/customers/customer-accounts?search=" + encodeURIComponent(accountSearch.trim()));
      setAccountMatches(data.items || []);
    } catch (e) { setError(e.message || "Only an owner or admin can search website accounts."); }
    finally { setSaving(false); }
  }

  async function linkCustomerAccount() {
    if (!customer360?.customer?.id || !selectedAccountId || !verificationConfirmed) return;
    setSaving(true); setError(""); setNotice("");
    try {
      await apiRequest("/customers/" + customer360.customer.id + "/account-link", {
        method: "POST",
        body: JSON.stringify({
          customer_account_id: Number(selectedAccountId),
          verification_confirmed: true,
          verification_method: verificationMethod,
        }),
      });
      setNotice("Website account linked after verification.");
      setAccountMatches([]); setSelectedAccountId(""); setVerificationConfirmed(false);
    } catch (e) { setError(e.message || "Unable to link website account."); }
    finally { setSaving(false); }
  }

  async function toggleActive(c) {
    setSaving(true); setError(""); setNotice("");
    try {
      await apiRequest("/customers/" + c.id, { method: "PATCH", body: JSON.stringify({ name: c.name, phone: c.phone, email: c.email, pin_code: c.pin_code, address: c.address, notes: c.notes, is_active: !c.is_active }) });
      setNotice(c.name + (c.is_active ? " deactivated." : " activated.")); await load();
    } catch (e) { setError(e.message || "Unable to update customer status."); }
    finally { setSaving(false); }
  }

  return <section className="sb-workspace sb-customers">
    <button className="sb-back" type="button" onClick={onBack}>← All workspaces</button>
    <p className="sb-eyebrow">CUSTOMERS & GROWTH · CRM</p><h1>Customers & CRM</h1>
    <p>Manage customer profiles and support cases. Customer records are shared by the customer and order APIs.</p>
    {error && <p className="sb-alert" role="alert">{error}</p>}
    {notice && <p className="sb-success" role="status">{notice}</p>}
    <div className="sb-customer-tabs" role="tablist" aria-label="Customer workspace">
      <button type="button" role="tab" aria-selected={tab === "customers"} className={tab === "customers" ? "is-active" : ""} onClick={() => setTab("customers")}>Customers <span>{customers.length}</span></button>
      <button type="button" role="tab" aria-selected={tab === "cases"} className={tab === "cases" ? "is-active" : ""} onClick={() => setTab("cases")}>Support cases <span>{cases.length}</span></button>
      <button type="button" role="tab" aria-selected={tab === "sla"} className={tab === "sla" ? "is-active" : ""} onClick={() => setTab("sla")}>SLA policies</button>
    </div>
    {tab === "customers" ? <>
      <form className="sb-customer-form" onSubmit={saveCustomer}>
        <h2>{editing ? "Edit customer" : "Add customer"}</h2>
        <div className="sb-customer-fields">
          <label>Full name *<input required maxLength="200" value={form.name} onChange={e => setCustomerField("name", e.target.value)} /></label>
          <label>Phone<input maxLength="20" value={form.phone} onChange={e => setCustomerField("phone", e.target.value)} /></label>
          <label>Email<input type="email" maxLength="254" value={form.email} onChange={e => setCustomerField("email", e.target.value)} /></label>
          <label>PIN code<input inputMode="numeric" pattern="[0-9]{6}" maxLength="6" value={form.pin_code} onChange={e => setCustomerField("pin_code", e.target.value)} placeholder="6-digit PIN" /></label>
          <label className="sb-span-all">Address<input maxLength="1000" value={form.address} onChange={e => setCustomerField("address", e.target.value)} /></label>
          <label className="sb-span-all">Notes<textarea rows="2" maxLength="2000" value={form.notes} onChange={e => setCustomerField("notes", e.target.value)} /></label>
          {editing && <label className="sb-customer-check"><input type="checkbox" checked={form.is_active !== false} onChange={e => setCustomerField("is_active", e.target.checked)} /> Active customer</label>}
        </div>
        <div className="sb-customer-actions"><button className="sb-primary" type="submit" disabled={saving}>{saving ? "Saving…" : editing ? "Save changes" : "Create customer"}</button>{editing && <button type="button" onClick={cancelEdit}>Cancel</button>}</div>
      </form>
      <div className="sb-customer-toolbar"><input aria-label="Search customers" placeholder="Search name, phone or email" value={search} onChange={e => setSearch(e.target.value)} /><button type="button" onClick={load} disabled={loading}>{loading ? "Loading…" : "Refresh"}</button></div>
      {loading ? <p className="sb-empty">Loading customers…</p> : customers.length ? <div className="sb-customer-list">{customers.map(c => <article className="sb-customer-card" key={c.id}>
        <div className="sb-customer-avatar">{(c.name || "?").trim().slice(0, 1).toUpperCase()}</div><div className="sb-customer-info"><strong>{c.name}</strong><small>{c.phone || "No phone"}{c.email ? " · " + c.email : ""}</small><small>SBID: {c.sbid || "Not linked"}</small><small>{[c.pin_code, c.address].filter(Boolean).join(" · ") || "No address saved"}</small><span className={"sb-order-status " + (c.is_active ? "status-delivered" : "status-cancelled")}>{c.is_active ? "Active" : "Inactive"}</span></div>
        <div className="sb-customer-row-actions"><button type="button" onClick={() => viewCustomer360(c)}>360 view</button><button type="button" onClick={() => startEdit(c)}>Edit</button><button type="button" disabled={saving} onClick={() => toggleActive(c)}>{c.is_active ? "Deactivate" : "Activate"}</button></div>
      </article>)}</div> : <p className="sb-empty">No customers found.</p>}
      {customer360Loading && <p className="sb-empty" role="status">Loading customer 360…</p>}
      {customer360 && <section className="sb-customer-360" aria-label="Customer 360">
        <div className="sb-customer-360-heading">
          <div><p className="sb-eyebrow">CUSTOMER 360</p><h2>{customer360.customer.name}</h2><small>{customer360.customer.email || "No email"} · {customer360.customer.phone || "No phone"}</small><small>SBID: {customer360.customer.sbid || "Not linked"}</small></div>
          <button type="button" onClick={() => setCustomer360(null)}>Close</button>
        </div>
        <div className="sb-customer-360-stats">
          <article><strong>{customer360.summary.order_count}</strong><span>Orders</span></article>
          <article><strong>{customer360.summary.open_case_count}</strong><span>Open cases</span></article>
          <article><strong>{customer360.summary.total_case_count}</strong><span>Total cases</span></article>
        </div>
        <section className="sb-customer-account-link">
          <h3>Link website account</h3>
          <p>Owner/admin only. Verify account ownership outside this screen before linking. Contact details alone do not grant ticket access.</p>
          <div className="sb-customer-toolbar">
            <input aria-label="Search website accounts" placeholder="Search account email or name" value={accountSearch} onChange={e => setAccountSearch(e.target.value)} />
            <button type="button" onClick={searchCustomerAccounts} disabled={saving || accountSearch.trim().length < 3}>Search accounts</button>
          </div>
          {accountMatches.length > 0 && <label>Website account<select value={selectedAccountId} onChange={e => setSelectedAccountId(e.target.value)}><option value="">Select account</option>{accountMatches.map(account => <option key={account.id} value={account.id}>{account.full_name} · {account.email} · #{account.id}</option>)}</select></label>}
          <label>Verification method<select value={verificationMethod} onChange={e => setVerificationMethod(e.target.value)}><option value="email_otp">Email OTP verified</option><option value="phone_otp">Phone OTP verified</option><option value="in_person">In-person verification</option><option value="other">Other approved verification</option></select></label>
          <label><input type="checkbox" checked={verificationConfirmed} onChange={e => setVerificationConfirmed(e.target.checked)} /> I confirm this customer account's ownership has been verified.</label>
          <button type="button" className="sb-primary" disabled={saving || !selectedAccountId || !verificationConfirmed} onClick={linkCustomerAccount}>Link verified account</button>
        </section>
        <div className="sb-customer-360-columns">
          <div><h3>Possible order matches</h3>{customer360.orders.length ? customer360.orders.map(order => <article className="sb-customer-360-row" key={order.order_number}><strong>{order.order_number}</strong><span>{label(order.status)} · ₹{Number(order.total || 0).toLocaleString("en-IN")}</span><small>{new Date(order.created_at).toLocaleString("en-IN")}</small></article>) : <p className="sb-empty">No orders matched this customer phone number.</p>}</div>
          <div><h3>Support history</h3>{customer360.support_cases.length ? customer360.support_cases.map(item => <article className="sb-customer-360-row" key={item.id}><strong>{item.case_number} · {item.subject}</strong><span>{label(item.status)} · {label(item.priority)}</span><small>{new Date(item.created_at).toLocaleString("en-IN")}</small></article>) : <p className="sb-empty">No support cases for this customer.</p>}</div>
        </div>
        <p className="sb-customer-360-note">Possible order matches are based only on the CRM phone number. Phone numbers can be shared or reassigned; verify each order before treating it as this customer’s order. This is not an identity link.</p>
      </section>}
    </> : tab === "cases" ? <>
      <form className="sb-customer-form" onSubmit={saveCase}>
        <h2>Create support case</h2><div className="sb-customer-fields">
          <label>Customer (optional)<select value={caseForm.customer_id} onChange={e => setCaseField("customer_id", e.target.value)}><option value="">No linked customer</option>{customers.map(c => <option key={c.id} value={c.id}>{c.name}{c.phone ? " · " + c.phone : ""}</option>)}</select></label>
          <label>Order ID (optional)<input type="number" min="1" value={caseForm.order_id} onChange={e => setCaseField("order_id", e.target.value)} placeholder="Order database ID" /></label>
          <label>Priority<select value={caseForm.priority} onChange={e => setCaseField("priority", e.target.value)}>{priorities.map(p => <option key={p} value={p}>{label(p)}</option>)}</select></label>
          <label>Subject *<input required minLength="3" maxLength="200" value={caseForm.subject} onChange={e => setCaseField("subject", e.target.value)} /></label>
          <label className="sb-span-all">Description *<textarea required maxLength="5000" rows="3" value={caseForm.description} onChange={e => setCaseField("description", e.target.value)} /></label>
        </div><button className="sb-primary" type="submit" disabled={saving}>{saving ? "Saving…" : "Create support case"}</button>
      </form>
      <div className="sb-customer-toolbar">
        <input aria-label="Search support cases" placeholder="Search case, subject or customer" value={caseSearch} onChange={e => setCaseSearch(e.target.value)} />
        <select aria-label="Filter support cases by status" value={caseStatus} onChange={e => setCaseStatus(e.target.value)}><option value="">All statuses</option>{statuses.map(s => <option key={s} value={s}>{label(s)}</option>)}</select>
        <select aria-label="Filter support cases by priority" value={casePriority} onChange={e => setCasePriority(e.target.value)}><option value="">All priorities</option>{priorities.map(p => <option key={p} value={p}>{label(p)}</option>)}</select>
        <button type="button" onClick={load} disabled={loading}>{loading ? "Loading…" : "Refresh"}</button>
      </div>
      {caseDetailLoading && <p className="sb-empty" role="status">Loading conversation…</p>}
      {caseDetail && <section className="sb-customer-360" aria-label="Support case conversation">
        <div className="sb-customer-360-heading">
          <div><p className="sb-eyebrow">CASE CONVERSATION</p><h2>{caseDetail.ticket.case_number} · {caseDetail.ticket.subject}</h2><small>{label(caseDetail.ticket.status)} · {label(caseDetail.ticket.priority)} · {caseDetail.ticket.customer_name || "Unlinked customer"}</small></div>
          <button type="button" onClick={() => setCaseDetail(null)}>Close</button>
        </div>
        <div className="sb-case-message-list">{caseDetail.messages.map(message => <article className={"sb-case-message " + (message.visibility === "internal" ? "is-internal" : "")} key={message.id}>
          <div><strong>{message.author_type === "customer" ? (message.customer_author || "Customer") : message.author_type === "system" ? "System" : (message.staff_author || "Staff")}</strong><small>{message.visibility === "internal" ? "Internal note" : "Public reply"} · {new Date(message.created_at).toLocaleString("en-IN")}</small></div>
          <p>{message.body}</p>
        </article>)}</div>
        <form className="sb-customer-form" onSubmit={sendCaseMessage}>
          <label>Reply type<select value={messageVisibility} onChange={e => setMessageVisibility(e.target.value)}><option value="public">Customer reply</option><option value="internal">Internal note</option></select></label>
          <label>Message<textarea required maxLength="10000" rows="3" value={messageDraft} onChange={e => setMessageDraft(e.target.value)} placeholder="Write a reply or internal note…" /></label>
          <button className="sb-primary" type="submit" disabled={saving || !messageDraft.trim()}>{saving ? "Sending…" : messageVisibility === "internal" ? "Add internal note" : "Send reply"}</button>
        </form>
        <p className="sb-customer-360-note">First response due: {caseDetail.ticket.first_response_due_at ? new Date(caseDetail.ticket.first_response_due_at).toLocaleString("en-IN") : "Not configured"} · Resolution due: {caseDetail.ticket.resolution_due_at ? new Date(caseDetail.ticket.resolution_due_at).toLocaleString("en-IN") : "Not configured"}</p>
        <div><strong>Audit events</strong>{caseDetail.events.map(event => <p key={event.id}>{label(event.event_type)} · {new Date(event.created_at).toLocaleString("en-IN")}</p>)}</div>
      </section>}
      {loading ? <p className="sb-empty">Loading support cases…</p> : cases.length ? <div className="sb-customer-list">{cases.map(item => <article className="sb-case-card" key={item.id}>
        <div className="sb-case-heading"><div><strong>{item.case_number} · {item.subject}</strong><small>{item.customer_name || "Unlinked customer"}{item.order_id ? " · Order #" + item.order_id : ""}</small></div><span className={"sb-order-status " + (item.priority === "urgent" || item.priority === "high" ? "status-cancelled" : "")}>{label(item.priority)}</span></div>
        <p>{item.description}</p><small className="sb-case-sla">{item.resolution_due_at ? "Resolution due: " + new Date(item.resolution_due_at).toLocaleString("en-IN") + (new Date(item.resolution_due_at).getTime() < Date.now() && !["resolved", "closed"].includes(item.status) ? " · OVERDUE" : "") : "SLA not configured"}</small><button type="button" onClick={() => openCaseConversation(item)}>View conversation & audit</button><div className="sb-case-edit"><label>Priority<select value={caseEdits[item.id]?.priority ?? item.priority} onChange={e => setCaseEdits(old => ({ ...old, [item.id]: { ...old[item.id], priority: e.target.value } }))}>{priorities.map(p => <option key={p} value={p}>{label(p)}</option>)}</select></label><label>Status<select value={caseEdits[item.id]?.status ?? item.status} onChange={e => setCaseEdits(old => ({ ...old, [item.id]: { ...old[item.id], status: e.target.value } }))}>{statuses.map(s => <option key={s} value={s}>{label(s)}</option>)}</select></label><label>Assigned to<input maxLength="200" value={caseEdits[item.id]?.assigned_to ?? item.assigned_to ?? ""} onChange={e => setCaseEdits(old => ({ ...old, [item.id]: { ...old[item.id], assigned_to: e.target.value } }))} placeholder="Team member" /></label><label className="sb-span-all">Resolution notes<textarea rows="2" maxLength="5000" value={caseEdits[item.id]?.resolution ?? item.resolution ?? ""} onChange={e => setCaseEdits(old => ({ ...old, [item.id]: { ...old[item.id], resolution: e.target.value } }))} /></label><button type="button" className="sb-primary" disabled={saving} onClick={() => updateCase(item)}>{saving ? "Saving…" : "Save case"}</button></div>
      </article>)}</div> : <p className="sb-empty">No support cases found.</p>}
    </> : <>
      <form className="sb-customer-form" onSubmit={saveSlaPolicy}>
        <h2>{slaEditing ? "Edit SLA policy" : "Add SLA policy"}</h2>
        <p>Targets are not preconfigured. Set business-approved response and resolution times before activating a policy.</p>
        <div className="sb-customer-fields">
          <label>Priority<select value={slaForm.priority} onChange={e => setSlaForm(old => ({ ...old, priority: e.target.value }))}>{priorities.map(p => <option key={p} value={p}>{label(p)}</option>)}</select></label>
          <label>First response (minutes)<input required type="number" min="1" max="525600" value={slaForm.first_response_minutes} onChange={e => setSlaForm(old => ({ ...old, first_response_minutes: e.target.value }))} /></label>
          <label>Resolution target (minutes)<input required type="number" min="1" max="525600" value={slaForm.resolution_minutes} onChange={e => setSlaForm(old => ({ ...old, resolution_minutes: e.target.value }))} /></label>
          <label>Timezone<input required maxLength="64" value={slaForm.timezone} onChange={e => setSlaForm(old => ({ ...old, timezone: e.target.value }))} /></label>
          <p>Time basis: calendar minutes (24×7). Business-hours SLAs remain disabled until working schedules are configured.</p>
          <label><input type="checkbox" checked={slaForm.is_active} onChange={e => setSlaForm(old => ({ ...old, is_active: e.target.checked }))} /> Active policy</label>
        </div>
        <div className="sb-customer-actions"><button className="sb-primary" type="submit" disabled={saving}>{saving ? "Saving…" : "Save SLA policy"}</button>{slaEditing && <button type="button" onClick={() => { setSlaEditing(null); setSlaForm(blankSla); }}>Cancel edit</button>}</div>
      </form>
      <div className="sb-customer-list">{slaPolicies.map(policy => <article className="sb-case-card" key={policy.id}>
        <div className="sb-case-heading"><strong>{label(policy.priority)} priority</strong><span className={"sb-order-status " + (policy.is_active ? "status-delivered" : "status-cancelled")}>{policy.is_active ? "Active" : "Inactive"}</span></div>
        <p>First response: {policy.first_response_minutes} min · Resolution: {policy.resolution_minutes} min · {policy.calendar_minutes ? "Calendar time" : "Business time"} · {policy.timezone}</p>
        <div className="sb-customer-actions"><button type="button" onClick={() => { setSlaEditing(policy.id); setSlaForm({ priority: policy.priority, first_response_minutes: String(policy.first_response_minutes), resolution_minutes: String(policy.resolution_minutes), calendar_minutes: policy.calendar_minutes, timezone: policy.timezone, is_active: policy.is_active }); }}>Edit</button><button type="button" disabled={saving} onClick={() => toggleSlaPolicy(policy)}>{policy.is_active ? "Deactivate" : "Activate"}</button></div>
      </article>)}</div>
    </>}
  </section>;
}