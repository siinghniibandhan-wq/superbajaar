import { useEffect, useState } from "react";
import { apiRequest } from "../../services/api.js";
import { prepareProductImage } from "./productImageFormat.js";
import { colourOptionLabel } from "./colourOptions.js";

// Readable variant name for pickers and gallery headings, e.g. "Red / 0.5 KG".
function variantName(variant) {
  const parts = Object.values(variant?.attributes || {}).map(raw => {
    const value = Array.isArray(raw) ? raw[0] : raw;
    return colourOptionLabel(value) || String(value ?? "").trim();
  }).filter(Boolean);
  return parts.length ? parts.join(" / ") : (variant?.sku || "Variant");
}
function variantCode(variant) {
  const tail = String(variant?.sku || "").split("-").pop();
  return /^V\d+$/i.test(tail) ? tail.toUpperCase() : "";
}
function variantOptionLabel(variant) {
  const code = variantCode(variant);
  return variantName(variant) + (code ? " · " + code : "");
}

export default function ProductImagesPanel({ products = [], initialProductId = "", embedded = false }) {
  const [productId, setProductId] = useState(initialProductId ? String(initialProductId) : "");
  const [variantId, setVariantId] = useState("");
  const [variants, setVariants] = useState([]);
  const [images, setImages] = useState([]);
  const [imageUrl, setImageUrl] = useState("");
  const [imageFiles, setImageFiles] = useState([]);
  const [fileInputKey, setFileInputKey] = useState(0);
  const [altText, setAltText] = useState("");
  const [sortOrder, setSortOrder] = useState("0");
  const [isPrimary, setIsPrimary] = useState(false);
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");
  const [busy, setBusy] = useState(false);
  const [pickerOpen, setPickerOpen] = useState(false);
  const [library, setLibrary] = useState([]);
  const [libQuery, setLibQuery] = useState("");
  const [libLoading, setLibLoading] = useState(false);
  const [libHasMore, setLibHasMore] = useState(false);
  const [pickedUrls, setPickedUrls] = useState([]);
  const [pickerSelection, setPickerSelection] = useState([]);

  async function loadLibrary(query = libQuery, append = false) {
    setLibLoading(true);
    try {
      const offset = append ? library.length : 0;
      const result = await apiRequest("/catalogue/media-library?limit=48&offset=" + offset + "&q=" + encodeURIComponent(query.trim()));
      setLibrary(prev => append ? [...prev, ...(result.items || [])] : (result.items || []));
      setLibHasMore(Boolean(result.has_more));
    } catch (e) { setError(e.message || "Unable to load the image library."); }
    finally { setLibLoading(false); }
  }
  function openPicker() { setPickerOpen(true); setPickerSelection(pickedUrls); loadLibrary("", false); setLibQuery(""); }
  function togglePicked(item) {
    setPickerSelection(prev => prev.some(i => i.image_url === item.image_url) ? prev.filter(i => i.image_url !== item.image_url) : [...prev, { image_url: item.image_url, alt_text: item.alt_text || "" }]);
  }
  function confirmPicked() {
    setPickedUrls(pickerSelection); setImageFiles([]); setFileInputKey(k => k + 1); setImageUrl("");
    setPickerOpen(false);
    setMessage(pickerSelection.length ? pickerSelection.length + " existing image" + (pickerSelection.length > 1 ? "s" : "") + " selected. Choose a variant if needed, then add them." : "");
  }

  async function loadImages(id = productId) {
    if (!id) { setImages([]); return; }
    try { const result = await apiRequest("/catalogue/products/" + id + "/images"); setImages(result.items || []); }
    catch (e) { setError(e.message || "Unable to load product images."); }
  }
  useEffect(() => { if (initialProductId && String(initialProductId) !== String(productId)) setProductId(String(initialProductId)); }, [initialProductId]);
  useEffect(() => {
    setVariants([]); setVariantId(""); setImages([]);
    if (!productId) return;
    Promise.all([
      apiRequest("/catalogue/products/" + productId + "/variants"),
      apiRequest("/catalogue/products/" + productId + "/images"),
    ]).then(([v, i]) => { setVariants(v.items || []); setImages(i.items || []); })
      .catch(e => setError(e.message || "Unable to load product media."));
  }, [productId]);

  async function setPrimary(image) {
    setBusy(true); setError(""); setMessage("");
    try {
      await apiRequest("/catalogue/products/" + productId + "/images/" + image.id + "/primary", { method: "PUT" });
      setMessage("Main cover image updated."); await loadImages(productId);
    } catch (e) { setError(e.message || "Unable to update the main cover image."); }
    finally { setBusy(false); }
  }

  async function removeImage(image) {
    if (!window.confirm("Delete this image? This cannot be undone.")) return;
    setBusy(true); setError(""); setMessage("");
    try {
      await apiRequest("/catalogue/products/" + productId + "/images/" + image.id, { method: "DELETE" });
      setMessage("Image deleted."); await loadImages(productId);
    } catch (e) { setError(e.message || "Unable to delete the image."); }
    finally { setBusy(false); }
  }

  async function submit(event) {
    event.preventDefault(); setBusy(true); setError(""); setMessage("");
    const base = Number(sortOrder) || 0;
    const jobs = imageFiles.length
      ? imageFiles.map((file, i) => ({ kind: "file", file, label: file.name, i }))
      : pickedUrls.length
        ? pickedUrls.map((item, i) => ({ kind: "url", url: item.image_url, alt: item.alt_text, label: item.alt_text || "Existing image", i }))
        : [{ kind: "url", url: imageUrl.trim(), alt: "", label: "Image URL", i: 0 }];
    let done = 0; let converted = 0; const failed = [];
    for (const job of jobs) {
      try {
        const order = Math.min(10000, base + job.i);
        const primary = isPrimary && job.i === 0;
        if (job.kind === "file") {
          const prepared = await prepareProductImage(job.file);
          if (prepared.type === "image/webp" && job.file.type !== "image/webp") converted += 1;
          const body = new FormData();
          body.append("file", prepared, prepared.name);
          if (variantId) body.append("variant_id", variantId);
          if (altText) body.append("alt_text", altText);
          body.append("sort_order", String(order));
          body.append("is_primary", String(primary));
          await apiRequest("/catalogue/products/" + productId + "/images/upload", { method: "POST", body });
        } else {
          await apiRequest("/catalogue/products/" + productId + "/images", {
            method: "POST",
            body: JSON.stringify({
              image_url: job.url, alt_text: altText || job.alt || null,
              variant_id: variantId ? Number(variantId) : null,
              sort_order: order, is_primary: primary,
            }),
          });
        }
        done += 1;
      } catch (e) { failed.push(job.label + ": " + (e.message || "failed")); }
    }
    if (done) {
      if (!failed.length) { setImageUrl(""); setImageFiles([]); setFileInputKey(k => k + 1); setPickedUrls([]); setAltText(""); setSortOrder("0"); setIsPrimary(false); }
      else if (imageFiles.length) {
        const failedNames = new Set(failed.map(f => f.split(": ")[0]));
        setImageFiles(prev => prev.filter(f => failedNames.has(f.name))); setFileInputKey(k => k + 1);
      }
      setMessage(done + " image" + (done > 1 ? "s" : "") + " added" + (converted ? " (" + converted + " converted to WebP)" : "") + ".");
      await loadImages(productId);
    }
    if (failed.length) setError(failed.length + " failed — " + failed.join("; "));
    setBusy(false);
  }

  const ImageForm = embedded ? "div" : "form";
  return <section className="sb-data-card">
    <h2>{embedded ? "Product & variant images" : "Product & variant images"}</h2>
    <p className="sb-muted">Add an image URL to the parent product or a specific variant. Each gallery can have one designated cover image. JPEG and PNG uploads are resized and converted to WebP automatically; existing WebP files stay unchanged and animated GIFs keep their animation.</p>
    {error && <p className="sb-alert" role="alert">{error}</p>}
    {message && <p className="sb-success" role="status">{message}</p>}
    {!embedded && <div className="sb-form-grid"><label>Product<select value={productId} onChange={e=>setProductId(e.target.value)}><option value="">Choose product</option>{products.map(p=><option key={p.id} value={p.id}>{p.name}</option>)}</select></label></div>}
    <ImageForm className="sb-form sb-form-inner" onSubmit={embedded ? undefined : submit}>
      <div className="sb-form-grid">
        <label className="sb-span-all">Image files — select one or many (JPEG/PNG converted to WebP; WebP and GIF supported; max 10 MB each)<input key={fileInputKey} type="file" multiple accept="image/jpeg,image/png,image/webp,image/gif" onChange={e=>{const files=Array.from(e.target.files||[]); setImageFiles(files); if(files.length){ setImageUrl(""); setPickedUrls([]); }}}/>{imageFiles.length>0 && <small className="sb-muted">{imageFiles.length} file{imageFiles.length>1?"s":""} selected</small>}</label>
        <div className="sb-span-all sb-media-choose"><button type="button" className="sb-row-action" onClick={openPicker}>Choose from already uploaded images</button>{pickedUrls.length>0 && <span className="sb-media-selected">{pickedUrls.slice(0,4).map(i=><img key={i.image_url} src={i.image_url} alt="" />)} {pickedUrls.length} existing selected <button type="button" className="sb-row-action" onClick={()=>setPickedUrls([])}>Clear</button></span>}</div>
        {pickerOpen && <div className="sb-span-all sb-media-picker" role="dialog" aria-label="Image library"><div className="sb-media-picker-head"><input type="search" placeholder="Search by product, name or file…" value={libQuery} onChange={e=>setLibQuery(e.target.value)} onKeyDown={e=>{ if(e.key==="Enter"){ e.preventDefault(); loadLibrary(libQuery,false);} }}/><button type="button" className="sb-row-action" onClick={()=>loadLibrary(libQuery,false)}>Search</button><button type="button" className="sb-row-action" onClick={()=>setPickerOpen(false)}>Cancel</button><button type="button" className="sb-primary" onClick={confirmPicked}>Use selected ({pickerSelection.length})</button></div>{libLoading && !library.length ? <p className="sb-muted">Loading images…</p> : library.length ? <div className="sb-media-grid">{library.map(item=>{const on=pickerSelection.some(i=>i.image_url===item.image_url); return <button type="button" key={item.image_url} aria-pressed={on} className={"sb-media-tile"+(on?" is-selected":"")} onClick={()=>togglePicked(item)} title={item.alt_text || item.image_url}><img src={item.image_url} alt={item.alt_text || ""} loading="lazy" onError={e=>{e.currentTarget.style.visibility="hidden";}}/><span>{on?"✓ ":""}{item.alt_text || "Image"}</span><small>{(item.product_names||[]).join(", ")}{item.use_count>1 ? " · used " + item.use_count + "×" : ""}</small></button>;})}</div> : <p className="sb-empty">No uploaded images found.</p>}{libHasMore && <button type="button" className="sb-row-action" disabled={libLoading} onClick={()=>loadLibrary(libQuery,true)}>{libLoading ? "Loading…" : "Load more"}</button>}</div>}
        <label className="sb-span-all">Or image URL<input type="url" maxLength="2048" value={imageUrl} disabled={imageFiles.length>0 || pickedUrls.length>0} onChange={e=>setImageUrl(e.target.value)} placeholder="https://…"/></label>
        <label>Alt text<input maxLength="300" value={altText} onChange={e=>setAltText(e.target.value)}/></label>
        <label>Variant (optional)<select value={variantId} onChange={e=>setVariantId(e.target.value)}><option value="">Product-level image</option>{variants.filter(v=>v.is_active!==false).map(v=><option key={v.id} value={v.id}>{variantOptionLabel(v)}</option>)}</select></label>
        <label>Sort order<input type="number" min="0" max="10000" value={sortOrder} onChange={e=>setSortOrder(e.target.value)}/></label>
        <label className="sb-check"><input type="checkbox" checked={isPrimary} onChange={e=>setIsPrimary(e.target.checked)}/> Set as main cover image</label>
      </div>
      <button className="sb-primary" disabled={busy || !productId || (!imageFiles.length && !pickedUrls.length && !imageUrl.trim())} type={embedded ? "button" : "submit"} onClick={embedded ? () => submit({ preventDefault: () => {} }) : undefined}>{busy ? "Saving…" : (imageFiles.length ? (imageFiles.length>1 ? "Upload " + imageFiles.length + " images" : "Upload image") : pickedUrls.length ? (pickedUrls.length>1 ? "Add " + pickedUrls.length + " selected images" : "Add selected image") : "Add image reference") + (variantId ? " for " + variantName(variants.find(v=>String(v.id)===String(variantId))) : "")}</button>
    </ImageForm>
    {images.length ? <div>{[{ id: "", title: "Product-level images (shown for every variant without its own image)", items: images.filter(i=>!i.variant_id) }, ...variants.map(v=>({ id: String(v.id), title: "Variant: " + variantName(v), items: images.filter(i=>String(i.variant_id)===String(v.id)) }))].filter(g=>g.id==="" ? g.items.length : true).map(g=><div key={g.id || "product"} className="sb-image-group"><h3 className="sb-image-group-title">{g.title}</h3>{g.items.length ? <div className="sb-image-grid">{g.items.map(image=><article className="sb-image-item" key={image.id}><img src={image.image_url} alt={image.alt_text || ""} loading="lazy" onError={e=>{e.currentTarget.style.display="none";}}/><div><strong>{image.alt_text || "Product image"}{image.is_primary ? " · Main cover" : ""}</strong><small>{image.variant_id ? "Variant image" : "Product-level"} · Order {image.sort_order}</small><a href={image.image_url} target="_blank" rel="noreferrer">Open image</a>{!image.is_primary && <button type="button" className="sb-row-action" disabled={busy} onClick={() => setPrimary(image)}>Make cover</button>}<button type="button" className="sb-row-action" disabled={busy} onClick={() => removeImage(image)}>Delete</button></div></article>)}</div> : <p className="sb-muted">No image yet for this variant. The shop shows the product-level image until you add one.</p>}</div>)}</div> : <p className="sb-empty">No images saved for this product.</p>}
  </section>;
}
