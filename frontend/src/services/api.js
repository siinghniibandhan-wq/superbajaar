// Use the deployed API by default in production while allowing Amplify build
// configuration to override it. Local development continues to use port 8001.
const configuredBase = import.meta.env.VITE_API_BASE_URL?.trim();
const productionApiBase = "https://superappkart.duckdns.org/api/v1";
const API_BASE_URL = (configuredBase || (import.meta.env.DEV
  ? "http://127.0.0.1:8001/api/v1"
  : productionApiBase)).replace(/\/+$/, "");

function readStoredToken() {
  try { return window.localStorage.getItem("superbajaar.access_token") || ""; }
  catch { return ""; }
}

export async function apiRequest(path, options = {}) {
  if (!API_BASE_URL) {
    throw new Error("Backend URL is not configured. Set VITE_API_BASE_URL in the frontend hosting environment.");
  }
  let response;
  const token = readStoredToken();
  try {
    response = await fetch(`${API_BASE_URL}${path.startsWith("/") ? path : `/${path}`}`, {
      ...options,
      headers: {
        Accept: "application/json",
        ...(options.body ? { "Content-Type": "application/json" } : {}),
        ...(token ? { Authorization: "Bearer " + token } : {}),
        ...(options.headers || {}),
      },
    });
  } catch {
    throw new Error("Cannot reach the Super Bajaar backend. Verify the API host is live and allows this Amplify origin in CORS.");
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
