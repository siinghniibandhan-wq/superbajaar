import { test, expect } from "@playwright/test";

test("customer can submit an existing SBID claim and see its review status", async ({ page }) => {
  const submitted = [];
  let claims = [];
  await page.addInitScript(() => {
    localStorage.setItem("sb-customer.access_token", "customer-identity-e2e-token");
    localStorage.setItem("sb-customer-profile", JSON.stringify({
      name: "Identity Test Customer",
      email: "identity.customer@example.test",
      phone: "9876543210",
    }));
  });

  await page.route("**/api/**", async route => {
    const url = new URL(route.request().url());
    const method = route.request().method();

    if (url.pathname === "/api/customer-auth/me") {
      return route.fulfill({ json: { customer: {
        full_name: "Identity Test Customer",
        email: "identity.customer@example.test",
        phone: "9876543210",
      } } });
    }

    if (url.pathname === "/api/customer-auth/identity-claims" && method === "GET") {
      return route.fulfill({ json: { items: claims } });
    }

    if (url.pathname === "/api/customer-auth/identity-claims" && method === "POST") {
      const body = route.request().postDataJSON();
      submitted.push(body);
      claims = [{
        id: 901,
        status: "proof_required",
        created_at: "2026-11-12T03:00:00Z",
        expires_at: "2026-11-19T03:00:00Z",
        reviewed_at: null,
      }];
      return route.fulfill({ status: 201, json: {
        message: "Your request has been submitted for secure review.",
        request: { id: 901, status: "proof_required" },
      } });
    }

    return route.fulfill({ status: 404, json: { detail: "Unexpected identity E2E API request" } });
  });

  await page.goto("/account");
  await expect(page.getByRole("heading", { name: "Hello, Identity" })).toBeVisible();
  await page.getByRole("button", { name: /Identity claims/ }).click();
  await expect(page.getByRole("heading", { name: "Claim an existing identity" })).toBeVisible();

  await page.getByLabel("Existing SBID").fill("SBID-0123456789ABCDEF0123");
  await page.getByLabel("Why are you claiming this identity?").fill(
    "This existing identity belongs to my customer profile."
  );
  await page.getByRole("button", { name: "Submit for secure review" }).click();

  await expect(page.getByRole("status").filter({
    hasText: "Your request has been submitted for secure review.",
  })).toBeVisible();
  await expect(page.getByText("Evidence required")).toBeVisible();
  expect(submitted).toEqual([{
    target_sbid: "SBID-0123456789ABCDEF0123",
    reason: "This existing identity belongs to my customer profile.",
  }]);
});
