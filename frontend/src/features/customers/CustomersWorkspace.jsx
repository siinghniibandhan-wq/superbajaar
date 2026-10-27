import { useCallback, useEffect, useState } from "react";
import { apiRequest } from "../../services/api.js";

const priorities = ["low", "normal", "high", "urgent"];
const statuses = ["open", "in_progress", "waiting_customer", "resolved", "closed"];
const label = value => String(value || "").replaceAll("_", " ").replace(/\b\w/g, c => c.toUpperCase());
const blankCustomer = { name: "", phone: "", email: "", pin_code: "", address: "", notes: "" };
const blankCase = { customer_id: "", order_id: "", subject: "", description: "", priority: "normal" };

export default function CustomersWorkspace({ onBack }) {
  const [tab, setTab] = useState("customers");
  const [customers, setCustomers] = useState([]);
  const [cases, setCases] = useState([]);
  const [search, setSearch] = useState("");
  const [caseStatus, setCaseStatus] = useState("");
  const [form, setForm] = useState(blankCustomer);
  const [caseForm, setCaseForm] = useState(blankCase);
  const [editing, setEditing] = useState(null);
  const [caseEdits, setCaseEdits] = useState({});
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");

  const load = useCallback(async () => {
    setLoading(true); setError("");
    try {
      const q = new URLSearchParams({ limit: "200" });
      if (search.trim()) q.set("search", search.trim());
      const cq = new URLSearchParams({ limit: "200" });
      if (caseStatus) cq.set("status", caseStatus);
      const [c, s] = await Promise.all([apiRequest("/customers?" + q), apiRequest("/customers/support-cases?" + cq)]);
      setCustomers(c.items || []); setCases(s.items || []);
    } catch (e) { setError(e.message || "Unable to load customer records."); }
    finally { setLoading(false); }
  }, [search, caseStatus]);

  useEffect(() => { load(); }, [load]);
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
      await apiRequest("/customers/support-cases/" + item.id, { method: "PATCH", body: JSON.stringify({ status: edit.status || item.status, assigned_to: edit.assigned_to ?? item.assigned_to ?? null, resolution: edit.resolution ?? item.resolution ?? null }) });
      setNotice(item.case_number + " updated."); await load();
    } catch (e) { setError(e.message || "Unable to update support case."); }
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
        <div className="sb-customer-avatar">{(c.name || "?").trim().slice(0, 1).toUpperCase()}</div><div className="sb-customer-info"><strong>{c.name}</strong><small>{c.phone || "No phone"}{c.email ? " · " + c.email : ""}</small><small>{[c.pin_code, c.address].filter(Boolean).join(" · ") || "No address saved"}</small><span className={"sb-order-status " + (c.is_active ? "status-delivered" : "status-cancelled")}>{c.is_active ? "Active" : "Inactive"}</span></div>
        <div className="sb-customer-row-actions"><button type="button" onClick={() => startEdit(c)}>Edit</button><button type="button" disabled={saving} onClick={() => toggleActive(c)}>{c.is_active ? "Deactivate" : "Activate"}</button></div>
      </article>)}</div> : <p className="sb-empty">No customers found.</p>}
    </> : <>
      <form className="sb-customer-form" onSubmit={saveCase}>
        <h2>Create support case</h2><div className="sb-customer-fields">
          <label>Customer (optional)<select value={caseForm.customer_id} onChange={e => setCaseField("customer_id", e.target.value)}><option value="">No linked customer</option>{customers.map(c => <option key={c.id} value={c.id}>{c.name}{c.phone ? " · " + c.phone : ""}</option>)}</select></label>
          <label>Order ID (optional)<input type="number" min="1" value={caseForm.order_id} onChange={e => setCaseField("order_id", e.target.value)} placeholder="Order database ID" /></label>
          <label>Priority<select value={caseForm.priority} onChange={e => setCaseField("priority", e.target.value)}>{priorities.map(p => <option key={p} value={p}>{label(p)}</option>)}</select></label>
          <label>Subject *<input required minLength="3" maxLength="200" value={caseForm.subject} onChange={e => setCaseField("subject", e.target.value)} /></label>
          <label className="sb-span-all">Description *<textarea required maxLength="5000" rows="3" value={caseForm.description} onChange={e => setCaseField("description", e.target.value)} /></label>
        </div><button className="sb-primary" type="submit" disabled={saving}>{saving ? "Saving…" : "Create support case"}</button>
      </form>
      <div className="sb-customer-toolbar"><select aria-label="Filter support cases" value={caseStatus} onChange={e => setCaseStatus(e.target.value)}><option value="">All case statuses</option>{statuses.map(s => <option key={s} value={s}>{label(s)}</option>)}</select><button type="button" onClick={load} disabled={loading}>{loading ? "Loading…" : "Refresh"}</button></div>
      {loading ? <p className="sb-empty">Loading support cases…</p> : cases.length ? <div className="sb-customer-list">{cases.map(item => <article className="sb-case-card" key={item.id}>
        <div className="sb-case-heading"><div><strong>{item.case_number} · {item.subject}</strong><small>{item.customer_name || "Unlinked customer"}{item.order_id ? " · Order #" + item.order_id : ""}</small></div><span className={"sb-order-status " + (item.priority === "urgent" || item.priority === "high" ? "status-cancelled" : "")}>{label(item.priority)}</span></div>
        <p>{item.description}</p><div className="sb-case-edit"><label>Status<select value={caseEdits[item.id]?.status ?? item.status} onChange={e => setCaseEdits(old => ({ ...old, [item.id]: { ...old[item.id], status: e.target.value } }))}>{statuses.map(s => <option key={s} value={s}>{label(s)}</option>)}</select></label><label>Assigned to<input maxLength="200" value={caseEdits[item.id]?.assigned_to ?? item.assigned_to ?? ""} onChange={e => setCaseEdits(old => ({ ...old, [item.id]: { ...old[item.id], assigned_to: e.target.value } }))} placeholder="Team member" /></label><label className="sb-span-all">Resolution notes<textarea rows="2" maxLength="5000" value={caseEdits[item.id]?.resolution ?? item.resolution ?? ""} onChange={e => setCaseEdits(old => ({ ...old, [item.id]: { ...old[item.id], resolution: e.target.value } }))} /></label><button type="button" className="sb-primary" disabled={saving} onClick={() => updateCase(item)}>{saving ? "Saving…" : "Save case"}</button></div>
      </article>)}</div> : <p className="sb-empty">No support cases found.</p>}
    </>}
  </section>;
}