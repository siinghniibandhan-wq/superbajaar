import { test, expect } from "@playwright/test";

test("inventory releases only inspected quarantined GRN quantity through the controlled accounting-backed API", async ({ page }) => {
  const writes = [];
  let quarantineQuantity = "4.000";
  let acceptedQuantity = "2.000";
  await page.addInitScript(() => localStorage.setItem("superbajaar.access_token", "owner-inventory-quarantine-token"));
  await page.route("**/api/**", async route => {
    const request = route.request();
    const url = new URL(request.url());
    const method = request.method();
    const body = method === "POST" ? request.postDataJSON() : undefined;
    if (url.pathname === "/api/auth/me") return route.fulfill({ json: { user: { id: 1, full_name: "Owner", role: "owner" } } });
    if (url.pathname === "/api/health") return route.fulfill({ json: { status: "ok", database: "connected" } });
    if (url.pathname === "/api/inventory/locations") return route.fulfill({ json: { items: [{ id: 9, name: "Patna Central", location_type: "warehouse", is_active: true, is_fulfillable: true, establishment_id: 4 }] } });
    if (url.pathname === "/api/catalogue/products") return route.fulfill({ json: { items: [] } });
    if (["/api/inventory/balances", "/api/inventory/movements", "/api/inventory/cost-layers", "/api/inventory/cost-layer-reconciliation", "/api/inventory/approval-requests"].includes(url.pathname)) return route.fulfill({ json: { items: [] } });
    if (url.pathname === "/api/inventory/overview") return route.fulfill({ json: { totals: {}, movement_groups: [], stock_by_location: [] } });
    if (url.pathname === "/api/hr/establishments") return route.fulfill({ json: { items: [{ id: 4, display_name: "Super Bajaar Bihar", code: "SB-BR" }] } });
    if (url.pathname === "/api/inventory/internal-locations") return route.fulfill({ json: { items: [] } });
    if (url.pathname === "/api/inventory/expired-stock") return route.fulfill({ json: { items: [] } });
    if (url.pathname === "/api/fulfilment/returns") return route.fulfill({ json: { items: [] } });
    if (url.pathname === "/api/purchasing/grns" && url.searchParams.get("quarantined_only") === "true") return route.fulfill({ json: { items: quarantineQuantity === "0.000" ? [] : [{ id: 33, grn_number: "GRN-33", purchase_number: "PO-33", supplier_name: "North Star Supplies", status: "partially_accepted", quarantined_quantity: quarantineQuantity }] } });
    if (url.pathname === "/api/purchasing/grns/33" && method === "GET") return route.fulfill({ json: { id: 33, grn_number: "GRN-33", status: "partially_accepted", lines: [{ id: 44, product_name: "Wheat Flour 5kg", sku: "WF-5KG", received_quantity: "6.000", accepted_quantity: acceptedQuantity, quarantined_quantity: quarantineQuantity, damaged_quantity: "0.000", rejected_quantity: "0.000", batch_code: "B-33", expiry_date: "2027-12-31", unit_cost: "210.00" }] } });
    if (url.pathname === "/api/purchasing/grns/33/release-quarantine" && method === "POST") {
      writes.push({ body });
      const released = body.lines[0].quantity;
      quarantineQuantity = (Number(quarantineQuantity) - released).toFixed(3);
      acceptedQuantity = (Number(acceptedQuantity) + released).toFixed(3);
      return route.fulfill({ json: { goods_receipt_id: 33, status: "partially_accepted", replayed: false, event_count: 1 } });
    }
    return route.fulfill({ status: 404, json: { detail: `Unexpected ${method} ${url.pathname}` } });
  });

  await page.goto("/admin");
  await page.getByRole("button", { name: "Inventory", exact: true }).click();
  await page.getByRole("button", { name: "Returns & quarantine" }).click();
  const grnRow = page.getByRole("button", { name: /GRN-33/ });
  await expect(grnRow).toBeVisible();
  await grnRow.click();
  await page.getByLabel("Release quantity").fill("1.500");
  await page.getByLabel("Inspection / release reason").fill("QC verified and released");
  await page.getByRole("button", { name: "Release selected quarantined stock" }).click();
  await expect(page.getByText(/Quarantined quantity released to saleable stock/)).toBeVisible();
  expect(writes[0].body.lines).toEqual([{ goods_receipt_line_id: 44, quantity: 1.5, reason: "QC verified and released" }]);
  expect(writes[0].body.idempotency_key).toBeTruthy();
  await expect(page.getByText(/Quarantined 2\.500/)).toBeVisible();
});
