import test from "node:test";
import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";

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

test("storefront requests an authenticated redemption quote and sends the chosen coins", async () => {
  const source = await readFile(new URL("../../src/app/Storefront.jsx", import.meta.url), "utf8");
  assert.match(source, /\/loyalty\/customer\/redemption-quote\?amount=/);
  assert.match(source, /redeem_coins:\s*redeemableCoins/);
  assert.doesNotMatch(source, /Customer redemption at checkout is not enabled yet/);
});
