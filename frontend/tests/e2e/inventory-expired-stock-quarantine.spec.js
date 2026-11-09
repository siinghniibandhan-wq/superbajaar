import { test, expect } from "@playwright/test";

test("inventory moves expired FEFO cost layers from a saleable store into a non-fulfillable quarantine location", async ({ page }) => {
  const writes = [];
  let expiredItems = [{ variant_id: 17, sku: "WF-5KG", product_name: "Wheat Flour 5kg", location_id: 9, location_name: "Patna Main Store", expired_quantity: "3.000", expired_value: "630.00", earliest_expiry: "2026-10-31", layer_count: 2 }];
  await page.addInitScript(() => localStorage.setItem("superbajaar.access_token", "owner-expired-stock-token"));
  await page.route("**/api/**", async route => {
    const request = route.request();
    const url = new URL(request.url());
    const method = request.method();
    const body = method === "POST" ? request.postDataJSON() : undefined;
    if (url.pathname === "/api/auth/me") return route.fulfill({ json: { user: { id: 1, full_name: "Owner", role: "owner" } } });
    if (url.pathname === "/api/health") return route.fulfill({ json: { status: "ok", database: "connected" } });
    if (url.pathname === "/api/inventory/locations") return route.fulfill({ json: { items: [
      { id: 9, name: "Patna Main Store", location_type: "store", is_active: true, is_fulfillable: true, establishment_id: 4 },
      { id: 10, name: "Patna Expired Quarantine", location_type: "warehouse", is_active: true, is_fulfillable: false, establishment_id: 4 },
    ] } });
    if (url.pathname === "/api/catalogue/products") return route.fulfill({ json: { items: [] } });
    if (["/api/inventory/balances", "/api/inventory/movements", "/api/inventory/cost-layers", "/api/inventory/cost-layer-reconciliation", "/api/inventory/approval-requests"].includes(url.pathname)) return route.fulfill({ json: { items: [] } });
    if (url.pathname === "/api/inventory/overview") return route.fulfill({ json: { totals: {}, movement_groups: [], stock_by_location: [] } });
    if (url.pathname === "/api/hr/establishments") return route.fulfill({ json: { items: [{ id: 4, display_name: "Super Bajaar Bihar", code: "SB-BR" }] } });
    if (url.pathname === "/api/fulfilment/returns") return route.fulfill({ json: { items: [] } });
    if (url.pathname === "/api/purchasing/grns") return route.fulfill({ json: { items: [] } });
    if (url.pathname === "/api/inventory/expired-stock") return route.fulfill({ json: { items: expiredItems, total: expiredItems.length } });
    if (url.pathname === "/api/inventory/quarantine-expired" && method === "POST") {
      writes.push({ body }); expiredItems = [];
      return route.fulfill({ json: { variant_id: 17, source_location_id: 9, quarantine_location_id: 10, quarantined_quantity: "3.000", remaining_expired_quantity: "0.000", total_cost_transferred: "630.00", replayed: false } });
    }
    return route.fulfill({ status: 404, json: { detail: `Unexpected ${method} ${url.pathname}` } });
  });

  await page.goto("/admin");
  await page.getByRole("button", { name: "Inventory", exact: true }).click();
  await page.getByRole("button", { name: "Returns & quarantine" }).click();
  await page.getByLabel("Quarantine destination").selectOption("10");
  await page.getByLabel("Quarantine reason").fill("Expiry confirmed during daily inspection");
  await page.getByRole("button", { name: "Quarantine all expired" }).click();
  await expect(page.getByText(/3.000 expired units moved to non-fulfillable quarantine/)).toBeVisible();
  expect(writes).toHaveLength(1);
  expect(writes[0].body).toMatchObject({ variant_id: 17, source_location_id: 9, quarantine_location_id: 10, reason: "Expiry confirmed during daily inspection" });
  expect(writes[0].body.idempotency_key).toBeTruthy();
  expect(writes[0].body.quantity).toBeUndefined();
});
