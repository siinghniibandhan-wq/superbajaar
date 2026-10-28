const configuredBase = import.meta.env.VITE_API_BASE_URL?.trim();

function normalizeApiBase(value) {
  const fallback = import.meta.env.DEV ? "http://127.0.0.1:8001/api/v1" : "";
  const candidate = (value || fallback).trim().replace(/\/+$/, "");
  if (!candidate) return "";
  // Accept a backend origin, /api, /api/v1, or a same-origin /api/v1 proxy.
  if (/\/api\/v1$/i.test(candidate)) return candidate;
  if (/\/api$/i.test(candidate)) return candidate + "/v1";
  return candidate + "/api/v1";
}

const API_BASE_URL = normalizeApiBase(configuredBase);

function readStoredToken() {
  try { return window.localStorage.getItem("superbajaar.access_token") || ""; } catch { return ""; }
}

function normalizeRequestPath(path) {
  const raw = path.startsWith("/") ? path : \`/\${path}\`;
  // Keep the shared prefix authoritative even if a caller supplies it itself.
  const withoutPrefix = raw.replace(/^\/api\/v1(?=\/|$)/i, "");
  return withoutPrefix || "/";
}

export async function apiRequest(path, options = {}) {
  if (!API_BASE_URL) {
    throw new Error("Backend URL is not configured in the production build. Configure VITE_API_BASE_URL to the reachable backend origin; /api/v1 is added automatically.");
  }

  const requestPath = normalizeRequestPath(path);
  const requestUrl = \`\${API_BASE_URL}\${requestPath}\`;
  const token = readStoredToken();
  let response;
  try {
    response = await fetch(requestUrl, {
      ...options,
      headers: {
        "Content-Type": "application/json",
        ...(token ? { Authorization: \`Bearer \${token}\` } : {}),
        ...(options.headers || {}),
      },
    });
  } catch {
    throw new Error(\`Cannot reach the Super Bajaar API at \${API_BASE_URL}. Check backend availability and CORS.\`);
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
      const responseHint = typeof message === "string" && message.length < 180 ? \` Response: \${message}\` : "";
      throw new Error(\`404 from \${requestUrl}.\${responseHint} Verify that this URL reaches the deployed FastAPI service and that its /api/v1 route is deployed.\`);
    }
    throw new Error(message || \`API request failed (\${response.status}) at \${requestUrl}\`);
  }
  if (typeof body === "string" && body === "") return null;
  return body;
}

export const healthApi = {
  check: () => apiRequest("/health"),
};
