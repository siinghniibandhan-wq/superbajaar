import { apiRequest } from "../../services/api.js";

// Thin wrappers around /api/accounting/*. The backend owns every calculation
// (GST split, balances, numbering); the UI only formats and submits.
function qs(params = {}) {
  const search = new URLSearchParams();
  Object.entries(params).forEach(([key, value]) => {
    if (value !== undefined && value !== null && value !== "") search.set(key, value);
  });
  const text = search.toString();
  return text ? `?${text}` : "";
}

const json = (method, body) => ({ method, body: JSON.stringify(body) });

export const accountingApi = {
  settings: () => apiRequest("/accounting/settings"),
  saveSettings: (body) => apiRequest("/accounting/settings", json("PUT", body)),
  accounts: (params) => apiRequest(`/accounting/accounts${qs(params)}`),
  createAccount: (body) => apiRequest("/accounting/accounts", json("POST", body)),
  updateAccount: (id, body) => apiRequest(`/accounting/accounts/${id}`, json("PATCH", body)),
  vouchers: (params) => apiRequest(`/accounting/vouchers${qs(params)}`),
  voucher: (id) => apiRequest(`/accounting/vouchers/${id}`),
  createVoucher: (body) => apiRequest("/accounting/vouchers", json("POST", body)),
  createInvoice: (body) => apiRequest("/accounting/invoices", json("POST", body)),
  reverse: (id, body) => apiRequest(`/accounting/vouchers/${id}/reverse`, json("POST", body)),
  summary: (params) => apiRequest(`/accounting/reports/summary${qs(params)}`),
  trialBalance: (params) => apiRequest(`/accounting/reports/trial-balance${qs(params)}`),
  profitLoss: (params) => apiRequest(`/accounting/reports/profit-loss${qs(params)}`),
  balanceSheet: (params) => apiRequest(`/accounting/reports/balance-sheet${qs(params)}`),
  ledger: (id, params) => apiRequest(`/accounting/reports/ledger/${id}${qs(params)}`),
  dayBook: (params) => apiRequest(`/accounting/reports/day-book${qs(params)}`),
  gst: (params) => apiRequest(`/accounting/reports/gst-summary${qs(params)}`),
  parties: (params) => apiRequest(`/accounting/reports/parties${qs(params)}`),
  bank: (params) => apiRequest(`/accounting/bank-reconciliation${qs(params)}`),
  reconcile: (lineId, body) => apiRequest(`/accounting/lines/${lineId}/reconcile`, json("PATCH", body)),
  syncStatus: () => apiRequest("/accounting/sync/status"),
  sync: () => apiRequest("/accounting/sync", { method: "POST" }),
};

export const VOUCHER_TYPES = {
  sales: { label: "Sales invoice", short: "Sale", tone: "green" },
  purchase: { label: "Purchase bill", short: "Purchase", tone: "orange" },
  expense: { label: "Expense", short: "Expense", tone: "red" },
  receipt: { label: "Receipt", short: "Receipt", tone: "green" },
  payment: { label: "Payment", short: "Payment", tone: "red" },
  contra: { label: "Contra (cash ↔ bank)", short: "Contra", tone: "blue" },
  journal: { label: "Journal", short: "Journal", tone: "purple" },
  credit_note: { label: "Credit note (sales return)", short: "Credit note", tone: "orange" },
  debit_note: { label: "Debit note (purchase return)", short: "Debit note", tone: "blue" },
  opening: { label: "Opening balances", short: "Opening", tone: "purple" },
  reversal: { label: "Reversal", short: "Reversal", tone: "grey" },
};

export const ACCOUNT_TYPES = [
  { key: "asset", label: "Assets" },
  { key: "liability", label: "Liabilities" },
  { key: "equity", label: "Equity" },
  { key: "income", label: "Income" },
  { key: "expense", label: "Expenses" },
];

export const GST_RATES = ["0", "0.1", "0.25", "1", "1.5", "3", "5", "6", "7.5", "12", "18", "28", "40"];

export const num = (value) => {
  const n = Number(value);
  return Number.isFinite(n) ? n : 0;
};

