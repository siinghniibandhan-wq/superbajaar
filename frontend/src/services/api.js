const configuredBase = import.meta.env.VITE_API_BASE_URL?.trim();

function normalizeApiBase(value) {
  const fallback = import.meta.env.DEV ? "http://127.0.0.1:8001/api" : "";
  const candidate = (value || fallback).trim().replace(/\/+$/, "");
  if (!candidate) return "";
  if (/\/api$/i.test(candidate)) return candidate;
  return candidate + "/api";
}

const API_BASE_URL = normalizeApiBase(configuredBase);

function readStoredToken() {
  try { return window.localStorage.getItem("superbajaar.access_token") || ""; } catch { return ""; }
}

function normalizeRequestPath(path) {
  const raw = path.startsWith("/") ? path : `/${path}`;
  // The base URL owns the /api prefix; remove it from callers to prevent duplication.
  const withoutPrefix = raw.replace(/^\/api(?=\/|$)/i, "");
  return withoutPrefix || "/";
}

export async function apiRequest(path, options = {}) {
  if (!API_BASE_URL) {
    throw new Error("Backend URL is not configured in the production build. Configure VITE_API_BASE_URL to the reachable backend origin; /api is added automatically.");
  }

  const requestPath = normalizeRequestPath(path);
  const requestUrl = `${API_BASE_URL}${requestPath}`;
  const { skipAuth = false, ...fetchOptions } = options;
  const token = skipAuth ? "" : readStoredToken();
  const isFormData = typeof FormData !== "undefined" && fetchOptions.body instanceof FormData;
  let response;
  try {
    response = await fetch(requestUrl, {
      ...fetchOptions,
      headers: {
        // Avoid forcing JSON content type on GETs; it can trigger unnecessary
        // cross-origin preflight requests for public storefront catalogue reads.
        ...(fetchOptions.body !== undefined && !isFormData ? { "Content-Type": "application/json" } : {}),
        ...(token ? { Authorization: `Bearer ${token}` } : {}),
        ...(fetchOptions.headers || {}),
      },
    });
  } catch (cause) {
    // Fetch failures are commonly caused by CORS, TLS, DNS, or a stale frontend
    // deployment. Include the exact endpoint so the failing request is identifiable.
    const reason = cause instanceof Error && cause.name ? ` (${cause.name})` : "";
    throw new Error(`Network request failed for ${requestUrl}${reason}. Check this endpoint's browser Network entry and CORS response.`);
  }

  const contentType = response.headers.get("content-type") || "";
  const rawBody = await response.text();
  let body = rawBody;
  if (contentType.includes("application/json") && rawBody) {
    try { body = JSON.parse(rawBody); } catch { /* Keep the original response for diagnostics. */ }
  }

  if (!response.ok) {
    const message = typeof body === "object" && body !== null ? body.detail || body.message : body;
    if (response.status === 404) {
      const responseHint = typeof message === "string" && message.length < 180 ? ` Response: ${message}` : "";
      throw new Error(`404 from ${requestUrl}.${responseHint} Verify that this URL reaches the deployed FastAPI service and that its /api route is deployed.`);
    }
    throw new Error(message || `API request failed (${response.status}) at ${requestUrl}`);
  }
  if (typeof body === "string" && body === "") return null;
  return body;
}

export const healthApi = {
  check: () => apiRequest("/health"),
};
