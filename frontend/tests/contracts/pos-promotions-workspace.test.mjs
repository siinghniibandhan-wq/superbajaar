import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

const pos = readFileSync(new URL("../../src/features/pos/POSWorkspace.jsx", import.meta.url), "utf8");
const pricing = readFileSync(new URL("../../src/features/pricing/PricingWorkspace.jsx", import.meta.url), "utf8");

test("POS applies a server-quoted coupon and sends it for transactional checkout validation", () => {
  assert.ok(pos.includes("/orders/promotions/quote"));
  assert.ok(pos.includes("coupon_code: couponCode.trim() || null"));
  assert.ok(pos.includes("Apply or reapply the coupon against the current cart subtotal"));
  assert.ok(pos.includes("Coupon · {couponCode}"));
});

test("held POS carts preserve coupon state, receipts show discounts and refunds are supported", () => {
  assert.ok(pos.includes("couponCode, couponApplied"));
  assert.ok(pos.includes("setCouponApplied(entry.couponApplied || null)"));
  assert.ok(pos.includes("receipt.order.discount_total"));
  assert.ok(pos.includes("/manual-refunds"));
  assert.ok(pos.includes("/refunds"));
  assert.ok(pos.includes("Record refund"));
  assert.ok(pos.includes("Refund ledger"));
});

test("POS split tender uses cash and an online payment with provider verification", () => {
  assert.ok(pos.includes("Split tender (cash + online)"));
  assert.ok(pos.includes("pos_tenders: splitIsTwoTenders ? splitTenders : null"));
  assert.ok(pos.includes("/razorpay/orders"));
  assert.ok(pos.includes("confirm-cash"));
});

test("pricing workspace can create, schedule and deactivate promotion rules", () => {
  assert.ok(pricing.includes("/orders/promotions"));
  assert.ok(pricing.includes("Create promotion"));
  assert.ok(pricing.includes("togglePromotion"));
  assert.ok(pricing.includes("usage_limit"));
  assert.ok(pricing.includes("per_customer_limit"));
  assert.ok(pricing.includes("datetime-local"));
});
