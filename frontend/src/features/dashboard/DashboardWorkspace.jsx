import { useCallback, useEffect, useMemo, useState } from "react";
import { apiRequest } from "../../services/api.js";
import { dashboardMetrics } from "./dashboardMetrics.js";
import { canReadPermission } from "../../app/moduleAccess.js";
import MonthlyTrendChart from "./MonthlyTrendChart.jsx";
import ReportActions from "../reports/ReportActions.jsx";

const money = value => new Intl.NumberFormat("en-IN", { style: "currency", currency: "INR", maximumFractionDigits: 0 }).format(Number(value || 0));
const count = value => Number(value || 0).toLocaleString("en-IN");
const rows = value => Array.isArray(value?.items) ? value.items : Array.isArray(value) ? value : [];
const dateKey = value => value ? String(value).slice(0, 10) : "";
const today = () => { const d = new Date(); return new Date(d.getTime() - d.getTimezoneOffset() * 60000).toISOString().slice(0, 10); };
const firstDay = () => today().slice(0, 8) + "01";
const within = (value, from, to) => dateKey(value) >= from && dateKey(value) <= to;
const label = value => String(value || "unknown").replaceAll("_", " ").replace(/\b\w/g, c => c.toUpperCase());

function Metric({ title, value, note, tone = "purple" }) {
  return <article className="an-metric"><span className={"an-metric-mark " + tone} /><small>{title}</small><strong>{value}</strong><span className="an-metric-note">{note}</span></article>;
}
function Bars({ items, value, name, format = count }) {
  const max = Math.max(1, ...items.map(item => Number(value(item) || 0)));
  if (!items.length) return <p className="an-empty">No records for this period.</p>;
  return <div className="an-bars">{items.map((item, i) => <div className="an-bar-row" key={name(item) + i}><span>{name(item)}</span><div><i style={{ width: Math.max(2, Number(value(item) || 0) / max * 100) + "%" }} /></div><strong>{format(value(item))}</strong></div>)}</div>;
}
function Panel({ title, note, children, action }) {
  return <section className="an-panel"><header><div><h2>{title}</h2>{note && <p>{note}</p>}</div>{action}</header>{children}</section>;
}

