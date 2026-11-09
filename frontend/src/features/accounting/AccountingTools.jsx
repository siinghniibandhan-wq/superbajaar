import { useMemo, useState } from "react";
import { Check, Download, Landmark, Lock, Plus, RefreshCw, Users } from "lucide-react";
import { accountingApi, ACCOUNT_TYPES, downloadCsv, drCr, errorText, formatDate, isoToday, money, num } from "./accountingApi.js";
import { Alert, Empty, Field, Loading, Sheet, useLoader } from "./AccountingUi.jsx";

/* ------------------------------------------------------------------ GST */

export function GstTab({ period, refreshKey }) {
  const { data, loading, error, reload } = useLoader(() => accountingApi.gst({ from_date: period.from, to_date: period.to }), [period.from, period.to, refreshKey]);
  if (loading && !data) return <div className="acc-card"><Loading rows={6} /></div>;
  if (error) return <Alert onRetry={reload}>{error}</Alert>;
  const comps = ["cgst", "sgst", "igst"];
  const csv = () => downloadCsv(`gst_summary_${data.from_date}_${data.to_date}.csv`, [
    ["GST rate %", (r) => r.rate], ["Outward taxable", (r) => num(r.outward_taxable).toFixed(2)], ["Outward B2B", (r) => num(r.outward_b2b).toFixed(2)], ["Outward B2C", (r) => num(r.outward_b2c).toFixed(2)],
    ["Output tax", (r) => num(r.output_tax).toFixed(2)], ["Inward taxable", (r) => num(r.inward_taxable).toFixed(2)], ["Input tax", (r) => num(r.input_tax).toFixed(2)],
  ], data.by_rate);
  const net = num(data.total_net_payable);
  return (
    <div className="acc-stack">
      <div className="acc-hero" style={{ gridTemplateColumns: "1fr" }}>
        <div>
          <small>{net >= 0 ? "Estimated GST payable" : "Input tax credit carried forward"} · {formatDate(data.from_date)} – {formatDate(data.to_date)}</small>
          <strong>{money(Math.abs(net))}</strong>
        </div>
        <div className="acc-hero-split" style={{ gridTemplateColumns: "repeat(3,1fr)" }}>
          {comps.map((c) => <div key={c}><small>{c.toUpperCase()} net</small><strong>{money(data.net_payable[c])}</strong></div>)}
        </div>
      </div>
      <section className="acc-card acc-printable">
        <div className="acc-card-head">
          <div><h2>Output vs input tax</h2><p>Collected on sales minus paid on purchases</p></div>
          <div className="acc-toolbar acc-no-print" style={{ margin: 0 }}><button type="button" className="acc-btn small" onClick={csv} disabled={!data.by_rate.length}><Download size={14} /> CSV</button></div>
        </div>
        <div className="acc-table-wrap" style={{ marginBottom: 14 }}>
          <table className="acc-table">
            <thead><tr><th>Component</th><th className="num">Output tax</th><th className="num">Input credit</th><th className="num">Net</th></tr></thead>
            <tbody>{comps.map((c) => <tr key={c}><td>{c.toUpperCase()}</td><td className="num">{money(data.output_tax[c])}</td><td className="num">{money(data.input_tax[c])}</td><td className="num">{money(data.net_payable[c])}</td></tr>)}</tbody>
            <tfoot><tr><td>Total</td><td className="num">{money(data.total_output_tax)}</td><td className="num">{money(data.total_input_tax)}</td><td className="num">{money(data.total_net_payable)}</td></tr></tfoot>
          </table>
        </div>
        <h3 style={{ fontSize: 14, margin: "4px 0 8px" }}>Rate-wise summary (helps with GSTR-1 / GSTR-3B)</h3>
        {data.by_rate.length ? (
          <div className="acc-table-wrap">
            <table className="acc-table">
              <thead><tr><th>Rate</th><th className="num">Outward taxable</th><th className="num">B2B</th><th className="num">B2C</th><th className="num">Output tax</th><th className="num">Inward taxable</th><th className="num">Input tax</th></tr></thead>
              <tbody>{data.by_rate.map((r) => <tr key={r.rate}><td>{r.rate}%</td><td className="num">{money(r.outward_taxable)}</td><td className="num">{money(r.outward_b2b)}</td><td className="num">{money(r.outward_b2c)}</td><td className="num">{money(r.output_tax)}</td><td className="num">{money(r.inward_taxable)}</td><td className="num">{money(r.input_tax)}</td></tr>)}</tbody>
            </table>
          </div>
        ) : <Empty title="No GST entries in this period" />}
        <Alert tone="warn">{data.disclaimer}</Alert>
      </section>
    </div>
  );
}

