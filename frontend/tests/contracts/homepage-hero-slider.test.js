import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

const read = path => readFileSync(new URL("../../src/" + path, import.meta.url), "utf8");

test("homepage loads admin banner images and shows them in the shared slider", () => {
  const storefront = read("app/Storefront.jsx");
  assert.match(storefront, /\/catalogue\/homepage-hero-images/);
  assert.match(storefront, /<CategoryHeroSlider images=\{homeHeroImages\}/);
  // With no banner images the original decorative hero stays.
  assert.match(storefront, /!homeHeroImages\.length && <section className="storefront-hero storefront-home-hero">/);
});

test("admin banner panel can manage the homepage slider", () => {
  const panel = read("features/catalogue/CategoryHeroPanel.jsx");
  assert.ok(panel.includes("/catalogue/homepage-hero-images"));
  assert.ok(panel.includes('value="home"'));
});
