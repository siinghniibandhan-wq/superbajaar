import { useCallback, useEffect, useMemo, useState } from "react";
import { apiRequest } from "../../services/api.js";
import LoginScreen from "../../app/LoginScreen.jsx";
import "./PortalWorkspace.css";

const money = value => new Intl.NumberFormat("en-IN", { style: "currency", currency: "INR", maximumFractionDigits: 2 }).format(Number(value || 0));
const dateText = value => value ? new Date(value).toLocaleDateString("en-IN", { day: "2-digit", month: "short", year: "numeric" }) : "—";

function PortalCard({ label, value, hint, tone = "blue" }) {
  return <article className="portal-stat"><span className={`portal-stat-icon tone-${tone}`}>{label.slice(0,1)}</span><div><small>{label}</small><strong>{value}</strong>{hint && <em>{hint}</em>}</div></article>;
}

function EmptyState({ title, copy }) {
  return <div className="portal-empty"><span>✦</span><strong>{title}</strong><p>{copy}</p></div>;
}

export default function PortalWorkspace({ portal }) {
  const isVendor = portal === "vendor";
  const base = isVendor ? "/vendor-portal" : "/employee-portal";
  const [user, setUser] = useState(null);
  const [profile, setProfile] = useState(null);
  const [dashboard, setDashboard] = useState(null);
  const [records, setRecords] = useState({});
  const [active, setActive] = useState("overview");
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [invoiceFile, setInvoiceFile] = useState(null);
  const [invoice, setInvoice] = useState({ purchase_order_id: "", invoice_number: "", invoice_date: new Date().toISOString().slice(0,10), taxable_value: "", cgst_amount: "0", sgst_amount: "0", igst_amount: "0", cess_amount: "0", freight_amount: "0", discount_amount: "0" });
  const [leave, setLeave] = useState({ leave_type: "annual", start_date: "", end_date: "", days: "1", reason: "" });
  const [expense, setExpense] = useState({ category: "Travel", amount: "", expense_date: new Date().toISOString().slice(0,10), description: "", receipt_reference: "" });

  const load = useCallback(async () => {
    setLoading(true); setError("");
    try {
      const [me, dash] = await Promise.all([apiRequest(`${base}/me`), apiRequest(`${base}/dashboard`)]);
      setProfile(isVendor ? me.supplier : me.employee);
      setDashboard(dash);
      const endpoints = isVendor
        ? { orders: "/orders", dispatches: "/dispatches", invoices: "/invoices" }
        : { attendance: "/attendance", leave: "/leave", expenses: "/expenses", payslips: "/payslips" };
      const pairs = await Promise.all(Object.entries(endpoints).map(async ([key, path]) => [key, await apiRequest(base + path)]));
      setRecords(Object.fromEntries(pairs));
    } catch (reason) {
      setError(reason.message || "We couldn't load your portal. Please retry.");
    } finally { setLoading(false); }
  }, [base, isVendor]);

  useEffect(() => {
    let token = "";
    try { token = window.localStorage.getItem("superbajaar.access_token") || ""; } catch {}
    if (!token) { setLoading(false); return; }
    apiRequest("/auth/me").then(result => setUser(result.user)).catch(() => {
      try { window.localStorage.removeItem("superbajaar.access_token"); } catch {}
      setUser(null);
    });
  }, []);

  useEffect(() => { if (user) load(); }, [user, load]);

  const signOut = async () => {
    try { await apiRequest("/auth/logout", { method: "POST" }); } catch {}
    try { window.localStorage.removeItem("superbajaar.access_token"); } catch {}
    setUser(null); setProfile(null); setDashboard(null); setRecords({});
  };
  const refresh = async () => { setNotice(""); await load(); };

  async function act(path, method, body, success) {
    setBusy(true); setError(""); setNotice("");
    try {
      await apiRequest(base + path, { method, body: body ? JSON.stringify(body) : undefined });
      setNotice(success); await load();
    } catch (reason) { setError(reason.message || "That action could not be completed."); }
    finally { setBusy(false); }
  }

  const tabs = isVendor
    ? [{ id: "overview", label: "Overview" }, { id: "orders", label: "Purchase orders" }, { id: "dispatches", label: "Dispatches" }, { id: "invoices", label: "Invoices & payments" }]
    : [{ id: "overview", label: "Overview" }, { id: "attendance", label: "Attendance" }, { id: "leave", label: "Leave" }, { id: "expenses", label: "Reimbursements" }, { id: "payslips", label: "Payslips" }];

  if (!user) return <div className="portal-login-wrap"><div className="portal-login-heading"><span className="portal-brand-mark">S</span><p>SUPER BAJAAR · {isVendor ? "VENDOR" : "EMPLOYEE"} PORTAL</p><h1>{isVendor ? "Your business, in sync." : "Your workday, made simpler."}</h1><span>Secure access for invited {isVendor ? "suppliers" : "team members"}.</span></div><LoginScreen onSignedIn={setUser} /></div>;
  if (loading && !profile) return <main className="portal-loading">Preparing your workspace…</main>;
  if (error && !profile) return <main className="portal-loading"><p role="alert">{error}</p><button onClick={load}>Retry</button><button onClick={signOut}>Sign out</button></main>;

  const orders = records.orders?.items || [];
  const invoices = records.invoices?.items || [];
  const leaveItems = records.leave?.items || [];
  const expenseItems = records.expenses?.items || [];
  const attendance = records.attendance?.items || [];
  const payslips = records.payslips?.items || [];
  const openClock = dashboard?.attendance?.open_clock_in;

  return <main className="portal-shell">
    <header className="portal-header">
      <div className="portal-brand"><span className="portal-brand-mark">S</span><div><strong>Super Bajaar</strong><small>{isVendor ? "Vendor portal" : "Employee portal"}</small></div></div>
      <div className="portal-header-right"><span className="portal-live"><i /> Secure workspace</span><span className="portal-avatar">{(profile?.supplier_name || profile?.first_name || user.full_name || "S").slice(0,1).toUpperCase()}</span><span className="portal-user-name">{profile?.supplier_name || [profile?.first_name, profile?.last_name].filter(Boolean).join(" ") || user.full_name}</span><button className="portal-logout" onClick={signOut}>Sign out</button></div>
    </header>
    <section className="portal-welcome">
      <div><span className="portal-eyebrow">{isVendor ? "SUPPLIER WORKSPACE" : "PEOPLE & CULTURE"}</span><h1>{isVendor ? "Good to have you here." : "Welcome to your workspace."}</h1><p>{isVendor ? "Keep orders, deliveries and invoices moving — all in one place." : "Your attendance, time off and pay information, all together."}</p></div>
      <button className="portal-refresh" onClick={refresh} disabled={loading}>↻ <span>Refresh</span></button>
    </section>
    <nav className="portal-tabs" aria-label="Portal sections">{tabs.map(tab => <button key={tab.id} className={active === tab.id ? "active" : ""} onClick={() => setActive(tab.id)}>{tab.label}</button>)}</nav>
    {error && <div className="portal-alert" role="alert">{error}</div>}
    {notice && <div className="portal-notice" role="status">{notice}</div>}
    {active === "overview" && <section className="portal-content">
      <div className="portal-section-heading"><div><h2>{isVendor ? "Business at a glance" : "Your snapshot"}</h2><p>{isVendor ? "A quick view of your activity with Super Bajaar." : "A quick view of your work and requests."}</p></div></div>
      {isVendor ? <div className="portal-stats">
        <PortalCard label="Purchase orders" value={dashboard?.orders?.total ?? "—"} hint={`${dashboard?.orders?.open ?? 0} currently open`} />
        <PortalCard label="Invoices submitted" value={dashboard?.invoices?.total ?? "—"} hint={`${dashboard?.invoices?.awaiting_review ?? 0} awaiting review`} tone="violet" />
        <PortalCard label="Submitted value" value={money(dashboard?.invoices?.submitted_value)} hint="Invoice value, not payment confirmation" tone="green" />
      </div> : <div className="portal-stats">
        <PortalCard label="Attendance today" value={openClock ? "Clocked in" : "Not clocked in"} hint={openClock ? "Your current session is open" : "Record your workday"} tone="green" />
        <PortalCard label="Leave requests" value={dashboard?.leave?.pending ?? 0} hint={`${dashboard?.leave?.upcoming ?? 0} upcoming approved`} tone="violet" />
        <PortalCard label="Reimbursements" value={dashboard?.expenses?.pending ?? 0} hint="Requests awaiting review" />
      </div>}
      <div className="portal-quick-grid">
        <article className="portal-panel portal-quick"><span className="portal-panel-icon">{isVendor ? "↗" : "◷"}</span><div><h3>{isVendor ? "Keep orders moving" : "Your day, your pace"}</h3><p>{isVendor ? "Review new purchase orders and confirm whether you can fulfil them." : "Record attendance and keep your time-off requests up to date."}</p></div><button onClick={() => setActive(isVendor ? "orders" : "attendance")}>Open {isVendor ? "orders" : "attendance"} →</button></article>
        <article className="portal-panel portal-quick"><span className="portal-panel-icon">{isVendor ? "₹" : "▤"}</span><div><h3>{isVendor ? "Invoice visibility" : "Your records, securely"}</h3><p>{isVendor ? "Submit invoices and follow their review and payment allocation status." : "View reimbursement decisions and approved payslips in one place."}</p></div><button onClick={() => setActive(isVendor ? "invoices" : "payslips")}>View {isVendor ? "invoices" : "payslips"} →</button></article>
      </div>
    </section>}
    {isVendor && active === "orders" && <section className="portal-content"><div className="portal-section-heading"><div><h2>Purchase orders</h2><p>Only orders assigned to your supplier account are shown.</p></div></div>{orders.length ? <div className="portal-list">{orders.map(order => <article className="portal-row" key={order.id}><div><strong>{order.purchase_number}</strong><small>{dateText(order.created_at)} · {order.line_count} line items</small></div><div className="portal-row-right"><span className={`portal-status status-${order.status}`}>{order.status.replaceAll("_"," ")}</span><span className="portal-amount">{money(order.subtotal)}</span>{!order.vendor_response && ["ordered","partially_received"].includes(order.status) && <><button disabled={busy} onClick={() => act(`/orders/${order.id}/respond`,"POST",{response:"accepted"},"Purchase order accepted.")}>Accept</button><button className="portal-secondary" disabled={busy} onClick={() => act(`/orders/${order.id}/respond`,"POST",{response:"rejected",note:"Unable to fulfil this order"},"Response recorded.")}>Decline</button></>}</div></article>)}</div> : <EmptyState title="No purchase orders yet" copy="New orders assigned to your supplier account will appear here."/>}</section>}
    {isVendor && active === "dispatches" && <section className="portal-content"><div className="portal-section-heading"><div><h2>Dispatch updates</h2><p>Share shipment and expected arrival details for active orders.</p></div></div><form className="portal-form" onSubmit={event => { event.preventDefault(); const form = new FormData(event.currentTarget); act("/dispatches","POST",Object.fromEntries(form),"Dispatch details submitted."); event.currentTarget.reset(); }}><label>Purchase order<select name="purchase_order_id" required defaultValue=""><option value="" disabled>Select an order</option>{orders.filter(o=>["ordered","partially_received"].includes(o.status)).map(o=><option key={o.id} value={o.id}>{o.purchase_number}</option>)}</select></label><label>Carrier<input name="carrier_name" maxLength="160" placeholder="Transport or courier partner"/></label><label>Tracking / LR number<input name="tracking_reference" maxLength="160" placeholder="Tracking reference"/></label><label>Expected arrival<input name="expected_arrival_at" type="date"/></label><label>Dispatch reference<input name="supplier_dispatch_reference" maxLength="100" placeholder="Your dispatch note number"/></label><label>Notes<input name="notes" maxLength="1000" placeholder="Optional shipment details"/></label><button className="portal-primary" disabled={busy || !orders.length}>Submit dispatch</button></form><div className="portal-list">{(records.dispatches?.items||[]).map(item=><article className="portal-row" key={item.id}><div><strong>{item.purchase_number} · {item.carrier_name || "Carrier not specified"}</strong><small>{item.tracking_reference || "No tracking reference"} · ETA {dateText(item.expected_arrival_at)}</small></div><span className="portal-status status-ordered">Submitted</span></article>)}</div></section>}
    {isVendor && active === "invoices" && <section className="portal-content"><div className="portal-section-heading"><div><h2>Invoices & payments</h2><p>Submit a supplier invoice against an issued purchase order.</p></div></div><form className="portal-form portal-form-wide" onSubmit={async event=>{event.preventDefault();const form=event.currentTarget;const data=Object.fromEntries(new FormData(form));const numeric=["purchase_order_id","taxable_value","cgst_amount","sgst_amount","igst_amount","cess_amount","freight_amount","discount_amount"];numeric.forEach(k=>data[k]=Number(data[k]||0));data.invoice_total=data.taxable_value+data.cgst_amount+data.sgst_amount+data.igst_amount+data.cess_amount+data.freight_amount-data.discount_amount;try{setBusy(true);setError("");const upload=new FormData();if(!invoiceFile)throw new Error("Attach the supplier invoice PDF or image before submitting.");upload.append("file",invoiceFile);const document=await apiRequest(base+"/documents",{method:"POST",body:upload});data.source_document_uri=document.document_uri;await apiRequest(base+"/invoices",{method:"POST",body:JSON.stringify(data)});setNotice("Invoice and supporting document submitted for Purchasing/Accounts review.");setInvoiceFile(null);form.reset();await load();}catch(reason){setError(reason.message||"Invoice submission failed.");}finally{setBusy(false);}}}><label>Purchase order<select name="purchase_order_id" required defaultValue=""><option value="" disabled>Select an order</option>{orders.filter(o=>["ordered","partially_received","received"].includes(o.status)).map(o=><option key={o.id} value={o.id}>{o.purchase_number}</option>)}</select></label><label>Invoice number<input name="invoice_number" required maxLength="100" placeholder="Supplier invoice number"/></label><label>Invoice date<input name="invoice_date" type="date" required defaultValue={invoice.invoice_date}/></label><label>Taxable value (₹)<input name="taxable_value" type="number" min="0" step="0.01" required placeholder="0.00"/></label><label>CGST (₹)<input name="cgst_amount" type="number" min="0" step="0.01" defaultValue="0"/></label><label>SGST (₹)<input name="sgst_amount" type="number" min="0" step="0.01" defaultValue="0"/></label><label>IGST (₹)<input name="igst_amount" type="number" min="0" step="0.01" defaultValue="0"/></label><label>CESS (₹)<input name="cess_amount" type="number" min="0" step="0.01" defaultValue="0"/></label><label>Freight (₹)<input name="freight_amount" type="number" min="0" step="0.01" defaultValue="0"/></label><label>Discount (₹)<input name="discount_amount" type="number" min="0" step="0.01" defaultValue="0"/></label><label className="portal-full">Invoice document (PDF, JPG or PNG)<input type="file" accept="application/pdf,image/jpeg,image/png" required onChange={event=>setInvoiceFile(event.target.files?.[0]||null)}/></label><button className="portal-primary" disabled={busy}>Submit invoice for review</button><p className="portal-form-note">Maximum 10 MB. Documents are stored privately with server-side encryption and supplier-scoped access.</p></form>{invoices.length?<div className="portal-list">{invoices.map(item=><article className="portal-row" key={item.id}><div><strong>{item.invoice_number}</strong><small>{item.purchase_number} · {dateText(item.invoice_date)}</small></div><div className="portal-row-right"><span className={`portal-status status-${item.match_status}`}>{item.match_status}</span><span className="portal-amount">{money(item.invoice_total)}</span><small>Paid: {money(item.paid_amount)}</small></div></article>)}</div>:<EmptyState title="No invoices submitted" copy="Your submitted invoices and review status will appear here."/>}</section>}
    {!isVendor && active === "attendance" && <section className="portal-content"><div className="portal-section-heading"><div><h2>Attendance</h2><p>Record your start and end time. Each action is linked to your employee profile.</p></div><button className="portal-primary" disabled={busy} onClick={()=>act("/attendance/punch","POST",{punch_type:openClock?"clock_out":"clock_in"},openClock?"You are clocked out.":"You are clocked in.")}>{openClock?"Clock out":"Clock in"}</button></div>{attendance.length?<div className="portal-list">{attendance.map(row=><article className="portal-row" key={row.id}><div><strong>{dateText(row.clock_in_at)}</strong><small>Started {new Date(row.clock_in_at).toLocaleTimeString("en-IN",{hour:"2-digit",minute:"2-digit"})}</small></div><div className="portal-row-right"><span className="portal-status status-approved">{row.clock_out_at?"Completed":"In progress"}</span><span>{row.clock_out_at?new Date(row.clock_out_at).toLocaleTimeString("en-IN",{hour:"2-digit",minute:"2-digit"}):"—"}</span></div></article>)}</div>:<EmptyState title="No attendance history" copy="Your attendance records will appear here after your first clock-in."/>}</section>}
    {!isVendor && active === "leave" && <section className="portal-content"><div className="portal-section-heading"><div><h2>Time off</h2><p>Apply for leave and follow its approval status.</p></div></div><form className="portal-form" onSubmit={event=>{event.preventDefault();const data=Object.fromEntries(new FormData(event.currentTarget));data.days=Number(data.days);act("/leave","POST",data,"Leave request submitted to HR.");event.currentTarget.reset();}}><label>Leave type<select name="leave_type"><option value="annual">Annual</option><option value="sick">Sick</option><option value="casual">Casual</option><option value="unpaid">Unpaid</option><option value="other">Other</option></select></label><label>From<input name="start_date" type="date" required/></label><label>To<input name="end_date" type="date" required/></label><label>Days<input name="days" type="number" min="0.5" step="0.5" defaultValue="1" required/></label><label className="portal-full">Reason<textarea name="reason" minLength="3" maxLength="1000" required placeholder="Briefly explain your request"/></label><button className="portal-primary" disabled={busy}>Submit leave request</button></form>{leaveItems.length?<div className="portal-list">{leaveItems.map(item=><article className="portal-row" key={item.id}><div><strong>{item.leave_type} leave · {item.days} days</strong><small>{dateText(item.start_date)} – {dateText(item.end_date)}</small></div><span className={`portal-status status-${item.status}`}>{item.status}</span></article>)}</div>:<EmptyState title="No leave requests" copy="Your applications and HR decisions will appear here."/>}</section>}
    {!isVendor && active === "expenses" && <section className="portal-content"><div className="portal-section-heading"><div><h2>Reimbursements</h2><p>Submit a work expense for HR/Manager review.</p></div></div><form className="portal-form" onSubmit={event=>{event.preventDefault();const data=Object.fromEntries(new FormData(event.currentTarget));data.amount=Number(data.amount);act("/expenses","POST",data,"Reimbursement request submitted.");event.currentTarget.reset();}}><label>Category<input name="category" required maxLength="64" defaultValue="Travel"/></label><label>Amount (₹)<input name="amount" type="number" min="0.01" step="0.01" required/></label><label>Expense date<input name="expense_date" type="date" required defaultValue={expense.expense_date}/></label><label>Receipt reference<input name="receipt_reference" maxLength="500" placeholder="Receipt number or approved document reference"/></label><label className="portal-full">Description<textarea name="description" minLength="3" maxLength="1000" required placeholder="Describe the business expense"/></label><button className="portal-primary" disabled={busy}>Submit reimbursement</button></form>{expenseItems.length?<div className="portal-list">{expenseItems.map(item=><article className="portal-row" key={item.id}><div><strong>{item.category} · {money(item.amount)}</strong><small>{dateText(item.expense_date)} · {item.description}</small></div><span className={`portal-status status-${item.status}`}>{item.status}</span></article>)}</div>:<EmptyState title="No reimbursement requests" copy="Submitted expenses and review outcomes will appear here."/>}</section>}
    {!isVendor && active === "payslips" && <section className="portal-content"><div className="portal-section-heading"><div><h2>Payslips</h2><p>Only approved or paid payroll periods are displayed.</p></div></div>{payslips.length?<div className="portal-list">{payslips.map(item=><article className="portal-row" key={item.id}><div><strong>{new Date(item.period_start).toLocaleDateString("en-IN",{month:"long",year:"numeric"})}</strong><small>Gross {money(item.gross_earnings)} · Deductions {money(item.deductions)}</small></div><div className="portal-row-right"><span className="portal-status status-approved">{item.payroll_status}</span><strong className="portal-amount">{money(item.net_pay)}</strong><button className="portal-secondary" onClick={()=>window.print()}>Print / Save PDF</button></div></article>)}</div>:<EmptyState title="No payslips available yet" copy="Approved and paid payroll records will appear here."/>}</section>}
    <footer className="portal-footer">Super Bajaar · {isVendor?"Vendor Portal":"Employee Portal"} · Your information is protected by account-level access controls.</footer>
  </main>;
}


