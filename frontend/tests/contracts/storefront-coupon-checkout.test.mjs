import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

const storefront = readFileSync(new URL("../../src/app/Storefront.jsx", import.meta.url), "utf8");

test("authenticated storefront checkout applies and revalidates coupon codes server-side", () => {
  assert.ok(storefront.includes("applyCheckoutCoupon"));
  assert.ok(storefront.includes("/orders/promotions/quote"));
  assert.ok(storefront.includes("coupon_code: validCouponQuote ? couponCode.trim().toUpperCase() : null"));
  assert.ok(storefront.includes("Apply or reapply your coupon against the current basket"));
});

test("storefront coupon discount reduces the Super Coin redemption quote and final payable", () => {
  assert.ok(storefront.includes("const total = Math.max(0, subtotal - couponDiscount)"));
  assert.ok(storefront.includes("/loyalty/customer/redemption-quote?amount="));
  assert.ok(storefront.includes("Coupon discount"));
  assert.ok(storefront.includes("Super Coin discount"));
});
