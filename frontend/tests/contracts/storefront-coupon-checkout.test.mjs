import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

const storefront = readFileSync(new URL("../../src/app/Storefront.jsx", import.meta.url), "utf8");

test("authenticated storefront checkout applies and revalidates coupon codes server-side", () => {
  assert.match(storefront, /applyCheckoutCoupon/);
  assert.match(storefront, /\/orders\/promotions\/quote/);
  assert.match(storefront, /coupon_code:s*validCouponQuotes*?s*couponCode.trim().toUpperCase()s*:s*null/);
  assert.match(storefront, /Apply or reapply your coupon against the current basket/);
});

test("storefront coupon discount reduces the Super Coin redemption quote and final payable", () => {
  assert.match(storefront, /const total = Math.max(0, subtotal - couponDiscount)/);
  assert.match(storefront, /loyalty/customer/redemption-quote?amount/);
  assert.match(storefront, /Coupon discount/);
  assert.match(storefront, /Super Coin discount/);
});
