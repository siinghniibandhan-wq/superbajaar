import { test, expect } from "@playwright/test";

test("catalogue saves product, attributes, variants and availability through one atomic endpoint", async ({ page }) => {
  const writes = [];
  let saved = false;
  await page.addInitScript(() => localStorage.setItem("superbajaar.access_token", "owner-catalogue-save-token"));
  await page.route("**/api/**", async route => {
    const permissionRequest = route.request();
    if (new URL(permissionRequest.url()).pathname.endsWith("/auth/my-permissions")) {
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
    if (url.pathname === "/api/catalogue/categories") return route.fulfill({ json: { items: [{ id: 3, name: "Grocery", slug: "grocery", parent_id: null }] } });
    if (url.pathname === "/api/catalogue/products") return route.fulfill({ json: { items: saved ? [{ id: 91, name: "Wheat Flour", slug: "wheat-flour", category_id: 3, category_ids: [3], status: "active", variant_count: 1, min_selling_price: "80.00", max_selling_price: "80.00" }] : [] } });
    if (url.pathname === "/api/catalogue/attributes") return route.fulfill({ json: { items: [] } });
    if (url.pathname === "/api/catalogue/stock-locations") return route.fulfill({ json: { items: [] } });
    if (url.pathname === "/api/catalogue/products/complete" && method === "POST") {
      writes.push({ path: url.pathname, method, body }); saved = true;
      return route.fulfill({ status: 201, json: { id: 91, name: "Wheat Flour", slug: "wheat-flour", category_id: 3, category_ids: [3], created_variant_count: 1 } });
    }
    if (url.pathname.startsWith("/api/catalogue/products/") && method !== "GET") {
      writes.push({ path: url.pathname, method, body });
      return route.fulfill({ status: 500, json: { detail: "Catalogue save must use the atomic complete endpoint" } });
    }
    return route.fulfill({ status: 404, json: { detail: `Unexpected ${method} ${url.pathname}` } });
  });

  await page.goto("/admin");
  await page.getByRole("button", { name: "Catalogue", exact: true }).click();
  await page.getByRole("button", { name: /Add product/ }).click();
  await page.getByLabel("Product name *").fill("Wheat Flour");
  await page.getByLabel("Grocery", { exact: true }).check();
  await page.getByLabel("Selling price (₹) *").fill("80");
  await page.getByLabel("MRP (₹) *").fill("90");
  await page.getByRole("button", { name: "Continue to Attributes & Variants" }).click();
  await page.getByRole("button", { name: "Next: Availability" }).click();
  await page.getByRole("button", { name: "Continue to Delivery" }).click();
  await page.getByRole("button", { name: "Continue to Images" }).click();
  await page.getByRole("button", { name: "Continue to Review & Save" }).click();
  await page.getByRole("button", { name: "Save product and variants" }).last().click();
  await expect(page.getByText("Wheat Flour", { exact: true })).toBeVisible();
  expect(writes).toHaveLength(1);
  expect(writes[0].body).toMatchObject({
    product: { name: "Wheat Flour", slug: "wheat-flour", category_ids: [3] },
    product_attributes: {}, custom_options: {},
    variants: [{ attributes: {}, selling_price: 80, mrp: 90, cost_price: null }],
    availability_rules: [],
  });
});
