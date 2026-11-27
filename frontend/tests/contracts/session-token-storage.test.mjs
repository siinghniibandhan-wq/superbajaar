import test from "node:test";
import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";

const api = await readFile(new URL("../../services/api.js", import.meta.url), "utf8");
const login = await readFile(new URL("../../src/app/LoginScreen.jsx", import.meta.url), "utf8");
const storefront = await readFile(new URL("../../src/app/Storefront.jsx", import.meta.url), "utf8");
const router = await readFile(new URL("../../src/app/router.jsx", import.meta.url), "utf8");

test("staff access tokens use tab-scoped session storage with legacy migration", () => {
  assert.match(api, /export function readSessionToken/);
  assert.match(api, /window\.sessionStorage\.getItem\(key\)/);
  assert.match(api, /window\.localStorage\.removeItem\(key\)/);
  assert.match(login, /storeSessionToken\("superbajaar\.access_token"/);
  assert.match(router, /readSessionToken\("superbajaar\.access_token"/);
});

test("customer access tokens use tab-scoped session storage", () => {
  assert.match(storefront, /readSessionToken\("sb-customer\.access_token"/);
  assert.match(storefront, /storeSessionToken\("sb-customer\.access_token"/);
  assert.match(storefront, /clearSessionToken\("sb-customer\.access_token"/);
});
