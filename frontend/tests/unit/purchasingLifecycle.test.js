import test from 'node:test';
import assert from 'node:assert/strict';
import { buildRequisitionPayload, buildRfqPayload } from '../../src/features/purchasing/purchasingLifecycle.js';

test('builds a normalized requisition payload and rejects duplicate variants', () => {
  const payload = buildRequisitionPayload({
    locationId: '12', department: 'Operations', costCentre: 'STORE-01', requiredBy: '2026-12-01',
    justification: 'Monthly stock replenishment',
    lines: [{ variant_id: '7', quantity: '2.500', estimated_unit_cost: '19.25', specification: 'Fresh batch' }],
  });
  assert.deepEqual(payload, {
    location_id: 12, department: 'Operations', cost_centre: 'STORE-01', required_by: '2026-12-01',
    justification: 'Monthly stock replenishment',
    lines: [{ variant_id: 7, quantity: 2.5, estimated_unit_cost: 19.25, specification: 'Fresh batch' }],
  });
  assert.throws(() => buildRequisitionPayload({
    locationId: '12', justification: 'Restock',
    lines: [{ variant_id: '7', quantity: '1' }, { variant_id: '7', quantity: '2' }],
  }), /Each variant may appear once/);
});

test('builds an RFQ payload with unique positive supplier IDs', () => {
  assert.deepEqual(buildRfqPayload({
    requisitionId: '4', supplierIds: ['3', '5'], responseDueAt: '2026-11-20T12:00', terms: 'Quote valid 15 days',
  }), {
    requisition_id: 4, supplier_ids: [3, 5], response_due_at: '2026-11-20T12:00', terms: 'Quote valid 15 days',
  });
  assert.throws(() => buildRfqPayload({ requisitionId: '4', supplierIds: ['3', '3'] }), /unique valid supplier/);
});
