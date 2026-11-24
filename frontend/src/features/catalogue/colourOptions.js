// Colour option helpers shared by Catalogue and Product Creation.
const NAMED_COLOURS = [
  ["Black","#000000"],["White","#FFFFFF"],["Red","#FF0000"],["Green","#008000"],["Blue","#0000FF"],
  ["Yellow","#FFFF00"],["Orange","#FFA500"],["Purple","#800080"],["Pink","#FFC0CB"],["Brown","#A52A2A"],
  ["Maroon","#800000"],["Navy","#000080"],["Teal","#008080"],["Olive","#808000"],["Lime","#00FF00"],
  ["Aqua","#00FFFF"],["Cyan","#00FFFF"],["Silver","#C0C0C0"],["Gray","#808080"],["Grey","#808080"],
  ["Gold","#FFD700"],["Beige","#F5F5DC"],["Ivory","#FFFFF0"],["Coral","#FF7F50"],["Salmon","#FA8072"],
  ["Tomato","#FF6347"],["Crimson","#DC143C"],["Indigo","#4B0082"],["Violet","#EE82EE"],["Lavender","#E6E6FA"],
  ["Plum","#DDA0DD"],["Orchid","#DA70D6"],["Turquoise","#40E0D0"],["Aquamarine","#7FFFD4"],["Sky Blue","#87CEEB"],
  ["Steel Blue","#4682B4"],["Royal Blue","#4169E1"],["Dodger Blue","#1E90FF"],["Powder Blue","#B0E0E6"],["Light Blue","#ADD8E6"],
  ["Dark Blue","#00008B"],["Light Green","#90EE90"],["Dark Green","#006400"],["Sea Green","#2E8B57"],["Forest Green","#228B22"],
  ["Mint","#98FF98"],["Khaki","#F0E68C"],["Tan","#D2B48C"],["Chocolate","#D2691E"],["Sienna","#A0522D"],
  ["Wheat","#F5DEB3"],["Hot Pink","#FF69B4"],["Deep Pink","#FF1493"],["Magenta","#FF00FF"],["Fuchsia","#FF00FF"],
  ["Azure","#F0FFFF"],["Alice Blue","#F0F8FF"],["Slate Gray","#708090"],["Charcoal","#36454F"],["Antique White","#FAEBD7"],
  ["Bisque","#FFE4C4"],["Blanched Almond","#FFEBCD"],["Blue Violet","#8A2BE2"],["Burly Wood","#DEB887"],["Cadet Blue","#5F9EA0"],
  ["Chartreuse","#7FFF00"],["Cornflower Blue","#6495ED"],["Cornsilk","#FFF8DC"],["Dark Cyan","#008B8B"],["Dark Goldenrod","#B8860B"],
  ["Dark Gray","#A9A9A9"],["Dark Grey","#A9A9A9"],["Dark Khaki","#BDB76B"],["Dark Magenta","#8B008B"],["Dark Olive Green","#556B2F"],
  ["Dark Orange","#FF8C00"],["Dark Orchid","#9932CC"],["Dark Red","#8B0000"],["Dark Salmon","#E9967A"],["Dark Sea Green","#8FBC8F"],
  ["Dark Slate Blue","#483D8B"],["Dark Slate Gray","#2F4F4F"],["Dark Slate Grey","#2F4F4F"],["Dark Turquoise","#00CED1"],["Dark Violet","#9400D3"],
  ["Deep Sky Blue","#00BFFF"],["Dim Gray","#696969"],["Dim Grey","#696969"],["Fire Brick","#B22222"],["Floral White","#FFFAF0"],
  ["Gainsboro","#DCDCDC"],["Ghost White","#F8F8FF"],["Goldenrod","#DAA520"],["Green Yellow","#ADFF2F"],["Honeydew","#F0FFF0"],
  ["Indian Red","#CD5C5C"],["Lavender Blush","#FFF0F5"],["Lawn Green","#7CFC00"],["Lemon Chiffon","#FFFACD"],["Light Coral","#F08080"],
  ["Light Cyan","#E0FFFF"],["Light Goldenrod Yellow","#FAFAD2"],["Light Gray","#D3D3D3"],["Light Grey","#D3D3D3"],["Light Pink","#FFB6C1"],
  ["Light Salmon","#FFA07A"],["Light Sea Green","#20B2AA"],["Light Sky Blue","#87CEFA"],["Light Slate Gray","#778899"],["Light Slate Grey","#778899"],
  ["Light Steel Blue","#B0C4DE"],["Light Yellow","#FFFFE0"],["Lime Green","#32CD32"],["Linen","#FAF0E6"],["Medium Aquamarine","#66CDAA"],
  ["Medium Blue","#0000CD"],["Medium Orchid","#BA55D3"],["Medium Purple","#9370DB"],["Medium Sea Green","#3CB371"],["Medium Slate Blue","#7B68EE"],
  ["Medium Spring Green","#00FA9A"],["Medium Turquoise","#48D1CC"],["Medium Violet Red","#C71585"],["Midnight Blue","#191970"],["Mint Cream","#F5FFFA"],
  ["Misty Rose","#FFE4E1"],["Moccasin","#FFE4B5"],["Navajo White","#FFDEAD"],["Old Lace","#FDF5E6"],["Olive Drab","#6B8E23"],
  ["Orange Red","#FF4500"],["Pale Goldenrod","#EEE8AA"],["Pale Green","#98FB98"],["Pale Turquoise","#AFEEEE"],["Pale Violet Red","#DB7093"],
  ["Papaya Whip","#FFEFD5"],["Peach Puff","#FFDAB9"],["Peru","#CD853F"],["Rebecca Purple","#663399"],["Rosy Brown","#BC8F8F"],
  ["Saddle Brown","#8B4513"],["Sandy Brown","#F4A460"],["Seashell","#FFF5EE"],["Slate Blue","#6A5ACD"],["Slate Grey","#708090"],
  ["Snow","#FFFAFA"],["Spring Green","#00FF7F"],["Thistle","#D8BFD8"],["White Smoke","#F5F5F5"],["Yellow Green","#9ACD32"]
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

const colourKey = text => String(text || "").toLowerCase().replace(/[^a-z]/g, "");
const NAME_LOOKUP = new Map(NAMED_COLOURS.map(([colourName, colourHex]) => [colourKey(colourName), [colourName, colourHex]]));
// Turns what a person typed (a HEX code like #1e90ff / 1E90FF / #fff, or a colour name like "blue" / "sky blue")
// into { hex, name, kind }. Returns null when the text is not recognised.
export function resolveColourInput(text) {
  const raw = String(text || "").trim();
  if (!raw) return null;
  const hexMatch = raw.match(/^#?([0-9a-f]{3}|[0-9a-f]{6})$/i);
  if (hexMatch) {
    let digits = hexMatch[1];
    if (digits.length === 3) digits = digits.split("").map(ch => ch + ch).join("");
    const hex = "#" + digits.toUpperCase();
    return { hex, name: suggestColourName(hex), kind: "hex" };
  }
  const found = NAME_LOOKUP.get(colourKey(raw));
  if (found) return { hex: found[1], name: found[0], kind: "name" };
  return null;
}
export function normalizeColourOption(option) {
  if (option && typeof option === "object" && !Array.isArray(option)) {
    return { name: String(option.name || "").trim(), hex: String(option.hex || "").toUpperCase() };
  }
  return { name: String(option ?? "").trim(), hex: "" };
}
// Hex for a colour value: uses the saved hex when present, otherwise looks the name up in the named list.
export function colourHexForValue(option) {
  const { name, hex } = normalizeColourOption(option);
  if (/^#[0-9A-F]{6}$/i.test(hex)) return hex;
  const found = NAMED_COLOURS.find(([colourName]) => colourName.toLowerCase() === name.toLowerCase());
  return found ? found[1] : "";
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