/* -------------------------------------------------------------- Parties */

export function PartiesTab({ period, refreshKey, onNewEntry }) {
  const [kind, setKind] = useState("receivable");
  const { data, loading, error, reload } = useLoader(() => accountingApi.parties({ kind, as_of: period.to }), [kind, period.to, refreshKey]);
  const items = data?.items || [];
  const csv = () => downloadCsv(`${kind}_${data.as_of}.csv`, [["Party", (r) => r.party_name], ["Outstanding", (r) => num(r.outstanding).toFixed(2)], ["0-30 days", (r) => num(r.current).toFixed(2)], ["31-60", (r) => num(r.d31_60).toFixed(2)], ["61-90", (r) => num(r.d61_90).toFixed(2)], ["90+", (r) => num(r.d90_plus).toFixed(2)]], items);
  return (
    <div className="acc-card">
      <div className="acc-card-head">
        <div className="acc-chips" role="tablist" aria-label="Party balances">
          <button type="button" role="tab" className="acc-chip" aria-pressed={kind === "receivable"} aria-selected={kind === "receivable"} onClick={() => setKind("receivable")}>Customers owe you</button>
          <button type="button" role="tab" className="acc-chip" aria-pressed={kind === "payable"} aria-selected={kind === "payable"} onClick={() => setKind("payable")}>You owe suppliers</button>
        </div>
        <div className="acc-toolbar" style={{ margin: 0 }}>
          <button type="button" className="acc-btn small" onClick={() => onNewEntry(kind === "receivable" ? "receipt" : "payment")}><Plus size={14} /> {kind === "receivable" ? "Record receipt" : "Record payment"}</button>
          <button type="button" className="acc-btn small" onClick={csv} disabled={!items.length}><Download size={14} /> CSV</button>
        </div>
      </div>
      <Alert onRetry={reload}>{error}</Alert>
      {loading && !data ? <Loading /> : (
        <>
          <div className="acc-totals" style={{ marginBottom: 12 }}><div className="grand" style={{ border: 0, padding: 0, margin: 0 }}><span>Total outstanding as of {formatDate(data?.as_of)}</span><span>{money(data?.total)}</span></div></div>
          {items.length ? (
            <ul className="acc-list">
              {items.map((p) => {
                const total = Math.max(num(p.outstanding), 0.01);
                const parts = [p.current, p.d31_60, p.d61_90, p.d90_plus].map((v) => `${Math.max(0, (num(v) / total) * 100)}%`);
                return (
                  <li key={p.party_name} className="acc-row">
                    <span className={`acc-avatar ${kind === "receivable" ? "green" : "orange"}`} aria-hidden="true">{p.party_name.slice(0, 2).toUpperCase()}</span>
                    <span className="acc-row-main">
                      <strong>{p.party_name}</strong>
                      <span className="acc-aging" title={`0–30: ${money(p.current)} · 31–60: ${money(p.d31_60)} · 61–90: ${money(p.d61_90)} · 90+: ${money(p.d90_plus)}`} style={{ marginTop: 6 }}>{parts.map((w, i) => <span key={i} style={{ width: w }} />)}</span>
                      <small>0–30 {money(p.current)} · 31–60 {money(p.d31_60)} · 61–90 {money(p.d61_90)} · 90+ {money(p.d90_plus)}</small>
                    </span>
                    <span className="acc-row-amt">{money(p.outstanding)}{num(p.d90_plus) > 0 && <small className="acc-tone-red">Overdue 90+</small>}</span>
                  </li>
                );
              })}
            </ul>
          ) : <Empty title={kind === "receivable" ? "No customer dues" : "No supplier dues"} icon={Users}>Balances appear when invoices or bills are posted on credit.</Empty>}
          <p className="acc-muted">Aging uses due date (or voucher date) and assumes older invoices are paid first.</p>
        </>
      )}
    </div>
  );
}

/* ----------------------------------------------------------------- Bank */

