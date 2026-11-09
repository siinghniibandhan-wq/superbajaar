import { useState } from "react";
import { Download, FileText, Printer, RotateCcw, Search } from "lucide-react";
import { accountingApi, VOUCHER_TYPES, downloadCsv, errorText, formatDate, isoToday, money, num } from "./accountingApi.js";
import { Alert, Empty, Field, Loading, Sheet, useLoader } from "./AccountingUi.jsx";

const PAGE = 50;

export function VoucherRow({ voucher, onOpen }) {
  const meta = VOUCHER_TYPES[voucher.voucher_type] || VOUCHER_TYPES.journal;
  const initials = meta.short.slice(0, 2).toUpperCase();
  return (
    <button type="button" className="acc-row" onClick={() => onOpen(voucher.id)}>
      <span className={`acc-avatar ${meta.tone}`} aria-hidden="true">{initials}</span>
      <span className="acc-row-main">
        <strong>{voucher.party_name || voucher.narration || meta.label}</strong>
        <small>{voucher.voucher_number} · {meta.short} · {formatDate(voucher.voucher_date)}{voucher.source_type ? " · auto" : ""}</small>
      </span>
      <span className="acc-row-amt">
        {money(voucher.total_amount)}
        {voucher.status === "reversed" ? <small className="acc-tone-red">Reversed</small> : voucher.reversal_of_id ? <small>Reversal</small> : <small>Posted</small>}
      </span>
    </button>
  );
}

export default function VouchersTab({ period, onOpen, refreshKey }) {
  const [filters, setFilters] = useState({ voucher_type: "", search: "" });
  const [query, setQuery] = useState("");
  const [page, setPage] = useState(0);
  const { data, loading, error, reload } = useLoader(
    () => accountingApi.vouchers({ voucher_type: filters.voucher_type, search: query, from_date: period.from, to_date: period.to, limit: PAGE, offset: page * PAGE }),
    [filters.voucher_type, query, period.from, period.to, page, refreshKey],
  );
  const items = data?.items || [];
  const total = data?.total || 0;

  const exportCsv = async () => {
    const all = await accountingApi.vouchers({ voucher_type: filters.voucher_type, search: query, from_date: period.from, to_date: period.to, limit: 500 });
    downloadCsv(`vouchers_${period.from}_${period.to}.csv`, [
      ["Number", (v) => v.voucher_number], ["Date", (v) => v.voucher_date], ["Type", (v) => VOUCHER_TYPES[v.voucher_type]?.label || v.voucher_type],
      ["Party", (v) => v.party_name], ["GSTIN", (v) => v.party_gstin], ["Reference", (v) => v.reference], ["Narration", (v) => v.narration],
      ["Taxable", (v) => num(v.taxable_total).toFixed(2)], ["Tax", (v) => num(v.tax_total).toFixed(2)], ["Total", (v) => num(v.total_amount).toFixed(2)],
      ["Status", (v) => v.status], ["Source", (v) => v.source_type ? `${v.source_type}:${v.source_id}` : "manual"], ["Created by", (v) => v.created_by_email],
    ], all.items || []);
  };

  return (
    <div className="acc-card">
      <div className="acc-card-head">
        <div><h2>Day book &amp; vouchers</h2><p>{total} entr{total === 1 ? "y" : "ies"} in this period</p></div>
        <button type="button" className="acc-btn small" onClick={exportCsv} disabled={!total}><Download size={14} /> CSV</button>
      </div>
      <form className="acc-toolbar" onSubmit={(e) => { e.preventDefault(); setPage(0); setQuery(filters.search.trim()); }}>
        <label className="acc-search acc-field"><Search size={16} aria-hidden="true" /><input aria-label="Search vouchers" placeholder="Search number, party, reference…" value={filters.search} onChange={(e) => setFilters((f) => ({ ...f, search: e.target.value }))} /></label>
        <label className="acc-field" style={{ width: 190 }}>
          <select aria-label="Voucher type" value={filters.voucher_type} onChange={(e) => { setPage(0); setFilters((f) => ({ ...f, voucher_type: e.target.value })); }}>
            <option value="">All types</option>
            {Object.entries(VOUCHER_TYPES).map(([key, meta]) => <option key={key} value={key}>{meta.label}</option>)}
          </select>
        </label>
      </form>
      <Alert onRetry={reload}>{error}</Alert>
      {loading && !data ? <Loading /> : items.length ? (
        <ul className="acc-list">{items.map((v) => <li key={v.id}><VoucherRow voucher={v} onOpen={onOpen} /></li>)}</ul>
      ) : <Empty title="No entries yet" icon={FileText}>Tap “New entry” to record a sale, purchase, expense or payment.</Empty>}
      {total > PAGE && (
        <div className="acc-toolbar" style={{ justifyContent: "center", marginTop: 12 }}>
          <button type="button" className="acc-btn small" disabled={page === 0} onClick={() => setPage((p) => p - 1)}>Previous</button>
          <span className="acc-muted">Page {page + 1} of {Math.ceil(total / PAGE)}</span>
          <button type="button" className="acc-btn small" disabled={(page + 1) * PAGE >= total} onClick={() => setPage((p) => p + 1)}>Next</button>
        </div>
      )}
    </div>
  );
}

