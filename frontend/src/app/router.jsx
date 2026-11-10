import { useEffect, useState } from "react";
import { AppProviders } from "./providers.jsx";
import CatalogueWorkspace from "../features/catalogue/CatalogueWorkspace.jsx";
import InventoryWorkspace from "../features/inventory/InventoryWorkspace.jsx";
import PricingWorkspace from "../features/pricing/PricingWorkspace.jsx";
import DashboardWorkspace from "../features/dashboard/DashboardWorkspace.jsx";
import OrdersWorkspace from "../features/orders/OrdersWorkspace.jsx";
import PaymentsWorkspace from "../features/payments/PaymentsWorkspace.jsx";
import DeliveryWorkspace from "../features/delivery/DeliveryWorkspace.jsx";
import FulfilmentWorkspace from "../features/fulfilment/FulfilmentWorkspace.jsx";
import CustomersWorkspace from "../features/customers/CustomersWorkspace.jsx";
import PurchasingWorkspace from "../features/purchasing/PurchasingWorkspace.jsx";
import POSWorkspace from "../features/pos/POSWorkspace.jsx";
import ReportsWorkspace from "../features/reports/ReportsWorkspace.jsx";
import SettingsWorkspace from "../features/settings/SettingsWorkspace.jsx";
import LoyaltyWorkspace from "../features/loyalty/LoyaltyWorkspace.jsx";
import AccountingWorkspace from "../features/accounting/AccountingWorkspace.jsx";
import HRWorkspace from "../features/hr/HRWorkspace.jsx";
import ModuleDataOverview from "../features/shared/ModuleDataOverview.jsx";
import { apiRequest, healthApi } from "../services/api.js";
import LoginScreen from "./LoginScreen.jsx";
import Storefront from "./Storefront.jsx";
import { filterNavigationGroups } from "./moduleAccess.js";
import PortalWorkspace, { PortalActivation } from "../features/portals/PortalWorkspace.jsx";
import PortalAccessWorkspace from "../features/portals/PortalAccessWorkspace.jsx";

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
    { id: "fulfilment", label: "Fulfilment", description: "Pick tasks, short picks, packages, returns and handover" },
    { id: "delivery", label: "Delivery", description: "Shipment dispatch, tracking and delivery status" },
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

function ModuleLauncher({ onOpen, groups: visibleGroups }) {
  return <section className="sb-launcher">
    <div className="sb-intro"><p className="sb-eyebrow">SUPER BAJAAR · OPERATIONS</p><h1>Workspaces</h1><p>Each business function has its own workspace. Open only the module you need.</p></div>
    {!visibleGroups.length && <p className="sb-empty">No workspaces have been assigned to this account yet. Ask your Super Admin to grant module access.</p>}
    {visibleGroups.map((group, index) => <section className="sb-module-group" key={group.title}>
      <div className="sb-group-heading"><h2>{group.title}</h2><span>{group.items.length} modules</span></div>
      <div className="sb-grid">{group.items.map((item, i) => <button className="sb-tile" key={item.id} type="button" onClick={() => onOpen(item)}>
        <span className={`sb-tile-icon sb-tone-${(index + i) % 5}`}>{item.label.slice(0,1)}</span>
        <span className="sb-tile-copy"><strong>{item.label}</strong><small>{item.description}</small></span><span className="sb-arrow" aria-hidden="true">↗</span>
      </button>)}</div>
    </section>)}
  </section>;
}

function UnavailableWorkspace({ item, onBack }) {
  return <section className="sb-workspace" role="alert">
    <button className="sb-back" type="button" onClick={onBack}>← All workspaces</button>
    <p className="sb-eyebrow">WORKSPACE ROUTING</p>
    <h1>{item?.label || "Workspace unavailable"}</h1>
    <div className="sb-notice"><strong>This workspace route is unavailable</strong><span>The module is not registered in the admin route map. No working module is represented as complete when its route is missing.</span></div>
  </section>;
}

