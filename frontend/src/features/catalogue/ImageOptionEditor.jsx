import { useState } from "react";
import { apiRequest } from "../../services/api.js";
import { prepareProductImage } from "./productImageFormat.js";
import ImageLibraryPicker from "./ImageLibraryPicker.jsx";

// Adds values to an Image-type attribute: upload a file, pick one already uploaded, or paste a link.
// onAdd(url) must return a promise; it throws (rejects) with a readable message on a duplicate.
export default function ImageOptionEditor({ onAdd, disabled = false }) {
  const [url, setUrl] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [picking, setPicking] = useState(false);
  const [inputKey, setInputKey] = useState(0);

  async function addMany(urls) {
    setBusy(true); setError("");
    const failures = [];
    for (const item of urls) {
      try { await onAdd(item); } catch (e) { failures.push(e.message || "Unable to add image."); }
    }
    if (failures.length) setError([...new Set(failures)].join(" "));
    setBusy(false);
  }
  async function upload(files) {
    const list = Array.from(files || []);
    if (!list.length) return;
    setBusy(true); setError("");
    const uploaded = [];
    try {
      for (const file of list) {
        const prepared = await prepareProductImage(file);
        const body = new FormData();
        body.append("file", prepared, prepared.name || file.name);
        const result = await apiRequest("/catalogue/attribute-images/upload", { method: "POST", body });
        uploaded.push(result.image_url);
      }
    } catch (e) { setError(e.message || "Image upload failed."); }
    setInputKey(k => k + 1);
    setBusy(false);
    if (uploaded.length) await addMany(uploaded);
  }
  const off = disabled || busy;

  return <div className="sb-image-option-editor">
    <div className="sb-image-option-row">
      <label className="sb-image-option-file">Upload image(s)
        <input key={inputKey} type="file" accept="image/jpeg,image/png,image/webp,image/gif" multiple disabled={off} onChange={e => upload(e.target.files)} />
      </label>
      <button type="button" className="sb-row-action" disabled={off} onClick={() => setPicking(true)}>Choose from uploaded images</button>
    </div>
    <div className="sb-add-option">
      <input aria-label="Image link" value={url} placeholder="Or paste an image link (https://…)" disabled={off} onChange={e => setUrl(e.target.value)} />
      <button type="button" className="sb-secondary" disabled={off || !url.trim()} onClick={async () => { await addMany([url.trim()]); setUrl(""); }}>Add value</button>
    </div>
    {busy && <small className="sb-muted">Working…</small>}
    {error && <p className="sb-error" role="alert">{error}</p>}
    {picking && <ImageLibraryPicker confirmLabel="Add selected" onCancel={() => setPicking(false)} onConfirm={async selection => { setPicking(false); await addMany(selection.map(i => i.image_url)); }} />}
  </div>;
}
