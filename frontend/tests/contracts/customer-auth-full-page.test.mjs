import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

const storefront = readFileSync(new URL("../../src/app/Storefront.jsx", import.meta.url), "utf8");
const styles = readFileSync(new URL("../../src/app/storefront.css", import.meta.url), "utf8");

test("customer login and registration routes use a standalone full-page shell", () => {
  assert.match(storefront, /isCustomerAuthPage\s*\?\s*" storefront-auth-shell"/);
  assert.match(storefront, /routePath === "\/customer\/login" \|\| routePath === "\/customer\/register"/);
  assert.match(styles, /\.storefront-auth-shell\s*\{[\s\S]*?min-height:\s*100svh/);
  assert.match(styles, /\.storefront-auth-shell>\s*:not\(\.storefront-checkout-page\)\s*\{display:none!important\}/);
});

test("existing login and signup form controls and social sign-in remain available", () => {
  assert.match(storefront, /submitCustomerAuth/);
  assert.match(storefront, /customerAuthMode === "register"/);
  assert.match(storefront, /customer-auth\/oauth\/google\/start/);
  assert.match(storefront, /customer-auth\/oauth\/github\/start/);
  assert.match(storefront, /referral_code/);
});

test("Google and GitHub OAuth buttons show their recognizable provider symbols", () => {
  assert.match(storefront, /import \{[^}]*Github[^}]*\} from "lucide-react"/);
  assert.match(storefront, /aria-label="Google"/);
  assert.match(storefront, /aria-label="GitHub"/);
  assert.match(storefront, /storefront-social-icon/);
  assert.match(styles, /\.storefront-social-icon/);
});
