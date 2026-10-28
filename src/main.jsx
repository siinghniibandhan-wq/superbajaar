import React from "react";
import { createRoot } from "react-dom/client";

// Keep the public storefront at the existing Amplify root URL.
// The ERP workspace remains available at /admin without changing AWS settings.
async function mountApplication() {
  const root = createRoot(document.getElementById("root"));
  if (window.location.pathname === "/admin" || window.location.pathname.startsWith("/admin/")) {
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
