import { useMemo, useState } from "react";
import { apiRequest } from "../../services/api.js";
import "./StockSheet.css";

const PAGE_SIZE = 100;

const COPY = {
  add: { title: "Add stock", qty: "Quantity to add", help: "Pick the location once, then type a quantity only on the products you want. Empty rows are skipped.", button: "Add stock" },
  issue: { title: "Remove stock", qty: "Quantity to remove", help: "Pick the location once, then type a quantity only on the products you want to remove or scrap. Empty rows are skipped.", button: "Remove stock" },
  count: { title: "Count stock", qty: "Counted on shelf", help: "Type the quantity you physically counted, only for the products you counted. The system fixes the difference.", button: "Save counts" },
  transfer: { title: "Move stock", qty: "Quantity to move", help: "Pick From and To once, then type a quantity only on the products you want to move. Empty rows are skipped.", button: "Move stock" },
};

const num = value => (value === "" || value === undefined || value === null ? NaN : Number(value));

export default function StockSheet({ action = "add", variants = [], balances = [], locations = [], onDone }) {
  const copy = COPY[action] || COPY.add;
  const [locationId, setLocationId] = useState("");
  const [toLocationId, setToLocationId] = useState("");
  const [note, setNote] = useState("");
  const [adjustmentType, setAdjustmentType] = useState("opening_balance");
  const [reasonType, setReasonType] = useState("issue");
  const [allocation, setAllocation] = useState("fifo");
  const [defaultCost, setDefaultCost] = useState("");
  const [search, setSearch] = useState("");
  const [onlyStocked, setOnlyStocked] = useState(false);
  const [onlyFilled, setOnlyFilled] = useState(false);
  const [showDetails, setShowDetails] = useState(false);
  const [shown, setShown] = useState(PAGE_SIZE);
  const [rows, setRows] = useState({});
  const [errors, setErrors] = useState({});
  const [reviewing, setReviewing] = useState(false);
  const [working, setWorking] = useState("");
  const [problem, setProblem] = useState("");
  const [result, setResult] = useState(null);

  const hasDetails = action === "add" || action === "count";
  const needsCost = action === "add";

  const stockHere = useMemo(() => {
    const map = new Map();
    for (const b of balances) {
      if (String(b.location_id) === String(locationId)) map.set(String(b.variant_id), b);
    }
    return map;
  }, [balances, locationId]);

  const isFilled = id => {
    const q = num((rows[id] || {}).qty);
    return Number.isFinite(q) && (action === "count" ? q >= 0 : q > 0);
  };
  const hasText = id => String((rows[id] || {}).qty ?? "") !== "";
  const filledIds = variants.filter(v => hasText(v.id)).map(v => v.id);

  const filtered = useMemo(() => {
    const q = search.trim().toLowerCase();
    return variants.filter(v => {
      if (q && !String(v.product_name || "").toLowerCase().includes(q) && !String(v.sku || "").toLowerCase().includes(q)) return false;
      if (onlyStocked && !(Number(stockHere.get(String(v.id))?.on_hand || 0) > 0)) return false;
      if (onlyFilled && !hasText(v.id)) return false;
      return true;
    });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [variants, search, onlyStocked, onlyFilled, stockHere, rows]);

  const visible = filtered.slice(0, shown);

  function setRow(id, patch) {
    setRows(old => ({ ...old, [id]: { ...(old[id] || {}), ...patch } }));
    setErrors(old => { if (!old[id]) return old; const next = { ...old }; delete next[id]; return next; });
    setResult(null);
  }

  const costOf = row => (row.cost !== undefined && row.cost !== "" ? row.cost : defaultCost);

  function collect() {
    if (!locationId) return { problem: action === "transfer" ? "Choose the From location first." : "Choose the location first." };
    if (action === "transfer") {
      if (!toLocationId) return { problem: "Choose the To location first." };
      if (toLocationId === locationId) return { problem: "From and To location must be different." };
    }
    if (note.trim().length < 3) return { problem: "Enter a reason or reference (at least 3 letters)." };
    const items = [];
    for (const v of variants) {
      if (!hasText(v.id)) continue;
      const row = rows[v.id] || {};
      const q = num(row.qty);
      if (!Number.isFinite(q) || (action === "count" ? q < 0 : q <= 0)) {
        return { problem: v.sku + ": enter a valid quantity" + (action === "count" ? " (0 or more)." : " (more than 0).") };
      }
      if (needsCost) {
        const c = num(costOf(row));
        if (!Number.isFinite(c) || c < 0) return { problem: v.sku + ": enter a unit cost, or type a Default unit cost at the top." };
      }
      items.push({ variant: v, row, qty: q });
    }
    if (!items.length) return { problem: "Type a quantity on at least one product." };
    return { items };
  }

  function payloadFor({ variant, row, qty }) {
    const batch = row.batch || null;
    const expiry = row.expiry || null;
    if (action === "add") {
      return { variant_id: Number(variant.id), location_id: Number(locationId), quantity: qty, unit_cost: Number(costOf(row)), adjustment_type: adjustmentType, batch_code: batch, expiry_date: expiry, note: note.trim() };
    }
    if (action === "issue") {
      return { variant_id: Number(variant.id), location_id: Number(locationId), quantity: qty, note: note.trim(), reason_type: reasonType, allocation_method: allocation };
    }
    if (action === "count") {
      const c = num(costOf(row));
      return { variant_id: Number(variant.id), location_id: Number(locationId), counted_quantity: qty, unit_cost: Number.isFinite(c) ? c : null, batch_code: batch, expiry_date: expiry, allocation_method: allocation, note: note.trim() };
    }
    return { variant_id: Number(variant.id), source_location_id: Number(locationId), destination_location_id: Number(toLocationId), quantity: qty, note: note.trim() };
  }

  const PATHS = { add: "/inventory/adjustments", issue: "/inventory/issues", count: "/inventory/counts", transfer: "/inventory/transfers" };
  const approvalType = action === "add" ? adjustmentType : action === "issue" ? (reasonType === "scrap" ? "scrap" : "issue") : action === "count" ? "physical_count" : "transfer";

  function startReview() {
    const found = collect();
    if (found.problem) { setProblem(found.problem); return; }
    setProblem(""); setResult(null); setReviewing(true);
    window.scrollTo?.({ top: 0, behavior: "smooth" });
  }

  async function run(mode) {
    const found = collect();
    if (found.problem) { setProblem(found.problem); setReviewing(false); return; }
    setProblem(""); setResult(null);
    const failed = [];
    const doneIds = [];
    const newErrors = {};
    for (let i = 0; i < found.items.length; i += 1) {
      const item = found.items[i];
      setWorking("Saving " + (i + 1) + " of " + found.items.length + "…");
      try {
        const payload = payloadFor(item);
        if (mode === "approval") {
          await apiRequest("/inventory/approval-requests", { method: "POST", body: JSON.stringify({ event_type: approvalType, location_id: Number(locationId), payload }) });
        } else {
          await apiRequest(PATHS[action], { method: "POST", body: JSON.stringify(payload) });
        }
        doneIds.push(item.variant.id);
      } catch (e) {
        const msg = e?.message || "Failed";
        failed.push({ sku: item.variant.sku, name: item.variant.product_name, msg });
        newErrors[item.variant.id] = msg;
      }
    }
    setWorking("");
    setRows(old => { const next = { ...old }; for (const id of doneIds) delete next[id]; return next; });
    setErrors(newErrors);
    setResult({ mode, ok: doneIds.length, failed });
    setReviewing(false);
    try { await onDone?.(); } catch { /* list refresh is best-effort */ }
    window.scrollTo?.({ top: 0, behavior: "smooth" });
  }

  const locationName = id => locations.find(l => String(l.id) === String(id))?.name || "";
  const reviewItems = reviewing ? (collect().items || []) : [];

  return <div className="ss">
    <header className="ss-head"><h2>{copy.title}</h2><p className="sb-muted">{copy.help}</p></header>

    {result && <div className={"ss-result " + (result.failed.length ? "has-fail" : "all-ok")} role="status">
      <strong>{result.mode === "approval" ? "Sent for approval: " : "Saved: "}{result.ok} row(s){result.failed.length ? " · Failed: " + result.failed.length : ""}</strong>
      {result.mode === "approval" && result.ok > 0 && <p>No stock has moved yet. Check the To-do tab for the approval requests.</p>}
      {result.failed.length > 0 && <>
        <p>These rows did not save. They are still in the list below with the reason. Fix them and save again.</p>
        <ul>{result.failed.map(f => <li key={f.sku}><b>{f.sku}</b> {f.name ? "(" + f.name + ")" : ""}: {f.msg}</li>)}</ul>
      </>}
    </div>}

    {reviewing ? <section className="ss-card" aria-label="Review before saving">
      <h3>Check before saving</h3>
      <p className="sb-muted">{copy.title} · {action === "transfer" ? "From " + locationName(locationId) + " to " + locationName(toLocationId) : locationName(locationId)} · Reason: {note.trim()}</p>
      <div className="ss-review-list">
        {reviewItems.map(({ variant, qty }) => <div className="ss-review-row" key={variant.id}>
          <span><strong>{variant.product_name}</strong><small>{variant.sku}</small></span>
          <b>{qty}</b>
        </div>)}
      </div>
      <div className="ss-actions">
        <button type="button" className="sb-primary" disabled={Boolean(working)} onClick={() => run("save")}>{working || "Confirm and save " + reviewItems.length + " row(s)"}</button>
        <button type="button" className="sb-secondary" disabled={Boolean(working)} onClick={() => run("approval")}>Send for approval instead</button>
        <button type="button" className="sb-secondary" disabled={Boolean(working)} onClick={() => setReviewing(false)}>Back to edit</button>
      </div>
    </section> : <>
      <section className="ss-card" aria-label="Settings for all rows">
        <h3><span className="ss-step">1</span> Settings for all rows</h3>
        <div className="ss-grid">
          <label>{action === "transfer" ? "From location" : "Stock location"}
            <select value={locationId} onChange={e => { setLocationId(e.target.value); setResult(null); }}>
              <option value="">Choose location</option>
              {locations.map(l => <option key={l.id} value={l.id}>{l.name}{l.location_type ? " (" + l.location_type + ")" : ""}</option>)}
            </select></label>
          {action === "transfer" && <label>To location
            <select value={toLocationId} onChange={e => setToLocationId(e.target.value)}>
              <option value="">Choose location</option>
              {locations.filter(l => l.is_fulfillable !== false && String(l.id) !== String(locationId)).map(l => <option key={l.id} value={l.id}>{l.name}</option>)}
            </select></label>}
          {action === "add" && <label>What is this?
            <select value={adjustmentType} onChange={e => setAdjustmentType(e.target.value)}>
              <option value="opening_balance">Opening stock (new quantity)</option>
              <option value="stock_gain">Found stock (new quantity)</option>
              <option value="opening_valuation">Only set cost of existing stock (quantity stays same)</option>
            </select></label>}
          {action === "issue" && <label>What is this?
            <select value={reasonType} onChange={e => setReasonType(e.target.value)}>
              <option value="issue">Issue / remove stock</option>
              <option value="scrap">Scrap / damaged stock</option>
            </select></label>}
          {(action === "issue" || action === "count") && <label>Cost method
            <select value={allocation} onChange={e => setAllocation(e.target.value)}>
              <option value="fifo">FIFO (oldest first)</option>
              <option value="fefo">FEFO (earliest expiry first)</option>
            </select></label>}
          {hasDetails && <label>{action === "add" ? "Default unit cost (₹)" : "Unit cost if count goes up (₹, optional)"}
            <input type="number" inputMode="decimal" min="0" step="0.0001" value={defaultCost} onChange={e => setDefaultCost(e.target.value)} placeholder={action === "add" ? "Used on rows without own cost" : "Optional"} /></label>}
          <label className="ss-wide">Reason / reference
            <input maxLength="500" value={note} onChange={e => setNote(e.target.value)} placeholder="Example: Opening stock Nov 2026" /></label>
        </div>
      </section>

      <section className="ss-card" aria-label="Choose products">
        <h3><span className="ss-step">2</span> Type quantities ({variants.length} products/SKUs)</h3>
        <input className="ss-search" type="search" aria-label="Search product or SKU" placeholder="Search product or SKU" value={search} onChange={e => { setSearch(e.target.value); setShown(PAGE_SIZE); }} />
        <div className="ss-toggles">
          {action !== "add" && <label><input type="checkbox" checked={onlyStocked} onChange={e => { setOnlyStocked(e.target.checked); setShown(PAGE_SIZE); }} /> Only items with stock here</label>}
          <label><input type="checkbox" checked={onlyFilled} onChange={e => { setOnlyFilled(e.target.checked); setShown(PAGE_SIZE); }} /> Only rows I filled</label>
          {hasDetails && <label><input type="checkbox" checked={showDetails} onChange={e => setShowDetails(e.target.checked)} /> Show cost, batch and expiry</label>}
        </div>
        {!locationId && <p className="ss-hint">Choose the location above to see current stock on each row.</p>}
        {!variants.length && <p className="sb-empty">No active products with variants found. Add products in Catalogue first.</p>}
        <div className="ss-list">
          {visible.map(v => {
            const row = rows[v.id] || {};
            const bal = stockHere.get(String(v.id));
            const onHand = Number(bal?.on_hand || 0);
            const available = Number(bal?.available ?? (onHand - Number(bal?.reserved || 0)));
            const q = num(row.qty);
            return <div className={"ss-row" + (hasText(v.id) ? " is-filled" : "") + (errors[v.id] ? " has-error" : "")} key={v.id}>
              <div className="ss-name"><strong>{v.product_name}</strong><small>{v.sku}</small></div>
              <div className="ss-stock"><b>{locationId ? available : "–"}</b><small>available here</small></div>
              <label className="ss-qty"><span>{copy.qty}</span>
                <input type="number" inputMode="decimal" min={action === "count" ? "0" : "0.001"} step="0.001" value={row.qty ?? ""} onChange={e => setRow(v.id, { qty: e.target.value })} /></label>
              {showDetails && hasDetails && <div className="ss-extra">
                <label>Unit cost (₹)<input type="number" inputMode="decimal" min="0" step="0.0001" value={row.cost ?? ""} placeholder={defaultCost || "Default"} onChange={e => setRow(v.id, { cost: e.target.value })} /></label>
                <label>Batch / lot<input maxLength="100" value={row.batch ?? ""} onChange={e => setRow(v.id, { batch: e.target.value })} /></label>
                <label>Expiry date<input type="date" value={row.expiry ?? ""} onChange={e => setRow(v.id, { expiry: e.target.value })} /></label>
              </div>}
              {action === "count" && Number.isFinite(q) && locationId && <p className="ss-variance">System has {onHand} · difference {q - onHand > 0 ? "+" : ""}{Math.round((q - onHand) * 1000) / 1000}</p>}
              {errors[v.id] && <p className="ss-err" role="alert">{errors[v.id]}</p>}
            </div>;
          })}
          {variants.length > 0 && !filtered.length && <p className="sb-empty">No product matches your filters.</p>}
        </div>
        {filtered.length > shown && <button type="button" className="sb-secondary ss-more" onClick={() => setShown(n => n + PAGE_SIZE)}>Show more ({filtered.length - shown} left)</button>}
      </section>

      {problem && <p className="sb-alert" role="alert">{problem}</p>}
      <div className="ss-bar">
        <span><b>{filledIds.length}</b> row(s) filled</span>
        <div>
          {filledIds.length > 0 && <button type="button" className="sb-secondary" onClick={() => { setRows({}); setErrors({}); setProblem(""); setResult(null); }}>Clear all</button>}
          <button type="button" className="sb-primary" disabled={!filledIds.length} onClick={startReview}>Review and save</button>
        </div>
      </div>
    </>}
  </div>;
}
