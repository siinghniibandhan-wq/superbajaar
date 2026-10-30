import { useState } from "react";
import { isDuplicateOption, suggestColourName } from "./colourOptions.js";

export default function ColourOptionEditor({ existingOptions = [], onAdd, disabled = false, compact = false }) {
  const [hex, setHex] = useState("#4169E1");
  const [suggestedName, setSuggestedName] = useState("Royal Blue");
  const [name, setName] = useState("Royal Blue");
  const [renaming, setRenaming] = useState(false);
  const [error, setError] = useState("");

  function chooseHex(value) {
    setHex(value.toUpperCase());
    const suggestion = suggestColourName(value);
    setSuggestedName(suggestion);
    setName(suggestion);
    setRenaming(false);
    setError("");
  }

  async function add() {
    const option = { name: name.trim(), hex: hex.toUpperCase() };
    if (!option.name) { setError("Enter a colour name."); return; }
    if (isDuplicateOption(existingOptions, option, "colour")) {
      setError('"' + option.name + '" or this HEX colour already exists in this attribute. Choose another colour.');
      return;
    }
    try {
      await onAdd(option);
      setHex("#4169E1");
      setSuggestedName("Royal Blue");
      setName("Royal Blue");
      setRenaming(false);
      setError("");
    } catch (e) {
      setError(e.message || "Unable to add this colour.");
    }
  }

  return <div className={"sb-colour-editor" + (compact ? " is-compact" : "")}>
    <label className="sb-colour-picker-label">Choose colour <input type="color" value={hex} disabled={disabled} onChange={event => chooseHex(event.target.value)} /></label>
    <span className="sb-colour-preview" style={{ backgroundColor: hex }} aria-label={"Selected colour " + hex} />
    <div className="sb-colour-name-area">
      <strong>{renaming ? "Rename colour" : "Suggested name: " + suggestedName}</strong>
      {renaming ? <input aria-label="Colour name" value={name} disabled={disabled} onChange={event => setName(event.target.value)} /> : <small>{name} · {hex}</small>}
      <div className="sb-colour-actions">
        {!renaming && <button type="button" className="sb-row-action" disabled={disabled} onClick={() => { setName(suggestedName); setRenaming(false); }}>Keep suggested name</button>}
        <button type="button" className="sb-row-action" disabled={disabled} onClick={() => { if (renaming) { setName(suggestedName); setRenaming(false); } else { setRenaming(true); } }}>{renaming ? "Use suggested name" : "Rename colour"}</button>
        <button type="button" className="sb-secondary" disabled={disabled || !name.trim()} onClick={add}>Add colour</button>
      </div>
    </div>
    {error && <p className="sb-alert" role="alert">{error}</p>}
  </div>;
}
