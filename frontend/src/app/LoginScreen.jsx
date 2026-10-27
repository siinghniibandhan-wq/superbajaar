import { useState } from "react";
import { apiRequest } from "../services/api.js";

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
      if (!response?.access_token) throw new Error("Login response did not include an access token.");
      try { window.localStorage.setItem("superbajaar.access_token", response.access_token); } catch {}
      onSignedIn(response.user);
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
