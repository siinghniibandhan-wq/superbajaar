import { useEffect, useState } from "react";
import { apiRequest } from "../../services/api.js";
import ProductCreateForm from "./ProductCreateForm.jsx";

export default function CatalogueWorkspace({ onBack }) {
  const [categories, setCategories] = useState([]);
  const [products, setProducts] = useState([]);
  const [name, setName] = useState("");
  const [slug, setSlug] = useState("");
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
        body: JSON.stringify({ name, slug }),
      });
      setName("");
      setSlug("");
      setMessage("Category created.");
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
        <label>Name<input required value={name} onChange={e => {setName(e.target.value); if (!slug) setSlug(e.target.value.toLowerCase().trim().replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, ""));}} /></label>
        <label>Slug<input required pattern="[a-z0-9]+(-[a-z0-9]+)*" value={slug} onChange={e => setSlug(e.target.value)} /></label>
      </div>
      <button className="sb-primary" type="submit">Create category</button>
    </form>
    <div className="sb-data-card">
      <div className="sb-data-heading"><h2>Categories</h2><button type="button" onClick={refresh}>Refresh</button></div>
      {categories.length ? <ul>{categories.map(item => <li key={item.id}>{item.name} <small>({item.slug})</small></li>)}</ul> : <p className="sb-empty">No categories loaded.</p>}
    </div>
    <div className="sb-data-card">
      <h2>Products ({products.length})</h2>
      {products.length ? <ul>{products.map(item => <li key={item.id}>{item.name} <small>— {item.status}</small></li>)}</ul> : <p className="sb-empty">No products loaded.</p>}
    </div>
  </section>;
}
