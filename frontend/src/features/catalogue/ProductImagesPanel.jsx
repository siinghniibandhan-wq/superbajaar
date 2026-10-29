import { useEffect, useState } from "react";
import { apiRequest } from "../../services/api.js";

export default function ProductImagesPanel({ products }) {
  const [productId, setProductId] = useState("");
  const [variantId, setVariantId] = useState("");
  const [variants, setVariants] = useState([]);
  const [images, setImages] = useState([]);
  const [imageUrl, setImageUrl] = useState("");
  const [selectedFile, setSelectedFile] = useState(null);
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
      if (selectedFile) {
        const formData = new FormData();
        formData.append("file", selectedFile);
        if (variantId) formData.append("variant_id", variantId);
        if (altText) formData.append("alt_text", altText);
        formData.append("sort_order", sortOrder);
        await apiRequest("/catalogue/products/" + productId + "/images/upload", {
          method: "POST",
          body: formData,
        });
        setMessage("Image uploaded and linked to " + (variantId ? "the selected variant." : "the product."));
      } else {
        if (!imageUrl.trim()) throw new Error("Choose an image file or enter an image URL.");
        await apiRequest("/catalogue/products/" + productId + "/images", {
          method: "POST",
          body: JSON.stringify({
            image_url: imageUrl.trim(), alt_text: altText || null,
            variant_id: variantId ? Number(variantId) : null,
            sort_order: Number(sortOrder),
          }),
        });
        setMessage("Image reference saved.");
      }
      setImageUrl(""); setSelectedFile(null); setAltText(""); setVariantId(""); setSortOrder("0");
      const fileInput = document.getElementById("sb-catalogue-image-file");
      if (fileInput) fileInput.value = "";
      await loadImages(productId);
    } catch (e) { setError(e.message || "Unable to save image reference."); }
    finally { setBusy(false); }
  }

  return <section className="sb-data-card">
    <h2>Product & variant images</h2>
    <p className="sb-muted">Upload a JPEG, PNG or WebP file (maximum 10 MB), or save an externally hosted image URL. Uploaded files are linked to the selected product or variant.</p>
    {error && <p className="sb-alert" role="alert">{error}</p>}
    {message && <p className="sb-success" role="status">{message}</p>}
    <div className="sb-form-grid"><label>Product<select value={productId} onChange={e=>setProductId(e.target.value)}><option value="">Choose product</option>{products.map(p=><option key={p.id} value={p.id}>{p.name}</option>)}</select></label></div>
    <form className="sb-form sb-form-inner" onSubmit={submit}>
      <div className="sb-form-grid">
        <label className="sb-span-all">Upload image file<input id="sb-catalogue-image-file" type="file" accept="image/jpeg,image/png,image/webp" onChange={e=>{setSelectedFile(e.target.files?.[0] || null);if(e.target.files?.[0])setImageUrl("");}}/><small className="sb-muted">JPEG, PNG or WebP · up to 10 MB</small></label>
        <label className="sb-span-all">Or image URL<input type="url" maxLength="2048" value={imageUrl} onChange={e=>{setImageUrl(e.target.value);if(e.target.value)setSelectedFile(null);}} placeholder="https://…"/></label>
        {selectedFile && <p className="sb-muted sb-span-all">Selected: {selectedFile.name} ({Math.ceil(selectedFile.size / 1024)} KB)</p>}
        <label>Alt text<input maxLength="300" value={altText} onChange={e=>setAltText(e.target.value)}/></label>
        <label>Variant (optional)<select value={variantId} onChange={e=>setVariantId(e.target.value)}><option value="">Product-level image</option>{variants.map(v=><option key={v.id} value={v.id}>{v.sku}</option>)}</select></label>
        <label>Sort order<input type="number" min="0" max="10000" value={sortOrder} onChange={e=>setSortOrder(e.target.value)}/></label>
      </div>
      <button className="sb-primary" disabled={busy || !productId} type="submit">{busy ? "Saving…" : selectedFile ? "Upload image" : "Add image reference"}</button>
    </form>
    {images.length ? <div className="sb-image-grid">{images.map(image=><article className="sb-image-item" key={image.id}><img src={image.image_url} alt={image.alt_text || ""} loading="lazy" onError={e=>{e.currentTarget.style.display="none";}}/><div><strong>{image.alt_text || "Product image"}</strong><small>{image.variant_id ? "Variant #" + image.variant_id : "Product-level"} · Order {image.sort_order}</small><a href={image.image_url} target="_blank" rel="noreferrer">Open image</a></div></article>)}</div> : <p className="sb-empty">No images saved for this product.</p>}
  </section>;
}
