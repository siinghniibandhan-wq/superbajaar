import test from "node:test";
import assert from "node:assert/strict";
import { cleanHsn, isValidHsn, matchHsnRule, categoriesWithoutRule, parseConditions, formatConditions, categoryPath } from "../../src/features/catalogue/hsnRules.js";

const categories = [
  { id: 1, parent_id: null, name: "Grocery" },
  { id: 2, parent_id: 1, name: "Rice" },
  { id: 3, parent_id: null, name: "Fresh Daily" },
  { id: 4, parent_id: 3, name: "Vegetables" },
];
const rules = [
  { id: 10, category_id: 2, conditions: {}, hsn_code: "10063090", gst_rate: 5 },
  { id: 11, category_id: 2, conditions: { packaging: "Loose" }, hsn_code: "10063090", gst_rate: 0 },
  { id: 12, category_id: 1, conditions: {}, hsn_code: "11010000", gst_rate: 5 },
  { id: 13, category_id: 4, conditions: { form: "Fresh" }, hsn_code: "09101110", gst_rate: 0 },
];

test("8-digit validation", () => {
  assert.equal(cleanHsn("1006 30 90 99"), "10063090");
  assert.ok(isValidHsn("10063090"));
  assert.ok(!isValidHsn("1006"));
  assert.ok(!isValidHsn("1006309A"));
});

test("condition beats plain category rule", () => {
  const loose = matchHsnRule(rules, categories, { categoryIds: [2], values: { Packaging: " loose " } });
  assert.equal(loose.id, 11);
  const packed = matchHsnRule(rules, categories, { categoryIds: [2], values: { packaging: "Packed & labelled" } });
  assert.equal(packed.id, 10);
});

test("sub-category rule beats parent rule, parent covers new sub-categories", () => {
  assert.equal(matchHsnRule(rules, categories, { categoryIds: [2], values: {} }).id, 10);
  const withNew = [...categories, { id: 5, parent_id: 1, name: "Atta" }];
  assert.equal(matchHsnRule(rules, withNew, { categoryIds: [5], values: {} }).id, 12);
});

test("no match returns null", () => {
  assert.equal(matchHsnRule(rules, categories, { categoryIds: [4], values: { form: "Dried" } }), null);
  assert.equal(matchHsnRule(rules, categories, { categoryIds: [], values: {} }), null);
});

test("lists categories without a rule", () => {
  const missing = categoriesWithoutRule(categories, rules).map(c => c.name);
  assert.deepEqual(missing, ["Fresh Daily"]);
});

test("conditions text round trip and path", () => {
  assert.deepEqual(parseConditions("form=Fresh; packaging=Loose"), { form: "Fresh", packaging: "Loose" });
  assert.equal(formatConditions({ form: "Fresh" }), "form=Fresh");
  assert.equal(categoryPath(categories, 2), "Grocery > Rice");
});
