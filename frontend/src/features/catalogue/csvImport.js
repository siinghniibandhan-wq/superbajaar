// Pure helpers for the catalogue CSV import: parsing, column mapping, validation and
// conversion into the payload accepted by POST /catalogue/products/complete.

export const GST_RATES = ["0", "0.1", "0.25", "1", "1.5", "3", "5", "6", "7.5", "12", "18", "28", "40"];
export const MAX_IMPORT_ROWS = 2000;

export const TEMPLATE_HEADERS = [
  "name", "brand", "category", "description", "hsn_code", "gst_rate",
  "selling_price", "mrp", "cost_price", "sku", "barcode", "status",
];

export const TEMPLATE_SAMPLE_ROWS = [
  ["Basmati Rice 5kg", "India Gate", "Grocery > Atta Dal Rice (ADR)", "Long grain aged basmati rice", "1006", "5", "649", "720", "590", "", "", "active"],
  ["Face Wash 100ml", "Himalaya", "Beauty | Personal Care", "Daily gentle face wash", "3304", "18", "125", "140", "", "FW-100", "", "active"],
];

const ALIASES = {
  name: "name", product_name: "name", product: "name", title: "name", item_name: "name",
  brand: "brand", brand_name: "brand",
  category: "category", categories: "category", category_name: "category",
  description: "description", product_description: "description", details: "description", product_details: "description",
  hsn_code: "tax_code", hsn: "tax_code", hsn_sac: "tax_code", hsn_sac_code: "tax_code", tax_code: "tax_code", sac_code: "tax_code",
  gst_rate: "tax_rate", gst: "tax_rate", tax_rate: "tax_rate", gst_percent: "tax_rate", tax: "tax_rate",
  selling_price: "selling_price", price: "selling_price", sale_price: "selling_price", sp: "selling_price", selling: "selling_price",
  mrp: "mrp", max_retail_price: "mrp", list_price: "mrp",
  cost_price: "cost_price", cost: "cost_price", purchase_price: "cost_price",
  sku: "sku", barcode: "barcode", ean: "barcode", upc: "barcode",
  status: "status",
  delivery: "delivery_options", delivery_options: "delivery_options",
  pos: "is_pos_available", available_pos: "is_pos_available", is_pos_available: "is_pos_available",
  website: "is_website_available", available_website: "is_website_available", is_website_available: "is_website_available",
};

export function slugify(value) {
  return String(value || "").toLowerCase().trim().replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "");
}

function headerKey(raw) {
  const key = String(raw || "").replace(/^﻿/, "").trim().toLowerCase().replace(/[^a-z0-9]+/g, "_").replace(/^_|_$/g, "");
  if (key.startsWith("attr_")) return key; // variant attribute column, e.g. attr_size
  if (key.startsWith("attribute_")) return "attr_" + key.slice(10);
  return ALIASES[key] || null;
}

/** RFC 4180 style parser: quoted fields, escaped quotes, CRLF/LF, BOM, auto delimiter. */
export function parseCsv(text) {
  let input = String(text || "").replace(/^﻿/, "");
  const firstLine = input.split(/\r?\n/, 1)[0] || "";
  const counts = { ",": 0, ";": 0, "\t": 0 };
  let inQ = false;
  for (const ch of firstLine) { if (ch === '"') inQ = !inQ; else if (!inQ && ch in counts) counts[ch]++; }
  const delimiter = Object.entries(counts).sort((a, b) => b[1] - a[1])[0][1] ? Object.entries(counts).sort((a, b) => b[1] - a[1])[0][0] : ",";
  const rows = [];
  let row = [], field = "", quoted = false, i = 0;
  while (i < input.length) {
    const ch = input[i];
    if (quoted) {
      if (ch === '"') { if (input[i + 1] === '"') { field += '"'; i += 2; continue; } quoted = false; i++; continue; }
      field += ch; i++; continue;
    }
    if (ch === '"' && field === "") { quoted = true; i++; continue; }
    if (ch === delimiter) { row.push(field); field = ""; i++; continue; }
    if (ch === "\r" || ch === "\n") {
      if (ch === "\r" && input[i + 1] === "\n") i++;
      row.push(field); field = ""; rows.push(row); row = []; i++; continue;
    }
    field += ch; i++;
  }
  if (field !== "" || row.length) { row.push(field); rows.push(row); }
  return rows.filter(r => r.some(cell => String(cell).trim() !== ""));
}

