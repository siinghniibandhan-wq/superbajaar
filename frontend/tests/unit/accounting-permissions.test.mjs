import test from "node:test";
import assert from "node:assert/strict";

import { canWriteAccounting } from "../../src/features/accounting/accountingPermissions.js";

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
