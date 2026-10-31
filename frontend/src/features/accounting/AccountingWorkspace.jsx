import { useCallback, useMemo, useState } from "react";
import {
  ArrowLeft, BarChart3, BookOpen, Boxes, CircleDollarSign, Grid2x2, Home, Landmark, ListTree, Lock, Plus,
  Receipt, RefreshCw, Settings, TrendingDown, TrendingUp, Users, Wallet,
} from "lucide-react";
import "./accounting.css";
import { accountingApi, VOUCHER_TYPES, compactMoney, formatDate, money, num, presetRange } from "./accountingApi.js";
import { Alert, Empty, Loading, Sheet, Toast, useLoader } from "./AccountingUi.jsx";
import EntrySheet from "./EntrySheet.jsx";
import VouchersTab, { VoucherRow, VoucherSheet } from "./VouchersTab.jsx";
import AccountingReports from "./AccountingReports.jsx";
import { AccountsTab, BankTab, GstTab, PartiesTab, SettingsTab } from "./AccountingTools.jsx";

const TABS = [
  { key: "overview", label: "Overview", icon: Home },
  { key: "vouchers", label: "Entries", icon: BookOpen },
  { key: "reports", label: "Reports", icon: BarChart3 },
  { key: "gst", label: "GST", icon: Receipt },
  { key: "parties", label: "Parties", icon: Users },
  { key: "bank", label: "Bank", icon: Landmark },
  { key: "accounts", label: "Accounts", icon: ListTree },
  { key: "settings", label: "Settings", icon: Settings },
];
const BOTTOM = ["overview", "vouchers", "reports", "parties"];
const PERIODS = [
  { key: "fy", label: "This financial year" },
  { key: "quarter", label: "This quarter" },
  { key: "month", label: "This month" },
  { key: "last_month", label: "Last month" },
  { key: "last_fy", label: "Last financial year" },
  { key: "custom", label: "Custom dates" },
];

