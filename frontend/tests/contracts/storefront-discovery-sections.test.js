import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

const source = readFileSync(new URL("../../src/app/Storefront.jsx", import.meta.url), "utf8");

test("homepage uses dedicated Best Sellers, New Arrivals and Recently Viewed shelves", () => {
  assert.match(source, /renderDiscoverySection\("Best Sellers",\s*"Customer favourites, ranked by recorded sales",\s*bestSellers/);
  assert.match(source, /renderDiscoverySection\("New Arrivals"/);
  assert.match(source, /renderDiscoverySection\("Recently Viewed"/);
  assert.doesNotMatch(source, /Popular picks/);
  assert.doesNotMatch(source, /bestSellers\.length\s*\?\s*["']Best Sellers["']\s*:\s*["']Popular picks["']/);
});

test("empty discovery shelves remain hidden rather than showing placeholders", () => {
  assert.match(source, /if\s*\(!items\.length\)\s*return\s+null/);
});
