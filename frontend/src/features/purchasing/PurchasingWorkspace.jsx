import { useCallback, useEffect, useState } from "react";
import { apiRequest } from "../../services/api.js";

const money = v => new Intl.NumberFormat("en-IN", { style: "currency", currency: "INR" }).format(Number(v || 0));
const label = v => String(v || "").replaceAll("_", " ").replace(/\b\w/g, c => c.toUpperCase());
const emptySupplier = { name: "", contact_name: "", phone: "", email: "", gstin: "", address: "" };
const emptyLine = { variant_id: "", quantity: "1", unit_cost: "" };

export default function PurchasingWorkspace({ onBack }) {
  const [tab, setTab] = useState("orders");
  const [suppliers, setSuppliers] = useState([]);
  const [locations, setLocations] = useState([]);
  const [variants, setVariants] = useState([]);
  const [orders, setOrders] = useState([]);
  const [supplierForm, setSupplierForm] = useState(emptySupplier);
  const [supplierId, setSupplierId] = useState("");
  const [locationId, setLocationId] = useState("");
  const [notes, setNotes] = useState("");
  const [lines, setLines] = useState([{ ...emptyLine }]);
  const [selected, setSelected] = useState(null);
  const [detail, setDetail] = useState(null);
  const [receipts, setReceipts] = useState({});
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");

  const load = useCallback(async () => {
    setLoading(true); setError("");
    try {
      const [s, l, p, v] = await Promise.all([
        apiRequest("/purchasing/suppliers?limit=500"),
        apiRequest("/inventory/locations?limit=500"),
        apiRequest("/purchasing/orders?limit=200"),
        apiRequest("/catalogue/variants?limit=500"),
      ]);
      setSuppliers(s.items || []); setLocations(l.items || []); setOrders(p.items || []); setVariants(v.items || []);
    } catch (e) { setError(e.message || "Unable to load purchasing data."); }
    finally { setLoading(false); }
  }, []);
  useEffect(() => { load(); }, [load]);

  async function createSupplier(e) {
    e.preventDefault(); setSaving(true); setError(""); setNotice("");
    try {
      const payload = { ...supplierForm };
      for (const k of ["contact_name", "phone", "email", "gstin", "address"]) payload[k] = payload[k].trim() || null;
      const created = await apiRequest("/purchasing/suppliers", { method: "POST", body: JSON.stringify(payload) });
      setSupplierForm(emptySupplier); setSupplierId(String(created.id)); setNotice("Supplier created."); await load();
    } catch (e) { setError(e.message || "Unable to create supplier."); }
    finally { setSaving(false); }
  }

  function setLine(index, key, value) {
    setLines(old => old.map((line, i) => i === index ? { ...line, [key]: value } : line));
  }

  async function createOrder(e) {
    e.preventDefault(); setSaving(true); setError(""); setNotice("");
    try {
      const payload = {
        supplier_id: Number(supplierId), location_id: Number(locationId), notes: notes.trim() || null,
        lines: lines.map(line => ({ variant_id: Number(line.variant_id), quantity: Number(line.quantity), unit_cost: Number(line.unit_cost) })),
      };
      if (!payload.supplier_id || !payload.location_id || payload.lines.some(line => !line.variant_id || !Number.isFinite(line.quantity) || line.quantity <= 0 || !Number.isFinite(line.unit_cost) || line.unit_cost < 0)) {
        throw new Error("Select a supplier, location, catalogue variant, quantity and valid unit cost for each line.");
      }
      const po = await apiRequest("/purchasing/orders", { method: "POST", body: JSON.stringify(payload) });
      setNotice("Purchase order " + po.purchase_number + " saved as a draft. Approve it before receiving goods."); setNotes(""); setLines([{ ...emptyLine }]); await load(); await openOrder(po.id);
    } catch (e) { setError(e.message || "Unable to create purchase order."); }
    finally { setSaving(false); }
  }

  async function openOrder(id) {
    setSelected(id); setError("");
    try {
      const data = await apiRequest("/purchasing/orders/" + id);
      setDetail(data);
      setReceipts(old => {
        const next = { ...old };
        for (const line of data.lines || []) if (next[line.line_id] === undefined) next[line.line_id] = String(line.quantity_open || "");
        return next;
      });
    } catch (e) { setError(e.message || "Unable to load purchase order details."); }
  }

  async function approveOrder() {
    if (!detail) return;
    setSaving(true); setError(""); setNotice("");
    try {
      const result = await apiRequest("/purchasing/orders/" + detail.id + "/approve", { method: "POST" });
      setNotice(result.message || "Purchase order approved."); await load(); await openOrder(detail.id);
    } catch (e) { setError(e.message || "Unable to approve purchase order."); }
    finally { setSaving(false); }
  }

  async function receiveGoods(e) {
    e.preventDefault(); if (!detail) return;
    const receiptLines = (detail.lines || []).filter(line => Number(receipts[line.line_id]) > 0).map(line => ({ line_id: line.line_id, quantity: Number(receipts[line.line_id]) }));
    if (!receiptLines.length) { setError("Enter a received quantity for at least one open line."); return; }
    setSaving(true); setError(""); setNotice("");
    try {
      const result = await apiRequest("/purchasing/orders/" + detail.id + "/receive", { method: "POST", body: JSON.stringify({ lines: receiptLines, note: "Goods receipt recorded in purchasing workspace" }) });
      setNotice("Goods receipt recorded. Order status: " + label(result.status) + ". Inventory balances updated."); await load(); await openOrder(detail.id);
    } catch (e) { setError(e.message || "Unable to record goods receipt."); }
    finally { setSaving(false); }
  }

  return <section className="sb-workspace sb-purchasing">
    <button className="sb-back" type="button" onClick={onBack}>← All workspaces</button>
    <p className="sb-eyebrow">OPERATIONS · PURCHASING</p><h1>Purchasing</h1>
    <p>Manage suppliers, save purchase orders as drafts, approve orders and receive goods into a selected stock location.</p>
    {error && <p className="sb-alert" role="alert">{error}</p>}{notice && <p className="sb-success" role="status">{notice}</p>}
    <div className="sb-customer-tabs" role="tablist" aria-label="Purchasing workspace">
      <button type="button" role="tab" aria-selected={tab === "orders"} className={tab === "orders" ? "is-active" : ""} onClick={() => setTab("orders")}>Purchase orders <span>{orders.length}</span></button>
      <button type="button" role="tab" aria-selected={tab === "suppliers"} className={tab === "suppliers" ? "is-active" : ""} onClick={() => setTab("suppliers")}>Suppliers <span>{suppliers.length}</span></button>
    </div>
    {tab === "suppliers" ? <>
      <form className="sb-customer-form" onSubmit={createSupplier}>
        <h2>Add supplier</h2><div className="sb-customer-fields">
          <label>Supplier name *<input required maxLength="200" value={supplierForm.name} onChange={e => setSupplierForm(o => ({ ...o, name: e.target.value }))} /></label>
          <label>Contact person<input maxLength="200" value={supplierForm.contact_name} onChange={e => setSupplierForm(o => ({ ...o, contact_name: e.target.value }))} /></label>
          <label>Phone<input maxLength="30" value={supplierForm.phone} onChange={e => setSupplierForm(o => ({ ...o, phone: e.target.value }))} /></label>
          <label>Email<input type="email" maxLength="254" value={supplierForm.email} onChange={e => setSupplierForm(o => ({ ...o, email: e.target.value }))} /></label>
          <label>GSTIN<input minLength="15" maxLength="15" value={supplierForm.gstin} onChange={e => setSupplierForm(o => ({ ...o, gstin: e.target.value.toUpperCase() }))} /></label>
          <label>Address<input maxLength="1000" value={supplierForm.address} onChange={e => setSupplierForm(o => ({ ...o, address: e.target.value }))} /></label>
        </div><button className="sb-primary" type="submit" disabled={saving}>{saving ? "Saving…" : "Create supplier"}</button>
      </form>
      <div className="sb-customer-list">{suppliers.map(s => <article className="sb-customer-card" key={s.id}><div className="sb-customer-avatar">{s.name.slice(0,1).toUpperCase()}</div><div className="sb-customer-info"><strong>{s.name}</strong><small>{s.contact_name || "No contact"} · {s.phone || "No phone"}</small><small>{s.email || "No email"}{s.gstin ? " · GSTIN " + s.gstin : ""}</small></div><span className="sb-order-status status-delivered">Active</span></article>)}</div>
    </> : <>
      <form className="sb-customer-form" onSubmit={createOrder}>
        <h2>Create purchase order</h2><div className="sb-customer-fields">
          <label>Supplier *<select required value={supplierId} onChange={e => setSupplierId(e.target.value)}><option value="">Choose supplier</option>{suppliers.map(s => <option key={s.id} value={s.id}>{s.name}</option>)}</select></label>
          <label>Receive into location *<select required value={locationId} onChange={e => setLocationId(e.target.value)}><option value="">Choose location</option>{locations.map(l => <option key={l.id} value={l.id}>{l.name}</option>)}</select></label>
          <label className="sb-span-all">Notes<input maxLength="2000" value={notes} onChange={e => setNotes(e.target.value)} /></label>
        </div>
        <div className="sb-purchase-lines"><div className="sb-purchase-lines-head"><strong>Order lines</strong><button type="button" onClick={() => setLines(old => [...old, { ...emptyLine }])}>+ Add line</button></div>
          {lines.map((line, i) => <div className="sb-purchase-line" key={i}>
            <label>Product variant *<select required value={line.variant_id} onChange={e => setLine(i, "variant_id", e.target.value)}><option value="">Choose variant</option>{variants.map(v => <option key={v.id} value={v.id}>{v.product_name || v.name || ("Product " + v.product_id)} · {v.sku || ("Variant " + v.id)}</option>)}</select></label>
            <label>Quantity<input required type="number" min="0.001" step="0.001" value={line.quantity} onChange={e => setLine(i, "quantity", e.target.value)} /></label>
            <label>Unit cost ₹<input required type="number" min="0" step="0.01" value={line.unit_cost} onChange={e => setLine(i, "unit_cost", e.target.value)} /></label>
            {lines.length > 1 && <button type="button" className="sb-remove-line" onClick={() => setLines(old => old.filter((_, n) => n !== i))} aria-label={"Remove line " + (i + 1)}>×</button>}
          </div>)}
          <p className="sb-purchase-total">Estimated subtotal <strong>{money(lines.reduce((sum, line) => sum + Math.max(0, Number(line.quantity) || 0) * Math.max(0, Number(line.unit_cost) || 0), 0))}</strong></p>
        </div>
        <button className="sb-primary" type="submit" disabled={saving || !suppliers.length || !locations.length}>{saving ? "Saving…" : "Create purchase order"}</button>
        {!suppliers.length && <small>Add a supplier first. </small>}{!locations.length && <small>Create an active inventory location first.</small>}
      </form>
      <div className="sb-customer-toolbar"><button type="button" onClick={load} disabled={loading}>{loading ? "Loading…" : "Refresh orders"}</button></div>
      {loading ? <p className="sb-empty">Loading purchase orders…</p> : orders.length ? <div className="sb-customer-list">{orders.map(po => <article className={"sb-order-card " + (selected === po.id ? "is-selected" : "")} key={po.id}>
        <button type="button" className="sb-order-open" onClick={() => openOrder(po.id)}><span><strong>{po.purchase_number}</strong><small>{po.supplier_name} · {po.location_name}</small></span><span className="sb-order-total">{money(po.subtotal)}<small>{po.line_count} lines</small></span><span className={"sb-order-status status-" + po.status}>{label(po.status)}</span></button>
        {selected === po.id && detail && <div className="sb-purchase-detail"><h3>{detail.purchase_number} · {detail.status === "draft" ? "Approval required" : "Goods receipt"}</h3>{detail.status === "draft" && <div className="sb-purchase-approval"><p className="sb-muted">Draft orders cannot receive stock until approved.</p><button className="sb-primary" type="button" onClick={approveOrder} disabled={saving}>{saving ? "Saving…" : "Approve purchase order"}</button></div>}<div className="sb-purchase-detail-lines">{detail.lines.map(line => <div className="sb-purchase-detail-line" key={line.line_id}><div><strong>{line.product_name}</strong><small>SKU {line.sku} · ordered {line.quantity_ordered} · received {line.quantity_received} · open {line.quantity_open}</small></div><label>Receive qty<input type="number" min="0" max={Number(line.quantity_open)} step="0.001" disabled={Number(line.quantity_open) <= 0 || detail.status === "cancelled" || detail.status === "received"} value={receipts[line.line_id] ?? ""} onChange={e => setReceipts(old => ({ ...old, [line.line_id]: e.target.value }))} /></label></div>)}</div>
          {detail.status !== "received" && detail.status !== "cancelled" && <form onSubmit={receiveGoods}><button className="sb-primary" type="submit" disabled={saving}>{saving ? "Saving…" : "Record goods receipt"}</button></form>}
        </div>}
      </article>)}</div> : <p className="sb-empty">No purchase orders yet.</p>}
    </>}
  </section>;
}
