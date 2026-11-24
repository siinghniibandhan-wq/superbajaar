import test from "node:test";
import assert from "node:assert/strict";
import { quantityOf, sortValuesLowToHigh, orderByList, moveValue, variantIdsInOrder } from "../../src/features/catalogue/variantOrder.js";

test("reads quantities including odd spacing and units", () => {
  assert.equal(quantityOf("0. 250 Kg"), 0.25);
  assert.equal(quantityOf("500 g"), 0.5);
  assert.equal(quantityOf("1 Kg"), 1);
  assert.equal(quantityOf("Large"), null);
});

test("sorts the storefront weights low to high", () => {
  assert.deepEqual(sortValuesLowToHigh(["0.5 Kg", "1 Kg", "0.1 Kg", "0. 250 Kg"]), ["0.1 Kg", "0. 250 Kg", "0.5 Kg", "1 Kg"]);
  assert.deepEqual(sortValuesLowToHigh(["250 g", "1 Kg", "100 g"]), ["100 g", "250 g", "1 Kg"]);
  assert.deepEqual(sortValuesLowToHigh(["Medium", "Large", "Small"]), ["Large", "Medium", "Small"]);
});

test("orders by a saved list and moves values", () => {
  assert.deepEqual(orderByList(["b", "c", "a"], ["a", "b"]), ["a", "b", "c"]);
  assert.deepEqual(moveValue(["a", "b", "c"], "c", -1), ["a", "c", "b"]);
  assert.deepEqual(moveValue(["a", "b", "c"], "a", -1), ["a", "b", "c"]);
});

test("orders variants by attribute value order", () => {
  const variants = [
    { id: 1, sku: "V01", attributes: { weight: "0.5 Kg" } },
    { id: 2, sku: "V02", attributes: { weight: "1 Kg" } },
    { id: 3, sku: "V03", attributes: { weight: "0.1 Kg" } },
    { id: 4, sku: "V04", attributes: { weight: "0. 250 Kg" } },
  ];
  assert.deepEqual(variantIdsInOrder(variants, ["weight"], { weight: ["0.1 Kg", "0. 250 Kg", "0.5 Kg", "1 Kg"] }), [3, 4, 1, 2]);
});
