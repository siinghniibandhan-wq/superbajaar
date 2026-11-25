import { useEffect, useState } from "react";
import { apiRequest } from "../../services/api.js";

// Reusable "choose from already uploaded images" picker.
// Tiles are fixed square boxes so wide banners and tall photos both show in full.
export default function ImageLibraryPicker({ initialSelection = [], multiple = true, confirmLabel = "Use selected", onConfirm, onCancel }) {
  const [items, setItems] = useState([]);
  const [query, setQuery] = useState("");
  const [loading, setLoading] = useState(false);
  const [hasMore, setHasMore] = useState(false);
  const [error, setError] = useState("");
  const [selected, setSelected] = useState(initialSelection);

  async function load(q = query, append = false, offset = items.length) {
    setLoading(true); setError("");
    try {
      const result = await apiRequest("/catalogue/media-library?limit=48&offset=" + (append ? offset : 0) + "&q=" + encodeURIComponent(q.trim()));
      setItems(prev => append ? [...prev, ...(result.items || [])] : (result.items || []));
      setHasMore(Boolean(result.has_more));
    } catch (e) { setError(e.message || "Unable to load the image library."); }
    finally { setLoading(false); }
  }
  useEffect(() => { load("", false, 0); }, []);

  const isOn = item => selected.some(i => i.image_url === item.image_url);
  function toggle(item) {
    const entry = { image_url: item.image_url, alt_text: item.alt_text || "" };
    if (!multiple) { setSelected([entry]); return; }
    setSelected(prev => prev.some(i => i.image_url === item.image_url) ? prev.filter(i => i.image_url !== item.image_url) : [...prev, entry]);
  }

  return <div className="sb-lib" role="dialog" aria-label="Image library">
    <div className="sb-lib-head">
      <input type="search" placeholder="Search by product, name or file…" value={query} onChange={e => setQuery(e.target.value)} onKeyDown={e => { if (e.key === "Enter") { e.preventDefault(); load(query, false, 0); } }} />
      <div className="sb-lib-actions">
        <button type="button" className="sb-row-action" onClick={() => load(query, false, 0)}>Search</button>
        <button type="button" className="sb-row-action" onClick={onCancel}>Cancel</button>
        <button type="button" className="sb-primary" disabled={!selected.length} onClick={() => onConfirm(selected)}>{confirmLabel} ({selected.length})</button>
      </div>
    </div>
    {error && <p className="sb-error">{error}</p>}
    {loading && !items.length ? <p className="sb-muted">Loading images…</p> : items.length ? <div className="sb-lib-grid">
      {items.map(item => <div key={item.image_url} role="button" tabIndex={0} aria-pressed={isOn(item)} className={"sb-lib-tile" + (isOn(item) ? " is-selected" : "")} onClick={() => toggle(item)} onKeyDown={e => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); toggle(item); } }} title={item.alt_text || item.image_url}>
        <div className="sb-lib-thumb"><img src={item.image_url} alt={item.alt_text || ""} loading="lazy" onError={e => { e.currentTarget.style.visibility = "hidden"; }} />{isOn(item) && <span className="sb-lib-tick">✓</span>}</div>
        <span className="sb-lib-name">{item.alt_text || "Image"}</span>
        <small className="sb-lib-meta">{(item.product_names || []).join(", ")}{item.use_count > 1 ? " · used " + item.use_count + "×" : ""}</small>
      </div>)}
    </div> : <p className="sb-empty">No uploaded images found.</p>}
    {hasMore && <button type="button" className="sb-row-action" disabled={loading} onClick={() => load(query, true, items.length)}>{loading ? "Loading…" : "Load more"}</button>}
  </div>;
}
