import { useEffect, useState } from "react";
import "./GoogleAnalytics.css";

const CONSENT_KEY = "sb.analytics.consent";
const measurementId = import.meta.env.VITE_GA4_MEASUREMENT_ID || "";

function hasConsent() {
  try { return window.localStorage.getItem(CONSENT_KEY) === "granted"; } catch { return false; }
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

export function trackAnalyticsEvent(name, params = {}) {
  if (!measurementId || !hasConsent() || typeof window.gtag !== "function") return;
  window.gtag("event", name, params);
}

export default function GoogleAnalytics({ pagePath }) {
  const [consent, setConsent] = useState(hasConsent);

  useEffect(() => {
    if (!measurementId || !consent) return;
    loadGoogleTag();
    window.gtag("event", "page_view", {
      page_title: document.title,
      page_location: window.location.href,
      page_path: pagePath || window.location.pathname,
    });
  }, [consent, pagePath]);

  if (!measurementId || consent) return null;

  const choose = value => {
    try { window.localStorage.setItem(CONSENT_KEY, value); } catch { /* Consent remains session-only if storage is unavailable. */ }
    setConsent(value === "granted");
  };

  return <aside className="sb-analytics-consent" aria-label="Analytics preferences">
    <div><strong>Help us improve Super Bajaar</strong><p>Allow privacy-conscious Google Analytics measurement to help us understand site usage. You can continue shopping if you decline.</p></div>
    <div className="sb-analytics-consent-actions">
      <button type="button" onClick={() => choose("denied")}>Decline</button>
      <button type="button" onClick={() => choose("granted")}>Allow analytics</button>
    </div>
  </aside>;
}