export function money(value, { sign = false } = {}) {
  const n = num(value);
  const text = "₹" + Math.abs(n).toLocaleString("en-IN", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
  if (n < 0) return "−" + text;
  return sign && n > 0 ? "+" + text : text;
}

export function compactMoney(value) {
  const n = num(value);
  const abs = Math.abs(n);
  const prefix = n < 0 ? "−₹" : "₹";
  if (abs >= 1e7) return `${prefix}${(abs / 1e7).toFixed(2)} Cr`;
  if (abs >= 1e5) return `${prefix}${(abs / 1e5).toFixed(2)} L`;
  if (abs >= 1e3) return `${prefix}${(abs / 1e3).toFixed(1)}K`;
  return `${prefix}${abs.toFixed(0)}`;
}

/** Ledger balance with Dr/Cr suffix (debit minus credit convention). */
export function drCr(value) {
  const n = num(value);
  if (n === 0) return "₹0.00";
  return `${money(Math.abs(n))} ${n > 0 ? "Dr" : "Cr"}`;
}

export function formatDate(value) {
  if (!value) return "—";
  const [y, m, d] = String(value).slice(0, 10).split("-").map(Number);
  if (!y) return String(value);
  return new Date(y, m - 1, d).toLocaleDateString("en-IN", { day: "2-digit", month: "short", year: "numeric" });
}

export function isoToday() {
  const now = new Date();
  const offset = now.getTimezoneOffset() * 60000;
  return new Date(now.getTime() - offset).toISOString().slice(0, 10);
}

/** Indian fiscal year (1 April – 31 March) containing the given ISO date. */
export function fiscalYearStart(iso = isoToday()) {
  const [y, m] = iso.split("-").map(Number);
  return `${m >= 4 ? y : y - 1}-04-01`;
}

export function presetRange(preset) {
  const today = isoToday();
  const [y, m] = today.split("-").map(Number);
  const pad = (v) => String(v).padStart(2, "0");
  if (preset === "month") return { from: `${y}-${pad(m)}-01`, to: today };
  if (preset === "last_month") {
    const first = new Date(y, m - 2, 1);
    const last = new Date(y, m - 1, 0);
    return { from: `${first.getFullYear()}-${pad(first.getMonth() + 1)}-01`, to: `${last.getFullYear()}-${pad(last.getMonth() + 1)}-${pad(last.getDate())}` };
  }
  if (preset === "quarter") {
    const qStartMonth = Math.floor((m - 1) / 3) * 3 + 1;
    return { from: `${y}-${pad(qStartMonth)}-01`, to: today };
  }
  if (preset === "last_fy") {
    const start = Number(fiscalYearStart(today).slice(0, 4)) - 1;
    return { from: `${start}-04-01`, to: `${start + 1}-03-31` };
  }
  return { from: fiscalYearStart(today), to: today };
}

export function newIdempotencyKey() {
  if (typeof crypto !== "undefined" && crypto.randomUUID) return crypto.randomUUID();
  return `acc-${Date.now()}-${Math.random().toString(36).slice(2, 12)}`;
}

/** Download rows as CSV. `columns` is [[header, (row) => value], ...]. */
export function downloadCsv(filename, columns, rows) {
  const escape = (value) => {
    const text = value === null || value === undefined ? "" : String(value);
    // Neutralise spreadsheet formula injection from user-entered narration/party names.
    const safe = /^[=+\-@\t\r]/.test(text) && !/^-?\d/.test(text) ? `'${text}` : text;
    return /[",\n]/.test(safe) ? `"${safe.replace(/"/g, '""')}"` : safe;
  };
  const lines = [columns.map(([header]) => escape(header)).join(",")];
  rows.forEach((row) => lines.push(columns.map(([, get]) => escape(get(row))).join(",")));
  const blob = new Blob(["\ufeff" + lines.join("\n")], { type: "text/csv;charset=utf-8" });
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  document.body.appendChild(link);
  link.click();
  link.remove();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}

export function errorText(error) {
  if (!error) return "";
  return error instanceof Error ? error.message : String(error);
}
