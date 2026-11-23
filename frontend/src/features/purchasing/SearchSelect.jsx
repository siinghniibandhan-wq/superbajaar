import { useEffect, useMemo, useRef, useState } from "react";

// Search-and-tap picker used instead of long drop-down lists.
// items: [{ id, title, sub, meta, search }]
// mode "single": shows the chosen item as a chip. mode "add": clears after every pick (quick add).
export default function SearchSelect({ label, items = [], value = "", onChange, placeholder = "Type to search", mode = "single", emptyText = "No match found", disabled = false, hint = "" }) {
  const [text, setText] = useState("");
  const [open, setOpen] = useState(false);
  const [active, setActive] = useState(0);
  const inputRef = useRef(null);
  const chosen = mode === "single" && value !== "" && value != null ? items.find(item => String(item.id) === String(value)) : null;

  const results = useMemo(() => {
    const words = text.trim().toLowerCase().split(/\s+/).filter(Boolean);
    const scored = [];
    for (const item of items) {
      const hay = (item.search || (String(item.title || "") + " " + String(item.sub || ""))).toLowerCase();
      if (words.some(word => !hay.includes(word))) continue;
      const first = String(item.title || "").toLowerCase();
      const rank = !words.length ? 2 : hay.split(/\s+/).includes(words[0]) ? 0 : first.startsWith(words[0]) ? 1 : 2;
      scored.push({ item, rank });
    }
    scored.sort((a, b) => a.rank - b.rank);
    return scored.slice(0, 40).map(entry => entry.item);
  }, [items, text]);

  useEffect(() => { setActive(0); }, [text]);

  function pick(item) {
    if (!item) return;
    onChange(item);
    setText("");
    setOpen(false);
    if (mode === "add") inputRef.current?.focus();
  }

  function onKeyDown(event) {
    if (event.key === "Enter") {
      event.preventDefault();
      if (open && results[active]) pick(results[active]);
    } else if (event.key === "ArrowDown") {
      event.preventDefault(); setOpen(true); setActive(index => Math.min(results.length - 1, index + 1));
    } else if (event.key === "ArrowUp") {
      event.preventDefault(); setActive(index => Math.max(0, index - 1));
    } else if (event.key === "Escape") {
      setOpen(false);
    }
  }

  if (chosen) {
    return <div className="sb-ss">
      {label && <span className="sb-ss-label">{label}</span>}
      <div className="sb-ss-chosen">
        <span><strong>{chosen.title}</strong>{chosen.sub && <small>{chosen.sub}</small>}</span>
        <button type="button" disabled={disabled} onClick={() => onChange(null)}>Change</button>
      </div>
    </div>;
  }

  return <div className="sb-ss">
    {label && <label className="sb-ss-label" htmlFor={undefined}>{label}</label>}
    <input
      ref={inputRef}
      type="search"
      role="combobox"
      aria-label={label || placeholder}
      aria-expanded={open}
      aria-autocomplete="list"
      autoComplete="off"
      disabled={disabled}
      placeholder={placeholder}
      value={text}
      onChange={event => { setText(event.target.value); setOpen(true); }}
      onFocus={() => setOpen(true)}
      onBlur={() => setOpen(false)}
      onKeyDown={onKeyDown}
    />
    {hint && <small className="sb-ss-hint">{hint}</small>}
    {open && <ul className="sb-ss-list" role="listbox" onPointerDown={event => event.preventDefault()}>
      {results.length ? results.map((item, index) => <li key={item.id} role="option" aria-selected={index === active} className={index === active ? "is-active" : ""} onClick={() => pick(item)}>
        <span><strong>{item.title}</strong>{item.sub && <small>{item.sub}</small>}</span>
        {item.meta && <em>{item.meta}</em>}
      </li>) : <li className="sb-ss-empty">{emptyText}</li>}
    </ul>}
  </div>;
}

const money = v => new Intl.NumberFormat("en-IN", { style: "currency", currency: "INR" }).format(Number(v || 0));

// Turns catalogue variants into picker items. stock = { total: {variantId: qty}, byLocation: {"variantId:locationId": qty} }
export function variantItems(variants = [], stock = null, locationId = "") {
  return variants.filter(variant => variant.is_active !== false).map(variant => {
    const name = variant.product_name || variant.name || ("Product " + variant.product_id);
    const attrs = Object.values(variant.attributes || {}).map(value => Array.isArray(value) ? value.join(", ") : String(value)).filter(Boolean).join(" / ");
    const sku = variant.sku || ("Variant " + variant.id);
    let meta = "";
    if (stock) {
      const here = locationId ? stock.byLocation?.[variant.id + ":" + locationId] : undefined;
      const total = stock.total?.[variant.id];
      meta = here !== undefined ? "Stock here " + here : total !== undefined ? "Stock " + total : "Stock 0";
    }
    if (variant.cost_price != null && variant.cost_price !== "") meta = (meta ? meta + " · " : "") + "Cost " + money(variant.cost_price);
    return { id: variant.id, title: name, sub: sku + (attrs ? " · " + attrs : ""), meta, search: [name, sku, attrs, variant.barcode, variant.brand].filter(Boolean).join(" ") };
  });
}
