import { useCallback, useEffect, useMemo, useState } from "react";
import { apiRequest } from "../../services/api.js";

const money = value => new Intl.NumberFormat("en-IN", { style: "currency", currency: "INR", maximumFractionDigits: 0 }).format(Number(value || 0));
const date = value => value ? new Date(value).toLocaleDateString("en-IN", { day: "2-digit", month: "short", year: "numeric" }) : "—";
const title = value => String(value || "unknown").replaceAll("_", " ").replace(/\b\w/g, c => c.toUpperCase());
const items = response => Array.isArray(response?.items) ? response.items : [];

export default function LoyaltyWorkspace({ onBack }) {
  const [tab, setTab] = useState("overview");
  const [accounts, setAccounts] = useState([]);
  const [rules, setRules] = useState([]);
  const [enquiries, setEnquiries] = useState([]);
  const [transactions, setTransactions] = useState([]);
  const [selected, setSelected] = useState(null);
  const [search, setSearch] = useState("");
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [sourceErrors, setSourceErrors] = useState({});
  const [rule, setRule] = useState({ scope_type: "default", scope_id: "", coins_per_100: "1", is_active: true });
  const [adjustment, setAdjustment] = useState({ customer_email: "", direction: "credit", coins: "", reason: "" });

  const load = useCallback(async () => {
    setLoading(true); setError(""); setNotice("");
    const results = await Promise.allSettled([
      apiRequest("/loyalty/admin/accounts?limit=200"),
      apiRequest("/loyalty/admin/rules"),
      apiRequest("/loyalty/admin/partner-enquiries?limit=100"),
    ]);
    const failures = {};
    if (results[0].status === "fulfilled") setAccounts(items(results[0].value)); else failures.accounts = results[0].reason?.message || "Unable to load loyalty accounts";
    if (results[1].status === "fulfilled") setRules(items(results[1].value)); else failures.rules = results[1].reason?.message || "Unable to load earning rules";
    if (results[2].status === "fulfilled") setEnquiries(items(results[2].value)); else failures.enquiries = results[2].reason?.message || "Unable to load partner enquiries";
    setSourceErrors(failures);
    if (Object.keys(failures).length) setError("Some loyalty data sources could not be loaded. Review the affected section below.");
    setLoading(false);
  }, []);

  useEffect(() => { load(); }, [load]);

  const loadLedger = async account => {
    setSelected(account); setTransactions([]);
    try {
      const response = await apiRequest("/loyalty/admin/accounts/" + account.id + "/transactions?limit=100");
      setTransactions(items(response));
    } catch (e) { setError(e.message || "Unable to load this customer's ledger."); }
  };

  const saveRule = async event => {
    event.preventDefault(); setBusy(true); setError(""); setNotice("");
    try {
      await apiRequest("/loyalty/rules", { method: "PUT", body: JSON.stringify({
        ...rule, scope_id: rule.scope_type === "default" ? null : Number(rule.scope_id),
        coins_per_100: Number(rule.coins_per_100),
      }) });
      setNotice("Earning rule saved."); setRule({ scope_type: "default", scope_id: "", coins_per_100: "1", is_active: true }); await load();
    } catch (e) { setError(e.message || "Unable to save earning rule."); }
    finally { setBusy(false); }
  };

  const submitAdjustment = async event => {
    event.preventDefault(); setBusy(true); setError(""); setNotice("");
    try {
      await apiRequest("/loyalty/admin/adjust", { method: "POST", body: JSON.stringify({
        ...adjustment, coins: Number(adjustment.coins),
        idempotency_key: "admin-" + crypto.randomUUID(),
      }) });
      setNotice("Super Coins adjustment posted."); setAdjustment({ customer_email: "", direction: "credit", coins: "", reason: "" }); await load();
    } catch (e) { setError(e.message || "Unable to adjust this account."); }
    finally { setBusy(false); }
  };

  const updateEnquiry = async (id, status) => {\n    setBusy(true); setError(""); setNotice("");\n    try { await apiRequest("/loyalty/admin/partner-enquiries/" + id, { method: "PATCH", body: JSON.stringify({ status }) }); setEnquiries(rows => rows.map(row => row.id === id ? { ...row, status } : row)); setNotice("Partner enquiry status updated."); }\n    catch (e) { setError(e.message || "Unable to update partner enquiry."); }\n    finally { setBusy(false); }\n  };\n\n  const expire = async () => {
    if (!window.confirm("Expire all currently due Super Coins lots in the next processing batch? Accounting postings will be created.")) return;
    setBusy(true); setError(""); setNotice("");
    try {
      const result = await apiRequest("/loyalty/admin/expire?limit=200", { method: "POST" });
      setNotice("Expiry processed: " + Number(result.expired_coins || 0).toLocaleString("en-IN") + " coins across " + Number(result.expired_lots || 0) + " lots."); await load();
    } catch (e) { setError(e.message || "Unable to process coin expiry."); }
    finally { setBusy(false); }
  };

  const filtered = useMemo(() => accounts.filter(account =>
    (account.customer_email + " " + account.card_number).toLowerCase().includes(search.toLowerCase())
  ), [accounts, search]);
  const totalCoins = accounts.reduce((sum, account) => sum + Number(account.available_coins || 0), 0);
  const sections = [["overview", "Overview"], ["members", "Members"], ["rules", "Earning rules"], ["adjust", "Adjustments"], ["enquiries", "Partner enquiries"]];

  return <section className="sb-workspace sb-loyalty">
    <button className="sb-back" onClick={onBack} type="button">← All workspaces</button>
    <div className="sb-loyalty-heading"><div><p className="sb-eyebrow">CUSTOMERS · RETENTION & REWARDS</p><h1>Loyalty & Super Coins</h1><p>Manage member balances, earning rules, ledger activity and partner enquiries.</p></div><button type="button" onClick={load} disabled={loading}>↻ Refresh</button></div>
    <nav className="sb-loyalty-tabs" aria-label="Loyalty sections">{sections.map(([key, label]) => <button type="button" key={key} className={tab === key ? "active" : ""} onClick={() => setTab(key)}>{label}</button>)}</nav>
    {error && <p className="sb-alert" role="alert">{error}</p>}
    {notice && <p className="sb-loyalty-notice" role="status">{notice}</p>}
    {loading && <p className="sb-empty">Loading loyalty programme…</p>}
    {!loading && tab === "overview" && <>
      <div className="sb-loyalty-kpis">
        <article><small>Loyalty members</small><strong>{accounts.length.toLocaleString("en-IN")}</strong><span>Accounts with a loyalty card</span></article>
        <article><small>Available Super Coins</small><strong>{totalCoins.toLocaleString("en-IN")}</strong><span>Unexpired spendable balance</span></article>
        <article><small>Earning rules</small><strong>{rules.length}</strong><span>{rules.filter(row => row.is_active).length} active rules</span></article>
        <article><small>Partner enquiries</small><strong>{enquiries.length}</strong><span>{enquiries.filter(row => row.status === "new").length} new enquiries</span></article>
      </div>
      <div className="sb-loyalty-overview-grid">
        <article className="sb-data-card"><h2>Programme controls</h2><p>Coins are earned under the configured rules, redeemed oldest-first, and expire after their earning lot's expiry date.</p><ul><li>Coin value: ₹1 per Super Coin</li><li>Redemption allocation: FIFO</li><li>Default expiry: 365 days</li><li>Accounting: requires approved Finance mappings</li></ul><button type="button" onClick={() => setTab("rules")}>Manage earning rules →</button></article>
        <article className="sb-data-card"><h2>Expiry processing</h2><p>Process due lots through the existing transactional expiry service. The service posts the associated accounting entries.</p><button type="button" className="sb-loyalty-danger" disabled={busy} onClick={expire}>Process due coin expiry</button></article>
      </div>
      {(sourceErrors.accounts || sourceErrors.rules || sourceErrors.enquiries) && <div className="sb-data-card"><h2>Data source status</h2>{Object.entries(sourceErrors).map(([key, message]) => <p key={key}><strong>{title(key)}:</strong> {message}</p>)}</div>}
    </>}
    {!loading && tab === "members" && <>
      <div className="sb-data-heading"><div><h2>Loyalty members</h2><span>{accounts.length} accounts loaded</span></div><input aria-label="Search loyalty members" placeholder="Search email or card number" value={search} onChange={e => setSearch(e.target.value)} /></div>
      {sourceErrors.accounts ? <p className="sb-empty">Member accounts unavailable: {sourceErrors.accounts}</p> : <div className="sb-table-wrap"><table><thead><tr><th>Member / email</th><th>Card number</th><th>Available coins</th><th>Joined</th><th>Ledger</th></tr></thead><tbody>{filtered.map(account => <tr key={account.id}><td>{account.customer_email}</td><td>{account.card_number}</td><td>{Number(account.available_coins || 0).toLocaleString("en-IN")}</td><td>{date(account.created_at)}</td><td><button type="button" className="sb-loyalty-link" onClick={() => loadLedger(account)}>View ledger</button></td></tr>)}</tbody></table>{!filtered.length && <p className="sb-empty">No matching loyalty members.</p>}</div>}
      {selected && <article className="sb-data-card sb-loyalty-ledger"><h2>Ledger · {selected.customer_email}</h2><p>{selected.card_number} · Current available balance: {Number(selected.available_coins || 0).toLocaleString("en-IN")} coins</p>{transactions.length ? <div className="sb-table-wrap"><table><thead><tr><th>Date</th><th>Type</th><th>Coins</th><th>Order / reference</th><th>Description</th><th>Expires</th></tr></thead><tbody>{transactions.map(row => <tr key={row.id}><td>{date(row.created_at)}</td><td>{title(row.transaction_type)}</td><td>{Number(row.coins).toLocaleString("en-IN")}</td><td>{row.order_reference || "—"}</td><td>{row.description || "—"}</td><td>{date(row.expires_at)}</td></tr>)}</tbody></table></div> : <p className="sb-empty">No ledger transactions found, or the ledger is still loading.</p>}</article>}
    </>}
    {!loading && tab === "rules" && <>
      <div className="sb-data-heading"><div><h2>Earning rules</h2><span>Most specific active rule takes precedence: product, category, then default.</span></div></div>
      <form className="sb-loyalty-form" onSubmit={saveRule}>
        <label>Rule scope<select value={rule.scope_type} onChange={e => setRule(value => ({ ...value, scope_type: e.target.value, scope_id: "" }))}><option value="default">Default</option><option value="category">Category ID</option><option value="product">Product ID</option></select></label>
        {rule.scope_type !== "default" && <label>{title(rule.scope_type)} ID<input required type="number" min="1" value={rule.scope_id} onChange={e => setRule(value => ({ ...value, scope_id: e.target.value }))} /></label>}
        <label>Coins per ₹100<input required type="number" min="0" max="100000" step="0.01" value={rule.coins_per_100} onChange={e => setRule(value => ({ ...value, coins_per_100: e.target.value }))} /></label>
        <label className="sb-loyalty-check"><input type="checkbox" checked={rule.is_active} onChange={e => setRule(value => ({ ...value, is_active: e.target.checked }))} /> Active</label>
        <button type="submit" disabled={busy}>{busy ? "Saving…" : "Save earning rule"}</button>
      </form>
      {sourceErrors.rules ? <p className="sb-empty">Rules unavailable: {sourceErrors.rules}</p> : <div className="sb-table-wrap"><table><thead><tr><th>Scope</th><th>Scope ID</th><th>Coins / ₹100</th><th>Status</th><th>Updated</th></tr></thead><tbody>{rules.map(row => <tr key={row.id}><td>{title(row.scope_type)}</td><td>{row.scope_id ?? "All eligible orders"}</td><td>{row.coins_per_100}</td><td><span className={row.is_active ? "sb-loyalty-status active" : "sb-loyalty-status"}>{row.is_active ? "Active" : "Inactive"}</span></td><td>{date(row.updated_at)}</td></tr>)}</tbody></table>{!rules.length && <p className="sb-empty">No earning rules configured.</p>}</div>}
    </>}
    {!loading && tab === "adjust" && <>
      <div className="sb-data-heading"><div><h2>Manual coin adjustment</h2><span>Every adjustment is recorded in the ledger and requires Finance-approved accounting mappings.</span></div></div>
      <form className="sb-loyalty-form" onSubmit={submitAdjustment}>
        <label>Customer email<input required type="email" value={adjustment.customer_email} onChange={e => setAdjustment(value => ({ ...value, customer_email: e.target.value }))} /></label>
        <label>Direction<select value={adjustment.direction} onChange={e => setAdjustment(value => ({ ...value, direction: e.target.value }))}><option value="credit">Credit coins</option><option value="debit">Debit coins</option></select></label>
        <label>Coins<input required type="number" min="1" max="10000000" step="1" value={adjustment.coins} onChange={e => setAdjustment(value => ({ ...value, coins: e.target.value }))} /></label>
        <label className="wide">Reason<input required minLength="5" maxLength="500" value={adjustment.reason} onChange={e => setAdjustment(value => ({ ...value, reason: e.target.value }))} /></label>
        <button type="submit" disabled={busy}>{busy ? "Posting…" : "Post adjustment"}</button>
      </form>
    </>}
    {!loading && tab === "enquiries" && <>
      <div className="sb-data-heading"><div><h2>Partner enquiries</h2><span>Incoming loyalty programme partnership requests.</span></div></div>
      {sourceErrors.enquiries ? <p className="sb-empty">Partner enquiries unavailable: {sourceErrors.enquiries}</p> : <div className="sb-table-wrap"><table><thead><tr><th>Received</th><th>Business</th><th>Contact</th><th>Type</th><th>Message</th><th>Status</th></tr></thead><tbody>{enquiries.map(row => <tr key={row.id}><td>{date(row.created_at)}</td><td>{row.business_name}</td><td>{row.name}<br />{row.email}<br />{row.phone}</td><td>{row.partnership_type}</td><td>{row.message}</td><td><select aria-label={"Status for " + row.business_name} value={row.status} disabled={busy} onChange={e => updateEnquiry(row.id, e.target.value)}><option value="new">New</option><option value="reviewing">Reviewing</option><option value="contacted">Contacted</option><option value="accepted">Accepted</option><option value="declined">Declined</option><option value="closed">Closed</option></select></td></tr>)}</tbody></table>{!enquiries.length && <p className="sb-empty">No partner enquiries received.</p>}</div>}
    </>}
  </section>;
}
