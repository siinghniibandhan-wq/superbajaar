import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

const workspace = readFileSync(new URL("../../src/features/identity/IdentityWorkspace.jsx", import.meta.url), "utf8");
const api = readFileSync(new URL("../../../backend/app/api/identity.py", import.meta.url), "utf8");

test("admin identity workspace exposes a legacy reconciliation report", () => {
  assert.match(workspace, /Legacy reconciliation/);
  assert.match(workspace, /identity\/reconciliation\/preview/);
  assert.match(workspace, /tab === "review" \?/);
  assert.match(workspace, /identity-reconciliation/);
  assert.match(workspace, /item\.request_type === "claim_existing_identity" && !item\.target_sbid/);
  assert.match(api, /manual_review_required/);
});

test("legacy reconciliation is a read-only preview and never merges candidates", () => {
  assert.match(api, /def legacy_reconciliation_preview/);
  assert.match(api, /automatic_linking.*False/);
  assert.match(api, /automatic_merging.*False/);
  assert.match(api, /_admin\(request\)/);
});

test("legacy reconciliation falls back when preferred contact columns are blank", () => {
  const normalizedApi = api.toLowerCase();
  for (const alias of ["ca", "c", "e", "s"]) {
    assert.ok(
      normalizedApi.includes(`nullif(trim(to_jsonb(${alias})->>'`),
      `expected blank-safe contact fallback for ${alias}`,
    );
  }
});


test("admin can resolve an unmatched customer claim to a selected individual SBID", () => {
  assert.match(api, /def resolve_unmatched_claim_target/);
  assert.match(api, /target_party_id/);
  assert.match(api, /target\["party_type"\] != "individual"/);
  assert.match(workspace, /resolveClaimTarget/);
  assert.match(workspace, /Resolve claim target/);
  assert.match(workspace, /identity\/review-queue\/requests\/\$\{id\}\/resolve-target/);
});


test("identity review offers only implemented manual evidence methods", () => {
  assert.match(api, /document_review\|in_person\|verified_account\|business_registry/);
  assert.doesNotMatch(workspace, /value="email_otp"|value="phone_otp"/);
  assert.match(workspace, /value="business_registry"/);
});
