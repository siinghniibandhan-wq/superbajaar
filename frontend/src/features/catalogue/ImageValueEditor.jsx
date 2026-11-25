import { useState } from "react";
import { apiRequest } from "../../services/api.js";
import { prepareProductImage } from "./productImageFormat.js";
import ImageLibraryPicker from "./ImageLibraryPicker.jsx";
import { normalizeImageOption } from "./imageOptions.js";

// Edits ONE Image value: fix its name (e.g. "Blak" -> "Black") and/or replace its picture.
// onSave({ name, image }) returns a promise and rejects with a readable message on failure.
export default function ImageValueEditor({ option, onSave, onCancel, disabled = false, note = "" }) {
  const original = normalizeImageOption(option);
  const [name, setName] = useState(original.name);
  const [image, setImage] = useState(original.image);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [picking, setPicking] = useState(false);
  const [inputKey, setInputKey] = useState(0);

  async function upload(files) {
    const file = Array.from(files || [])[0];
    if (!file) return;
    setBusy(true); setError("");
    try {
      const prepared = await prepareProductImage(file);
      const body = new FormData();
      body.append("file", prepared, prepared.name || file.name);
      const result = await apiRequest("/catalogue/attribute-images/upload", { method: "POST", body });
      setImage(result.image_url);
    } catch (e) { setError(e.message || "Image upload failed."); }
    setInputKey(k => k + 1);
    setBusy(false);
  }
  async function save() {
    const trimmed = name.trim();
    if (!trimmed) { setError("Give this value a name."); return; }
    if (!image) { setError("Choose a picture for this value."); return; }
    setBusy(true); setError("");
    try { await onSave({ name: trimmed, image }); }
    catch (e) { setError(e.message || "Unable to save this value."); setBusy(false); }
  }
  const off = disabled || busy;
  const changed = name.trim() !== original.name || image !== original.image;

  return <div className="sb-image-value-editor" role="group" aria-label={"Edit value " + original.name}>
    <div className="sb-image-value-editor-row">
      {image && <img className="sb-image-thumb" src={image} alt="" />}
      <input aria-label="Value name" value={name} maxLength={120} placeholder="Name, e.g. Black" disabled={off} onChange={e => setName(e.target.value)} />
    </div>
    <div className="sb-image-value-editor-row">
      <label className="sb-image-option-file">Change picture
        <input key={inputKey} type="file" accept="image/jpeg,image/png,image/webp,image/gif" disabled={off} onChange={e => upload(e.target.files)} />
      </label>
      <button type="button" className="sb-row-action" disabled={off} onClick={() => setPicking(true)}>Choose from uploaded images</button>
    </div>
    {note && <small className="sb-muted">{note}</small>}
    {error && <p className="sb-error" role="alert">{error}</p>}
    <div className="sb-image-value-editor-row">
      <button type="button" className="sb-primary" disabled={off || !changed} onClick={save}>{busy ? "Saving…" : "Save changes"}</button>
      <button type="button" className="sb-secondary" disabled={busy} onClick={onCancel}>Cancel</button>
    </div>
    {picking && <ImageLibraryPicker multiple={false} confirmLabel="Use this picture" onCancel={() => setPicking(false)} onConfirm={selection => { setPicking(false); if (selection[0]?.image_url) setImage(selection[0].image_url); }} />}
  </div>;
}
