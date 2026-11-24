// Helpers for the storefront display order of variant values (e.g. 0.1 Kg, 0.250 Kg, 0.5 Kg, 1 Kg).

const UNIT_FACTORS = { mg: 0.000001, g: 0.001, gm: 0.001, gram: 0.001, grams: 0.001, kg: 1, kgs: 1, kilo: 1, ml: 0.001, l: 1, ltr: 1, litre: 1, liter: 1 };

// "0. 250 Kg" -> 0.25, "500 g" -> 0.5, "1 Kg" -> 1. Returns null when the label is not a quantity.
export function quantityOf(label) {
  const match = String(label ?? "").trim().toLowerCase().match(/^(\d+(?:\s*\.\s*\d+)?|\.\d+)\s*([a-z]*)$/);
  if (!match) return null;
  const number = Number(match[1].replace(/\s+/g, ""));
  if (!Number.isFinite(number)) return null;
  const unit = match[2];
  if (!unit) return number;
  return unit in UNIT_FACTORS ? number * UNIT_FACTORS[unit] : null;
}

// Smallest quantity first when every value is a quantity; otherwise natural A-Z order.
export function sortValuesLowToHigh(values = []) {
  const list = [...values];
  const quantities = list.map(quantityOf);
  if (quantities.every(q => q !== null)) {
    return list.map((value, i) => ({ value, q: quantities[i] })).sort((a, b) => a.q - b.q).map(item => item.value);
  }
  return list.sort((a, b) => String(a).localeCompare(String(b), undefined, { numeric: true, sensitivity: "base" }));
}

// Orders values by a saved list. Values missing from the list keep their relative order at the end.
export function orderByList(values = [], order = []) {
  const rank = value => { const i = order.findIndex(item => String(item) === String(value)); return i === -1 ? Number.MAX_SAFE_INTEGER : i; };
  return [...values].sort((a, b) => rank(a) - rank(b));
}

// Moves one value up (-1) or down (+1) in the list.
export function moveValue(values = [], value, direction) {
  const list = [...values];
  const from = list.findIndex(item => String(item) === String(value));
  const to = from + direction;
  if (from === -1 || to < 0 || to >= list.length) return list;
  [list[from], list[to]] = [list[to], list[from]];
  return list;
}

function firstValue(raw) { return String(Array.isArray(raw) ? raw[0] : raw ?? ""); }

// Returns variant ids in the order implied by the per-attribute value order.
// `codes` lists the variant attribute codes, most important first.
export function variantIdsInOrder(variants = [], codes = [], valueOrder = {}) {
  const rankOf = (variant, code) => {
    const list = valueOrder[code] || [];
    const i = list.findIndex(item => String(item) === firstValue((variant.attributes || {})[code]));
    return i === -1 ? Number.MAX_SAFE_INTEGER : i;
  };
  return [...variants]
    .sort((a, b) => {
      for (const code of codes) { const d = rankOf(a, code) - rankOf(b, code); if (d) return d; }
      return String(a.sku || "").localeCompare(String(b.sku || ""));
    })
    .map(variant => variant.id);
}
