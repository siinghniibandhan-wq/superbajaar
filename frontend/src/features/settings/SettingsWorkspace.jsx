import { useEffect, useState } from "react";

const STORAGE_KEY = "superbajaar.admin.settings.v1";
const defaults = {
  businessName: "Super Bajaar",
  legalName: "",
  gstin: "",
  supportEmail: "",
  supportPhone: "",
  currency: "INR",
  timezone: "Asia/Kolkata",
  taxMode: "exclusive",
  defaultGstRate: "18",
  lowStockThreshold: "5",
  allowBackorders: false,
  requireOrderReview: true,
  deliveryMode: "serviceable-pincode",
  estimatedDeliveryDays: "2-5",
  orderEmailAlerts: true,
  stockAlerts: true,
  paymentAlerts: true,
  marketingEmails: false,
  theme: "system",
};

function readSettings() {
  try {
    const saved = JSON.parse(window.localStorage.getItem(STORAGE_KEY) || "{}");
    return { ...defaults, ...(saved && typeof saved === "object" ? saved : {}) };
  } catch {
    return { ...defaults };
  }
}

function Field({ label, value, onChange, type = "text", hint, ...props }) {
  return <label className="sb-settings-field">{label}
    <input type={type} value={value} onChange={event => onChange(event.target.value)} {...props} />
    {hint && <small>{hint}</small>}
  </label>;
}