export function BankTab({ accounts, period, canWrite, refreshKey, onOpenVoucher, onToast }) {
  const banks = (accounts || []).filter((a) => a.sub_type === "bank" && a.is_active !== false);
  const [accountId, setAccountId] = useState(banks[0]?.id || "");
  const [show, setShow] = useState("unreconciled");
  const [drafts, setDrafts] = useState({});
  const [busyLine, setBusyLine] = useState(null);
  const [actionError, setActionError] = useState("");
  const selected = accountId || banks[0]?.id || "";
  const { data, loading, error, reload } = useLoader(
    () => (selected ? accountingApi.bank({ account_id: selected, to_date: period.to, show }) : Promise.resolve(null)),
    [selected, period.to, show, refreshKey],
  );

  const mark = async (line, clear) => {
    const draft = drafts[line.line_id] || {};
    setBusyLine(line.line_id);
    setActionError("");
    try {
      await accountingApi.reconcile(line.line_id, clear ? { reconciled_on: null, bank_reference: null } : {
        reconciled_on: draft.date || line.voucher_date || isoToday(), bank_reference: (draft.ref ?? line.bank_reference ?? "").trim() || null,
      });
      onToast(clear ? "Marked as not cleared" : "Marked as cleared in bank");
      reload();
    } catch (err) {
      setActionError(errorText(err));
    } finally {
      setBusyLine(null);
    }
  };

  if (!banks.length) return <div className="acc-card"><Empty title="No bank accounts" icon={Landmark}>Add an account with sub-type “bank” in Accounts.</Empty></div>;
  return (
    <div className="acc-stack">
      <div className="acc-card">
        <div className="acc-toolbar" style={{ marginBottom: 0 }}>
          <label className="acc-field" style={{ minWidth: 220 }}>
            <span>Account</span>
            <select value={selected} onChange={(e) => setAccountId(Number(e.target.value))}>{banks.map((b) => <option key={b.id} value={b.id}>{b.code} · {b.name}</option>)}</select>
          </label>
          <span className="acc-spacer" />
          <div className="acc-chips">
            <button type="button" className="acc-chip" aria-pressed={show === "unreconciled"} onClick={() => setShow("unreconciled")}>Not cleared</button>
            <button type="button" className="acc-chip" aria-pressed={show === "all"} onClick={() => setShow("all")}>All</button>
          </div>
        </div>
      </div>
      <Alert onRetry={reload}>{error}</Alert>
      <Alert>{actionError}</Alert>
      {loading && !data ? <div className="acc-card"><Loading /></div> : data && (
        <>
          <div className="acc-kpis" style={{ gridTemplateColumns: "repeat(3,minmax(0,1fr))", marginBottom: 0 }}>
            <div className="acc-kpi"><div><small>Balance in books</small><strong>{drCr(data.book_balance)}</strong></div></div>
            <div className="acc-kpi"><div><small>Cleared in bank</small><strong>{drCr(data.cleared_balance)}</strong></div></div>
            <div className="acc-kpi"><div><small>Not yet cleared</small><strong>{drCr(data.uncleared_amount)}</strong></div></div>
          </div>
          <div className="acc-card">
            <p className="acc-muted" style={{ marginTop: 0 }}>Compare with your bank statement up to {formatDate(data.to_date)}. “Cleared in bank” should match the statement closing balance.</p>
            {data.items.length ? (
              <div className="acc-table-wrap">
                <table className="acc-table">
                  <thead><tr><th>Date</th><th>Voucher</th><th className="num">Money in</th><th className="num">Money out</th><th>Bank date</th><th>Bank ref</th><th /></tr></thead>
                  <tbody>{data.items.map((l) => {
                    const draft = drafts[l.line_id] || {};
                    return (
                      <tr key={l.line_id}>
                        <td>{formatDate(l.voucher_date)}</td>
                        <td><button type="button" className="acc-btn small" onClick={() => onOpenVoucher(l.voucher_id)}>{l.voucher_number}</button><div className="acc-muted">{l.party_name || l.narration || ""}</div></td>
                        <td className="num">{num(l.debit) ? money(l.debit) : ""}</td><td className="num">{num(l.credit) ? money(l.credit) : ""}</td>
                        <td>{l.reconciled_on ? formatDate(l.reconciled_on) : <input className="acc-input" style={{ height: 34, width: 150 }} type="date" aria-label="Bank clearing date" min={l.voucher_date} value={draft.date || l.voucher_date} disabled={!canWrite} onChange={(e) => setDrafts((d) => ({ ...d, [l.line_id]: { ...draft, date: e.target.value } }))} />}</td>
                        <td>{l.reconciled_on ? l.bank_reference || "—" : <input className="acc-input" style={{ height: 34, width: 130 }} aria-label="Bank reference" maxLength={100} value={draft.ref ?? ""} disabled={!canWrite} onChange={(e) => setDrafts((d) => ({ ...d, [l.line_id]: { ...draft, ref: e.target.value } }))} />}</td>
                        <td>{canWrite && (l.reconciled_on
                          ? <button type="button" className="acc-btn small" disabled={busyLine === l.line_id} onClick={() => mark(l, true)}>Undo</button>
                          : <button type="button" className="acc-btn small primary" disabled={busyLine === l.line_id} onClick={() => mark(l, false)}><Check size={14} /> Cleared</button>)}</td>
                      </tr>
                    );
                  })}</tbody>
                </table>
              </div>
            ) : <Empty title={show === "unreconciled" ? "Everything is cleared" : "No bank movements"} icon={Landmark} />}
          </div>
        </>
      )}
    </div>
  );
}

