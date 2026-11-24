import { normalizeDisplayType } from "../features/catalogue/attributeDisplay.js";
import { colourOptionLabel, colourHexForValue } from "../features/catalogue/colourOptions.js";

// Turns one saved variant attribute value into a stable key and a label.
function optionOf(raw) {
  const value = Array.isArray(raw) ? raw[0] : raw;
  const label = colourOptionLabel(value) || String(value ?? "").trim();
  return { key: label.toLowerCase(), label, raw: value };
}

// Builds the choosers shown on the product page: one group per attribute that
// has at least two different values across the product's variants.
export function variantAttributeGroups(variants = [], definitions = []) {
  const byCode = new Map();
  for (const variant of variants) {
    for (const [code, raw] of Object.entries(variant.attributes || {})) {
      const option = optionOf(raw);
      if (!option.label) continue;
      if (!byCode.has(code)) byCode.set(code, new Map());
      if (!byCode.get(code).has(option.key)) byCode.get(code).set(option.key, option);
    }
  }
  const groups = [];
  for (const [code, options] of byCode) {
    if (options.size < 2) continue;
    const definition = definitions.find(item => item.code === code) || {};
    const valueType = definition.value_type || "text";
    groups.push({
      code,
      name: definition.name || code.replace(/_/g, " ").replace(/^./, c => c.toUpperCase()),
      valueType,
      displayType: normalizeDisplayType(definition.display_type, valueType),
      options: [...options.values()].map(option => ({ ...option, hex: valueType === "colour" ? colourHexForValue(option.raw) : "" })),
    });
  }
  return groups;
}

export function selectedKeyFor(variant, code) {
  return optionOf((variant?.attributes || {})[code]).key;
}

// Picks the variant to show after the customer taps a value. Prefers the variant
// that keeps every other choice; otherwise the closest match with that value.
export function pickVariant(variants, current, code, valueKey) {
  const wanted = Object.fromEntries(Object.entries(current?.attributes || {}).map(([key, raw]) => [key, optionOf(raw).key]));
  wanted[code] = valueKey;
  let best = null; let bestScore = -1;
  for (const variant of variants) {
    const attrs = Object.fromEntries(Object.entries(variant.attributes || {}).map(([key, raw]) => [key, optionOf(raw).key]));
    if (attrs[code] !== valueKey) continue;
    const score = Object.entries(wanted).filter(([key, value]) => key !== code && attrs[key] === value).length;
    if (score > bestScore) { best = variant; bestScore = score; }
  }
  return best;
}
