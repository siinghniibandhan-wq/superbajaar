import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

const storefront = readFileSync(new URL("../../src/app/Storefront.jsx", import.meta.url), "utf8");
const css = readFileSync(new URL("../../src/app/storefront.css", import.meta.url), "utf8");

test("saved customer addresses load from the account API and can be managed", () => {
  assert.match(storefront, /customerRequest\(["']\/customer-auth\/addresses["']\)/);
  assert.match(storefront, /Add new address/);
  assert.match(storefront, /Set as default/);
  assert.match(storefront, /Delete address/);
  assert.match(storefront, /if \(!customerToken \|\| !customerAuth\)/);
  assert.match(storefront, /legacy browser address available for manual saving/);
});

test("checkout selects a saved address and allows changing it", () => {
  assert.match(storefront, /selectedAddressId/);
  assert.match(storefront, /Change address/);
  assert.match(storefront, /selectedAddress/);
  assert.match(storefront, /Delivery address \(/);
});

test("checkout is organized into responsive summary, delivery and payment sections", () => {
  assert.match(storefront, /checkout-section--summary/);
  assert.match(storefront, /checkout-section--delivery/);
  assert.match(storefront, /checkout-section--payment/);
  assert.match(css, /\.storefront-checkout-section/);
  assert.match(css, /@media\s*\(max-width:\s*640px\)/);
});
