import { useEffect, useMemo, useRef, useState } from "react";
import { apiRequest } from "../../services/api.js";
import "./POSWorkspace.css";

const money = value => new Intl.NumberFormat("en-IN", { style: "currency", currency: "INR", maximumFractionDigits: 2 }).format(Number(value || 0));

export default function POSWorkspace({ onBack }) {
  const [variants, setVariants] = useState([]);
  const [posSummary, setPosSummary] = useState(null);
  const [recentSales, setRecentSales] = useState([]);
  const [analyticsError, setAnalyticsError] = useState("");
  const [locations, setLocations] = useState([]);
  const [cart, setCart] = useState([]);
  const [locationId, setLocationId] = useState("");
  const [customer, setCustomer] = useState({ name: "Walk-in Customer", phone: "", pin: "" });
  const [method, setMethod] = useState("upi");
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [receipt, setReceipt] = useState(null);
  const [search, setSearch] = useState("");
  const [selectedVariantByProduct, setSelectedVariantByProduct] = useState({});
  const checkoutAttempt = useRef(null);

  async function refreshAnalytics() {
    const analytics = await Promise.allSettled([
      apiRequest("/pos/summary"),
      apiRequest("/pos/sales?limit=10"),
    ]);
    if (analytics[0].status === "fulfilled") setPosSummary({ orders: analytics[0].value.orders, payments: analytics[0].value.payments });
    else setPosSummary(null);
    if (analytics[1].status === "fulfilled") setRecentSales(analytics[1].value.items || []);
    else setRecentSales([]);
    const failedAnalytics = analytics.filter(result => result.status === "rejected").length;
    setAnalyticsError(failedAnalytics ? "POS overview is partially unavailable; checkout remains connected to the existing order and payment workflows." : "");
  }

  async function load() {
    setLoading(true); setError("");
    try {
      const [result, locationResult] = await Promise.all([
        apiRequest("/catalogue/variants?limit=500"),
        apiRequest("/inventory/locations?limit=500"),
      ]);
      setVariants(result.items || []);
      setLocations((locationResult.items || []).filter(location => location.is_active !== false));
      await refreshAnalytics();
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
    const checkoutPayload = {
      channel: "pos", customer_name: customer.name.trim(), customer_phone: customer.phone.trim() || null,
      delivery_pin: customer.pin.trim() || null, location_id: Number(locationId), pos_payment_method: method,
      notes: "Created at POS", lines: cart.map(line => ({ variant_id: line.id, quantity: line.quantity })),
    };
    const signature = JSON.stringify(checkoutPayload);
    if (!checkoutAttempt.current || checkoutAttempt.current.signature !== signature) {
      checkoutAttempt.current = { signature, key: globalThis.crypto?.randomUUID?.() || (Date.now().toString(16) + Math.random().toString(16).slice(2)) };
    }
    try {
      const order = await apiRequest("/orders", {
        method: "POST",
        body: JSON.stringify({ ...checkoutPayload, checkout_idempotency_key: checkoutAttempt.current.key }),
      });
      const payment = order.payment || null;
      setReceipt({ order, payment });
      if (!payment) {
        setError("Order " + order.order_number + " was returned without its tender record. Do not create another order; reconcile this sale before retrying.");
      } else {
        setNotice("POS order and pending tender were created atomically. Cash has not been confirmed and electronic payment has not been provider-verified.");
        setCart([]);
        checkoutAttempt.current = null;
      }
      void refreshAnalytics();
    } catch (e) {
      setError(e.message || "POS checkout could not be completed. Retry the same sale to safely reuse its checkout key.");
    } finally { setSaving(false); }
  }

  return <section className="sb-workspace sb-pos">
    <button className="sb-back" type="button" onClick={onBack}>← All workspaces</button>
    <p className="sb-eyebrow">OPERATIONS · STORES</p><h1>POS & Stores</h1>
    <p>Create a walk-in sale with an atomic order and pending tender record. Tender confirmation remains a separate controlled step.</p>
    {error && <p className="sb-alert" role="alert">{error}</p>}
    {analyticsError && <p className="sb-alert" role="status">{analyticsError}</p>}
    {notice && <p className="sb-success" role="status">{notice}</p>}
    {posSummary && <div className="sb-report-grid" aria-label="POS overview">
      <article className="sb-report-card"><small>POS orders</small><strong>{Number(posSummary.orders?.order_count || 0).toLocaleString("en-IN")}</strong><span>All recorded POS orders</span></article>
      <article className="sb-report-card"><small>Today's sales value</small><strong>{money(posSummary.orders?.today_order_value)}</strong><span>{Number(posSummary.orders?.today_order_count || 0)} orders today</span></article>
      <article className="sb-report-card"><small>Captured payments</small><strong>{money(posSummary.payments?.captured_amount)}</strong><span>{Number(posSummary.payments?.captured_count || 0)} confirmed records</span></article>
      <article className="sb-report-card"><small>Pending payments</small><strong>{money(posSummary.payments?.pending_amount)}</strong><span>{Number(posSummary.payments?.pending_count || 0)} awaiting confirmation</span></article>
    </div>}
    {receipt && <div className="sb-data-card"><h2>Latest order</h2><p><strong>{receipt.order.order_number}</strong> · {money(receipt.order.total)} · {receipt.order.status}</p><p>Payment record: {receipt.payment ? receipt.payment.payment_reference + " · " + receipt.payment.status : "Not returned — reconcile before retrying."}</p></div>}
    <div className="sb-data-card">
      <div className="sb-data-heading"><h2>Recent POS sales</h2><button type="button" onClick={load} disabled={loading}>Refresh sales</button></div>
      {recentSales.length ? <div className="sb-table-wrap"><table><thead><tr><th>Order</th><th>Customer</th><th>Status</th><th>Total</th><th>Captured</th><th>Payment state</th></tr></thead><tbody>{recentSales.map(sale => <tr key={sale.id}><td>{sale.order_number}</td><td>{sale.customer_name}</td><td>{sale.status}</td><td>{money(sale.total)}</td><td>{money(sale.captured_amount)}</td><td>{sale.payment_statuses || "No payment record"}</td></tr>)}</tbody></table></div> : <p className="sb-empty">No POS sales recorded yet.</p>}
    </div>
    <div className="sb-pos-layout">
      <div className="sb-data-card">
        <div className="sb-data-heading"><h2>Catalogue</h2><button type="button" onClick={load} disabled={loading}>{loading ? "Loading…" : "Refresh"}</button></div>
        <label>Search product or SKU<input value={search} onChange={e => setSearch(e.target.value)} placeholder="Search catalogue…" /></label>
        {loading ? <p className="sb-empty">Loading variants…</p> : <div className="sb-pos-products">{groupedVisible.map(group => <article className="sb-pos-product" key={group.productId}><strong>{group.productName}</strong>{group.variants.length > 1 ? <label>Variant<select aria-label={"Variant for " + group.productName} value={String(group.selected.id)} onChange={e => setSelectedVariantByProduct(old => ({ ...old, [String(group.productId)]: e.target.value }))}>{group.variants.map(v => <option key={v.id} value={v.id}>{variantLabel(v)}</option>)}</select></label> : <small>{variantLabel(group.selected)}</small>}<span>{money(group.selected.selling_price)}</span><button type="button" className="sb-primary" onClick={() => add(group.selected)}>Add to sale</button></article>)}</div>}
        {!loading && !visible.length && <p className="sb-empty">No active saleable variants are available. Add or activate a product and its variant in Catalogue.</p>}
      </div>
      <div className="sb-data-card">
        <h2>Current sale ({cart.reduce((sum, line) => sum + line.quantity, 0)} items)</h2>
        {!cart.length ? <p className="sb-empty">Choose a catalogue item to start a sale.</p> : <div className="sb-pos-cart">{cart.map(line => <div className="sb-pos-cart-line" key={line.id}><div><strong>{line.product_name || line.name || line.sku}</strong><small>{line.sku} · {money(line.selling_price)} each</small></div><label>Qty<input type="number" min="0" max="100000" step="1" value={line.quantity} onChange={e => setQuantity(line.id, e.target.value)} /></label><strong>{money(Number(line.selling_price || 0) * line.quantity)}</strong></div>)}</div>}
        <div className="sb-pos-total"><span>Subtotal</span><strong>{money(total)}</strong></div>
        <form className="sb-form" onSubmit={checkout}>
          <h3>Customer & tender intent</h3>
          <label>Stock location<select required value={locationId} onChange={e => setLocationId(e.target.value)}><option value="">Choose stock location</option>{locations.map(location => <option key={location.id} value={location.id}>{location.name} · {location.location_type || "location"}</option>)}</select></label>
          <label>Customer name<input required minLength="1" maxLength="200" value={customer.name} onChange={e => setCustomer(v => ({ ...v, name: e.target.value }))} /></label>
          <label>Phone (optional)<input maxLength="20" value={customer.phone} onChange={e => setCustomer(v => ({ ...v, phone: e.target.value }))} /></label>
          <label>Delivery PIN (optional)<input inputMode="numeric" pattern="[0-9]{6}" maxLength="6" value={customer.pin} onChange={e => setCustomer(v => ({ ...v, pin: e.target.value }))} /></label>
          <label>Payment method<select value={method} onChange={e => setMethod(e.target.value)}><option value="upi">UPI</option><option value="card">Card</option><option value="netbanking">Net banking</option><option value="cod">Cash (pending confirmation)</option><option value="wallet">Wallet</option><option value="bank_transfer">Bank transfer</option></select></label>
          <p className="sb-muted">Order and pending tender are saved in one transaction. Cash must be confirmed by an authorised cashier; electronic tender remains pending until verified provider confirmation. Register shifts and cash-drawer reconciliation require the approved POS register controls.</p>
          <button className="sb-primary" type="submit" disabled={saving || !cart.length || !locationId}>{saving ? "Creating sale…" : "Create sale & pending tender"}</button>
          {!locations.length && !loading && <small>No active stock locations are available. Create or activate a store or warehouse in Inventory before checkout.</small>}
        </form>
      </div>
    </div>
  </section>;
}
