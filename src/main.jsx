import React from "react";
import { createRoot } from "react-dom/client";

// Keep the existing Amplify root URL on the public storefront by default.
// Open ERP with ?admin=1 (no hosting rewrite needed), or /admin if the host
// rewrites SPA paths to index.html.
async function mountApplication() {
  const root = createRoot(document.getElementById("root"));
  const params = new URLSearchParams(window.location.search);
  const isAdminRoute =
    params.get("admin") === "1" ||
    window.location.pathname === "/admin" ||
    window.location.pathname.startsWith("/admin/");

  if (isAdminRoute) {
    await import("../frontend/src/styles.css");
    const { default: AdminApp } = await import("../frontend/src/app/App.jsx");
    root.render(<React.StrictMode><AdminApp /></React.StrictMode>);
    return;
  }

  await import("./styles.css");
  const { default: StorefrontApp } = await import("./App.jsx");
  root.render(<React.StrictMode><StorefrontApp /></React.StrictMode>);
}

mountApplication().catch(error => {
  console.error("Super Bajaar failed to start", error);
  const root = document.getElementById("root");
  if (root) root.textContent = "Super Bajaar could not load. Please refresh and try again.";
});
