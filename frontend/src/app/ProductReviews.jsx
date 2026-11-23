import { useCallback, useEffect, useRef, useState } from "react";
import { Star } from "lucide-react";

const dateText = value => value ? new Date(value).toLocaleDateString("en-IN", { day: "2-digit", month: "short", year: "numeric" }) : "";

function Stars({ value, size = 15 }) {
  return <span className="sb-review-stars" aria-label={value + " out of 5 stars"}>
    {[1, 2, 3, 4, 5].map(n => <Star key={n} size={size} aria-hidden="true" fill={n <= Math.round(value) ? "currentColor" : "none"} />)}
  </span>;
}

export default function ProductReviews({ productId, customerToken, request: requestProp, onSignIn, onChanged }) {
  // The parent recreates its request function on every render; keep the latest in a ref so loading does not loop.
  const requestRef = useRef(requestProp);
  requestRef.current = requestProp;
  const request = useCallback((...args) => requestRef.current(...args), []);
  const [data, setData] = useState({ rating_average: 0, review_count: 0, items: [] });
  const [loadError, setLoadError] = useState("");
  const [eligibility, setEligibility] = useState(null);
  const [rating, setRating] = useState(0);
  const [title, setTitle] = useState("");
  const [body, setBody] = useState("");
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("");
  const [formError, setFormError] = useState("");

  const load = useCallback(async () => {
    setLoadError("");
    try { setData(await request("/reviews/product/" + productId)); }
    catch { setData({ rating_average: 0, review_count: 0, items: [] }); setLoadError("Reviews could not be loaded right now."); }
    if (!customerToken) { setEligibility(null); return; }
    try { setEligibility(await request("/reviews/eligibility?product_id=" + productId)); }
    catch { setEligibility(null); }
  }, [productId, customerToken, request]);

  useEffect(() => { setRating(0); setTitle(""); setBody(""); setMessage(""); setFormError(""); load(); }, [load]);

  async function submit(event) {
    event.preventDefault();
    if (!rating) { setFormError("Please choose a star rating."); return; }
    setBusy(true); setFormError("");
    try {
      const result = await request("/reviews", { method: "POST", body: JSON.stringify({ product_id: Number(productId), rating, title, body }) });
      setMessage(result?.message || "Thank you. Your review is now live.");
      setRating(0); setTitle(""); setBody("");
      await load();
      if (onChanged) onChanged();
    } catch (err) { setFormError(err?.message || "Could not save your review."); }
    finally { setBusy(false); }
  }

  const existing = eligibility?.existing;
  const statusText = { pending: "waiting for approval", approved: "published", rejected: "not published" };

  return <section className="sb-reviews" aria-label="Customer reviews">
    <h2>Customer reviews</h2>
    {data.review_count > 0
      ? <p className="sb-reviews-summary"><Stars value={data.rating_average} /> <b>{Number(data.rating_average).toFixed(1)}</b> out of 5 · {data.review_count} {data.review_count === 1 ? "review" : "reviews"}</p>
      : <p className="sb-reviews-empty">No reviews yet.</p>}
    {loadError && <p className="sb-reviews-note" role="alert">{loadError}</p>}

    <div className="sb-review-form-box">
      {!customerToken && <p className="sb-reviews-note">Only customers who bought this product can write a review. <button type="button" className="sb-link-button" onClick={onSignIn}>Sign in</button></p>}
      {customerToken && eligibility?.reason === "not_delivered" && <p className="sb-reviews-note">You can write a review after your order with this product is delivered.</p>}
      {customerToken && existing && <p className="sb-reviews-note">You reviewed this product ({existing.rating} of 5 stars), {statusText[existing.status] || existing.status}.</p>}
      {message && <p className="sb-reviews-success" role="status">{message}</p>}
      {customerToken && eligibility?.can_review && !message && <form onSubmit={submit}>
        <h3>Write a review</h3>
        <div className="sb-review-pick" role="radiogroup" aria-label="Your rating">
          {[1, 2, 3, 4, 5].map(n => <button type="button" key={n} role="radio" aria-checked={rating === n} aria-label={n + (n === 1 ? " star" : " stars")} className={n <= rating ? "is-on" : ""} onClick={() => setRating(n)}><Star size={26} fill={n <= rating ? "currentColor" : "none"} /></button>)}
        </div>
        <label>Headline (optional)<input maxLength={120} value={title} onChange={e => setTitle(e.target.value)} /></label>
        <label>Your review (optional)<textarea rows={4} maxLength={2000} value={body} onChange={e => setBody(e.target.value)} /></label>
        {formError && <p className="sb-reviews-error" role="alert">{formError}</p>}
        <button type="submit" className="storefront-primary" disabled={busy}>{busy ? "Saving…" : "Submit review"}</button>
      </form>}
    </div>

    <ul className="sb-review-list">
      {data.items.map(item => <li key={item.id}>
        <div className="sb-review-head"><Stars value={item.rating} size={14} /> {item.title && <strong>{item.title}</strong>}</div>
        {item.body && <p>{item.body}</p>}
        <small>{item.author} · Verified buyer · {dateText(item.created_at)}</small>
      </li>)}
    </ul>
  </section>;
}
