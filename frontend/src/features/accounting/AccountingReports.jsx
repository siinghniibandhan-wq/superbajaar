import { useState } from "react";
import { BarChart3, Download, Printer, Scale } from "lucide-react";
import { accountingApi, ACCOUNT_TYPES, VOUCHER_TYPES, downloadCsv, drCr, formatDate, money, num } from "./accountingApi.js";
import { AccountSelect, Alert, Empty, Loading, useLoader } from "./AccountingUi.jsx";

const REPORTS = [
  { key: "pl", label: "Profit & loss" },
  { key: "bs", label: "Balance sheet" },
  { key: "tb", label: "Trial balance" },
  { key: "ledger", label: "Account ledger" },
  { key: "daybook", label: "Day book" },
];

export default function AccountingReports({ period, accounts, ledgerAccountId, onLedgerAccount, onOpenVoucher, refreshKey, initialReport = "pl" }) {
  const [report, setReport] = useState(ledgerAccountId ? "ledger" : initialReport);
  return (
    <div className="acc-stack">
      <div className="acc-chips acc-no-print" role="tablist" aria-label="Reports">
        {REPORTS.map((r) => <button key={r.key} type="button" role="tab" className="acc-chip" aria-pressed={report === r.key} aria-selected={report === r.key} onClick={() => setReport(r.key)}>{r.label}</button>)}
      </div>
      {report === "pl" && <ProfitLoss period={period} refreshKey={refreshKey} onLedger={(id) => { onLedgerAccount(id); setReport("ledger"); }} />}
      {report === "bs" && <BalanceSheet period={period} refreshKey={refreshKey} onLedger={(id) => { onLedgerAccount(id); setReport("ledger"); }} />}
      {report === "tb" && <TrialBalance period={period} refreshKey={refreshKey} onLedger={(id) => { onLedgerAccount(id); setReport("ledger"); }} />}
      {report === "ledger" && <Ledger period={period} accounts={accounts} accountId={ledgerAccountId} onAccount={onLedgerAccount} onOpenVoucher={onOpenVoucher} refreshKey={refreshKey} />}
      {report === "daybook" && <DayBook period={period} refreshKey={refreshKey} onOpenVoucher={onOpenVoucher} />}
    </div>
  );
}

function ReportCard({ title, subtitle, onCsv, children, status }) {
  return (
    <section className="acc-card acc-printable">
      <div className="acc-card-head">
        <div><h2>{title}</h2><p>{subtitle}</p></div>
        <div className="acc-toolbar acc-no-print" style={{ margin: 0 }}>
          {status}
          {onCsv && <button type="button" className="acc-btn small" onClick={onCsv}><Download size={14} /> CSV</button>}
          <button type="button" className="acc-btn small" onClick={() => window.print()}><Printer size={14} /> Print</button>
        </div>
      </div>
      {children}
    </section>
  );
}

function BalancedPill({ balanced }) {
  return <span className={`acc-pill ${balanced ? "green" : "red"}`}><Scale size={12} aria-hidden="true" /> {balanced ? "Balanced" : "Out of balance"}</span>;
}

