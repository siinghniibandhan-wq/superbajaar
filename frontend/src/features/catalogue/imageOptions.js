// Image-type attribute values are stored as the image URL (or a plain key, for older data).
export const isImageUrl = value => /^(https?:)?\/\//i.test(String(value ?? "").trim()) || /^\/[^\s]+\.(webp|png|jpe?g|gif|svg)(\?.*)?$/i.test(String(value ?? "").trim());

// Short readable name for an image value, e.g. ".../attributes/ab12.webp" -> "ab12".
export function imageOptionLabel(value) {
  const text = String(value ?? "").trim();
  if (!isImageUrl(text)) return text;
  try {
    const last = decodeURIComponent(text.split("?")[0].split("#")[0].split("/").filter(Boolean).pop() || "");
    return last.replace(/\.[a-z0-9]+$/i, "") || "Image";
  } catch { return "Image"; }
}
