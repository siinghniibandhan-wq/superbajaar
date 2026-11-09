
import test from "node:test";
import assert from "node:assert/strict";
import { buildEventMappingPayload } from "../../src/features/accounting/accountingMapping.js";

test("mapping draft trims identifiers and converts optional values to null", () => {
  const payload = buildEventMappingPayload({
    legal_entity_code: " SB-BR ", source_module: " inventory ", event_type: " qc_acceptance ",
    line_role: " inventory_asset ", account_id: "1200", tax_component: "", cost_centre: " ",
    effective_from: "2026-11-07", effective_to: "", source_reference: " GRN QC ", notes: " reviewed ",
  });
  assert.deepEqual(payload, {
    legal_entity_code: "SB-BR", source_module: "inventory", event_type: "qc_acceptance",
    line_role: "inventory_asset", account_id: 1200, tax_component: null, cost_centre: null,
    effective_from: "2026-11-07", effective_to: null, source_reference: "GRN QC", notes: "reviewed",
  });
});

test("mapping draft rejects missing identifiers and invalid account IDs", () => {
  assert.throws(() => buildEventMappingPayload({}), /legal entity code/i);
  assert.throws(() => buildEventMappingPayload({
    legal_entity_code: "DEFAULT", source_module: "inventory", event_type: "qc_acceptance",
    line_role: "inventory_asset", account_id: "0", effective_from: "2026-11-07",
  }), /active ledger account/i);
});

test("mapping draft rejects malformed or reversed effective periods", () => {
  const base = { legal_entity_code: "DEFAULT", source_module: "inventory", event_type: "qc_acceptance", line_role: "inventory_asset", account_id: "1200", effective_from: "2026-11-07" };
  assert.throws(() => buildEventMappingPayload({ ...base, effective_from: "07-11-2026" }), /valid effective-from date/i);
  assert.throws(() => buildEventMappingPayload({ ...base, effective_to: "2026-11-06" }), /end date cannot precede/i);
});
