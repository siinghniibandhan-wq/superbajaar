import test from "node:test";
import assert from "node:assert/strict";
import { duplicateProductRecord, copyName, slugifyName } from "../../src/features/catalogue/duplicateProduct.js";

function makeApi({ takenSlugs = [], failImages = false } = {}) {
  const calls = [];
  const taken = new Set(takenSlugs);
  const api = async (path, options = {}) => {
    calls.push({ path, options });
    const body = options.body ? JSON.parse(options.body) : null;
    if (path === "/catalogue/products/7/attributes") return { items: [
      { id: 1, is_variant_attribute: false, value: "Cotton" },
      { id: 2, is_variant_attribute: true, value: null },
    ] };
    if (path === "/catalogue/products/7/variants?limit=5000") return { items: [
      { id: 71, sku: "A-1", is_active: true, attributes: { size: "S" }, selling_price: "100.00", mrp: "120.00", cost_price: "60.00" },
      { id: 72, sku: "A-2", is_active: true, attributes: { size: "M" }, selling_price: "110.00", mrp: null, cost_price: null },
      { id: 73, sku: "A-3", is_active: false, attributes: { size: "L" }, selling_price: "130.00", mrp: "150.00", cost_price: null },
    ] };
    if (path === "/catalogue/products/7/availability-rules") return { items: [{ id: 9, channel: "website", pincode: "110001", is_allowed: true }] };
    if (path === "/catalogue/products/7/images") return { items: [
      { id: 1, variant_id: null, image_url: "https://img.example/a.jpg", alt_text: "A", sort_order: 0, is_primary: true },
      { id: 2, variant_id: 71, image_url: "https://img.example/variant.jpg", sort_order: 0, is_primary: false },
    ] };
    if (path === "/catalogue/attributes") return { items: [{ id: 2, value_type: "text", is_variant_attribute: true }, { id: 1, value_type: "text", is_variant_attribute: false }] };
    if (path === "/catalogue/products/7/attributes/2/options") return { items: [{ value: "S" }, { value: "M" }] };
    if (path === "/catalogue/products/complete") {
      if (taken.has(body.product.slug)) throw new Error("A record with this unique value already exists");
      return { id: 99, name: body.product.name, slug: body.product.slug, created_variant_count: body.variants.length };
    }
    if (path === "/catalogue/products/99/images") {
      if (failImages) throw new Error("boom");
      return { id: 500 };
    }
    throw new Error("unexpected call " + path);
  };
  return { api, calls };
}

const item = { id: 7, name: "Cotton Shirt", slug: "cotton-shirt", brand: "Acme", description: "Nice", category_id: 3, category_ids: [3, 4], tax_code: "6205", tax_rate: "5.00", status: "active", is_pos_available: true, is_website_available: false, delivery_options: ["standard"] };

test("duplicate copies details, active variants with prices, attributes, options, rules and product images", async () => {
  const { api, calls } = makeApi();
  const result = await duplicateProductRecord(api, item);
  const create = calls.find(c => c.path === "/catalogue/products/complete");
  const body = JSON.parse(create.options.body);
  assert.equal(create.options.method, "POST");
  assert.equal(body.product.name, "Cotton Shirt (Copy)");
  assert.equal(body.product.slug, "cotton-shirt-copy");
  assert.deepEqual(body.product.category_ids, [3, 4]);
  assert.equal(body.product.is_website_available, false);
  assert.equal(body.product.tax_rate, 5);
  assert.deepEqual(body.product_attributes, { "1": "Cotton" });
  assert.deepEqual(body.custom_options, { "2": ["S", "M"] });
  assert.equal(body.variants.length, 2);
  assert.deepEqual(body.variants[0], { attributes: { size: "S" }, selling_price: 100, mrp: 120, cost_price: 60 });
  assert.deepEqual(body.variants[1], { attributes: { size: "M" }, selling_price: 110, mrp: 110, cost_price: null });
  assert.equal(body.availability_rules[0].pincode, "110001");
  assert.equal(result.variantCount, 2);
  assert.equal(result.imageCount, 1);
  assert.equal(calls.filter(c => c.path === "/catalogue/products/99/images").length, 1);
});

test("duplicate picks a free name when the copy name is already taken", async () => {
  const { api } = makeApi({ takenSlugs: ["cotton-shirt-copy", "cotton-shirt-copy-2"] });
  const result = await duplicateProductRecord(api, item);
  assert.equal(result.product.name, "Cotton Shirt (Copy 3)");
});

test("image copy failures do not undo the product copy", async () => {
  const { api } = makeApi({ failImages: true });
  const result = await duplicateProductRecord(api, item);
  assert.equal(result.product.id, 99);
  assert.equal(result.imageFailures, 1);
});

test("other errors stop the copy and are reported", async () => {
  const { api } = makeApi();
  const failing = async (path, options) => { if (path === "/catalogue/products/complete") throw new Error("Catalogue database is unavailable"); return api(path, options); };
  await assert.rejects(() => duplicateProductRecord(failing, item), /unavailable/);
});

test("helpers", () => {
  assert.equal(copyName("X", 1), "X (Copy)");
  assert.equal(copyName("X", 4), "X (Copy 4)");
  assert.equal(slugifyName("Cotton Shirt (Copy 2)"), "cotton-shirt-copy-2");
});
