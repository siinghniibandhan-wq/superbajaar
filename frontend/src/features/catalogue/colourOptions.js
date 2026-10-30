// Colour option helpers shared by Catalogue and Product Creation.
const NAMED_COLOURS = [
  ["Black","#000000"],["White","#FFFFFF"],["Red","#FF0000"],["Green","#008000"],["Blue","#0000FF"],
  ["Yellow","#FFFF00"],["Orange","#FFA500"],["Purple","#800080"],["Pink","#FFC0CB"],["Brown","#A52A2A"],
  ["Maroon","#800000"],["Navy","#000080"],["Teal","#008080"],["Olive","#808000"],["Lime","#00FF00"],
  ["Aqua","#00FFFF"],["Cyan","#00FFFF"],["Silver","#C0C0C0"],["Gray","#808080"],["Grey","#808080"],
  ["Gold","#FFD700"],["Beige","#F5F5DC"],["Ivory","#FFFFF0"],["Coral","#FF7F50"],["Salmon","#FA8072"],
  ["Tomato","#FF6347"],["Crimson","#DC143C"],["Indigo","#4B0082"],["Violet","#EE82EE"],["Lavender","#E6E6FA"],
  ["Plum","#DDA0DD"],["Orchid","#DA70D6"],["Turquoise","#40E0D0"],["Aquamarine","#7FFFD4"],["Sky Blue","#87CEEB"],
  ["Steel Blue","#4682B4"],["Royal Blue","#4169E1"],["Dodger Blue","#1E90FF"],["Powder Blue","#B0E0E6"],
  ["Light Blue","#ADD8E6"],["Dark Blue","#00008B"],["Light Green","#90EE90"],["Dark Green","#006400"],
  ["Sea Green","#2E8B57"],["Forest Green","#228B22"],["Mint","#98FF98"],["Khaki","#F0E68C"],
  ["Tan","#D2B48C"],["Chocolate","#D2691E"],["Sienna","#A0522D"],["Wheat","#F5DEB3"],
  ["Hot Pink","#FF69B4"],["Deep Pink","#FF1493"],["Magenta","#FF00FF"],["Fuchsia","#FF00FF"],
  ["Azure","#F0FFFF"],["Alice Blue","#F0F8FF"],["Slate Gray","#708090"],["Charcoal","#36454F"]
];
const rgb = hex => [1,3,5].map(i => parseInt(hex.slice(i,i+2),16));
export function suggestColourName(hex) {
  const target = rgb(hex);
  let best = NAMED_COLOURS[0], distance = Infinity;
  for (const entry of NAMED_COLOURS) {
    const candidate = rgb(entry[1]);
    const score = candidate.reduce((sum, channel, i) => sum + (channel-target[i])**2, 0);
    if (score < distance) { distance = score; best = entry; }
  }
  return best[0];
}
export function normalizeColourOption(option) {
  if (option && typeof option === "object" && !Array.isArray(option)) {
    return { name: String(option.name || "").trim(), hex: String(option.hex || "").toUpperCase() };
  }
  return { name: String(option ?? "").trim(), hex: "" };
}
export function colourOptionLabel(option) { return normalizeColourOption(option).name; }
export function isDuplicateOption(existing, candidate, valueType) {
  if (valueType === "colour") {
    const next = normalizeColourOption(candidate);
    return existing.some(item => {
      const current = normalizeColourOption(item);
      return current.name.toLocaleLowerCase() === next.name.toLocaleLowerCase()
        || Boolean(next.hex && current.hex && current.hex.toUpperCase() === next.hex.toUpperCase());
    });
  }
  const next = String(candidate ?? "").trim().toLocaleLowerCase();
  return existing.some(item => String(item ?? "").trim().toLocaleLowerCase() === next);
}
