import { useEffect, useMemo, useState } from "react";
import { apiRequest } from "../../services/api.js";

const TABS = [
  ["information", "Product Information"],
  ["variants", "Attributes & Variants"],
  ["price", "Price & Tax"],
  ["availability", "Availability"],
  ["delivery", "Delivery"],
  ["images", "Images"],
  ["details", "Details"],
];
const OPTION_TYPES = ["select", "multi_select", "colour", "size"];
const emptyForm = {
  name: "", slug: "", brand: "", category_id: "", description: "",
  tax_code: "", tax_rate: "", mrp: "", selling_price: "", cost_price: "",
  status: "active",
};
const slugify = value => value.toLowerCase().trim().replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "");

function combinations(definitions, selected) {
  const active = definitions.filter(def => def.is_variant_attribute && (selected[def.code] || []).length);
  if (!active.length) return [{}];
  return active.reduce((all, def) => {
    const values = selected[def.code] || [];
    return all.flatMap(item => values.map(value => ({ ...item, [def.code]: value })));
  }, [{}]);
}

export default function ProductCreateForm({ categories, onSaved, product = null }) {
  const [form, setForm] = useState(() => product ? {
    ...emptyForm, ...product,
    category_id: product.category_id == null ? "" : String(product.category_id),
    mrp: product.max_mrp == null ? "" : String(product.max_mrp),
    selling_price: product.min_selling_price == null ? "" : String(product.min_selling_price),
    tax_rate: product.tax_rate == null ? "" : String(product.tax_rate),
  } : emptyForm);
  const [tab, setTab] = useState("information");
  const [settingsLoading, setSettingsLoading] = useState(false);
  useEffect(() => {
    if (!product) { setForm(emptyForm); setSettingsLoading(false); return; }
    setSettingsLoading(true);
    setForm({
      ...emptyForm, ...product,
      category_id: product.category_id == null ? "" : String(product.category_id),
      mrp: product.max_mrp == null ? "" : String(product.max_mrp),
      selling_price: product.min_selling_price == null ? "" : String(product.min_selling_price),
      tax_rate: product.tax_rate == null ? "" : String(product.tax_rate),
    });
    setTab("information");
    setPosEnabled(product.pos_enabled !== false);
    setWebsiteEnabled(product.website_enabled !== false);
    setStandardDelivery(product.standard_delivery_enabled !== false);
    setExpressDelivery(product.express_delivery_enabled === true);
    Promise.all([
      apiRequest("/catalogue/products/" + product.id + "/availability"),
      apiRequest("/catalogue/products/" + product.id + "/attributes"),
      apiRequest("/catalogue/products/" + product.id + "/variants"),
    ]).then(([result, attrResult, variantResult]) => {
      const selectedValues = {};
      (attrResult.items || []).forEach(item => {
        if (!item.is_variant_attribute && item.value !== undefined && item.value !== null) {
          selectedValues[item.code] = Array.isArray(item.value) ? item.value : [item.value];
        }
      });
      (variantResult.items || []).filter(item => item.is_active).forEach(item => {
        Object.entries(item.attributes || {}).forEach(([code, value]) => {
          const values = Array.isArray(value) ? value : [value];
          selectedValues[code] = [...new Map([...(selectedValues[code] || []), ...values].map(v => [String(v), v])).values()];
        });
      });
      setSelected(selectedValues);
      const grouped = { region: [], state: [], warehouse: [], pincode: [] };
      (result.restrictions || []).forEach(item => { if (grouped[item.type]) grouped[item.type].push(item.value); });
      setRestrictionValues(Object.fromEntries(Object.entries(grouped).map(([key, values]) => [key, values.join(", ")])));
    }).catch(e => setError(e.message || "Unable to load product settings.")).finally(() => setSettingsLoading(false));
  }, [product?.id]);
  const [definitions, setDefinitions] = useState([]);
  const [selected, setSelected] = useState({});
  const [newOptions, setNewOptions] = useState({});
  const [imageUrl, setImageUrl] = useState("");
  const [imageAlt, setImageAlt] = useState("");
  const [posEnabled, setPosEnabled] = useState(true);
  const [websiteEnabled, setWebsiteEnabled] = useState(true);
  const [standardDelivery, setStandardDelivery] = useState(true);
  const [expressDelivery, setExpressDelivery] = useState(false);
  const [restrictionValues, setRestrictionValues] = useState({ region: "", state: "", warehouse: "", pincode: "" });
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const variantCombinations = useMemo(() => combinations(definitions, selected), [definitions, selected]);
  const change = (key, value) => setForm(old => ({ ...old, [key]: value }));

  async function loadDefinitions() {
    const result = await apiRequest("/catalogue/attributes");
    setDefinitions(result.items || []);
  }
  useEffect(() => { loadDefinitions().catch(e => setError(e.message || "Unable to load attributes.")); }, []);

  function toggleValue(def, value) {
    setSelected(old => {
      const current = old[def.code] || [];
      return { ...old, [def.code]: current.some(item => String(item) === String(value))
        ? current.filter(item => String(item) !== String(value))
        : [...current, value] };
    });
  }

  async function addOption(def) {
    const value = (newOptions[def.code] || "").trim();
    if (!value) return;
    await apiRequest("/catalogue/attributes/" + def.id + "/options", {
      method: "PUT", body: JSON.stringify({ options: [value] }),
    });
    await loadDefinitions();
    setSelected(old => ({ ...old, [def.code]: [...(old[def.code] || []), value] }));
    setNewOptions(old => ({ ...old, [def.code]: "" }));
    setNotice("Added option to the existing " + def.name + " attribute.");
  }

  async function submit(event) {
    event.preventDefault();
    setError(""); setNotice("");
    const mrp = Number(form.mrp);
    const sellingPrice = Number(form.selling_price);
    const costPrice = form.cost_price === "" ? null : Number(form.cost_price);
    if (!form.name.trim()) { setTab("information"); setError("Enter a product name."); return; }
    if (!Number.isFinite(mrp) || !Number.isFinite(sellingPrice) || mrp < 0 || sellingPrice < 0 || mrp < sellingPrice) {
      setTab("price"); setError("Enter valid prices. MRP must be equal to or higher than selling price."); return;
    }
    if (variantCombinations.length > 500) { setTab("variants"); setError("This selection creates more than 500 variants. Reduce the selected values."); return; }
    setBusy(true);
    const isEditing = Boolean(product?.id);
    let savedProduct = null;
    try {
      const productPayload = {
        name: form.name.trim(), slug: form.slug || slugify(form.name), brand: form.brand || null,
        category_id: form.category_id ? Number(form.category_id) : null,
        description: form.description || null, tax_code: form.tax_code || null,
        tax_rate: form.tax_rate === "" ? null : Number(form.tax_rate), status: form.status,
        pos_enabled: posEnabled, website_enabled: websiteEnabled,
        standard_delivery_enabled: standardDelivery, express_delivery_enabled: expressDelivery,
      };
      savedProduct = await apiRequest(isEditing ? "/catalogue/products/" + product.id : "/catalogue/products", {
        method: isEditing ? "PUT" : "POST",
        body: JSON.stringify(productPayload),
      });
      const restrictions = Object.entries(restrictionValues).flatMap(([type, raw]) => raw.split(",").map(value => value.trim()).filter(Boolean).map(value => ({ type, value })));
      await apiRequest("/catalogue/products/" + savedProduct.id + "/availability", {
        method: "PUT",
        body: JSON.stringify({
          pos_enabled: posEnabled, website_enabled: websiteEnabled,
          standard_delivery_enabled: standardDelivery, express_delivery_enabled: expressDelivery,
          restrictions,
        }),
      });
      const baseAttributes = definitions.filter(def => !def.is_variant_attribute && (selected[def.code] || []).length);
      for (const def of baseAttributes) {
        const values = selected[def.code] || [];
        const value = def.value_type === "multi_select" ? values : values[0];
        if (value !== undefined) await apiRequest("/catalogue/products/" + savedProduct.id + "/attributes/" + def.id, {
          method: "PUT", body: JSON.stringify({ value }),
        });
      }
      const existingResult = isEditing ? await apiRequest("/catalogue/products/" + savedProduct.id + "/variants") : { items: [] };
      const existingByCombination = new Map((existingResult.items || []).filter(item => item.is_active).map(item => [JSON.stringify(Object.fromEntries(Object.entries(item.attributes || {}).sort(([a],[b]) => a.localeCompare(b)))), item]));
      let variantsCreated = 0;
      for (const attrs of variantCombinations) {
        const key = JSON.stringify(Object.fromEntries(Object.entries(attrs).sort(([a],[b]) => a.localeCompare(b))));
        if (existingByCombination.has(key)) continue;
        await apiRequest("/catalogue/products/" + savedProduct.id + "/variants", {
          method: "POST",
          body: JSON.stringify({ attributes: attrs, selling_price: sellingPrice, mrp, cost_price: costPrice }),
        });
        variantsCreated += 1;
      }
      if (imageUrl.trim()) {
        const currentImages = await apiRequest("/catalogue/products/" + savedProduct.id + "/images");
        if (!(currentImages.items || []).some(item => item.image_url === imageUrl.trim() && item.variant_id == null)) {
          await apiRequest("/catalogue/products/" + savedProduct.id + "/images", {
            method: "POST",
            body: JSON.stringify({ image_url: imageUrl.trim(), alt_text: imageAlt || null, variant_id: null, sort_order: 0 }),
          });
        }
      }
      const notes = [];
      if (variantsCreated) notes.push(variantsCreated + " new variant(s) created");
      setNotice((isEditing ? "Product updated successfully" : "Product saved successfully") + (notes.length ? ". " + notes.join("; ") + "." : "."));
      if (!isEditing) { setForm(emptyForm); setSelected({}); setImageUrl(""); setImageAlt(""); setTab("information"); }
      await onSaved?.(savedProduct);
    } catch (e) {
      setError((e.message || "Unable to save product.") + (savedProduct ? " The product record was saved; review its variants/images before retrying to avoid duplicates." : ""));
    } finally { setBusy(false); }
  }

  return <form className="sb-form sb-product-wizard" onSubmit={submit}>
    <div className="sb-wizard-heading"><div><h2>{product?.id ? "Edit product" : "Add product"}</h2><p className="sb-muted">Complete the product details in the tabs below. Your selections stay in place as you move between tabs.</p></div></div>
    {error && <p role="alert" className="sb-alert">{error}</p>}
    {notice && <p role="status" className="sb-success">{notice}</p>}
    <nav className="sb-wizard-tabs" aria-label="Product creation steps">
      {TABS.map(([key, label], index) => <button key={key} type="button" className={tab === key ? "is-active" : ""} aria-current={tab === key ? "step" : undefined} onClick={() => setTab(key)}><span>{index + 1}</span>{label}</button>)}
    </nav>

    {tab === "information" && <section className="sb-wizard-panel">
      <h3>Product Information</h3>
      <div className="sb-form-grid">
        <label>Product name *<input required maxLength="240" value={form.name} onChange={e => setForm(old => ({ ...old, name: e.target.value, slug: slugify(e.target.value) }))}/></label>
        <label>Slug (automatic)<input required value={form.slug} readOnly aria-readonly="true"/></label>
        <label>Brand<input maxLength="160" value={form.brand} onChange={e => change("brand", e.target.value)}/></label>
        <label>Category<select value={form.category_id} onChange={e => change("category_id", e.target.value)}><option value="">Choose category</option>{categories.map(c => <option key={c.id} value={c.id}>{c.parent_id ? "↳ " : ""}{c.name}</option>)}</select></label>
        <label className="sb-span-all">Description<textarea rows="3" value={form.description} onChange={e => change("description", e.target.value)} placeholder="Short product description"/></label>
      </div>
    </section>}

    {tab === "variants" && <section className="sb-wizard-panel">
      <h3>Attributes & Variants</h3>
      <p className="sb-muted">Select values from the central Attributes library. Only attributes marked for variant generation create SKU combinations.</p>
      {definitions.length ? definitions.map(def => <div className="sb-attribute-picker" key={def.id}>
        <div className="sb-attribute-heading"><strong>{def.name}</strong><span className="sb-muted">{def.value_type} · {def.is_variant_attribute ? "Variant attribute" : "Descriptive attribute"}</span></div>
        {OPTION_TYPES.includes(def.value_type) ? (def.display_style === "dropdown"
          ? <select multiple className="sb-attribute-dropdown" aria-label={def.name + " values"} value={(selected[def.code] || []).map(String)} onChange={e => { const values = Array.from(e.target.selectedOptions, option => (def.options || []).find(value => String(value) === option.value)); setSelected(old => ({...old,[def.code]:values})); }}>{(def.options || []).map(value => <option key={String(value)} value={String(value)}>{String(value)}</option>)}</select>
          : <div className="sb-option-chips">{(def.options || []).map(value => <label className={"sb-option-chip sb-option-style-" + (def.display_style || "text")} key={String(value)}>{def.display_style === "colour_swatch" && <span className="sb-colour-swatch" style={{backgroundColor:String(value)}} aria-hidden="true"/>}<input type="checkbox" checked={(selected[def.code] || []).some(item => String(item) === String(value))} onChange={() => toggleValue(def, value)}/>{String(value)}</label>)}</div>)
          : <input value={(selected[def.code] || [])[0] || ""} placeholder={"Enter " + def.name.toLowerCase()} onChange={e => setSelected(old => ({ ...old, [def.code]: e.target.value ? [e.target.value] : [] }))}/>} 
        {OPTION_TYPES.includes(def.value_type) && <div className="sb-add-option"><input aria-label={"New " + def.name + " option"} value={newOptions[def.code] || ""} placeholder={"Add option to " + def.name} onChange={e => setNewOptions(old => ({ ...old, [def.code]: e.target.value }))}/><button type="button" className="sb-secondary" disabled={busy || !(newOptions[def.code] || "").trim()} onClick={() => addOption(def).catch(e => setError(e.message || "Unable to add option."))}>Add option</button></div>}
      </div>) : <p className="sb-empty">No active attributes yet. Create them in the Attributes section first.</p>}
      <p className="sb-variant-count">{variantCombinations.length} variant combination(s) will be created.</p>
    </section>}

    {tab === "price" && <section className="sb-wizard-panel"><h3>Price & Tax</h3>
      <div className="sb-form-grid">
        <label>MRP (₹) *<input required type="number" min="0" step="0.01" value={form.mrp} onChange={e => change("mrp", e.target.value)}/></label>
        <label>Selling price (₹) *<input required type="number" min="0" step="0.01" value={form.selling_price} onChange={e => change("selling_price", e.target.value)}/></label>
        <label>Cost price (₹)<input type="number" min="0" step="0.01" value={form.cost_price} onChange={e => change("cost_price", e.target.value)}/></label>
        <label>Tax code<input maxLength="32" value={form.tax_code} onChange={e => change("tax_code", e.target.value)}/></label>
        <label>Tax rate (%)<input type="number" min="0" max="100" step="0.01" value={form.tax_rate} onChange={e => change("tax_rate", e.target.value)} placeholder="Enter configured rate"/></label>
      </div>
      <p className="sb-muted">The current backend exposes tax code and tax rate fields, but the repository has no tax-rate lookup endpoint. The rate remains manually entered until the existing Tax Module exposes one.</p>
    </section>}

    {tab === "availability" && <section className="sb-wizard-panel"><h3>Availability</h3>
      <p className="sb-muted">Choose the sales channels for this product.</p>
      <label className="sb-check"><input type="checkbox" checked={posEnabled} onChange={e => setPosEnabled(e.target.checked)}/> Available in POS</label>
      <label className="sb-check"><input type="checkbox" checked={websiteEnabled} onChange={e => setWebsiteEnabled(e.target.checked)}/> Available on Website</label>
      <div className="sb-form-grid">
        <label>Regions (comma-separated)<input value={restrictionValues.region} onChange={e => setRestrictionValues(old => ({...old, region:e.target.value}))} placeholder="e.g. South, East"/></label>
        <label>States (comma-separated)<input value={restrictionValues.state} onChange={e => setRestrictionValues(old => ({...old, state:e.target.value}))} placeholder="e.g. Karnataka, Jharkhand"/></label>
        <label>Warehouse IDs (comma-separated)<input value={restrictionValues.warehouse} onChange={e => setRestrictionValues(old => ({...old, warehouse:e.target.value}))} placeholder="Active warehouse IDs"/></label>
        <label>Pincodes (comma-separated)<input value={restrictionValues.pincode} onChange={e => setRestrictionValues(old => ({...old, pincode:e.target.value}))} placeholder="6-digit pincodes"/></label>
      </div>
      <p className="sb-muted">Leave all restriction fields empty to make the product available across the supported service area. Warehouse restrictions use active warehouse IDs.</p>
    </section>}

    {tab === "delivery" && <section className="sb-wizard-panel"><h3>Delivery</h3>
      <label className="sb-check"><input type="checkbox" checked={standardDelivery} onChange={e => setStandardDelivery(e.target.checked)}/> Standard delivery</label>
      <label className="sb-check"><input type="checkbox" checked={expressDelivery} onChange={e => setExpressDelivery(e.target.checked)}/> Express delivery</label>
      <p className="sb-muted">Delivery selections are saved with the product configuration.</p>
    </section>}

    {tab === "images" && <section className="sb-wizard-panel"><h3>Images</h3>
      <p className="sb-muted">The existing API stores image URLs and metadata; it does not currently provide file upload/storage.</p>
      <div className="sb-form-grid"><label className="sb-span-all">Image URL<input type="url" maxLength="2048" value={imageUrl} onChange={e => setImageUrl(e.target.value)} placeholder="https://…"/></label><label className="sb-span-all">Alt text<input maxLength="300" value={imageAlt} onChange={e => setImageAlt(e.target.value)}/></label></div>
    </section>}

    {tab === "details" && <section className="sb-wizard-panel"><h3>Details & Review</h3>
      <div className="sb-review-list"><div><span>Product</span><strong>{form.name || "Not entered"}</strong></div><div><span>Category</span><strong>{categories.find(c => String(c.id) === String(form.category_id))?.name || "Uncategorised"}</strong></div><div><span>MRP / Selling price</span><strong>{form.mrp === "" ? "—" : "₹" + form.mrp} / {form.selling_price === "" ? "—" : "₹" + form.selling_price}</strong></div><div><span>Variant combinations</span><strong>{variantCombinations.length}</strong></div><div><span>Channels</span><strong>{[posEnabled && "POS", websiteEnabled && "Website"].filter(Boolean).join(", ") || "None selected"}</strong></div><div><span>Delivery</span><strong>{[standardDelivery && "Standard", expressDelivery && "Express"].filter(Boolean).join(", ") || "None selected"}</strong></div></div>
      <label className="sb-check"><input type="checkbox" checked={form.status === "draft"} onChange={e => change("status", e.target.checked ? "draft" : "active")}/> Save as draft (leave unchecked to activate)</label>
    </section>}

    <div className="sb-wizard-footer">
      <button type="button" className="sb-secondary" disabled={tab === TABS[0][0] || busy} onClick={() => setTab(TABS[Math.max(0, TABS.findIndex(item => item[0] === tab) - 1)][0])}>Previous</button>
      <span className="sb-muted">Step {TABS.findIndex(item => item[0] === tab) + 1} of {TABS.length}</span>
      {tab !== "details" ? <button type="button" className="sb-primary" onClick={() => setTab(TABS[Math.min(TABS.length - 1, TABS.findIndex(item => item[0] === tab) + 1)][0])}>Next</button> : <button className="sb-primary" disabled={busy || settingsLoading} type="submit">{settingsLoading ? "Loading existing settings…" : busy ? "Saving product…" : product?.id ? "Save changes" : form.status === "draft" ? "Save draft" : "Save product"}</button>}
    </div>
  </form>;
}
