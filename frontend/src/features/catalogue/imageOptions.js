// Image-type attribute values are { name, image }. Variants store the NAME, so the product page,
// SKUs and admin screens read "Black" instead of a file link. Older data stored just the image
// link as a plain string; those values are still understood.
export const isImageUrl = value => /^(https?:)?\/\//i.test(String(value ?? "").trim()) || /^\/[^\s]+\.(webp|png|jpe?g|gif|svg)(\?.*)?$/i.test(String(value ?? "").trim());

// Short readable name for an image link, e.g. ".../attributes/ab12.webp" -> "ab12".
export function imageOptionLabel(value) {
  const text = String(value ?? "").trim();
  if (!isImageUrl(text)) return text;
  try {
    const last = decodeURIComponent(text.split("?")[0].split("#")[0].split("/").filter(Boolean).pop() || "");
    return last.replace(/\.[a-z0-9]+$/i, "") || "Image";
  } catch { return "Image"; }
}

// Suggested name for a new value from a file name or caption; "" when it is only a machine hash.
export function suggestImageName(text) {
  const base = String(text ?? "").trim().split("/").pop().replace(/\.[a-z0-9]{2,5}$/i, "").replace(/[-_]+/g, " ").replace(/\s+/g, " ").trim();
  if (!base || /^[0-9a-f]{12,}$/i.test(base.replace(/\s/g, ""))) return "";
  return base.charAt(0).toUpperCase() + base.slice(1);
}

// One saved option -> { name, image, value } where `value` is what variants store.
export function normalizeImageOption(option) {
  if (option && typeof option === "object") {
    const name = String(option.name ?? "").trim();
    const image = String(option.image ?? "").trim();
    return { name: name || imageOptionLabel(image), image, value: name || image, legacy: false };
  }
  const text = String(option ?? "").trim();
  return { name: imageOptionLabel(text), image: isImageUrl(text) ? text : "", value: text, legacy: true };
}

// Turns a value saved on a variant (a name, or an old image link) into { name, image }.
export function resolveImageValue(raw, options = []) {
  const value = String(Array.isArray(raw) ? raw[0] : raw ?? "").trim();
  for (const option of options || []) {
    const item = normalizeImageOption(option);
    if (item.value === value || item.name === value || (item.image && item.image === value)) return item;
  }
  return { name: imageOptionLabel(value), image: isImageUrl(value) ? value : "", value, legacy: true };
}
