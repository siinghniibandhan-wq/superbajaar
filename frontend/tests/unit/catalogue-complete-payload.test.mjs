import test from "node:test";
import assert from "node:assert/strict";
import { buildCompleteProductPayload } from "../../src/features/catalogue/catalogueComplete.js";

test("complete catalogue payload carries product, supported attribute values, new options, variants and availability in one request", () => {
  const result = buildCompleteProductPayload({
    product: { name: "Wheat Flour", category_ids: [3], tax_rate: 5 },
    productAttributes: { 4: "Whole wheat", 5: "" },
    customOptions: { 7: ["500g", "1kg"] },
    variants: [{ attributes: { pack: "500g" }, selling_price: 80, mrp: 90, cost_price: 60 }],
    availabilityRules: [{ channel: "website", pincode: "800001", is_allowed: true }],
  });
  assert.deepEqual(result, {
    product: { name: "Wheat Flour", category_ids: [3], tax_rate: 5 },
    product_attributes: { "4": "Whole wheat", "5": "" },
    custom_options: { "7": ["500g", "1kg"] },
    variants: [{ attributes: { pack: "500g" }, selling_price: 80, mrp: 90, cost_price: 60 }],
    availability_rules: [{ channel: "website", pincode: "800001", is_allowed: true }],
  });
});

test("complete catalogue payload always sends arrays and objects for empty optional sections", () => {
  assert.deepEqual(buildCompleteProductPayload({ product: { name: "Simple product" } }), {
    product: { name: "Simple product" }, product_attributes: {}, custom_options: {}, variants: [], availability_rules: [],
  });
});