/** Voucher detail sheet with print and reverse actions. */
export function VoucherSheet({ voucherId, settings, canWrite, onClose, onChanged, onOpen }) {
  const { data: voucher, loading, error, reload } = useLoader(() => accountingApi.voucher(voucherId), [voucherId]);
  const [reversing, setReversing] = useState(false);
  const [reason, setReason] = useState("");
  const [reversalDate, setReversalDate] = useState(isoToday());
  const [busy, setBusy] = useState(false);
  const [actionError, setActionError] = useState("");
  const meta = voucher ? VOUCHER_TYPES[voucher.voucher_type] || VOUCHER_TYPES.journal : null;
  const isInvoice = voucher && ["sales", "purchase", "credit_note", "debit_note"].includes(voucher.voucher_type);
  const lines = voucher?.lines || [];
  const itemLines = lines.filter((l) => l.gst_rate !== null && l.gst_rate !== undefined && !l.tax_component);
  const taxLines = lines.filter((l) => l.tax_component);
  const lockDate = settings?.lock_date;
  const locked = Boolean(lockDate && reversalDate && reversalDate <= lockDate);

  const doReverse = async () => {
    setBusy(true);
    setActionError("");
    try {
      const result = await accountingApi.reverse(voucherId, { reason: reason.trim(), reversal_date: reversalDate || null });
      onChanged(`Reversed with ${result.voucher_number || "a reversal entry"}`);
      setReversing(false);
      reload();
    } catch (err) {
      setActionError(errorText(err));
    } finally {
      setBusy(false);
    }
  };

  const footer = voucher && (
    <>
      <button type="button" className="acc-btn" onClick={() => window.print()}><Printer size={15} /> Print</button>
      <span className="acc-spacer acc-hide-mobile" />
      {canWrite && voucher.status === "posted" && !voucher.reversal_of_id && !reversing && (
        <button type="button" className="acc-btn danger" onClick={() => setReversing(true)}><RotateCcw size={15} /> Reverse</button>
      )}
      <button type="button" className="acc-btn primary" onClick={onClose}>Done</button>
    </>
  );

  return (
    <Sheet wide title={voucher ? voucher.voucher_number : "Voucher"} onClose={onClose} footer={footer}>
      <Alert onRetry={reload}>{error}</Alert>
      {loading && !voucher ? <Loading rows={6} /> : voucher && (
        <div className="acc-stack">
          {voucher.status === "reversed" && (
            <Alert tone="warn">This entry was reversed.{voucher.reversed_by_voucher_id && <> <button type="button" className="acc-btn small" onClick={() => onOpen(voucher.reversed_by_voucher_id)}>Open reversal</button></>}{voucher.reversal_reason && <> Reason: {voucher.reversal_reason}</>}</Alert>
          )}
          {voucher.reversal_of_id && <Alert tone="info">This is a reversal entry. <button type="button" className="acc-btn small" onClick={() => onOpen(voucher.reversal_of_id)}>Open original</button></Alert>}
          {reversing && (
            <div className="acc-card" style={{ borderColor: "#f3c9d1" }}>
              <h3 style={{ fontSize: 15, marginBottom: 8 }}>Reverse this entry</h3>
              <p className="acc-muted" style={{ marginTop: 0 }}>Posted entries are never edited or deleted. A reversal posts the opposite entry so the books stay auditable.</p>
              <Alert>{actionError}</Alert>
              {locked && <Alert tone="warn">Books are locked up to {formatDate(lockDate)}. Pick a later reversal date.</Alert>}
              <div className="acc-form-grid">
                <Field label="Reason (required)"><input value={reason} onChange={(e) => setReason(e.target.value)} minLength={5} maxLength={500} placeholder="e.g. Entered twice by mistake" /></Field>
                <Field label="Reversal date"><input type="date" value={reversalDate} min={voucher.voucher_date} onChange={(e) => setReversalDate(e.target.value)} /></Field>
              </div>
              <div className="acc-toolbar" style={{ marginTop: 12, marginBottom: 0 }}>
                <button type="button" className="acc-btn" onClick={() => setReversing(false)} disabled={busy}>Keep entry</button>
                <button type="button" className="acc-btn danger" onClick={doReverse} disabled={busy || reason.trim().length < 5 || locked}>{busy ? "Reversing…" : "Confirm reversal"}</button>
              </div>
            </div>
          )}
          <article className="acc-doc acc-printable">
            <div className="acc-doc-head">
              <div>
                <p className="acc-print-only" style={{ margin: 0, fontWeight: 800 }}>{settings?.business_name}{settings?.gstin ? ` · GSTIN ${settings.gstin}` : ""}</p>
                <h3>{isInvoice && voucher.voucher_type === "sales" ? "Tax invoice" : meta.label}</h3>
                <span className="acc-muted">{voucher.voucher_number}</span>
              </div>
              <div style={{ textAlign: "right" }}>
                <strong style={{ font: "800 22px Manrope,sans-serif" }}>{money(voucher.total_amount)}</strong>
                <div className="acc-muted">{formatDate(voucher.voucher_date)}</div>
              </div>
            </div>
            <div className="acc-doc-meta">
              {voucher.party_name && <div><small>{voucher.party_type === "supplier" ? "Supplier" : voucher.party_type === "customer" ? "Customer" : "Party"}</small><strong>{voucher.party_name}</strong></div>}
              {voucher.party_gstin && <div><small>Party GSTIN</small><strong>{voucher.party_gstin}</strong></div>}
              {voucher.place_of_supply && <div><small>Place of supply</small><strong>{voucher.place_of_supply === "inter" ? "Inter-state (IGST)" : "Intra-state (CGST+SGST)"}</strong></div>}
              {voucher.reference && <div><small>Reference</small><strong>{voucher.reference}</strong></div>}
              {voucher.due_date && <div><small>Due date</small><strong>{formatDate(voucher.due_date)}</strong></div>}
              <div><small>Recorded by</small><strong>{voucher.created_by_email || (voucher.source_type ? "Automatic sync" : "—")}</strong></div>
            </div>
            {isInvoice && itemLines.length > 0 && (
              <div className="acc-table-wrap" style={{ marginBottom: 12 }}>
                <table className="acc-table">
                  <thead><tr><th>Item</th><th>HSN/SAC</th><th className="num">Qty</th><th className="num">Rate</th><th className="num">GST</th><th className="num">Taxable</th></tr></thead>
                  <tbody>{itemLines.map((l) => <tr key={l.id}><td>{l.narration}</td><td>{l.hsn_sac || "—"}</td><td className="num">{l.quantity ? num(l.quantity) : "—"}</td><td className="num">{l.unit_rate ? money(l.unit_rate) : "—"}</td><td className="num">{num(l.gst_rate)}%</td><td className="num">{money(num(l.debit) || num(l.credit))}</td></tr>)}</tbody>
                  <tfoot>
                    <tr><td colSpan={5}>Taxable value</td><td className="num">{money(voucher.taxable_total)}</td></tr>
                    {taxLines.map((l) => <tr key={l.id}><td colSpan={5}>{l.narration}</td><td className="num">{money(num(l.debit) || num(l.credit))}</td></tr>)}
                    <tr><td colSpan={5}>Invoice total</td><td className="num">{money(voucher.total_amount)}</td></tr>
                  </tfoot>
                </table>
              </div>
            )}
            <h4 style={{ margin: "6px 0 8px", fontFamily: "Manrope,sans-serif" }}>Ledger postings</h4>
            <div className="acc-table-wrap">
              <table className="acc-table">
                <thead><tr><th>Account</th><th>Note</th><th className="num">Debit</th><th className="num">Credit</th></tr></thead>
                <tbody>{lines.map((l) => <tr key={l.id}><td><strong>{l.account_code}</strong> {l.account_name}</td><td>{l.narration || ""}</td><td className="num">{num(l.debit) ? money(l.debit) : ""}</td><td className="num">{num(l.credit) ? money(l.credit) : ""}</td></tr>)}</tbody>
                <tfoot><tr><td colSpan={2}>Total</td><td className="num">{money(lines.reduce((s, l) => s + num(l.debit), 0))}</td><td className="num">{money(lines.reduce((s, l) => s + num(l.credit), 0))}</td></tr></tfoot>
              </table>
            </div>
            {voucher.narration && <p style={{ marginBottom: 0 }}><strong>Narration:</strong> {voucher.narration}</p>}
            {voucher.source_type && <p className="acc-muted">Posted automatically from {voucher.source_type.replace(/_/g, " ")} #{voucher.source_id}.</p>}
          </article>
        </div>
      )}
    </Sheet>
  );
}
