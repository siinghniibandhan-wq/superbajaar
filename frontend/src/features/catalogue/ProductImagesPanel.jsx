import { useEffect, useState } from "react";
import { apiRequest } from "../../services/api.js";

export default function ProductImagesPanel({ products = [], initialProductId = "", embedded = false }) {
  const [productId, setProductId] = useState(initialProductId ? String(initialProductId) : "");
  const [variantId, setVariantId] = useState("");
  const [variants, setVariants] = useState([]);
  const [images, setImages] = useState([]);
  const [imageUrl, setImageUrl] = useState("");
  const [altText, setAltText] = useState("");
  const [sortOrder, setSortOrder] = useState("0");
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");
  const [busy, setBusy] = useState(false);

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

  async function submit(event) {
    event.preventDefault(); setBusy(true); setError(""); setMessage("");
    try {
      await apiRequest("/catalogue/products/" + productId + "/images", {
        method: "POST",
        body: JSON.stringify({
          image_url: imageUrl, alt_text: altText || null,
          variant_id: variantId ? Number(variantId) : null,
          sort_order: Number(sortOrder),
        }),
      });
      setImageUrl(""); setAltText(""); setVariantId(""); setSortOrder("0");
      setMessage("Image reference saved."); await loadImages(productId);
    } catch (e) { setError(e.message || "Unable to save image reference."); }
    finally { setBusy(false); }
  }

  const ImageForm = embedded ? "div" : "form";
  return <section className="sb-data-card">
    <h2>{embedded ? "Product & variant images" : "Product & variant images"}</h2>
    <p className="sb-muted">Add an HTTPS/HTTP image URL. This stores image metadata only; upload/storage hosting is not configured yet.</p>
    {error && <p className="sb-alert" role="alert">{error}</p>}
    {message && <p className="sb-success" role="status">{message}</p>}
    {!embedded && <div className="sb-form-grid"><label>Product<select value={productId} onChange={e=>setProductId(e.target.value)}><option value="">Choose product</option>{products.map(p=><option key={p.id} value={p.id}>{p.name}</option>)}</select></label></div>}
    <ImageForm className="sb-form sb-form-inner" onSubmit={embedded ? undefined : submit}>
      <div className="sb-form-grid">
        <label className="sb-span-all">Image URL<input type="url" required maxLength="2048" value={imageUrl} onChange={e=>setImageUrl(e.target.value)} placeholder="https://…"/></label>
        <label>Alt text<input maxLength="300" value={altText} onChange={e=>setAltText(e.target.value)}/></label>
        <label>Variant (optional)<select value={variantId} onChange={e=>setVariantId(e.target.value)}><option value="">Product-level image</option>{variants.map(v=><option key={v.id} value={v.id}>{v.sku}</option>)}</select></label>
        <label>Sort order<input type="number" min="0" max="10000" value={sortOrder} onChange={e=>setSortOrder(e.target.value)}/></label>
      </div>
      <button className="sb-primary" disabled={busy || !productId} type={embedded ? "button" : "submit"} onClick={embedded ? () => submit({ preventDefault: () => {} }) : undefined}>{busy ? "Saving…" : "Add image reference"}</button>
    </ImageForm>
    {images.length ? <div className="sb-image-grid">{images.map(image=><article className="sb-image-item" key={image.id}><img src={image.image_url} alt={image.alt_text || ""} loading="lazy" onError={e=>{e.currentTarget.style.display="none";}}/><div><strong>{image.alt_text || "Product image"}</strong><small>{image.variant_id ? "Variant #" + image.variant_id : "Product-level"} · Order {image.sort_order}</small><a href={image.image_url} target="_blank" rel="noreferrer">Open image</a></div></article>)}</div> : <p className="sb-empty">No images saved for this product.</p>}
  </section>;
}