/* ------------------------------------------------------------- Accounts */

export function AccountsTab({ accountsState, canWrite, onLedger, onToast }) {
  const { data, loading, error, reload } = accountsState;
  const [showInactive, setShowInactive] = useState(false);
  const [creating, setCreating] = useState(false);
  const [filter, setFilter] = useState("");
  const items = useMemo(() => (data?.items || []).filter((a) => (showInactive || a.is_active) && (!filter || `${a.code} ${a.name}`.toLowerCase().includes(filter.toLowerCase()))), [data, showInactive, filter]);

  const toggleActive = async (account) => {
    try {
      await accountingApi.updateAccount(account.id, { is_active: !account.is_active });
      onToast(account.is_active ? `${account.name} deactivated` : `${account.name} activated`);
      reload();
    } catch (err) {
      onToast(errorText(err));
    }
  };

  return (
    <div className="acc-card">
      <div className="acc-card-head">
        <div><h2>Chart of accounts</h2><p>Balances as of today. Tap an account to open its ledger.</p></div>
        <div className="acc-toolbar" style={{ margin: 0 }}>
          <label className="acc-switch"><input type="checkbox" checked={showInactive} onChange={(e) => setShowInactive(e.target.checked)} /> Show inactive</label>
          {canWrite && <button type="button" className="acc-btn small primary" onClick={() => setCreating(true)}><Plus size={14} /> Add account</button>}
        </div>
      </div>
      <div className="acc-field" style={{ marginBottom: 12 }}><input aria-label="Filter accounts" placeholder="Filter by code or name" value={filter} onChange={(e) => setFilter(e.target.value)} /></div>
      <Alert onRetry={reload}>{error}</Alert>
      {loading && !data ? <Loading rows={8} /> : ACCOUNT_TYPES.map((type) => {
        const group = items.filter((a) => a.account_type === type.key);
        if (!group.length) return null;
        return (
          <div key={type.key} style={{ marginBottom: 14 }}>
            <h3 style={{ fontSize: 13, color: "var(--acc-brand)", margin: "8px 0 4px", textTransform: "uppercase", letterSpacing: ".6px" }}>{type.label}</h3>
            <ul className="acc-list">
              {group.map((a) => (
                <li key={a.id} className="acc-row">
                  <button type="button" className="acc-row" style={{ padding: 0, border: 0 }} onClick={() => onLedger(a.id)}>
                    <span className="acc-avatar" aria-hidden="true" style={{ fontSize: 10 }}>{a.code}</span>
                    <span className="acc-row-main">
                      <strong>{a.name}{!a.is_active && <span className="acc-pill grey" style={{ marginLeft: 6 }}>Inactive</span>}{a.is_system && <Lock size={11} style={{ marginLeft: 6, color: "#a99bc4" }} aria-label="System account" />}</strong>
                      <small>{a.sub_type.replace(/_/g, " ")}{a.description ? ` · ${a.description}` : ""}</small>
                    </span>
                    <span className="acc-row-amt">{money(a.balance)}</span>
                  </button>
                  {canWrite && !a.is_system && <button type="button" className="acc-btn small" onClick={() => toggleActive(a)}>{a.is_active ? "Deactivate" : "Activate"}</button>}
                </li>
              ))}
            </ul>
          </div>
        );
      })}
      {creating && <AccountSheet subTypes={data?.sub_types || {}} accounts={data?.items || []} onClose={() => setCreating(false)} onSaved={(a) => { setCreating(false); onToast(`Account ${a.code} created`); reload(); }} />}
    </div>
  );
}

