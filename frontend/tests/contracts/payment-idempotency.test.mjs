import test from "node:test";
import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";

const source = await readFile(new URL("../../src/features/payments/PaymentsWorkspace.jsx", import.meta.url), "utf8");

test("manual payment creation reuses a stable idempotency key until success or payload change", () => {
  assert.match(source, /useRef/);
  assert.match(source, /Idempotency-Key/);
  assert.match(source, /idempotencyKeyRef\.current/);
  assert.match(source, /idempotencyKeyRef\.current = null/);
});
