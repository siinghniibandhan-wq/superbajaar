import test from "node:test";
import assert from "node:assert/strict";
import { buildMonthlyTrend } from "../../src/features/dashboard/monthlyTrend.js";

test("buildMonthlyTrend normalises monthly income and expense series", () => {
  const result = buildMonthlyTrend([
    { month: "2026-04", income: "12000", expense: 5000 },
    { month: "2026-05", income: 9000, expense: 7000 },
  ]);
  assert.deepEqual(result.labels, ["2026-04", "2026-05"]);
  assert.deepEqual(result.income, [12000, 9000]);
  assert.deepEqual(result.expenses, [5000, 7000]);
  assert.equal(result.maxValue, 12000);
});

test("buildMonthlyTrend handles empty and invalid values without NaN", () => {
  const result = buildMonthlyTrend([{ month: "2026-06", income: "bad", expense: null }]);
  assert.deepEqual(result.income, [0]);
  assert.deepEqual(result.expenses, [0]);
  assert.equal(result.maxValue, 1);
});