function AccountSheet({ subTypes, accounts, onClose, onSaved }) {
  const [form, setForm] = useState({ code: "", name: "", account_type: "expense", sub_type: "operating", parent_id: "", description: "" });
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const set = (key) => (e) => setForm((f) => {
    const next = { ...f, [key]: e.target.value };
    if (key === "account_type") next.sub_type = (subTypes[e.target.value] || ["general"]).includes("general") ? "general" : subTypes[e.target.value][0];
    return next;
  });
  const save = async (e) => {
    e.preventDefault();
    setBusy(true);
    setError("");
    try {
      const account = await accountingApi.createAccount({ ...form, parent_id: form.parent_id ? Number(form.parent_id) : null, description: form.description.trim() || null });
      onSaved(account);
    } catch (err) {
      setError(errorText(err));
    } finally {
      setBusy(false);
    }
  };
  return (
    <Sheet title="Add account" onClose={onClose} footer={<><button type="button" className="acc-btn" onClick={onClose} disabled={busy}>Cancel</button><button type="submit" form="acc-account-form" className="acc-btn primary" disabled={busy}>{busy ? "Saving…" : "Create account"}</button></>}>
      <form id="acc-account-form" className="acc-form-grid" onSubmit={save}>
        <div className="wide"><Alert>{error}</Alert></div>
        <Field label="Code" hint="Letters, digits and hyphens. e.g. 6150"><input value={form.code} onChange={set("code")} required maxLength={20} /></Field>
        <Field label="Name"><input value={form.name} onChange={set("name")} required maxLength={160} placeholder="e.g. Packaging material" /></Field>
        <Field label="Type"><select value={form.account_type} onChange={set("account_type")}>{ACCOUNT_TYPES.map((t) => <option key={t.key} value={t.key}>{t.label}</option>)}</select></Field>
        <Field label="Sub-type"><select value={form.sub_type} onChange={set("sub_type")}>{(subTypes[form.account_type] || ["general"]).map((s) => <option key={s} value={s}>{s.replace(/_/g, " ")}</option>)}</select></Field>
        <Field label="Parent (optional)" className="wide"><select value={form.parent_id} onChange={set("parent_id")}><option value="">None</option>{accounts.filter((a) => a.account_type === form.account_type).map((a) => <option key={a.id} value={a.id}>{a.code} · {a.name}</option>)}</select></Field>
        <Field label="Description (optional)" className="wide"><textarea value={form.description} onChange={set("description")} maxLength={500} /></Field>
      </form>
    </Sheet>
  );
}

/* ------------------------------------------------------------- Settings */

