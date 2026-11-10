
import { test, expect } from "@playwright/test";

test("storefront route renders a non-empty application root", async ({ page }) => {
  await page.goto("/");
  await expect(page).toHaveTitle("Super Bajaar - Your Everyday Super Store");
  await expect(page.locator("#root")).not.toBeEmpty();
});

test("admin route presents accessible sign-in controls without a session", async ({ page }) => {
  await page.goto("/admin");
  await expect(page.getByRole("heading", { name: "Welcome back" })).toBeVisible();
  await expect(page.getByLabel("Email address")).toHaveAttribute("type", "email");
  await expect(page.getByLabel("Password")).toHaveAttribute("type", "password");
  await expect(page.getByRole("button", { name: "Sign in" })).toBeEnabled();
});


test("payment information page discloses current online payment availability", async ({ page }) => {
  await page.goto("/");
  await page.getByRole("link", { name: "Payment Information" }).click();
  await expect(page.getByRole("heading", { name: "Payment Information" })).toBeVisible();
  await expect(page.getByText(/Online payment, when available, is collected through the Razorpay secure checkout/)).toBeVisible();
  await expect(page.getByText(/server-to-server confirmation has been securely verified/)).toBeVisible();
});

test("customer checkout completes a mocked Razorpay payment", async ({ page }) => {
  const requests = [];
  await page.addInitScript(() => {
    localStorage.setItem("sb-customer.access_token", "customer-test-token");
    localStorage.setItem("sb-cart", JSON.stringify([{
      id: 7,
      sku: "TEST-7",
      product_name: "Test grocery",
      selling_price: 12.34,
      quantity: 1,
    }]));
    localStorage.setItem("sb-customer-profile", JSON.stringify({
      name: "Test Buyer",
      email: "buyer@example.com",
      phone: "9876543210",
      pin: "110001",
      address: "1 Test Street, Delhi",
    }));
    window.Razorpay = class {
      constructor(options) { this.options = options; }
      on() {}
      open() {
        this.options.handler({
          razorpay_order_id: "order_test123456",
          razorpay_payment_id: "pay_test123456",
          razorpay_signature: "a".repeat(64),
        });
      }
    };
  });
  await page.route("**/api/**", async route => {
    const request = route.request();
    const url = new URL(request.url());
    const method = request.method();
    const body = method === "POST" ? request.postDataJSON() : undefined;
    requests.push({ path: url.pathname, method, body });

    if (url.pathname === "/api/customer-auth/me") {
      return route.fulfill({ json: { customer: {
        full_name: "Test Buyer",
        email: "buyer@example.com",
        phone: "9876543210",
      } } });
    }
    if (url.pathname === "/api/loyalty/rules") {
      return route.fulfill({ json: { items: [], default_coins_per_100: 0 } });
    }
    if (url.pathname.startsWith("/api/catalogue/")) {
      return route.fulfill({ json: { items: [] } });
    }
    if (url.pathname === "/api/delivery/serviceability/110001") {
      return route.fulfill({ json: { serviceable: true } });
    }
    if (url.pathname === "/api/orders" && method === "POST") {
      return route.fulfill({ json: {
        id: 42,
        order_number: "SB-42",
        total: 12.34,
      } });
    }
    if (url.pathname === "/api/razorpay/orders" && method === "POST") {
      return route.fulfill({ json: {
        key_id: "rzp_test_key",
        razorpay_order_id: "order_test123456",
        amount: 1234,
        currency: "INR",
        payment_id: 21,
        order_number: "SB-42",
      } });
    }
    if (url.pathname === "/api/razorpay/verify" && method === "POST") {
      return route.fulfill({ json: { status: "captured", order_number: "SB-42" } });
    }
    return route.fulfill({ status: 404, json: { detail: "Unexpected mocked API request" } });
  });

  await page.goto("/checkout");
  await expect(page.getByRole("heading", { name: "Checkout" })).toBeVisible();
  await page.getByRole("checkbox").check();
  await page.getByRole("button", { name: "Pay securely with Razorpay" }).click();
  await expect(page.getByRole("status").filter({ hasText: "Payment received securely" })).toBeVisible();

  expect(requests.map(({ path }) => path)).toContain("/api/razorpay/orders");
  expect(requests.map(({ path }) => path)).toContain("/api/razorpay/verify");
  expect(requests.find(({ path }) => path === "/api/orders")?.body?.lines).toEqual([
    { variant_id: 7, quantity: 1 },
  ]);
  expect(requests.find(({ path }) => path === "/api/razorpay/verify")?.body).toMatchObject({
    razorpay_order_id: "order_test123456",
    razorpay_payment_id: "pay_test123456",
  });
});


