import { fileURLToPath } from "node:url";
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

const frontendModules = fileURLToPath(new URL("./node_modules/", import.meta.url));

export default defineConfig({
  plugins: [react()],
  // The public storefront assets live in the repository-root public directory.
  publicDir: "../public",
  // The storefront source is shared from the repository root. Alias dependencies
  // to this app's installed modules so Vite can resolve imports outside frontend/.
  resolve: {
    alias: {
      "lucide-react": fileURLToPath(new URL("./node_modules/lucide-react", import.meta.url)),
      "react-dom": fileURLToPath(new URL("./node_modules/react-dom", import.meta.url)),
      "react": fileURLToPath(new URL("./node_modules/react", import.meta.url)),
    },
    dedupe: ["react", "react-dom"],
  },
  server: { host: "0.0.0.0", port: 5173, strictPort: true },
  preview: { host: "0.0.0.0", port: 4173, strictPort: true },
});
