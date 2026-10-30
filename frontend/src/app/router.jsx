import { useEffect, useState } from "react";
import { AppProviders } from "./providers.jsx";
import CatalogueWorkspace from "../features/catalogue/CatalogueWorkspace.jsx";
import InventoryWorkspace from "../features/inventory/InventoryWorkspace.jsx";
import PricingWorkspace from "../features/pricing/PricingWorkspace.jsx";
import DashboardWorkspace from "../features/dashboard/DashboardWorkspace.jsx";
import OrdersWorkspace from "../features/orders/OrdersWorkspace.jsx";
import PaymentsWorkspace from "../features/payments/PaymentsWorkspace.jsx";
import DeliveryWorkspace from "../features/delivery/DeliveryWorkspace.jsx";
import CustomersWorkspace from "../features/customers/CustomersWorkspace.jsx";
import PurchasingWorkspace from "../features/purchasing/PurchasingWorkspace.jsx";
import POSWorkspace from "../features/pos/POSWorkspace.jsx";
import ReportsWorkspace from "../features/reports/ReportsWorkspace.jsx";
import SettingsWorkspace from "../features/settings/SettingsWorkspace.jsx";
import LoyaltyWorkspace from "../features/loyalty/LoyaltyWorkspace.jsx";
import AccountingWorkspace from "../features/accounting/AccountingWorkspace.jsx";
import HRWorkspace from "../features/hr/HRWorkspace.jsx";
import { apiRequest, healthApi } from "../services/api.js";
import LoginScreen from "./LoginScreen.jsx";
import Storefront from "./Storefront.jsx";

const groups = [
  { title: "Commerce", items: [
    { id: "dashboard", label: "Dashboard", description: "Business overview and alerts" },
    { id: "catalogue", label: "Catalogue", description: "Categories, products, attributes, variants and images" },
    { id: "pricing", label: "Pricing & Promotions", description: "Price lists, discounts and offers" },
    { id: "orders", label: "Orders", description: "Website and POS order lifecycle" },
    { id: "payments", label: "Payments & Refunds", description: "Payment status, refunds and reconciliation" },
  ]},
  { title: "Operations", items: [
    { id: "inventory", label: "Inventory", description: "Stock balances, locations, movements and adjustments" },
    { id: "purchase", label: "Purchasing", description: "Suppliers, purchase orders and goods receipt" },
    { id: "delivery", label: "Delivery", description: "PIN serviceability, dispatch and tracking" },
    { id: "pos", label: "POS & Stores", description: "Walk-in sales, receipts and shift closing" },
  ]},
  { title: "Customers & Growth", items: [
    { id: "customers", label: "Customers & CRM", description: "Customer profiles, enquiries and history" },
    { id: "loyalty", label: "Loyalty & Rewards", description: "Points, rewards and customer benefits" },
  ]},
  { title: "Business Management", items: [
    { id: "accounting", label: "Accounting & Tax", description: "Ledgers, journals, GST and financial reports" },
    { id: "hr", label: "HR & Payroll", description: "Employees, attendance, salary and payslips" },
    { id: "reports", label: "Reports", description: "Sales, stock, margin and operational reporting" },
    { id: "settings", label: "Settings & Access", description: "Users, roles, permissions and configuration" },
  ]},
];
const allItems = groups.flatMap(group => group.items);

function ModuleLauncher({ onOpen }) {
  return <section className="sb-launcher">
    <div className="sb-intro"><p className="sb-eyebrow">SUPER BAJAAR · OPERATIONS</p><h1>Workspaces</h1><p>Each business function has its own workspace. Open only the module you need.</p></div>
    {groups.map((group, index) => <section className="sb-module-group" key={group.title}>
      <div className="sb-group-heading"><h2>{group.title}</h2><span>{group.items.length} modules</span></div>
      <div className="sb-grid">{group.items.map((item, i) => <button className="sb-tile" key={item.id} type="button" onClick={() => onOpen(item)}>
        <span className={`sb-tile-icon sb-tone-${(index + i) % 5}`}>{item.label.slice(0,1)}</span>
        <span className="sb-tile-copy"><strong>{item.label}</strong><small>{item.description}</small></span><span className="sb-arrow" aria-hidden="true">↗</span>
      </button>)}</div>
    </section>)}
  </section>;
}

function Workspace({ item, onBack }) {
  return <section className="sb-workspace">
    <button className="sb-back" type="button" onClick={onBack}>← All workspaces</button>
    <p className="sb-eyebrow">SEPARATE WORKSPACE</p><h1>{item.label}</h1><p>{item.description}</p>
    <div className="sb-notice"><strong>This module is not implemented yet</strong><span>The module has its own entry point, but its operational screens and APIs are not complete. It is intentionally not mixed into another module or represented as working functionality.</span></div>
  </section>;
}

