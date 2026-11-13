export const PRODUCT_IMAGE_MAX_BYTES = 10 * 1024 * 1024;
const MAX_IMAGE_EDGE = 1920;
const WEBP_QUALITY = 0.82;
const CONVERTIBLE_IMAGE_TYPES = new Set(["image/jpeg", "image/png"]);

export async function prepareProductImage(file, browser = globalThis) {
  if (!file) throw new Error("Choose a product image first.");
  if (file.size > PRODUCT_IMAGE_MAX_BYTES) {
    throw new Error("Image files must be 10 MB or smaller.");
  }

  // WebP stays untouched. GIF is kept animated instead of converting only its first frame.
  if (file.type === "image/webp" || file.type === "image/gif") return file;
  if (!CONVERTIBLE_IMAGE_TYPES.has(file.type)) {
    throw new Error("Choose a JPEG, PNG, WebP or GIF image.");
  }
  if (typeof browser.createImageBitmap !== "function" || !browser.document?.createElement || typeof browser.File !== "function") {
    throw new Error("This browser cannot prepare product images for WebP upload.");
  }

  const bitmap = await browser.createImageBitmap(file);
  let canvas;
  try {
    const width = Number(bitmap.width);
    const height = Number(bitmap.height);
    if (!Number.isFinite(width) || !Number.isFinite(height) || width <= 0 || height <= 0) {
      throw new Error("The selected image could not be decoded.");
    }

    const scale = Math.min(1, MAX_IMAGE_EDGE / Math.max(width, height));
    const outputWidth = Math.max(1, Math.round(width * scale));
    const outputHeight = Math.max(1, Math.round(height * scale));
    canvas = browser.document.createElement("canvas");
    canvas.width = outputWidth;
    canvas.height = outputHeight;
    const context = canvas.getContext("2d");
    if (!context) throw new Error("The selected image could not be prepared for WebP upload.");
    context.drawImage(bitmap, 0, 0, outputWidth, outputHeight);

    const webpBlob = await new Promise((resolve, reject) => {
      try {
        canvas.toBlob(blob => {
          if (!blob) {
            reject(new Error("The selected image could not be converted to WebP. Try another image."));
            return;
          }
          resolve(blob);
        }, "image/webp", WEBP_QUALITY);
      } catch (error) {
        reject(error);
      }
    });
    if (webpBlob.type !== "image/webp") {
      throw new Error("This browser could not convert the selected image to WebP. Update Chrome and try again.");
    }

    const originalName = String(file.name || "product-image").replace(/\.[^.]+$/, "") || "product-image";
    const output = new browser.File([webpBlob], originalName + ".webp", {
      type: "image/webp",
      lastModified: file.lastModified || Date.now(),
    });
    if (output.size > PRODUCT_IMAGE_MAX_BYTES) {
      throw new Error("The converted WebP image is larger than 10 MB. Choose a smaller image.");
    }
    return output;
  } finally {
    bitmap.close?.();
    if (canvas) {
      canvas.width = 0;
      canvas.height = 0;
    }
  }
}
