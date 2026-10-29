import { useEffect, useState } from "react";
import { apiRequest } from "../../services/api.js";

const initialAttribute = { name: "", code: "", value_type: "select", is_variant_attribute: true, is_required: true, options: "" };
const initialVariant = { sku: "", barcode: "", attributes: "{}", selling_price: "", mrp: "", cost_price: "" };

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

export default function CatalogueVariantsPanel({ products, categories = [] }) {
  const [definitions, setDefinitions] = useState([]);
  const [productId, setProductId] = useState("");
  const [variants, setVariants] = useState([]);
  const [attribute, setAttribute] = useState(initialAttribute);
  const [variant, setVariant] = useState(initialVariant);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [busy, setBusy] = useState(false);

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
  useEffect(() => { loadVariants(productId); }, [productId]);

  async function createAttribute(event) {
    event.preventDefault(); setBusy(true); setError(""); setNotice("");
    try {
      const optionTypes = ["select", "multi_select", "colour", "size"];
      const payload = { ...attribute, options: optionTypes.includes(attribute.value_type) ? attribute.options.split(",").map(x => x.trim()).filter(Boolean) : [] };
      await apiRequest("/catalogue/attributes", { method: "POST", body: JSON.stringify(payload) });
      setAttribute(initialAttribute); setNotice("Attribute definition saved."); await loadDefinitions();
    } catch (e) { setError(e.message || "Unable to save attribute."); }
    finally { setBusy(false); }
  }

  async function createVariant(event) {
    event.preventDefault(); setBusy(true); setError(""); setNotice("");
    try {
      let attributes;
      try { attributes = JSON.parse(variant.attributes || "{}"); }
      catch { throw new Error("Variant attributes must be valid JSON, for example { \"size\": \"M\" }."); }
      await apiRequest("/catalogue/products/" + productId + "/variants", {
        method: "POST",
        body: JSON.stringify({
          barcode: variant.barcode || null, attributes,
          selling_price: Number(variant.selling_price),
          mrp: variant.mrp === "" ? null : Number(variant.mrp),
          cost_price: variant.cost_price === "" ? null : Number(variant.cost_price),
        }),
      });
      setVariant(initialVariant); setNotice("Variant saved."); await loadVariants(productId);
    } catch (e) { setError(e.message || "Unable to save variant."); }
    finally { setBusy(false); }
  }

  return <section className="sb-data-card">
    <h2>Attributes & variants</h2>
    {error && <p className="sb-alert" role="alert">{error}</p>}
    {notice && <p className="sb-success" role="status">{notice}</p>}
    <form className="sb-form sb-form-inner" onSubmit={createAttribute}>
      <h3>Create attribute definition</h3>
      <div className="sb-form-grid">
        <label>Name<input required value={attribute.name} onChange={e=>setAttribute(v=>({...v,name:e.target.value}))}/></label>
        <label>Code<input required pattern="[a-z][a-z0-9_]*" value={attribute.code} onChange={e=>setAttribute(v=>({...v,code:e.target.value}))}/></label>
        <label>Type<select value={attribute.value_type} onChange={e=>setAttribute(v=>({...v,value_type:e.target.value,options:""}))}>{["text","number","boolean","date","select","multi_select","colour","size"].map(x=><option key={x}>{x}</option>)}</select></label>
        <label>Options (comma-separated)<input value={attribute.options} disabled={!["select","multi_select","colour","size"].includes(attribute.value_type)} placeholder="S, M, L" onChange={e=>setAttribute(v=>({...v,options:e.target.value}))}/></label>
      </div>
      <label className="sb-check"><input type="checkbox" checked={attribute.is_variant_attribute} onChange={e=>setAttribute(v=>({...v,is_variant_attribute:e.target.checked}))}/> Used to define variant combinations</label>
      <label className="sb-check"><input type="checkbox" checked={attribute.is_required} onChange={e=>setAttribute(v=>({...v,is_required:e.target.checked}))}/> Required attribute</label>
      <button className="sb-primary" disabled={busy} type="submit">{busy ? "Saving…" : "Save attribute"}</button>
    </form>
    <p className="sb-muted">Active attributes: {definitions.map(d=>d.code + " (" + d.value_type + ")").join(", ") || "None yet"}</p>
    <div className="sb-form-grid">
      <label>Product for variants<select value={productId} onChange={e=>setProductId(e.target.value)}><option value="">Choose product</option>{products.map(p=><option key={p.id} value={p.id}>{p.name} · #{p.id}</option>)}</select></label>
    </div>
    <form className="sb-form sb-form-inner" onSubmit={createVariant}>
      <h3>Create SKU variant</h3>
      <div className="sb-form-grid">
        <label className="sb-span-all">SKU (automatic)<input readOnly aria-readonly="true" value={skuPreview(products.find(p => String(p.id) === String(productId)), categories, (() => { try { return JSON.parse(variant.attributes || "{}"); } catch { return {}; } })(), variants.length + 1)} /><small className="sb-muted">Generated from category, department, brand, product ID and variant attributes. The server checks uniqueness when saving.</small></label>
        <label>Barcode<input value={variant.barcode} onChange={e=>setVariant(v=>({...v,barcode:e.target.value}))}/></label>
        <label>Selling price (₹)<input required type="number" min="0" step="0.01" value={variant.selling_price} onChange={e=>setVariant(v=>({...v,selling_price:e.target.value}))}/></label>
        <label>MRP (₹)<input type="number" min="0" step="0.01" value={variant.mrp} onChange={e=>setVariant(v=>({...v,mrp:e.target.value}))}/></label>
        <label>Cost price (₹)<input type="number" min="0" step="0.01" value={variant.cost_price} onChange={e=>setVariant(v=>({...v,cost_price:e.target.value}))}/></label>
        <label className="sb-span-all">Attribute values (JSON)<input value={variant.attributes} onChange={e=>setVariant(v=>({...v,attributes:e.target.value}))} placeholder='{"size":"M","colour":"Blue"}'/></label>
      </div>
      <button className="sb-primary" disabled={busy || !productId} type="submit">{busy ? "Saving…" : "Save variant"}</button>
    </form>
    <h3>Variants for selected product</h3>
    {variants.length ? <ul>{variants.map(v=><li key={v.id}><strong>{v.sku}</strong> — ₹{v.selling_price} <small>{JSON.stringify(v.attributes)}</small></li>)}</ul> : <p className="sb-empty">Choose a product to load its variants.</p>}
  </section>;
}
