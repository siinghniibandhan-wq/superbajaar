import { useCallback, useEffect, useState } from "react";
import { apiRequest } from "../../services/api.js";

const money = value => new Intl.NumberFormat("en-IN", { style: "currency", currency: "INR", maximumFractionDigits: 2 }).format(Number(value || 0));
export default function ReportsWorkspace({ onBack }) {
  const [data, setData] = useState({ orders: [], payments: [], balances: [], products: [], variants: [] });
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const load = useCallback(async () => {
    setLoading(true); setError("");
    const results = await Promise.allSettled([
      apiRequest("/orders?limit=500"), apiRequest("/payments?limit=500"),
      apiRequest("/inventory/balances?limit=500"), apiRequest("/catalogue/products?limit=500"),
      apiRequest("/catalogue/variants?limit=500"),
    ]);
    const failed = results.filter(r => r.status === "rejected");
    setData({
      orders: results[0].status === "fulfilled" ? results[0].value.items || [] : [],
      payments: results[1].status === "fulfilled" ? results[1].value.items || [] : [],
      balances: results[2].status === "fulfilled" ? results[2].value.items || [] : [],
      products: results[3].status === "fulfilled" ? results[3].value.items || [] : [],
      variants: results[4].status === "fulfilled" ? results[4].value.items || [] : [],
    });
    if (failed.length) setError(failed.length + " report source(s) could not be loaded. Values below include only successfully loaded sources.");
    setLoading(false);
  }, []);
  useEffect(() => { load(); }, [load]);
  const orderValue = data.orders.reduce((sum, row) => sum + Number(row.total || 0), 0);
  const paymentValue = data.payments.reduce((sum, row) => sum + Number(row.amount || 0), 0);
  const pendingPayments = data.payments.filter(row => ["pending", "authorized"].includes(row.status));
  const stockUnits = data.balances.reduce((sum, row) => sum + Number(row.on_hand || 0), 0);
  const lowStock = data.balances.filter(row => Number(row.on_hand || 0) <= 5).length;
  const statuses = Object.entries(data.orders.reduce((counts, row) => { counts[row.status] = (counts[row.status] || 0) + 1; return counts; }, {}));
  return <section className="sb-workspace">
    <button className="sb-back" type="button" onClick={onBack}>← All workspaces</button>
    <p className="sb-eyebrow">BUSINESS MANAGEMENT · REPORTING</p><h1>Reports</h1>
    <p>Live summaries from the current orders, payment, catalogue and inventory APIs. No separate reporting tables are created.</p>
    {error && <p className="sb-alert" role="alert">{error}</p>}
    <div className="sb-data-heading"><span>{loading ? "Refreshing report data…" : "Latest API snapshot"}</span><button type="button" onClick={load} disabled={loading}>{loading ? "Loading…" : "Refresh reports"}</button></div>
    <div className="sb-report-grid">
      <article className="sb-report-card"><small>Orders loaded</small><strong>{data.orders.length}</strong><span>Order value: {money(orderValue)}</span></article>
      <article className="sb-report-card"><small>Payment records</small><strong>{data.payments.length}</strong><span>Recorded amount: {money(paymentValue)}</span></article>
      <article className="sb-report-card"><small>Pending / authorized</small><strong>{pendingPayments.length}</strong><span>Amount: {money(pendingPayments.reduce((sum, row) => sum + Number(row.amount || 0), 0))}</span></article>
      <article className="sb-report-card"><small>Catalogue</small><strong>{data.products.length} products</strong><span>{data.variants.length} variants loaded</span></article>
      <article className="sb-report-card"><small>Stock on hand</small><strong>{stockUnits.toLocaleString("en-IN")}</strong><span>{lowStock} balance rows at or below 5 units</span></article>
    </div>
    <div className="sb-data-card"><h2>Orders by status</h2>{statuses.length ? <div className="sb-table-wrap"><table><thead><tr><th>Status</th><th>Orders</th></tr></thead><tbody>{statuses.map(([status,count]) => <tr key={status}><td>{status.replaceAll("_"," ")}</td><td>{count}</td></tr>)}</tbody></table></div> : <p className="sb-empty">No order rows loaded.</p>}</div>
    <div className="sb-data-card"><h2>Recent orders</h2>{data.orders.length ? <div className="sb-table-wrap"><table><thead><tr><th>Order</th><th>Customer</th><th>Channel</th><th>Status</th><th>Total</th><th>Created</th></tr></thead><tbody>{data.orders.slice(0,25).map(row => <tr key={row.id}><td>{row.order_number}</td><td>{row.customer_name}</td><td>{row.channel}</td><td>{row.status}</td><td>{money(row.total)}</td><td>{row.created_at ? new Date(row.created_at).toLocaleString() : "—"}</td></tr>)}</tbody></table></div> : <p className="sb-empty">No order rows loaded.</p>}</div>
    <div className="sb-data-card"><h2>Recent payment records</h2>{data.payments.length ? <div className="sb-table-wrap"><table><thead><tr><th>Reference</th><th>Order</th><th>Method</th><th>Status</th><th>Amount</th></tr></thead><tbody>{data.payments.slice(0,25).map(row => <tr key={row.id}><td>{row.payment_reference}</td><td>{row.order_number}</td><td>{row.method}</td><td>{row.status}</td><td>{money(row.amount)}</td></tr>)}</tbody></table></div> : <p className="sb-empty">No payment rows loaded.</p>}</div>
  </section>;
}
