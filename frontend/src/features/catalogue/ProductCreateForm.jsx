import { useEffect, useMemo, useState } from "react";
import { apiRequest } from "../../services/api.js";

const EMPTY = { name: "", slug: "", brand: "", category_id: "", description: "", tax_code: "", tax_rate: "", selling_price: "", mrp: "" };
const OPTION_TYPES = ["select", "multi_select", "colour", "size"];

function combinations(items) {
  return items.reduce((acc, item) => acc.flatMap(prefix => item.values.map(value => [...prefix, [item.code, value]])), [[]]).map(entries => Object.fromEntries(entries));
}

export default function ProductCreateForm({ categories = [], product = null, onSaved }) {
  const [form, setForm] = useState(product ? { ...EMPTY, ...product, category_id: product.category_id ? String(product.category_id) : "" } : EMPTY);
  const [definitions, setDefinitions] = useState([]);
  const [selected, setSelected] = useState({});
  const [newOptions, setNewOptions] = useState({});
  const [activeTab, setActiveTab] = useState("general");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [success, setSuccess] = useState("");
  const slugify = value => value.toLowerCase().trim().replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "");
  const change = (key, value) => setForm(old => ({ ...old, [key]: value }));

  async function loadDefinitions() {
    const result = await apiRequest("/catalogue/attributes");
    setDefinitions(result.items || []);
  }
  useEffect(() => { loadDefinitions().catch(e => setError(e.message || "Unable to load attributes.")); }, []);

  const chosenAttributes = useMemo(() => definitions.filter(def => def.is_variant_attribute && (selected[def.code] || []).length), [definitions, selected]);
  const variantCombinations = useMemo(() => {
    if (!chosenAttributes.length) return [{}];
    return combinations(chosenAttributes.map(def => ({ code: def.code, values: def.value_type === "multi_select" ? [[...(selected[def.code] || [])]] : (selected[def.code] || []) })));
  }, [chosenAttributes, selected]);

  function toggleValue(def, value) {
    setSelected(old => {
      const values = old[def.code] || [];
      return { ...old, [def.code]: values.includes(value) ? values.filter(item => item !== value) : [...values, value] };
    });
  }

  async function addOption(def) {
    const raw = (newOptions[def.code] || "").trim();
    if (!raw) return;
    await apiRequest("/catalogue/attributes/" + def.id + "/options", { method: "PUT", body: JSON.stringify({ options: [raw] }) });
    await loadDefinitions();
    setSelected(old => ({ ...old, [def.code]: [...(old[def.code] || []), raw] }));
    setNewOptions(old => ({ ...old, [def.code]: "" }));
  }

  async function submit(event) {
    event.preventDefault();
    setBusy(true); setError(""); setSuccess("");
    let savedProduct = null;
    try {
      if (!form.name.trim()) throw new Error("Product name is required.");
      if (!form.slug.trim()) throw new Error("Product slug could not be generated. Enter a valid product name.");
      const price = Number(form.selling_price);
      const mrp = Number(form.mrp);
      if (!Number.isFinite(price) || !Number.isFinite(mrp) || form.selling_price === "" || form.mrp === "" || price < 0 || mrp < price) {
        setActiveTab("general");
        throw new Error("Enter a valid selling price and an MRP equal to or higher than the selling price.");
      }
      const payload = { name: form.name.trim(), slug: form.slug, brand: form.brand || null, category_id: form.category_id ? Number(form.category_id) : null, description: form.description || null, tax_code: form.tax_code || null, tax_rate: form.tax_rate === "" ? null : Number(form.tax_rate), status: product?.status || "active" };
      savedProduct = await apiRequest(product?.id ? "/catalogue/products/" + product.id : "/catalogue/products", { method: product?.id ? "PUT" : "POST", body: JSON.stringify(payload) });
      // Editing updates only the product record. It must not duplicate existing variants.
      if (!product?.id) {
        for (const def of chosenAttributes) {
          const values = selected[def.code] || [];
          if (OPTION_TYPES.includes(def.value_type)) {
            const missing = values.filter(value => !(def.options || []).some(option => String(option) === String(value)));
            if (missing.length) await apiRequest("/catalogue/attributes/" + def.id + "/options", { method: "PUT", body: JSON.stringify({ options: missing }) });
          }
        }
        for (const attrs of variantCombinations) {
          await apiRequest("/catalogue/products/" + savedProduct.id + "/variants", {
            method: "POST",
            body: JSON.stringify({ attributes: attrs, selling_price: price, mrp, cost_price: null }),
          });
        }
      }
      setSuccess(product?.id ? "Product details updated. Existing variants were preserved." : "Product saved with " + variantCombinations.length + " variant(s) and default prices.");
      await onSaved?.(savedProduct);
    } catch (e) {
      setError((e.message || "Unable to save product.") + (savedProduct && !product?.id ? " The product record was created, but one or more variant operations may not have completed. Review its variants before retrying." : ""));
    } finally { setBusy(false); }
  }

  return <form className="sb-form" noValidate onSubmit={submit}>
    <h2>{product ? "Edit product" : "Add product"}</h2>
    {error && <p role="alert" className="sb-alert">{error}</p>}
    {success && <p role="status" className="sb-success">{success}</p>}
    <nav className="sb-catalogue-tabs" aria-label="Product form sections" role="tablist">
      <button type="button" role="tab" aria-selected={activeTab === "general"} className={activeTab === "general" ? "is-active" : ""} onClick={() => setActiveTab("general")}>Product Information</button>
      <button type="button" role="tab" aria-selected={activeTab === "attributes"} className={activeTab === "attributes" ? "is-active" : ""} onClick={() => setActiveTab("attributes")}>Attributes &amp; Variants</button>
    </nav>
    <section hidden={activeTab !== "general"} aria-label="Product information">
      <div className="sb-form-grid">
        <label>Product name *<input required maxLength="240" value={form.name} onChange={e => { const name=e.target.value; setForm(old => ({...old,name,slug:slugify(name)})); }} /></label>
        <label>Slug (automatic)<input required pattern="[a-z0-9]+(-[a-z0-9]+)*" value={form.slug} readOnly aria-readonly="true" /></label>
        <label>Brand<input maxLength="160" value={form.brand || ""} onChange={e => change("brand", e.target.value)} /></label>
        <label>Category<select value={form.category_id} onChange={e => change("category_id", e.target.value)}><option value="">No category</option>{categories.map(c => <option key={c.id} value={c.id}>{c.parent_id ? "↳ " : ""}{c.name}</option>)}</select></label>
        <label>Selling price (₹) *<input required type="number" min="0" step="0.01" value={form.selling_price} onChange={e => change("selling_price", e.target.value)} /></label>
        <label>MRP (₹) *<input required type="number" min="0" step="0.01" value={form.mrp} onChange={e => change("mrp", e.target.value)} /></label>
        <label>Tax code<input maxLength="32" value={form.tax_code || ""} onChange={e => change("tax_code", e.target.value)} /></label>
        <label>Tax rate (%)<input type="number" min="0" max="100" step="0.01" value={form.tax_rate ?? ""} onChange={e => change("tax_rate", e.target.value)} /></label>
        <label className="sb-span-all">Product description<textarea rows="4" value={form.description || ""} onChange={e => change("description", e.target.value)} placeholder="Features, material, fit, usage and care instructions" /></label>
      </div>
      <button type="button" className="sb-primary" onClick={() => { if (!form.name.trim() || !form.slug.trim() || form.selling_price === "" || form.mrp === "" || Number(form.selling_price) < 0 || Number(form.mrp) < Number(form.selling_price)) { setError("Complete product name, selling price and valid MRP before continuing."); return; } setError(""); setActiveTab("attributes"); }}>Continue to Attributes &amp; Variants</button>
    </section>
    <section hidden={activeTab !== "attributes"} aria-label="Attributes and variants">
      {product?.id ? <p className="sb-muted">Existing variants are preserved while editing product information. Manage individual variants in the Variants section below the catalogue.</p> : <>
        <p className="sb-muted">Choose values from the central Attributes module. Each unique combination creates a variant with the default prices above.</p>
        <section className="sb-product-attributes">
          <h3>Attributes and variants</h3>
          {definitions.map(def => <div className="sb-attribute-picker" key={def.id}>
            <strong>{def.name}</strong><small className="sb-muted">{def.value_type}{def.is_variant_attribute ? " · Variant attribute" : ""}{def.is_required ? " · Required" : ""}</small>
            {OPTION_TYPES.includes(def.value_type) ? <div className="sb-option-chips">{(def.options || []).map(value => <label className="sb-option-chip" key={String(value)}><input type="checkbox" checked={(selected[def.code] || []).includes(value)} onChange={() => toggleValue(def, value)} />{String(value)}</label>)}</div> :
              <input value={(selected[def.code] || [])[0] || ""} placeholder={"Enter " + def.name.toLowerCase()} onChange={e => setSelected(old => ({ ...old, [def.code]: e.target.value ? [e.target.value] : [] }))} />}
            {OPTION_TYPES.includes(def.value_type) && <div className="sb-add-option"><input aria-label={"New " + def.name + " option"} value={newOptions[def.code] || ""} placeholder={"Add new " + def.name.toLowerCase() + " option"} onChange={e => setNewOptions(old => ({ ...old, [def.code]: e.target.value }))} /><button type="button" className="sb-secondary" disabled={busy || !(newOptions[def.code] || "").trim()} onClick={() => addOption(def).catch(e => setError(e.message || "Unable to add option."))}>Add value</button></div>}
          </div>)}
          {!definitions.length && <p className="sb-empty">Create an attribute in the Attributes tab first, or continue with a product that has no variants.</p>}
          <p className="sb-muted">This product will create {variantCombinations.length} variant(s).</p>
        </section>
      </>}
      <div className="sb-product-actions"><button className="sb-primary" disabled={busy} type="submit">{busy ? "Saving product and variants…" : product ? "Save product changes" : "Save product and variants"}</button><button className="sb-secondary" type="button" disabled={busy} onClick={() => setActiveTab("general")}>Back to Product Information</button></div>
    </section>
  </form>;
}
