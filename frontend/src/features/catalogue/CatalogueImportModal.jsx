import { useMemo, useRef, useState } from "react";
import { apiRequest } from "../../services/api.js";
import CatalogueModal from "./CatalogueModal.jsx";
import { buildImportPlan, parseCsv, templateCsv, toCsv } from "./csvImport.js";

const MAX_BYTES = 5 * 1024 * 1024;

function download(filename, text) {
  const url = URL.createObjectURL(new Blob(["﻿" + text], { type: "text/csv;charset=utf-8" }));
  const a = document.createElement("a");
  a.href = url; a.download = filename; document.body.appendChild(a); a.click(); a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}

export default function CatalogueImportModal({ open, categories = [], onClose, onImported }) {
  const fileRef = useRef(null);
  const [fileName, setFileName] = useState("");
  const [plan, setPlan] = useState(null);
  const [readError, setReadError] = useState("");
  const [busy, setBusy] = useState(false);
  const [progress, setProgress] = useState(0);
  const [results, setResults] = useState(null); // { key: {status, message} }
  const [finished, setFinished] = useState(false);

  const validItems = useMemo(() => (plan?.items || []).filter(i => !i.errors.length), [plan]);
  const invalidItems = useMemo(() => (plan?.items || []).filter(i => i.errors.length), [plan]);

  function reset() {
    setFileName(""); setPlan(null); setReadError(""); setBusy(false); setProgress(0); setResults(null); setFinished(false);
    if (fileRef.current) fileRef.current.value = "";
  }
  function close() {
    if (busy) return;
    const changed = finished;
    reset(); onClose?.(changed);
  }

  async function onFile(event) {
    const file = event.target.files?.[0];
    setPlan(null); setResults(null); setFinished(false); setReadError("");
    if (!file) return;
    setFileName(file.name);
    if (!/\.(csv|txt)$/i.test(file.name)) { setReadError("Please choose a .csv file. In Excel or Google Sheets use File → Save as/Download → CSV."); return; }
    if (file.size > MAX_BYTES) { setReadError("This file is larger than 5 MB. Split it into smaller files."); return; }
    try {
      const text = await file.text();
      setPlan(buildImportPlan(parseCsv(text), { categories }));
    } catch (e) { setReadError("Could not read this file: " + (e.message || "unknown error")); }
  }

  async function runImport() {
    if (busy || !validItems.length) return;
    setBusy(true); setFinished(false); setProgress(0);
    const out = {};
    for (let i = 0; i < validItems.length; i++) {
      const item = validItems[i];
      try {
        await apiRequest("/catalogue/products/complete", { method: "POST", body: JSON.stringify(item.payload) });
        out[item.key] = { status: "created", message: "Created" };
      } catch (e) {
        const msg = e.message || "Import failed";
        out[item.key] = /already exists/i.test(msg)
          ? { status: "skipped", message: "A product with this name already exists. Skipped" }
          : { status: "failed", message: msg };
      }
      setProgress(i + 1); setResults({ ...out });
    }
    setBusy(false); setFinished(true);
    if (Object.values(out).some(r => r.status === "created")) await onImported?.();
  }

  function downloadReport() {
    const rows = [["product", "rows", "result", "details"]];
    for (const item of plan.items) {
      const r = results?.[item.key];
      if (item.errors.length) rows.push([item.name, item.lines.join(" "), "invalid", item.errors.join(" ; ")]);
      else if (r) rows.push([item.name, item.lines.join(" "), r.status, r.message]);
      else rows.push([item.name, item.lines.join(" "), "not imported", ""]);
    }
    download("catalogue-import-report.csv", toCsv(rows));
  }

  const counts = results ? Object.values(results).reduce((a, r) => ({ ...a, [r.status]: (a[r.status] || 0) + 1 }), {}) : {};

  return <CatalogueModal
    open={open}
    title="Import products from CSV"
    className="sb-product-modal"
    onRequestClose={close}
    footer={<>
      {plan && !plan.fatal && !finished && <button type="button" className="sb-primary" disabled={busy || !validItems.length} onClick={runImport}>{busy ? `Importing ${progress}/${validItems.length}…` : `Import ${validItems.length} product${validItems.length === 1 ? "" : "s"}`}</button>}
      {finished && <button type="button" className="sb-primary" onClick={close}>Done</button>}
      <button type="button" className="sb-secondary" disabled={busy} onClick={close}>{finished ? "Close" : "Cancel"}</button>
    </>}
  >
    <div className="sb-import">
      <p className="sb-muted">Upload a CSV with one product per row. Required columns: <b>name</b>, <b>category</b> and <b>selling_price</b>. Others are optional: brand, description, hsn_code, gst_rate, mrp, cost_price, sku, barcode, status. Several rows with the same name become variants of one product, using columns like <b>attr_size</b>.</p>
      <div className="sb-import-actions">
        <button type="button" className="sb-secondary" onClick={() => download("catalogue-import-template.csv", templateCsv())}>Download template</button>
        <label className="sb-import-file">
          <span className="sb-secondary">Choose CSV file</span>
          <input ref={fileRef} type="file" accept=".csv,text/csv,text/plain" disabled={busy} onChange={onFile} hidden />
        </label>
        {fileName && <small className="sb-muted">{fileName}</small>}
      </div>
      <p className="sb-muted"><small>Categories must already exist (match by name, or use "Parent &gt; Child"; separate several with |). Products whose name already exists are skipped, never overwritten.</small></p>

      {readError && <p role="alert" className="sb-alert">{readError}</p>}
      {plan?.fatal && <p role="alert" className="sb-alert">{plan.fatal}</p>}
      {plan && !plan.fatal && <>
        {!!plan.unknownColumns.length && <p className="sb-alert" role="status">These columns are not recognised and will be ignored: {plan.unknownColumns.join(", ")}</p>}
        <p><b>{plan.items.length}</b> product{plan.items.length === 1 ? "" : "s"} found · <span style={{ color: "#18754f" }}>{validItems.length} ready</span>{!!invalidItems.length && <> · <span style={{ color: "#a82f45" }}>{invalidItems.length} with errors (will not be imported)</span></>}</p>
        {finished && <p className="sb-success" role="status">Finished: {counts.created || 0} created{counts.skipped ? `, ${counts.skipped} skipped` : ""}{counts.failed ? `, ${counts.failed} failed` : ""}.</p>}
        <div className="sb-strip-list sb-import-list" aria-label="Import preview">
          {plan.items.map(item => {
            const r = results?.[item.key];
            return <article className="sb-strip-row" key={item.key + item.lines[0]}>
              <div className="sb-strip-main">
                <strong>{item.name || "(no name)"}</strong>
                <small>Row{item.lines.length > 1 ? "s" : ""} {item.lines.join(", ")} · {item.variantCount} variant{item.variantCount === 1 ? "" : "s"}{item.payload.variants[0] ? ` · ₹${item.payload.variants[0].selling_price}` : ""}</small>
                {item.errors.map((e, i) => <small key={i} style={{ color: "#a82f45", display: "block" }}>{e}</small>)}
                {r && r.status !== "created" && <small style={{ color: r.status === "failed" ? "#a82f45" : "#8c6d1f", display: "block" }}>{r.message}</small>}
              </div>
              <span className={"sb-status-pill " + (item.errors.length || r?.status === "failed" ? "sb-status-archived" : "sb-status-active")}>{item.errors.length ? "Error" : r ? r.status : "Ready"}</span>
            </article>;
          })}
        </div>
        {(finished || invalidItems.length > 0) && <button type="button" className="sb-secondary" onClick={downloadReport}>Download report (CSV)</button>}
      </>}
    </div>
  </CatalogueModal>;
}
