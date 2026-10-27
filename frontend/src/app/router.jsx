import { useEffect, useState } from "react";
import { AppProviders } from "./providers.jsx";
import CatalogueWorkspace from "../features/catalogue/CatalogueWorkspace.jsx";
import InventoryWorkspace from "../features/inventory/InventoryWorkspace.jsx";
import { healthApi } from "../services/api.js";

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
  useEffect(() => {
    let active = true;
    healthApi.check().then(result => { if (active) setApiStatus(result?.status === "ok" ? "online" : "offline"); })
      .catch(() => { if (active) setApiStatus("offline"); });
    return () => { active = false; };
  }, []);
  const statusText = { checking: "Checking API…", online: "Backend connected", offline: "Backend unavailable" };
  const open = item => setSelected(item);
  const back = () => setSelected(null);
  const activeModule = selected?.id;
  return <main className="sb-shell">
    <header className="sb-header">
      <button className="sb-brand" type="button" onClick={back} aria-label="Back to workspaces"><span className="sb-mark">S</span><span><strong>Super Bajaar</strong><small>Commerce & ERP</small></span></button>
      <span className={`sb-status sb-status-${apiStatus}`} role="status"><i />{statusText[apiStatus]}</span>
    </header>
    <div className="sb-app-layout">
      <aside className="sb-sidebar" aria-label="Module navigation">
        <button className={`sb-nav-home ${!selected ? "is-active" : ""}`} type="button" onClick={back}>⌂ <span>All workspaces</span></button>
        {groups.map(group => <div className="sb-nav-group" key={group.title}><p>{group.title}</p>{group.items.map(item => <button key={item.id} type="button" className={`sb-nav-item ${activeModule === item.id ? "is-active" : ""}`} onClick={() => open(item)}><span>{item.label}</span></button>)}</div>)}
      </aside>
      <div className="sb-main-content">
        {selected?.id === "catalogue" ? <CatalogueWorkspace onBack={back} /> : selected?.id === "inventory" ? <InventoryWorkspace onBack={back} /> : selected ? <Workspace item={selected} onBack={back} /> : <ModuleLauncher onOpen={open} />}
      </div>
    </div>
    <footer>Super Bajaar · Separate module workspaces · Backend port 8001 · PostgreSQL port 5432</footer>
  </main>;
}
export function Router() { return <AppProviders><AppShell /></AppProviders>; }
