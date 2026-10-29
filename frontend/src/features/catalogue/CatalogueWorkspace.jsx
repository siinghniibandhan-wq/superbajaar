import { useEffect, useState } from "react";
import { apiRequest } from "../../services/api.js";
import ProductCreateForm from "./ProductCreateForm.jsx";
import CatalogueVariantsPanel from "./CatalogueVariantsPanel.jsx";
import ProductImagesPanel from "./ProductImagesPanel.jsx";
import "./catalogue.css";

export default function CatalogueWorkspace({ onBack }) {
  const [activeTab, setActiveTab] = useState("catalogue");
  const [categories, setCategories] = useState([]);
  const [products, setProducts] = useState([]);
  const [showProductForm, setShowProductForm] = useState(false);
  const [editingProduct, setEditingProduct] = useState(null);
  const [selectedProduct, setSelectedProduct] = useState(null);
  const [productVariants, setProductVariants] = useState([]);
  const [selectedVariant, setSelectedVariant] = useState(null);
  const [variantMode, setVariantMode] = useState("view");
  const [variantDraft, setVariantDraft] = useState(null);
  const [variantBusy, setVariantBusy] = useState(false);
  const [showCategoryForm, setShowCategoryForm] = useState(false);
  const [name, setName] = useState("");
  const [slug, setSlug] = useState("");
  const [parentId, setParentId] = useState("");
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");

  async function refresh() {
    try {
      const [c, p] = await Promise.all([
        apiRequest("/catalogue/categories"),
        apiRequest("/catalogue/products?status=all"),
      ]);
      setCategories(c.items || []);
      setProducts(p.items || []);
      setError("");
    } catch (e) {
      setError(e.message || "Catalogue API unavailable");
    }
  }

  useEffect(() => { refresh(); }, []);

  useEffect(() => {
    if (!selectedProduct) { setProductVariants([]); return; }
    apiRequest("/catalogue/products/" + selectedProduct.id + "/variants")
      .then(result => setProductVariants(result.items || []))
      .catch(e => setError(e.message || "Unable to load product variants."));
  }, [selectedProduct?.id]);

  async function createCategory(event) {
    event.preventDefault();
    setError("");
    setMessage("");
    try {
      await apiRequest("/catalogue/categories", {
        method: "POST",
        body: JSON.stringify({ name, slug, parent_id: parentId ? Number(parentId) : null }),
      });
      setName("");
      setSlug("");
      setParentId("");
      setShowCategoryForm(false);
      setMessage(parentId ? "Subcategory created." : "Category created.");
      await refresh();
    } catch (e) {
      setError(e.message || "Unable to create category");
    }
  }

  const parentCategories = categories.filter(item => !item.parent_id);
  const childrenOf = id => categories.filter(child => Number(child.parent_id) === Number(id));

  return <section className="sb-workspace">
    <button className="sb-back" onClick={onBack} type="button">← All workspaces</button>
    <p className="sb-eyebrow">CATALOGUE MANAGEMENT</p>
    <h1>Catalogue</h1>
    <p>Manage products, categories and product attributes in one place.</p>

    <nav className="sb-catalogue-tabs" aria-label="Catalogue sections" role="tablist">
      <button type="button" role="tab" aria-selected={activeTab === "catalogue"} className={activeTab === "catalogue" ? "is-active" : ""} onClick={() => { setActiveTab("catalogue"); setError(""); setMessage(""); }}>Catalogue <span>{products.length}</span></button>
      <button type="button" role="tab" aria-selected={activeTab === "categories"} className={activeTab === "categories" ? "is-active" : ""} onClick={() => { setActiveTab("categories"); setError(""); setMessage(""); }}>Categories <span>{categories.length}</span></button>
      <button type="button" role="tab" aria-selected={activeTab === "attributes"} className={activeTab === "attributes" ? "is-active" : ""} onClick={() => { setActiveTab("attributes"); setError(""); setMessage(""); }}>Attributes</button>
    </nav>

    {error && <p role="alert" className="sb-alert">{error}</p>}
    {message && <p role="status" className="sb-success">{message}</p>}

    {activeTab === "catalogue" && <>
      <div className="sb-catalogue-toolbar">
        <div><h2>All products</h2><p className="sb-muted">Products loaded from the backend API.</p></div>
        <button className="sb-primary" type="button" onClick={() => setShowProductForm(value => !value)}>{showProductForm ? "Cancel" : "+ Add product"}</button>
      </div>
      {(showProductForm || editingProduct) && <ProductCreateForm product={editingProduct} categories={categories} onSaved={async () => { await refresh(); setShowProductForm(false); setEditingProduct(null); }} />}
      <div className="sb-strip-list" aria-label="Product list">
        {products.length ? products.map(item => <article className="sb-strip-row sb-product-row" key={item.id}>
          <div className="sb-strip-icon" aria-hidden="true">S</div>
          <div className="sb-strip-main"><strong>{item.name}</strong><small>{item.brand || "No brand"} · {categories.find(category => Number(category.id) === Number(item.category_id))?.name || "Uncategorised"}</small><small>{item.min_selling_price != null ? "₹" + item.min_selling_price + (item.max_selling_price != null && Number(item.max_selling_price) !== Number(item.min_selling_price) ? " – ₹" + item.max_selling_price : "") : "Price not set"}</small></div>
          <button type="button" className="sb-row-action" onClick={() => { setSelectedProduct(item); setSelectedVariant(null); }}>Variants ({item.variant_count || 0})</button>
          <span className={"sb-status-pill sb-status-" + item.status}>{item.status}</span>
          <button type="button" className="sb-row-action" onClick={() => { setEditingProduct(item); setShowProductForm(false); }}>Edit</button>
          {item.status !== "archived" && <button type="button" className="sb-row-action" onClick={async () => { if (!window.confirm("Archive " + item.name + "? Existing order history will be preserved.")) return; try { await apiRequest("/catalogue/products/" + item.id + "/archive", {method:"POST"}); setMessage("Product archived."); await refresh(); if (selectedProduct?.id === item.id) setSelectedProduct(null); } catch(e) { setError(e.message || "Unable to archive product."); } }}>Archive</button>}
          <span className="sb-strip-meta">#{item.id}</span>
        </article>) : <p className="sb-empty">No products found. Select Add product to create your first product.</p>}
      </div>
      {selectedProduct && <section className="sb-data-card sb-variant-catalogue">
        <div className="sb-data-heading"><div><h2>Variants for {selectedProduct.name}</h2><p className="sb-muted">Each action applies only to the selected variant.</p></div><button type="button" onClick={() => {setSelectedProduct(null);setSelectedVariant(null);}}>Close variants</button></div>
        {productVariants.length ? <div className="sb-strip-list">{productVariants.map(variant => <article className="sb-strip-row" key={variant.id}>
          <div className="sb-strip-icon" aria-hidden="true">SKU</div><div className="sb-strip-main"><strong>{variant.sku}</strong><small>{JSON.stringify(variant.attributes || {})}</small><small>₹{variant.selling_price} · MRP {variant.mrp == null ? "—" : "₹" + variant.mrp}</small></div>
          <span className={"sb-status-pill " + (variant.is_active ? "sb-status-active" : "sb-status-archived")}>{variant.is_active ? "Active" : "Archived"}</span>
          <button type="button" className="sb-row-action" onClick={() => {setSelectedVariant(variant);setVariantDraft({...variant,attributes:JSON.stringify(variant.attributes || {},null,2),selling_price:String(variant.selling_price),mrp:variant.mrp == null ? "" : String(variant.mrp),cost_price:variant.cost_price == null ? "" : String(variant.cost_price),barcode:variant.barcode || ""});setVariantMode("view");}}>View</button>
          {variant.is_active && <button type="button" className="sb-row-action" onClick={() => {setSelectedVariant(variant);setVariantDraft({...variant,attributes:JSON.stringify(variant.attributes || {},null,2),selling_price:String(variant.selling_price),mrp:variant.mrp == null ? "" : String(variant.mrp),cost_price:variant.cost_price == null ? "" : String(variant.cost_price),barcode:variant.barcode || ""});setVariantMode("edit");}}>Edit</button>}
          {variant.is_active && <button type="button" className="sb-row-action" onClick={async () => {if(!window.confirm("Archive variant "+variant.sku+"? Historical records will be preserved.")) return;try{await apiRequest("/catalogue/variants/"+variant.id+"/archive",{method:"POST"});setMessage("Variant archived.");const updated=await apiRequest("/catalogue/products/"+selectedProduct.id+"/variants");setProductVariants(updated.items||[]);setSelectedVariant(null);await refresh();}catch(e){setError(e.message||"Unable to archive variant.");}}}>Archive</button>}
        </article>)}</div> : <p className="sb-empty">No variants have been created for this product yet.</p>}
        {selectedVariant && variantDraft && <form className="sb-form sb-form-inner" onSubmit={async e=>{e.preventDefault();if(variantMode!=="edit")return;setVariantBusy(true);setError("");try{let attrs;try{attrs=JSON.parse(variantDraft.attributes||"{}");}catch{throw new Error("Variant attributes must be valid JSON.");}await apiRequest("/catalogue/variants/"+selectedVariant.id,{method:"PUT",body:JSON.stringify({sku:variantDraft.sku,barcode:variantDraft.barcode||null,attributes:attrs,selling_price:Number(variantDraft.selling_price),mrp:variantDraft.mrp===""?null:Number(variantDraft.mrp),cost_price:variantDraft.cost_price===""?null:Number(variantDraft.cost_price)})});setMessage("Variant updated.");const updated=await apiRequest("/catalogue/products/"+selectedProduct.id+"/variants");setProductVariants(updated.items||[]);setSelectedVariant(null);await refresh();}catch(e){setError(e.message||"Unable to update variant.");}finally{setVariantBusy(false);}}}>
          <div className="sb-data-heading"><h3>{variantMode==="view"?"View variant":"Edit variant"} · {selectedVariant.sku}</h3><button type="button" onClick={()=>setSelectedVariant(null)}>Close</button></div>
          <div className="sb-form-grid">
            <label>SKU<input required value={variantDraft.sku||""} readOnly={variantMode==="view"} onChange={e=>setVariantDraft(v=>({...v,sku:e.target.value}))}/></label>
            <label>Barcode<input readOnly={variantMode==="view"} value={variantDraft.barcode||""} onChange={e=>setVariantDraft(v=>({...v,barcode:e.target.value}))}/></label>
            <label>Selling price (₹)<input required type="number" min="0" step="0.01" readOnly={variantMode==="view"} value={variantDraft.selling_price} onChange={e=>setVariantDraft(v=>({...v,selling_price:e.target.value}))}/></label>
            <label>MRP (₹)<input type="number" min="0" step="0.01" readOnly={variantMode==="view"} value={variantDraft.mrp} onChange={e=>setVariantDraft(v=>({...v,mrp:e.target.value}))}/></label>
            <label>Cost price (₹)<input type="number" min="0" step="0.01" readOnly={variantMode==="view"} value={variantDraft.cost_price} onChange={e=>setVariantDraft(v=>({...v,cost_price:e.target.value}))}/></label>
            <label className="sb-span-all">Attributes (JSON)<textarea rows="4" readOnly={variantMode==="view"} value={variantDraft.attributes} onChange={e=>setVariantDraft(v=>({...v,attributes:e.target.value}))}/></label>
          </div>
          {variantMode==="edit" && <button className="sb-primary" disabled={variantBusy} type="submit">{variantBusy?"Saving…":"Save variant changes"}</button>}
        </form>}
      </section>}
      <details className="sb-catalogue-tools"><summary>Product images</summary><ProductImagesPanel products={products} /></details>
    </>}

    {activeTab === "categories" && <>
      <div className="sb-catalogue-toolbar">
        <div><h2>All categories</h2><p className="sb-muted">Organise parent categories and subcategories.</p></div>
        <button className="sb-primary" type="button" onClick={() => setShowCategoryForm(value => !value)}>{showCategoryForm ? "Cancel" : "+ Add category"}</button>
      </div>
      {showCategoryForm && <form className="sb-form" onSubmit={createCategory}>
        <h2>Create category</h2>
        <div className="sb-form-grid">
          <label>Name<input required maxLength="160" value={name} onChange={e => {setName(e.target.value); setSlug(e.target.value.toLowerCase().trim().replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, ""));}} /></label>
          <label>Slug (automatic)<input required pattern="[a-z0-9]+(-[a-z0-9]+)*" value={slug} readOnly aria-readonly="true" /><small className="sb-muted">Generated from the category name.</small></label>
          <label className="sb-span-all">Parent category (optional)<select value={parentId} onChange={e => setParentId(e.target.value)}><option value="">None — create a main category</option>{parentCategories.map(item => <option key={item.id} value={item.id}>{item.name}</option>)}</select><small className="sb-muted">Choose a parent to create a subcategory.</small></label>
        </div>
        <button className="sb-primary" type="submit">Create category</button>
      </form>}
      <div className="sb-strip-list" aria-label="Category list">
        {parentCategories.length ? parentCategories.map(item => <div key={item.id}>
          <article className="sb-strip-row"><div className="sb-strip-icon" aria-hidden="true"><span>▦</span></div><div className="sb-strip-main"><strong>{item.name}</strong><small>/{item.slug} · Parent category</small></div><span className="sb-strip-meta">{childrenOf(item.id).length} subcategories</span></article>
          {childrenOf(item.id).map(child => <article className="sb-strip-row sb-strip-child" key={child.id}><div className="sb-strip-icon" aria-hidden="true">↳</div><div className="sb-strip-main"><strong>{child.name}</strong><small>/{child.slug} · Subcategory of {item.name}</small></div></article>)}
        </div>) : <p className="sb-empty">No categories found. Select Add category to create one.</p>}
      </div>
    </>}

    {activeTab === "attributes" && <>
      <div className="sb-catalogue-toolbar">
        <div><h2>Product attributes</h2><p className="sb-muted">Define properties such as colour, size and material.</p></div>
      </div>
      <CatalogueVariantsPanel products={[]} categories={[]} mode="attributes" />
    </>}
  </section>;
}
