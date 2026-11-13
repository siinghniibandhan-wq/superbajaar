import test from "node:test";
import assert from "node:assert/strict";
import { prepareProductImage, PRODUCT_IMAGE_MAX_BYTES } from "../../src/features/catalogue/productImageFormat.js";

function fakeBrowser({ blob = new Blob(["webp-content"], { type: "image/webp" }), width = 2400, height = 1200 } = {}) {
  const calls = { decoded: 0, drawn: null, requestedType: "", quality: 0 };
  class FakeFile {
    constructor(parts, name, options) {
      this.name = name;
      this.type = options.type;
      this.lastModified = options.lastModified;
      this.size = parts.reduce((total, part) => total + part.size, 0);
      this.parts = parts;
    }
  }
  return {
    calls,
    File: FakeFile,
    async createImageBitmap() {
      calls.decoded += 1;
      return { width, height, close() {} };
    },
    document: {
      createElement() {
        return {
          width: 0,
          height: 0,
          getContext() { return { drawImage(...args) { calls.drawn = args.slice(1); } }; },
          toBlob(callback, type, quality) {
            calls.requestedType = type;
            calls.quality = quality;
            callback(blob);
          },
        };
      },
    },
  };
}

test("converts JPEG and PNG files to resized WebP output", async () => {
  const browser = fakeBrowser();
  const source = { name: "blue-shirt.jpeg", type: "image/jpeg", size: 1024, lastModified: 123 };
  const result = await prepareProductImage(source, browser);

  assert.equal(result.name, "blue-shirt.webp");
  assert.equal(result.type, "image/webp");
  assert.equal(browser.calls.requestedType, "image/webp");
  assert.equal(browser.calls.quality, 0.82);
  assert.deepEqual(browser.calls.drawn, [0, 0, 1920, 960]);
});

test("does not re-encode existing WebP files", async () => {
  const browser = fakeBrowser();
  const source = { name: "product.webp", type: "image/webp", size: 200 };
  assert.equal(await prepareProductImage(source, browser), source);
  assert.equal(browser.calls.decoded, 0);
});

test("preserves GIF files instead of silently dropping animation", async () => {
  const browser = fakeBrowser();
  const source = { name: "animated.gif", type: "image/gif", size: 200 };
  assert.equal(await prepareProductImage(source, browser), source);
  assert.equal(browser.calls.decoded, 0);
});

test("rejects source files above the existing 10 MB upload limit", async () => {
  const source = { name: "large.png", type: "image/png", size: PRODUCT_IMAGE_MAX_BYTES + 1 };
  await assert.rejects(() => prepareProductImage(source, fakeBrowser()), /10 MB or smaller/);
});

test("rejects browsers that cannot encode WebP rather than uploading a mislabeled file", async () => {
  const browser = fakeBrowser({ blob: new Blob(["png"], { type: "image/png" }) });
  const source = { name: "product.png", type: "image/png", size: 200 };
  await assert.rejects(() => prepareProductImage(source, browser), /could not convert the selected image to WebP/);
});