export default function DashboardWorkspace({ onOpen, permissions = {} }) {
  const [tab, setTab] = useState("overview");
  const [period, setPeriod] = useState("month");
  const [data, setData] = useState({});
  const [errors, setErrors] = useState({});
  const [loading, setLoading] = useState(true);
  const to = today();
  const from = period === "7d" ? new Date(Date.now() - 6 * 86400000).toISOString().slice(0, 10) : period === "30d" ? new Date(Date.now() - 29 * 86400000).toISOString().slice(0, 10) : period === "fy" ? (Number(to.slice(5, 7)) >= 4 ? to.slice(0, 4) : String(Number(to.slice(0, 4)) - 1)) + "-04-01" : firstDay();

  const refresh = useCallback(async () => {
    setLoading(true);
    const requests = {
      products: () => apiRequest("/catalogue/products?status=all&limit=500"),
      variants: () => apiRequest("/catalogue/variants?limit=500"),
      balances: () => apiRequest("/inventory/balances?limit=500"),
      inventoryOverview: () => apiRequest("/inventory/overview"),
      reportSummary: () => apiRequest("/reports/overview?from_date=" + from + "&to_date=" + to),
      orders: () => apiRequest("/orders?limit=500"),
      payments: () => apiRequest("/payments?limit=500"),
      customers: () => apiRequest("/customers?limit=500"),
      cases: () => apiRequest("/customers/support-cases?limit=500"),
      employees: () => apiRequest("/hr/employees"),
      attendance: () => apiRequest("/hr/attendance/register?start_date=" + from + "&end_date=" + to),
      payroll: () => apiRequest("/hr/payroll/runs"),
      expenses: () => apiRequest("/hr/expenses"),
      finance: () => apiRequest("/accounting/reports/summary?from_date=" + from + "&to_date=" + to),
      purchases: () => apiRequest("/purchasing/orders?limit=500"),
      pos: () => apiRequest("/pos/summary"),
      pricing: () => apiRequest("/pricing/overview"),
      shipments: () => apiRequest("/delivery/shipments?limit=200"),
      pickTasks: () => apiRequest("/fulfilment/pick-tasks?limit=200"),
      fulfilmentReturns: () => apiRequest("/fulfilment/returns?limit=100"),
      loyaltyAccounts: () => apiRequest("/loyalty/admin/accounts?limit=200"),
      loyaltyRules: () => apiRequest("/loyalty/admin/rules"),
    };
    const requestModules = {
      products: "catalogue", variants: "catalogue",
      balances: "inventory", inventoryOverview: "inventory",
      reportSummary: "dashboard", orders: "orders", payments: "payments",
      customers: "crm", cases: "crm",
      employees: "hr_payroll", attendance: "hr_payroll", payroll: "hr_payroll", expenses: "hr_payroll",
      finance: "accounting", purchases: "purchasing", pos: "pos", pricing: "pricing",
      shipments: "delivery", pickTasks: "fulfillment", fulfilmentReturns: "fulfillment",
      loyaltyAccounts: "loyalty", loyaltyRules: "loyalty",
    };
    const entries = Object.entries(requests).filter(([key]) => canReadPermission(requestModules[key], permissions));
    const denied = Object.fromEntries(Object.entries(requestModules)
      .filter(([, moduleKey]) => !canReadPermission(moduleKey, permissions))
      .map(([key]) => [key, "Read permission not granted"]));
    const results = await Promise.allSettled(entries.map(([, request]) => request()));
    const next = {}; const failed = { ...denied };
    results.forEach((result, index) => {
      const key = entries[index][0];
      if (result.status === "fulfilled") next[key] = ["finance", "pos", "pricing", "inventoryOverview", "reportSummary"].includes(key) ? result.value : rows(result.value);
      else failed[key] = result.reason?.message || "Unable to load";
    });
    setData(next); setErrors(failed); setLoading(false);
  }, [from, to]);

  useEffect(() => { refresh(); }, [refresh]);

  const orders = useMemo(() => (data.orders || []).filter(row => within(row.created_at || row.placed_at, from, to)), [data.orders, from, to]);
  const aggregate = dashboardMetrics(data.reportSummary, data.inventoryOverview);
  const stockUnits = aggregate.stockOnHand;
  const lowStock = aggregate.lowStockRows;
  const outStock = aggregate.outOfStockRows;
  const customerCount = (data.customers || []).length;
  const finance = data.finance || {};
  const monthly = finance.monthly || [];
  const statuses = aggregate.orderStatuses?.map(row => ({ status: label(row.status), total: row.total })) || [];

  const sections = [
    ["overview", "Overview"], ["sales", "Sales"], ["inventory", "Inventory"],
    ["customers", "Customers"], ["finance", "Finance"], ["people", "HR & People"], ["modules", "All modules"],
  ];
  const unavailable = Object.keys(errors);
  const moduleCards = [
    ["catalogue", "Catalogue", ["products", "variants"]],
    ["inventory", "Inventory", ["balances", "inventoryOverview"]],
    ["purchase", "Purchasing", ["purchases"]],
    ["pos", "POS & Stores", ["pos"]],
    ["customers", "CRM & Customers", ["customers", "cases"]],
    ["orders", "Orders", ["orders", "reportSummary"]],
    ["payments", "Payments", ["payments", "reportSummary"]],
    ["fulfilment", "Fulfilment", ["pickTasks", "fulfilmentReturns"]],
    ["delivery", "Delivery", ["shipments"]],
    ["pricing", "Pricing", ["pricing"]],
    ["loyalty", "Loyalty", ["loyaltyAccounts", "loyaltyRules"]],
    ["hr", "HR & Payroll", ["employees", "attendance", "payroll"]],
    ["accounting", "Accounting", ["finance"]],
    ["dashboard", "Master Dashboard", ["orders", "balances", "customers", "finance", "employees"]],
    ["reports", "Reports", ["orders", "payments", "balances", "products"]],
  ].map(([id, name, keys]) => {
    const failed = keys.filter(key => errors[key]);
    const loaded = keys.filter(key => data[key] !== undefined);
    return { id, name, failed, loaded, keys, state: failed.length ? "Needs attention" : loaded.length === keys.length ? "Data connected" : "Loading" };
  });
  const metricValue = (key, value, format = count) => loading ? "—" : errors[key] ? "Unavailable" : format(value);
  const metricNote = key => errors[key] ? "Source unavailable" : "Live API data";
  const go = id => onOpen?.(id);
  const dashboardExportRows = [["Section", "Metric", "Value"], ["Period", "From", from + " to " + to], ["Orders", "Order count", aggregate.orderCount], ["Orders", "Active order value (INR)", aggregate.activeOrderValue], ["Payments", "Captured amount (INR)", aggregate.capturedAmount], ["Inventory", "Stock on hand", stockUnits], ["Customers", "Customer records", customerCount], ["Finance", "Net profit/loss (INR)", finance.net_profit], ...monthly.flatMap(item => [["Finance", item.month + " income (INR)", item.income], ["Finance", item.month + " expenses (INR)", item.expense]])];

  return <section className="sb-workspace sb-dashboard an-dashboard">
    <div className="an-heading"><div><p className="sb-eyebrow">SUPER BAJAAR · MANAGEMENT INTELLIGENCE</p><h1>Business analytics</h1><p>One view of trading, stock, customers, finance and workforce performance.</p></div><button className="an-refresh" type="button" onClick={refresh} disabled={loading}>{loading ? "Updating…" : "↻ Refresh data"}</button></div>
    <div className="an-controls"><nav aria-label="Analytics sections">{sections.map(([key, text]) => <button type="button" key={key} className={tab === key ? "active" : ""} onClick={() => setTab(key)}>{text}</button>)}</nav><label>Period<select value={period} onChange={e => setPeriod(e.target.value)}><option value="month">This month</option><option value="7d">Last 7 days</option><option value="30d">Last 30 days</option><option value="fy">Current financial year</option></select></label></div>
    {unavailable.length > 0 && <div className="sb-alert an-alert" role="status"><strong>{unavailable.length} data source(s) need attention.</strong><span>{unavailable.map(key => key.replaceAll("_", " ")).join(" · ")} unavailable. Their figures are shown as unavailable, not zero.</span></div>}
    {tab === "overview" && <>
      <div className="an-section-title"><div><h2>Business at a glance</h2><p>{from} to {to}</p></div></div>
      <div className="an-metrics">
        <Metric title="Orders" value={metricValue("reportSummary", aggregate.orderCount)} note="Full-period PostgreSQL aggregate" />
        <Metric title="Order value" value={metricValue("reportSummary", aggregate.activeOrderValue, money)} note="Non-cancelled orders; not recognised revenue" tone="orange" />
        <Metric title="Captured payments" value={metricValue("reportSummary", aggregate.capturedAmount, money)} note="Provider-captured payments in the selected period" tone="green" />
        <Metric title="Stock on hand" value={metricValue("inventoryOverview", stockUnits)} note="Full-dataset inventory aggregate" tone="blue" />
        <Metric title="Customers" value={metricValue("customers", customerCount)} note="Customer records loaded" />
        <Metric title="Net profit / loss" value={errors.finance ? "Unavailable" : loading ? "—" : money(finance.net_profit)} note={errors.finance ? "Accounting summary unavailable" : "Posted accounting records"} tone="green" />
      </div>
      <div className="an-grid">
        <Panel title="Order status" note="Full-period database distribution">{errors.reportSummary ? <p className="an-empty">Order status aggregate unavailable: {errors.reportSummary}</p> : <Bars items={statuses} value={x => x.total} name={x => x.status} />}</Panel>
        <Panel title="Finance snapshot" note="From the accounting ledger"><div className="an-finance-pairs"><div><small>Income</small><strong>{errors.finance ? "Unavailable" : loading ? "—" : money(finance.income)}</strong></div><div><small>Expenses</small><strong>{errors.finance ? "Unavailable" : loading ? "—" : money(finance.expenses)}</strong></div><div><small>Gross profit</small><strong>{errors.finance ? "Unavailable" : loading ? "—" : money(finance.gross_profit)}</strong></div><div><small>Receivables</small><strong>{errors.finance ? "Unavailable" : loading ? "—" : money(finance.receivables)}</strong></div></div>{errors.finance ? <p className="an-empty">Financial trend unavailable: {errors.finance}</p> : <MonthlyTrendChart monthly={monthly} />}<button className="an-link" type="button" onClick={() => go("accounting")}>Open accounting →</button></Panel>
      </div>
      <div className="an-shortcuts">{[["orders","Orders"],["inventory","Inventory"],["customers","Customers & CRM"],["accounting","Accounting"],["hr","HR & Payroll"]].map(([id,name]) => <button type="button" key={id} onClick={() => go(id)}>{name}<span>↗</span></button>)}</div>
    </>}
    {tab === "modules" && <>
      <div className="an-section-title"><div><h2>Department and module health</h2><p>Live connectivity snapshot for all 14 business modules plus Reports. Connectivity does not certify every workflow; use each module's own tests and readiness review.</p></div></div>
      <div className="an-module-grid">{moduleCards.map(module => <button type="button" className="an-module-card" key={module.id} onClick={() => go(module.id)}>
        <span className={"an-module-state " + (module.state === "Data connected" ? "is-live" : module.state === "Needs attention" ? "is-error" : "")}>{module.state}</span>
        <strong>{module.name}</strong>
        <small>{module.failed.length ? module.failed.length + " source(s) unavailable: " + module.failed.join(", ") : module.loaded.length + " of " + module.keys.length + " data sources connected"}</small>
        <span className="an-module-open">Open workspace →</span>
      </button>)}</div>
    </>}
    {tab === "sales" && <><div className="an-section-title"><div><h2>Sales performance</h2><p>Order and payment activity for the selected period.</p></div></div><div className="an-metrics"><Metric title="Orders placed" value={metricValue("reportSummary", aggregate.orderCount)} note="Full-period PostgreSQL aggregate" /><Metric title="Order value" value={metricValue("reportSummary", aggregate.activeOrderValue, money)} note="Excludes drafts and cancellations" tone="orange" /><Metric title="Successful payments" value={metricValue("reportSummary", aggregate.capturedCount)} note="Provider-captured payments" tone="green" /><Metric title="Amount captured" value={metricValue("reportSummary", aggregate.capturedAmount, money)} note="Provider-captured payment amount" tone="blue" /></div><div className="an-grid"><Panel title="Orders by status" note="Full-period database distribution">{errors.reportSummary ? <p className="an-empty">Order status aggregate unavailable: {errors.reportSummary}</p> : <Bars items={statuses} value={x=>x.total} name={x=>x.status}/>}</Panel><Panel title="Recent orders" note="Latest 8 in the selected period"><div className="an-table-wrap"><table><thead><tr><th>Order</th><th>Status</th><th>Value</th></tr></thead><tbody>{orders.slice().sort((a,b)=>String(b.created_at).localeCompare(String(a.created_at))).slice(0,8).map(row=><tr key={row.id}><td>{row.order_number || "Order #"+row.id}</td><td>{label(row.status)}</td><td>{money(row.total)}</td></tr>)}</tbody></table></div>{!orders.length && !errors.orders && <p className="an-empty">No orders in this period.</p>}</Panel></div></>}
    {tab === "inventory" && <><div className="an-section-title"><div><h2>Inventory health</h2><p>Stock balances across configured locations.</p></div><button className="an-link" type="button" onClick={()=>go("inventory")}>Manage inventory →</button></div><div className="an-metrics"><Metric title="Units on hand" value={metricValue("inventoryOverview",stockUnits)} note="Full-dataset inventory aggregate" /><Metric title="Low-stock balances" value={metricValue("inventoryOverview",lowStock)} note="More than 0 and up to 5 units" tone="orange" /><Metric title="Out-of-stock balances" value={metricValue("inventoryOverview",outStock)} note="Zero or negative balance" tone="red" /><Metric title="Active products" value={metricValue("reportSummary",aggregate.activeProducts)} note="Full catalogue aggregate" tone="blue" /></div><Panel title="Stock by location" note="Full-dataset database aggregates">{errors.inventoryOverview ? <p className="an-empty">Inventory aggregate unavailable: {errors.inventoryOverview}</p> : <Bars items={(aggregate.stockByLocation || []).map(row=>({name:row.location_name || ("Location " + row.location_id),total:Number(row.on_hand || 0)})).slice(0,8)} value={x=>x.total} name={x=>x.name}/>}</Panel></>}
    {tab === "customers" && <><div className="an-section-title"><div><h2>Customer intelligence</h2><p>Customer base and service workload.</p></div><button className="an-link" type="button" onClick={()=>go("customers")}>Open CRM →</button></div><div className="an-metrics"><Metric title="Total customers" value={metricValue("customers",customerCount)} note={metricNote("customers")} /><Metric title="Active customers" value={metricValue("customers",(data.customers||[]).filter(x=>x.is_active!==false).length)} note="Not deactivated" tone="green" /><Metric title="Support cases" value={metricValue("cases",(data.cases||[]).length)} note={metricNote("cases")} tone="blue" /><Metric title="Open cases" value={metricValue("cases",(data.cases||[]).filter(x=>!["resolved","closed"].includes(x.status)).length)} note="Awaiting resolution" tone="orange" /></div><Panel title="Support case status"><Bars items={Object.entries((data.cases||[]).reduce((acc,row)=>{const key=label(row.status);acc[key]=(acc[key]||0)+1;return acc;},{})).map(([status,total])=>({status,total}))} value={x=>x.total} name={x=>x.status}/></Panel></>}
    {tab === "finance" && <><div className="an-section-title"><div><h2>Financial performance</h2><p>Accounting ledger summary · {from} to {to}</p></div><button className="an-link" type="button" onClick={()=>go("accounting")}>Open accounting →</button></div>{errors.finance ? <div className="sb-alert">Accounting summary unavailable: {errors.finance}</div> : <><div className="an-metrics"><Metric title="Income" value={metricValue("finance",finance.income,money)} note="Posted ledger income" tone="green" /><Metric title="Expenses" value={metricValue("finance",finance.expenses,money)} note="Posted ledger expenses" tone="orange" /><Metric title="Net profit / loss" value={metricValue("finance",finance.net_profit,money)} note="Accounting summary" /><Metric title="GST payable (net)" value={metricValue("finance",finance.gst_payable,money)} note="Ledger summary" tone="blue" /><Metric title="Receivables" value={metricValue("finance",finance.receivables,money)} note="Customers owe" /><Metric title="Payables" value={metricValue("finance",finance.payables,money)} note="Owed to suppliers" tone="orange" /></div><Panel title="Monthly income vs expenses" note="Posted accounting figures"><MonthlyTrendChart monthly={monthly} /><div className="an-table-wrap"><table><thead><tr><th>Month</th><th>Income</th><th>Expenses</th></tr></thead><tbody>{monthly.map(item=><tr key={item.month}><td>{item.month}</td><td>{money(item.income)}</td><td>{money(item.expense)}</td></tr>)}</tbody></table></div></Panel></>}</>}
    {tab === "people" && <><div className="an-section-title"><div><h2>People & workforce</h2><p>Workforce records, attendance and payroll activity.</p></div><button className="an-link" type="button" onClick={()=>go("hr")}>Open HR & Payroll →</button></div><div className="an-metrics"><Metric title="Employees" value={metricValue("employees",(data.employees||[]).length)} note={metricNote("employees")} /><Metric title="Attendance records" value={metricValue("attendance",(data.attendance||[]).length)} note="Selected date range" tone="blue" /><Metric title="Payroll runs" value={metricValue("payroll",(data.payroll||[]).length)} note="Payroll history" tone="green" /><Metric title="Pending expenses" value={metricValue("expenses",(data.expenses||[]).filter(x=>x.status==="pending").length)} note={metricNote("expenses")} tone="orange" /></div><Panel title="Payroll runs" note="Latest payroll periods"><div className="an-table-wrap"><table><thead><tr><th>Period</th><th>Status</th><th>Employees</th></tr></thead><tbody>{(data.payroll||[]).slice(0,8).map(row=><tr key={row.id}><td>{row.period_start || row.payroll_month || "—"}</td><td>{label(row.status)}</td><td>{row.employee_count ?? "—"}</td></tr>)}</tbody></table></div>{!data.payroll?.length && !errors.payroll && <p className="an-empty">No payroll runs found.</p>}</Panel></>}
  </section>;
}
