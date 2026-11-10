import test from "node:test";
import assert from "node:assert/strict";

import { exportStatutoryRemittancesCsv } from "../../src/features/hr/hrStatutoryExport.js";

test("exports statutory remittance reconciliation fields", () => {
  const csv = exportStatutoryRemittancesCsv([{
    id: 21,
    payroll_period_start: "2026-10-01",
    payroll_period_end: "2026-10-31",
    display_name: "Super Bajaar Retail Private Limited",
    state_code: "BR",
    component: "pf",
    due_date: "2026-11-15",
    employee_amount: "1800.00",
    employer_amount: "1800.00",
    total_amount: "3600.00",
    status: "filed",
    challan_reference: "PF-CH-2026-10",
  }]);

  assert.match(csv, /^\uFEFFRemittance ID,Payroll period start/);
  assert.match(csv, /Super Bajaar Retail Private Limited,BR,pf,2026-11-15,1800\.00,1800\.00,3600\.00,filed,PF-CH-2026-10/);
});

test("neutralises spreadsheet formula prefixes in challan references", () => {
  const csv = exportStatutoryRemittancesCsv([{
    id: 22,
    challan_reference: '=HYPERLINK("https://bad.example","click")',
  }]);
  assert.match(csv, /"'=HYPERLINK\(""https:\/\/bad\.example"",""click""\)"/);
});
