function requiredText(value, label) {
  const text = String(value ?? "").trim();
  if (!text) throw new Error(`${label} is required.`);
  return text;
}

function optionalText(value) {
  const text = String(value ?? "").trim();
  return text || null;
}

function validIsoDate(value, label, required = false) {
  const text = String(value ?? "").trim();
  if (!text) {
    if (required) throw new Error(`${label} is required.`);
    return null;
  }
  const parsed = new Date(`${text}T00:00:00Z`);
  if (!/^\d{4}-\d{2}-\d{2}$/.test(text) || Number.isNaN(parsed.valueOf()) || parsed.toISOString().slice(0, 10) !== text) {
    throw new Error(`Enter a valid ${label.toLowerCase()}.`);
  }
  return text;
}

export function buildEventMappingPayload(form) {
  const legalEntityCode = requiredText(form.legal_entity_code, "Legal entity code");
  const sourceModule = requiredText(form.source_module, "Source module");
  const eventType = requiredText(form.event_type, "Event type");
  const lineRole = requiredText(form.line_role, "Posting role");
  const accountId = Number(form.account_id);
  if (!Number.isSafeInteger(accountId) || accountId <= 0) throw new Error("Choose an active ledger account.");
  const effectiveFrom = validIsoDate(form.effective_from, "Effective-from date", true);
  const effectiveTo = validIsoDate(form.effective_to, "Effective-to date");
  if (effectiveTo && effectiveTo < effectiveFrom) throw new Error("Mapping end date cannot precede the start date.");
  const taxComponent = optionalText(form.tax_component);
  if (taxComponent && !["cgst", "sgst", "igst"].includes(taxComponent)) throw new Error("Choose a supported GST tax component.");
  return {
    legal_entity_code: legalEntityCode,
    source_module: sourceModule,
    event_type: eventType,
    line_role: lineRole,
    account_id: accountId,
    tax_component: taxComponent,
    cost_centre: optionalText(form.cost_centre),
    effective_from: effectiveFrom,
    effective_to: effectiveTo,
    source_reference: optionalText(form.source_reference),
    notes: optionalText(form.notes),
  };
}