const workspaceRoutes = {
  dashboard: ({ onOpen, permissions }) => <DashboardWorkspace onOpen={onOpen} permissions={permissions} />,
  catalogue: ({ onBack, currentUser }) => <><ModuleDataOverview moduleId="catalogue" /><CatalogueWorkspace onBack={onBack} currentUser={currentUser} /></>,
  pricing: ({ onBack }) => <PricingWorkspace onBack={onBack} />,
  orders: ({ onBack }) => <><ModuleDataOverview moduleId="orders" /><OrdersWorkspace onBack={onBack} /></>,
  payments: ({ onBack }) => <><ModuleDataOverview moduleId="payments" /><PaymentsWorkspace onBack={onBack} /></>,
  inventory: ({ onBack }) => <InventoryWorkspace onBack={onBack} />,
  purchase: ({ onBack }) => <PurchasingWorkspace onBack={onBack} />,
  fulfilment: ({ onBack }) => <><ModuleDataOverview moduleId="fulfilment" /><FulfilmentWorkspace onBack={onBack} /></>,
  delivery: ({ onBack }) => <><ModuleDataOverview moduleId="delivery" /><DeliveryWorkspace onBack={onBack} /></>,
  pos: ({ onBack }) => <POSWorkspace onBack={onBack} />,
  customers: ({ onBack }) => <><ModuleDataOverview moduleId="customers" /><CustomersWorkspace onBack={onBack} /></>,
  loyalty: ({ onBack }) => <><ModuleDataOverview moduleId="loyalty" /><LoyaltyWorkspace onBack={onBack} /></>,
  accounting: ({ onBack, currentUser }) => <AccountingWorkspace onBack={onBack} currentUser={currentUser} />,
  hr: ({ onBack, currentUser }) => <HRWorkspace onBack={onBack} currentUser={currentUser} />,
  reports: ({ onBack }) => <ReportsWorkspace onBack={onBack} />,
  settings: ({ onBack, currentUser, permissions }) => <SettingsWorkspace onBack={onBack} currentUser={currentUser} permissions={permissions} />,
  portalAccess: () => <PortalAccessWorkspace />,
};

