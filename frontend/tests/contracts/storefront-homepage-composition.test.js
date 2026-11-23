import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

const source = readFileSync(new URL("../../src/app/Storefront.jsx", import.meta.url), "utf8");
const styles = readFileSync(new URL("../../src/app/storefront.css", import.meta.url), "utf8");

test("homepage does not render empty discovery carousels", () => {
  assert.match(source, /function renderDiscoverySection\([\s\S]*?if\s*\(!items\.length\)\s*return\s+null/);
});

test("homepage shows one coherent catalogue empty state instead of three placeholder panels", () => {
  assert.match(source, /className="storefront-home-empty"/);
  assert.match(source, /No products are available to shop just yet/);
  assert.match(source, /!displayedVariants\.length\s*&&\s*!newArrivals\.length\s*&&\s*!recentVariants\.length/);
  assert.doesNotMatch(source, /bestSellers\.length\s*\?\s*bestSellers\s*:\s*displayedVariants\.slice\(0,\s*8\)/);
});

test("homepage sections use a shared compact rhythm on mobile", () => {
  assert.match(styles, /\.storefront-home-empty/);
  assert.match(styles, /\.storefront-home-section/);
  assert.match(styles, /@media\s*\(max-width:\s*760px\)/);
});
