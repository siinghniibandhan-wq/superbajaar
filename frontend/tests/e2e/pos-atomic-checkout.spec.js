import { test, expect } from "@playwright/test";

test("POS creates order and pending tender atomically with a retry-safe checkout key", async ({ page }) => {
  const writes = [];
  let orderCreated = false;
  await page.addInitScript(() => localStorage.setItem("superbajaar.access_token", "owner-pos-checkout-token"));
  await page.route("**/api/**", async route => {
    const request = route.request();
    const url = new URL(request.url());
    const method = request.method();
    const body = method === "POST" ? request.postDataJSON() : undefined;
    if (url.pathname === "/api/auth/me") return route.fulfill({ json: { user: { id: 1, full_name: "Owner", role: "owner" } } });
    if (url.pathname === "/api/health") return route.fulfill({ json: { status: "ok", database: "connected" } });
    if (url.pathname === "/api/catalogue/variants") return route.fulfill({ json: { items: [{ id: 17, product_id: 8, product_name: "Wheat Flour 5kg", sku: "WF-5KG", selling_price: "250.00", is_active: true, attributes: {} }] } });
    if (url.pathname === "/api/inventory/locations") return route.fulfill({ json: { items: [{ id: 9, name: "Patna Main Store", location_type: "store", is_active: true }] } });
    if (url.pathname === "/api/pos/summary") return route.fulfill({ json: { orders: { order_count: 0, today_order_count: 0, today_order_value: 0 }, payments: { captured_amount: 0, captured_count: 0, pending_amount: 0, pending_count: 0 } } });
    if (url.pathname === "/api/pos/sales") return route.fulfill({ json: { items: [] } });
    if (url.pathname === "/api/orders" && method === "POST") {
      writes.push({ path: url.pathname, method, body }); orderCreated = true;
      return route.fulfill({ status: 201, json: {
        id: 101, order_number: "SB-POS-101", channel: "pos", status: "placed", subtotal: "250.00", total: "250.00",
        payment: { id: 201, payment_reference: "PAY-POS-201", order_id: 101, method: "upi", amount: "250.00", status: "pending" },
      } });
    }
    if (url.pathname === "/api/payments" && method === "POST") {
      writes.push({ path: url.pathname, method, body });
      return route.fulfill({ status: 500, json: { detail: "POS must not create a separate payment request" } });
    }
    return route.fulfill({ status: 404, json: { detail: `Unexpected ${method} ${url.pathname}` } });
  });

  await page.goto("/admin");
  await page.getByRole("button", { name: "POS & Stores", exact: true }).click();
  await page.getByRole("button", { name: "Add to sale" }).click();
  await page.getByLabel("Stock location").selectOption("9");
  await page.getByRole("button", { name: "Create sale & pending tender" }).click();
  await expect(page.getByText("SB-POS-101", { exact: true })).toBeVisible();
  await expect(page.getByText(/PAY-POS-201 · pending/)).toBeVisible();
  expect(orderCreated).toBeTruthy();
  expect(writes).toHaveLength(1);
  expect(writes[0].body).toMatchObject({
    channel: "pos", location_id: 9, pos_payment_method: "upi",
    lines: [{ variant_id: 17, quantity: 1 }],
  });
  expect(writes[0].body.checkout_idempotency_key).toBeTruthy();
});


test("POS workspace stacks its catalogue and checkout panels at tablet and phone widths", async ({ page }) => {
  await page.setViewportSize({ width: 980, height: 900 });
  await page.addInitScript(() => localStorage.setItem("superbajaar.access_token", "owner-pos-layout-token"));
  await page.route("**/api/**", async route => {
    const url = new URL(route.request().url());
    if (url.pathname === "/api/auth/me") return route.fulfill({ json: { user: { id: 1, full_name: "Owner", role: "owner" } } });
    if (url.pathname === "/api/health") return route.fulfill({ json: { status: "ok", database: "connected" } });
    if (url.pathname === "/api/catalogue/variants") return route.fulfill({ json: { items: [] } });
    if (url.pathname === "/api/inventory/locations") return route.fulfill({ json: { items: [] } });
    if (url.pathname === "/api/pos/summary") return route.fulfill({ json: { orders: {}, payments: {} } });
    if (url.pathname === "/api/pos/sales") return route.fulfill({ json: { items: [] } });
    return route.fulfill({ status: 404, json: { detail: "Not found" } });
  });

  await page.goto("/admin");
  await page.getByRole("button", { name: "POS & Stores", exact: true }).click();
  const layout = page.locator(".sb-pos-layout");
  await expect(layout).toBeVisible();
  const columnsAtTabletWidth = await layout.evaluate(element => getComputedStyle(element).gridTemplateColumns.split(" ").length);
  expect(columnsAtTabletWidth).toBe(1);

  await page.setViewportSize({ width: 390, height: 844 });
  const columnsAtPhoneWidth = await layout.evaluate(element => getComputedStyle(element).gridTemplateColumns.split(" ").length);
  expect(columnsAtPhoneWidth).toBe(1);
});
