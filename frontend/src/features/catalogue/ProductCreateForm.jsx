import { useState } from "react";
import { apiRequest } from "../../services/api.js";

export default function ProductCreateForm({ categories, onSaved }) {
  const [form, setForm] = useState({ name: "", slug: "", brand: "", category_id: "", description: "", tax_code: "", tax_rate: "" });
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [success, setSuccess] = useState("");
  const change = (key, value) => setForm(old => ({ ...old, [key]: value }));
  const slugify = value => value.toLowerCase().trim().replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "");

  async function submit(event) {
    event.preventDefault(); setBusy(true); setError(""); setSuccess("");
    try {
      await apiRequest("/catalogue/products", { method: "POST", body: JSON.stringify({
        ...form,
        category_id: form.category_id ? Number(form.category_id) : null,
        tax_rate: form.tax_rate === "" ? null : Number(form.tax_rate),
      }) });
      setSuccess("Product saved as draft.");
      setForm({ name: "", slug: "", brand: "", category_id: "", description: "", tax_code: "", tax_rate: "" });
      await onSaved?.();
    } catch (e) { setError(e.message || "Unable to save product."); }
    finally { setBusy(false); }
  }

  return <form className="sb-form" onSubmit={submit}>
    <h2>Add product</h2>
    {error && <p role="alert" className="sb-alert">{error}</p>}
    {success && <p role="status" className="sb-success">{success}</p>}
    <div className="sb-form-grid">
      <label>Product name<input required maxLength="240" value={form.name} onChange={e => {const name=e.target.value;setForm(old=>({...old,name,slug:old.slug || slugify(name)}));}} /></label>
      <label>Slug<input required pattern="[a-z0-9]+(-[a-z0-9]+)*" value={form.slug} onChange={e=>change("slug",e.target.value)} /></label>
      <label>Brand<input maxLength="160" value={form.brand} onChange={e=>change("brand",e.target.value)} /></label>
      <label>Category<select value={form.category_id} onChange={e=>change("category_id",e.target.value)}><option value="">No category</option>{categories.map(c=><option key={c.id} value={c.id}>{c.name}</option>)}</select></label>
      <label>Tax code<input maxLength="32" value={form.tax_code} onChange={e=>change("tax_code",e.target.value)} /></label>
      <label>Tax rate (%)<input type="number" min="0" max="100" step="0.01" value={form.tax_rate} onChange={e=>change("tax_rate",e.target.value)} /></label>
      <label className="sb-span-all">Description<input value={form.description} onChange={e=>change("description",e.target.value)} /></label>
    </div>
    <button className="sb-primary" disabled={busy} type="submit">{busy ? "Saving…" : "Save draft product"}</button>
  </form>;
}
