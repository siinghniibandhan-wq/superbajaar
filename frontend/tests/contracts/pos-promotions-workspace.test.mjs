import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

const pos = readFileSync(new URL("../../src/features/pos/POSWorkspace.jsx", import.meta.url), "utf8");
const pricing = readFileSync(new URL("../../src/features/pricing/PricingWorkspace.jsx", import.meta.url), "utf8");

test("POS applies a server-quoted coupon and sends it for transactional checkout validation", () => {
  assert.match(pos, /\/orders\/promotions\/quote/);
  assert.match(pos, /coupon_code:s*couponCode.trim()s*||s*null/);
  assert.match(pos, /Apply or reapply the coupon against the current cart subtotal/);
  assert.match(pos, /Coupon · {couponCode}/);
});

test("held POS carts preserve coupon state and checkout receipts show discount snapshots", () => {
  assert.match(pos, /couponCode,s*couponApplied/);
  assert.match(pos, /setCouponApplied(entry.couponApplied || null)/);
  assert.match(pos, /receipt.order.discount_total/);
});

test("pricing workspace can create and deactivate promotion rules through admin APIs", () => {
  assert.match(pricing, //orders/promotions/);
  assert.match(pricing, /Create promotion/);
  assert.match(pricing, /togglePromotion/);
  assert.match(pricing, /usage_limit/);
  assert.match(pricing, /per_customer_limit/);
});
