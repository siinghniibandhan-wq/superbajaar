import assert from "node:assert/strict";
import { readFileSync, readdirSync } from "node:fs";
import { resolve, dirname } from "node:path";
import { fileURLToPath } from "node:url";

const here = dirname(fileURLToPath(import.meta.url));
const frontendRoot = resolve(here, "..");
const repoRoot = resolve(frontendRoot, "..");
const routerSource = readFileSync(resolve(frontendRoot, "src/app/router.jsx"), "utf8");
const backendMain = readFileSync(resolve(repoRoot, "backend/app/main.py"), "utf8");

const groups = routerSource.match(/const groups = \[([\s\S]*?)\n\];/);
const workspaces = routerSource.match(/const workspaceRoutes = \{([\s\S]*?)\n\};/);
assert.ok(groups && workspaces, "navigation groups and workspace registry must exist");
const navIds = [...groups[1].matchAll(/id: "([^\"]+)"/g)].map((m) => m[1]);
const routeIds = [...workspaces[1].matchAll(/^\s{2}([a-z][a-z0-9]*):/gm)].map((m) => m[1]);
assert.equal(new Set(navIds).size, navIds.length, "navigation IDs must be unique");
assert.deepEqual([...navIds].sort(), [...routeIds].sort(), "every navigation ID must have exactly one workspace route");

// Build the set of API prefixes that are both imported and mounted by FastAPI.
const importedRouters = new Map();
for (const match of backendMain.matchAll(/from app\.api\.([a-z_]+) import router as ([a-z_]+)_router/g)) {
  importedRouters.set(match[2], match[1]);
}
if (backendMain.includes("from app.api.payments import router as payments_router, razorpay_router")) {
  importedRouters.set("razorpay", "payments");
}
const mounted = new Set();
for (const match of backendMain.matchAll(/app\.include_router\(([a-z_]+)_router, prefix=settings\.api_prefix\)/g)) {
  const moduleName = importedRouters.get(match[1]);
  assert.ok(moduleName, `mounted router ${match[1]} must have a matching import`);
  mounted.add(moduleName);
}

// Include API path prefixes used in module workspaces. Dynamic suffixes are
// intentionally ignored; this check verifies router-domain coverage, not every
// parameterized operation or HTTP method.
const usedPrefixes = new Set();
const featureRoot = resolve(frontendRoot, "src/features");
function walk(directory) {
  for (const entry of readdirSync(directory, { withFileTypes: true })) {
    const path = resolve(directory, entry.name);
    if (entry.isDirectory()) walk(path);
    else if (/\.(jsx?|tsx?)$/.test(entry.name)) {
      const source = readFileSync(path, "utf8");
      for (const match of source.matchAll(/apiRequest\(\s*["'`]\/([a-z][a-z0-9-]*)/g)) {
        usedPrefixes.add(match[1].replaceAll("-", "_"));
      }
    }
  }
}
walk(featureRoot);
const aliases = new Map([["customer_auth", "customer_auth"], ["razorpay", "payments"]]);
const missing = [...usedPrefixes].filter((prefix) => !mounted.has(aliases.get(prefix) || prefix));
assert.deepEqual(missing, [], `frontend API domains lack registered backend routers: ${missing.join(", ")}`);

console.log(`Module API contract OK: ${navIds.length} workspace routes; ${usedPrefixes.size} API domain prefixes are mounted by FastAPI.`);
