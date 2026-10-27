const API_BASE_URL = (import.meta.env.VITE_API_BASE_URL || "http://127.0.0.1:8001/api/v1").replace(/\/$/, "");

export async function apiRequest(path, options = {}) {
  const response = await fetch(`${API_BASE_URL}${path.startsWith("/") ? path : `/${path}`}`, {
    ...options,
    headers: { "Content-Type": "application/json", ...(options.headers || {}) },
  });
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
