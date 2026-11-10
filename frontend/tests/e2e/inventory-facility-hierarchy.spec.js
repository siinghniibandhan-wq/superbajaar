import { test, expect } from "@playwright/test";

test("inventory manager can create and edit internal warehouse addresses without changing facility stock APIs", async ({ page }) => {
  const writes = [];
  let internalLocations = [];
  await page.addInitScript(() => localStorage.setItem("superbajaar.access_token", "owner-inventory-hierarchy-token"));
  await page.route("**/api/**", async route => {
    const permissionRequest = route.request();
    if (new URL(permissionRequest.url()).pathname === "/api/auth/my-permissions") {
      const token = permissionRequest.headers().authorization || "";
      const moduleKeys = ["dashboard", "catalogue", "pricing", "orders", "payments", "inventory", "purchasing", "fulfillment", "delivery", "pos", "crm", "loyalty", "accounting", "hr_payroll", "user_management"];
      const allowedKeys = /manager|employee/i.test(token) ? ["hr_payroll"] : moduleKeys;
      const permissions = Object.fromEntries(allowedKeys.map(key => [key, { read: true }]));
      return route.fulfill({ json: { permissions } });
    }

    const request = route.request();
    const url = new URL(request.url());
    const method = request.method();
    const body = method === "POST" || method === "PUT" ? request.postDataJSON() : undefined;
    if (url.pathname === "/api/auth/me") return route.fulfill({ json: { user: { id: 1, full_name: "Owner", role: "owner" } } });
    if (url.pathname === "/api/health") return route.fulfill({ json: { status: "ok", database: "connected" } });
    if (url.pathname === "/api/inventory/locations") return route.fulfill({ json: { items: [{ id: 9, name: "Patna Central", location_type: "warehouse", is_active: true, is_fulfillable: true, establishment_id: 4 }] } });
    if (url.pathname === "/api/catalogue/products") return route.fulfill({ json: { items: [] } });
    if (["/api/inventory/balances", "/api/inventory/movements", "/api/inventory/cost-layers", "/api/inventory/cost-layer-reconciliation", "/api/inventory/approval-requests"].includes(url.pathname)) return route.fulfill({ json: { items: [] } });
    if (url.pathname === "/api/inventory/overview") return route.fulfill({ json: { totals: {}, movement_groups: [], stock_by_location: [] } });
    if (url.pathname === "/api/hr/establishments") return route.fulfill({ json: { items: [{ id: 4, display_name: "Super Bajaar Bihar", code: "SB-BR" }] } });
    if (url.pathname === "/api/inventory/internal-locations" && method === "GET") return route.fulfill({ json: { items: internalLocations } });
    if (url.pathname === "/api/inventory/internal-locations" && method === "POST") {
      writes.push({ method, body });
      internalLocations = [{ id: 101, facility_id: 9, parent_id: body.parent_id, code: body.code, name: body.name, location_type: body.location_type, is_active: true }];
      return route.fulfill({ status: 201, json: internalLocations[0] });
    }
    if (url.pathname === "/api/inventory/internal-locations/101" && method === "PUT") {
      writes.push({ method, body });
      internalLocations = [{ ...internalLocations[0], ...body }];
      return route.fulfill({ json: internalLocations[0] });
    }
    return route.fulfill({ status: 404, json: { detail: `Unexpected ${method} ${url.pathname}` } });
  });

  await page.goto("/admin");
  await page.getByRole("button", { name: "Inventory", exact: true }).click();
  const sections = page.getByRole("navigation", { name: "Inventory sections" });
  await expect(sections.getByRole("button").nth(0)).toHaveText("Overview");
  await expect(sections.getByRole("button").nth(1)).toHaveText("Locations");
  await sections.getByRole("button", { name: "Locations" }).click();
  await page.getByLabel("Location code").fill("A-01");
  await page.getByLabel("Location name").last().fill("Receiving Bay A");
  await page.getByLabel("Location type").selectOption("receiving");
  await page.getByRole("button", { name: "Create internal location" }).click();
  await expect(page.getByText("Receiving Bay A", { exact: true })).toBeVisible();
  expect(writes.find(write => write.method === "POST")?.body).toMatchObject({ facility_id: 9, parent_id: null, code: "A-01", name: "Receiving Bay A", location_type: "receiving" });

  await page.getByRole("button", { name: "Edit", exact: true }).click();
  await page.getByLabel("Location name").last().fill("Receiving Bay A1");
  await page.getByRole("button", { name: "Save internal location" }).click();
  await expect(page.getByText("Receiving Bay A1", { exact: true })).toBeVisible();
  expect(writes.find(write => write.method === "PUT")?.body).toMatchObject({ code: "A-01", name: "Receiving Bay A1", location_type: "receiving", is_active: true });
});
