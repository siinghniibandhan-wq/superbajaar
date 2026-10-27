import { useEffect, useState } from "react";
import { apiRequest } from "../../services/api.js";

export default function InventoryWorkspace({ onBack }) {
  const [locations, setLocations] = useState([]);
  const [products, setProducts] = useState([]);
  const [variants, setVariants] = useState([]);
  const [balances, setBalances] = useState([]);
  const [movements, setMovements] = useState([]);
  const [productId, setProductId] = useState("");
  const [form, setForm] = useState({ variant_id: "", location_id: "", quantity: "", note: "" });
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");
  const [busy, setBusy] = useState(false);

  async function loadBase() {
    try {
      const [l, p, b, m] = await Promise.all([
        apiRequest("/inventory/locations"),
        apiRequest("/catalogue/products?status=all"),
        apiRequest("/inventory/balances"),
        apiRequest("/inventory/movements"),
      ]);
      setLocations(l.items || []); setProducts(p.items || []); setBalances(b.items || []); setMovements(m.items || []);
    } catch (e) { setError(e.message || "Inventory API unavailable."); }
  }
  useEffect(() => { loadBase(); }, []);
  useEffect(() => {
    if (!productId) { setVariants([]); return; }
    apiRequest("/catalogue/products/" + productId + "/variants")
      .then(result => setVariants(result.items || []))
      .catch(e => setError(e.message || "Unable to load variants."));
  }, [productId]);

  async function submit(event) {
    event.preventDefault(); setBusy(true); setError(""); setMessage("");
    try {
      await apiRequest("/inventory/adjustments", { method: "POST", body: JSON.stringify({
        variant_id: Number(form.variant_id), location_id: Number(form.location_id),
        quantity: Number(form.quantity), note: form.note,
      })});
      setForm(v => ({ ...v, quantity: "", note: "" }));
      setMessage("Stock receipt adjustment recorded."); await loadBase();
    } catch (e) { setError(e.message || "Stock adjustment failed."); }
    finally { setBusy(false); }
  }

  return <section className="sb-workspace">
    <button className="sb-back" type="button" onClick={onBack}>← All workspaces</button>
    <p className="sb-eyebrow">STOCK CONTROL</p><h1>Inventory</h1>
    <p>Balances, available stock, movement history and positive stock receipt adjustments.</p>
    {error && <p className="sb-alert" role="alert">{error}</p>}
    {message && <p className="sb-success" role="status">{message}</p>}
    <form className="sb-form" onSubmit={submit}>
      <h2>Record stock receipt adjustment</h2>
      <p className="sb-muted">This operation only adds stock. It does not implement stock reduction, transfers, reservations or cycle counts.</p>
      <div className="sb-form-grid">
        <label>Product<select required value={productId} onChange={e=>{setProductId(e.target.value);setForm(v=>({...v,variant_id:""}));}}><option value="">Choose product</option>{products.map(p=><option key={p.id} value={p.id}>{p.name}</option>)}</select></label>
        <label>Variant / SKU<select required value={form.variant_id} onChange={e=>setForm(v=>({...v,variant_id:e.target.value}))}><option value="">Choose variant</option>{variants.map(v=><option key={v.id} value={v.id}>{v.sku} · ₹{v.selling_price}</option>)}</select></label>
        <label>Stock location<select required value={form.location_id} onChange={e=>setForm(v=>({...v,location_id:e.target.value}))}><option value="">Choose location</option>{locations.map(l=><option key={l.id} value={l.id}>{l.name} ({l.location_type})</option>)}</select></label>
        <label>Quantity to add<input required type="number" min="0.001" step="0.001" value={form.quantity} onChange={e=>setForm(v=>({...v,quantity:e.target.value}))}/></label>
        <label className="sb-span-all">Reason / reference<input required minLength="3" maxLength="500" value={form.note} onChange={e=>setForm(v=>({...v,note:e.target.value}))}/></label>
      </div>
      <button className="sb-primary" disabled={busy || !locations.length} type="submit">{busy ? "Saving…" : "Record adjustment"}</button>
      {!locations.length && <p className="sb-muted">No active stock locations are configured.</p>}
    </form>
    <div className="sb-data-card"><div className="sb-data-heading"><h2>Stock balances ({balances.length})</h2><button type="button" onClick={loadBase}>Refresh</button></div>
      {balances.length ? <div className="sb-table-wrap"><table><thead><tr><th>SKU</th><th>Location</th><th>On hand</th><th>Reserved</th><th>Available</th></tr></thead><tbody>{balances.map((b,i)=><tr key={b.variant_id+"-"+b.location_id+"-"+i}><td>{b.sku}</td><td>{b.location_name}</td><td>{b.on_hand}</td><td>{b.reserved}</td><td>{b.available}</td></tr>)}</tbody></table></div> : <p className="sb-empty">No stock balances found.</p>}
    </div>
    <div className="sb-data-card"><h2>Recent movements ({movements.length})</h2>
      {movements.length ? <div className="sb-table-wrap"><table><thead><tr><th>Date</th><th>SKU ID</th><th>Location ID</th><th>Type</th><th>Quantity</th><th>Note</th></tr></thead><tbody>{movements.map(m=><tr key={m.id}><td>{new Date(m.created_at).toLocaleString()}</td><td>{m.variant_id}</td><td>{m.location_id}</td><td>{m.movement_type}</td><td>{m.quantity}</td><td>{m.note}</td></tr>)}</tbody></table></div> : <p className="sb-empty">No inventory movements found.</p>}
    </div>
  </section>;
}
