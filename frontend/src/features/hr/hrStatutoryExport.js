const COLUMNS = [
  ["id", "Remittance ID"],
  ["payroll_period_start", "Payroll period start"],
  ["payroll_period_end", "Payroll period end"],
  ["display_name", "Legal establishment"],
  ["state_code", "State code"],
  ["component", "Statutory component"],
  ["due_date", "Due date"],
  ["employee_amount", "Employee amount (INR)"],
  ["employer_amount", "Employer amount (INR)"],
  ["total_amount", "Total remittance (INR)"],
  ["status", "Status"],
  ["challan_reference", "Challan reference"],
  ["paid_at", "Paid at"],
  ["filed_at", "Filed at"],
];

const cell = value => {
  let text = value == null ? "" : String(value);
  if (/^[\s]*[=+@\-]/.test(text)) text = "'" + text;
  return /[",\r\n]/.test(text) ? '"' + text.replaceAll('"', '""') + '"' : text;
};

export function exportStatutoryRemittancesCsv(items = []) {
  const header = COLUMNS.map(([, label]) => cell(label)).join(",");
  const rows = items.map(item => COLUMNS.map(([key]) => cell(item[key])).join(","));
  return "\uFEFF" + [header, ...rows].join("\r\n");
}
