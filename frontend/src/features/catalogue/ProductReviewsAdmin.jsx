import { useCallback, useEffect, useState } from "react";
import { apiRequest } from "../../services/api.js";

const dateText = value => value ? new Date(value).toLocaleDateString("en-IN", { day: "2-digit", month: "short", year: "numeric" }) : "—";

export default function ProductReviewsAdmin() {
  const [status, setStatus] = useState("pending");
  const [items, setItems] = useState([]);
  const [error, setError] = useState("");
  const [busyId, setBusyId] = useState(null);
  const [notes, setNotes] = useState({});

  const load = useCallback(async () => {
    setError("");
    try { const result = await apiRequest("/reviews/admin?status=" + status); setItems(Array.isArray(result?.items) ? result.items : []); }
    catch (err) { setItems([]); setError(err?.message || "Reviews could not be loaded."); }
  }, [status]);
  useEffect(() => { load(); }, [load]);

  async function decide(id, decision) {
    setBusyId(id); setError("");
    try { await apiRequest("/reviews/admin/" + id + "/approve", { method: "POST", body: JSON.stringify({ decision, note: notes[id] || "" }) }); await load(); }
    catch (err) { setError(err?.message || "Could not save the decision."); }
    finally { setBusyId(null); }
  }

  return <section className="sb-reviews-admin">
    <div className="sb-data-heading"><div><h2>Product reviews</h2><span>Customers who received the product can review it once. Approve a review to show it in the shop.</span></div>
      <select aria-label="Review status" value={status} onChange={e => setStatus(e.target.value)}>
        <option value="pending">Waiting for approval</option><option value="approved">Approved</option><option value="rejected">Rejected</option><option value="all">All</option>
      </select></div>
    {error && <p className="sb-empty" role="alert">{error}</p>}
    {!error && items.length === 0 && <p className="sb-empty">No reviews in this list.</p>}
    {items.map(r => <article key={r.id} className="sb-review-admin-card">
      <header><strong>{r.product_name}</strong> <span>{"★".repeat(r.rating)}{"☆".repeat(5 - r.rating)}</span> <em>{r.status}</em></header>
      {r.title && <p><b>{r.title}</b></p>}
      {r.body && <p>{r.body}</p>}
      <small>{r.customer_name} ({r.customer_email}) · Order {r.order_number || "—"} · {dateText(r.created_at)}</small>
      <input placeholder="Note (optional)" maxLength={500} value={notes[r.id] ?? r.moderation_note ?? ""} onChange={e => setNotes(old => ({ ...old, [r.id]: e.target.value }))} />
      <div>
        {r.status !== "approved" && <button type="button" disabled={busyId === r.id} onClick={() => decide(r.id, "approved")}>Approve</button>}
        {r.status !== "rejected" && <button type="button" disabled={busyId === r.id} onClick={() => decide(r.id, "rejected")}>Reject</button>}
      </div>
    </article>)}
  </section>;
}
