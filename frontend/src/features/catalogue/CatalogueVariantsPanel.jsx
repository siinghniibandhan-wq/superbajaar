import { useEffect, useState } from "react";
import { apiRequest } from "../../services/api.js";
import CatalogueModal from "./CatalogueModal.jsx";

const initialAttribute = { name: "", code: "", value_type: "text", is_variant_attribute: true, is_required: true, options: "" };
const initialVariant = { sku: "", barcode: "", attributes: "{}", selling_price: "", mrp: "", cost_price: "" };
const OPTION_TYPES = ["select", "multi_select", "colour", "size"];
function makeCombinations(items) {
  return items.reduce((rows, item) => rows.flatMap(row => item.values.map(value => [...row, [item.code, value]])), [[]]).map(entries => Object.fromEntries(entries));
}

function skuToken(value, limit = 8) {
  return String(value || "").toUpperCase().replace(/[^A-Z0-9]+/g, "-").replace(/^-|-$/g, "").slice(0, limit).replace(/-$/g, "") || "GEN";
}

function categoryCode(name) {
  const slug = String(name || "").toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "");
  const codes = { fashion: "FS", clothing: "FS", apparel: "FS", footwear: "FS", grocery: "GR", groceries: "GR", electronics: "EL", "personal-care": "PC", beauty: "PC", "pet-care": "PT", "fresh-products": "FR", fresh: "FR", "home-kitchen": "HK" };
  return codes[slug] || slug.split("-").filter(Boolean).map(part => part[0]).join("").slice(0, 3).toUpperCase() || "OT";
}

function skuPreview(product, categories, attributes, version) {
  if (!product) return "Choose a product to generate its SKU";
  const category = categories.find(item => Number(item.id) === Number(product.category_id));
  const parentCategory = category?.parent_id ? categories.find(item => Number(item.id) === Number(category.parent_id)) : null;
  const normalized = Object.fromEntries(Object.entries(attributes || {}).map(([key, value]) => [key.toLowerCase(), value]));
  const department = String(normalized.gender || normalized.department || normalized.audience || category?.name || "").toLowerCase();
  const deptCode = ["m", "men", "mens", "male", "man"].includes(department) ? "M" : ["w", "women", "womens", "female", "woman"].includes(department) ? "W" : ["k", "kids", "kid", "children", "child"].includes(department) ? "K" : "U";
  const productName = String(product.name || "").toUpperCase();
  const productCode = productName.includes("T-SHIRT") || productName.includes("TSHIRT") || productName.includes("TEE") ? "TSH" : productName.includes("RICE") ? "RIC" : productName.includes("JEAN") || productName.includes("DENIM") ? "JNS" : productName.includes("SNEAKER") || productName.includes("SHOE") || productName.includes("FOOTWEAR") ? "SH" : productName.includes("DRESS") ? "DRS" : productName.includes("PHONE") ? "PHN" : productName.includes("LAPTOP") || productName.includes("NOTEBOOK") ? "LTP" : productName.includes("DETERGENT") ? "DTR" : productName.includes("MILK") ? "MLK" : productName.replace(/-/g, " ").split(/\s+/).filter(Boolean).slice(0, 4).map(word => word[0]).join("") || "PROD";
  const values = Object.keys(attributes || {}).sort().flatMap(key => Array.isArray(attributes[key]) ? attributes[key] : [attributes[key]]).filter(value => ["string", "number"].includes(typeof value) && String(value).trim()).slice(0, 4).map(value => skuToken(value));
  return ["SB", categoryCode(parentCategory?.name || category?.name), deptCode, skuToken(product.brand), skuToken(productCode, 6), String(product.id).padStart(5, "0"), ...values, "V" + String(version).padStart(2, "0")].join("-");
}

