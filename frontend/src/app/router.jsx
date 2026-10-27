import { useEffect, useState } from "react";
import { AppProviders } from "./providers.jsx";
import CatalogueWorkspace from "../features/catalogue/CatalogueWorkspace.jsx";
import InventoryWorkspace from "../features/inventory/InventoryWorkspace.jsx";
import { healthApi } from "../services/api.js";

const workspaces = [
  { id: "dashboard", label: "Dashboard", description: "Business overview and operational alerts" },
  { id: "catalogue", label: "Catalogue", description: "Categories, attributes, products and variants" },
  { id: "inventory", label: "Inventory", description: "Stock balances, movements and adjustments" },
  { id: "pricing", label: "Pricing & Promotions", description: "Price lists, discounts and offer rules" },
  { id: "orders", label: "Orders", description: "Website and POS order lifecycle" },
  { id: "payments", label: "Payments", description: "Payment attempts, COD and refunds" },
  { id: "delivery", label: "Delivery", description: "PIN serviceability, dispatch and tracking" },
  { id: "customers", label: "Customers / CRM", description: "Customer profiles, enquiries and history" },
  { id: "pos", label: "POS & Stores", description: "Walk-in sales, receipts and shift closing" },
  { id: "purchase", label: "Purchase", description: "Suppliers, purchase orders and goods receipt" },
  { id: "accounting", label: "Accounting & Tax", description: "Ledgers, journals, GST and financial reports" },
  { id: "hr", label: "HR & Payroll", description: "Employees, attendance, salary and payslips" },
  { id: "loyalty", label: "Loyalty & Rewards", description: "Points, rewards and customer benefits" },
  { id: "reports", label: "Reports", description: "Sales, stock, margin and operational reporting" },
  { id: "settings", label: "Settings & Access", description: "Users, roles, permissions and configuration" },
];

function WorkspaceLauncher({ onOpen }) {
  return <>
    <section className="sb-intro">
      <p className="sb-eyebrow">OPERATIONS PLATFORM</p>
      <h1>Choose your workspace</h1>
      <p>Choose a module to enter its workspace. These are navigation entry points; each module must be connected to real APIs and tests before it is considered complete.</p>
    </section>
    <section className="sb-grid" aria-label="Application workspaces">
      {workspaces.map((item, index) => <button className="sb-tile" key={item.id} type="button" onClick={() => onOpen(item)}>
        <span className={`sb-tile-icon sb-tone-${index % 5}`}>{item.label.slice(0, 1)}</span>
        <span className="sb-tile-copy"><strong>{item.label}</strong><small>{item.description}</small></span>
        <span className="sb-arrow" aria-hidden="true">↗</span>
      </button>)}
    </section>
  </>;
}

function Workspace({ item, onBack }) {
  return <section className="sb-workspace">
    <button className="sb-back" type="button" onClick={onBack}>← All workspaces</button>
    <p className="sb-eyebrow">WORKSPACE</p>
    <h1>{item.label}</h1>
    <p>{item.description}</p>
    <div className="sb-notice"><strong>Workspace foundation created</strong><span>This module is not marked complete yet. Its screens, permission checks, database operations and API tests must be implemented before live use.</span></div>
  </section>;
}

function AppShell() {
  const clearSelection = () => setSelected(null);
  const [selected, setSelected] = useState(null);
  const [apiStatus, setApiStatus] = useState("checking");

  useEffect(() => {
    let active = true;
    const check = async () => {
      try {
        const result = await healthApi.check();
        if (active) setApiStatus(result?.status === "ok" ? "online" : "offline");
      } catch {
        if (active) setApiStatus("offline");
      }
    };
    check();
    return () => { active = false; };
  }, []);

  const labels = {
    checking: "Checking API…",
    online: "Backend connected",
    offline: "Backend unavailable",
  };

  return <main className="sb-shell">
    <header className="sb-header">
      <div><span className="sb-mark">S</span><div><strong>Super Bajaar</strong><small>Commerce & ERP</small></div></div>
      <span className={`sb-status sb-status-${apiStatus}`} role="status"><i />{labels[apiStatus]}</span>
    </header>
    {selected && selected.id === "catalogue" ? <CatalogueWorkspace onBack={clearSelection} /> : selected ? <Workspace item={selected} onBack={clearSelection} /> : <WorkspaceLauncher onOpen={setSelected} />}
    <footer>Clean-start interface scaffold · Backend port 8001 · PostgreSQL port 5432</footer>
  </main>;
}

export function Router() {
  return <AppProviders><AppShell /></AppProviders>;
}
