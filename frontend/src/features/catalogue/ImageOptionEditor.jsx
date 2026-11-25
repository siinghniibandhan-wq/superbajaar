import { useState } from "react";
import { apiRequest } from "../../services/api.js";
import { prepareProductImage } from "./productImageFormat.js";
import ImageLibraryPicker from "./ImageLibraryPicker.jsx";
import { suggestImageName } from "./imageOptions.js";

// Adds values to an Image-type attribute. Choose pictures (upload, library or link), give each one
// a name (e.g. "Black", "Floral"), then add. onAdd({ name, image }) returns a promise and rejects
// with a readable message on a duplicate.
export default function ImageOptionEditor({ onAdd, disabled = false }) {
  const [url, setUrl] = useState("");
  const [pending, setPending] = useState([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [picking, setPicking] = useState(false);
  const [inputKey, setInputKey] = useState(0);

  function stage(items) {
    setPending(old => {
      const known = new Set(old.map(i => i.image));
      return [...old, ...items.filter(i => i.image && !known.has(i.image))];
    });
  }
  async function upload(files) {
    const list = Array.from(files || []);
    if (!list.length) return;
    setBusy(true); setError("");
    const staged = [];
    try {
      for (const file of list) {
        const prepared = await prepareProductImage(file);
        const body = new FormData();
        body.append("file", prepared, prepared.name || file.name);
        const result = await apiRequest("/catalogue/attribute-images/upload", { method: "POST", body });
        staged.push({ image: result.image_url, name: suggestImageName(file.name) });
      }
    } catch (e) { setError(e.message || "Image upload failed."); }
    stage(staged);
    setInputKey(k => k + 1);
    setBusy(false);
  }
  function addLink() {
    const link = url.trim();
    if (!link) return;
    stage([{ image: link, name: suggestImageName(link) }]);
    setUrl("");
  }
  const setName = (index, name) => setPending(old => old.map((item, i) => i === index ? { ...item, name } : item));
  const drop = index => setPending(old => old.filter((_, i) => i !== index));
  const ready = pending.length > 0 && pending.every(item => item.name.trim());

  async function addAll() {
    setBusy(true); setError("");
    const failed = []; const messages = [];
    for (const item of pending) {
      try { await onAdd({ name: item.name.trim(), image: item.image }); }
      catch (e) { failed.push(item); messages.push(e.message || "Unable to add value."); }
    }
    setPending(failed);
    if (messages.length) setError([...new Set(messages)].join(" "));
    setBusy(false);
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
      <input aria-label="Image link" value={url} placeholder="Or paste an image link (https://…)" disabled={off} onChange={e => setUrl(e.target.value)} onKeyDown={e => { if (e.key === "Enter") { e.preventDefault(); addLink(); } }} />
      <button type="button" className="sb-secondary" disabled={off || !url.trim()} onClick={addLink}>Use link</button>
    </div>
    {pending.length > 0 && <div className="sb-image-pending">
      <small className="sb-muted">Name each picture (for example Black, Pink, Floral). The name is what customers and variants see.</small>
      {pending.map((item, index) => <div className="sb-image-pending-row" key={item.image}>
        <img className="sb-image-thumb" src={item.image} alt="" />
        <input aria-label="Value name" value={item.name} maxLength={120} placeholder="Name, e.g. Black" disabled={off} onChange={e => setName(index, e.target.value)} />
        <button type="button" className="sb-row-action" disabled={off} aria-label="Discard this picture" onClick={() => drop(index)}>×</button>
      </div>)}
      <button type="button" className="sb-primary" disabled={off || !ready} onClick={addAll}>Add {pending.length} value{pending.length > 1 ? "s" : ""}</button>
    </div>}
    {busy && <small className="sb-muted">Working…</small>}
    {error && <p className="sb-error" role="alert">{error}</p>}
    {picking && <ImageLibraryPicker confirmLabel="Use selected" onCancel={() => setPicking(false)} onConfirm={selection => { setPicking(false); stage(selection.map(i => ({ image: i.image_url, name: suggestImageName(i.alt_text || "") }))); }} />}
  </div>;
}
