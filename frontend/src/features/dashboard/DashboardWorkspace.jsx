import { useEffect, useState } from "react";
import { apiRequest } from "../../services/api.js";

const money = value => new Intl.NumberFormat("en-IN", { style: "currency", currency: "INR", maximumFractionDigits: 2 }).format(Number(value || 0));
const itemsOf = result => Array.isArray(result?.items) ? result.items : Array.isArray(result) ? result : [];

export default function DashboardWorkspace({ onOpen }) {
  const [data, setData] = useState({ products: [], variants: [], balances: [], orders: [], payments: [] });
  const [loading, setLoading] = useState(true);
  const [errors, setErrors] = useState([]);

  async function refresh() {
    setLoading(true);
    const sources = [
      ["products", "/catalogue/products?status=all&limit=500"],
      ["variants", "/catalogue/variants?limit=500"],
      ["balances", "/inventory/balances?limit=500"],
      ["orders", "/orders?limit=500"],
      ["payments", "/payments?limit=500"],
    ];
    const results = await Promise.allSettled(sources.map(([, path]) => apiRequest(path)));
    const next = { products: [], variants: [], balances: [], orders: [], payments: [] };
    const failed = [];
    results.forEach((result, index) => {
      const [key, path] = sources[index];
      if (result.status === "fulfilled") next[key] = itemsOf(result.value);
      else failed.push({ key, message: result.reason?.message || "Unable to load data", path });
    });
    setData(next);
    setErrors(failed);
    setLoading(false);
  }

  useEffect(() => { refresh(); }, []);

  const activeProducts = data.products.filter(p => p.status === "active").length;
  const totalStock = data.balances.reduce((sum, row) => sum + Number(row.on_hand || 0), 0);
  const lowStock = data.balances.filter(row => Number(row.on_hand || 0) > 0 && Number(row.on_hand || 0) <= 5).length;
  const outOfStock = data.balances.filter(row => Number(row.on_hand || 0) === 0).length;
  const inventoryValue = data.balances.reduce((sum, row) => {
    const variant = data.variants.find(v => Number(v.id) === Number(row.variant_id));
    return sum + Number(row.on_hand || 0) * Number(variant?.cost_price || 0);
  }, 0);
  const orderValue = data.orders.reduce((sum, row) => sum + Number(row.total || 0), 0);
  const pendingOrders = data.orders.filter(row => ["draft", "placed", "confirmed", "processing", "ready_for_dispatch"].includes(row.status)).length;
  const pendingPayments = data.payments.filter(row => ["pending", "authorized"].includes(row.status)).length;
  const recordedPaymentAmount = data.payments.reduce((sum, row) => sum + Number(row.amount || 0), 0);

  return <section className="sb-workspace sb-dashboard">
    <p className="sb-eyebrow">SUPER BAJAAR · BUSINESS OVERVIEW</p><h1>Dashboard</h1>
    <p>Live snapshot from catalogue, inventory, orders and payment records. Figures include only successfully loaded API sources.</p>
    <div className="sb-dashboard-actions"><button type="button" onClick={refresh} disabled={loading}>{loading ? "Refreshing…" : "Refresh overview"}</button></div>
    {errors.length > 0 && <div className="sb-alert" role="alert"><strong>{errors.length} data source(s) unavailable.</strong><ul>{errors.map(error => <li key={error.key}>{error.key}: {error.message}</li>)}</ul><span>Cards for unavailable sources may show zero. Resolve the API errors before relying on this snapshot.</span></div>}
    <div className="sb-kpi-grid">
      <article><small>Active products</small><strong>{loading ? "—" : activeProducts}</strong><span>Published catalogue</span><button type="button" onClick={()=>onOpen("catalogue")}>Open Catalogue →</button></article>
      <article><small>Active variants</small><strong>{loading ? "—" : data.variants.length}</strong><span>Sellable SKU variants loaded</span><button type="button" onClick={()=>onOpen("catalogue")}>Manage SKUs →</button></article>
      <article><small>Units on hand</small><strong>{loading ? "—" : totalStock.toLocaleString("en-IN")}</strong><span>Across recorded stock locations</span><button type="button" onClick={()=>onOpen("inventory")}>Open Inventory →</button></article>
      <article><small>Low-stock balances</small><strong>{loading ? "—" : lowStock}</strong><span>1–5 units per location</span><button type="button" onClick={()=>onOpen("inventory")}>Review stock →</button></article>
      <article><small>Out-of-stock balances</small><strong>{loading ? "—" : outOfStock}</strong><span>Zero units recorded</span><button type="button" onClick={()=>onOpen("inventory")}>Review stock →</button></article>
      <article><small>Recorded stock cost</small><strong>{loading ? "—" : money(inventoryValue)}</strong><span>On-hand units × variant cost</span><button type="button" onClick={()=>onOpen("reports")}>Reports →</button></article>
      <article><small>Orders loaded</small><strong>{loading ? "—" : data.orders.length}</strong><span>{pendingOrders} open / in-progress orders</span><button type="button" onClick={()=>onOpen("orders")}>Manage orders →</button></article>
      <article><small>Recorded order value</small><strong>{loading ? "—" : money(orderValue)}</strong><span>All loaded orders; not recognised revenue</span><button type="button" onClick={()=>onOpen("reports")}>View reports →</button></article>
      <article><small>Pending payments</small><strong>{loading ? "—" : pendingPayments}</strong><span>Pending or authorised records</span><button type="button" onClick={()=>onOpen("payments")}>Review payments →</button></article>
      <article><small>Payment records</small><strong>{loading ? "—" : data.payments.length}</strong><span>{loading ? "—" : money(recordedPaymentAmount)} recorded, any status</span><button type="button" onClick={()=>onOpen("payments")}>Open payments →</button></article>
    </div>
    <div className="sb-notice"><strong>Financial figures are operational records</strong><span>Order value is not recognised revenue, and payment records may still be pending. Gateway capture, refunds, accounting reconciliation and final revenue reporting require their respective verified workflows.</span></div>
  </section>;
}