export default function SettingsWorkspace({ onBack, user }) {
  const [settings, setSettings] = useState(readSettings);
  const [activeTab, setActiveTab] = useState("business");
  const [notice, setNotice] = useState("");
  const [error, setError] = useState("");

  useEffect(() => {
    try {
      const saved = window.localStorage.getItem(STORAGE_KEY);
      if (saved) setSettings({ ...defaults, ...JSON.parse(saved) });
    } catch { /* fall back to safe defaults */ }
  }, []);

  function update(key, value) {
    setSettings(previous => ({ ...previous, [key]: value }));
    setNotice("");
    setError("");
  }

  function save() {
    if (!settings.businessName.trim()) { setError("Business name is required."); return; }
    if (settings.gstin && !/^[0-9A-Z]{15}$/.test(settings.gstin.trim().toUpperCase())) {
      setError("GSTIN must contain 15 letters/numbers.");
      return;
    }
    const threshold = Number(settings.lowStockThreshold);
    if (!Number.isInteger(threshold) || threshold < 0) {
      setError("Low-stock threshold must be a whole number of 0 or more.");
      return;
    }
    try {
      window.localStorage.setItem(STORAGE_KEY, JSON.stringify({
        ...settings,
        businessName: settings.businessName.trim(),
        gstin: settings.gstin.trim().toUpperCase(),
      }));
      setNotice("Settings saved in this browser.");
      setError("");
    } catch {
      setError("This browser could not save settings. Check available site storage.");
    }
  }

  function reset() {
    setSettings({ ...defaults });
    try { window.localStorage.removeItem(STORAGE_KEY); } catch {}
    setNotice("Browser settings reset to defaults.");
    setError("");
  }

  function exportSettings() {
    const blob = new Blob([JSON.stringify(settings, null, 2)], { type: "application/json" });
    const url = URL.createObjectURL(blob);
    const anchor = document.createElement("a");
    anchor.href = url;
    anchor.download = "super-bajaar-settings.json";
    anchor.click();
    URL.revokeObjectURL(url);
  }

  const tabs = [
    ["business", "Business profile"],
    ["commerce", "Commerce & tax"],
    ["operations", "Inventory & delivery"],
    ["notifications", "Notifications"],
    ["access", "Account & access"],
  ];

  return <section className="sb-workspace sb-settings">
    <button className="sb-back" onClick={onBack} type="button">← All workspaces</button>
    <p className="sb-eyebrow">ADMINISTRATION · CONFIGURATION</p>
    <h1>Settings & Access</h1>
    <p>Configure the operating defaults used by this browser. Account security and shared server settings are managed separately by the backend.</p>
    {error && <p role="alert" className="sb-alert">{error}</p>}
    {notice && <p role="status" className="sb-success">{notice}</p>}
    <div className="sb-settings-layout">
      <nav className="sb-settings-tabs" aria-label="Settings sections">
        {tabs.map(([id, label]) => <button type="button" key={id} className={activeTab === id ? "is-active" : ""} onClick={() => setActiveTab(id)}>{label}</button>)}
      </nav>
      <div className="sb-settings-panel">
        {activeTab === "business" && <>
          <h2>Business profile</h2><p>Store identity and customer-facing contact details.</p>
          <div className="sb-settings-grid">
            <Field label="Store name *" value={settings.businessName} onChange={v => update("businessName", v)} required maxLength={120} />
            <Field label="Legal entity name" value={settings.legalName} onChange={v => update("legalName", v)} maxLength={160} />
            <Field label="GSTIN" value={settings.gstin} onChange={v => update("gstin", v.toUpperCase())} maxLength={15} hint="15-character GST identification number." />
            <Field label="Support email" type="email" value={settings.supportEmail} onChange={v => update("supportEmail", v)} maxLength={254} />
            <Field label="Support phone" type="tel" value={settings.supportPhone} onChange={v => update("supportPhone", v)} maxLength={20} />
            <label className="sb-settings-field">Display theme<select value={settings.theme} onChange={e => update("theme", e.target.value)}><option value="system">System default</option><option value="light">Light</option><option value="dark">Dark</option></select></label>
          </div>
        </>}
        {activeTab === "commerce" && <>
          <h2>Commerce & tax defaults</h2><p>Defaults for price entry and order processing. Confirm tax treatment with your accountant before production use.</p>
          <div className="sb-settings-grid">
            <label className="sb-settings-field">Currency<select value={settings.currency} onChange={e => update("currency", e.target.value)}><option value="INR">INR — Indian Rupee</option></select></label>
            <label className="sb-settings-field">Business timezone<select value={settings.timezone} onChange={e => update("timezone", e.target.value)}><option value="Asia/Kolkata">India Standard Time (Asia/Kolkata)</option><option value="UTC">UTC</option></select></label>
            <label className="sb-settings-field">Product price tax mode<select value={settings.taxMode} onChange={e => update("taxMode", e.target.value)}><option value="exclusive">Tax exclusive</option><option value="inclusive">Tax inclusive</option></select></label>
            <Field label="Default GST rate (%)" type="number" min="0" max="100" step="0.01" value={settings.defaultGstRate} onChange={v => update("defaultGstRate", v)} hint="Only a default; product-specific GST classification takes precedence." />
          </div>
          <label className="sb-settings-toggle"><input type="checkbox" checked={settings.requireOrderReview} onChange={e => update("requireOrderReview", e.target.checked)} /><span><strong>Require order review</strong><small>Keep this as an operating preference; it does not change server-side order rules.</small></span></label>
        </>}
        {activeTab === "operations" && <>
          <h2>Inventory & delivery</h2><p>Default operating thresholds and fulfilment preferences.</p>
          <div className="sb-settings-grid">
            <Field label="Low-stock alert threshold" type="number" min="0" step="1" value={settings.lowStockThreshold} onChange={v => update("lowStockThreshold", v)} hint="Alert when available stock reaches this quantity." />
            <label className="sb-settings-field">Delivery availability<select value={settings.deliveryMode} onChange={e => update("deliveryMode", e.target.value)}><option value="serviceable-pincode">Serviceable PIN codes only</option><option value="manual">Manual confirmation</option></select></label>
            <Field label="Estimated delivery window" value={settings.estimatedDeliveryDays} onChange={v => update("estimatedDeliveryDays", v)} maxLength={40} />
          </div>
          <label className="sb-settings-toggle"><input type="checkbox" checked={settings.allowBackorders} onChange={e => update("allowBackorders", e.target.checked)} /><span><strong>Allow backorders</strong><small>Saved as a browser preference only; stock/order APIs are not changed by this switch.</small></span></label>
        </>}
        {activeTab === "notifications" && <>
          <h2>Notification preferences</h2><p>Choose which operational alerts you want this browser to flag as preferred.</p>
          {[
            ["orderEmailAlerts", "Order updates", "New orders, cancellations and status changes."],
            ["stockAlerts", "Low-stock alerts", "Products reaching the configured stock threshold."],
            ["paymentAlerts", "Payment alerts", "Payment failures and reconciliation exceptions."],
            ["marketingEmails", "Marketing communications", "Promotional and campaign updates."],
          ].map(([key, title, description]) => <label className="sb-settings-toggle" key={key}><input type="checkbox" checked={settings[key]} onChange={e => update(key, e.target.checked)} /><span><strong>{title}</strong><small>{description}</small></span></label>)}
          <p className="sb-settings-note">These choices are stored locally; delivery of emails/SMS requires configured backend notification services.</p>
        </>}
        {activeTab === "access" && <>
          <h2>Account & access</h2><p>Current signed-in identity and security status.</p>
          <div className="sb-settings-account"><span className="sb-settings-avatar">{(user?.full_name || user?.email || "A").slice(0,1).toUpperCase()}</span><div><strong>{user?.full_name || "Signed-in user"}</strong><small>{user?.email || "Email not provided by authentication API"}</small><small>Role: {user?.role || "Not provided by API"}</small></div></div>
          <div className="sb-settings-note"><strong>Server-side access controls are not available in the current API.</strong><p>Creating users, assigning roles, changing permissions, password resets and session revocation must be implemented against the backend identity tables. This screen does not pretend those security actions are enabled.</p></div>
        </>}
        <div className="sb-settings-actions"><button className="sb-primary" type="button" onClick={save}>Save browser settings</button><button type="button" onClick={exportSettings}>Export settings</button><button type="button" onClick={reset}>Reset defaults</button></div>
        <p className="sb-settings-footnote">Important: these settings are stored only in this browser. They are not yet shared with other devices or persisted to PostgreSQL.</p>
      </div>
    </div>
  </section>;
}
