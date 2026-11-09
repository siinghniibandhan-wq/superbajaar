import { useCallback, useEffect, useState } from "react";
import { apiRequest } from "../../services/api.js";
import "./PaymentsWorkspace.css";

const statuses = ["pending", "authorized", "captured", "failed", "cancelled", "refunded"];
const methods = ["upi", "card", "netbanking", "cod", "wallet", "bank_transfer", "other"];
const next = { pending: ["authorized", "failed", "cancelled"], authorized: ["failed", "cancelled"], captured: [], failed: [], cancelled: [], refunded: [] };
const label = value => String(value || "").replaceAll("_", " ").replace(/\b\w/g, char => char.toUpperCase());
const money = value => new Intl.NumberFormat("en-IN", { style: "currency", currency: "INR", maximumFractionDigits: 2 }).format(Number(value || 0));

export default function PaymentsWorkspace({ onBack }) {
  const [items, setItems] = useState([]);
  const [total, setTotal] = useState(0);
  const [orders, setOrders] = useState([]);
  const [reconciliation, setReconciliation] = useState(null);
  const [status, setStatus] = useState("");
  const [method, setMethod] = useState("");
  const [search, setSearch] = useState("");
  const [orderId, setOrderId] = useState("");
  const [payMethod, setPayMethod] = useState("upi");
  const [amount, setAmount] = useState("");
  const [providerRef, setProviderRef] = useState("");
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [busy, setBusy] = useState(null);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");

  const load = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      const query = new URLSearchParams({ limit: "200" });
      if (status) query.set("status", status);
      if (method) query.set("method", method);
      if (search.trim()) query.set("search", search.trim());
      const [payments, orderResult, summary] = await Promise.all([
        apiRequest("/payments?" + query.toString()),
        apiRequest("/orders?limit=200"),
        apiRequest("/payments/reconciliation")
      ]);
      setItems(payments.items || []);
      setTotal(payments.total || 0);
      setOrders((orderResult.items || []).filter(order => order.status !== "cancelled"));
      setReconciliation(summary);
    } catch (err) {
      setError(err.message || "Unable to load payment records.");
    } finally {
      setLoading(false);
    }
  }, [status, method, search]);

  useEffect(() => { load(); }, [load]);

  async function create(event) {
    event.preventDefault();
    setSaving(true);
    setError("");
    setNotice("");
    if (!orderId || !amount.trim() || !Number.isFinite(Number(amount)) || Number(amount) <= 0) {
      setError("Choose an order and enter a positive payment amount.");
      setSaving(false);
      return;
    }
    try {
      await apiRequest("/payments", {
        method: "POST",
        body: JSON.stringify({
          order_id: Number(orderId), method: payMethod, amount: Number(amount),
          status: "pending", provider_reference: providerRef.trim() || null
        })
      });
      setOrderId("");
      setAmount("");
      setProviderRef("");
      setNotice("Payment record created as pending. No gateway charge was initiated.");
      await load();
    } catch (err) {
      setError(err.message || "Unable to create payment record.");
    } finally {
      setSaving(false);
    }
  }

  async function update(item, value) {
    setBusy(item.id);
    setError("");
    setNotice("");
    try {
      await apiRequest("/payments/" + item.id + "/status", {
        method: "PATCH", body: JSON.stringify({ status: value })
      });
      setNotice(item.payment_reference + " updated to " + label(value) + ".");
      await load();
    } catch (err) {
      setError(err.message || "Unable to update payment.");
    } finally {
      setBusy(null);
    }
  }

  const summaryCards = reconciliation ? [
    { title: "Total order value", value: money(reconciliation.orders?.value), note: (reconciliation.orders?.count || 0) + " non-cancelled orders", tone: "violet", mark: "₹" },
    { title: "Pending payments", value: String(reconciliation.payments_by_status?.pending?.count || 0), note: money(reconciliation.payments_by_status?.pending?.amount) + " pending", tone: "amber", mark: "◷" },
    { title: "Captured (verified)", value: money(reconciliation.captured_amount_recorded), note: "Razorpay capture confirmation", tone: "green", mark: "✓" },
    { title: "Refunded (legacy records)", value: money(reconciliation.refunded_amount_recorded), note: "Refund API not enabled", tone: "rose", mark: "↶" }
  ] : [];

  return (
    <section className="sb-workspace sb-payments">
      <button className="sb-back" type="button" onClick={onBack}>← All workspaces</button>
      <header className="sb-payments-heading">
        <div>
          <p className="sb-eyebrow">COMMERCE <span>›</span> PAYMENTS</p>
          <h1>Payments</h1>
          <p>Review payment intents and provider-verified captures. Refund and settlement workflows are awaiting their controlled lifecycle implementation.</p>
        </div>
        <div className="sb-payment-heading-mark" aria-hidden="true">₹</div>
      </header>

      {error && <p className="sb-alert" role="alert">{error}</p>}
      {notice && <p className="sb-success" role="status">{notice}</p>}

      {reconciliation && (
        <section className="sb-payment-panel" aria-label="Payment overview">
          <div className="sb-payment-section-heading">
            <div><span className="sb-payment-section-icon">▥</span><h2>Payment overview</h2></div>
            <span className="sb-payment-asof">Live application records</span>
          </div>
          <div className="sb-payment-summary-grid">
            {summaryCards.map(card => (
              <article className={"sb-payment-summary-card tone-" + card.tone} key={card.title}>
                <span className="sb-payment-summary-mark" aria-hidden="true">{card.mark}</span>
                <span className="sb-payment-summary-label">{card.title}</span>
                <strong>{card.value}</strong>
                <small>{card.note}</small>
              </article>
            ))}
          </div>
          <div className="sb-payment-secondary-stats">
            <span>Authorised <strong>{reconciliation.payments_by_status?.authorized?.count || 0}</strong> · {money(reconciliation.payments_by_status?.authorized?.amount)}</span>
            <span>Net captured (recorded) <strong>{money(reconciliation.net_captured_amount_recorded)}</strong></span>
          </div>
          <p className="sb-payment-disclaimer">Razorpay captures are provider-verified. Refund requests/provider refunds, settlement batches, fees and bank-deposit reconciliation are not yet implemented; these totals are not a settlement or bank statement.</p>
        </section>
      )}

      <form className="sb-payment-panel sb-payment-form" onSubmit={create}>
        <div className="sb-payment-section-heading">
          <div><span className="sb-payment-section-icon">＋</span><h2>Record a payment</h2></div>
          <span className="sb-payment-manual-note">Manual entry · No gateway charge</span>
        </div>
        <div className="sb-payment-fields">
          <label>Order <span aria-hidden="true">*</span>
            <select required value={orderId} onChange={event => {
              setOrderId(event.target.value);
              const order = orders.find(item => String(item.id) === event.target.value);
              if (order) setAmount(String(order.total));
            }}>
              <option value="">Choose order</option>
              {orders.map(order => <option key={order.id} value={order.id}>{order.order_number} · {order.customer_name} · {money(order.total)}</option>)}
            </select>
          </label>
          <label>Payment method <span aria-hidden="true">*</span>
            <select value={payMethod} onChange={event => setPayMethod(event.target.value)}>
              {methods.map(item => <option key={item} value={item}>{label(item)}</option>)}
            </select>
          </label>
          <label>Amount (₹) <span aria-hidden="true">*</span>
            <input type="number" min="0.01" step="0.01" required value={amount} onChange={event => setAmount(event.target.value)} placeholder="Enter amount" />
          </label>
          <label>Provider reference <small>(Optional)</small>
            <input maxLength="200" value={providerRef} onChange={event => setProviderRef(event.target.value)} placeholder="Transaction / gateway reference" />
          </label>
        </div>
        <div className="sb-payment-form-actions">
          <button className="sb-primary" type="submit" disabled={saving}>{saving ? "Saving…" : "＋ Create pending record"}</button>
          <button className="sb-payment-clear" type="button" onClick={() => { setOrderId(""); setPayMethod("upi"); setAmount(""); setProviderRef(""); setError(""); setNotice(""); }}>Clear</button>
        </div>
      </form>

      <section className="sb-payment-panel sb-payment-records" aria-label="Payment records">
        <div className="sb-payment-section-heading">
          <div><span className="sb-payment-section-icon">☷</span><h2>Payment records</h2><span className="sb-payment-count">{total}</span></div>
          <button className="sb-payment-refresh" type="button" onClick={load} disabled={loading}>{loading ? "Refreshing…" : "↻ Refresh"}</button>
        </div>
        <div className="sb-payment-toolbar">
          <label className="sb-payment-search"><span aria-hidden="true">⌕</span><input aria-label="Search payments" placeholder="Search by order, payment or reference…" value={search} onChange={event => setSearch(event.target.value)} /></label>
          <select aria-label="Filter payment status" value={status} onChange={event => setStatus(event.target.value)}>
            <option value="">All statuses</option>{statuses.map(item => <option key={item} value={item}>{label(item)}</option>)}
          </select>
          <select aria-label="Filter payment method" value={method} onChange={event => setMethod(event.target.value)}>
            <option value="">All methods</option>{methods.map(item => <option key={item} value={item}>{label(item)}</option>)}
          </select>
        </div>
        <p className="sb-payment-record-count">Showing {items.length} of {total} payment records</p>
        {loading ? <p className="sb-empty">Loading payment records…</p> : items.length ? (
          <div className="sb-payment-table-wrap">
            <table className="sb-payment-table">
              <thead><tr><th>Payment / Order</th><th>Amount</th><th>Method</th><th>Provider reference</th><th>Status</th><th>Actions</th></tr></thead>
              <tbody>{items.map(item => (
                <tr key={item.id}>
                  <td><strong>{item.payment_reference}</strong><small>{item.order_number || "Order #" + item.order_id}</small></td>
                  <td className="sb-payment-amount">{money(item.amount)}</td>
                  <td>{label(item.method)}</td>
                  <td className="sb-payment-reference">{item.provider_reference || "—"}</td>
                  <td><span className={"sb-payment-status status-" + item.status}>{label(item.status)}</span></td>
                  <td><select aria-label={"Update status for " + item.payment_reference} value="" disabled={busy === item.id || !(next[item.status] || []).length} onChange={event => event.target.value && update(item, event.target.value)}>
                    <option value="">{busy === item.id ? "Saving…" : (next[item.status] || []).length ? "Update…" : "No changes"}</option>
                    {(next[item.status] || []).map(value => <option key={value} value={value}>{label(value)}</option>)}
                  </select></td>
                </tr>
              ))}</tbody>
            </table>
          </div>
        ) : (
          <div className="sb-payment-empty">
            <span aria-hidden="true">₹</span>
            <h3>{error ? "Payment records unavailable" : "No payment records found"}</h3>
            <p>{error ? "Check the connection and refresh the records." : "There are no payment records matching the selected filters."}</p>
            {!error && <button type="button" onClick={() => { setSearch(""); setStatus(""); setMethod(""); }}>Clear filters</button>}
          </div>
        )}
      </section>
    </section>
  );
}
