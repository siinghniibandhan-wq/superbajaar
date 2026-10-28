import { useEffect, useState } from "react";
import { apiRequest } from "../../services/api.js";
import "../catalogue/catalogue.css";

export default function InventoryWorkspace({ onBack }) {
  const [locations, setLocations] = useState([]);
  const [products, setProducts] = useState([]);
  const [variants, setVariants] = useState([]);
  const [balances, setBalances] = useState([]);
  const [movements, setMovements] = useState([]);
  const [productId, setProductId] = useState("");
  const [form, setForm] = useState({ variant_id: "", location_id: "", quantity: "", note: "" });
  const [issueForm, setIssueForm] = useState({ variant_id: "", location_id: "", quantity: "", note: "" });
  const [transferForm, setTransferForm] = useState({ variant_id: "", source_location_id: "", destination_location_id: "", quantity: "", note: "" });
  const [locationForm, setLocationForm] = useState({ name: "", location_type: "warehouse", pin_code: "" });
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

  async function createLocation(event) {
    event.preventDefault(); setBusy(true); setError(""); setMessage("");
    try {
      await apiRequest("/inventory/locations", { method: "POST", body: JSON.stringify({
        name: locationForm.name, location_type: locationForm.location_type, pin_code: locationForm.pin_code || null,
      })});
      setLocationForm({ name: "", location_type: "warehouse", pin_code: "" });
      setMessage("Stock location created."); await loadBase();
    } catch (e) { setError(e.message || "Unable to create stock location."); }
    finally { setBusy(false); }
  }

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


  async function submitIssue(event) {
    event.preventDefault(); setBusy(true); setError(""); setMessage("");
    try {
      await apiRequest("/inventory/issues", { method: "POST", body: JSON.stringify({
        variant_id: Number(issueForm.variant_id), location_id: Number(issueForm.location_id),
        quantity: Number(issueForm.quantity), note: issueForm.note,
      })});
      setIssueForm(v => ({ ...v, quantity: "", note: "" }));
      setMessage("Stock issue recorded. Reserved units were protected."); await loadBase();
    } catch (e) { setError(e.message || "Stock issue failed."); }
    finally { setBusy(false); }
  }

  async function submitTransfer(event) {
    event.preventDefault(); setBusy(true); setError(""); setMessage("");
    try {
      await apiRequest("/inventory/transfers", { method: "POST", body: JSON.stringify({
        variant_id: Number(transferForm.variant_id), source_location_id: Number(transferForm.source_location_id),
        destination_location_id: Number(transferForm.destination_location_id),
        quantity: Number(transferForm.quantity), note: transferForm.note,
      })});
      setTransferForm(v => ({ ...v, quantity: "", note: "" }));
      setMessage("Stock transfer completed and both location movements recorded."); await loadBase();
    } catch (e) { setError(e.message || "Stock transfer failed."); }
    finally { setBusy(false); }
  }

  return <section className="sb-workspace">
    <button className="sb-back" type="button" onClick={onBack}>← All workspaces</button>
    <p className="sb-eyebrow">STOCK CONTROL</p><h1>Inventory</h1>
    <p>Manage stock locations, receipt adjustments, stock issues, inter-location transfers, balances and movement history.</p>
    {error && <p className="sb-alert" role="alert">{error}</p>}
    {message && <p className="sb-success" role="status">{message}</p>}
    <form className="sb-form" onSubmit={createLocation}>
      <h2>Add stock location</h2>
      <div className="sb-form-grid">
        <label>Location name<input required maxLength="160" value={locationForm.name} onChange={e=>setLocationForm(v=>({...v,name:e.target.value}))}/></label>
        <label>Type<select value={locationForm.location_type} onChange={e=>setLocationForm(v=>({...v,location_type:e.target.value}))}><option value="warehouse">Warehouse</option><option value="store">Store</option><option value="dark_store">Dark store</option></select></label>
        <label>PIN code (optional)<input inputMode="numeric" pattern="[0-9]{6}" maxLength="6" value={locationForm.pin_code} onChange={e=>setLocationForm(v=>({...v,pin_code:e.target.value}))}/></label>
      </div>
      <button className="sb-primary" disabled={busy} type="submit">{busy ? "Saving…" : "Create location"}</button>
    </form>
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
    <form className="sb-form" onSubmit={submitIssue}>
      <h2>Issue / reduce stock</h2>
      <p className="sb-muted">Reduces on-hand quantity only when unreserved available stock is sufficient. Reserved units cannot be issued.</p>
      <div className="sb-form-grid">
        <label>Product<select required value={productId} onChange={e=>{setProductId(e.target.value);setIssueForm(v=>({...v,variant_id:""}));}}><option value="">Choose product</option>{products.map(p=><option key={p.id} value={p.id}>{p.name}</option>)}</select></label>
        <label>Variant / SKU<select required value={issueForm.variant_id} onChange={e=>setIssueForm(v=>({...v,variant_id:e.target.value}))}><option value="">Choose variant</option>{variants.map(v=><option key={v.id} value={v.id}>{v.sku} · ₹{v.selling_price}</option>)}</select></label>
        <label>Stock location<select required value={issueForm.location_id} onChange={e=>setIssueForm(v=>({...v,location_id:e.target.value}))}><option value="">Choose location</option>{locations.map(l=><option key={l.id} value={l.id}>{l.name}</option>)}</select></label>
        <label>Quantity to issue<input required type="number" min="0.001" step="0.001" value={issueForm.quantity} onChange={e=>setIssueForm(v=>({...v,quantity:e.target.value}))}/></label>
        <label className="sb-span-all">Reason / reference<input required minLength="3" maxLength="500" value={issueForm.note} onChange={e=>setIssueForm(v=>({...v,note:e.target.value}))}/></label>
      </div>
      <button className="sb-primary" disabled={busy || !locations.length} type="submit">{busy ? "Saving…" : "Issue stock"}</button>
    </form>
    <form className="sb-form" onSubmit={submitTransfer}>
      <h2>Transfer stock between locations</h2>
      <p className="sb-muted">Source stock is reduced and destination stock increased in one database transaction. Reserved units are not transferable.</p>
      <div className="sb-form-grid">
        <label>Product<select required value={productId} onChange={e=>{setProductId(e.target.value);setTransferForm(v=>({...v,variant_id:""}));}}><option value="">Choose product</option>{products.map(p=><option key={p.id} value={p.id}>{p.name}</option>)}</select></label>
        <label>Variant / SKU<select required value={transferForm.variant_id} onChange={e=>setTransferForm(v=>({...v,variant_id:e.target.value}))}><option value="">Choose variant</option>{variants.map(v=><option key={v.id} value={v.id}>{v.sku} · ₹{v.selling_price}</option>)}</select></label>
        <label>From location<select required value={transferForm.source_location_id} onChange={e=>setTransferForm(v=>({...v,source_location_id:e.target.value}))}><option value="">Choose source</option>{locations.map(l=><option key={l.id} value={l.id}>{l.name}</option>)}</select></label>
        <label>To location<select required value={transferForm.destination_location_id} onChange={e=>setTransferForm(v=>({...v,destination_location_id:e.target.value}))}><option value="">Choose destination</option>{locations.filter(l=>String(l.id)!==transferForm.source_location_id).map(l=><option key={l.id} value={l.id}>{l.name}</option>)}</select></label>
        <label>Quantity to transfer<input required type="number" min="0.001" step="0.001" value={transferForm.quantity} onChange={e=>setTransferForm(v=>({...v,quantity:e.target.value}))}/></label>
        <label className="sb-span-all">Reason / reference<input required minLength="3" maxLength="500" value={transferForm.note} onChange={e=>setTransferForm(v=>({...v,note:e.target.value}))}/></label>
      </div>
      <button className="sb-primary" disabled={busy || locations.length < 2} type="submit">{busy ? "Saving…" : "Transfer stock"}</button>
      {locations.length < 2 && <p className="sb-muted">Create at least two active locations to transfer stock.</p>}
    </form>
    <div className="sb-data-card"><div className="sb-data-heading"><h2>Stock balances ({balances.length})</h2><button type="button" onClick={loadBase}>Refresh</button></div>
      {balances.length ? <div className="sb-table-wrap"><table><thead><tr><th>SKU</th><th>Location</th><th>On hand</th><th>Reserved</th><th>Available</th></tr></thead><tbody>{balances.map((b,i)=><tr key={b.variant_id+"-"+b.location_id+"-"+i}><td>{b.sku}</td><td>{b.location_name}</td><td>{b.on_hand}</td><td>{b.reserved}</td><td>{b.available}</td></tr>)}</tbody></table></div> : <p className="sb-empty">No stock balances found.</p>}
    </div>
    <div className="sb-data-card"><h2>Recent movements ({movements.length})</h2>
      {movements.length ? <div className="sb-table-wrap"><table><thead><tr><th>Date</th><th>Variant ID</th><th>Location ID</th><th>Type</th><th>Quantity</th><th>Note</th></tr></thead><tbody>{movements.map(m=><tr key={m.id}><td>{new Date(m.created_at).toLocaleString()}</td><td>{m.variant_id}</td><td>{m.location_id}</td><td>{m.movement_type}</td><td>{m.quantity}</td><td>{m.note}</td></tr>)}</tbody></table></div> : <p className="sb-empty">No inventory movements found.</p>}
    </div>
  </section>;
}
