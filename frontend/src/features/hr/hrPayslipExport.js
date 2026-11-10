const CSV_COLUMNS = [
  ["period_start", "Pay period start"],
  ["period_end", "Pay period end"],
  ["gross_earnings", "Gross earnings (INR)"],
  ["reimbursements", "Reimbursements (INR)"],
  ["deductions", "Employee deductions (INR)"],
  ["employer_contributions", "Employer contributions (INR)"],
  ["net_pay", "Net pay (INR)"],
  ["basic", "Basic (INR)"],
  ["hra", "HRA (INR)"],
  ["special_allowance", "Special allowance (INR)"],
  ["other_allowance", "Other allowance (INR)"],
  ["manual_deduction", "Manual deduction (INR)"],
  ["manual_note", "Manual deduction reason"],
  ["pf_employee", "PF employee (INR)"],
  ["pf_employer", "PF employer (INR)"],
  ["esi_employee", "ESI employee (INR)"],
  ["esi_employer", "ESI employer (INR)"],
  ["pt_employee", "PT employee (INR)"],
  ["pt_employer", "PT employer (INR)"],
  ["tds_employee", "TDS employee (INR)"],
  ["tds_employer", "TDS employer (INR)"],
];

const csvCell = value => {
  let text = value == null ? "" : String(value);
  if (/^[\s]*[=+@\-]/.test(text)) text = "'" + text;
  return /[",\r\n]/.test(text) ? '"' + text.replaceAll('"', '""') + '"' : text;
};

const componentAmount = (statutory, component, side) =>
  statutory?.[component]?.[side] ?? "";

export function exportPayslipsCsv(payslips = [], { includeEmployee = false } = {}) {
  const columns = includeEmployee
    ? [["employee_code", "Employee code"], ["employee_name", "Employee name"], ...CSV_COLUMNS]
    : CSV_COLUMNS;
  const header = columns.map(([, label]) => csvCell(label)).join(",");
  const rows = payslips.map(payslip => {
    const earnings = payslip.earnings_breakdown || {};
    const deductions = payslip.deduction_breakdown || {};
    const statutory = deductions.statutory || {};
    const values = {
      ...payslip,
      employee_name: [payslip.first_name, payslip.last_name].filter(Boolean).join(" "),
      basic: earnings.basic,
      hra: earnings.hra,
      special_allowance: earnings.special_allowance,
      other_allowance: earnings.other_allowance,
      manual_deduction: deductions.manual_deduction,
      manual_note: deductions.manual_note,
      pf_employee: componentAmount(statutory, "pf", "employee_amount"),
      pf_employer: componentAmount(statutory, "pf", "employer_amount"),
      esi_employee: componentAmount(statutory, "esi", "employee_amount"),
      esi_employer: componentAmount(statutory, "esi", "employer_amount"),
      pt_employee: componentAmount(statutory, "pt", "employee_amount"),
      pt_employer: componentAmount(statutory, "pt", "employer_amount"),
      tds_employee: componentAmount(statutory, "tds", "employee_amount"),
      tds_employer: componentAmount(statutory, "tds", "employer_amount"),
    };
    return columns.map(([key]) => csvCell(values[key])).join(",");
  });
  return "\uFEFF" + [header, ...rows].join("\r\n");
}
