function parseJsonObject(value, label) {
  let parsed;
  try {
    parsed = JSON.parse(value || "{}");
  } catch {
    throw new Error(label + " must be valid JSON objects.");
  }
  if (!parsed || typeof parsed !== "object" || Array.isArray(parsed)) {
    throw new Error(label + " must be valid JSON objects.");
  }
  return parsed;
}

export function parsePayrollInputs(deductionsText, notesText) {
  const rawDeductions = parseJsonObject(deductionsText, "Manual deductions");
  const rawNotes = parseJsonObject(notesText, "Deduction notes");
  const deductions = {};
  const notes = {};

  for (const [employeeId, rawAmount] of Object.entries(rawDeductions)) {
    if (!/^[1-9]\d*$/.test(employeeId)) {
      throw new Error("Manual deduction keys must be positive employee IDs.");
    }
    if (!(typeof rawAmount === "number" || typeof rawAmount === "string") || String(rawAmount).trim() === "") {
      throw new Error("Each manual deduction must be a non-negative finite amount.");
    }
    const amount = Number(rawAmount);
    if (!Number.isFinite(amount) || amount < 0) {
      throw new Error("Each manual deduction must be a non-negative finite amount.");
    }
    deductions[employeeId] = amount;
  }

  for (const [employeeId, note] of Object.entries(rawNotes)) {
    if (!/^[1-9]\d*$/.test(employeeId) || typeof note !== "string") {
      throw new Error("Deduction notes must use positive employee IDs and notes must be text.");
    }
    notes[employeeId] = note.trim();
  }

  return { deductions_by_employee: deductions, deduction_notes: notes };
}
