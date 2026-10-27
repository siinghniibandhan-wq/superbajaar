import { useCallback, useEffect, useState } from "react";
import { apiRequest } from "../../services/api.js";

export default function PricingWorkspace({ onBack }) {
  const [items, setItems] = useState([]);
  const [drafts, setDrafts] = useState({});
  const [loading, setLoading] = useState(true);
  const [busyId, setBusyId] = useState(null);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const load = useCallback(async () => {
    setLoading(true); setError("");
    try {
      const result = await apiRequest("/catalogue/variants?limit=500");
      setItems(result.items || []);
      setDrafts(Object.fromEntries((result.items || []).map(item => [item.id, {
        selling_price: String(item.selling_price), mrp: String(item.mrp),
        cost_price: item.cost_price == null ? "" : String(item.cost_price),
      }])));
    } catch (e) { setError(e.message || "Unable to load variant prices."); }
    finally { setLoading(false); }
  }, []);
  useEffect(() => { load(); }, [load]);
  function change(id, field, value) { setDrafts(old => ({ ...old, [id]: { ...old[id], [field]: value } })); }
  async function save(item) {
    const draft = drafts[item.id]; setBusyId(item.id); setError(""); setNotice("");
    const selling = Number(draft.selling_price), mrp = Number(draft.mrp);
    if (draft.selling_price.trim() === "" || draft.mrp.trim() === "" || !Number.isFinite(selling) || !Number.isFinite(mrp) || selling < 0 || mrp < selling) {
      setError("Enter valid prices. MRP must be equal to or higher than selling price."); setBusyId(null); return;
    }
    if (draft.cost_price !== "" && (!Number.isFinite(Number(draft.cost_price)) || Number(draft.cost_price) < 0)) {
      setError("Cost price must be blank or a non-negative number."); setBusyId(null); return;
    }
    try {
      await apiRequest("/catalogue/variants/" + item.id + "/price", { method: "PUT", body: JSON.stringify({
        selling_price: selling, mrp, cost_price: draft.cost_price === "" ? null : Number(draft.cost_price),
      })});
      setNotice("Price saved for " + item.sku + "."); await load();
    } catch (e) { setError(e.message || "Unable to save price."); }
    finally { setBusyId(null); }
  }
  return <section className="sb-workspace sb-pricing">
    <button className="sb-back" onClick={onBack} type="button">← All workspaces</button>
    <p className="sb-eyebrow">COMMERCE · PRICING</p><h1>Pricing & Promotions</h1>
    <p>Manage SKU-level selling price, MRP and cost price. Promotion rules are not yet enabled.</p>
    <div className="sb-pricing-toolbar"><strong>{items.length} active variants</strong><button type="button" onClick={load} disabled={loading}>Refresh prices</button></div>
    {error && <p className="sb-alert" role="alert">{error}</p>}
    {notice && <p className="sb-success" role="status">{notice}</p>}
    {loading ? <p className="sb-empty">Loading prices…</p> : items.length ? <div className="sb-pricing-list">{items.map(item => <article className="sb-price-card" key={item.id}>
      <div className="sb-price-product"><strong>{item.product_name}</strong><small>SKU: {item.sku}{item.attributes && Object.keys(item.attributes).length ? " · " + Object.values(item.attributes).join(" / ") : ""}</small></div>
      <div className="sb-price-fields">
        <label>Selling price ₹<input type="number" min="0" step="0.01" value={drafts[item.id]?.selling_price ?? ""} onChange={e=>change(item.id,"selling_price",e.target.value)}/></label>
        <label>MRP ₹<input type="number" min="0" step="0.01" value={drafts[item.id]?.mrp ?? ""} onChange={e=>change(item.id,"mrp",e.target.value)}/></label>
        <label>Cost price ₹<input type="number" min="0" step="0.01" value={drafts[item.id]?.cost_price ?? ""} onChange={e=>change(item.id,"cost_price",e.target.value)}/></label>
      </div>
      <button className="sb-primary" type="button" disabled={busyId !== null} onClick={()=>save(item)}>{busyId === item.id ? "Saving…" : "Save price"}</button>
    </article>)}</div> : <p className="sb-empty">No active variants found. Create a product and SKU variant in Catalogue first.</p>}
  </section>;
}
