import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

const storefront = readFileSync(new URL("../../src/app/Storefront.jsx", import.meta.url), "utf8");
const panel = readFileSync(new URL("../../src/app/IdentityClaimsPanel.jsx", import.meta.url), "utf8");

test("customer account exposes a dedicated identity claims section", () => {
  assert.match(storefront, /IdentityClaimsPanel/);
  assert.match(storefront, /identity-claims/);
});

test("identity claim panel supports submit and customer-owned status history", () => {
  assert.match(panel, /\/customer-auth\/identity-claims/);
  assert.match(panel, /method:\s*["']POST["']/);
  assert.match(panel, /status/i);
  assert.match(panel, /target_sbid/);
});


test("customer claim history can cancel only unreviewed claims", () => {
  assert.match(panel, /identity-claims\/\$\{claimId\}\/cancel/);
  assert.match(panel, /\["pending", "proof_required"\]\.includes\(item\.status\)/);
  assert.match(panel, /Cancel request/);
});
