import test from "node:test";
import assert from "node:assert/strict";
import { parseCsv, buildImportPlan, templateCsv, toCsv } from "../../src/features/catalogue/csvImport.js";

const categories = [
  { id: 1, name: "Grocery", parent_id: null },
  { id: 2, name: "Atta Dal Rice (ADR)", parent_id: 1 },
  { id: 3, name: "Beauty", parent_id: null },
  { id: 4, name: "Snacks", parent_id: 1 },
  { id: 5, name: "Snacks", parent_id: 3 },
  { id: 6, name: "Personal Care", parent_id: null },
];

test("parser handles quotes, embedded commas/newlines, BOM and CRLF", () => {
  const rows = parseCsv('﻿name,description\r\n"Rice, 5kg","Line1\nLine ""2"""\r\nTea,Good\r\n');
  assert.deepEqual(rows, [["name", "description"], ["Rice, 5kg", 'Line1\nLine "2"'], ["Tea", "Good"]]);
});

test("parser detects semicolon delimiter", () => {
  assert.deepEqual(parseCsv("name;price\nA;5"), [["name", "price"], ["A", "5"]]);
});

test("the downloadable template imports cleanly", () => {
  const plan = buildImportPlan(parseCsv(templateCsv()), { categories });
  assert.equal(plan.fatal, "");
  assert.equal(plan.items.length, 2);
  assert.deepEqual(plan.items.map(i => i.errors), [[], []]);
  assert.deepEqual(plan.items[0].payload.product.category_ids, [2]);
  assert.deepEqual(plan.items[1].payload.product.category_ids, [3, 6]);
  assert.equal(plan.items[0].payload.variants[0].mrp, 720);
});

test("header aliases, MRP default and currency symbols", () => {
  const ok = buildImportPlan(parseCsv('Product Name,Price,Category,GST,HSN\nTea,"₹1,200.50",Beauty,5%,0902'), { categories });
  assert.deepEqual(ok.items[0].errors, []);
  assert.equal(ok.items[0].payload.variants[0].selling_price, 1200.5);
  assert.equal(ok.items[0].payload.variants[0].mrp, 1200.5);
  assert.equal(ok.items[0].payload.product.tax_rate, 5);
  assert.equal(ok.items[0].payload.product.tax_code, "0902");
});

test("validation errors are reported per row", () => {
  const plan = buildImportPlan(parseCsv("name,selling_price,mrp,category,gst_rate\n,5,5,Beauty,\nA,-1,,Beauty,\nB,10,5,Beauty,\nC,10,10,Nope,\nD,10,10,Beauty,13\nE,10,10,Snacks,"), { categories });
  const msgs = plan.items.map(i => i.errors.join(" | "));
  assert.match(msgs[0], /name is required/i);
  assert.match(msgs[1], /Selling price must be/);
  assert.match(msgs[2], /MRP cannot be below/);
  assert.match(msgs[3], /does not exist/);
  assert.match(msgs[4], /GST rate/);
  assert.match(msgs[5], /several categories/);
});

test("rows with the same name become variants; exact duplicates are flagged", () => {
  const plan = buildImportPlan(parseCsv("name,category,selling_price,attr_size\nTee,Beauty,100,S\nTee,Beauty,110,M\nTee,Beauty,120,M"), { categories });
  assert.equal(plan.items.length, 1);
  assert.equal(plan.items[0].variantCount, 3);
  assert.match(plan.items[0].errors.join(" "), /Duplicate variant/);
  const dup = buildImportPlan(parseCsv("name,category,selling_price\nTea,Beauty,5\nTea,Beauty,6"), { categories });
  assert.match(dup.items[0].errors.join(" "), /appears twice/);
});

test("missing required columns is fatal; unknown columns are listed", () => {
  assert.match(buildImportPlan(parseCsv("title,foo\nA,1"), { categories }).fatal, /selling_price/);
  assert.match(buildImportPlan(parseCsv("price,foo\n1,1"), { categories }).fatal, /name/);
  assert.deepEqual(buildImportPlan(parseCsv("name,selling_price,colourway\nA,1,x"), { categories }).unknownColumns, ["colourway"]);
});

test("toCsv escapes", () => assert.equal(toCsv([["a,b", 'c"d']]), '"a,b","c""d"\r\n'));
