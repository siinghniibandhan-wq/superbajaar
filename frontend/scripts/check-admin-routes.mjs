import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

const source = readFileSync(new URL("../src/app/router.jsx", import.meta.url), "utf8");
const groupsMatch = source.match(/const groups = \[([\s\S]*?)\n\];/);
const routesMatch = source.match(/const workspaceRoutes = \{([\s\S]*?)\n\};/);
assert.ok(groupsMatch, "admin navigation groups must exist");
assert.ok(routesMatch, "explicit workspace route registry must exist");

const ids = [...groupsMatch[1].matchAll(/id: "([^"]+)"/g)].map(match => match[1]);
const routeIds = [...routesMatch[1].matchAll(/^\s{2}([a-z][a-z0-9]*):/gm)].map(match => match[1]);
assert.equal(new Set(ids).size, ids.length, "navigation module IDs must be unique");
assert.deepEqual([...ids].sort(), [...routeIds].sort(), "every navigable module must have exactly one registered route");
assert.ok(source.includes("function UnavailableWorkspace"), "unknown IDs must have an explicit unavailable state");
assert.ok(!source.includes("This module is not implemented yet"), "old unfinished-workspace fallback must be removed");
assert.ok(!source.includes('["super_admin", "owner", "admin"].includes(role)'), "Owner must not be an Admin Console role");
assert.ok(!source.includes('role === "manager"'), "Manager access must be driven by module permissions, not a hardcoded HR-only shell");
assert.ok(source.includes("my-permissions"), "Admin shell must load the signed-in user effective module permissions");
assert.ok(source.includes("groups={visibleGroups}"), "The launcher must render only the filtered module groups");
console.log(`Admin route map OK: ${ids.length} unique navigation modules are registered.`);
