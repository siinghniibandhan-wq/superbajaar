import { useState } from "react";
import { isDuplicateOption, resolveColourInput, suggestColourName } from "./colourOptions.js";

const DEFAULT_HEX = "#4169E1";

export default function ColourOptionEditor({ existingOptions = [], onAdd, disabled = false, compact = false }) {
  const [hex, setHex] = useState(DEFAULT_HEX);
  const [query, setQuery] = useState("");
  const [suggestedName, setSuggestedName] = useState(suggestColourName(DEFAULT_HEX));
  const [name, setName] = useState(suggestColourName(DEFAULT_HEX));
  const [renaming, setRenaming] = useState(false);
  const [unrecognised, setUnrecognised] = useState(false);
  const [matchedBy, setMatchedBy] = useState("");
  const [confirming, setConfirming] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  function applyColour(nextHex, nextName, how) {
    setHex(nextHex);
    setSuggestedName(nextName);
    setName(nextName);
    setRenaming(false);
    setUnrecognised(false);
    setMatchedBy(how);
    setConfirming(false);
    setError("");
  }

  // 1) Colour picker
  function choosePicker(value) {
    const next = value.toUpperCase();
    setQuery(next);
    applyColour(next, suggestColourName(next), "picker");
  }

  // 2) Typed HEX code or colour name
  function typeColour(text) {
    setQuery(text);
    setConfirming(false);
    setError("");
    if (!text.trim()) { setUnrecognised(false); setMatchedBy(""); return; }
    const resolved = resolveColourInput(text);
    if (resolved) applyColour(resolved.hex, resolved.name, resolved.kind);
    else { setUnrecognised(true); setMatchedBy(""); }
  }

  function startConfirm() {
    const trimmed = name.trim();
    if (unrecognised) { setError("This colour is not recognised. Pick a colour or type a HEX code like #1E90FF."); return; }
    if (!trimmed) { setError("Enter a colour name."); return; }
    if (isDuplicateOption(existingOptions, { name: trimmed, hex }, "colour")) {
      setError('"' + trimmed + '" or this HEX colour already exists in this attribute. Choose another colour.');
      return;
    }
    setError("");
    setConfirming(true);
  }

  async function confirmAdd() {
    setBusy(true);
    try {
      await onAdd({ name: name.trim(), hex: hex.toUpperCase() });
      setQuery("");
      applyColour(DEFAULT_HEX, suggestColourName(DEFAULT_HEX), "");
    } catch (e) {
      setConfirming(false);
      setError(e.message || "Unable to add this colour.");
    } finally { setBusy(false); }
  }

  const hint = unrecognised
    ? 'We don\u2019t recognise "' + query.trim() + '". Pick a colour or type a HEX code like #1E90FF.'
    : matchedBy === "name" ? "Matched colour name \u2192 " + hex
    : matchedBy === "hex" ? "HEX code recognised \u2192 suggested name below"
    : "";

  return <div className={"sb-colour-editor" + (compact ? " is-compact" : "")}>
    <label className="sb-colour-picker-label">Pick colour <input type="color" value={hex} disabled={disabled || busy} onChange={event => choosePicker(event.target.value)} /></label>
    <span className="sb-colour-preview" style={{ backgroundColor: hex }} aria-label={"Selected colour " + hex} />
    <label className="sb-colour-text">Or type a colour name / HEX code
      <input
        type="text"
        value={query}
        placeholder="e.g. blue or #1E90FF"
        autoComplete="off"
        spellCheck={false}
        disabled={disabled || busy}
        aria-invalid={unrecognised}
        onChange={event => typeColour(event.target.value)}
        onKeyDown={event => { if (event.key === "Enter") { event.preventDefault(); if (!confirming) startConfirm(); } }}
      />
    </label>
    {hint && <p className={"sb-colour-hint" + (unrecognised ? " is-warning" : "")}>{hint}</p>}
    <div className="sb-colour-name-area">
      <strong>{renaming ? "Rename colour" : "Suggested name: " + suggestedName}</strong>
      {renaming ? <input aria-label="Colour name" value={name} disabled={disabled || busy} onChange={event => { setName(event.target.value); setConfirming(false); }} /> : <small>{name} · {hex}</small>}
      {!confirming && <div className="sb-colour-actions">
        {!renaming && <button type="button" className="sb-row-action" disabled={disabled || busy} onClick={() => { setName(suggestedName); setRenaming(false); }}>Keep suggested name</button>}
        <button type="button" className="sb-row-action" disabled={disabled || busy} onClick={() => { if (renaming) { setName(suggestedName); setRenaming(false); } else { setRenaming(true); } }}>{renaming ? "Use suggested name" : "Rename colour"}</button>
        <button type="button" className="sb-secondary" disabled={disabled || busy || !name.trim() || unrecognised} onClick={startConfirm}>Add colour</button>
      </div>}
    </div>
    {confirming && <div className="sb-colour-confirm" role="group" aria-label="Confirm new colour">
      <span className="sb-colour-preview" style={{ backgroundColor: hex }} aria-hidden="true" />
      <div><strong>Add “{name.trim()}” ({hex}) to this attribute?</strong><small>Check the colour and name before it is created.</small></div>
      <div className="sb-colour-actions">
        <button type="button" className="sb-secondary" disabled={disabled || busy} onClick={confirmAdd}>{busy ? "Adding…" : "Yes, add colour"}</button>
        <button type="button" className="sb-row-action" disabled={busy} onClick={() => setConfirming(false)}>Go back</button>
      </div>
    </div>}
    {error && <p className="sb-alert" role="alert">{error}</p>}
  </div>;
}
