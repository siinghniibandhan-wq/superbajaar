import { useEffect, useMemo, useState } from "react";
import { apiRequest } from "../../services/api.js";

const ACCEPTED_IMAGE_TYPES = "image/jpeg,image/png,image/webp,image/gif";

export default function ProductImagesPanel({ products = [], initialProductId = "", embedded = false }) {
  const [productId, setProductId] = useState(initialProductId ? String(initialProductId) : "");
  const [variants, setVariants] = useState([]);
  const [images, setImages] = useState([]);
  const [drafts, setDrafts] = useState({});
  const [busyKey, setBusyKey] = useState("");
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");

  useEffect(() => {
    if (initialProductId && String(initialProductId) !== String(productId)) setProductId(String(initialProductId));
  }, [initialProductId, productId]);

  async function loadImages(id = productId) {
    if (!id) { setImages([]); return; }
    const result = await apiRequest("/catalogue/products/" + id + "/images");
    setImages(result.items || []);
  }

  useEffect(() => {
    let cancelled = false;
    setVariants([]);
    setImages([]);
    setDrafts({});
    setError("");
    setMessage("");
    if (!productId) return () => { cancelled = true; };
    Promise.all([
      apiRequest("/catalogue/products/" + productId + "/variants?limit=500"),
      apiRequest("/catalogue/products/" + productId + "/images"),
    ]).then(([variantResult, imageResult]) => {
      if (cancelled) return;
      setVariants((variantResult.items || []).filter(item => item.is_active !== false));
      setImages(imageResult.items || []);
    }).catch(e => {
      if (!cancelled) setError(e.message || "Unable to load product variants and images.");
    });
    return () => { cancelled = true; };
  }, [productId]);

  const galleries = useMemo(() => [
    { key: "product", variantId: null, title: "Main product image", subtitle: "Used when a selected variant has no image of its own." },
    ...variants.map(variant => ({
      key: String(variant.id),
      variantId: Number(variant.id),
      title: Object.entries(variant.attributes || {}).map(([key, value]) => key.replace(/_/g, " ") + ": " + (Array.isArray(value) ? value.join(", ") : value)).join(" · ") || variant.sku,
      subtitle: variant.sku,
    })),
  ], [variants]);

  function updateDraft(key, patch) {
    setDrafts(old => ({ ...old, [key]: { ...(old[key] || {}), ...patch } }));
  }

  async function saveImage(event, gallery) {
    event.preventDefault();
    const draft = drafts[gallery.key] || {};
    if (!draft.file && !String(draft.url || "").trim()) {
      setError("Choose an image file or enter an image URL.");
      return;
    }
    setBusyKey(gallery.key);
    setError("");
    setMessage("");
    try {
      if (draft.file) {
        const body = new FormData();
        body.append("file", draft.file);
        if (gallery.variantId !== null) body.append("variant_id", String(gallery.variantId));
        body.append("alt_text", draft.altText || gallery.title);
        body.append("sort_order", "0");
        body.append("is_primary", "true");
        await apiRequest("/catalogue/products/" + productId + "/images/upload", { method: "POST", body });
      } else {
        await apiRequest("/catalogue/products/" + productId + "/images", {
          method: "POST",
          body: JSON.stringify({
            image_url: String(draft.url).trim(),
            alt_text: draft.altText || gallery.title,
            variant_id: gallery.variantId,
            sort_order: 0,
            is_primary: true,
          }),
        });
      }
      setDrafts(old => ({ ...old, [gallery.key]: {} }));
      await loadImages(productId);
      setMessage((gallery.variantId === null ? "Main product image" : "Variant image") + " saved successfully.");
    } catch (e) {
      setError(e.message || "Unable to save this image.");
    } finally {
      setBusyKey("");
    }
  }

  async function setPrimary(image) {
    const key = image.variant_id == null ? "product" : String(image.variant_id);
    setBusyKey(key);
    setError("");
    setMessage("");
    try {
      await apiRequest("/catalogue/products/" + productId + "/images/" + image.id + "/primary", { method: "PUT" });
      await loadImages(productId);
      setMessage("Image selection updated.");
    } catch (e) {
      setError(e.message || "Unable to update the selected image.");
    } finally {
      setBusyKey("");
    }
  }

  function primaryImage(gallery) {
    const group = images.filter(image => (image.variant_id == null ? null : Number(image.variant_id)) === gallery.variantId);
    return group.find(image => image.is_primary) || group[0] || null;
  }

  const ImageForm = embedded ? "div" : "form";
  return <section className="sb-data-card sb-product-media-manager">
    <div className="sb-data-heading">
      <div>
        <h2>Product &amp; variant images</h2>
        <p className="sb-muted">Upload an image from your device or use an existing image URL. Each variant has its own independent primary image.</p>
      </div>
    </div>
    {error && <p className="sb-alert" role="alert">{error}</p>}
    {message && <p className="sb-success" role="status">{message}</p>}
    {!embedded && <div className="sb-form-grid sb-media-product-select"><label>Product<select value={productId} onChange={e => setProductId(e.target.value)}><option value="">Choose product</option>{products.map(p => <option key={p.id} value={p.id}>{p.name}</option>)}</select></label></div>}
    {!productId ? <p className="sb-empty">Choose a product to manage its images.</p> : <>
      <div className="sb-media-gallery-list">
        {galleries.map(gallery => {
          const current = primaryImage(gallery);
          const draft = drafts[gallery.key] || {};
          const saving = busyKey === gallery.key;
          const groupImages = images.filter(image => (image.variant_id == null ? null : Number(image.variant_id)) === gallery.variantId);
          return <article className="sb-media-gallery-card" key={gallery.key}>
            <div className="sb-media-gallery-heading">
              <div><strong>{gallery.variantId === null ? gallery.title : "Variant · " + gallery.title}</strong><small>{gallery.subtitle}</small></div>
              {current?.is_primary && <span className="sb-media-primary-pill">Primary</span>}
            </div>
            <div className="sb-media-gallery-body">
              <div className="sb-media-current">
                {current ? <img src={current.image_url} alt={current.alt_text || gallery.title} loading="lazy" /> : <div className="sb-media-placeholder"><span>＋</span><small>No image added</small></div>}
                {current && <small>{current.alt_text || "Saved image"}</small>}
              </div>
              <ImageForm className="sb-media-upload-form" onSubmit={event => saveImage(event, gallery)}>
                <label className="sb-media-file-label">Upload from device
                  <input key={gallery.key + "-" + (draft.file ? draft.file.name : "empty")} type="file" accept={ACCEPTED_IMAGE_TYPES} onChange={e => updateDraft(gallery.key, { file: e.target.files?.[0] || null, url: "" })} />
                </label>
                {draft.file && <small className="sb-media-file-name">{draft.file.name}</small>}
                <label>Or use image URL
                  <input type="url" maxLength="2048" value={draft.url || ""} disabled={Boolean(draft.file)} onChange={e => updateDraft(gallery.key, { url: e.target.value, file: null })} placeholder="https://example.com/image.jpg" />
                </label>
                <label>Alt text (optional)
                  <input maxLength="300" value={draft.altText || ""} onChange={e => updateDraft(gallery.key, { altText: e.target.value })} placeholder="Describe the image" />
                </label>
                <button className="sb-primary" type={embedded ? "button" : "submit"} onClick={embedded ? event => saveImage(event, gallery) : undefined} disabled={Boolean(busyKey) || (!draft.file && !String(draft.url || "").trim())}>{saving ? "Saving…" : draft.file ? "Upload & set as primary" : "Save URL as primary"}</button>
              </ImageForm>
            </div>
            {groupImages.length > 1 && <div className="sb-media-existing-list"><small>Other saved images</small>{groupImages.filter(image => image.id !== current?.id).map(image => <div className="sb-media-existing-item" key={image.id}><img src={image.image_url} alt={image.alt_text || "Saved product image"} loading="lazy" /><span>{image.alt_text || "Image"}{image.is_primary ? " · Primary" : ""}</span>{!image.is_primary && <button type="button" className="sb-row-action" disabled={Boolean(busyKey)} onClick={() => setPrimary(image)}>Make primary</button>}</div>)}</div>}
          </article>;
        })}
      </div>
      {!variants.length && <p className="sb-muted">No active variants are configured. The main product image can still be added here.</p>}
    </>}
  </section>;
}
