import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

function googleSiteVerification() {
  return {
    name: "google-site-verification",
    transformIndexHtml(html) {
      const token = process.env.VITE_GOOGLE_SITE_VERIFICATION || "";
      if (!token) return html;
      const safeToken = token.replace(/[&"<>]/g, character => ({ "&": "&amp;", "\"": "&quot;", "<": "&lt;", ">": "&gt;" }[character]));
      return html.replace("</head>", `    <meta name="google-site-verification" content="${safeToken}" />\n  </head>`);
    },
  };
}

export default defineConfig({
  plugins: [react(), googleSiteVerification()],
  server: { host: "0.0.0.0", port: 5173, strictPort: true },
  preview: { host: "0.0.0.0", port: 4173, strictPort: true },
});
