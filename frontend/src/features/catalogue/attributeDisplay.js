// How an attribute is shown to customers. Every style is a tap-to-select control;
// dropdowns are intentionally not offered.

export const DISPLAY_STYLES = {
  text: [
    { value: "button", label: "Pill buttons", hint: "Rounded buttons. Best for sizes and pack weights (default)" },
    { value: "circle", label: "Circles", hint: "Round buttons. Best for short values like S, M, L or 1, 2, 3" },
    { value: "tile", label: "Tiles", hint: "Larger boxes. Best for longer values like 500 g pack" },
    { value: "text", label: "Plain text", hint: "Shown as simple text, not as a selector" },
  ],
  colour: [
    { value: "colour", label: "Colour circles", hint: "Round colour swatches (default)" },
    { value: "colour_chip", label: "Colour with name", hint: "Swatch with the colour name beside it" },
    { value: "button", label: "Name buttons", hint: "Pill buttons showing only the colour name" },
  ],
  image: [
    { value: "image", label: "Image squares", hint: "Small square pictures (default)" },
    { value: "image_circle", label: "Image circles", hint: "Round pictures" },
  ],
};

export function defaultDisplayType(valueType) {
  return valueType === "colour" ? "colour" : valueType === "image" ? "image" : "button";
}

export function displayStylesFor(valueType) {
  return DISPLAY_STYLES[valueType] || DISPLAY_STYLES.text;
}

/** Old data may hold "dropdown" or an empty value; map it, and anything unsupported, to the default selector. */
export function normalizeDisplayType(displayType, valueType) {
  return displayStylesFor(valueType).some(style => style.value === displayType) ? displayType : defaultDisplayType(valueType);
}

export function displayStyleLabel(displayType, valueType) {
  const style = displayStylesFor(valueType).find(item => item.value === normalizeDisplayType(displayType, valueType));
  return style ? style.label : "Pill buttons";
}
