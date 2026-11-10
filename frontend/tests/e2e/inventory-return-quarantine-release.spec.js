import { test, expect } from "@playwright/test";

test("inventory releases inspected customer-return quarantine stock to a same-establishment saleable facility", async ({ page }) => {
  const writes = [];
  let remaining = "2.000";
  let released = "0.000";
  await page.addInitScript(() => localStorage.setItem("superbajaar.access_token", "owner-return-quarantine-token"));
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
    const body = method === "POST" ? request.postDataJSON() : undefined;
    if (url.pathname === "/api/auth/me") return route.fulfill({ json: { user: { id: 1, full_name: "Owner", role: "owner" } } });
    if (url.pathname === "/api/health") return route.fulfill({ json: { status: "ok", database: "connected" } });
    if (url.pathname === "/api/inventory/locations") return route.fulfill({ json: { items: [
      { id: 9, name: "Patna Quarantine", location_type: "warehouse", is_active: true, is_fulfillable: false, establishment_id: 4 },
      { id: 10, name: "Patna Main Store", location_type: "store", is_active: true, is_fulfillable: true, establishment_id: 4 },
    ] } });
    if (url.pathname === "/api/catalogue/products") return route.fulfill({ json: { items: [] } });
    if (["/api/inventory/balances", "/api/inventory/movements", "/api/inventory/cost-layers", "/api/inventory/cost-layer-reconciliation", "/api/inventory/approval-requests"].includes(url.pathname)) return route.fulfill({ json: { items: [] } });
    if (url.pathname === "/api/inventory/overview") return route.fulfill({ json: { totals: {}, movement_groups: [], stock_by_location: [] } });
    if (url.pathname === "/api/hr/establishments") return route.fulfill({ json: { items: [{ id: 4, display_name: "Super Bajaar Bihar", code: "SB-BR" }] } });
    if (url.pathname === "/api/inventory/internal-locations") return route.fulfill({ json: { items: [] } });
    if (url.pathname === "/api/inventory/expired-stock") return route.fulfill({ json: { items: [] } });
    if (url.pathname === "/api/fulfilment/returns") return route.fulfill({ json: { items: [{ id: 22, return_number: "RET-22", order_number: "SB-ORDER-22", shipment_reference: "SHP-22", line_count: 1, status: "closed" }] } });
    if (url.pathname === "/api/purchasing/grns") return route.fulfill({ json: { items: [] } });
    if (url.pathname === "/api/fulfilment/returns/22" && method === "GET") return route.fulfill({ json: {
      id: 22, return_number: "RET-22", order_number: "SB-ORDER-22", reason: "Damaged packaging", status: "closed",
      lines: [{ id: 23, sku: "WF-5KG", product_name: "Wheat Flour 5kg", requested_quantity: "2.000", received_quantity: "2.000", inspection_status: "quarantined", disposition: "quarantine", disposition_posted_at: "2026-11-06T10:00:00Z", quarantine_remaining_quantity: remaining, quarantine_releasable_quantity: remaining, quarantine_released_quantity: released }],
    } });
    if (url.pathname === "/api/fulfilment/returns/22/lines/23/release-quarantine" && method === "POST") {
      writes.push({ body }); remaining = "0.000"; released = "2.000";
      return route.fulfill({ json: { return_id: 22, return_line_id: 23, released_quantity: "2.000", remaining_quarantine_quantity: "0.000", expired_quantity_not_released: "0.000", total_cost_transferred: "420.00", replayed: false } });
    }
    return route.fulfill({ status: 404, json: { detail: `Unexpected ${method} ${url.pathname}` } });
  });

  await page.goto("/admin");
  await page.getByRole("button", { name: "Inventory", exact: true }).click();
  await page.getByRole("button", { name: "Returns & quarantine" }).click();
  const returnRow = page.getByRole("button", { name: /RET-22/ });
  await expect(returnRow).toBeVisible();
  await returnRow.click();
  await page.getByLabel("Saleable destination").selectOption("10");
  await page.getByLabel("Reinspection / release reason").fill("QC reinspection passed");
  await page.getByRole("button", { name: "Release", exact: true }).click();
  await expect(page.getByText(/2.000 units moved to saleable stock/)).toBeVisible();
  expect(writes).toHaveLength(1);
  expect(writes[0].body).toMatchObject({ destination_location_id: 10, reason: "QC reinspection passed" });
  expect(writes[0].body.idempotency_key).toBeTruthy();
});
