// Makes a real copy of a product in one go: details, categories, attributes,
// product-specific options, variants with prices, availability rules and
// product-level images. SKUs and barcodes are created fresh. Stock is not copied.
const OPTION_TYPES = ["text", "colour", "image"];

export function slugifyName(value) {
  return String(value).toLowerCase().trim().replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "");
}

export function copyName(name, attempt = 1) {
  const base = String(name || "Product").trim().slice(0, 215);
  return attempt <= 1 ? base + " (Copy)" : base + " (Copy " + attempt + ")";
}

const isNameTaken = error => /already exists|unique/i.test(String(error?.message || ""));

export async function duplicateProductRecord(api, item, { maxTries = 25 } = {}) {
  if (!item?.id) throw new Error("Choose a product to duplicate.");
  const id = item.id;
  const [attributeResult, variantResult, ruleResult, imageResult, definitionResult] = await Promise.all([
    api("/catalogue/products/" + id + "/attributes"),
    api("/catalogue/products/" + id + "/variants?limit=500"),
    api("/catalogue/products/" + id + "/availability-rules").catch(() => ({ items: [] })),
    api("/catalogue/products/" + id + "/images").catch(() => ({ items: [] })),
    api("/catalogue/attributes"),
  ]);

  const productAttributes = {};
  for (const attribute of attributeResult.items || []) {
    if (!attribute.is_variant_attribute && attribute.value !== null && attribute.value !== undefined) {
      productAttributes[attribute.id] = attribute.value;
    }
  }

  const optionDefinitions = (definitionResult.items || []).filter(def => def.is_variant_attribute && OPTION_TYPES.includes(def.value_type));
  const optionEntries = await Promise.all(optionDefinitions.map(async def => {
    const result = await api("/catalogue/products/" + id + "/attributes/" + def.id + "/options");
    return [def.id, (result.items || []).map(option => option.value)];
  }));
  const customOptions = Object.fromEntries(optionEntries.filter(([, values]) => values.length));

  const variants = (variantResult.items || []).filter(row => row.is_active !== false).map(row => ({
    attributes: row.attributes || {},
    selling_price: Number(row.selling_price),
    mrp: row.mrp == null ? Number(row.selling_price) : Number(row.mrp),
    cost_price: row.cost_price == null ? null : Number(row.cost_price),
  }));

  const availabilityRules = (ruleResult.items || []).map(rule => ({
    channel: rule.channel,
    region_code: rule.region_code || null,
    pincode: rule.pincode || null,
    location_id: rule.location_id ? Number(rule.location_id) : null,
    is_allowed: rule.is_allowed !== false,
  }));

  const categoryIds = [...new Set((Array.isArray(item.category_ids) && item.category_ids.length ? item.category_ids : [item.category_id]).map(Number).filter(value => Number.isInteger(value) && value > 0))];

  let saved = null;
  let lastError = null;
  for (let attempt = 1; attempt <= maxTries && !saved; attempt += 1) {
    const name = copyName(item.name, attempt);
    const body = {
      product: {
        name,
        slug: slugifyName(name),
        brand: item.brand || null,
        category_id: categoryIds[0] || null,
        category_ids: categoryIds,
        description: item.description || null,
        tax_code: item.tax_code || null,
        tax_rate: item.tax_rate == null || item.tax_rate === "" ? null : Number(item.tax_rate),
        is_pos_available: item.is_pos_available !== false,
        is_website_available: item.is_website_available !== false,
        delivery_options: item.delivery_options?.length ? item.delivery_options : ["standard"],
        status: item.status === "draft" ? "draft" : "active",
      },
      product_attributes: Object.fromEntries(Object.entries(productAttributes).map(([key, value]) => [String(Number(key)), value])),
      custom_options: Object.fromEntries(Object.entries(customOptions).map(([key, values]) => [String(Number(key)), values])),
      variants,
      availability_rules: availabilityRules,
    };
    try {
      saved = await api("/catalogue/products/complete", { method: "POST", body: JSON.stringify(body) });
    } catch (error) {
      if (!isNameTaken(error)) throw error;
      lastError = error;
    }
  }
  if (!saved) throw lastError || new Error("Could not find a free name for the copy.");

  const images = (imageResult.items || []).filter(image => image.variant_id == null && image.image_url);
  let imageCount = 0;
  let imageFailures = 0;
  for (const image of images) {
    try {
      await api("/catalogue/products/" + saved.id + "/images", {
        method: "POST",
        body: JSON.stringify({ image_url: image.image_url, alt_text: image.alt_text || null, sort_order: Number(image.sort_order || 0), is_primary: Boolean(image.is_primary) }),
      });
      imageCount += 1;
    } catch {
      imageFailures += 1;
    }
  }
  return { product: saved, variantCount: saved.created_variant_count ?? variants.length, imageCount, imageFailures };
}
