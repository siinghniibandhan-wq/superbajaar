import { mkdir, writeFile } from "node:fs/promises";
import { resolve } from "node:path";

const configuredSiteUrl = process.env.VITE_SITE_URL || process.env.SITE_URL || "";
if (!configuredSiteUrl) {
  console.warn("[seo] VITE_SITE_URL is not set; sitemap.xml and robots.txt were not generated.");
  process.exit(0);
}

let siteUrl;
try {
  siteUrl = new URL(configuredSiteUrl);
  if (!["https:", "http:"].includes(siteUrl.protocol)) throw new Error("Only HTTP(S) site URLs are supported.");
} catch (error) {
  console.error("[seo] Invalid VITE_SITE_URL:", error.message);
  process.exit(1);
}

const origin = siteUrl.origin;
const publicRoutes = [
  "/", "/deals", "/pages/about-us", "/pages/faq",
  "/pages/shipping-delivery", "/pages/returns-refunds",
  "/pages/cancellation-policy", "/pages/privacy-policy",
  "/pages/terms-and-conditions",
];
const escapeXml = value => value.replaceAll("&", "&amp;").replaceAll("<", "&lt;").replaceAll(">", "&gt;").replaceAll('"', "&quot;").replaceAll("'", "&apos;");
const urls = publicRoutes.map(route => `  <url><loc>${escapeXml(origin + route)}</loc></url>`).join("\n");
const sitemap = `<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n${urls}\n</urlset>\n`;
const robots = `User-agent: *\nAllow: /\nDisallow: /admin/\nDisallow: /checkout\nDisallow: /account\nDisallow: /customer/login\nDisallow: /customer/register\nDisallow: /wishlist\n\nSitemap: ${origin}/sitemap.xml\n`;

const output = resolve("dist");
await mkdir(output, { recursive: true });
await Promise.all([
  writeFile(resolve(output, "sitemap.xml"), sitemap, "utf8"),
  writeFile(resolve(output, "robots.txt"), robots, "utf8"),
]);
console.log(`[seo] Generated sitemap.xml (${publicRoutes.length} public routes) and robots.txt for ${origin}`);
