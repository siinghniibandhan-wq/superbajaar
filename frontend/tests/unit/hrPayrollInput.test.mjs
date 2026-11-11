import test from "node:test";
import assert from "node:assert/strict";

import { parsePayrollInputs } from "../../src/features/hr/hrPayrollInput.js";

test("parses valid employee deductions and notes", () => {
  assert.deepEqual(parsePayrollInputs('{"12":"150.50"}', '{"12":"Approved advance recovery"}'), {
    deductions_by_employee: { "12": 150.5 },
    deduction_notes: { "12": "Approved advance recovery" },
  });
});

test("rejects malformed JSON without throwing an uncaught form error", () => {
  assert.throws(() => parsePayrollInputs("{", "{}"), /valid JSON objects/);
});

test("rejects arrays and non-object payroll payloads", () => {
  assert.throws(() => parsePayrollInputs("[]", "{}"), /valid JSON objects/);
  assert.throws(() => parsePayrollInputs("{}", "null"), /valid JSON objects/);
});

test("rejects negative, non-finite, and non-numeric deductions", () => {
  for (const value of ['{"12":-1}', '{"12":"NaN"}', '{"12":"abc"}', '{"12":null}', '{"12":""}', '{"12":true}']) {
    assert.throws(() => parsePayrollInputs(value, "{}"), /non-negative finite amount/);
  }
});

test("requires deduction notes to be strings", () => {
  assert.throws(() => parsePayrollInputs("{}", '{"12":123}'), /notes must be text/);
});

test("requires a meaningful reason for every positive manual deduction", () => {
  assert.throws(() => parsePayrollInputs('{"12":100}', "{}"), /reason of at least 5 characters/);
  assert.throws(() => parsePayrollInputs('{"12":100}', '{"12":"no"}'), /reason of at least 5 characters/);
});
