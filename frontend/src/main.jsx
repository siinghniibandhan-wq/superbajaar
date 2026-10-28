import React from "react";
import { createRoot } from "react-dom/client";

// Amplify builds this frontend directory. Keep the public storefront at "/"
// and expose the ERP workspace at "/?admin=1" without requiring a rewrite.
async function mountApplication() {
  const root = createRoot(document.getElementById("root"));
  const params = new URLSearchParams(window.location.search);
  const isAdminRoute =
    params.get("admin") === "1" ||
    window.location.pathname === "/admin" ||
    window.location.pathname.startsWith("/admin/");

  if (isAdminRoute) {
    await import("./styles.css");
    const { default: AdminApp } = await import("./app/App.jsx");
    root.render(<React.StrictMode><AdminApp /></React.StrictMode>);
    return;
  }

  await import("../../src/styles.css");
  const { default: StorefrontApp } = await import("../../src/App.jsx");
  root.render(<React.StrictMode><StorefrontApp /></React.StrictMode>);
}

mountApplication().catch(error => {
  console.error("Super Bajaar failed to start", error);
  const root = document.getElementById("root");
  if (root) root.textContent = "Super Bajaar could not load. Please refresh and try again.";
});
