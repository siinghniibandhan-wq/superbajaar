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
        <button className="sb-primary" type="button" onClick={() => { setEditingProduct(null); setShowProductForm(value => !value); }}>{showProductForm ? "Cancel" : "+ Add product"}</button>
      </div>
      {showProductForm && <ProductCreateForm categories={categories} product={editingProduct} onSaved={async () => { await refresh(); setShowProductForm(false); setEditingProduct(null); }} />}
      <div className="sb-strip-list" aria-label="Product list">
        {products.length ? products.map(item => <article className="sb-strip-row" key={item.id}>
          <div className="sb-strip-icon" aria-hidden="true">S</div>
          <div className="sb-strip-main"><strong>{item.name}</strong><small>{item.brand || "No brand"} · {categories.find(category => Number(category.id) === Number(item.category_id))?.name || "Uncategorised"} · {item.variant_count || 0} variant(s)</small><b>{item.min_selling_price == null ? "Price not set" : item.min_selling_price === item.max_selling_price ? "₹" + Number(item.min_selling_price).toFixed(2) : "₹" + Number(item.min_selling_price).toFixed(2) + " – ₹" + Number(item.max_selling_price).toFixed(2)}</b></div>
          <span className={"sb-status-pill sb-status-" + item.status}>{item.status}</span>
          <button type="button" className="sb-row-action" onClick={() => { setEditingProduct(item); setShowProductForm(true); }}>Edit</button>
          {item.status !== "archived" && <button type="button" className="sb-row-action" onClick={async () => { if (!window.confirm("Archive " + item.name + "?")) return; try { await apiRequest("/catalogue/products/" + item.id + "/archive", {method:"POST"}); await refresh(); } catch (e) { setError(e.message || "Unable to archive product"); } }}>Archive</button>}
          <span className="sb-strip-meta">#{item.id}</span>
        </article>) : <p className="sb-empty">No products found. Select Add product to create your first product.</p>}
      </div>
      
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
      <CatalogueVariantsPanel products={products} categories={categories} />
      <ProductImagesPanel products={products} />
    </>}
  </section>;
}
