import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

const candidateRelease = process.env.AWS_COMMIT_ID || process.env.GITHUB_SHA || "local";
const releaseId = /^[0-9a-f]{7,64}$/i.test(candidateRelease) ? candidateRelease : "unknown";

function releaseMarker() {
  return {
    name: "super-bajaar-release-marker",
    transformIndexHtml(html) {
      return html.replace(
        "</head>",
        `<meta name="sb-release" content="${releaseId}" />\n  </head>`,
      );
    },
  };
}

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
  plugins: [react(), releaseMarker(), googleSiteVerification()],
  server: { host: "0.0.0.0", port: 5173, strictPort: true },
  preview: { host: "0.0.0.0", port: 4173, strictPort: true },
});