export function PortalActivation({ portal }) {
  const [password, setPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [done, setDone] = useState(false);
  const token = new URLSearchParams(window.location.search).get("token") || "";
  async function submit(event) {
    event.preventDefault(); setError("");
    if (password !== confirm) { setError("Your passwords do not match."); return; }
    setBusy(true);
    try {
      await apiRequest("/portal-invitations/accept", {
        method: "POST", skipAuth: true,
        body: JSON.stringify({ token, password }),
      });
      setDone(true);
    } catch (reason) { setError(reason.message || "This invitation could not be activated."); }
    finally { setBusy(false); }
  }
  return <main className="portal-login-wrap">
    <div className="portal-login-heading"><span className="portal-brand-mark">S</span><p>SUPER BAJAAR · {portal.toUpperCase()} PORTAL</p><h1>Make this space yours.</h1><span>Set a password to activate your invited account.</span></div>
    <form className="sb-login-card" onSubmit={submit}>
      <p className="sb-eyebrow">SECURE ACCOUNT ACTIVATION</p>
      {done ? <><h1>You're all set.</h1><p>Your account is active. Sign in to continue to your {portal} workspace.</p><a className="sb-primary" href={portal === "vendor" ? "/vendor" : "/employee"}>Continue to sign in</a></> : <>
        <h1>Activate your account</h1><p>Choose a strong password to get started.</p>
        {!token && <p className="sb-alert" role="alert">The invitation link is missing its token. Ask your administrator for a fresh invitation.</p>}
        {error && <p className="sb-alert" role="alert">{error}</p>}
        <label>Password<input type="password" autoComplete="new-password" minLength={12} maxLength={1024} required value={password} onChange={event=>setPassword(event.target.value)}/></label>
        <label>Confirm password<input type="password" autoComplete="new-password" minLength={12} maxLength={1024} required value={confirm} onChange={event=>setConfirm(event.target.value)}/></label>
        <button className="sb-primary" type="submit" disabled={busy || !token}>{busy ? "Activating…" : "Activate account"}</button>
      </>}
    </form>
  </main>;
}
