const configuredBase = import.meta.env.VITE_API_BASE_URL?.trim();
const API_BASE_URL = (configuredBase || (import.meta.env.DEV ? "http://127.0.0.1:8001/api/v1" : "")).replace(/\/$/, "");

function readStoredToken() { try { return window.localStorage.getItem("superbajaar.access_token") || ""; } catch { return ""; } }

export async function apiRequest(path, options = {}) {
  if (!API_BASE_URL) {
    throw new Error("Backend URL is not configured. Set VITE_API_BASE_URL in the frontend hosting environment.");
  }
  let response;
  try {
    response = await fetch(`${API_BASE_URL}${path.startsWith("/") ? path : `/${path}`}`, {
      ...options,
      headers: { "Content-Type": "application/json", ...(readStoredToken() ? { Authorization: "Bearer " + readStoredToken() } : {}), ...(options.headers || {}) },
    });
  } catch {
    throw new Error("Cannot reach the Super Bajaar backend. Check VITE_API_BASE_URL, server health and CORS settings.");
  }
  const contentType = response.headers.get("content-type") || "";
  const body = contentType.includes("application/json") ? await response.json() : await response.text();
  if (!response.ok) {
    const message = typeof body === "object" && body !== null ? body.detail || body.message : body;
    throw new Error(message || `API request failed (${response.status})`);
  }
  return body;
}

export const healthApi = {
  check: () => apiRequest("/health"),
};
