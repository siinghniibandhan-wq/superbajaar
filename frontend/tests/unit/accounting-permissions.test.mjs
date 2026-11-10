import test from "node:test";
import assert from "node:assert/strict";

import { canWriteAccounting, isAccountingSchemaUnavailableError } from "../../src/features/accounting/accountingPermissions.js";

test("Super Admin can post and reverse accounting entries", () => {
  assert.equal(canWriteAccounting("super_admin"), true);
});

test("owner and admin can post and reverse accounting entries", () => {
  assert.equal(canWriteAccounting("owner"), true);
  assert.equal(canWriteAccounting("admin"), true);
});

test("manager and non-administrator roles remain read-only in accounting", () => {
  for (const role of ["manager", "staff", "viewer", "", null, undefined]) {
    assert.equal(canWriteAccounting(role), false);
  }
});

test("an accounting permission denial is not misreported as a missing migration", () => {
  assert.equal(
    isAccountingSchemaUnavailableError("Accounting is restricted to owner, admin and manager roles"),
    false,
  );
});

test("missing accounting relations are identified as a schema readiness issue", () => {
  assert.equal(
    isAccountingSchemaUnavailableError('relation "accounting_accounts" does not exist'),
    true,
  );
  assert.equal(
    isAccountingSchemaUnavailableError("Accounting storage is not ready; apply migration 015_accounting_ledger.sql"),
    true,
  );
});