function AppShell() {
  const [selected, setSelected] = useState(null);
  const [apiStatus, setApiStatus] = useState("checking");
  const [user, setUser] = useState(null);
  const [authChecked, setAuthChecked] = useState(false);
  useEffect(() => {
    let active = true;
    healthApi.check().then(result => { if (active) setApiStatus(result?.status === "ok" ? "online" : "offline"); })
      .catch(() => { if (active) setApiStatus("offline"); });
    return () => { active = false; };
  }, []);
  useEffect(() => {
    let active = true;
    let token = "";
    try { token = window.localStorage.getItem("superbajaar.access_token") || ""; } catch {}
    if (!token) { setAuthChecked(true); return () => { active = false; }; }
    apiRequest("/auth/me").then(result => { if (active) setUser(result.user); }).catch(() => {
      try { window.localStorage.removeItem("superbajaar.access_token"); } catch {}
      if (active) setUser(null);
    }).finally(() => { if (active) setAuthChecked(true); });
    return () => { active = false; };
  }, []);
  const statusText = { checking: "Checking API…", online: "Backend connected", offline: "Backend unavailable" };
  const open = item => setSelected(item);
  const back = () => setSelected(null);
  const activeModule = selected?.id;
  const openById = id => { const found = allItems.find(item => item.id === id); if (found) setSelected(found); };
  if (!authChecked) return <main className="sb-login-page"><p>Checking sign-in…</p></main>;
  if (!user) return <LoginScreen onSignedIn={setUser} />;
  if (!["owner", "admin"].includes(String(user.role || "").toLowerCase())) return <main className="sb-login-page"><section className="sb-login-card"><div className="sb-login-mark">S</div><p className="sb-eyebrow">SUPER BAJAAR · ACCESS CONTROL</p><h1>Admin access required</h1><p>Your account does not have permission to open the Admin Console.</p><button className="sb-primary" type="button" onClick={() => { window.location.assign("/"); }}>Return to storefront</button></section></main>;
  return <main className="sb-shell">
    <header className="sb-header">
      <button className="sb-brand" type="button" onClick={back} aria-label="Back to workspaces"><span className="sb-mark">S</span><span><strong>Super Bajaar</strong><small>Commerce & ERP</small></span></button>
      <div className="sb-header-actions"><span className={`sb-status sb-status-${apiStatus}`} role="status"><i />{statusText[apiStatus]}</span><span className="sb-user-label">{user.full_name || user.email}</span><button className="sb-signout" type="button" onClick={async () => { try { await apiRequest("/auth/logout", { method: "POST" }); } catch {} try { window.localStorage.removeItem("superbajaar.access_token"); } catch {} setUser(null); setSelected(null); }}>Sign out</button></div>
    </header>
    <div className="sb-app-layout">
      <aside className="sb-sidebar" aria-label="Module navigation">
        <button className={`sb-nav-home ${!selected ? "is-active" : ""}`} type="button" onClick={back}>⌂ <span>All workspaces</span></button>
        {groups.map(group => <div className="sb-nav-group" key={group.title}><p>{group.title}</p>{group.items.map(item => <button key={item.id} type="button" className={`sb-nav-item ${activeModule === item.id ? "is-active" : ""}`} onClick={() => open(item)}><span>{item.label}</span></button>)}</div>)}
      </aside>
      <div className="sb-main-content">
        {selected?.id === "dashboard" ? <DashboardWorkspace onOpen={openById} /> : selected?.id === "pos" ? <POSWorkspace onBack={back} /> : selected?.id === "reports" ? <ReportsWorkspace onBack={back} /> : selected?.id === "settings" ? <SettingsWorkspace onBack={back} currentUser={user} /> : selected?.id === "loyalty" ? <LoyaltyWorkspace onBack={back} /> : selected?.id === "accounting" ? <AccountingWorkspace onBack={back} /> : selected?.id === "hr" ? <HRWorkspace onBack={back} currentUser={user} /> : selected?.id === "orders" ? <OrdersWorkspace onBack={back} /> : selected?.id === "payments" ? <PaymentsWorkspace onBack={back} /> : selected?.id === "delivery" ? <DeliveryWorkspace onBack={back} /> : selected?.id === "catalogue" ? <CatalogueWorkspace onBack={back} currentUser={user} /> : selected?.id === "inventory" ? <InventoryWorkspace onBack={back} /> : selected?.id === "pricing" ? <PricingWorkspace onBack={back} /> : selected?.id === "customers" ? <CustomersWorkspace onBack={back} /> : selected?.id === "purchase" ? <PurchasingWorkspace onBack={back} /> : selected ? <Workspace item={selected} onBack={back} /> : <ModuleLauncher onOpen={open} />}
      </div>
    </div>
    <footer>Super Bajaar · Separate module workspaces · Backend port 8001 · PostgreSQL port 5432</footer>
  </main>;
}
function AdminApp() { return <AppProviders><AppShell /></AppProviders>; }

export function Router() {
  const path = window.location.pathname.replace(/\/+$/, "") || "/";
  if (path === "/admin" || path.startsWith("/admin/")) return <AdminApp />;
  return <Storefront />;
}
