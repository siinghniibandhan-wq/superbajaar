function positiveInteger(value, label) {
  const number = Number(value);
  if (!Number.isInteger(number) || number <= 0) throw new Error(`${label} must be a valid positive ID.`);
  return number;
}

function positiveQuantity(value) {
  const number = Number(value);
  if (!Number.isFinite(number) || number <= 0) throw new Error('Each requisition line needs a quantity greater than zero.');
  return number;
}

export function buildRequisitionPayload({
  locationId, department = '', costCentre = '', requiredBy = '', justification = '', lines = [],
}) {
  const cleanJustification = String(justification || '').trim();
  if (cleanJustification.length < 3) throw new Error('Enter a justification of at least 3 characters.');
  if (!Array.isArray(lines) || lines.length === 0) throw new Error('Add at least one requisition line.');
  const normalizedLines = lines.map((line) => {
    const variantId = positiveInteger(line.variant_id, 'Product variant');
    const quantity = positiveQuantity(line.quantity);
    const estimatedCost = line.estimated_unit_cost === '' || line.estimated_unit_cost == null
      ? null : Number(line.estimated_unit_cost);
    if (estimatedCost != null && (!Number.isFinite(estimatedCost) || estimatedCost < 0)) {
      throw new Error('Estimated unit cost must be zero or greater.');
    }
    return {
      variant_id: variantId,
      quantity,
      estimated_unit_cost: estimatedCost,
      specification: String(line.specification || '').trim() || null,
    };
  });
  if (new Set(normalizedLines.map((line) => line.variant_id)).size !== normalizedLines.length) {
    throw new Error('Each variant may appear once per requisition.');
  }
  return {
    location_id: positiveInteger(locationId, 'Stock location'),
    department: String(department || '').trim() || null,
    cost_centre: String(costCentre || '').trim() || null,
    required_by: String(requiredBy || '').trim() || null,
    justification: cleanJustification,
    lines: normalizedLines,
  };
}

export function buildRfqPayload({ requisitionId, supplierIds = [], responseDueAt = '', terms = '' }) {
  const requisition_id = positiveInteger(requisitionId, 'Approved requisition');
  if (!Array.isArray(supplierIds) || supplierIds.length === 0) throw new Error('Select at least one supplier for the RFQ.');
  const supplier_ids = supplierIds.map((id) => positiveInteger(id, 'Supplier'));
  if (new Set(supplier_ids).size !== supplier_ids.length) throw new Error('Select unique valid supplier IDs.');
  return {
    requisition_id,
    supplier_ids,
    response_due_at: String(responseDueAt || '').trim() || null,
    terms: String(terms || '').trim() || null,
  };
}
