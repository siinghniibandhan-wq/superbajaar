import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

const source = readFileSync(new URL("../../src/app/Storefront.jsx", import.meta.url), "utf8");

test("homepage exposes quick-commerce mobile navigation", () => {
  assert.match(source, /className="storefront-mobile-nav"/);
  assert.match(source, /aria-label="Mobile shopping navigation"/);
  assert.match(source, />Categories</);
  assert.match(source, />Orders</);
});

test("homepage communicates delivery availability without promising an unsupported ETA", () => {
  assert.match(source, /storefront-delivery-note/);
  assert.match(source, /Check delivery availability/);
});