test("HR manager can access the HR workspace without admin-wide module access", async ({ page }) => {
  await page.addInitScript(() => {
    localStorage.setItem("superbajaar.access_token", "manager-test-token");
  });
  await page.route("**/api/**", async route => {
    const url = new URL(route.request().url());
    if (url.pathname === "/api/auth/me") {
      return route.fulfill({ json: { user: {
        id: 77,
        full_name: "HR Manager",
        email: "hr.manager@example.test",
        role: "manager",
      } } });
    }
    if (url.pathname === "/api/health") {
      return route.fulfill({ json: { status: "ok", database: "connected" } });
    }
    return route.fulfill({ json: { items: [] } });
  });

  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto("/admin");
  await expect(page.getByRole("heading", { name: "HR & Payroll" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Admin access required" })).toHaveCount(0);
  await expect(page.getByRole("navigation", { name: "Module navigation" })).toHaveCount(0);

  for (const section of ["People directory", "Attendance", "Leave", "Planning & lifecycle", "Expenses", "Payroll", "Payslips", "Statutory policies"]) {
    await expect(page.getByRole("button", { name: section })).toBeVisible();
  }
  await page.getByRole("button", { name: "People directory" }).click();
  await expect(page.getByRole("heading", { name: "Employee directory" })).toBeVisible();
  await page.getByRole("button", { name: "Attendance", exact: true }).click();
  await expect(page.getByRole("heading", { name: "Attendance register" })).toBeVisible();
  await page.getByRole("button", { name: "Leave", exact: true }).click();
  await expect(page.getByRole("heading", { name: "Leave requests" })).toBeVisible();
  await expect(page.getByText("No leave requests for this period.")).toBeVisible();
  await page.getByRole("button", { name: "Expenses", exact: true }).click();
  await expect(page.getByRole("heading", { name: "Expense claims" })).toBeVisible();
  await expect(page.getByText("No expense claims submitted for this period.")).toBeVisible();
  await page.getByRole("button", { name: "Payroll", exact: true }).click();
  await expect(page.getByRole("heading", { name: "Payroll", exact: true })).toBeVisible();
  await page.getByRole("button", { name: "Planning & lifecycle" }).click();
  await expect(page.getByRole("heading", { name: "Shift definitions & roster" })).toBeVisible();
  await page.getByRole("button", { name: "Holiday calendar" }).click();
  await expect(page.getByRole("heading", { name: "Holiday calendars" })).toBeVisible();
  await page.getByRole("button", { name: "Leave policy & balances" }).click();
  await expect(page.getByRole("heading", { name: "Leave policies & balances" })).toBeVisible();
  await page.getByRole("button", { name: "Onboarding & offboarding" }).click();
  await expect(page.getByRole("heading", { name: "Employee onboarding & offboarding" })).toBeVisible();
  await page.getByRole("button", { name: "Statutory policies" }).click();
  await expect(page.getByRole("heading", { name: "Establishments & statutory policies" })).toBeVisible();
  await page.getByRole("button", { name: "Payslips", exact: true }).click();
  await expect(page.getByRole("heading", { name: "Payslips", exact: true })).toBeVisible();
});


test("HR attendance register formats Unix-second timestamps as real dates", async ({ page }) => {
  await page.addInitScript(() => {
    localStorage.setItem("superbajaar.access_token", "manager-test-token");
  });
  await page.route("**/api/**", async route => {
    const url = new URL(route.request().url());
    if (url.pathname === "/api/auth/me") {
      return route.fulfill({ json: { user: { id: 77, full_name: "HR Manager", role: "manager" } } });
    }
    if (url.pathname === "/api/health") return route.fulfill({ json: { status: "ok", database: "connected" } });
    if (url.pathname === "/api/hr/attendance/register") {
      return route.fulfill({ json: { items: [{ id: 501, employee_code: "SB-0001", first_name: "Test", last_name: "Employee", clock_in_at: 1800000000, clock_out_at: null, hours: null }] } });
    }
    return route.fulfill({ json: { items: [] } });
  });
  await page.setViewportSize({ width: 1440, height: 1000 });
  await page.goto("/admin");
  await page.getByRole("button", { name: "Attendance", exact: true }).click();
  await expect(page.getByRole("heading", { name: "Attendance register" })).toBeVisible();
  await expect(page.getByText(/2027/)).toBeVisible();
  await expect(page.getByText(/1970/)).toHaveCount(0);
  await page.getByRole("button", { name: "Adjust" }).click();
  await expect(page.locator('input[type="datetime-local"]').first()).toHaveValue(/^2027-/);
});


test("HR workspace adapts its navigation and employee form across desktop and mobile", async ({ page }) => {
  await page.addInitScript(() => localStorage.setItem("superbajaar.access_token", "manager-test-token"));
  await page.route("**/api/**", async route => {
    const url = new URL(route.request().url());
    if (url.pathname === "/api/auth/me") return route.fulfill({ json: { user: { id: 77, full_name: "HR Manager", role: "manager" } } });
    if (url.pathname === "/api/health") return route.fulfill({ json: { status: "ok", database: "connected" } });
    return route.fulfill({ json: { items: [] } });
  });

  await page.setViewportSize({ width: 1440, height: 1000 });
  await page.goto("/admin");
  const navigation = page.getByRole("navigation", { name: "HR sections" });
  await expect(navigation).toBeVisible();
  const desktopLayout = await navigation.evaluate(el => getComputedStyle(el).display);
  expect(desktopLayout).toBe("flex");
  await expect(navigation.locator(".hr-nav-group")).toHaveCount(5);
  await expect(navigation).toHaveCSS("overflow-x", "auto");

  await page.getByRole("button", { name: "People directory" }).click();
  const employeeDetails = page.locator("details.hr-disclosure").filter({ has: page.locator("form.hr-grid") });
  await expect(employeeDetails).not.toHaveAttribute("open", "");
  await employeeDetails.locator("summary").click();
  const employeeForm = page.locator("form.hr-form.hr-grid");
  await expect(employeeForm).toBeVisible();
  const desktopFormColumns = await employeeForm.evaluate(el => getComputedStyle(el).gridTemplateColumns.split(" ").length);
  expect(desktopFormColumns).toBe(3);

  await page.getByRole("button", { name: "Statutory policies" }).click();
  await expect(page.getByRole("heading", { name: "Establishments & statutory policies" })).toBeVisible();
  await expect(page.getByLabel("State code")).toHaveValue("");

  await page.getByRole("button", { name: "People directory" }).click();
  await page.setViewportSize({ width: 390, height: 844 });
  await expect(navigation).toBeVisible();
  const mobileColumns = await navigation.evaluate(el => getComputedStyle(el).gridTemplateColumns.split(" ").length);
  expect(mobileColumns).toBe(1);
  const mobileFormColumns = await employeeForm.evaluate(el => getComputedStyle(el).gridTemplateColumns.split(" ").length);
  expect(mobileFormColumns).toBe(1);
});
test("HR establishment edits preserve existing address and registration details", async ({ page }) => {
  const establishment = {
    id: 41,
    code: "KPMC-HO",
    legal_name: "KPMC Enterprises Private Limited",
    display_name: "KPMC Head Office",
    state_code: "JH",
    address: { line1: "Main Road", city: "Daltonganj", pincode: "822101" },
    registrations: { gstin: "20ABCDE1234F1Z5", pf_code: "JH/12345" },
    is_active: true,
  };
  let savedBody;
  await page.addInitScript(() => localStorage.setItem("superbajaar.access_token", "manager-test-token"));
  await page.route("**/api/**", async route => {
    const request = route.request();
    const url = new URL(request.url());
    if (url.pathname === "/api/auth/me") {
      return route.fulfill({ json: { user: { id: 77, full_name: "HR Manager", role: "manager" } } });
    }
    if (url.pathname === "/api/health") return route.fulfill({ json: { status: "ok", database: "connected" } });
    if (url.pathname === "/api/hr/establishments" && request.method() === "GET") {
      return route.fulfill({ json: { items: [establishment] } });
    }
    if (url.pathname === "/api/hr/establishments/41" && request.method() === "PUT") {
      savedBody = request.postDataJSON();
      return route.fulfill({ json: { ...establishment, ...savedBody } });
    }
    return route.fulfill({ json: { items: [] } });
  });

  await page.goto("/admin");
  await page.getByRole("button", { name: "Statutory policies" }).click();
  await expect(page.getByRole("heading", { name: "Establishments & statutory policies" })).toBeVisible();
  await page.getByRole("button", { name: "Edit", exact: true }).click();
  await expect(page.getByLabel("Address (JSON)")).toHaveValue(/Main Road/);
  await page.getByRole("button", { name: "Save establishment" }).click();
  await expect.poll(() => savedBody).toBeTruthy();
  expect(savedBody.address).toEqual(establishment.address);
  expect(savedBody.registrations).toEqual(establishment.registrations);
});


test("HR planning defaults use the employee's local calendar date, not the UTC date", async ({ page }) => {
  const timezoneSession = await page.context().newCDPSession(page);
  await timezoneSession.send("Emulation.setTimezoneOverride", { timezoneId: "Asia/Kolkata" });
  await page.addInitScript(() => {
    const RealDate = Date;
    const fixedNow = RealDate.parse("2026-11-04T20:00:00.000Z");
    class FixedDate extends RealDate {
      constructor(...args) { super(...(args.length ? args : [fixedNow])); }
      static now() { return fixedNow; }
    }
    window.Date = FixedDate;
    localStorage.setItem("superbajaar.access_token", "manager-test-token");
  });
  await page.route("**/api/**", async route => {
    const url = new URL(route.request().url());
    if (url.pathname === "/api/auth/me") {
      return route.fulfill({ json: { user: { id: 77, full_name: "HR Manager", role: "manager" } } });
    }
    if (url.pathname === "/api/health") return route.fulfill({ json: { status: "ok", database: "connected" } });
    return route.fulfill({ json: { items: [] } });
  });

  await page.goto("/admin");
  await page.getByRole("button", { name: "Planning & lifecycle" }).click();
  await expect(page.getByRole("heading", { name: "Shift definitions & roster" })).toBeVisible();
  await expect(page.getByLabel("Work date")).toHaveValue("2026-11-05");
  await expect(page.getByLabel("Effective from")).toHaveValue("2026-11-05");
});


test("HR planning surfaces workforce API failures instead of silently showing empty records", async ({ page }) => {
  await page.addInitScript(() => localStorage.setItem("superbajaar.access_token", "manager-test-token"));
  await page.route("**/api/**", async route => {
    const url = new URL(route.request().url());
    if (url.pathname === "/api/auth/me") {
      return route.fulfill({ json: { user: { id: 77, full_name: "HR Manager", role: "manager" } } });
    }
    if (url.pathname === "/api/health") return route.fulfill({ json: { status: "ok", database: "connected" } });
    if (url.pathname === "/api/hr/shifts") {
      return route.fulfill({ status: 503, json: { detail: "HR shifts unavailable" } });
    }
    return route.fulfill({ json: { items: [] } });
  });

  await page.goto("/admin");
  await page.getByRole("button", { name: "Planning & lifecycle" }).click();
  await expect(page.getByRole("alert")).toContainText("HR shifts unavailable");
});


test("HR establishment form retains entered details when the save request fails", async ({ page }) => {
  await page.addInitScript(() => localStorage.setItem("superbajaar.access_token", "manager-test-token"));
  await page.route("**/api/**", async route => {
    const request = route.request();
    const url = new URL(request.url());
    if (url.pathname === "/api/auth/me") {
      return route.fulfill({ json: { user: { id: 77, full_name: "HR Manager", role: "manager" } } });
    }
    if (url.pathname === "/api/health") return route.fulfill({ json: { status: "ok", database: "connected" } });
    if (url.pathname === "/api/hr/establishments" && request.method() === "POST") {
      return route.fulfill({ status: 503, json: { detail: "Establishment save failed" } });
    }
    return route.fulfill({ json: { items: [] } });
  });

  await page.goto("/admin");
  await page.getByRole("button", { name: "Statutory policies" }).click();
  await page.getByLabel("Establishment code").fill("KPMC-JH");
  await page.getByLabel("Legal name").fill("KPMC Enterprises");
  await page.getByLabel("Display name").fill("Jharkhand Office");
  await page.getByLabel("State code").selectOption("JH");
  await page.getByRole("button", { name: "Add establishment" }).click();
  await expect(page.getByRole("alert")).toContainText("Establishment save failed");
  await expect(page.getByLabel("Establishment code")).toHaveValue("KPMC-JH");
  await expect(page.getByLabel("Legal name")).toHaveValue("KPMC Enterprises");
  await expect(page.getByLabel("Display name")).toHaveValue("Jharkhand Office");
  await expect(page.getByLabel("State code")).toHaveValue("JH");
});


test("management analytics dashboard renders real module summaries and section views", async ({ page }) => {
  await page.addInitScript(() => localStorage.setItem("superbajaar.access_token", "owner-analytics-token"));
  await page.route("**/api/**", async route => {
    const url = new URL(route.request().url());
    const path = url.pathname;
    if (path === "/api/auth/me") return route.fulfill({ json: { user: { id: 1, full_name: "Owner", role: "owner" } } });
    if (path === "/api/health") return route.fulfill({ json: { status: "ok", database: "connected" } });
    if (path === "/api/catalogue/products") return route.fulfill({ json: { items: [{ id: 1, name: "Rice", status: "active" }] } });
    if (path === "/api/catalogue/variants") return route.fulfill({ json: { items: [{ id: 1, sku: "RICE-1" }] } });
    if (path === "/api/inventory/balances") return route.fulfill({ json: { items: [{ id: 1, location_id: 2, location_name: "Main Warehouse", on_hand: 12 }] } });
    if (path === "/api/inventory/overview") return route.fulfill({ json: { totals: { on_hand: 12, low_stock_rows: 0, out_of_stock_rows: 0 }, stock_by_location: [{ location_id: 2, location_name: "Main Warehouse", on_hand: 12 }], movement_groups: [] } });
    if (path === "/api/reports/overview") return route.fulfill({ json: { orders: { order_count: 1, active_order_value: 1200 }, payments: { captured_count: 1, captured_amount: 1200 }, catalogue: { active_products: 1 }, order_statuses: [{ status: "confirmed", count: 1 }] } });
    if (path === "/api/orders") return route.fulfill({ json: { items: [{ id: 9, order_number: "SB-9", status: "confirmed", total: 1200, created_at: new Date().toISOString() }] } });
    if (path === "/api/payments") return route.fulfill({ json: { items: [{ id: 3, amount: 1200, status: "captured", created_at: new Date().toISOString() }] } });
    if (path === "/api/customers") return route.fulfill({ json: { items: [{ id: 5, name: "Test Customer", is_active: true }] } });
    if (path === "/api/customers/support-cases") return route.fulfill({ json: { items: [{ id: 7, status: "open" }] } });
    if (path === "/api/hr/employees") return route.fulfill({ json: { items: [{ id: 11 }] } });
    if (path === "/api/hr/attendance/register") return route.fulfill({ json: { items: [{ id: 12 }] } });
    if (path === "/api/hr/payroll/runs") return route.fulfill({ json: { items: [{ id: 13, status: "posted", period_start: "2026-11-01", employee_count: 1 }] } });
    if (path === "/api/hr/expenses") return route.fulfill({ json: { items: [{ id: 14, status: "pending" }] } });
    if (path === "/api/accounting/reports/summary") return route.fulfill({ json: { income: 10000, expenses: 6000, net_profit: 4000, gross_profit: 5000, receivables: 2000, payables: 500, gst_payable: 300, monthly: [{ month: "2026-11", income: 10000, expense: 6000 }] } });
    return route.fulfill({ status: 404, json: { detail: "Unexpected analytics API request: " + path } });
  });

  await page.setViewportSize({ width: 1440, height: 1000 });
  await page.goto("/admin");
  await page.getByRole("button", { name: "Dashboard", exact: true }).click();
  await expect(page.getByRole("heading", { name: "Business analytics" })).toBeVisible();
  await expect(page.getByText("₹4,000", { exact: true })).toBeVisible();
  await expect(page.getByRole("article").filter({ hasText: "Order value" }).getByText("₹1,200", { exact: true })).toBeVisible();

  await page.getByRole("button", { name: "Sales", exact: true }).click();
  await expect(page.getByRole("heading", { name: "Sales performance" })).toBeVisible();
  await expect(page.getByText("SB-9")).toBeVisible();

  await page.getByLabel("Analytics sections").getByRole("button", { name: "Inventory", exact: true }).click();
  await expect(page.getByRole("heading", { name: "Inventory health" })).toBeVisible();
  await expect(page.getByText("Main Warehouse")).toBeVisible();

  await page.getByRole("button", { name: "Customers", exact: true }).click();
  await expect(page.getByRole("heading", { name: "Customer intelligence" })).toBeVisible();

  await page.getByRole("button", { name: "Finance", exact: true }).click();
  await expect(page.getByRole("heading", { name: "Financial performance" })).toBeVisible();
  await expect(page.locator("strong").filter({ hasText: /^₹10,000$/ })).toBeVisible();

  await page.getByRole("button", { name: "HR & People", exact: true }).click();
  await expect(page.getByRole("heading", { name: "People & workforce" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Payroll runs", exact: true })).toBeVisible();
});


test("inventory workspace separates locations, stock operations, approvals, valuation and policy into tabs", async ({ page }) => {
  await page.addInitScript(() => localStorage.setItem("superbajaar.access_token", "owner-inventory-token"));
  await page.route("**/api/**", async route => {
    const url = new URL(route.request().url());
    if (url.pathname === "/api/auth/me") return route.fulfill({ json: { user: { id: 1, full_name: "Owner", role: "owner" } } });
    if (url.pathname === "/api/health") return route.fulfill({ json: { status: "ok", database: "connected" } });
    return route.fulfill({ json: { items: [] } });
  });

  await page.goto("/admin");
  await page.getByRole("button", { name: "Inventory", exact: true }).click();
  const navigation = page.getByRole("navigation", { name: "Inventory sections" });
  await expect(navigation).toBeVisible();
  await navigation.getByRole("button", { name: "Locations", exact: true }).click();
  await expect(page.getByRole("heading", { name: "Add stock location" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Value or add stock" })).toHaveCount(0);

  await navigation.getByRole("button", { name: "Stock operations" }).click();
  await expect(page.getByRole("heading", { name: "Value or add stock" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Add stock location" })).toHaveCount(0);
  await expect(page.getByRole("heading", { name: "Issue / reduce stock" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Physical inventory count" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Transfer stock between locations" })).toBeVisible();

  await navigation.getByRole("button", { name: "Approvals" }).click();
  await expect(page.getByRole("heading", { name: /Inventory approval queue/ })).toBeVisible();
  await navigation.getByRole("button", { name: "Stock & valuation" }).click();
  await expect(page.getByRole("heading", { name: /Stock balances/ })).toBeVisible();
  await expect(page.getByRole("heading", { name: /Cost reconciliation/ })).toBeVisible();
  await expect(page.getByRole("heading", { name: /Recent movements/ })).toBeVisible();
  await navigation.getByRole("button", { name: "Control policy" }).click();
  await expect(page.getByText("Inventory control policy")).toBeVisible();
});

test("HR section tabs stay compact and scroll horizontally on mobile", async ({ page }) => {
  await page.addInitScript(() => localStorage.setItem("superbajaar.access_token", "manager-test-token"));
  await page.route("**/api/**", async route => {
    const url = new URL(route.request().url());
    if (url.pathname === "/api/auth/me") return route.fulfill({ json: { user: { id: 77, full_name: "HR Manager", role: "manager" } } });
    if (url.pathname === "/api/health") return route.fulfill({ json: { status: "ok", database: "connected" } });
    return route.fulfill({ json: { items: [] } });
  });
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto("/admin");
  const navigation = page.getByRole("navigation", { name: "HR sections" });
  await expect(navigation).toBeVisible();
  const metrics = await navigation.evaluate(el => ({
    height: el.getBoundingClientRect().height,
    scrollWidth: el.scrollWidth,
    clientWidth: el.clientWidth,
    tabHeight: el.querySelector("button").getBoundingClientRect().height,
    flexWrap: getComputedStyle(el).flexWrap,
  }));
  expect(metrics.tabHeight).toBeLessThanOrEqual(32);
  expect(metrics.flexWrap).toBe("nowrap");
  expect(metrics.scrollWidth).toBeGreaterThanOrEqual(metrics.clientWidth);
});


test("inventory workspace exposes its Overview section with live stock and control metrics", async ({ page }) => {
  await page.addInitScript(() => localStorage.setItem("superbajaar.access_token", "owner-inventory-analytics-token"));
  await page.route("**/api/**", async route => {
    const url = new URL(route.request().url());
    const path = url.pathname;
    if (path === "/api/auth/me") return route.fulfill({ json: { user: { id: 1, full_name: "Owner", role: "owner" } } });
    if (path === "/api/health") return route.fulfill({ json: { status: "ok", database: "connected" } });
    if (path === "/api/inventory/locations") return route.fulfill({ json: { items: [] } });
    if (path === "/api/catalogue/products") return route.fulfill({ json: { items: [{ id: 1, name: "Rice", status: "active" }] } });
    if (path === "/api/inventory/balances") return route.fulfill({ json: { items: [
      { id: 1, location_id: 1, location_name: "Main Warehouse", on_hand: 12, reserved: 2, available: 10 },
      { id: 2, location_id: 2, location_name: "Dark Store", on_hand: 5, reserved: 1, available: 4 },
    ] } });
    if (path === "/api/inventory/movements") return route.fulfill({ json: { items: [
      { id: 1, movement_type: "receipt", quantity: 10, created_at: new Date().toISOString() },
      { id: 2, movement_type: "issue", quantity: -2, created_at: new Date().toISOString() },
      { id: 3, movement_type: "transfer", quantity: 4, created_at: new Date().toISOString() },
    ] } });
    if (path === "/api/inventory/cost-layers") return route.fulfill({ json: { items: [{ id: 1 }, { id: 2 }] } });
    if (path === "/api/inventory/cost-layer-reconciliation") return route.fulfill({ json: { items: [{ id: 1, status: "mismatch" }] } });
    if (path === "/api/inventory/approval-requests") return route.fulfill({ json: { items: [{ id: 1, status: "pending" }, { id: 2, status: "approved" }] } });
    if (path === "/api/inventory/overview") return route.fulfill({ json: { totals: { on_hand: 17, reserved: 3, available: 14, movements: 3, pending_approvals: 1, active_cost_layers: 2 }, movement_groups: [{ movement_type: "receipt", total: 1 }, { movement_type: "issue", total: 1 }, { movement_type: "transfer", total: 1 }], stock_by_location: [{ location_id: 1, location_name: "Main Warehouse", on_hand: 12 }, { location_id: 2, location_name: "Dark Store", on_hand: 5 }] } });
    return route.fulfill({ json: { items: [] } });
  });

  await page.goto("/admin");
  await page.getByRole("button", { name: "Inventory", exact: true }).click();
  const navigation = page.getByRole("navigation", { name: "Inventory sections" });
  await expect(navigation.getByRole("button", { name: "Overview", exact: true })).toBeVisible();
  await navigation.getByRole("button", { name: "Overview", exact: true }).click();
  await expect(page.getByRole("heading", { name: "Inventory analytics" })).toBeVisible();
  await expect(page.locator(".inventory-analytics-metrics article").filter({ hasText: "Units on hand" }).locator("strong")).toHaveText("17");
  await expect(page.locator(".inventory-analytics-metrics article").filter({ hasText: "Reserved units" }).locator("strong")).toHaveText("3");
  await expect(page.locator(".inventory-analytics-metrics article").filter({ hasText: "Movement records" }).locator("strong")).toHaveText("3");
  await expect(page.locator(".inventory-analytics-metrics article").filter({ hasText: "Pending approvals" }).locator("strong")).toHaveText("1");
  await expect(page.getByText("Main Warehouse")).toBeVisible();
});


test("HR staff can view their own payslips in employee self-service", async ({ page }) => {
  await page.addInitScript(() => {
    localStorage.setItem("superbajaar.access_token", "employee-test-token");
  });
  await page.route("**/api/**", async route => {
    const url = new URL(route.request().url());
    if (url.pathname === "/api/auth/me") {
      return route.fulfill({ json: { user: {
        id: 88,
        full_name: "HR Employee",
        email: "employee@example.test",
        role: "staff",
      } } });
    }
    if (url.pathname === "/api/health") {
      return route.fulfill({ json: { status: "ok", database: "connected" } });
    }
    if (url.pathname === "/api/hr/payroll/me/payslips") {
      return route.fulfill({ json: { items: [{
        id: 901,
        period_start: "2026-10-01",
        period_end: "2026-10-31",
        gross_earnings: "42000.00",
        reimbursements: "1500.00",
        deductions: "3500.00",
        employer_contributions: "2400.00",
        net_pay: "40000.00",
        earnings_breakdown: { basic: "30000.00", hra: "8000.00", special_allowance: "3000.00", other_allowance: "1000.00" },
        deduction_breakdown: { manual_deduction: "500.00", manual_note: "Approved salary advance recovery", statutory: { pf: { employee_amount: "1800.00", employer_amount: "1800.00" }, esi: { employee_amount: "0.00", employer_amount: "0.00" }, pt: { employee_amount: "200.00", employer_amount: "0.00" }, tds: { employee_amount: "1000.00", employer_amount: "0.00" } } },
      }] } });
    }
    return route.fulfill({ json: { items: [] } });
  });

  await page.goto("/admin");
  await expect(page.getByRole("heading", { name: "HR & Payroll" })).toBeVisible();
  await expect(page.getByRole("button", { name: "Payslips", exact: true })).toBeVisible();
  await page.getByRole("button", { name: "Payslips", exact: true }).click();
  await expect(page.getByRole("heading", { name: "My payslips", exact: true })).toBeVisible();
  await expect(page.getByText("2026-10-01 – 2026-10-31")).toBeVisible();
  await expect(page.getByText("₹40,000.00")).toBeVisible();
  await page.getByText("View breakdown").click();
  await expect(page.getByText("Basic", { exact: true })).toBeVisible();
  await expect(page.getByText("Approved salary advance recovery")).toBeVisible();
  await expect(page.getByText(/PF: Employee/)).toBeVisible();
  const downloadPromise = page.waitForEvent("download");
  await page.getByRole("button", { name: "Export CSV" }).click();
  const download = await downloadPromise;
  expect(download.suggestedFilename()).toBe("my-payslips.csv");
});


test("HR payroll calculation sends employee-specific manual deduction reasons", async ({ page }) => {
  await page.addInitScript(() => {
    localStorage.setItem("superbajaar.access_token", "manager-test-token");
  });
  let payrollPayload;
  await page.route("**/api/**", async route => {
    const url = new URL(route.request().url());
    if (url.pathname === "/api/auth/me") {
      return route.fulfill({ json: { user: { id: 77, full_name: "HR Manager", role: "manager" } } });
    }
    if (url.pathname === "/api/health") {
      return route.fulfill({ json: { status: "ok", database: "connected" } });
    }
    if (url.pathname === "/api/hr/payroll/runs" && route.request().method() === "POST") {
      payrollPayload = route.request().postDataJSON();
      return route.fulfill({ status: 201, json: { id: 44, status: "calculated" } });
    }
    return route.fulfill({ json: { items: [] } });
  });

  await page.goto("/admin");
  await page.getByRole("button", { name: "Payroll", exact: true }).click();
  await page.getByLabel("Manual payroll deductions by employee ID").fill('{"123": 500}');
  await page.getByLabel("Manual deduction notes by employee ID").fill('{"123": "Approved salary advance recovery"}');
  await page.getByRole("button", { name: "Calculate payroll" }).click();
  await expect.poll(() => payrollPayload).toMatchObject({
    deductions_by_employee: { "123": 500 },
    deduction_notes: { "123": "Approved salary advance recovery" },
  });
});
