import { normalizeDisplayType } from "../features/catalogue/attributeDisplay.js";
import { isImageUrl, imageOptionLabel, resolveImageValue } from "../features/catalogue/imageOptions.js";
import { colourOptionLabel, colourHexForValue, normalizeColourOption } from "../features/catalogue/colourOptions.js";

// Turns one saved variant attribute value into a stable key and a label.
function optionOf(raw) {
  const value = Array.isArray(raw) ? raw[0] : raw;
  if (isImageUrl(value)) {
    const url = String(value).trim();
    return { key: url.toLowerCase(), label: imageOptionLabel(url), raw: value, image: url };
  }
  const label = colourOptionLabel(value) || String(value ?? "").trim();
  return { key: label.toLowerCase(), label, raw: value };
}

// Readable text for one saved variant value (an Image value shows its name, never its link).
export function variantValueLabel(code, raw, definitions = []) {
  const definition = (definitions || []).find(item => item.code === code);
  if (definition?.value_type === "image") return resolveImageValue(raw, definition.options || []).name;
  return Array.isArray(raw) ? raw.join(", ") : String(raw ?? "");
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
    // Hex codes picked in Catalogue live on the attribute definition's options ({name, hex}).
    // Variants only store the colour name, so look the saved hex up by name first.
    const savedHex = new Map();
    for (const saved of definition.options || []) {
      const { name, hex } = normalizeColourOption(saved);
      if (name && /^#[0-9A-F]{6}$/i.test(hex)) savedHex.set(name.toLowerCase(), hex);
    }
    groups.push({
      code,
      name: definition.name || code.replace(/_/g, " ").replace(/^./, c => c.toUpperCase()),
      valueType,
      displayType: normalizeDisplayType(definition.display_type, valueType),
      options: [...options.values()].map(option => {
        if (valueType === "image") {
          // Variants store the value NAME (older data: the image link). Look the picture up on the attribute.
          const item = resolveImageValue(option.raw, definition.options || []);
          return { ...option, label: item.name, image: item.image, hex: "" };
        }
        return { ...option, hex: valueType === "colour" ? (savedHex.get(option.key) || colourHexForValue(option.raw)) : "" };
      }),
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
