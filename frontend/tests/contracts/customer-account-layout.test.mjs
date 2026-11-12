import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

const css = readFileSync(new URL("../../src/app/storefront.css", import.meta.url), "utf8");
const storefront = readFileSync(new URL("../../src/app/Storefront.jsx", import.meta.url), "utf8");

test("customer account uses a wide desktop layout with a stable navigation column", () => {
  assert.match(css, /\.storefront-account-page\s*\{[^}]*max-width:\s*1240px/s);
  assert.match(css, /\.storefront-account-layout\s*\{[^}]*grid-template-columns:\s*240px\s+minmax\(0,\\s*1fr\)/s);
});

test("referral and loyalty panels have dedicated responsive layout hooks", () => {
  assert.match(storefront, /storefront-account-section--referrals/);
  assert.match(storefront, /storefront-account-section--loyalty/);
  assert.match(css, /\.storefront-account-section--referrals/);
  assert.match(css, /\.storefront-account-section--loyalty/);
});

test("account navigation and cards collapse cleanly on narrow screens", () => {
  assert.match(css, /@media\s*\(max-width:\s*760px\)[\s\S]*?\.storefront-account-layout\s*\{[^}]*grid-template-columns:\s*minmax\(0,\\s*1fr\)/);
  assert.match(css, /\.storefront-account-nav\s*\{[^}]*overflow-x:\s*auto/s);
  assert.match(css, /\.storefront-loyalty-summary\s*\{[^}]*grid-template-columns:\s*repeat\(2,minmax\(0,\\s*1fr\)\)/s);
});