function ProfitLoss({ period, refreshKey, onLedger }) {
  const { data, loading, error, reload } = useLoader(() => accountingApi.profitLoss({ from_date: period.from, to_date: period.to }), [period.from, period.to, refreshKey]);
  if (loading && !data) return <div className="acc-card"><Loading rows={6} /></div>;
  if (error) return <Alert onRetry={reload}>{error}</Alert>;
  const s = data.sections;
  const t = data.totals;
  const section = (title, rows, total) => (
    <>
      <tr className="acc-section-row"><td colSpan={2}>{title}</td></tr>
      {rows.length ? rows.map((r) => <tr key={r.id} className="clickable" onClick={() => onLedger(r.id)}><td>{r.code} · {r.name}</td><td className="num">{money(r.amount)}</td></tr>)
        : <tr><td className="acc-muted" colSpan={2}>No entries</td></tr>}
      <tr><td><strong>Total {title.toLowerCase()}</strong></td><td className="num"><strong>{money(total)}</strong></td></tr>
    </>
  );
  const csv = () => downloadCsv(`profit_loss_${data.from_date}_${data.to_date}.csv`, [["Section", (r) => r.section], ["Code", (r) => r.code], ["Account", (r) => r.name], ["Amount", (r) => num(r.amount).toFixed(2)]],
    [...["revenue", "cogs", "other_income", "expenses"].flatMap((k) => s[k].map((r) => ({ ...r, section: k }))),
      { section: "gross_profit", code: "", name: "Gross profit", amount: data.gross_profit }, { section: "net_profit", code: "", name: "Net profit", amount: data.net_profit }]);
  return (
    <ReportCard title="Profit & loss" subtitle={`${formatDate(data.from_date)} – ${formatDate(data.to_date)}`} onCsv={csv}>
      <div className="acc-kpis" style={{ gridTemplateColumns: "repeat(3,minmax(0,1fr))" }}>
        <div className="acc-kpi"><div><small>Income</small><strong>{money(num(t.revenue) + num(t.other_income))}</strong></div></div>
        <div className="acc-kpi"><div><small>Gross profit</small><strong>{money(data.gross_profit)}</strong></div></div>
        <div className="acc-kpi"><div><small>Net profit</small><strong className={num(data.net_profit) >= 0 ? "acc-tone-green" : "acc-tone-red"}>{money(data.net_profit)}</strong></div></div>
      </div>
      <div className="acc-table-wrap">
        <table className="acc-table">
          <thead><tr><th>Account</th><th className="num">Amount</th></tr></thead>
          <tbody>
            {section("Revenue", s.revenue, t.revenue)}
            {section("Cost of goods sold", s.cogs, t.cogs)}
            <tr className="acc-section-row"><td>Gross profit</td><td className="num">{money(data.gross_profit)}</td></tr>
            {section("Other income", s.other_income, t.other_income)}
            {section("Operating expenses", s.expenses, t.expenses)}
          </tbody>
          <tfoot><tr><td>Net profit</td><td className="num">{money(data.net_profit)}</td></tr></tfoot>
        </table>
      </div>
    </ReportCard>
  );
}

function BalanceSheet({ period, refreshKey, onLedger }) {
  const { data, loading, error, reload } = useLoader(() => accountingApi.balanceSheet({ as_of: period.to }), [period.to, refreshKey]);
  if (loading && !data) return <div className="acc-card"><Loading rows={6} /></div>;
  if (error) return <Alert onRetry={reload}>{error}</Alert>;
  const block = (title, rows, total) => (
    <div className="acc-table-wrap">
      <table className="acc-table">
        <thead><tr><th>{title}</th><th className="num">Amount</th></tr></thead>
        <tbody>{rows.length ? rows.map((r) => <tr key={r.code} className={r.id ? "clickable" : ""} onClick={() => r.id && onLedger(r.id)}><td>{r.code} · {r.name}</td><td className="num">{money(r.amount)}</td></tr>) : <tr><td className="acc-muted" colSpan={2}>Nothing recorded</td></tr>}</tbody>
        <tfoot><tr><td>Total {title.toLowerCase()}</td><td className="num">{money(total)}</td></tr></tfoot>
      </table>
    </div>
  );
  const csv = () => downloadCsv(`balance_sheet_${data.as_of}.csv`, [["Group", (r) => r.group], ["Code", (r) => r.code], ["Account", (r) => r.name], ["Amount", (r) => num(r.amount).toFixed(2)]],
    [...data.assets.map((r) => ({ ...r, group: "Assets" })), ...data.liabilities.map((r) => ({ ...r, group: "Liabilities" })), ...data.equity.map((r) => ({ ...r, group: "Equity" }))]);
  return (
    <ReportCard title="Balance sheet" subtitle={`As of ${formatDate(data.as_of)}`} onCsv={csv} status={<BalancedPill balanced={data.balanced} />}>
      <div className="acc-grid acc-grid-2">
        {block("Assets", data.assets, data.total_assets)}
        <div className="acc-stack">
          {block("Liabilities", data.liabilities, data.total_liabilities)}
          {block("Equity", data.equity, data.total_equity)}
          <div className="acc-totals"><div className="grand" style={{ border: 0, margin: 0, padding: 0 }}><span>Liabilities + equity</span><span>{money(num(data.total_liabilities) + num(data.total_equity))}</span></div></div>
        </div>
      </div>
    </ReportCard>
  );
}