export default function CatalogueVariantsPanel({ products, categories = [], initialProductId = "" }) {
  const [definitions, setDefinitions] = useState([]);
  const [productId, setProductId] = useState(initialProductId);
  const [variants, setVariants] = useState([]);
  const [attribute, setAttribute] = useState(initialAttribute);
  const [variant, setVariant] = useState(initialVariant);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [busy, setBusy] = useState(false);
  const [editingVariant, setEditingVariant] = useState(null);
  const [viewingVariant, setViewingVariant] = useState(null);
  const [showAttributeForm, setShowAttributeForm] = useState(false);
  const [selectedValues, setSelectedValues] = useState({});
  const [defaultPrice, setDefaultPrice] = useState("");
  const [defaultMrp, setDefaultMrp] = useState("");
  const [defaultCost, setDefaultCost] = useState("");
  const [generatedRows, setGeneratedRows] = useState([]);

  function closeAttributeForm() {
    if (busy) return;
    if (JSON.stringify(attribute) !== JSON.stringify(initialAttribute) && !window.confirm("Discard unsaved attribute changes?")) return;
    setAttribute(initialAttribute);
    setError("");
    setShowAttributeForm(false);
  }

  async function loadDefinitions() {
    try { const result = await apiRequest("/catalogue/attributes"); setDefinitions(result.items || []); }
    catch (e) { setError(e.message || "Unable to load attributes."); }
  }
  async function loadVariants(id = productId) {
    if (!id) { setVariants([]); return; }
    try { const result = await apiRequest("/catalogue/products/" + id + "/variants"); setVariants(result.items || []); }
    catch (e) { setError(e.message || "Unable to load variants."); }
  }
  useEffect(() => { loadDefinitions(); }, []);
  useEffect(() => { if (initialProductId && String(initialProductId) !== String(productId)) setProductId(String(initialProductId)); }, [initialProductId]);
  useEffect(() => { loadVariants(productId); setGeneratedRows([]); }, [productId]);

  const selectableAttributes = definitions.filter(def => def.is_variant_attribute && OPTION_TYPES.includes(def.value_type) && (def.options || []).length);
  const chosenAttributes = selectableAttributes.filter(def => (selectedValues[def.code] || []).length);
  const combinationPreview = makeCombinations(chosenAttributes.map(def => ({ code: def.code, values: selectedValues[def.code] || [] })));
  function toggleAttributeValue(def, value) {
    setSelectedValues(old => { const current = old[def.code] || []; return { ...old, [def.code]: current.includes(value) ? current.filter(v => v !== value) : [...current, value] }; });
  }
  function prepareGeneratedRows() {
    if (!productId) { setError("Choose a product first."); return; }
    if (!chosenAttributes.length) { setError("Choose at least one attribute and value."); return; }
    const existing = new Set(variants.filter(v => v.is_active).map(v => JSON.stringify(Object.fromEntries(Object.entries(v.attributes || {}).sort(([a],[b]) => a.localeCompare(b)))));
    const fresh = combinationPreview.filter(attrs => !existing.has(JSON.stringify(Object.fromEntries(Object.entries(attrs).sort(([a],[b]) => a.localeCompare(b)))));
    if (!fresh.length) { setError("Those attribute combinations already exist for this product."); return; }
    setGeneratedRows(fresh.map(attributes => ({ attributes, selling_price: defaultPrice, mrp: defaultMrp, cost_price: defaultCost, barcode: "" })));
    setError(""); setNotice(fresh.length + " variant combination(s) ready to review.");
  }
  async function saveGeneratedRows() {
    setBusy(true); setError(""); setNotice("");
    try {
      for (const row of generatedRows) {
        if (row.selling_price === "" || !Number.isFinite(Number(row.selling_price))) throw new Error("Enter a selling price for every variant.");
        await apiRequest("/catalogue/products/" + productId + "/variants", { method: "POST", body: JSON.stringify({ attributes: row.attributes, barcode: row.barcode || null, selling_price: Number(row.selling_price), mrp: row.mrp === "" ? null : Number(row.mrp), cost_price: row.cost_price === "" ? null : Number(row.cost_price) }) });
      }
      setGeneratedRows([]); setNotice("Variants saved successfully."); await loadVariants(productId);
    } catch (e) { setError((e.message || "Unable to save variants.") + " Check the variant list before retrying to avoid duplicates."); await loadVariants(productId); }
    finally { setBusy(false); }
  }

  async function createAttribute(event) {
    event.preventDefault(); setBusy(true); setError(""); setNotice("");
    try {
      const optionTypes = ["select", "multi_select", "colour", "size"];
      const options = optionTypes.includes(attribute.value_type) ? attribute.options.split(",").map(x => x.trim()).filter(Boolean) : [];
      if (optionTypes.includes(attribute.value_type) && !options.length) {
        throw new Error("Enter at least one option for this attribute type.");
      }
      const payload = { ...attribute, name: attribute.name.trim(), options };
      await apiRequest("/catalogue/attributes", { method: "POST", body: JSON.stringify(payload) });
      setAttribute(initialAttribute); setShowAttributeForm(false); setNotice("Attribute definition saved."); await loadDefinitions();
    } catch (e) { setError(e.message || "Unable to save attribute."); }
    finally { setBusy(false); }
  }

  async function createVariant(event) {
    event.preventDefault(); setBusy(true); setError(""); setNotice("");
    try {
      let attributes;
      try { attributes = JSON.parse(variant.attributes || "{}"); }
      catch { throw new Error("Variant attributes must be valid JSON, for example { \"size\": \"M\" }."); }
      await apiRequest(editingVariant ? "/catalogue/variants/" + editingVariant.id : "/catalogue/products/" + productId + "/variants", {
        method: editingVariant ? "PUT" : "POST",
        body: JSON.stringify({
          barcode: variant.barcode || null, attributes,
          selling_price: Number(variant.selling_price),
          mrp: variant.mrp === "" ? null : Number(variant.mrp),
          cost_price: variant.cost_price === "" ? null : Number(variant.cost_price),
        }),
      });
      setVariant(initialVariant); setEditingVariant(null); setNotice(editingVariant ? "Variant updated." : "Variant saved."); await loadVariants(productId);
    } catch (e) { setError(e.message || "Unable to save variant."); }
    finally { setBusy(false); }
  }

  return <section className="sb-data-card">
    <div className="sb-data-heading">
      <h2>Attributes & variants</h2>
      <button type="button" className="sb-primary" onClick={() => { setError(""); setShowAttributeForm(true); }}>+ Add attribute</button>
    </div>
    {error && <p className="sb-alert" role="alert">{error}</p>}
    {notice && <p className="sb-success" role="status">{notice}</p>}
    <CatalogueModal
      open={showAttributeForm}
      title="Create attribute definition"
      onRequestClose={closeAttributeForm}
      footer={<>
        <button type="submit" form="catalogue-attribute-form" className="sb-primary" disabled={busy}>{busy ? "Saving…" : "Save attribute"}</button>
        <button type="button" className="sb-secondary" disabled={busy} onClick={closeAttributeForm}>Cancel</button>
      </>}
    >
      {showAttributeForm && <>
        {error && <p className="sb-alert" role="alert">{error}</p>}
        <form id="catalogue-attribute-form" className="sb-form sb-modal-form" onSubmit={createAttribute}>
        <div className="sb-form-grid">
          <label>Name<input required value={attribute.name} onChange={e=>setAttribute(v=>({...v,name:e.target.value,code:e.target.value.toLowerCase().trim().replace(/[^a-z0-9]+/g,"_").replace(/^_+|_+$/g,"").replace(/^([0-9])/,"attr_$1") || "attribute"}))}/></label>
          <label>Code (automatic)<input required pattern="[a-z][a-z0-9_]*" value={attribute.code} readOnly aria-readonly="true"/><small className="sb-muted">Generated from the attribute name.</small></label>
          <label>Type<select value={attribute.value_type} onChange={e=>setAttribute(v=>({...v,value_type:e.target.value,options:""}))}>{["text","number","boolean","date","select","multi_select","colour","size"].map(x=><option key={x}>{x}</option>)}</select></label>
          <label>Options (comma-separated)<input required={["select","multi_select","colour","size"].includes(attribute.value_type)} value={attribute.options} disabled={!["select","multi_select","colour","size"].includes(attribute.value_type)} placeholder="S, M, L" onChange={e=>setAttribute(v=>({...v,options:e.target.value}))}/></label>
        </div>
        <label className="sb-check"><input type="checkbox" checked={attribute.is_variant_attribute} onChange={e=>setAttribute(v=>({...v,is_variant_attribute:e.target.checked}))}/> Used to define variant combinations</label>
        <label className="sb-check"><input type="checkbox" checked={attribute.is_required} onChange={e=>setAttribute(v=>({...v,is_required:e.target.checked}))}/> Required attribute</label>
        </form>
      </>}
    </CatalogueModal>
    <div className="sb-strip-list" aria-label="Attribute definitions">
      {definitions.length ? definitions.map(definition => <article className="sb-strip-row" key={definition.id}>
        <div className="sb-strip-icon" aria-hidden="true">Aa</div>
        <div className="sb-strip-main"><strong>{definition.name}</strong><small>{definition.code} · {definition.value_type}{definition.options?.length ? " · " + definition.options.join(", ") : ""}</small></div>
        <span className="sb-status-pill">{definition.is_required ? "Required" : "Optional"}</span>
        {definition.is_variant_attribute && <span className="sb-strip-meta">Variant</span>}
      </article>) : <p className="sb-empty">No attributes found. Select Add attribute to create one.</p>}
    </div>
    <div className="sb-form-grid">
      <label>Product for variants<select value={productId} onChange={e=>setProductId(e.target.value)}><option value="">Choose product</option>{products.map(p=><option key={p.id} value={p.id}>{p.name} · #{p.id}</option>)}</select></label>
    </div>
    <section className="sb-form-inner sb-variant-builder" aria-label="Generate variants">
      <h3>Assign attributes and generate variants</h3>
      <p className="sb-muted">Choose a product above, then select the attribute values this product comes in. We will prepare one variant for each combination.</p>
      {!productId && <p className="sb-empty">Choose a product above to assign its attributes.</p>}
      {productId && !selectableAttributes.length && <p className="sb-empty">No option-based variant attributes yet. Add a Colour, Size or Select attribute above first.</p>}
      {productId && selectableAttributes.map(def => <div className="sb-attribute-picker" key={def.id}>
        <strong>{def.name}</strong><small className="sb-muted">{def.code} · select every value this product offers</small>
        <div className="sb-option-chips">{(def.options || []).map(value => <label className="sb-option-chip" key={String(value)}><input type="checkbox" checked={(selectedValues[def.code] || []).includes(value)} onChange={() => toggleAttributeValue(def, value)} />{String(value)}</label>)}</div>
      </div>)}
      <div className="sb-form-grid">
        <label>Default selling price (₹)<input type="number" min="0" step="0.01" value={defaultPrice} onChange={e=>setDefaultPrice(e.target.value)} placeholder="Can be edited per variant"/></label>
        <label>Default MRP (₹)<input type="number" min="0" step="0.01" value={defaultMrp} onChange={e=>setDefaultMrp(e.target.value)} placeholder="Optional"/></label>
        <label>Default cost price (₹)<input type="number" min="0" step="0.01" value={defaultCost} onChange={e=>setDefaultCost(e.target.value)} placeholder="Optional"/></label>
      </div>
      <div className="sb-product-actions"><button type="button" className="sb-primary" disabled={busy || !productId} onClick={prepareGeneratedRows}>Preview combinations</button></div>
      {generatedRows.length > 0 && <>
        <h3>Review variants ({generatedRows.length})</h3>
        {generatedRows.map((row,index)=><div className="sb-variant-review-row" key={JSON.stringify(row.attributes)}>
          <strong>{Object.entries(row.attributes).map(([code,value]) => definitions.find(d=>d.code===code)?.name + ": " + (Array.isArray(value)?value.join(", "):value)).join(" · ")}</strong>
          <div className="sb-form-grid">
            <label>Selling price (₹)<input required type="number" min="0" step="0.01" value={row.selling_price} onChange={e=>setGeneratedRows(old=>old.map((r,i)=>i===index?{...r,selling_price:e.target.value}:r))}/></label>
            <label>MRP (₹)<input type="number" min="0" step="0.01" value={row.mrp} onChange={e=>setGeneratedRows(old=>old.map((r,i)=>i===index?{...r,mrp:e.target.value}:r))}/></label>
            <label>Cost price (₹)<input type="number" min="0" step="0.01" value={row.cost_price} onChange={e=>setGeneratedRows(old=>old.map((r,i)=>i===index?{...r,cost_price:e.target.value}:r))}/></label>
            <label>Barcode (optional)<input value={row.barcode} onChange={e=>setGeneratedRows(old=>old.map((r,i)=>i===index?{...r,barcode:e.target.value}:r))}/></label>
          </div>
        </div>)}
        <div className="sb-product-actions"><button type="button" className="sb-primary" disabled={busy} onClick={saveGeneratedRows}>{busy ? "Saving…" : "Save all variants"}</button><button type="button" className="sb-secondary" disabled={busy} onClick={()=>setGeneratedRows([])}>Cancel preview</button></div>
      </>}
    </section>
    <form className="sb-form sb-form-inner" onSubmit={createVariant}>
      <h3>{editingVariant ? "Edit SKU variant" : "Advanced: create one variant manually"}</h3>
      <div className="sb-form-grid">
        <label className="sb-span-all">SKU (automatic)<input readOnly aria-readonly="true" value={skuPreview(products.find(p => String(p.id) === String(productId)), categories, (() => { try { return JSON.parse(variant.attributes || "{}"); } catch { return {}; } })(), variants.length + 1)} /><small className="sb-muted">Generated from category, department, brand, product ID and variant attributes. The server checks uniqueness when saving.</small></label>
        <label>Barcode<input value={variant.barcode} onChange={e=>setVariant(v=>({...v,barcode:e.target.value}))}/></label>
        <label>Selling price (₹)<input required type="number" min="0" step="0.01" value={variant.selling_price} onChange={e=>setVariant(v=>({...v,selling_price:e.target.value}))}/></label>
        <label>MRP (₹)<input type="number" min="0" step="0.01" value={variant.mrp} onChange={e=>setVariant(v=>({...v,mrp:e.target.value}))}/></label>
        <label>Cost price (₹)<input type="number" min="0" step="0.01" value={variant.cost_price} onChange={e=>setVariant(v=>({...v,cost_price:e.target.value}))}/></label>
        <label className="sb-span-all">Advanced attribute values (JSON)<input value={variant.attributes} onChange={e=>setVariant(v=>({...v,attributes:e.target.value}))} placeholder='{"size":"M","colour":"Blue"}'/></label>
      </div>
      <div className="sb-product-actions"><button className="sb-primary" disabled={busy || !productId} type="submit">{busy ? "Saving…" : editingVariant ? "Save variant changes" : "Save variant"}</button>{editingVariant && <button type="button" className="sb-secondary" disabled={busy} onClick={() => { setEditingVariant(null); setVariant(initialVariant); }}>Cancel edit</button>}</div>
    </form>
    <h3>Variants for selected product</h3>
    {viewingVariant && <section className="sb-form-inner" aria-label="Variant details">
      <h3>View variant — read only</h3>
      <p><strong>SKU:</strong> {viewingVariant.sku}</p>
      <p><strong>Barcode:</strong> {viewingVariant.barcode || "—"}</p>
      <p><strong>Attributes:</strong> {JSON.stringify(viewingVariant.attributes)}</p>
      <p><strong>Selling price:</strong> ₹{viewingVariant.selling_price}</p>
      <p><strong>MRP:</strong> {viewingVariant.mrp == null ? "—" : "₹" + viewingVariant.mrp}</p>
      <p><strong>Cost price:</strong> {viewingVariant.cost_price == null ? "—" : "₹" + viewingVariant.cost_price}</p>
      <button type="button" className="sb-secondary" onClick={() => setViewingVariant(null)}>Close view</button>
    </section>}
    {variants.length ? <div className="sb-strip-list">{variants.map(v=><article className="sb-strip-row" key={v.id}>
      <div className="sb-strip-main"><strong>{v.sku}</strong><small>{JSON.stringify(v.attributes)} · ₹{v.selling_price} · {v.is_active ? "Active" : "Archived"}</small></div>
      <button type="button" className="sb-row-action" onClick={() => setViewingVariant(v)}>View</button>
      {v.is_active && <button type="button" className="sb-row-action" onClick={() => { setEditingVariant(v); setViewingVariant(null); setVariant({sku:v.sku || "", barcode:v.barcode || "", attributes:JSON.stringify(v.attributes || {}, null, 2), selling_price:String(v.selling_price ?? ""), mrp:v.mrp == null ? "" : String(v.mrp), cost_price:v.cost_price == null ? "" : String(v.cost_price)}); }}>Edit</button>}
      {v.is_active && <button type="button" className="sb-row-action" onClick={async () => { if (!window.confirm("Archive variant " + v.sku + "? This will not archive the product or other variants.")) return; setError(""); try { await apiRequest("/catalogue/variants/" + v.id + "/archive", {method:"POST"}); setNotice("Variant archived."); await loadVariants(productId); } catch(e) { setError(e.message || "Unable to archive variant."); } }}>Archive</button>}
    </article>)}</div> : <p className="sb-empty">Choose a product to load its variants.</p>}
  </section>;
}
