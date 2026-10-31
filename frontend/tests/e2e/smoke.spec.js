import { test, expect } from "@playwright/test";

test("storefront route renders a non-empty application root", async ({ page }) => {
  await page.goto("/");
  await expect(page).toHaveTitle("Super Bajaar");
  await expect(page.locator("#root")).not.toBeEmpty();
});

test("admin route presents accessible sign-in controls without a session", async ({ page }) => {
  await page.goto("/admin");
  await expect(page.getByRole("heading", { name: "Welcome back" })).toBeVisible();
  await expect(page.getByLabel("Email address")).toHaveAttribute("type", "email");
  await expect(page.getByLabel("Password")).toHaveAttribute("type", "password");
  await expect(page.getByRole("button", { name: "Sign in" })).toBeEnabled();
});
