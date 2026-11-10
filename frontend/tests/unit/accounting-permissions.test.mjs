import test from "node:test";
import assert from "node:assert/strict";

import {
  canWriteAccounting,
  isAccountingSchemaUnavailableError,
} from "../../src/features/accounting/accountingPermissions.js";

test("Super Admin and Admin can write Accounting entries", () => {
  assert.equal(canWriteAccounting("super_admin"), true);
  assert.equal(canWriteAccounting("admin"), true);
});

test("Manager, Staff and Viewer remain read-only", () => {
  for (const role of ["manager", "staff", "viewer", "", null, undefined]) {
    assert.equal(canWriteAccounting(role), false);
  }
});

test("role checks are case- and whitespace-tolerant", () => {
  assert.equal(canWriteAccounting("  SUPER_ADMIN "), true);
  assert.equal(canWriteAccounting(" Admin "), true);
});

test("an Accounting permission error is not classified as a missing migration", () => {
  assert.equal(
    isAccountingSchemaUnavailableError("Accounting is restricted to Super Admin, Admin and manager roles"),
    false,
  );
});

test("an unrelated Accounting API error is not classified as a missing migration", () => {
  assert.equal(isAccountingSchemaUnavailableError("Accounting database is unavailable"), false);
});

test("explicit migration readiness errors are classified correctly", () => {
  assert.equal(
    isAccountingSchemaUnavailableError("Accounting storage is not ready; apply migration 015_accounting_ledger.sql"),
    true,
  );
  assert.equal(
    isAccountingSchemaUnavailableError('relation "accounting_accounts" does not exist'),
    true,
  );
  assert.equal(isAccountingSchemaUnavailableError("undefined table accounting_vouchers"), true);
});
