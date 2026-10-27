import { AppProviders } from "./providers.jsx";

const workspaces = [
  { id: "dashboard", label: "Dashboard" },
  { id: "catalogue", label: "Catalogue" },
  { id: "inventory", label: "Inventory" },
  { id: "pricing", label: "Pricing & Promotions" },
  { id: "orders", label: "Orders" },
  { id: "payments", label: "Payments" },
  { id: "delivery", label: "Delivery" },
  { id: "customers", label: "Customers / CRM" },
  { id: "pos", label: "POS & Stores" },
  { id: "purchase", label: "Purchase" },
  { id: "accounting", label: "Accounting & Tax" },
  { id: "hr", label: "HR & Payroll" },
  { id: "loyalty", label: "Loyalty & Rewards" },
  { id: "reports", label: "Reports" },
  { id: "settings", label: "Settings & Access" },
];

export function Router() {
  return <AppProviders>
    <main className="sb-shell">
      <header className="sb-header">
        <div><span className="sb-mark">S</span><div><strong>Super Bajaar</strong><small>Commerce & ERP</small></div></div>
        <span className="sb-status"><i /> Workspace launcher</span>
      </header>
      <section className="sb-intro">
        <p className="sb-eyebrow">OPERATIONS PLATFORM</p>
        <h1>Choose your workspace</h1>
        <p>Each module will have its own screens, permissions, APIs and connected business records.</p>
      </section>
      <section className="sb-grid" aria-label="Application workspaces">
        {workspaces.map((item, index) => <button className="sb-tile" key={item.id} type="button" onClick={() => window.dispatchEvent(new CustomEvent("sb-workspace-select", { detail: item.id }))}>
          <span className={`sb-tile-icon sb-tone-${index % 5}`}>{item.label.slice(0, 1)}</span>
          <span className="sb-tile-copy"><strong>{item.label}</strong><small>Workspace scaffold</small></span>
          <span className="sb-arrow" aria-hidden="true">↗</span>
        </button>)}
      </section>
      <footer>Clean-start interface scaffold · No module is opened automatically</footer>
    </main>
  </AppProviders>;
}
