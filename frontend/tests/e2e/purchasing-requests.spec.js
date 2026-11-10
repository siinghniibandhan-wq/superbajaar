import { test, expect } from "@playwright/test";

const supplier = { id: 5, name: "North Star Supplies", email: "sales@northstar.test", phone: "9876543210", is_active: true };
const location = { id: 3, name: "Patna Central Warehouse", is_active: true };
const variant = { id: 17, product_id: 8, product_name: "Wheat Flour 5kg", sku: "WF-5KG" };

async function openPurchasing(page) {
  await page.addInitScript(() => localStorage.setItem("superbajaar.access_token", "owner-purchasing-test-token"));
  await page.goto("/admin");
  await page.getByRole("button", { name: "Purchasing", exact: true }).click();
  await page.getByRole("tab", { name: /Requisitions & RFQs/ }).click();
}

test("purchasing workspace creates and submits a requisition through its API", async ({ page }) => {
  const writes = [];
  let requisitionStatus = "draft";
  await page.route("**/api/**", async route => {
    const request = route.request();
    const url = new URL(request.url());
    const method = request.method();
    const body = method === "POST" ? request.postDataJSON() : undefined;
    if (url.pathname === "/api/auth/me") return route.fulfill({ json: { user: { id: 11, full_name: "Owner", email: "owner@superbajaar.test", role: "owner" } } });
    if (url.pathname === "/api/health") return route.fulfill({ json: { status: "ok", database: "connected" } });
    if (url.pathname === "/api/purchasing/suppliers") return route.fulfill({ json: { items: [supplier] } });
    if (url.pathname === "/api/inventory/locations") return route.fulfill({ json: { items: [location] } });
    if (url.pathname === "/api/purchasing/orders") return route.fulfill({ json: { items: [] } });
    if (url.pathname === "/api/catalogue/variants") return route.fulfill({ json: { items: [variant] } });
    if (url.pathname === "/api/purchasing/requisitions" && method === "GET") return route.fulfill({ json: { items: requisitionStatus === "draft" ? [{ id: 41, requisition_number: "PR-TEST-41", requester_email: "owner@superbajaar.test", location_id: 3, location_name: location.name, department: "Operations", status: "draft", line_count: 1 }] : [{ id: 41, requisition_number: "PR-TEST-41", requester_email: "owner@superbajaar.test", location_id: 3, location_name: location.name, department: "Operations", status: requisitionStatus, line_count: 1 }] } });
    if (url.pathname === "/api/purchasing/rfqs") return route.fulfill({ json: { items: [] } });
    if (url.pathname === "/api/purchasing/requisitions" && method === "POST") {
      writes.push({ path: url.pathname, method, body });
      requisitionStatus = "draft";
      return route.fulfill({ status: 201, json: { id: 41, requisition_number: "PR-TEST-41", status: "draft" } });
    }
    if (url.pathname === "/api/purchasing/requisitions/41" && method === "GET") return route.fulfill({ json: { id: 41, requisition_number: "PR-TEST-41", requester_email: "owner@superbajaar.test", location_id: 3, location_name: location.name, department: "Operations", status: requisitionStatus, justification: "Maintain safety stock", lines: [{ id: 1, variant_id: 17, product_name: variant.product_name, sku: variant.sku, quantity: "12", estimated_unit_cost: "220.00", specification: null }], approval_events: [] } });
    if (url.pathname === "/api/purchasing/requisitions/41/submit" && method === "POST") {
      writes.push({ path: url.pathname, method });
      requisitionStatus = "submitted";
      return route.fulfill({ json: { id: 41, requisition_number: "PR-TEST-41", status: "submitted" } });
    }
    return route.fulfill({ status: 404, json: { detail: `Unexpected ${method} ${url.pathname}` } });
  });

  await openPurchasing(page);
  await page.getByLabel("Receive into location *").selectOption("3");
  await page.getByLabel("Department").fill("Operations");
  await page.getByLabel("Business justification *").fill("Maintain safety stock");
  await page.getByLabel("Variant *").selectOption("17");
  await page.getByLabel("Quantity *").fill("12");
  await page.getByLabel("Estimated unit cost ₹").fill("220");
  await page.getByRole("button", { name: "Create draft requisition" }).click();
  await expect(page.getByText("PR-TEST-41", { exact: true })).toBeVisible();
  await expect(page.getByRole("button", { name: "Submit for approval" })).toBeVisible();
  await page.getByRole("button", { name: "Submit for approval" }).click();
  await expect(page.getByText(/submitted for configured approval/)).toBeVisible();
  expect(writes.find(write => write.method === "POST" && write.path === "/api/purchasing/requisitions")?.body).toMatchObject({
    location_id: 3,
    department: "Operations",
    justification: "Maintain safety stock",
    lines: [{ variant_id: 17, quantity: 12, estimated_unit_cost: 220 }],
  });
  expect(writes.some(write => write.path === "/api/purchasing/requisitions/41/submit")).toBeTruthy();
});

