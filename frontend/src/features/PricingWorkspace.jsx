import { useCallback, useEffect, useState } from "react";
import { apiRequest } from "../../services/api.js";
import "./pricing.css";

const money = value => new Intl.NumberFormat("en-IN", { style: "currency", currency: "INR", maximumFractionDigits: 2 }).format(Number(value || 0));

export default function PricingWorkspace({ onBack }) {
  const [items, setItems] = useState([]);
  const [total, setTotal] = useState(0);
  const [offset, setOffset] = useState(0);
  const [searchDraft, setSearchDraft] = useState("");
  const [search, setSearch] = useState("");
  const pageSize = 50;
  const [summary, setSummary] = useState(null);
  const [summaryError, setSummaryError] = useState("");
  const [drafts, setDrafts] = useState({});
  const [loading, setLoading] = useState(true);
  const [busyId, setBusyId] = useState(null);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const load = useCallback(async () => {
    setLoading(true); setError("");
    try {
      const params = new URLSearchParams({ limit: String(pageSize), offset: String(offset) });
      if (search) params.set("search", search);
      const [result, overview] = await Promise.all([
        apiRequest("/pricing/variants?" + params.toString()),
        apiRequest("/pricing/overview").catch(e => {
          setSummary(null); setSummaryError(e.message || "Pricing overview unavailable"); return null;
        }),
      ]);
      setItems(result.items || []); setTotal(Number(result.total || 0));
      if (overview) { setSummary(overview.metrics || null); setSummaryError(""); }
      setDrafts(Object.fromEntries((result.items || []).map(item => [item.id, {
        selling_price: String(item.selling_price), mrp: String(item.mrp),
        cost_price: item.cost_price == null ? "" : String(item.cost_price),
      }])));
    } catch (e) { setError(e.message || "Unable to load variant prices."); }
    finally { setLoading(false); }
  }, [offset, search]);
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
      await apiRequest("/pricing/variants/" + item.id + "/price", { method: "PUT", body: JSON.stringify({
        selling_price: selling, mrp, cost_price: draft.cost_price === "" ? null : Number(draft.cost_price),
      })});
      setNotice("Price saved for " + item.sku + "."); await load();
    } catch (e) { setError(e.message || "Unable to save price."); }
    finally { setBusyId(null); }
  }
  return <section className="sb-workspace sb-pricing" aria-label="Pricing and promotions workspace">
    <button className="sb-back" onClick={onBack} type="button">← All workspaces</button>
    <p className="sb-eyebrow">COMMERCE · PRICING</p><h1>Pricing & Promotions</h1>
    <p>Manage SKU-level selling price, MRP and cost price using the live pricing API.</p>
    {summaryError && <p className="sb-alert" role="status">{summaryError}. SKU price editing remains available.</p>}
    {summary && <div className="sb-report-grid" aria-label="Pricing overview">
      <article className="sb-report-card"><small>Active variants</small><strong>{Number(summary.variant_count || 0).toLocaleString("en-IN")}</strong><span>Live catalogue variants</span></article>
      <article className="sb-report-card"><small>Missing / zero price</small><strong>{Number(summary.missing_price_count || 0).toLocaleString("en-IN")}</strong><span>Require pricing review</span></article>
      <article className="sb-report-card"><small>Invalid MRP</small><strong>{Number(summary.invalid_mrp_count || 0).toLocaleString("en-IN")}</strong><span>MRP below selling price</span></article>
      <article className="sb-report-card"><small>Average selling price</small><strong>{money(summary.average_selling_price)}</strong><span>Across active variants</span></article>
    </div>}
    <div className="sb-pricing-toolbar"><strong>{total.toLocaleString("en-IN")} active variants</strong><button type="button" onClick={load} disabled={loading}>Refresh prices</button></div>
    <form className="sb-pricing-search" onSubmit={event => { event.preventDefault(); setOffset(0); setSearch(searchDraft.trim()); }}>
      <label>Search product, SKU or barcode<input value={searchDraft} onChange={event => setSearchDraft(event.target.value)} placeholder="Search catalogue variants" /></label>
      <button type="submit" className="sb-primary">Search</button>
      {search && <button type="button" className="sb-secondary" onClick={() => { setSearchDraft(""); setSearch(""); setOffset(0); }}>Clear</button>}
    </form>
    <div className="sb-pricing-pagination"><span>Showing {total ? offset + 1 : 0}–{Math.min(offset + items.length, total)} of {total} variants</span><div><button type="button" disabled={offset === 0 || loading} onClick={() => setOffset(Math.max(0, offset - pageSize))}>Previous</button><button type="button" disabled={offset + pageSize >= total || loading} onClick={() => setOffset(offset + pageSize)}>Next</button></div></div>
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
