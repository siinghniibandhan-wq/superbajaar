import { useCallback, useEffect, useState } from "react";
import { apiRequest } from "../../services/api.js";

const statusLabels = {
  pending: "Under review",
  proof_required: "Evidence required",
  approved: "Approved",
  rejected: "Not approved",
  expired: "Expired",
  cancelled: "Cancelled",
};

export default function IdentityClaimsPanel({ customerToken }) {
  const [targetSbid, setTargetSbid] = useState("");
  const [reason, setReason] = useState("");
  const [items, setItems] = useState([]);
  const [loading, setLoading] = useState(true);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");

  const request = useCallback((path, options = {}) => apiRequest(path, {
    ...options,
    skipAuth: true,
    headers: {
      ...(customerToken ? { Authorization: "Bearer " + customerToken } : {}),
      ...(options.headers || {}),
    },
  }), [customerToken]);

  const loadClaims = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      const result = await request("/customer-auth/identity-claims");
      setItems(Array.isArray(result.items) ? result.items : []);
    } catch (cause) {
      setError(cause.message || "Could not load your identity claim history.");
    } finally {
      setLoading(false);
    }
  }, [request]);

  useEffect(() => {
    loadClaims();
  }, [loadClaims]);

  const submitClaim = async event => {
    event.preventDefault();
    const sbid = targetSbid.trim().toUpperCase();
    const claimReason = reason.trim();
    if (!/^SBID-[A-Z0-9]{20}$/.test(sbid)) {
      setError("Enter a valid SBID in the format SBID- followed by 20 letters or numbers.");
      return;
    }
    if (claimReason.length < 5) {
      setError("Explain why this existing identity belongs to you.");
      return;
    }
    setSubmitting(true);
    setError("");
    setMessage("");
    try {
      const result = await request("/customer-auth/identity-claims", {
        method: "POST",
        body: JSON.stringify({ target_sbid: sbid, reason: claimReason }),
      });
      setMessage(result.message || "Your request has been submitted for review.");
      setTargetSbid("");
      setReason("");
      await loadClaims();
    } catch (cause) {
      setError(cause.message || "Could not submit your identity claim.");
    } finally {
      setSubmitting(false);
    }
  };

  return <section className="storefront-account-section storefront-identity-claims">
    <span className="storefront-kicker">YOUR SUPER BAJAAR IDENTITY</span>
    <h2>Claim an existing identity</h2>
    <p>If you already have a customer, employee or supplier-related identity, you can request a secure review to link it to your signed-in customer account. We will never merge records automatically.</p>
    <form className="storefront-account-form" onSubmit={submitClaim}>
      <label>Existing SBID
        <input value={targetSbid} onChange={event => setTargetSbid(event.target.value.toUpperCase())}
          placeholder="SBID-XXXXXXXXXXXXXXXXXXXX" autoComplete="off" maxLength={25}
          aria-describedby="identity-claim-sbid-help" required />
      </label>
      <small id="identity-claim-sbid-help">Enter the SBID shown on the existing identity record or shared with you by Super Bajaar.</small>
      <label>Why are you claiming this identity?
        <textarea value={reason} onChange={event => setReason(event.target.value)}
          rows={3} minLength={5} maxLength={500} required
          placeholder="Describe your relationship to the existing record. Do not enter passwords or OTPs." />
      </label>
      <button className="storefront-primary" type="submit" disabled={submitting || !targetSbid.trim() || reason.trim().length < 5}>
        {submitting ? "Submitting claim…" : "Submit for secure review"}
      </button>
    </form>
    {error && <p className="storefront-account-note" role="alert">{error}</p>}
    {message && <p className="storefront-account-note" role="status">{message}</p>}
    <div className="storefront-identity-claim-history">
      <div className="storefront-account-section-heading">
        <div><h3>Your claim history</h3><p>Only requests submitted from this signed-in account are shown.</p></div>
        <button type="button" className="storefront-inline-link" onClick={loadClaims} disabled={loading}>Refresh</button>
      </div>
      {loading ? <p className="storefront-account-note" role="status">Loading claim history…</p>
        : items.length ? <div className="storefront-account-summary">
          {items.map(item => <div key={item.id}>
            <small>Claim #{item.id} · {new Date(item.created_at).toLocaleString("en-IN")}</small>
            <strong>{statusLabels[item.status] || "Status unavailable"}</strong>
            <span>{item.reviewed_at ? "Reviewed " + new Date(item.reviewed_at).toLocaleString("en-IN") : item.expires_at ? "Review window ends " + new Date(item.expires_at).toLocaleDateString("en-IN") : "Awaiting review"}</span>
          </div>)}
        </div> : <p className="storefront-account-empty">You have not submitted any identity claims yet.</p>}
    </div>
  </section>;
}
