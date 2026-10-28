import { useEffect, useState } from "react";
import { apiRequest } from "../../services/api.js";

const defaults = {
  businessName: "Super Bajaar", legalName: "", gstin: "", supportEmail: "", supportPhone: "",
  currency: "INR", timezone: "Asia/Kolkata", taxMode: "exclusive", defaultGstRate: "18",
  lowStockThreshold: "5", allowBackorders: false, requireOrderReview: true,
  deliveryMode: "serviceable-pincode", estimatedDeliveryDays: "2-5",
  orderEmailAlerts: true, stockAlerts: true, paymentAlerts: true, marketingEmails: false, theme: "system",
};

function Field({ label, value, onChange, type = "text", hint, ...props }) {
  return <label className="sb-settings-field">{label}
    <input type={type} value={value} onChange={event => onChange(event.target.value)} {...props} />
    {hint && <small>{hint}</small>}
  </label>;
}

export default function SettingsWorkspace({ onBack, user }) {
  const [settings, setSettings] = useState({ ...defaults });
  const [activeTab, setActiveTab] = useState("business");
  const [notice, setNotice] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [updatedAt, setUpdatedAt] = useState(null);

  async function loadSettings() {
    setLoading(true);
    setError("");
    try {
      const result = await apiRequest("/settings");
      setSettings({ ...defaults, ...(result.settings || {}) });
      setUpdatedAt(result.updated_at || null);
      setNotice("Loaded shared settings from the server.");
    } catch (reason) {
      setError(reason.message || "Unable to load shared settings. Verify the backend and apply migration 008.");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => { loadSettings(); }, []);

  function update(key, value) {
    setSettings(previous => ({ ...previous, [key]: value }));
    setNotice("");
    setError("");
  }

  async function persist(nextSettings, successMessage) {
    if (!nextSettings.businessName?.trim()) { setError("Business name is required."); return; }
    const gstin = (nextSettings.gstin || "").trim().toUpperCase();
    if (gstin && !/^[0-9A-Z]{15}$/.test(gstin)) { setError("GSTIN must contain 15 letters/numbers."); return; }
    const threshold = Number(nextSettings.lowStockThreshold);
    if (!Number.isInteger(threshold) || threshold < 0 || threshold > 1000000) {
      setError("Low-stock threshold must be a whole number between 0 and 1,000,000."); return;
    }
    const rate = Number(nextSettings.defaultGstRate);
    if (!Number.isFinite(rate) || rate < 0 || rate > 100) { setError("Default GST rate must be between 0 and 100."); return; }
    setSaving(true); setError(""); setNotice("");
    try {
      const result = await apiRequest("/settings", {
        method: "PUT",
        body: JSON.stringify({ ...nextSettings, businessName: nextSettings.businessName.trim(), gstin }),
      });
      setSettings({ ...defaults, ...(result.settings || nextSettings) });
      setUpdatedAt(result.updated_at || null);
      setNotice(successMessage);
    } catch (reason) {
      setError(reason.message || "Could not save shared settings.");
    } finally { setSaving(false); }
  }

  function reset() {
    const confirmed = window.confirm("Reset shared Super Bajaar settings to their defaults for all users?");
    if (confirmed) persist({ ...defaults }, "Shared settings reset to defaults.");
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

  const canManage = ["owner", "admin"].includes(user?.role);
  const tabs = [
    ["business", "Business profile"], ["commerce", "Commerce & tax"],
    ["operations", "Inventory & delivery"], ["notifications", "Notifications"], ["access", "Account & access"],
  ];

  return <section className="sb-workspace sb-settings">
    <button className="sb-back" onClick={onBack} type="button">← All workspaces</button>
    <p className="sb-eyebrow">ADMINISTRATION · CONFIGURATION</p>
    <h1>Settings & Access</h1>
    <p>Shared operating defaults are stored in PostgreSQL and apply across signed-in devices.</p>
    {loading && <p role="status" className="sb-settings-note">Loading shared settings…</p>}
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
            <Field label="Default GST rate (%)" type="number" min="0" max="100" step="0.01" value={settings.defaultGstRate} onChange={v => update("defaultGstRate", v)} hint="Default only; product-specific tax classification takes precedence." />
          </div>
          <label className="sb-settings-toggle"><input type="checkbox" checked={settings.requireOrderReview} onChange={e => update("requireOrderReview", e.target.checked)} /><span><strong>Require order review</strong><small>Saved as a shared operating preference. Order API enforcement requires separate workflow integration.</small></span></label>
        </>}
        {activeTab === "operations" && <>
          <h2>Inventory & delivery</h2><p>Default operating thresholds and fulfilment preferences.</p>
          <div className="sb-settings-grid">
            <Field label="Low-stock alert threshold" type="number" min="0" max="1000000" step="1" value={settings.lowStockThreshold} onChange={v => update("lowStockThreshold", v)} hint="Configured threshold; alert delivery requires notification integration." />
            <label className="sb-settings-field">Delivery availability<select value={settings.deliveryMode} onChange={e => update("deliveryMode", e.target.value)}><option value="serviceable-pincode">Serviceable PIN codes only</option><option value="manual">Manual confirmation</option></select></label>
            <Field label="Estimated delivery window" value={settings.estimatedDeliveryDays} onChange={v => update("estimatedDeliveryDays", v)} maxLength={40} />
          </div>
          <label className="sb-settings-toggle"><input type="checkbox" checked={settings.allowBackorders} onChange={e => update("allowBackorders", e.target.checked)} /><span><strong>Allow backorders</strong><small>Stored as a shared preference; stock/order APIs still need to enforce this policy.</small></span></label>
        </>}
        {activeTab === "notifications" && <>
          <h2>Notification preferences</h2><p>Shared preferences for operational alerts.</p>
          {[
            ["orderEmailAlerts", "Order updates", "New orders, cancellations and status changes."],
            ["stockAlerts", "Low-stock alerts", "Products reaching the configured stock threshold."],
            ["paymentAlerts", "Payment alerts", "Payment failures and reconciliation exceptions."],
            ["marketingEmails", "Marketing communications", "Promotional and campaign updates."],
          ].map(([key, title, description]) => <label className="sb-settings-toggle" key={key}><input type="checkbox" checked={settings[key]} onChange={e => update(key, e.target.checked)} /><span><strong>{title}</strong><small>{description}</small></span></label>)}
          <p className="sb-settings-note">Preferences persist on the server. Actual email/SMS delivery requires provider credentials and notification workers.</p>
        </>}
        {activeTab === "access" && <>
          <h2>Account & access</h2><p>Signed-in identity and current permissions.</p>
          <div className="sb-settings-account"><span className="sb-settings-avatar">{(user?.full_name || user?.email || "A").slice(0,1).toUpperCase()}</span><div><strong>{user?.full_name || "Signed-in user"}</strong><small>{user?.email || "Email not provided by authentication API"}</small><small>Role: {user?.role || "Not provided by API"}</small></div></div>
          <div className="sb-settings-note"><strong>{canManage ? "Settings administrator" : "Read-only settings access"}</strong><p>{canManage ? "Your role can update shared business settings. User creation, role assignment and password reset remain separate security operations and are not exposed here." : "Only owners and admins can change shared business settings. Contact an owner or admin to request a change."}</p></div>
        </>}
        <div className="sb-settings-actions">
          <button className="sb-primary" type="button" onClick={() => persist(settings, "Shared settings saved successfully.")} disabled={loading || saving || !canManage}>{saving ? "Saving…" : "Save shared settings"}</button>
          <button type="button" onClick={exportSettings} disabled={loading}>Export settings</button>
          <button type="button" onClick={reset} disabled={loading || saving || !canManage}>Reset shared defaults</button>
          <button type="button" onClick={loadSettings} disabled={loading || saving}>Reload from server</button>
        </div>
        <p className="sb-settings-footnote">{updatedAt ? `Last server update: ${new Date(updatedAt).toLocaleString()}. ` : ""}Settings are shared through the backend; this workspace does not store the settings in browser local storage.</p>
      </div>
    </div>
  </section>;
}