function TrialBalance({ period, refreshKey, onLedger }) {
  const { data, loading, error, reload } = useLoader(() => accountingApi.trialBalance({ as_of: period.to }), [period.to, refreshKey]);
  if (loading && !data) return <div className="acc-card"><Loading rows={6} /></div>;
  if (error) return <Alert onRetry={reload}>{error}</Alert>;
  const csv = () => downloadCsv(`trial_balance_${data.as_of}.csv`, [["Code", (r) => r.code], ["Account", (r) => r.name], ["Type", (r) => r.account_type], ["Debit", (r) => num(r.debit).toFixed(2)], ["Credit", (r) => num(r.credit).toFixed(2)]], data.items);
  return (
    <ReportCard title="Trial balance" subtitle={`As of ${formatDate(data.as_of)}`} onCsv={csv} status={<BalancedPill balanced={data.balanced} />}>
      {data.items.length ? (
        <div className="acc-table-wrap">
          <table className="acc-table">
            <thead><tr><th>Code</th><th>Account</th><th>Type</th><th className="num">Debit</th><th className="num">Credit</th></tr></thead>
            <tbody>{data.items.map((r) => <tr key={r.id} className="clickable" onClick={() => onLedger(r.id)}><td>{r.code}</td><td>{r.name}</td><td>{ACCOUNT_TYPES.find((t) => t.key === r.account_type)?.label}</td><td className="num">{num(r.debit) ? money(r.debit) : ""}</td><td className="num">{num(r.credit) ? money(r.credit) : ""}</td></tr>)}</tbody>
            <tfoot><tr><td colSpan={3}>Total</td><td className="num">{money(data.total_debit)}</td><td className="num">{money(data.total_credit)}</td></tr></tfoot>
          </table>
        </div>
      ) : <Empty title="No balances yet" icon={BarChart3}>Post an entry or run the sync to see balances.</Empty>}
    </ReportCard>
  );
}

function Ledger({ period, accounts, accountId, onAccount, onOpenVoucher, refreshKey }) {
  const { data, loading, error, reload } = useLoader(
    () => (accountId ? accountingApi.ledger(accountId, { from_date: period.from, to_date: period.to }) : Promise.resolve(null)),
    [accountId, period.from, period.to, refreshKey],
  );
  const csv = () => downloadCsv(`ledger_${data.account.code}_${data.from_date}_${data.to_date}.csv`, [["Date", (r) => r.voucher_date], ["Voucher", (r) => r.voucher_number], ["Type", (r) => r.voucher_type], ["Party", (r) => r.party_name], ["Narration", (r) => r.narration], ["Debit", (r) => num(r.debit).toFixed(2)], ["Credit", (r) => num(r.credit).toFixed(2)], ["Balance (Dr+/Cr-)", (r) => num(r.balance).toFixed(2)]], data.items);
  return (
    <ReportCard title={data?.account ? `${data.account.code} · ${data.account.name}` : "Account ledger"} subtitle={data ? `${formatDate(data.from_date)} – ${formatDate(data.to_date)}` : "Choose an account"} onCsv={data?.items?.length ? csv : null}>
      <div className="acc-field acc-no-print" style={{ maxWidth: 420, marginBottom: 12 }}>
        <AccountSelect accounts={accounts} value={accountId} onChange={onAccount} ariaLabel="Ledger account" />
      </div>
      <Alert onRetry={reload}>{error}</Alert>
      {!accountId ? <Empty title="Pick an account" icon={BarChart3}>Every debit and credit for the account appears here with a running balance.</Empty>
        : loading && !data ? <Loading rows={6} /> : data && (
          <div className="acc-table-wrap">
            <table className="acc-table">
              <thead><tr><th>Date</th><th>Voucher</th><th>Particulars</th><th className="num">Debit</th><th className="num">Credit</th><th className="num">Balance</th></tr></thead>
              <tbody>
                <tr className="acc-section-row"><td colSpan={5}>Opening balance</td><td className="num">{drCr(data.opening_balance)}</td></tr>
                {data.items.map((r) => (
                  <tr key={r.line_id} className="clickable" onClick={() => onOpenVoucher(r.voucher_id)}>
                    <td>{formatDate(r.voucher_date)}</td><td>{r.voucher_number}<div className="acc-muted">{VOUCHER_TYPES[r.voucher_type]?.short}</div></td>
                    <td>{r.party_name || ""}{r.party_name && r.narration ? " — " : ""}{r.narration || ""}</td>
                    <td className="num">{num(r.debit) ? money(r.debit) : ""}</td><td className="num">{num(r.credit) ? money(r.credit) : ""}</td><td className="num">{drCr(r.balance)}</td>
                  </tr>
                ))}
                {!data.items.length && <tr><td colSpan={6} className="acc-muted">No movements in this period.</td></tr>}
              </tbody>
              <tfoot><tr><td colSpan={3}>Closing balance</td><td className="num">{money(data.total_debit)}</td><td className="num">{money(data.total_credit)}</td><td className="num">{drCr(data.closing_balance)}</td></tr></tfoot>
            </table>
          </div>
        )}
    </ReportCard>
  );
}