export function csvEscape(value) {
  const s = String(value ?? "");
  return /[",\r\n]/.test(s) ? '"' + s.replace(/"/g, '""') + '"' : s;
}
export function toCsv(rows) { return rows.map(r => r.map(csvEscape).join(",")).join("\r\n") + "\r\n"; }
export function templateCsv() { return toCsv([TEMPLATE_HEADERS, ...TEMPLATE_SAMPLE_ROWS]); }

function categoryPath(category, byId) {
  const path = []; const seen = new Set(); let current = category;
  while (current && !seen.has(current.id)) { seen.add(current.id); path.unshift(current.name); current = byId.get(Number(current.parent_id)); }
  return path;
}

export function buildCategoryResolver(categories = []) {
  const byId = new Map(categories.map(c => [Number(c.id), c]));
  const byName = new Map(); const byPath = new Map();
  for (const c of categories) {
    const nameKey = c.name.trim().toLowerCase();
    byName.set(nameKey, [...(byName.get(nameKey) || []), c]);
    byPath.set(categoryPath(c, byId).join(">").toLowerCase().replace(/\s*>\s*/g, ">"), c);
  }
  return function resolve(cell) {
    const ids = []; const errors = [];
    for (const part of String(cell || "").split(/[|;]/).map(p => p.trim()).filter(Boolean)) {
      const pathKey = part.split(/\s*[>›/]\s*/).map(p => p.trim()).join(">").toLowerCase();
      const hit = byPath.get(pathKey);
      if (hit) { ids.push(Number(hit.id)); continue; }
      const named = byName.get(part.toLowerCase()) || [];
      if (named.length === 1) ids.push(Number(named[0].id));
      else if (named.length > 1) errors.push(`Category "${part}" matches several categories; use the full path like "Parent > Child"`);
      else errors.push(`Category "${part}" does not exist. Create it first in the Categories tab`);
    }
    return { ids: [...new Set(ids)], errors };
  };
}

function parseBool(value, fallback) {
  const v = String(value ?? "").trim().toLowerCase();
  if (!v) return fallback;
  if (["1", "true", "yes", "y"].includes(v)) return true;
  if (["0", "false", "no", "n"].includes(v)) return false;
  return null;
}

function parseMoney(value, label, errors, { required = false } = {}) {
  const raw = String(value ?? "").trim().replace(/^(₹|rs\.?|inr)\s*/i, "").replace(/,/g, "");
  if (raw === "") { if (required) errors.push(`${label} is required`); return null; }
  const n = Number(raw);
  if (!Number.isFinite(n) || n < 0) { errors.push(`${label} must be a number of 0 or more`); return null; }
  return Math.round(n * 100) / 100;
}

/**
 * Turns parsed CSV rows into an import plan.
 * Rows sharing a product name form one product with several variants (use attr_<code> columns).
 * Returns { fatal, unknownColumns, items: [{ key, name, slug, lines, payload, errors, variantCount }] }
 */
export function buildImportPlan(rows, { categories = [] } = {}) {
  if (!rows.length) return { fatal: "The file is empty.", unknownColumns: [], items: [] };
  const headers = rows[0].map(headerKey);
  const unknownColumns = rows[0].filter((_, i) => !headers[i]).map(h => String(h).trim()).filter(Boolean);
  if (!headers.includes("name")) return { fatal: 'A "name" column is required. Download the template to see the expected columns.', unknownColumns, items: [] };
  if (!headers.includes("selling_price")) return { fatal: 'A "selling_price" column is required. Download the template to see the expected columns.', unknownColumns, items: [] };
  const dataRows = rows.slice(1);
  if (dataRows.length > MAX_IMPORT_ROWS) return { fatal: `A file can hold at most ${MAX_IMPORT_ROWS} rows. Split it into smaller files.`, unknownColumns, items: [] };
  const resolveCategories = buildCategoryResolver(categories);
  const groups = new Map();

  dataRows.forEach((cells, index) => {
    const line = index + 2;
    const rec = {}; const attrs = {};
    headers.forEach((h, i) => {
      if (!h) return;
      const v = String(cells[i] ?? "").trim();
      if (h.startsWith("attr_")) { if (v) attrs[h.slice(5)] = v; } else rec[h] = v;
    });
    const name = (rec.name || "").trim();
    const slug = slugify(name);
    const key = slug || "__line" + line;
    if (!groups.has(key)) groups.set(key, { name, slug, lines: [], first: rec, variants: [], errors: [], seen: new Set() });
    const g = groups.get(key); g.lines.push(line);
    const errs = [];
    if (!name) errs.push("Product name is required");
    else if (!slug) errs.push("Product name must contain letters or numbers");
    if (name.length > 240) errs.push("Product name is longer than 240 characters");
    const selling = parseMoney(rec.selling_price, "Selling price", errs, { required: true });
    let mrp = parseMoney(rec.mrp, "MRP", errs);
    const cost = parseMoney(rec.cost_price, "Cost price", errs);
    if (selling != null && mrp != null && mrp < selling) errs.push("MRP cannot be below the selling price");
    if (mrp == null && selling != null) mrp = selling;
    const attrKey = JSON.stringify(Object.fromEntries(Object.entries(attrs).sort(([a], [b]) => a.localeCompare(b))));
    if (g.seen.has(attrKey)) errs.push(Object.keys(attrs).length ? "Duplicate variant for this product (same attribute values)" : "Product appears twice. Add attr_ columns (e.g. attr_size) to make each row a variant");
    g.seen.add(attrKey);
    if (rec.sku && rec.sku.length > 100) errs.push("SKU is longer than 100 characters");
    if (rec.barcode && rec.barcode.length > 100) errs.push("Barcode is longer than 100 characters");
    g.errors.push(...errs.map(e => `Row ${line}: ${e}`));
    g.variants.push({ sku: rec.sku || null, barcode: rec.barcode || null, attributes: attrs, selling_price: selling ?? 0, mrp, cost_price: cost });
  });

  const items = [...groups.values()].map(g => {
    const rec = g.first; const errors = [...g.errors];
    const cat = resolveCategories(rec.category);
    if (!cat.ids.length && !cat.errors.length) errors.push(`Row ${g.lines[0]}: Category is required`);
    errors.push(...cat.errors.map(e => `Row ${g.lines[0]}: ${e}`));
    let taxRate = null;
    if (rec.tax_rate) {
      const t = rec.tax_rate.replace(/%/g, "").trim();
      if (!GST_RATES.includes(String(Number(t)))) errors.push(`Row ${g.lines[0]}: GST rate "${rec.tax_rate}" must be one of ${GST_RATES.join(", ")}`);
      else taxRate = Number(t);
    }
    const status = (rec.status || "active").toLowerCase();
    if (!["active", "draft"].includes(status)) errors.push(`Row ${g.lines[0]}: Status must be active or draft`);
    if (rec.tax_code && rec.tax_code.length > 32) errors.push(`Row ${g.lines[0]}: HSN/SAC code is longer than 32 characters`);
    if (rec.brand && rec.brand.length > 160) errors.push(`Row ${g.lines[0]}: Brand is longer than 160 characters`);
    const delivery = rec.delivery_options ? [...new Set(rec.delivery_options.toLowerCase().split(/[|;,]/).map(s => s.trim()).filter(Boolean))] : ["standard"];
    if (!delivery.length || delivery.some(d => !["standard", "express"].includes(d))) errors.push(`Row ${g.lines[0]}: Delivery must be standard and/or express`);
    const pos = parseBool(rec.is_pos_available, true), web = parseBool(rec.is_website_available, true);
    if (pos === null || web === null) errors.push(`Row ${g.lines[0]}: POS/website availability must be yes or no`);
    const hasAttrVariants = g.variants.some(v => Object.keys(v.attributes).length);
    if (hasAttrVariants && g.variants.some(v => !Object.keys(v.attributes).length)) errors.push("A product cannot mix variant rows that have attributes with rows that have none");
    return {
      key: g.slug || g.lines[0], name: g.name, slug: g.slug, lines: g.lines, errors, variantCount: g.variants.length,
      payload: {
        product: {
          name: g.name, slug: g.slug, brand: rec.brand || null, category_id: cat.ids[0] || null, category_ids: cat.ids,
          description: rec.description || null, tax_code: rec.tax_code || null, tax_rate: taxRate,
          status, is_pos_available: pos !== false, is_website_available: web !== false, delivery_options: delivery,
        },
        product_attributes: {}, custom_options: {}, availability_rules: [], variants: g.variants,
      },
    };
  });
  return { fatal: "", unknownColumns, items };
}
