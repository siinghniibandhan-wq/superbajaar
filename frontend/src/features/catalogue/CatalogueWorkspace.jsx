import { useEffect, useState } from "react";
import { apiRequest } from "../../services/api.js";
import ProductCreateForm from "./ProductCreateForm.jsx";
import CatalogueVariantsPanel from "./CatalogueVariantsPanel.jsx";
import ProductImagesPanel from "./ProductImagesPanel.jsx";
import CatalogueModal from "./CatalogueModal.jsx";
import "./catalogue.css";

export default function CatalogueWorkspace({ onBack, currentUser }) {
  const canDeleteProducts = ["owner", "admin"].includes(String(currentUser?.role || "").toLowerCase());
  const [activeTab, setActiveTab] = useState("catalogue");
  const [categories, setCategories] = useState([]);
  const [products, setProducts] = useState([]);
  const [showProductForm, setShowProductForm] = useState(false);
  const [editingProduct, setEditingProduct] = useState(null);
  const [productFormBusy, setProductFormBusy] = useState(false);
  const [selectedVariantProductId, setSelectedVariantProductId] = useState("");
  const [showCategoryForm, setShowCategoryForm] = useState(false);
  const [editingCategory, setEditingCategory] = useState(null);
  const [categoryFormBusy, setCategoryFormBusy] = useState(false);
  const [name, setName] = useState("");
  const [slug, setSlug] = useState("");
  const [parentId, setParentId] = useState("");
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");

  async function refresh() {
    try {
      const [c, p] = await Promise.all([
        apiRequest("/catalogue/categories?limit=500"),
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

  function openCategoryForm(category = null, selectedParentId = "") {
    setEditingCategory(category);
    setName(category?.name || "");
    setSlug(category?.slug || "");
    setParentId(category?.parent_id ? String(category.parent_id) : selectedParentId);
    setShowCategoryForm(true);
    setError("");
    setMessage("");
  }

  function closeCategoryForm() {
    if (categoryFormBusy) return;
    if ((name || slug) && !window.confirm("Discard unsaved category changes?")) return;
    setShowCategoryForm(false);
    setEditingCategory(null);
    setName("");
    setSlug("");
    setParentId("");
  }

  async function saveCategory(event) {
    event.preventDefault();
    setCategoryFormBusy(true);
    setError("");
    setMessage("");
    try {
      const savedParentId = parentId;
      await apiRequest(editingCategory ? "/catalogue/categories/" + editingCategory.id : "/catalogue/categories", {
        method: editingCategory ? "PUT" : "POST",
        body: JSON.stringify({ name, slug, parent_id: parentId ? Number(parentId) : null }),
      });
      setName("");
      setSlug("");
      setParentId("");
      setShowCategoryForm(false);
      setEditingCategory(null);
      setMessage(editingCategory ? "Category updated." : savedParentId ? "Subcategory created." : "Category created.");
      await refresh();
    } catch (e) {
      setError(e.message || "Unable to save category");
    } finally { setCategoryFormBusy(false); }
  }

  const childrenOf = id => categories.filter(child => Number(child.parent_id) === Number(id));
  const descendantIds = (categoryId, found = new Set()) => {
    for (const child of childrenOf(categoryId)) {
      if (!found.has(Number(child.id))) {
        found.add(Number(child.id));
        descendantIds(child.id, found);
      }
    }
    return found;
  };
  const excludedParentIds = editingCategory
    ? new Set([Number(editingCategory.id), ...descendantIds(editingCategory.id)])
    : new Set();
  const categoryParents = categories.filter(item => !excludedParentIds.has(Number(item.id)));
  async function deleteProduct(item) {
    const reason = window.prompt('Reason for deleting "' + item.name + '" (required, at least 10 characters):');
    if (reason === null) return;
    if (reason.trim().length < 10) {
      setError("Deletion cancelled: enter a reason of at least 10 characters.");
      return;
    }
    if (!window.confirm('Permanently delete product "' + item.name + '"? This cannot be undone.')) return;
    setError(""); setMessage("");
    try {
      await apiRequest("/catalogue/products/" + item.id, {
        method: "DELETE",
        body: JSON.stringify({ reason: reason.trim() }),
      });
      setMessage("Product deleted. The deletion reason has been recorded.");
      await refresh();
    } catch (e) {
      setError(e.message || "Unable to delete product");
    }
  }

  function closeProductForm() {
    if (productFormBusy) return;
    if (!window.confirm("Close this product form? Unsaved changes will be lost.")) return;
    setShowProductForm(false);
    setEditingProduct(null);
  }
  const categoryPathFor = category => {
    const path = [];
    const seen = new Set();
    let current = category;
    while (current && !seen.has(Number(current.id))) {
      seen.add(Number(current.id));
      path.unshift(current.name);
      current = categories.find(value => Number(value.id) === Number(current.parent_id));
    }
    return path;
  };
  const renderCategory = (item, depth = 0) => <div key={item.id}>
    <article className="sb-strip-row">
      <div className="sb-strip-icon" aria-hidden="true">{depth ? "↳" : <span>▦</span>}</div>
      <div className="sb-strip-main"><strong>{item.name}</strong><small>/{item.slug}{item.parent_id ? " · Subcategory" : " · Parent category"}</small></div>
      <div className="sb-category-actions">
        <button type="button" className="sb-row-action" onClick={() => openCategoryForm(item)}>Edit</button>
        <button type="button" className="sb-row-action" onClick={() => openCategoryForm(null, String(item.id))}>Add child</button>
      </div>
    </article>
    {childrenOf(item.id).map(child => <div className="sb-category-nested" key={child.id}>{renderCategory(child, depth + 1)}</div>)}
  </div>;

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
        <button className="sb-primary" type="button" onClick={() => { setEditingProduct(null); setShowProductForm(true); }}>+ Add product</button>
      </div>
      <CatalogueModal
        open={showProductForm}
        title={editingProduct ? "Edit product" : "Add product"}
        className="sb-product-modal"
        onRequestClose={closeProductForm}
        footer={<>
          <button type="submit" form="catalogue-product-form" className="sb-primary" disabled={productFormBusy}>{productFormBusy ? "Saving…" : editingProduct ? "Save product" : "Save product and variants"}</button>
          <button type="button" className="sb-secondary" disabled={productFormBusy} onClick={closeProductForm}>Cancel</button>
        </>}
      >
        {showProductForm && <ProductCreateForm
          categories={categories}
          product={editingProduct}
          onBusyChange={setProductFormBusy}
          onSaved={async () => { await refresh(); setShowProductForm(false); setEditingProduct(null); }}
        />}
      </CatalogueModal>
      <div className="sb-strip-list" aria-label="Product list">
        {products.length ? products.map(item => {
          const category = categories.find(value => Number(value.id) === Number(item.category_id));
          const detail = [item.brand, categoryPathFor(category).join(" · ")].filter(Boolean).join(" · ") || "No brand or category";
          return <article className="sb-strip-row sb-product-card" key={item.id}>
          <div className="sb-strip-icon" aria-hidden="true">S</div>
          <div className="sb-strip-main">
            <strong>{item.name}</strong>
            <small>{detail}</small>
            <button type="button" className="sb-variant-pill" onClick={() => { setSelectedVariantProductId(String(item.id)); setActiveTab("attributes"); }}>{item.variant_count ?? 0} Variants</button>
            <b className="sb-product-price">{item.min_selling_price == null ? "Price not set" : item.min_selling_price === item.max_selling_price ? "₹" + Number(item.min_selling_price).toFixed(2) : "₹" + Number(item.min_selling_price).toFixed(2) + " – ₹" + Number(item.max_selling_price).toFixed(2)}</b>
            <small className="sb-product-stock">Available stock · {item.available_stock == null ? "Not recorded" : Number(item.available_stock).toLocaleString(undefined, { maximumFractionDigits: 3 }) + " across active locations"}</small>
          </div>
          <span className={"sb-status-pill sb-status-" + item.status}>{item.status}</span>
          <button type="button" className="sb-row-action sb-product-edit" onClick={() => { setEditingProduct(item); setShowProductForm(true); }}>Edit</button>
          {item.status !== "archived" && <button type="button" className="sb-row-action sb-product-archive" onClick={async () => { if (!window.confirm("Archive " + item.name + "?")) return; try { await apiRequest("/catalogue/products/" + item.id + "/archive", {method:"POST"}); await refresh(); } catch (e) { setError(e.message || "Unable to archive product"); } }}>Archive</button>}
          {canDeleteProducts && <button type="button" className="sb-row-action sb-product-delete" onClick={() => deleteProduct(item)}>Delete</button>}
          <span className="sb-strip-meta sb-product-id">#{item.id}</span>
        </article>;
        }) : <p className="sb-empty">No products found. Select Add product to create your first product.</p>}
      </div>

    </>}

    {activeTab === "categories" && <>
      <div className="sb-catalogue-toolbar">
        <div><h2>All categories</h2><p className="sb-muted">Organise parent categories and subcategories.</p></div>
        <button className="sb-primary" type="button" onClick={() => openCategoryForm()}>+ Add category</button>
      </div>
      <CatalogueModal
        open={showCategoryForm}
        title={editingCategory ? "Edit category" : parentId ? "Add child category" : "Add category"}
        onRequestClose={closeCategoryForm}
        footer={<>
          <button type="submit" form="catalogue-category-form" className="sb-primary" disabled={categoryFormBusy}>{categoryFormBusy ? "Saving…" : editingCategory ? "Save category" : "Create category"}</button>
          <button type="button" className="sb-secondary" disabled={categoryFormBusy} onClick={closeCategoryForm}>Cancel</button>
        </>}
      >
        {showCategoryForm && <>
          {error && <p className="sb-alert" role="alert">{error}</p>}
          <form id="catalogue-category-form" className="sb-form sb-modal-form" onSubmit={saveCategory}>
          <div className="sb-form-grid">
            <label>Name<input required maxLength="160" value={name} onChange={e => {setName(e.target.value); setSlug(e.target.value.toLowerCase().trim().replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, ""));}} /></label>
            <label>Slug (automatic)<input required pattern="[a-z0-9]+(-[a-z0-9]+)*" value={slug} readOnly aria-readonly="true" /><small className="sb-muted">Generated from the category name.</small></label>
            <label className="sb-span-all">Parent category (optional)<select value={parentId} onChange={e => setParentId(e.target.value)}><option value="">None — create a main category</option>{categoryParents.map(item => <option key={item.id} value={item.id}>{categoryPathFor(item).join(" · ")}</option>)}</select><small className="sb-muted">Choose a parent to create a category at any depth.</small></label>
          </div>
          </form>
        </>}
      </CatalogueModal>
      <div className="sb-strip-list" aria-label="Category list">
        {categories.some(item => !item.parent_id) ? categories.filter(item => !item.parent_id).map(item => renderCategory(item)) : <p className="sb-empty">No categories found. Select Add category to create one.</p>}
      </div>
    </>}

    {activeTab === "attributes" && <>
      <div className="sb-catalogue-toolbar">
        <div><h2>Product attributes</h2><p className="sb-muted">Define properties such as colour, size and material.</p></div>
      </div>
      <CatalogueVariantsPanel products={products} categories={categories} initialProductId={selectedVariantProductId} />
      <ProductImagesPanel products={products} />
    </>}
  </section>;
}