function DayBook({ period, refreshKey, onOpenVoucher }) {
  const { data, loading, error, reload } = useLoader(() => accountingApi.dayBook({ from_date: period.from, to_date: period.to }), [period.from, period.to, refreshKey]);
  if (loading && !data) return <div className="acc-card"><Loading rows={6} /></div>;
  if (error) return <Alert onRetry={reload}>{error}</Alert>;
  const csv = () => downloadCsv(`day_book_${data.from_date}_${data.to_date}.csv`, [["Date", (r) => r.voucher_date], ["Voucher", (r) => r.voucher_number], ["Type", (r) => r.voucher_type], ["Party", (r) => r.party_name], ["Account", (r) => `${r.code} ${r.name}`], ["Debit", (r) => num(r.debit).toFixed(2)], ["Credit", (r) => num(r.credit).toFixed(2)]],
    data.items.flatMap((v) => v.lines.map((l) => ({ ...l, voucher_date: v.voucher_date, voucher_number: v.voucher_number, voucher_type: v.voucher_type, party_name: v.party_name }))));
  return (
    <ReportCard title="Day book" subtitle={`${formatDate(data.from_date)} – ${formatDate(data.to_date)} · ${data.items.length} entries`} onCsv={data.items.length ? csv : null}>
      {data.items.length ? (
        <div className="acc-table-wrap">
          <table className="acc-table">
            <thead><tr><th>Date</th><th>Voucher</th><th>Account</th><th className="num">Debit</th><th className="num">Credit</th></tr></thead>
            <tbody>
              {data.items.map((v) => v.lines.map((l, i) => (
                <tr key={`${v.id}-${i}`} className="clickable" onClick={() => onOpenVoucher(v.id)}>
                  <td>{i === 0 ? formatDate(v.voucher_date) : ""}</td>
                  <td>{i === 0 ? <>{v.voucher_number}{v.status === "reversed" && <span className="acc-pill red" style={{ marginLeft: 6 }}>Reversed</span>}<div className="acc-muted">{v.party_name || v.narration || ""}</div></> : ""}</td>
                  <td>{l.code} · {l.name}</td><td className="num">{num(l.debit) ? money(l.debit) : ""}</td><td className="num">{num(l.credit) ? money(l.credit) : ""}</td>
                </tr>
              )))}
            </tbody>
          </table>
        </div>
      ) : <Empty title="No entries in this period" />}
    </ReportCard>
  );
}