function AppShell() {
  const [selected, setSelected] = useState(null);
  const [apiStatus, setApiStatus] = useState("checking");
  const [user, setUser] = useState(null);
  const [authChecked, setAuthChecked] = useState(false);
  const [permissions, setPermissions] = useState(null);
  const [permissionsLoaded, setPermissionsLoaded] = useState(false);
  const [permissionError, setPermissionError] = useState("");
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
  useEffect(() => {
    if (!user?.id) {
      setPermissions(null);
      setPermissionsLoaded(false);
      setPermissionError("");
      return;
    }
    let active = true;
    setPermissionsLoaded(false);
    setPermissionError("");
    apiRequest("/auth/my-permissions")
      .then(result => { if (active) setPermissions(result.permissions || {}); })
      .catch(error => { if (active) setPermissionError(error.message || "Unable to load module permissions."); })
      .finally(() => { if (active) setPermissionsLoaded(true); });
    return () => { active = false; };
  }, [user?.id]);
  const statusText = { checking: "Checking API…", online: "Backend connected", offline: "Backend unavailable" };
  const visibleGroups = filterNavigationGroups(groups, permissions || {});
  const visibleItems = visibleGroups.flatMap(group => group.items);
  const visibleIds = new Set(visibleItems.map(item => item.id));
  const open = item => { if (visibleIds.has(item.id)) setSelected(item); };
  const back = () => setSelected(null);
  const activeModule = selected?.id;
  const openById = id => { const found = visibleItems.find(item => item.id === id); if (found) setSelected(found); };
  const signOut = async () => {
    try { await apiRequest("/auth/logout", { method: "POST" }); } catch {}
    try { window.localStorage.removeItem("superbajaar.access_token"); } catch {}
    setUser(null);
    setSelected(null);
  };
  if (!authChecked) return <main className="sb-login-page"><p>Checking sign-in…</p></main>;
  if (!user) return <LoginScreen onSignedIn={setUser} />;
  if (!permissionsLoaded) return <main className="sb-login-page"><p>Loading your module access…</p></main>;
  if (permissionError) return <main className="sb-login-page"><section className="sb-login-card" role="alert"><h1>Module access unavailable</h1><p>{permissionError}</p><button className="sb-primary" type="button" onClick={() => { setPermissionsLoaded(false); apiRequest("/auth/my-permissions").then(result => { setPermissions(result.permissions || {}); setPermissionError(""); }).catch(error => setPermissionError(error.message || "Unable to load module permissions.")).finally(() => setPermissionsLoaded(true)); }}>Retry</button><button type="button" onClick={signOut}>Sign out</button></section></main>;
  // HR-only accounts (including employee self-service) should land in their
  // assigned workspace directly instead of an otherwise empty module launcher.
  if (visibleItems.length === 1 && visibleItems[0].id === "hr") return <main className="sb-shell">
    <header className="sb-header">
      <span className="sb-brand"><span className="sb-mark">S</span><span><strong>Super Bajaar</strong><small>HR & Payroll</small></span></span>
      <div className="sb-header-actions"><span className="sb-user-label">{user.full_name || user.email}</span><button className="sb-signout" type="button" onClick={signOut}>Sign out</button></div>
    </header>
    <div className="sb-main-content"><HRWorkspace currentUser={user} /></div>
  </main>;
  return <main className="sb-shell">
    <header className="sb-header">
      <button className="sb-brand" type="button" onClick={back} aria-label="Back to workspaces"><span className="sb-mark">S</span><span><strong>Super Bajaar</strong><small>Commerce & ERP</small></span></button>
      <div className="sb-header-actions">{["super_admin","admin"].includes(user.role) && <button className="sb-signout" type="button" onClick={() => setSelected({ id: "portalAccess", label: "Portals & Access" })}>Portals & Access</button>}<span className={`sb-status sb-status-${apiStatus}`} role="status"><i />{statusText[apiStatus]}</span><span className="sb-user-label">{user.full_name || user.email}</span><button className="sb-signout" type="button" onClick={signOut}>Sign out</button></div>
    </header>
    <div className="sb-app-layout">
      <aside className="sb-sidebar" aria-label="Module navigation">
        <button className={`sb-nav-home ${!selected ? "is-active" : ""}`} type="button" onClick={back}>⌂ <span>All workspaces</span></button>
        {visibleGroups.map(group => <div className="sb-nav-group" key={group.title}><p>{group.title}</p>{group.items.map(item => <button key={item.id} type="button" className={`sb-nav-item ${activeModule === item.id ? "is-active" : ""}`} onClick={() => open(item)}><span>{item.label}</span></button>)}</div>)}
      </aside>
      <div className="sb-main-content">
        {selected && (visibleIds.has(selected.id) || selected.id === "portalAccess") ? (workspaceRoutes[selected.id]
          ? workspaceRoutes[selected.id]({ item: selected, onBack: back, onOpen: openById, currentUser: user, permissions })
          : <UnavailableWorkspace item={selected} onBack={back} />)
          : <ModuleLauncher onOpen={open} groups={visibleGroups} />}
      </div>
    </div>
    <footer>Super Bajaar · Separate module workspaces · Backend port 8001 · PostgreSQL port 5432</footer>
  </main>;
}
function AdminApp() { return <AppProviders><AppShell /></AppProviders>; }

export function Router() {
  const path = window.location.pathname.replace(/\/+$/, "") || "/";
  if (path === "/admin" || path.startsWith("/admin/")) return <AdminApp />;
  if (path === "/vendor/activate") return <PortalActivation portal="vendor" />;
  if (path === "/employee/activate") return <PortalActivation portal="employee" />;
  if (path === "/vendor" || path.startsWith("/vendor/")) return <PortalWorkspace portal="vendor" />;
  if (path === "/employee" || path.startsWith("/employee/")) return <PortalWorkspace portal="employee" />;
  return <Storefront />;
}
