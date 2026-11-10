import { useEffect, useRef, useState } from "react";
import { apiRequest } from "../../services/api.js";

const definitions = {
  catalogue: [
    { key: "products", label: "Products", path: "/catalogue/products?status=all&limit=500", value: r => r.total ?? (r.items || []).length, note: "Catalogue records" },
    { key: "variants", label: "Variants", path: "/catalogue/variants?limit=500", value: r => r.total ?? (r.items || []).length, note: "Active SKU variants" },
    { key: "categories", label: "Categories", path: "/catalogue/categories?limit=500", value: r => r.total ?? (r.items || []).length, note: "Category records" },
  ],
  orders: [
    { key: "orders", label: "Orders loaded", path: "/orders?limit=500", value: r => r.total ?? (r.items || []).length, note: "Latest 500 records at most", breakdown: "status" },
  ],
  payments: [
    { key: "payments", label: "Captured amount", path: "/payments/reconciliation", value: r => r.captured_amount_recorded ?? 0, format: "money", note: "Application-recorded captured payments" },
    { key: "pending", label: "Pending payments", path: "/payments/reconciliation", value: r => r.payments_by_status?.pending?.count ?? 0, note: "Awaiting confirmation" },
    { key: "reconciled", label: "Gateway reconciliation", path: "/payments/reconciliation", value: r => r.gateway_or_bank_reconciled ? "Yes" : "No", note: "Provider/bank settlement verification" },
  ],
  delivery: [
    { key: "shipments", label: "Shipments loaded", path: "/delivery/shipments?limit=200", value: r => r.total ?? (r.items || []).length, note: "Latest 200 records at most", breakdown: "status" },
  ],
  fulfilment: [
    { key: "picks", label: "Pick tasks", path: "/fulfilment/pick-tasks?limit=200", value: r => r.total ?? (r.items || []).length, note: "Latest 200 records at most", breakdown: "status" },
    { key: "returns", label: "Returns", path: "/fulfilment/returns?limit=100", value: r => r.total ?? (r.items || []).length, note: "Latest 100 records at most" },
  ],
  customers: [
    { key: "customers", label: "Customers", path: "/customers?limit=500", value: r => r.total ?? (r.items || []).length, note: "Latest 500 records at most" },
    { key: "cases", label: "Support cases", path: "/customers/support-cases?limit=500", value: r => r.total ?? (r.items || []).length, note: "Customer support records", breakdown: "status" },
  ],
  loyalty: [
    { key: "accounts", label: "Loyalty accounts", path: "/loyalty/admin/accounts?limit=200", value: r => r.total ?? (r.items || []).length, note: "Customer reward accounts" },
    { key: "rules", label: "Programme rules", path: "/loyalty/admin/rules", value: r => Array.isArray(r) ? r.length : (r.items || []).length, note: "Configured earning and redemption rules" },
  ],
};

const money = value => new Intl.NumberFormat("en-IN", { style: "currency", currency: "INR", maximumFractionDigits: 0 }).format(Number(value || 0));
const display = (value, format) => format === "money" ? money(value) : typeof value === "number" ? value.toLocaleString("en-IN") : String(value);

export default function ModuleDataOverview({ moduleId }) {
  const [results, setResults] = useState({});
  const [errors, setErrors] = useState({});
  const [loading, setLoading] = useState(false);
  const [refreshedAt, setRefreshedAt] = useState(null);
  const requestSequence = useRef(0);
  const sources = definitions[moduleId] || [];

  async function refresh() {
    const sequence = ++requestSequence.current;
    setLoading(true);
    const paths = [...new Set(sources.map(source => source.path))];
    const responses = await Promise.allSettled(paths.map(path => apiRequest(path)));
    const byPath = Object.fromEntries(paths.map((path, index) => [path, responses[index]]));
    const next = {}, failed = {};
    sources.forEach(source => {
      const response = byPath[source.path];
      if (response.status === "fulfilled") next[source.key] = response.value;
      else failed[source.key] = response.reason?.message || "Source unavailable";
    });
    if (sequence !== requestSequence.current) return;
    setResults(next);
    setErrors(failed);
    setRefreshedAt(new Date().toLocaleString("en-IN"));
    setLoading(false);
  }

  useEffect(() => {
    setResults({});
    setErrors({});
    refresh();
    return () => { requestSequence.current += 1; };
  }, [moduleId]);

  if (!sources.length) return null;
  const chartSource = sources.find(source => source.breakdown && Array.isArray(results[source.key]?.items));
  const chartRows = chartSource ? results[chartSource.key].items : [];
  const paymentBreakdown = moduleId === "payments" ? results.payments?.payments_by_status || {} : {};
  const chartGroups = chartSource
    ? Object.entries(chartRows.reduce((groups, row) => {
        const value = String(row[chartSource.breakdown] || "Unknown").replaceAll("_", " ");
        groups[value] = (groups[value] || 0) + 1;
        return groups;
      }, {})).sort((a, b) => b[1] - a[1]).slice(0, 6)
    : Object.entries(paymentBreakdown).map(([status, value]) => [status.replaceAll("_", " "), Number(value?.count || 0)]).sort((a, b) => b[1] - a[1]);
  const chartTitle = chartSource ? `${chartSource.label} by ${chartSource.breakdown}` : moduleId === "payments" ? "Payments by status" : "";
  const chartMax = Math.max(1, ...chartGroups.map(([, value]) => value));
  return <section className="sb-data-overview" aria-label={`${moduleId} data overview`}>
    <div className="sb-data-heading">
      <div><strong>Overview</strong><small>{loading ? "Refreshing live sources…" : `Live API snapshot${refreshedAt ? " · " + refreshedAt : ""}`}</small></div>
      <button type="button" onClick={refresh} disabled={loading}>{loading ? "Refreshing…" : "Refresh overview"}</button>
    </div>
    <div className="sb-report-grid">
      {sources.map(source => <article className="sb-report-card" key={source.key}>
        <small>{source.label}</small>
        <strong>{errors[source.key] ? "Unavailable" : results[source.key] ? display(source.value(results[source.key]), source.format) : loading ? "—" : "No data"}</strong>
        <span>{errors[source.key] ? errors[source.key] : source.note}</span>
      </article>)}
    </div>
    {chartTitle && (chartSource ? !errors[chartSource.key] : !errors.payments) && <div className="sb-overview-chart">
      <div><strong>{chartTitle}</strong><small>Distribution of the loaded records</small></div>
      {chartGroups.length ? chartGroups.map(([label, value]) => <div className="sb-overview-bar" key={label}><span>{label}</span><div><i style={{ width: `${Math.max(2, value / chartMax * 100)}%` }} /></div><strong>{value.toLocaleString("en-IN")}</strong></div>) : <p>No breakdown data is available for this snapshot.</p>}
    </div>}
  </section>;
}
