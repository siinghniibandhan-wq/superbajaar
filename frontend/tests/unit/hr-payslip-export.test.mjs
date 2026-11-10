import test from "node:test";
import assert from "node:assert/strict";

import { exportPayslipsCsv } from "../../src/features/hr/hrPayslipExport.js";

test("exports an employee's payslip with earnings and statutory breakdown", () => {
  const csv = exportPayslipsCsv([{
    period_start: "2026-10-01",
    period_end: "2026-10-31",
    gross_earnings: "42000.00",
    reimbursements: "1500.00",
    deductions: "3500.00",
    employer_contributions: "2400.00",
    net_pay: "40000.00",
    earnings_breakdown: { basic: "30000.00", hra: "12000.00" },
    deduction_breakdown: {
      manual_deduction: "500.00",
      manual_note: "Approved salary advance recovery",
      statutory: { pf: { employee_amount: "1800.00", employer_amount: "1800.00" } },
    },
  }]);

  assert.match(csv, /^\uFEFFPay period start,Pay period end,/);
  assert.match(csv, /2026-10-01,2026-10-31,42000\.00,1500\.00,3500\.00,2400\.00,40000\.00/);
  assert.match(csv, /30000\.00,12000\.00,,,\[\],500\.00,Approved salary advance recovery,1800\.00,1800\.00/);
});

test("includes employee identifiers only for manager exports", () => {
  const payslip = {
    employee_code: "SB-0007",
    first_name: "Asha",
    last_name: "Singh",
    period_start: "2026-10-01",
    period_end: "2026-10-31",
  };
  const employeeCsv = exportPayslipsCsv([payslip]);
  const managerCsv = exportPayslipsCsv([payslip], { includeEmployee: true });

  assert.doesNotMatch(employeeCsv, /Employee code/);
  assert.match(managerCsv, /Employee code,Employee name/);
  assert.match(managerCsv, /SB-0007,Asha Singh/);
});

test("escapes CSV delimiters and neutralises spreadsheet formula prefixes", () => {
  const csv = exportPayslipsCsv([{
    period_start: "2026-10-01",
    period_end: "2026-10-31",
    deduction_breakdown: { manual_note: '=HYPERLINK("https://bad.example","click")' },
  }]);

  assert.match(csv, /"'=HYPERLINK\(""https:\/\/bad\.example"",""click""\)"/);
});


test("exports approved overtime and incentive details in the payslip register", () => {
  const csv = exportPayslipsCsv([{
    period_start: "2026-12-01",
    period_end: "2026-12-31",
    earnings_breakdown: {
      variable_earnings: [{
        type: "overtime",
        amount: "1500.00",
        hours: "10.00",
        hourly_rate: "150.00",
        reason: "Approved weekend coverage",
      }],
    },
  }]);
  assert.match(csv, /Overtime \/ incentives \/ bonuses/);
  assert.match(csv, /overtime/);
  assert.match(csv, /Approved weekend coverage/);
});