export default function AccountingWorkspace({ onBack, currentUser }) {
  const role = String(currentUser?.role || "").toLowerCase();
  // Writes are owner/admin only (enforced by the backend middleware); managers get read-only screens.
  const canWrite = role === "owner" || role === "admin";
  const [tab, setTab] = useState("overview");
  const [periodKey, setPeriodKey] = useState("fy");
  const [period, setPeriod] = useState(() => presetRange("fy"));
  const [entryType, setEntryType] = useState(null); // null = closed, "" = type picker
  const [openVoucher, setOpenVoucher] = useState(null);
  const [ledgerAccountId, setLedgerAccountId] = useState("");
  const [refreshKey, setRefreshKey] = useState(0);
  const [toast, setToast] = useState("");
  const [moreOpen, setMoreOpen] = useState(false);
  const clearToast = useCallback(() => setToast(""), []);

  const settingsState = useLoader(() => accountingApi.settings(), [refreshKey]);
  const accountsState = useLoader(() => accountingApi.accounts({ include_inactive: true }), [refreshKey]);
  const accounts = accountsState.data?.items || [];
  const settings = settingsState.data;

  const refresh = () => setRefreshKey((k) => k + 1);
  const choosePeriod = (key) => {
    setPeriodKey(key);
    if (key !== "custom") setPeriod(presetRange(key));
  };
  const goLedger = (id) => { setLedgerAccountId(id); setTab("reports"); };
  const onPosted = (voucher) => {
    setEntryType(null);
    setToast(voucher?.idempotent_replay ? `Already posted as ${voucher.voucher_number}` : `Posted ${voucher?.voucher_number || "entry"}`);
    refresh();
    if (voucher?.id) setOpenVoucher(voucher.id);
  };
  const current = TABS.find((t) => t.key === tab);
  const schemaMissing = /accounting|relation|migration 015|does not exist/i.test(settingsState.error || "");

  return (
    <section className="sb-acc">
      <header className="acc-appbar acc-no-print">
        <button type="button" className="acc-icon-btn" onClick={onBack} aria-label="Back to all workspaces"><ArrowLeft size={18} /></button>
        <div className="acc-appbar-title">
          <small>{settings?.business_name || "Super Bajaar"} · Accounting</small>
          <h1>{tab === "overview" ? "Accounting & Tax" : current.label}</h1>
        </div>
        <div className="acc-appbar-actions">
          {settings?.lock_date && <span className="acc-pill grey acc-hide-mobile" title="Books are locked up to this date"><Lock size={12} aria-hidden="true" /> Locked to {formatDate(settings.lock_date)}</span>}
          <button type="button" className="acc-icon-btn" onClick={refresh} aria-label="Refresh"><RefreshCw size={17} /></button>
          {canWrite && <button type="button" className="acc-btn primary acc-hide-mobile" onClick={() => setEntryType("")}><Plus size={16} /> New entry</button>}
        </div>
      </header>

      <nav className="acc-tabs acc-no-print" role="tablist" aria-label="Accounting sections">
        {TABS.map(({ key, label, icon: Icon }) => (
          <button key={key} type="button" role="tab" className="acc-tab" aria-selected={tab === key} onClick={() => setTab(key)}><Icon size={15} aria-hidden="true" /> {label}</button>
        ))}
      </nav>

      {!["accounts", "settings"].includes(tab) && (
        <div className="acc-period acc-no-print">
          <select aria-label="Reporting period" value={periodKey} onChange={(e) => choosePeriod(e.target.value)}>
            {PERIODS.map((p) => <option key={p.key} value={p.key}>{p.label}</option>)}
          </select>
          {periodKey === "custom" ? (
            <>
              <input type="date" aria-label="From date" value={period.from} max={period.to} onChange={(e) => setPeriod((p) => ({ ...p, from: e.target.value }))} />
              <input type="date" aria-label="To date" value={period.to} min={period.from} onChange={(e) => setPeriod((p) => ({ ...p, to: e.target.value }))} />
            </>
          ) : <span className="acc-period-label">{formatDate(period.from)} – {formatDate(period.to)}</span>}
        </div>
      )}

      {schemaMissing && <Alert tone="warn">Accounting tables are not available yet. The owner needs to apply database migration 015 before this workspace can be used.</Alert>}
      {!canWrite && <Alert tone="info">You have read-only access. Only the owner or an admin can post or reverse entries.</Alert>}

      {tab === "overview" && <Overview period={period} refreshKey={refreshKey} settings={settings} canWrite={canWrite} onOpen={setOpenVoucher} onTab={setTab} onNewEntry={setEntryType} />}
      {tab === "vouchers" && <VouchersTab period={period} onOpen={setOpenVoucher} refreshKey={refreshKey} />}
      {tab === "reports" && <AccountingReports period={period} accounts={accounts} ledgerAccountId={ledgerAccountId} onLedgerAccount={setLedgerAccountId} onOpenVoucher={setOpenVoucher} refreshKey={refreshKey} />}
      {tab === "gst" && <GstTab period={period} refreshKey={refreshKey} />}
      {tab === "parties" && <PartiesTab period={period} refreshKey={refreshKey} onNewEntry={(t) => (canWrite ? setEntryType(t) : setToast("Read-only access"))} />}
      {tab === "bank" && (accountsState.data ? <BankTab accounts={accounts} period={period} canWrite={canWrite} refreshKey={refreshKey} onOpenVoucher={setOpenVoucher} onToast={setToast} /> : <div className="acc-card"><Loading /></div>)}
      {tab === "accounts" && <AccountsTab accountsState={accountsState} canWrite={canWrite} onLedger={goLedger} onToast={setToast} />}
      {tab === "settings" && <SettingsTab settingsState={settingsState} role={role} canWrite={canWrite} onToast={setToast} onSynced={refresh} />}

      {canWrite && <button type="button" className="acc-fab acc-no-print" onClick={() => setEntryType("")} aria-label="New entry"><Plus size={22} /> <span>New entry</span></button>}

      <nav className="acc-bottomnav acc-no-print" aria-label="Accounting navigation">
        {BOTTOM.map((key) => {
          const t = TABS.find((x) => x.key === key);
          const Icon = t.icon;
          return <button key={key} type="button" aria-current={tab === key ? "page" : undefined} onClick={() => setTab(key)}><Icon size={20} aria-hidden="true" />{t.label}</button>;
        })}
        <button type="button" aria-current={!BOTTOM.includes(tab) ? "page" : undefined} onClick={() => setMoreOpen(true)}><Grid2x2 size={20} aria-hidden="true" />More</button>
      </nav>

      {moreOpen && (
        <Sheet title="More" onClose={() => setMoreOpen(false)}>
          <div className="acc-type-grid">
            {TABS.filter((t) => !BOTTOM.includes(t.key)).map(({ key, label, icon: Icon }) => (
              <button key={key} type="button" className="acc-type" onClick={() => { setTab(key); setMoreOpen(false); }}>
                <span className="acc-avatar"><Icon size={18} aria-hidden="true" /></span><strong>{label}</strong>
              </button>
            ))}
          </div>
        </Sheet>
      )}

      {entryType !== null && accountsState.data && (
        <EntrySheet initialType={entryType} accounts={accounts.filter((a) => a.is_active)} settings={settings} onClose={() => setEntryType(null)} onPosted={onPosted} />
      )}
      {entryType !== null && !accountsState.data && (
        <Sheet title="New entry" onClose={() => setEntryType(null)}>{accountsState.error ? <Alert onRetry={accountsState.reload}>{accountsState.error}</Alert> : <Loading />}</Sheet>
      )}
      {openVoucher && (
        <VoucherSheet key={openVoucher} voucherId={openVoucher} settings={settings} canWrite={canWrite} onClose={() => setOpenVoucher(null)} onOpen={setOpenVoucher} onChanged={(msg) => { setToast(msg); refresh(); }} />
      )}
      <Toast message={toast} onDone={clearToast} />
    </section>
  );
}

