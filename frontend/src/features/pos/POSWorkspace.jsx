import { useEffect, useMemo, useState } from "react";
import { apiRequest } from "../../services/api.js";
import "./POSWorkspace.css";

const money = value => new Intl.NumberFormat("en-IN", { style: "currency", currency: "INR", maximumFractionDigits: 2 }).format(Number(value || 0));

export default function POSWorkspace({ onBack }) {
  const [variants, setVariants] = useState([]);
  const [cart, setCart] = useState([]);
  const [customer, setCustomer] = useState({ name: "Walk-in Customer", phone: "", pin: "" });
  const [method, setMethod] = useState("upi");
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [receipt, setReceipt] = useState(null);
  const [search, setSearch] = useState("");
  const [selectedVariantByProduct, setSelectedVariantByProduct] = useState({});

  async function load() {
    setLoading(true); setError("");
    try {
      const result = await apiRequest("/catalogue/variants?limit=500");
      setVariants(result.items || []);
    } catch (e) { setError(e.message || "Unable to load active catalogue variants."); }
    finally { setLoading(false); }
  }
  useEffect(() => { load(); }, []);

  const visible = useMemo(() => {
    const term = search.trim().toLowerCase();
    return variants.filter(v => v.is_active !== false && (!term || [v.sku, v.product_name, v.name, v.brand].some(x => String(x || "").toLowerCase().includes(term))));
  }, [variants]);
  const groupedVisible = useMemo(() => {
    const groups = new Map();
    for (const variant of visible) {
      const key = String(variant.product_id);
      if (!groups.has(key)) groups.set(key, []);
      groups.get(key).push(variant);
    }
    return [...groups.values()].map(items => ({
      productId: items[0].product_id,
      productName: items[0].product_name || items[0].name || ("Product " + items[0].product_id),
      variants: items,
      selected: items.find(v => String(v.id) === String(selectedVariantByProduct[String(items[0].product_id)])) || items[0],
    }));
  }, [visible, selectedVariantByProduct]);
  const variantLabel = v => {
    const attrs = Object.entries(v.attributes || {}).map(([key, value]) => (Array.isArray(value) ? value.join(", ") : String(value)));
    return attrs.length ? attrs.join(" / ") : "Default variant";
  };
  const total = cart.reduce((sum, line) => sum + Number(line.selling_price || 0) * line.quantity, 0);

  function add(variant) {
    setCart(old => {
      const existing = old.find(line => line.id === variant.id);
      if (existing) return old.map(line => line.id === variant.id ? { ...line, quantity: line.quantity + 1 } : line);
      return [...old, { ...variant, quantity: 1 }];
    });
    setNotice("");
  }
  function setQuantity(id, value) {
    const quantity = Number(value);
    setCart(old => quantity <= 0 ? old.filter(line => line.id !== id) : old.map(line => line.id === id ? { ...line, quantity: Math.min(100000, Math.floor(quantity)) } : line));
  }

  async function checkout(event) {
    event.preventDefault();
    if (!cart.length) { setError("Add at least one item before checkout."); return; }
    setSaving(true); setError(""); setNotice(""); setReceipt(null);
    let order;
    try {
      order = await apiRequest("/orders", { method: "POST", body: JSON.stringify({
        channel: "pos", customer_name: customer.name.trim(), customer_phone: customer.phone.trim() || null,
        delivery_pin: customer.pin.trim() || null, notes: "Created at POS", lines: cart.map(line => ({ variant_id: line.id, quantity: line.quantity })),
      }) });
    } catch (e) {
      setError(e.message || "Order could not be created. No payment record was created.");
      setSaving(false);
      return;
    }
    try {
      const payment = await apiRequest("/payments", { method: "POST", body: JSON.stringify({
        order_id: order.id, method, amount: Number(order.total), status: "pending",
        note: "POS payment record; gateway confirmation is not configured",
      }) });
      setReceipt({ order, payment });
      setNotice("POS order created. Payment is recorded as PENDING; no gateway charge or cash confirmation was performed by this screen.");
      setCart([]);
    } catch (e) {
      setReceipt({ order, payment: null });
      setError("Order " + order.order_number + " was created, but its payment record failed: " + (e.message || "Unknown API error") + ". Do not create the order again; open Payments and reconcile this order.");
    } finally { setSaving(false); }
  }

  return <section className="sb-workspace sb-pos">
    <button className="sb-back" type="button" onClick={onBack}>← All workspaces</button>
    <p className="sb-eyebrow">OPERATIONS · STORES</p><h1>POS & Stores</h1>
    <p>Create a walk-in sale using active catalogue variants and the existing order API.</p>
    {error && <p className="sb-alert" role="alert">{error}</p>}
    {notice && <p className="sb-success" role="status">{notice}</p>}
    {receipt && <div className="sb-data-card"><h2>Latest order</h2><p><strong>{receipt.order.order_number}</strong> · {money(receipt.order.total)} · {receipt.order.status}</p><p>Payment record: {receipt.payment ? receipt.payment.payment_reference + " · " + receipt.payment.status : "Not created — reconcile before retrying."}</p></div>}
    <div className="sb-pos-layout">
      <div className="sb-data-card">
        <div className="sb-data-heading"><h2>Catalogue</h2><button type="button" onClick={load} disabled={loading}>{loading ? "Loading…" : "Refresh"}</button></div>
        <label>Search product or SKU<input value={search} onChange={e => setSearch(e.target.value)} placeholder="Search catalogue…" /></label>
        {loading ? <p className="sb-empty">Loading variants…</p> : <div className="sb-pos-products">{groupedVisible.map(group => <article className="sb-pos-product" key={group.productId}><strong>{group.productName}</strong>{group.variants.length > 1 ? <label>Variant<select aria-label={"Variant for " + group.productName} value={String(group.selected.id)} onChange={e => setSelectedVariantByProduct(old => ({ ...old, [String(group.productId)]: e.target.value }))}>{group.variants.map(v => <option key={v.id} value={v.id}>{variantLabel(v)}</option>)}</select></label> : <small>{variantLabel(group.selected)}</small>}<span>{money(group.selected.selling_price)}</span><button type="button" className="sb-primary" onClick={() => add(group.selected)}>Add to sale</button></article>)}</div>}
        {!loading && !visible.length && <p className="sb-empty">No matching active products. Create a product in Catalogue first.</p>}
      </div>
      <div className="sb-data-card">
        <h2>Current sale ({cart.reduce((sum, line) => sum + line.quantity, 0)} items)</h2>
        {!cart.length ? <p className="sb-empty">Choose a catalogue item to start a sale.</p> : <div className="sb-pos-cart">{cart.map(line => <div className="sb-pos-cart-line" key={line.id}><div><strong>{line.product_name || line.name || line.sku}</strong><small>{line.sku} · {money(line.selling_price)} each</small></div><label>Qty<input type="number" min="0" max="100000" step="1" value={line.quantity} onChange={e => setQuantity(line.id, e.target.value)} /></label><strong>{money(Number(line.selling_price || 0) * line.quantity)}</strong></div>)}</div>}
        <div className="sb-pos-total"><span>Subtotal</span><strong>{money(total)}</strong></div>
        <form className="sb-form" onSubmit={checkout}>
          <h3>Customer & payment record</h3>
          <label>Customer name<input required minLength="1" maxLength="200" value={customer.name} onChange={e => setCustomer(v => ({ ...v, name: e.target.value }))} /></label>
          <label>Phone (optional)<input maxLength="20" value={customer.phone} onChange={e => setCustomer(v => ({ ...v, phone: e.target.value }))} /></label>
          <label>Delivery PIN (optional)<input inputMode="numeric" pattern="[0-9]{6}" maxLength="6" value={customer.pin} onChange={e => setCustomer(v => ({ ...v, pin: e.target.value }))} /></label>
          <label>Payment method<select value={method} onChange={e => setMethod(e.target.value)}><option value="upi">UPI</option><option value="card">Card</option><option value="netbanking">Net banking</option><option value="cod">Cash / COD</option><option value="wallet">Wallet</option><option value="bank_transfer">Bank transfer</option><option value="other">Other</option></select></label>
          <p className="sb-muted">Checkout creates an order and a pending payment record. It does not charge a gateway, mark cash as received, or confirm a payment.</p>
          <button className="sb-primary" type="submit" disabled={saving || !cart.length}>{saving ? "Creating sale…" : "Create POS order"}</button>
        </form>
      </div>
    </div>
  </section>;
}
