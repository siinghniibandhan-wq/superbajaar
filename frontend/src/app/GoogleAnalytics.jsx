import { useEffect, useState } from "react";
import "./GoogleAnalytics.css";

const CONSENT_KEY = "sb.analytics.consent";
const measurementId = import.meta.env.VITE_GA4_MEASUREMENT_ID || "";

function readConsent() {
  try { return window.localStorage.getItem(CONSENT_KEY); } catch { return null; }
}

function hasConsent() {
  return readConsent() === "granted";
}

function loadGoogleTag() {
  if (!measurementId || window.gtag) return;
  window.dataLayer = window.dataLayer || [];
  window.gtag = function gtag() { window.dataLayer.push(arguments); };
  window.gtag("js", new Date());
  window.gtag("config", measurementId, { send_page_view: false, allow_google_signals: false });
  const script = document.createElement("script");
  script.async = true;
  script.src = "https://www.googletagmanager.com/gtag/js?id=" + encodeURIComponent(measurementId);
  script.dataset.sbGoogleAnalytics = "true";
  document.head.appendChild(script);
}

export function getAnalyticsConsent() {
  try { return window.localStorage.getItem(CONSENT_KEY) === "granted"; } catch { return false; }
}

export function setAnalyticsConsent(granted) {
  const value = granted ? "granted" : "denied";
  try { window.localStorage.setItem(CONSENT_KEY, value); } catch {}
  if (typeof window.gtag === "function") {
    window.gtag("consent", "update", {
      analytics_storage: granted ? "granted" : "denied",
      ad_storage: "denied",
      ad_user_data: "denied",
      ad_personalization: "denied",
    });
  }
  window.dispatchEvent(new CustomEvent("sb:analytics-consent", { detail: { granted, value } }));
}

export function trackAnalyticsEvent(name, params = {}) {
  if (!measurementId || !hasConsent() || typeof window.gtag !== "function") return;
  window.gtag("event", name, params);
}

export default function GoogleAnalytics({ pagePath }) {
  const [consent, setConsent] = useState(readConsent);
  useEffect(() => {
    const syncConsent = event => setConsent(event.detail?.value ?? (event.detail?.granted ? "granted" : "denied"));
    window.addEventListener("sb:analytics-consent", syncConsent);
    return () => window.removeEventListener("sb:analytics-consent", syncConsent);
  }, []);

  useEffect(() => {
    if (!measurementId || consent !== "granted") return;
    loadGoogleTag();
    window.gtag("event", "page_view", {
      page_title: document.title,
      page_location: window.location.href,
      page_path: pagePath || window.location.pathname,
    });
  }, [consent, pagePath]);

  if (!measurementId || consent !== null) return null;

  const choose = value => {
    try { window.localStorage.setItem(CONSENT_KEY, value); } catch { /* Consent remains session-only if storage is unavailable. */ }
    setConsent(value);
  };

  return <aside className="sb-analytics-consent" aria-label="Analytics preferences">
    <div><strong>Help us improve Super Bajaar</strong><p>Allow privacy-conscious Google Analytics measurement to help us understand site usage. You can continue shopping if you decline.</p></div>
    <div className="sb-analytics-consent-actions">
      <button type="button" onClick={() => choose("denied")}>Decline</button>
      <button type="button" onClick={() => choose("granted")}>Allow analytics</button>
    </div>
  </aside>;
}
