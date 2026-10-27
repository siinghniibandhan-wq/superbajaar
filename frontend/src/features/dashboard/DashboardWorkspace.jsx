import { useEffect, useState } from "react";
import { apiRequest } from "../../services/api.js";

const money = value => new Intl.NumberFormat("en-IN", { style: "currency", currency: "INR", maximumFractionDigits: 2 }).format(Number(value || 0));
export default function DashboardWorkspace({ onOpen }) {
  const [data, setData] = useState({ products: [], variants: [], balances: [] });
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  async function refresh() {
    setLoading(true); setError("");
    try {
      const [products, variants, balances] = await Promise.all([
        apiRequest("/catalogue/products?status=all&limit=500"),
        apiRequest("/catalogue/variants?limit=500"),
        apiRequest("/inventory/balances?limit=500"),
      ]);
      setData({ products: products.items || products || [], variants: variants.items || [], balances: balances.items || [] });
    } catch (e) { setError(e.message || "Dashboard data is unavailable."); }
    finally { setLoading(false); }
  }
  useEffect(() => { refresh(); }, []);
  const activeProducts = data.products.filter(p => p.status === "active").length;
  const totalStock = data.balances.reduce((sum, row) => sum + Number(row.on_hand || 0), 0);
  const lowStock = data.balances.filter(row => Number(row.on_hand || 0) <= 5).length;
  const outOfStock = data.balances.filter(row => Number(row.on_hand || 0) === 0).length;
  const inventoryValue = data.balances.reduce((sum, row) => {
    const variant = data.variants.find(v => Number(v.id) === Number(row.variant_id));
    return sum + Number(row.on_hand || 0) * Number(variant?.cost_price || 0);
  }, 0);
  return <section className="sb-workspace sb-dashboard">
    <p className="sb-eyebrow">SUPER BAJAAR · BUSINESS OVERVIEW</p><h1>Dashboard</h1>
    <p>Live catalogue and stock indicators from the backend. Orders and revenue appear only after the order workflow is implemented.</p>
    <div className="sb-dashboard-actions"><button type="button" onClick={refresh} disabled={loading}>{loading ? "Refreshing…" : "Refresh overview"}</button></div>
    {error && <p className="sb-alert" role="alert">{error}</p>}
    <div className="sb-kpi-grid">
      <article><small>Active products</small><strong>{loading ? "—" : activeProducts}</strong><span>Published catalogue</span><button type="button" onClick={()=>onOpen("catalogue")}>Open Catalogue →</button></article>
      <article><small>Active variants</small><strong>{loading ? "—" : data.variants.length}</strong><span>Sellable SKU variants</span><button type="button" onClick={()=>onOpen("catalogue")}>Manage SKUs →</button></article>
      <article><small>Units on hand</small><strong>{loading ? "—" : totalStock.toLocaleString("en-IN")}</strong><span>Across recorded stock locations</span><button type="button" onClick={()=>onOpen("inventory")}>Open Inventory →</button></article>
      <article><small>Low-stock balances</small><strong>{loading ? "—" : lowStock}</strong><span>At or below 5 units per location</span><button type="button" onClick={()=>onOpen("inventory")}>Review stock →</button></article>
      <article><small>Out-of-stock balances</small><strong>{loading ? "—" : outOfStock}</strong><span>Zero units recorded</span><button type="button" onClick={()=>onOpen("inventory")}>Review stock →</button></article>
      <article><small>Recorded stock cost</small><strong>{loading ? "—" : money(inventoryValue)}</strong><span>On-hand units × variant cost</span><button type="button" onClick={()=>onOpen("reports")}>Reports →</button></article>
    </div>
    <div className="sb-notice"><strong>Order metrics not shown</strong><span>Orders, payments, customers and revenue are deliberately not fabricated. Their database workflows must be implemented before those figures can be reported.</span></div>
  </section>;
}
