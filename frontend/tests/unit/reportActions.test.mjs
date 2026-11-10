import test from "node:test";
import assert from "node:assert/strict";
import { buildCsv, buildMailto } from "../../src/features/reports/reportActions.js";

test("CSV safely quotes commas, quotes and line breaks", () => {
  assert.equal(buildCsv([["Order", "Customer"], ["A,1", 'A "B"']]), '"Order","Customer"\r\n"A,1","A ""B"""');
});

test("email action encodes subject and report body", () => {
  const url = buildMailto("Monthly report", "Orders: 3\nRevenue: ₹500");
  assert.match(url, /^mailto:\?subject=/);
  assert.match(decodeURIComponent(url), /Orders: 3/);
});
