import { useEffect, useMemo, useState } from "react";
import { apiRequest } from "../../services/api.js";
import { parseCsv, toCsv } from "./csvImport.js";
import { GST_RATES, cleanHsn, isValidHsn, categoryPath, categoriesWithoutRule, parseConditions, formatConditions } from "./hsnRules.js";

const BLANK = { id: null, category_id: "", conditions: [], hsn_code: "", gst_rate: "", note: "" };
const CSV_HEADERS = ["category_id", "category_path", "conditions", "hsn_code", "gst_rate", "note"];

export default function HsnRulesPanel({ categories = [] }) {
  const [rules, setRules] = useState([]);
  const [definitions, setDefinitions] = useState([]);
  const [form, setForm] = useState(BLANK);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");

  async function load() {
    const [ruleResult, attributeResult] = await Promise.all([
      apiRequest("/catalogue/hsn-rules"),
      apiRequest("/catalogue/attributes?limit=5000").catch(() => ({ items: [] })),
    ]);
    setRules(ruleResult.items || []);
    setDefinitions(attributeResult.items || []);
  }
  useEffect(() => { load().catch(e => setError(e.message || "Unable to load HSN rules.")); }, []);

  const sortedCategories = useMemo(() => [...categories].filter(c => c.is_active !== false)
    .map(c => ({ ...c, path: categoryPath(categories, c.id) })).sort((a, b) => a.path.localeCompare(b.path)), [categories]);
  const missing = useMemo(() => categoriesWithoutRule(categories, rules), [categories, rules]);
  const attributeName = code => definitions.find(d => d.code === code)?.name || code;

  const setField = (key, value) => setForm(old => ({ ...old, [key]: value }));
  const setCondition = (index, key, value) => setForm(old => ({ ...old, conditions: old.conditions.map((c, i) => i === index ? { ...c, [key]: value } : c) }));

  function edit(rule) {
    setError(""); setMessage("");
    setForm({ id: rule.id, category_id: rule.category_id ? String(rule.category_id) : "", conditions: Object.entries(rule.conditions || {}).map(([code, value]) => ({ code, value })), hsn_code: rule.hsn_code, gst_rate: String(Number(rule.gst_rate)), note: rule.note || "" });
    window.scrollTo?.({ top: 0, behavior: "smooth" });
  }

  async function save(event) {
    event.preventDefault();
    setError(""); setMessage("");
    if (!isValidHsn(form.hsn_code)) { setError("HSN code must be exactly 8 digits."); return; }
    if (form.gst_rate === "") { setError("Select a GST rate."); return; }
    if (!form.category_id && !form.conditions.some(c => c.code && c.value.trim())) { setError("Choose a category or add at least one condition."); return; }
    const conditions = Object.fromEntries(form.conditions.filter(c => c.code && c.value.trim()).map(c => [c.code, c.value.trim()]));
    const body = JSON.stringify({ category_id: form.category_id ? Number(form.category_id) : null, conditions, hsn_code: form.hsn_code, gst_rate: Number(form.gst_rate), note: form.note.trim() || null });
    setBusy(true);
    try {
      await apiRequest(form.id ? "/catalogue/hsn-rules/" + form.id : "/catalogue/hsn-rules", { method: form.id ? "PUT" : "POST", body });
      setForm(BLANK); setMessage("HSN rule saved."); await load();
    } catch (e) { setError(e.message || "Unable to save the rule."); } finally { setBusy(false); }
  }

  async function remove(rule) {
    if (!window.confirm("Delete this HSN rule? Products keep the HSN they already have.")) return;
    setBusy(true); setError(""); setMessage("");
    try { await apiRequest("/catalogue/hsn-rules/" + rule.id, { method: "DELETE" }); setMessage("HSN rule deleted."); await load(); }
    catch (e) { setError(e.message || "Unable to delete the rule."); } finally { setBusy(false); }
  }

  function downloadSheet() {
    const rows = [CSV_HEADERS];
    for (const rule of rules) rows.push([rule.category_id ?? "", rule.category_id ? categoryPath(categories, rule.category_id) : "", formatConditions(rule.conditions), rule.hsn_code, Number(rule.gst_rate), rule.note || ""]);
    for (const category of missing) rows.push([category.id, categoryPath(categories, category.id), "", "", "", ""]);
    const url = URL.createObjectURL(new Blob([toCsv(rows)], { type: "text/csv" }));
    const link = document.createElement("a"); link.href = url; link.download = "hsn-rules-sheet.csv"; link.click(); URL.revokeObjectURL(url);
  }

  async function uploadSheet(event) {
    const file = event.target.files?.[0]; event.target.value = "";
    if (!file) return;
    setError(""); setMessage(""); setBusy(true);
    try {
      const rows = parseCsv(await file.text());
      const header = (rows.shift() || []).map(h => String(h).trim().toLowerCase());
      const col = name => header.indexOf(name);
      if (col("hsn_code") === -1 || col("gst_rate") === -1) throw new Error("The sheet needs hsn_code and gst_rate columns. Download the sheet to get the right format.");
      const ids = new Set(categories.map(c => String(c.id)));
      const items = []; const problems = [];
      rows.forEach((row, index) => {
        const get = name => (col(name) === -1 ? "" : String(row[col(name)] ?? "").trim());
        if (!get("hsn_code") && !get("gst_rate")) return;
        const line = index + 2;
        const hsn = cleanHsn(get("hsn_code"));
        const rate = String(Number(get("gst_rate")));
        const categoryId = get("category_id");
        if (!isValidHsn(hsn)) problems.push("Row " + line + ": HSN must be exactly 8 digits.");
        else if (get("gst_rate") === "" || !GST_RATES.includes(rate)) problems.push("Row " + line + ": GST rate is not a supported rate.");
        else if (categoryId && !ids.has(categoryId)) problems.push("Row " + line + ": category_id " + categoryId + " does not exist.");
        else items.push({ category_id: categoryId ? Number(categoryId) : null, conditions: parseConditions(get("conditions")), hsn_code: hsn, gst_rate: Number(rate), note: get("note") || null });
      });
      if (problems.length) throw new Error(problems.slice(0, 5).join(" ") + (problems.length > 5 ? " (+" + (problems.length - 5) + " more)" : "") + " Nothing was saved.");
      if (!items.length) throw new Error("No filled rows found. Fill in hsn_code and gst_rate and try again.");
      const result = await apiRequest("/catalogue/hsn-rules/bulk", { method: "POST", body: JSON.stringify({ items }) });
      setMessage("Sheet loaded: " + result.created + " rule(s) added, " + result.updated + " updated."); await load();
    } catch (e) { setError(e.message || "Unable to load the sheet."); } finally { setBusy(false); }
  }

  const productAttributes = definitions.filter(d => !d.is_variant_attribute);

  return <>
    <div className="sb-catalogue-toolbar">
      <div><h2>HSN rules</h2><p className="sb-muted">Set the 8-digit HSN and GST rate once for a category, then product forms fill it in automatically. A rule on a category also covers its sub-categories, including ones you add later.</p></div>
      <div className="sb-product-actions">
        <button type="button" className="sb-secondary" disabled={busy} onClick={downloadSheet}>Download sheet</button>
        <label className="sb-secondary" style={{ cursor: "pointer" }}>Upload filled sheet<input type="file" accept=".csv,text/csv" hidden disabled={busy} onChange={uploadSheet} /></label>
      </div>
    </div>
    {error && <p role="alert" className="sb-alert">{error}</p>}
    {message && <p role="status" className="sb-success">{message}</p>}

    <form className="sb-form" noValidate onSubmit={save}>
      <h3>{form.id ? "Edit rule" : "Add rule"}</h3>
      <div className="sb-form-grid">
        <label>Category / sub-category<select value={form.category_id} onChange={e => setField("category_id", e.target.value)}><option value="">Any category</option>{sortedCategories.map(c => <option key={c.id} value={c.id}>{c.path}</option>)}</select></label>
        <label>HSN code (8 digits) *<input inputMode="numeric" maxLength="8" value={form.hsn_code} onChange={e => setField("hsn_code", cleanHsn(e.target.value))} placeholder="e.g. 10063090" /></label>
        <label>GST rate *<select value={form.gst_rate} onChange={e => setField("gst_rate", e.target.value)}><option value="">Select GST rate</option>{GST_RATES.map(rate => <option key={rate} value={rate}>{rate}%</option>)}</select></label>
        <label>Note (optional)<input maxLength="300" value={form.note} onChange={e => setField("note", e.target.value)} placeholder="e.g. Loose rice, not pre-packed" /></label>
      </div>
      <div className="sb-attribute-picker">
        <strong>Only when the product details say (optional)</strong>
        <small className="sb-muted">Use this for Form, Formulation or Packaging, e.g. Packaging = Loose. More conditions make a rule more specific, so it wins over a plain category rule.</small>
        {form.conditions.map((condition, index) => <div className="sb-add-option" key={index}>
          <select aria-label="Attribute" value={condition.code} onChange={e => setCondition(index, "code", e.target.value)}><option value="">Select attribute</option>{productAttributes.map(d => <option key={d.id} value={d.code}>{d.name}</option>)}</select>
          <input aria-label="Value" list={"hsn-values-" + index} value={condition.value} onChange={e => setCondition(index, "value", e.target.value)} placeholder="Value, e.g. Loose" />
          <datalist id={"hsn-values-" + index}>{(definitions.find(d => d.code === condition.code)?.options || []).map(option => <option key={String(option)} value={typeof option === "string" ? option : option?.name} />)}</datalist>
          <button type="button" className="sb-secondary" onClick={() => setForm(old => ({ ...old, conditions: old.conditions.filter((_, i) => i !== index) }))}>Remove</button>
        </div>)}
        <button type="button" className="sb-secondary" onClick={() => setForm(old => ({ ...old, conditions: [...old.conditions, { code: "", value: "" }] }))}>Add condition</button>
        {!productAttributes.length && <small className="sb-muted">No product attributes yet. Create attributes named Form, Formulation and Packaging in the Attributes tab first.</small>}
      </div>
      <div className="sb-product-actions">
        <button type="submit" className="sb-primary" disabled={busy}>{form.id ? "Save changes" : "Add rule"}</button>
        {form.id && <button type="button" className="sb-secondary" disabled={busy} onClick={() => setForm(BLANK)}>Cancel edit</button>}
      </div>
    </form>

    <section aria-label="Categories without an HSN rule">
      <h3>Categories without an HSN rule <span className="sb-muted">({missing.length})</span></h3>
      {missing.length ? <div className="sb-strip-list">{missing.map(category => <article className="sb-strip-row" key={category.id}>
        <div className="sb-strip-main"><strong>{categoryPath(categories, category.id)}</strong><small>No rule yet. HSN stays empty on products until you add one.</small></div>
        <button type="button" className="sb-secondary" onClick={() => { setForm({ ...BLANK, category_id: String(category.id) }); window.scrollTo?.({ top: 0, behavior: "smooth" }); }}>Add rule</button>
      </article>)}</div> : <p className="sb-muted">Every category and sub-category is covered.</p>}
    </section>

    <section aria-label="HSN rules list">
      <h3>Rules <span className="sb-muted">({rules.length})</span></h3>
      {rules.length ? <div className="sb-strip-list">{rules.map(rule => <article className="sb-strip-row" key={rule.id}>
        <div className="sb-strip-main">
          <strong>{rule.category_id ? categoryPath(categories, rule.category_id) || "Category #" + rule.category_id : "Any category"}</strong>
          <small>{Object.keys(rule.conditions || {}).length ? Object.entries(rule.conditions).map(([code, value]) => attributeName(code) + " = " + value).join(" · ") : "No extra conditions"}{rule.note ? " · " + rule.note : ""}</small>
        </div>
        <span><strong>{rule.hsn_code}</strong> · GST {Number(rule.gst_rate)}%</span>
        <span className="sb-product-actions"><button type="button" className="sb-secondary" disabled={busy} onClick={() => edit(rule)}>Edit</button><button type="button" className="sb-secondary" disabled={busy} onClick={() => remove(rule)}>Delete</button></span>
      </article>)}</div> : <p className="sb-empty">No rules yet. Add one above, or download the sheet, fill it in and upload it.</p>}
    </section>
  </>;
}
