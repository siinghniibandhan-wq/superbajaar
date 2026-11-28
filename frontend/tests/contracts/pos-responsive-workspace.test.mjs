import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

const workspace = readFileSync(new URL("../../src/features/pos/POSWorkspace.jsx", import.meta.url), "utf8");
const styles = readFileSync(new URL("../../src/features/pos/POSWorkspace.css", import.meta.url), "utf8");

test("POS checkout exposes mobile Catalogue, Cart and Pay steps", () => {
  assert.match(workspace, /mobileCheckoutTab/);
  assert.match(workspace, /aria-label="POS checkout steps"/);
  assert.match(workspace, />Items</);
  assert.match(workspace, />Cart \(/);
  assert.match(workspace, />Pay</);
});

test("POS mobile steps switch the visible checkout panel without replacing desktop panels", () => {
  assert.match(workspace, /sb-pos-mobile-step/);
  assert.match(workspace, /sb-pos-cart-panel/);
  assert.match(workspace, /sb-pos-payment-panel/);
  assert.match(styles, /\.sb-pos-mobile-step/);
  assert.match(styles, /\.sb-pos-products/);
  assert.match(styles, /@media\s*\(max-width:\s*760px\)/);
});

test("POS responsive layout preserves desktop split view and prevents narrow-screen overflow", () => {
  assert.match(styles, /grid-template-columns:\s*minmax\(0,1\.5fr\)\s+minmax\(340px,\.9fr\)/);
  assert.match(styles, /@media\s*\(max-width:\s*760px\)/);
  assert.match(styles, /min-width:\s*0/);
  assert.match(styles, /overflow-wrap:\s*anywhere/);
});

test("responsive presentation retains the existing register, shift and checkout API flows", () => {
  assert.match(workspace, /apiRequest\("\/orders"/);
  assert.match(workspace, /\/registers\/" \+ selectedRegisterId \+ "\/open/);
  assert.match(workspace, /confirm-cash/);
  assert.match(workspace, /checkout_idempotency_key/);
});


test("POS sales history exposes server-side search, date, register and tender filters", () => {
  assert.match(workspace, /salesFilters/);
  assert.match(workspace, /date_from/);
  assert.match(workspace, /date_to/);
  assert.match(workspace, /payment_method/);
  assert.match(workspace, /register_id/);
  assert.match(workspace, /apiRequest\("\/pos\/sales\?"/);
  assert.match(workspace, /Apply filters/);
  assert.match(workspace, /Clear/);
});


test("POS sales history opens server-backed item and payment details", () => {
  assert.match(workspace, /openSaleDetails/);
  assert.match(workspace, /apiRequest\("\/pos\/sales\/" \+ saleId\)/);
  assert.match(workspace, /selectedSale\.lines/);
  assert.match(workspace, /selectedSale\.payments/);
  assert.match(workspace, /Close details/);
});


test("POS sales history paginates server-filtered results", () => {
  assert.match(workspace, /salesOffset/);
  assert.match(workspace, /offset: String\(offset\)/);
  assert.match(workspace, />Previous</);
  assert.match(workspace, />Next</);
});
