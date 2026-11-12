import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

const workspace = readFileSync(new URL("../../src/features/identity/IdentityWorkspace.jsx", import.meta.url), "utf8");

test("identity workspace can request owner, director, representative and vendor-user links", () => {
  assert.match(workspace, /Request an organisation relationship/);
  assert.match(workspace, /requester_party_id/);
  assert.match(workspace, /request_type: "organisation_relationship"/);
  assert.match(workspace, /relationship_type/);
  for (const type of ["owner", "director", "representative", "authorised_vendor_user"]) {
    assert.match(workspace, new RegExp(type));
  }
});
