import test from "node:test";
import assert from "node:assert/strict";

import { clampRedeemCoins } from "../../src/features/loyalty/checkout.js";

test("keeps a requested redemption within the quoted maximum", () => {
  assert.equal(clampRedeemCoins(25, 40), 25);
  assert.equal(clampRedeemCoins(75, 40), 40);
});

test("normalizes invalid, negative and fractional coin requests", () => {
  assert.equal(clampRedeemCoins(-5, 40), 0);
  assert.equal(clampRedeemCoins(4.9, 40), 4);
  assert.equal(clampRedeemCoins("not-a-number", 40), 0);
  assert.equal(clampRedeemCoins(5, 0), 0);
});
