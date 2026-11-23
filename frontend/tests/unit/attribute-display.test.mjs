import test from "node:test";
import assert from "node:assert/strict";
import { DISPLAY_STYLES, defaultDisplayType, normalizeDisplayType, displayStyleLabel } from "../../src/features/catalogue/attributeDisplay.js";

test("no display style is a dropdown", () => {
  for (const styles of Object.values(DISPLAY_STYLES)) assert.ok(styles.every(s => s.value !== "dropdown"));
});
test("defaults are selectors", () => {
  assert.equal(defaultDisplayType("text"), "button");
  assert.equal(defaultDisplayType("colour"), "colour");
  assert.equal(defaultDisplayType("image"), "image");
});
test("legacy and incompatible values fall back to the default", () => {
  assert.equal(normalizeDisplayType("dropdown", "text"), "button");
  assert.equal(normalizeDisplayType(undefined, "colour"), "colour");
  assert.equal(normalizeDisplayType("colour", "text"), "button");
  assert.equal(normalizeDisplayType("circle", "text"), "circle");
  assert.equal(displayStyleLabel("dropdown", "text"), "Pill buttons");
});
test("every first style equals the default", () => {
  for (const type of ["text", "colour", "image"]) assert.equal(DISPLAY_STYLES[type][0].value, defaultDisplayType(type));
});
