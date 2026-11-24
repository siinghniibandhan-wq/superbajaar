import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

const read = path => readFileSync(new URL("../../src/" + path, import.meta.url), "utf8");

test("category pages load admin hero images and show them in a slider", () => {
  const storefront = read("app/Storefront.jsx");
  assert.match(storefront, /\/catalogue\/category-hero-images/);
  assert.match(storefront, /<CategoryHeroSlider /);
  // Categories without images keep the original decorative hero.
  assert.match(storefront, /storefront-category-hero-art/);
});

test("admin Catalogue has a Category banners tab", () => {
  const workspace = read("features/catalogue/CatalogueWorkspace.jsx");
  assert.match(workspace, /<CategoryHeroPanel categories=\{categories\}/);
  const panel = read("features/catalogue/CategoryHeroPanel.jsx");
  for (const part of ["/hero-images\"", "\"/upload\"", "/reorder", "method: \"DELETE\""]) assert.ok(panel.includes(part), part);
});
