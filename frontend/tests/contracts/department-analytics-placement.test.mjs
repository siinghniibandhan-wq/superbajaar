import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';

const root = new URL('../../src/', import.meta.url);
const read = path => readFileSync(new URL(path, root), 'utf8');
const router = read('app/router.jsx');

test('Inventory, CRM, POS, Accounting and HR expose analytics within their own workspaces', () => {
  const inventory = read('features/inventory/InventoryWorkspace.jsx');
  const pos = read('features/pos/POSWorkspace.jsx');
  const accounting = read('features/accounting/AccountingWorkspace.jsx');
  const hr = read('features/hr/HRWorkspace.jsx');
  assert.match(inventory, /\/inventory\/overview/);
  assert.match(router, /ModuleDataOverview moduleId="customers"/);
  assert.match(pos, /\/pos\/summary/);
  assert.match(accounting, /key: "overview", label: "Overview"/);
  assert.match(hr, /tab==="overview"/);
});

test('Master Dashboard remains a separate cross-module overview', () => {
  const dashboard = read('features/dashboard/DashboardWorkspace.jsx');
  assert.match(router, /dashboard: \(\{ onOpen, permissions \}\) => <DashboardWorkspace onOpen=\{onOpen\} permissions=\{permissions\}/);
  assert.match(dashboard, /Department and module health/);
  assert.match(dashboard, /14 business modules/);
});
