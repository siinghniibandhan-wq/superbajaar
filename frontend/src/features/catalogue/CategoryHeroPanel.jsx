import { useEffect, useMemo, useState } from "react";
import { apiRequest } from "../../services/api.js";
import { prepareProductImage } from "./productImageFormat.js";
import { categoryPath } from "./hsnRules.js";

// Admin: manage the hero slider images shown at the top of each storefront category page.
export default function CategoryHeroPanel({ categories = [] }) {
  const [categoryId, setCategoryId] = useState("");
  const [images, setImages] = useState([]);
  const [files, setFiles] = useState([]);
  const [fileInputKey, setFileInputKey] = useState(0);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");

  const sortedCategories = useMemo(() => [...categories].filter(c => c.is_active !== false)
    .map(c => ({ ...c, path: categoryPath(categories, c.id) })).sort((a, b) => a.path.localeCompare(b.path)), [categories]);
  const base = "/catalogue/categories/" + categoryId + "/hero-images";

  async function load(id = categoryId) {
    if (!id) { setImages([]); return; }
    try { const result = await apiRequest("/catalogue/categories/" + id + "/hero-images"); setImages(result.items || []); }
    catch (e) { setError(e.message || "Unable to load banner images."); }
  }
  useEffect(() => { setError(""); setMessage(""); setFiles([]); setFileInputKey(k => k + 1); load(categoryId); }, [categoryId]);

  async function run(action, success) {
    setBusy(true); setError(""); setMessage("");
    try { await action(); if (success) setMessage(success); await load(); }
    catch (e) { setError(e.message || "Something went wrong. Please try again."); }
    finally { setBusy(false); }
  }

  async function upload(event) {
    event.preventDefault();
    if (!categoryId || !files.length) return;
    setBusy(true); setError(""); setMessage("");
    let done = 0; const failed = [];
    for (const file of files) {
      try {
        const prepared = await prepareProductImage(file);
        const body = new FormData();
        body.append("file", prepared, prepared.name);
        await apiRequest(base + "/upload", { method: "POST", body });
        done += 1;
      } catch (e) { failed.push(file.name + ": " + (e.message || "failed")); }
    }
    if (done) { setMessage(done + " image" + (done > 1 ? "s" : "") + " added to the slider."); setFiles([]); setFileInputKey(k => k + 1); await load(); }
    if (failed.length) setError(failed.length + " failed — " + failed.join("; "));
    setBusy(false);
  }

  const move = (index, step) => {
    const ids = images.map(i => i.id);
    const target = index + step;
    if (target < 0 || target >= ids.length) return;
    [ids[index], ids[target]] = [ids[target], ids[index]];
    run(() => apiRequest(base + "/reorder", { method: "POST", body: JSON.stringify({ ids }) }), "Slider order saved.");
  };
  const toggle = image => run(() => apiRequest(base + "/" + image.id, { method: "PUT", body: JSON.stringify({ is_active: !image.is_active }) }),
    image.is_active ? "Image hidden from the website." : "Image is live on the website.");
  const remove = image => { if (window.confirm("Delete this image? This cannot be undone.")) run(() => apiRequest(base + "/" + image.id, { method: "DELETE" }), "Image deleted."); };
  const saveAlt = (image, alt_text) => { if ((alt_text || "") !== (image.alt_text || "")) run(() => apiRequest(base + "/" + image.id, { method: "PUT", body: JSON.stringify({ alt_text }) }), "Description saved."); };

  return <section className="sb-data-card sb-hero-panel">
    <h2>Category banners</h2>
    <p className="sb-muted">Upload images for the hero slider at the top of a category page. Add more than one and they play as a slider, in the order shown here. A category with no images keeps the standard banner.</p>
    {error && <p role="alert" className="sb-alert">{error}</p>}
    {message && <p role="status" className="sb-success">{message}</p>}

    <label className="sb-hero-field">Category
      <select value={categoryId} onChange={event => setCategoryId(event.target.value)}>
        <option value="">Choose a category…</option>
        {sortedCategories.map(c => <option key={c.id} value={c.id}>{c.path}</option>)}
      </select>
    </label>

    {categoryId && <>
      <form className="sb-hero-upload" onSubmit={upload}>
        <label className="sb-hero-field">Add images
          <input key={fileInputKey} type="file" multiple accept="image/jpeg,image/png,image/webp,image/gif" onChange={event => setFiles(Array.from(event.target.files || []))} />
        </label>
        <small className="sb-muted">Best size: wide banner, about 1600 × 600 px (up to 10 MB each). Keep the important part in the centre, because phones show the sides cropped.</small>
        <button className="sb-primary" type="submit" disabled={busy || !files.length}>{busy ? "Working…" : "Upload " + (files.length || "") + " image" + (files.length === 1 ? "" : "s")}</button>
      </form>

      {images.length === 0 && <p className="sb-muted">No images yet for this category.</p>}
      <ol className="sb-hero-list">
        {images.map((image, index) => <li key={image.id} className={"sb-hero-item" + (image.is_active ? "" : " is-hidden")}>
          <img src={image.image_url} alt={image.alt_text || "Banner " + (index + 1)} loading="lazy" />
          <div className="sb-hero-item-body">
            <strong>Slide {index + 1}{image.is_active ? "" : " · hidden"}</strong>
            <input type="text" maxLength={300} defaultValue={image.alt_text || ""} placeholder="Short description (optional)" aria-label={"Description for slide " + (index + 1)} onBlur={event => saveAlt(image, event.target.value.trim())} disabled={busy} />
            <div className="sb-hero-actions">
              <button type="button" className="sb-secondary" disabled={busy || index === 0} onClick={() => move(index, -1)} aria-label="Move earlier">↑ Earlier</button>
              <button type="button" className="sb-secondary" disabled={busy || index === images.length - 1} onClick={() => move(index, 1)} aria-label="Move later">↓ Later</button>
              <button type="button" className="sb-secondary" disabled={busy} onClick={() => toggle(image)}>{image.is_active ? "Hide" : "Show"}</button>
              <button type="button" className="sb-secondary" disabled={busy} onClick={() => remove(image)}>Delete</button>
            </div>
          </div>
        </li>)}
      </ol>
    </>}
  </section>;
}
