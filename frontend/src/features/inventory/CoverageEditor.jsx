import { useEffect, useState } from "react";
import { apiRequest } from "../../services/api.js";

export const INDIAN_STATES = [
  "Andaman and Nicobar Islands", "Andhra Pradesh", "Arunachal Pradesh", "Assam", "Bihar", "Chandigarh", "Chhattisgarh",
  "Dadra and Nagar Haveli and Daman and Diu", "Delhi", "Goa", "Gujarat", "Haryana", "Himachal Pradesh", "Jammu and Kashmir",
  "Jharkhand", "Karnataka", "Kerala", "Ladakh", "Lakshadweep", "Madhya Pradesh", "Maharashtra", "Manipur", "Meghalaya",
  "Mizoram", "Nagaland", "Odisha", "Puducherry", "Punjab", "Rajasthan", "Sikkim", "Tamil Nadu", "Telangana", "Tripura",
  "Uttar Pradesh", "Uttarakhand", "West Bengal",
];

export const emptyCoverage = () => ({ states: [], districts: [], pins: "" });

export function parsePins(text) {
  return String(text || "").split(/[\s,;]+/).map(pin => pin.trim()).filter(Boolean);
}

export function coverageSummary({ states, districts, pins }) {
  const pinList = parsePins(pins);
  if (pinList.length) return "Serves only these " + pinList.length + " PIN code" + (pinList.length === 1 ? "" : "s") + ".";
  if (districts.length) return "Serves every PIN in: " + districts.join(", ") + (states.length ? " (" + states.join(", ") + ")" : "") + ".";
  if (states.length) return "Serves every PIN in: " + states.join(", ") + ".";
  return "No area selected.";
}

/** Step-wise coverage picker: 1) States  2) optional Districts  3) optional PIN codes (narrows to only those PINs). */
export default function CoverageEditor({ title, value, onChange, hint }) {
  const [stateToPick, setStateToPick] = useState("");
  const [districtDraft, setDistrictDraft] = useState("");
  const [suggestions, setSuggestions] = useState([]);
  const listId = "districts-" + title.replace(/\W+/g, "-").toLowerCase();
  const set = patch => onChange({ ...value, ...patch });

  useEffect(() => {
    let live = true;
    if (!value.states.length) { setSuggestions([]); return undefined; }
    Promise.all(value.states.map(state => apiRequest("/delivery/regions/districts?state=" + encodeURIComponent(state)).catch(() => ({ districts: [] }))))
      .then(results => { if (live) setSuggestions([...new Set(results.flatMap(r => r.districts || []))]); });
    return () => { live = false; };
  }, [value.states.join("|")]);

  const addState = () => { if (stateToPick && !value.states.includes(stateToPick)) set({ states: [...value.states, stateToPick] }); setStateToPick(""); };
  const addDistrict = () => {
    const name = districtDraft.trim();
    if (name && !value.districts.some(d => d.toLowerCase() === name.toLowerCase())) set({ districts: [...value.districts, name] });
    setDistrictDraft("");
  };

  return <fieldset className="sb-span-all sb-coverage">
    <legend>{title}</legend>
    {hint && <p className="sb-muted">{hint}</p>}
    <div className="sb-form-grid">
      <div className="sb-span-all">
        <strong>Step 1 · States</strong>
        <div className="sb-chip-row">{value.states.map(state => <span className="sb-chip" key={state}>{state} <button type="button" aria-label={"Remove " + state} onClick={() => set({ states: value.states.filter(x => x !== state) })}>×</button></span>)}</div>
        <div className="sb-inline-row">
          <select value={stateToPick} onChange={e => setStateToPick(e.target.value)} aria-label="Add a state">
            <option value="">Select a state…</option>
            {INDIAN_STATES.filter(state => !value.states.includes(state)).map(state => <option key={state} value={state}>{state}</option>)}
          </select>
          <button type="button" className="sb-secondary" onClick={addState} disabled={!stateToPick}>Add state</button>
        </div>
      </div>
      {value.states.length > 0 && <div className="sb-span-all">
        <strong>Step 2 · Districts (optional)</strong>
        <p className="sb-muted">Leave empty to serve the whole selected state(s).</p>
        <div className="sb-chip-row">{value.districts.map(d => <span className="sb-chip" key={d}>{d} <button type="button" aria-label={"Remove " + d} onClick={() => set({ districts: value.districts.filter(x => x !== d) })}>×</button></span>)}</div>
        <div className="sb-inline-row">
          <input list={listId} value={districtDraft} maxLength="100" placeholder="Type a district name" onChange={e => setDistrictDraft(e.target.value)} onKeyDown={e => { if (e.key === "Enter") { e.preventDefault(); addDistrict(); } }}/>
          <datalist id={listId}>{suggestions.map(d => <option key={d} value={d}/>)}</datalist>
          <button type="button" className="sb-secondary" onClick={addDistrict} disabled={!districtDraft.trim()}>Add district</button>
        </div>
      </div>}
      {value.states.length > 0 && <label className="sb-span-all"><strong>Step 3 · PIN codes (optional)</strong>
        <small className="sb-muted">Leave empty to serve everything selected above. If you enter PIN codes, ONLY those PINs are served.</small>
        <textarea rows="2" placeholder="822101, 822102, 110001" value={value.pins} onChange={e => set({ pins: e.target.value })}/>
      </label>}
      <p className="sb-span-all sb-coverage-summary" role="status"><strong>{coverageSummary(value)}</strong></p>
    </div>
  </fieldset>;
}
