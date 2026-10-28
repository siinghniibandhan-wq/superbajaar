import { useState } from "react";
import { apiRequest } from "../services/api.js";

function normalizeLoginResponse(response) {
  // Support the canonical FastAPI response and common API gateway wrappers.
  const payload = response?.data && typeof response.data === "object" ? response.data : response;
  const token = payload?.access_token || payload?.accessToken || payload?.token || payload?.data?.access_token || payload?.data?.accessToken;
  const user = payload?.user || payload?.data?.user || (payload?.id || payload?.email ? payload : null);
  return { token, user, keys: payload && typeof payload === "object" ? Object.keys(payload) : [] };
}

export default function LoginScreen({ onSignedIn }) {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  async function submit(event) {
    event.preventDefault();
    setBusy(true);
    setError("");
    try {
      const response = await apiRequest("/auth/login", { method: "POST", body: JSON.stringify({ email, password }) });
      const { token, user, keys } = normalizeLoginResponse(response);
      if (!token) {
        const shape = keys.length ? keys.join(", ") : typeof response;
        throw new Error(`The configured login API returned no access token (response fields: ${shape}). Check VITE_API_BASE_URL points to the Super Bajaar API ending in /api/v1.`);
      }
      if (!user || typeof user !== "object") {
        throw new Error("Login API returned an access token but no user profile. Check the configured authentication API.");
      }
      try { window.localStorage.setItem("superbajaar.access_token", token); } catch {}
      onSignedIn(user);
    } catch (reason) {
      setError(reason.message || "Unable to sign in.");
    } finally {
      setBusy(false);
    }
  }

  return <main className="sb-login-page">
    <form className="sb-login-card" onSubmit={submit}>
      <div className="sb-login-mark">S</div>
      <p className="sb-eyebrow">SUPER BAJAAR · SECURE ACCESS</p>
      <h1>Welcome back</h1>
      <p>Sign in to open your business workspaces.</p>
      {error && <p className="sb-alert" role="alert">{error}</p>}
      <label>Email address<input type="email" autoComplete="username" required maxLength={254} value={email} onChange={event => setEmail(event.target.value)} /></label>
      <label>Password<input type="password" autoComplete="current-password" required maxLength={1024} value={password} onChange={event => setPassword(event.target.value)} /></label>
      <button className="sb-primary" type="submit" disabled={busy}>{busy ? "Signing in…" : "Sign in"}</button>
      <small>Initial owner access must be created using the backend bootstrap command after the access-control migration is reviewed and applied.</small>
    </form>
  </main>;
}