export function SettingsTab({ settingsState, role, canWrite, onToast, onSynced }) {
  const { data, loading, error, reload } = settingsState;
  const [form, setForm] = useState(null);
  const [busy, setBusy] = useState(false);
  const [saveError, setSaveError] = useState("");
  const sync = useLoader(() => accountingApi.syncStatus(), []);
  const [syncing, setSyncing] = useState(false);
  const [syncResult, setSyncResult] = useState(null);
  const current = form || (data ? { business_name: data.business_name || "", gstin: data.gstin || "", state_code: data.state_code || "", default_supply: data.default_supply || "intra", lock_date: data.lock_date || "" } : null);
  const set = (key) => (e) => setForm({ ...current, [key]: key === "gstin" ? e.target.value.toUpperCase() : e.target.value });

  const save = async (e) => {
    e.preventDefault();
    setBusy(true);
    setSaveError("");
    try {
      await accountingApi.saveSettings({ ...current, gstin: current.gstin.trim() || null, state_code: current.state_code.trim() || null, lock_date: current.lock_date || null });
      setForm(null);
      onToast("Accounting settings saved");
      reload();
    } catch (err) {
      setSaveError(errorText(err));
    } finally {
      setBusy(false);
    }
  };

  const runSync = async () => {
    setSyncing(true);
    setSyncResult(null);
    try {
      const result = await accountingApi.sync();
      setSyncResult(result);
      sync.reload();
      onSynced();
    } catch (err) {
      setSyncResult({ error: errorText(err) });
    } finally {
      setSyncing(false);
    }
  };

  return (
    <div className="acc-grid acc-grid-2" style={{ alignItems: "start" }}>
      <section className="acc-card">
        <div className="acc-card-head"><div><h2>Business &amp; GST</h2><p>Used on printed vouchers and for the default GST split.</p></div></div>
        <Alert onRetry={reload}>{error}</Alert>
        {loading && !data ? <Loading /> : current && (
          <form className="acc-form-grid" onSubmit={save}>
            <div className="wide"><Alert>{saveError}</Alert></div>
            <Field label="Business name" className="wide"><input value={current.business_name} onChange={set("business_name")} required maxLength={200} disabled={!canWrite} /></Field>
            <Field label="GSTIN"><input value={current.gstin} onChange={set("gstin")} maxLength={15} placeholder="10ABCDE1234F1Z5" disabled={!canWrite} /></Field>
            <Field label="State code" hint="Bihar is 10"><input value={current.state_code} onChange={set("state_code")} maxLength={2} inputMode="numeric" placeholder="10" disabled={!canWrite} /></Field>
            <Field label="Default place of supply" className="wide"><select value={current.default_supply} onChange={set("default_supply")} disabled={!canWrite}><option value="intra">Within state (CGST + SGST)</option><option value="inter">Other state (IGST)</option></select></Field>
            <Field label="Books locked up to" hint={role === "owner" ? "No entry can be posted or reversed on or before this date." : "Only the owner can change the lock date."} className="wide">
              <input type="date" value={current.lock_date} onChange={set("lock_date")} disabled={!canWrite || role !== "owner"} />
            </Field>
            {canWrite && <div className="wide"><button type="submit" className="acc-btn primary block" disabled={busy || !form}>{busy ? "Saving…" : "Save settings"}</button></div>}
            {data?.updated_at && <p className="acc-muted wide" style={{ margin: 0 }}>Last updated {formatDate(String(data.updated_at).slice(0, 10))}{data.updated_by_email ? ` by ${data.updated_by_email}` : ""}.</p>}
          </form>
        )}
      </section>
      <section className="acc-card">
        <div className="acc-card-head">
          <div><h2>Sync from store operations</h2><p>Posts orders, cancellations, captured payments, refunds and goods receipts once each.</p></div>
          <button type="button" className="acc-icon-btn" aria-label="Refresh pending count" onClick={sync.reload}><RefreshCw size={16} /></button>
        </div>
        <Alert onRetry={sync.reload}>{sync.error}</Alert>
        {sync.loading && !sync.data ? <Loading rows={3} /> : sync.data && (
          <ul className="acc-list">
            {[["Orders to post as sales", sync.data.orders], ["Cancellations to post as credit notes", sync.data.order_cancellations], ["Captured payments to post as receipts", sync.data.payments], ["Refunds to post", sync.data.refunds], ["Goods receipts to post to inventory", sync.data.goods_receipts]].map(([label, count]) => (
              <li key={label} className="acc-row"><span className="acc-row-main"><strong style={{ fontWeight: 600 }}>{label}</strong></span><span className={`acc-pill ${count ? "orange" : "green"}`}>{count}</span></li>
            ))}
          </ul>
        )}
        {syncResult?.error && <Alert>{syncResult.error}</Alert>}
        {syncResult && !syncResult.error && (
          <Alert tone={syncResult.errors?.length ? "warn" : "ok"}>
            Posted {syncResult.orders} sales, {syncResult.order_cancellations} cancellations, {syncResult.payments} receipts, {syncResult.refunds} refunds and {syncResult.goods_receipts} goods receipts.
            {syncResult.skipped_locked > 0 && <> {syncResult.skipped_locked} skipped because the books are locked.</>}
            {syncResult.errors?.length > 0 && <ul style={{ margin: "6px 0 0", paddingLeft: 18 }}>{syncResult.errors.slice(0, 8).map((e) => <li key={e}>{e}</li>)}</ul>}
          </Alert>
        )}
        {canWrite && <button type="button" className="acc-btn primary block" style={{ marginTop: 12 }} onClick={runSync} disabled={syncing || !sync.data?.pending_total}>{syncing ? "Posting…" : sync.data?.pending_total ? `Post ${sync.data.pending_total} pending records` : "Everything is posted"}</button>}
        <p className="acc-muted">Order prices are treated as GST-inclusive using each product's tax rate, with the default place of supply. Sync is safe to run again; records already posted are skipped.</p>
      </section>
    </div>
  );
}
