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
assert.ok(source.includes('["super_admin", "owner", "admin"].includes(role)'), "Super Admin, owner, and admin must be allowed into the Admin Console");
console.log(`Admin route map OK: ${ids.length} unique navigation modules are registered.`);

const settingsSource = readFileSync(new URL("../src/features/settings/SettingsWorkspace.jsx", import.meta.url), "utf8");
assert.ok(settingsSource.includes('currentUser?.role === "super_admin"'), "Super Admin must see elevated role assignment options");
assert.ok(settingsSource.includes('<option value="super_admin">Super Admin</option>'), "Super Admin must be assignable by a Super Admin");
assert.ok(settingsSource.includes('currentUser?.role === "owner" || currentUser?.role === "super_admin"'), "Owner and Super Admin must see owner/admin assignment options");
