import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

const workspace = readFileSync(new URL("../../src/features/identity/IdentityWorkspace.jsx", import.meta.url), "utf8");
const api = readFileSync(new URL("../../../backend/app/api/identity.py", import.meta.url), "utf8");
const service = readFileSync(new URL("../../../backend/app/services/identity.py", import.meta.url), "utf8");

test("identity register records reviewed contact verification with an audit event", () => {
  assert.match(workspace, /identity\/contacts\/.*\/verify/);
  assert.match(workspace, /Record contact verification/);
  assert.match(api, /def verify_contact/);
  assert.match(api, /_admin\(request\)/);
  assert.match(service, /event_type="contact_verified"/);
  assert.match(workspace, /identity\/relationships\/.*\/revoke/);
  assert.match(workspace, /Revoke relationship/);
  assert.match(api, /def revoke_relationship/);
  assert.match(service, /event_type="relationship_revoked"/);
});

test("contact verification requires an evidence method and documented reason", () => {
  assert.match(api, /class ContactVerifyIn/);
  assert.match(api, /document_review\|in_person\|verified_account\|business_registry/);
  assert.match(service, /verification_status IN \('unverified','expired'\)/);
});