function Overview({ period, refreshKey, settings, canWrite, onOpen, onTab, onNewEntry }) {
  const { data, loading, error, reload } = useLoader(() => accountingApi.summary({ from_date: period.from, to_date: period.to }), [period.from, period.to, refreshKey]);
  const sync = useLoader(() => (canWrite ? accountingApi.syncStatus() : Promise.resolve(null)), [refreshKey, canWrite]);
  const maxBar = useMemo(() => Math.max(1, ...(data?.monthly || []).flatMap((m) => [num(m.income), num(m.expense)])), [data]);

  if (loading && !data) return <div className="acc-stack"><div className="acc-card"><Loading rows={3} /></div><div className="acc-card"><Loading rows={5} /></div></div>;
  if (error) return <Alert onRetry={reload}>{error}</Alert>;
  const net = num(data.net_profit);
  const kpis = [
    { label: "Cash in hand", value: data.cash_balance, icon: Wallet, tab: "reports" },
    { label: "Bank, UPI & card", value: data.bank_balance, icon: Landmark, tab: "bank" },
    { label: "Customers owe you", value: data.receivables, icon: TrendingUp, tab: "parties" },
    { label: "You owe suppliers", value: data.payables, icon: TrendingDown, tab: "parties" },
    { label: "GST payable (net)", value: data.gst_payable, icon: Receipt, tab: "gst" },
    { label: "Stock value (books)", value: data.inventory_value, icon: Boxes, tab: "reports" },
    { label: "Gross profit", value: data.gross_profit, icon: CircleDollarSign, tab: "reports" },
    { label: "Entries this period", value: null, count: data.voucher_count, icon: BookOpen, tab: "vouchers" },
  ];
  return (
    <div className="acc-stack">
      {!settings?.gstin && canWrite && <Alert tone="info">Add your GSTIN and state code in Settings so invoices print correctly. <button type="button" className="acc-btn small" onClick={() => onTab("settings")}>Open settings</button></Alert>}
      {sync.data?.pending_total > 0 && (
        <Alert tone="warn">{sync.data.pending_total} store record{sync.data.pending_total === 1 ? " is" : "s are"} not yet in the books (orders, payments or goods receipts). <button type="button" className="acc-btn small" onClick={() => onTab("settings")}>Review &amp; sync</button></Alert>
      )}
      <div className="acc-hero">
        <div>
          <small>Net {net >= 0 ? "profit" : "loss"} · FY {data.fiscal_year}</small>
          <strong>{money(Math.abs(net))}</strong>
          <small>{formatDate(data.from_date)} – {formatDate(data.to_date)}</small>
        </div>
        <div className="acc-hero-split">
          <div><small>Income</small><strong>{compactMoney(data.income)}</strong></div>
          <div><small>Expenses</small><strong>{compactMoney(data.expenses)}</strong></div>
        </div>
      </div>
      <div className="acc-kpis">
        {kpis.map(({ label, value, count, icon: Icon, tab }) => (
          <button key={label} type="button" className="acc-kpi" onClick={() => onTab(tab)}>
            <span className="acc-kpi-icon"><Icon size={18} aria-hidden="true" /></span>
            <span style={{ minWidth: 0 }}><small>{label}</small><strong>{value === null ? count : money(value)}</strong></span>
          </button>
        ))}
      </div>
      <div className="acc-grid acc-grid-2">
        <section className="acc-card">
          <div className="acc-card-head">
            <div><h2>Income vs expenses</h2><p>By month</p></div>
            <div className="acc-legend"><span><i style={{ background: "#7a45d0" }} />Income</span><span><i style={{ background: "#ec9450" }} />Expenses</span></div>
          </div>
          {data.monthly.length ? (
            <div className="acc-bars" role="img" aria-label="Monthly income and expenses">
              {data.monthly.map((m) => (
                <div className="acc-bar-group" key={m.month} title={`${m.month}: income ${money(m.income)}, expenses ${money(m.expense)}`}>
                  <div className="acc-bar-pair">
                    <div className="acc-bar income" style={{ height: `${Math.max(1, (num(m.income) / maxBar) * 100)}%` }} />
                    <div className="acc-bar expense" style={{ height: `${Math.max(1, (num(m.expense) / maxBar) * 100)}%` }} />
                  </div>
                  <small>{new Date(`${m.month}-01T00:00:00`).toLocaleDateString("en-IN", { month: "short" })}</small>
                </div>
              ))}
            </div>
          ) : <Empty title="No income or expenses yet" icon={BarChart3} />}
        </section>
        <section className="acc-card">
          <div className="acc-card-head">
            <div><h2>Recent entries</h2><p>Latest postings</p></div>
            <button type="button" className="acc-btn small" onClick={() => onTab("vouchers")}>View all</button>
          </div>
          {data.recent.length ? <ul className="acc-list">{data.recent.map((v) => <li key={v.id}><VoucherRow voucher={v} onOpen={onOpen} /></li>)}</ul>
            : <Empty title="Your books are empty" icon={BookOpen}>{canWrite ? <>Start with opening balances, then record sales and expenses.<div style={{ marginTop: 10 }}><button type="button" className="acc-btn primary small" onClick={() => onNewEntry("opening")}>Add opening balances</button></div></> : "No entries have been posted."}</Empty>}
        </section>
      </div>
      {canWrite && (
        <section className="acc-card">
          <div className="acc-card-head"><div><h2>Quick actions</h2></div></div>
          <div className="acc-chips">
            {["sales", "purchase", "expense", "receipt", "payment", "contra", "journal"].map((t) => (
              <button key={t} type="button" className="acc-chip" onClick={() => onNewEntry(t)}>+ {VOUCHER_TYPES[t].short}</button>
            ))}
          </div>
        </section>
      )}
    </div>
  );
}
