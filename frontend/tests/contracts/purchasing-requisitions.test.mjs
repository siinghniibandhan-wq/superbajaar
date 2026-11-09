import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';

const root = new URL('../../src/features/purchasing/', import.meta.url);
const workspace = readFileSync(new URL('PurchasingWorkspace.jsx', root), 'utf8');

test('Purchasing workspace mounts the requisition workflow without replacing existing tabs', () => {
  assert.match(workspace, /import PurchasingRequestsWorkspace from ['"]\.\/PurchasingRequestsWorkspace\.jsx['"]/);
  assert.match(workspace, /tab === "requests"/);
  for (const existing of ['overview', 'orders', 'suppliers', 'invoices', 'returns']) {
    assert.match(workspace, new RegExp(`tab === "${existing}"`));
  }
});

test('requisition workflow uses canonical lifecycle APIs and server-side decisions', () => {
  const panel = readFileSync(new URL('PurchasingRequestsWorkspace.jsx', root), 'utf8');
  for (const path of ['/purchasing/requisitions', '/submit', '/decision', '/purchasing/rfqs', '/purchasing/quotations']) {
    assert.ok(panel.includes(path), path);
  }
  assert.match(panel, /JSON\.stringify\(/);
  assert.match(panel, /reason/);
  assert.match(panel, /offset|limit/);
});
