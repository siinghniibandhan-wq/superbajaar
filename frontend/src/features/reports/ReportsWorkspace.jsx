import { useCallback, useEffect, useState } from "react";
import { apiRequest } from "../../services/api.js";

const money = value => new Intl.NumberFormat("en-IN", { style: "currency", currency: "INR", maximumFractionDigits: 2 }).format(Number(value || 0));
const localDate = value => new Date(value.getTime() - value.getTimezoneOffset() * 60000).toISOString().slice(0, 10);
const today = () => localDate(new Date());
const monthStart = () => today().slice(0, 8) + "01";
export default function ReportsWorkspace({ onBack }) {
  const [data, setData] = useState({ orders: [], payments: [], balances: [], products: [], variants: [] });
  const [summary, setSummary] = useState(null);
  const [summaryError, setSummaryError] = useState("");
  const [fromDate, setFromDate] = useState(monthStart);
  const [toDate, setToDate] = useState(today);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [sourceErrors, setSourceErrors] = useState({});
  const [refreshedAt, setRefreshedAt] = useState(null);
  const load = useCallback(async () => {
    if (!fromDate || !toDate || fromDate > toDate) {
      setSummary(null); setSummaryError("Choose a valid reporting date range"); setLoading(false); return;
    }
    setLoading(true); setError("");
    const results = await Promise.allSettled([
      apiRequest("/orders?limit=500"), apiRequest("/payments?limit=500"),
      apiRequest("/inventory/balances?limit=500"), apiRequest("/catalogue/products?limit=500"),
      apiRequest("/catalogue/variants?limit=500"),
      apiRequest("/reports/overview?from_date=" + fromDate + "&to_date=" + toDate),
    ]);
    const keys = ["orders", "payments", "balances", "products", "variants", "overview"];
    const failures = {};
    results.forEach((result, index) => { if (result.status === "rejected") failures[keys[index]] = result.reason?.message || "Source unavailable"; });
    setSourceErrors(failures);
    if (results[5].status === "fulfilled") { setSummary(results[5].value); setSummaryError(""); }
    else { setSummary(null); setSummaryError(results[5].reason?.message || "Full report summary unavailable"); }
    setData({
      orders: results[0].status === "fulfilled" ? results[0].value.items || [] : [],
      payments: results[1].status === "fulfilled" ? results[1].value.items || [] : [],
      balances: results[2].status === "fulfilled" ? results[2].value.items || [] : [],
      products: results[3].status === "fulfilled" ? results[3].value.items || [] : [],
      variants: results[4].status === "fulfilled" ? results[4].value.items || [] : [],
    });
    setError(Object.keys(failures).length ? Object.keys(failures).length + " report source(s) could not be loaded. A failed source is shown as unavailable, not as zero." : "");
    setRefreshedAt(new Date().toISOString()); setLoading(false);
  }, [fromDate, toDate]);
  useEffect(() => { load(); }, [load]);
  const statuses = summary?.order_statuses?.map(row => [row.status, row.count]) || Object.entries(data.orders.reduce((counts, row) => { counts[row.status] = (counts[row.status] || 0) + 1; return counts; }, {}));
  return <section className="sb-workspace">
    <button className="sb-back" type="button" onClick={onBack}>← All workspaces</button>
    <p className="sb-eyebrow">BUSINESS MANAGEMENT · REPORTING</p><h1>Reports</h1>
    <p>Server-side aggregates across all matching orders and payments, with current inventory and catalogue totals. Recent-record tables are bounded snapshots; no separate reporting tables are created.</p>
    {error && <p className="sb-alert" role="alert">{error}</p>}
    <div className="sb-data-heading">
      <div><span>{loading ? "Refreshing report data…" : "Full database aggregates" + (refreshedAt ? " · " + new Date(refreshedAt).toLocaleString("en-IN") : "")}</span>
        <label>From <input type="date" value={fromDate} max={toDate} onChange={e => setFromDate(e.target.value)} /></label>
        <label>To <input type="date" value={toDate} min={fromDate} max={today()} onChange={e => setToDate(e.target.value)} /></label>
      </div>
      <button type="button" onClick={load} disabled={loading || !fromDate || !toDate || fromDate > toDate}>{loading ? "Loading…" : "Refresh reports"}</button>
    </div>
    {summaryError && <p className="sb-alert" role="alert">Full report aggregates unavailable: {summaryError}</p>}
    <div className="sb-report-grid">
      <article className="sb-report-card"><small>Orders · selected period</small><strong>{summaryError ? "Unavailable" : Number(summary?.orders?.order_count || 0).toLocaleString("en-IN")}</strong><span>{summaryError ? "Aggregate source unavailable" : "Active order value: " + money(summary?.orders?.active_order_value)}</span></article>
      <article className="sb-report-card"><small>Captured payments</small><strong>{summaryError ? "Unavailable" : money(summary?.payments?.captured_amount)}</strong><span>{summaryError ? "Aggregate source unavailable" : Number(summary?.payments?.captured_count || 0).toLocaleString("en-IN") + " captured records"}</span></article>
      <article className="sb-report-card"><small>Pending / authorized</small><strong>{summaryError ? "Unavailable" : Number(summary?.payments?.pending_count || 0).toLocaleString("en-IN")}</strong><span>{summaryError ? "Aggregate source unavailable" : "Amount: " + money(summary?.payments?.pending_amount)}</span></article>
      <article className="sb-report-card"><small>Active catalogue</small><strong>{summaryError ? "Unavailable" : Number(summary?.catalogue?.active_products || 0).toLocaleString("en-IN") + " products"}</strong><span>{summaryError ? "Aggregate source unavailable" : Number(summary?.catalogue?.active_variants || 0).toLocaleString("en-IN") + " variants"}</span></article>
      <article className="sb-report-card"><small>Stock on hand</small><strong>{summaryError ? "Unavailable" : Number(summary?.inventory?.stock_units || 0).toLocaleString("en-IN")}</strong><span>{summaryError ? "Aggregate source unavailable" : Number(summary?.inventory?.low_stock_rows || 0) + " low-stock rows · " + Number(summary?.inventory?.out_of_stock_rows || 0) + " out of stock"}</span></article>
    </div>
    <div className="sb-data-card"><h2>Orders by status</h2>{summaryError ? <p className="sb-empty">Aggregate status distribution unavailable.</p> : statuses.length ? <div className="sb-table-wrap"><table><thead><tr><th>Status</th><th>Orders</th></tr></thead><tbody>{statuses.map(([status,count]) => <tr key={status}><td>{status.replaceAll("_"," ")}</td><td>{count}</td></tr>)}</tbody></table></div> : <p className="sb-empty">No order rows loaded.</p>}</div>
    <div className="sb-data-card"><h2>Recent orders</h2>{sourceErrors.orders ? <p className="sb-empty">Orders source unavailable; recent orders cannot be displayed.</p> : data.orders.length ? <div className="sb-table-wrap"><table><thead><tr><th>Order</th><th>Customer</th><th>Channel</th><th>Status</th><th>Total</th><th>Created</th></tr></thead><tbody>{data.orders.slice(0,25).map(row => <tr key={row.id}><td>{row.order_number}</td><td>{row.customer_name}</td><td>{row.channel}</td><td>{row.status}</td><td>{money(row.total)}</td><td>{row.created_at ? new Date(row.created_at).toLocaleString() : "—"}</td></tr>)}</tbody></table></div> : <p className="sb-empty">No order rows loaded.</p>}</div>
    <div className="sb-data-card"><h2>Recent payment records</h2>{sourceErrors.payments ? <p className="sb-empty">Payments source unavailable; payment records cannot be displayed.</p> : data.payments.length ? <div className="sb-table-wrap"><table><thead><tr><th>Reference</th><th>Order</th><th>Method</th><th>Status</th><th>Amount</th></tr></thead><tbody>{data.payments.slice(0,25).map(row => <tr key={row.id}><td>{row.payment_reference}</td><td>{row.order_number}</td><td>{row.method}</td><td>{row.status}</td><td>{money(row.amount)}</td></tr>)}</tbody></table></div> : <p className="sb-empty">No payment rows loaded.</p>}</div>
  </section>;
}
