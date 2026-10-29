import { useEffect, useState } from "react";
import { apiRequest } from "../../services/api.js";
import ProductCreateForm from "./ProductCreateForm.jsx";
import CatalogueVariantsPanel from "./CatalogueVariantsPanel.jsx";
import ProductImagesPanel from "./ProductImagesPanel.jsx";
import "./catalogue.css";

export default function CatalogueWorkspace({ onBack }) {
  const [categories, setCategories] = useState([]);
  const [products, setProducts] = useState([]);
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
      setMessage(parentId ? "Subcategory created." : "Category created.");
      await refresh();
    } catch (e) {
      setError(e.message || "Unable to create category");
    }
  }

  return <section className="sb-workspace">
    <button className="sb-back" onClick={onBack} type="button">← All workspaces</button>
    <p className="sb-eyebrow">CATALOGUE MANAGEMENT</p>
    <h1>Catalogue</h1>
    <p>Categories and products loaded from the backend API.</p>
    <ProductCreateForm categories={categories} onSaved={refresh} />
    {error && <p role="alert" className="sb-alert">{error}</p>}
    {message && <p role="status" className="sb-success">{message}</p>}
    <form className="sb-form" onSubmit={createCategory}>
      <h2>Create category</h2>
      <div className="sb-form-grid">
        <label>Name<input required value={name} onChange={e => {setName(e.target.value); setSlug(e.target.value.toLowerCase().trim().replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, ""));}} /></label>
        <label>Slug (automatic)<input required pattern="[a-z0-9]+(-[a-z0-9]+)*" value={slug} readOnly aria-readonly="true" /><small className="sb-muted">Generated from the category name.</small></label>
        <label className="sb-span-all">Parent category (optional)<select value={parentId} onChange={e => setParentId(e.target.value)}><option value="">None — create a main category</option>{categories.filter(item => !item.parent_id).map(item => <option key={item.id} value={item.id}>{item.name}</option>)}</select><small className="sb-muted">Choose a parent to create a subcategory.</small></label>
      </div>
      <button className="sb-primary" type="submit">Create category</button>
    </form>
    <div className="sb-data-card">
      <div className="sb-data-heading"><h2>Categories</h2><button type="button" onClick={refresh}>Refresh</button></div>
      {categories.length ? <ul>{categories.filter(item => !item.parent_id).map(item => <li key={item.id}>{item.name} <small>({item.slug})</small>{categories.filter(child => Number(child.parent_id) === Number(item.id)).length > 0 && <ul>{categories.filter(child => Number(child.parent_id) === Number(item.id)).map(child => <li key={child.id}>{child.name} <small>({child.slug})</small></li>)}</ul>}</li>)}</ul> : <p className="sb-empty">No categories loaded.</p>}
    </div>
    <div className="sb-data-card">
      <CatalogueVariantsPanel products={products} categories={categories} />
      <ProductImagesPanel products={products} />
      <h2>Products ({products.length})</h2>
      {products.length ? <ul>{products.map(item => <li key={item.id}>{item.name} <small>— {item.status}</small></li>)}</ul> : <p className="sb-empty">No products loaded.</p>}
    </div>
  </section>;
}