test("approved requisition can be sourced through RFQ, quotation and draft PO award", async ({ page }) => {
  const writes = [];
  let rfqStatus = "draft";
  let quotationRecorded = false;
  await page.route("**/api/**", async route => {
    const request = route.request();
    const url = new URL(request.url());
    const method = request.method();
    const body = method === "POST" ? request.postDataJSON() : undefined;
    if (url.pathname === "/api/auth/me") return route.fulfill({ json: { user: { id: 1, full_name: "Owner", email: "owner@superbajaar.test", role: "owner" } } });
    if (url.pathname === "/api/health") return route.fulfill({ json: { status: "ok", database: "connected" } });
    if (url.pathname === "/api/purchasing/suppliers") return route.fulfill({ json: { items: [supplier] } });
    if (url.pathname === "/api/inventory/locations") return route.fulfill({ json: { items: [location] } });
    if (url.pathname === "/api/purchasing/orders") return route.fulfill({ json: { items: [] } });
    if (url.pathname === "/api/purchasing/orders/81" && method === "GET") return route.fulfill({ json: {
      id: 81, purchase_number: "PO-81", status: "draft", supplier_id: 5,
      supplier_name: supplier.name, location_id: 3, location_name: location.name,
      lines: [], total_amount: "2150.00", approval_required: true,
    } });
    if (url.pathname === "/api/catalogue/variants") return route.fulfill({ json: { items: [variant] } });
    if (url.pathname === "/api/purchasing/requisitions") return route.fulfill({ json: { items: [{ id: 51, requisition_number: "PR-APPROVED-51", requester_email: "buyer@superbajaar.test", location_id: 3, location_name: location.name, department: "Procurement", status: "approved", line_count: 1 }] } });
    if (url.pathname === "/api/purchasing/rfqs" && method === "GET") return route.fulfill({ json: { items: rfqStatus === "draft" ? [] : [{ id: 61, rfq_number: "RFQ-TEST-61", requisition_id: 51, status: rfqStatus, supplier_count: 1, quotation_count: quotationRecorded ? 1 : 0 }] } });
    if (url.pathname === "/api/purchasing/requisitions/51") return route.fulfill({ json: { id: 51, requisition_number: "PR-APPROVED-51", requester_email: "buyer@superbajaar.test", location_id: 3, location_name: location.name, department: "Procurement", status: "approved", justification: "Seasonal demand", lines: [{ id: 2, variant_id: 17, product_name: variant.product_name, sku: variant.sku, quantity: "10", estimated_unit_cost: "210.00" }], approval_events: [] } });
    if (url.pathname === "/api/purchasing/rfqs" && method === "POST") {
      writes.push({ path: url.pathname, method, body });
      rfqStatus = "draft";
      return route.fulfill({ status: 201, json: { id: 61, rfq_number: "RFQ-TEST-61", status: "draft" } });
    }
    if (url.pathname === "/api/purchasing/rfqs/61" && method === "GET") return route.fulfill({ json: {
      id: 61, rfq_number: "RFQ-TEST-61", requisition_id: 51, status: rfqStatus, terms: "Deliver to central warehouse",
      lines: [{ id: 4, variant_id: 17, product_name: variant.product_name, sku: variant.sku, quantity: "10" }],
      suppliers: [{ supplier_id: 5, name: supplier.name, response_status: quotationRecorded ? "responded" : "invited" }],
      quotations: quotationRecorded ? [{ id: 71, quotation_number: "Q-71", supplier_id: 5, supplier_name: supplier.name, status: "received", valid_until: null, lead_time_days: 4, freight_amount: "100.00", discount_amount: "0.00", tax_amount: "0.00", lines: [{ variant_id: 17, product_name: variant.product_name, sku: variant.sku, quantity: "10", unit_price: "205.00" }] }] : [],
    } });
    if (url.pathname === "/api/purchasing/rfqs/61/issue" && method === "POST") {
      writes.push({ path: url.pathname, method }); rfqStatus = "issued";
      return route.fulfill({ json: { id: 61, rfq_number: "RFQ-TEST-61", status: "issued" } });
    }
    if (url.pathname === "/api/purchasing/quotations" && method === "POST") {
      writes.push({ path: url.pathname, method, body }); quotationRecorded = true; rfqStatus = "evaluation";
      return route.fulfill({ status: 201, json: { id: 71, quotation_number: "Q-71", status: "received" } });
    }
    if (url.pathname === "/api/purchasing/rfqs/61/award" && method === "POST") {
      writes.push({ path: url.pathname, method, body }); rfqStatus = "awarded";
      return route.fulfill({ status: 201, json: { id: 81, purchase_number: "PO-81", status: "draft", approval_required: true } });
    }
    return route.fulfill({ status: 404, json: { detail: `Unexpected ${method} ${url.pathname}` } });
  });

  await openPurchasing(page);
  await page.getByRole("button", { name: /PR-APPROVED-51/ }).click();
  await page.getByLabel(supplier.name).check();
  await page.getByRole("button", { name: "Create RFQ" }).click();
  await expect(page.getByText("RFQ-TEST-61", { exact: true })).toBeVisible();
  await page.getByRole("button", { name: "Issue RFQ to invited suppliers" }).click();
  await page.getByLabel("Invited supplier *").selectOption("5");
  await page.getByLabel("Supplier quotation number *").fill("Q-71");
  await page.getByLabel("Unit price ₹").fill("205");
  await page.getByRole("button", { name: "Record quotation" }).click();
  await expect(page.getByText("Q-71 · North Star Supplies")).toBeVisible();
  page.once("dialog", dialog => dialog.accept());
  await page.getByRole("button", { name: "Award & create draft PO" }).click();
  await expect(page.getByText(/Quotation awarded\. Draft PO PO-81 created and still requires purchase approval\./)).toBeVisible();
  expect(writes.find(write => write.path === "/api/purchasing/rfqs" && write.method === "POST")?.body).toMatchObject({ requisition_id: 51, supplier_ids: [5] });
  expect(writes.find(write => write.path === "/api/purchasing/quotations")?.body).toMatchObject({ rfq_id: 61, supplier_id: 5, quotation_number: "Q-71", lines: [{ variant_id: 17, quantity: 10, unit_price: 205 }] });
  expect(writes.find(write => write.path === "/api/purchasing/rfqs/61/award")?.body).toEqual({ quotation_id: 71 });
});
