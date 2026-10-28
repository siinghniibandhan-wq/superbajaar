// The storefront and ERP share the existing backend host, but use different
// API prefixes: the storefront calls /api/* while the ERP calls /api/v1/*.
// Amplify has historically supplied VITE_API_BASE_URL ending in /api, so
// normalize that value for this ERP client instead of generating /api/auth/*.
const configuredBase = import.meta.env.VITE_API_BASE_URL?.trim().replace(/\/+$/, "");
const productionApiOrigin = "https://superappkart.duckdns.org";
function resolveApiBase(value) {
  if (!value) {
    return import.meta.env.DEV
      ? "http://127.0.0.1:8001/api/v1"
      : `${productionApiOrigin}/api/v1`;
  }
  if (/\/api\/v1$/i.test(value)) return value;
  if (/\/api$/i.test(value)) return value + "/v1";
  return value + "/api/v1";
}
const API_BASE_URL = resolveApiBase(configuredBase);

function readStoredToken() {
  try { return window.localStorage.getItem("superbajaar.access_token") || ""; }
  catch { return ""; }
}

export async function apiRequest(path, options = {}) {
  const token = readStoredToken();
  let response;
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
    throw new Error(`Cannot reach the Super Bajaar API at ${API_BASE_URL}. Check backend availability and CORS for this Amplify origin.`);
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
