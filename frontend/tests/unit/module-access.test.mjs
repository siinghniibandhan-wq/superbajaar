import test from "node:test";
import assert from "node:assert/strict";

import { canReadModule, filterNavigationGroups } from "../../src/app/moduleAccess.js";

const groups = [
  { title: "Commerce", items: [{ id: "catalogue" }, { id: "orders" }] },
  { title: "Business", items: [{ id: "accounting" }, { id: "settings" }] },
];

test("navigation exposes only modules with explicit read permission", () => {
  const visible = filterNavigationGroups(groups, {
    catalogue: { read: true },
    accounting: { read: false },
    user_management: { read: true },
  });
  assert.deepEqual(visible.map(group => group.items.map(item => item.id)), [["catalogue"], ["settings"]]);
});

test("unmapped and unassigned modules are denied by default", () => {
  assert.equal(canReadModule("orders", {}), false);
  assert.equal(canReadModule("unknown", { unknown: { read: true } }), false);
});

test("reports and purchasing navigation map to their central permission keys", () => {
  assert.equal(canReadModule("reports", { dashboard: { read: true } }), true);
  assert.equal(canReadModule("purchase", { purchasing: { read: true } }), true);
});
