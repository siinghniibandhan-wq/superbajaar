import React, { useCallback, useEffect, useMemo, useState } from 'react';

/* Connected ERP screens. Every action here calls the backend workflow APIs, so a step taken in one module
   (for example a GRN quality check) immediately changes stock, accounting and the next module's worklist. */

const API = (import.meta.env.VITE_API_BASE_URL || 'https://superappkart.duckdns.org/api').replace(/\/$/, '');
const API_PATH = path => API.endsWith('/api') ? API + path : API + '/api' + path;
const money = n => '₹' + Number(n || 0).toLocaleString('en-IN', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
const label = s => String(s || '').replace(/_/g, ' ');
const when = d => d ? new Date(d).toLocaleDateString('en-IN') : '—';

function useErp() {
  const [busy, setBusy] = useState(false), [error, setError] = useState(''), [notice, setNotice] = useState('');
  const call = useCallback(async (path, options = {}) => {
    const token = localStorage.getItem('sb_admin_token') || '';
    if (!token) throw Error('Sign in through Users & Access first.');
    const headers = { Authorization: 'Bearer ' + token, ...(options.body ? { 'Content-Type': 'application/json' } : {}) };
    const r = await fetch(API_PATH(path), { method: options.method || 'GET', headers, body: options.body ? JSON.stringify(options.body) : undefined });
    const j = await r.json().catch(() => ({}));
    if (!r.ok) throw Error(typeof j.detail === 'string' ? j.detail : Array.isArray(j.detail) ? j.detail.map(d => d.msg).join('; ') : 'Request failed (' + r.status + ')');
    return j;
  }, []);
  const act = async (fn, ok) => {
    setBusy(true); setError(''); setNotice('');
    try { const j = await fn(); if (ok) setNotice(typeof ok === 'function' ? ok(j) : ok); return j || true; }
    catch (e) { setError(e.message || 'Action failed'); return null; }
    finally { setBusy(false); }
  };
  return { call, busy, error, notice, act, setError, setNotice };
}

function Feedback({ error, notice }) {
  return <>{error && <p className="review-feedback error" role="alert">{error}</p>}{notice && <p className="review-feedback" role="status">{notice}</p>}</>;
}
function Badge({ s }) { return <span className="status-badge">{label(s)}</span>; }
function Field({ name, children }) { return <label className="erp-field"><span>{name}</span>{children}</label>; }

/* ------------------------------------------------------------------ PURCHASE */

const NEXT_LABEL = {
  approve: 'Approve the requisition', quote: 'Record the vendor quotation', select_quote: 'Choose a quotation',
  make_po: 'Convert to purchase order', ship: 'Vendor dispatch', receive: 'Receive goods (GRN)', inspect: 'Quality inspection',
  bill: 'Enter vendor bill', approve_bill: 'Approve vendor bill', pay: 'Pay vendor', done: 'Complete', closed: 'Closed'
};

function QuoteForm({ doc, run, call, vendors }) {
  const [prices, setPrices] = useState(() => Object.fromEntries(doc.lines.map(l => [l.variant_id, Number(l.unit_price) > 0 ? l.unit_price : ''])));
  const [vendorId, setVendorId] = useState(String(doc.vendor_id));
  const ready = doc.lines.every(l => Number(prices[l.variant_id]) >= 0 && prices[l.variant_id] !== '');
  const items = doc.lines.map(l => ({ variant_id: l.variant_id, quantity: l.ordered, unit_price: Number(prices[l.variant_id]) }));
  const primary = Number(vendorId) === Number(doc.vendor_id);
  return <div className="erp-form">
    <p className="muted-note">Enter the rate the vendor quoted for each line. {doc.quotations.length > 0 ? 'You can add another vendor’s quote to compare.' : ''}</p>
    {vendors.length > 1 && doc.quotations.length > 0 && <Field name="Quote from"><select value={vendorId} onChange={e => setVendorId(e.target.value)}>{vendors.map(v => <option key={v.id} value={v.id}>{v.name}</option>)}</select></Field>}
    {doc.lines.map(l => <Field key={l.variant_id} name={`${l.name} × ${l.ordered} — rate (₹)`}><input type="number" min="0" step="0.01" value={prices[l.variant_id]} onChange={e => setPrices(p => ({ ...p, [l.variant_id]: e.target.value }))} /></Field>)}
    <button className="primary-cta" disabled={!ready} onClick={() => run(() => primary && doc.quotations.length === 0
      ? call(`/admin/procurements/${doc.id}/quotation`, { method: 'POST', body: { status: 'quoted', items } })
      : call(`/admin/procurements/${doc.id}/quotations`, { method: 'POST', body: { vendor_id: Number(vendorId), items } }), 'Quotation recorded.')}>Save quotation</button>
  </div>;
}

function ShipForm({ doc, run, call }) {
  const [qty, setQty] = useState(() => Object.fromEntries(doc.lines.map(l => [l.variant_id, l.to_ship])));
  const [carrier, setCarrier] = useState(''), [track, setTrack] = useState('');
  const items = doc.lines.filter(l => Number(qty[l.variant_id]) > 0).map(l => ({ variant_id: l.variant_id, quantity: Number(qty[l.variant_id]) }));
  return <div className="erp-form">
    <p className="muted-note">Record what the vendor has sent so the store can receive it against this order.</p>
    {doc.lines.filter(l => l.to_ship > 0).map(l => <Field key={l.variant_id} name={`${l.name} — sending (max ${l.to_ship})`}><input type="number" min="0" max={l.to_ship} value={qty[l.variant_id]} onChange={e => setQty(q => ({ ...q, [l.variant_id]: e.target.value }))} /></Field>)}
    <Field name="Carrier"><input value={carrier} onChange={e => setCarrier(e.target.value)} /></Field>
    <Field name="Tracking / LR number"><input value={track} onChange={e => setTrack(e.target.value)} /></Field>
    <button className="primary-cta" disabled={!items.length} onClick={() => run(() => call(`/erp/purchase/orders/${doc.id}/vendor-shipment`, { method: 'POST', body: { items, carrier, tracking_reference: track } }), 'Vendor dispatch recorded. Goods can now be received.')}>Record dispatch</button>
  </div>;
}

function ReceiveForm({ doc, run, call, warehouses }) {
  const active = warehouses.filter(w => w.active !== false);
  const [wid, setWid] = useState(active[0] ? String(active[0].id) : '');
  const wh = active.find(w => String(w.id) === wid);
  const locations = Array.isArray(wh?.locations) ? wh.locations : [];
  const [rows, setRows] = useState(() => Object.fromEntries(doc.lines.map(l => [l.variant_id, { qty: l.awaiting_receipt, location: '' }])));
  const items = doc.lines.filter(l => Number(rows[l.variant_id]?.qty) > 0).map(l => ({ variant_id: l.variant_id, quantity: Number(rows[l.variant_id].qty), location: rows[l.variant_id].location || '' }));
  const set = (id, patch) => setRows(r => ({ ...r, [id]: { ...r[id], ...patch } }));
  return <div className="erp-form">
    <p className="muted-note">Count what arrived. Stock is only added after the quality check, into the bin you choose here.</p>
    <Field name="Receive into warehouse"><select value={wid} onChange={e => setWid(e.target.value)}>{active.map(w => <option key={w.id} value={w.id}>{w.name}</option>)}</select></Field>
    {doc.lines.filter(l => l.awaiting_receipt > 0).map(l => <div className="erp-row" key={l.variant_id}>
      <Field name={`${l.name} — received (expected ${l.awaiting_receipt})`}><input type="number" min="0" max={l.awaiting_receipt} value={rows[l.variant_id].qty} onChange={e => set(l.variant_id, { qty: e.target.value })} /></Field>
      <Field name="Bin / location">{locations.length ? <select value={rows[l.variant_id].location} onChange={e => set(l.variant_id, { location: e.target.value })}><option value="">Unassigned</option>{locations.map(x => <option key={x} value={x}>{x}</option>)}</select> : <input placeholder="Optional" value={rows[l.variant_id].location} onChange={e => set(l.variant_id, { location: e.target.value })} />}</Field>
    </div>)}
    <button className="primary-cta" disabled={!items.length || !wid} onClick={() => run(() => call(`/admin/procurements/${doc.id}/receipts`, { method: 'POST', body: { warehouse_id: Number(wid), items } }), 'GRN created. It is now waiting for quality inspection.')}>Create GRN</button>
  </div>;
}

function InspectForm({ doc, receipt, run, call }) {
  const [acc, setAcc] = useState(() => Object.fromEntries(receipt.items.map(i => [i.variant_id, i.quantity])));
  const [note, setNote] = useState('');
  const names = Object.fromEntries(doc.lines.map(l => [l.variant_id, l.name]));
  const accepted = receipt.items.map(i => ({ variant_id: Number(i.variant_id), quantity: Math.min(Math.max(Number(acc[i.variant_id]) || 0, 0), Number(i.quantity)) }));
  const rejected = receipt.items.map((i, n) => ({ variant_id: Number(i.variant_id), quantity: Number(i.quantity) - accepted[n].quantity }));
  const rejectedTotal = rejected.reduce((s, x) => s + x.quantity, 0);
  return <div className="erp-form">
    <p className="muted-note">{receipt.reference}: accepted goods go to stock in their bin. Rejected goods are returned to the vendor and a debit note is raised automatically.</p>
    {receipt.items.map(i => <Field key={i.variant_id} name={`${names[i.variant_id] || 'Item ' + i.variant_id} — accepted out of ${i.quantity}`}><input type="number" min="0" max={i.quantity} value={acc[i.variant_id]} onChange={e => setAcc(a => ({ ...a, [i.variant_id]: e.target.value }))} /></Field>)}
    <Field name="Inspection note"><input value={note} onChange={e => setNote(e.target.value)} placeholder="Optional" /></Field>
    <button className="primary-cta" onClick={() => run(() => call(`/admin/receipts/${receipt.id}/inspect`, { method: 'POST', body: { accepted_items: accepted, rejected_items: rejected, note } }),
      j => j.debit_note_reference ? `Inspection saved. Return ${j.vendor_return_reference} and debit note ${j.debit_note_reference} created for ${rejectedTotal} rejected unit(s).` : 'Inspection saved. Accepted stock is now in the warehouse.')}>
      Complete inspection{rejectedTotal ? ` (${rejectedTotal} rejected)` : ''}</button>
  </div>;
}

function BillForm({ doc, run, call }) {
  const suggested = doc.lines.reduce((s, l) => s + Number(l.unit_price) * l.accepted, 0);
  const [no, setNo] = useState(''), [amount, setAmount] = useState(suggested ? suggested.toFixed(2) : ''), [tax, setTax] = useState('0'), [due, setDue] = useState('');
  return <div className="erp-form">
    <p className="muted-note">Convert the vendor’s invoice into a bill. The amount is suggested from accepted quantities at the agreed rate.</p>
    <Field name="Vendor invoice number"><input value={no} onChange={e => setNo(e.target.value)} /></Field>
    <Field name="Amount before tax (₹)"><input type="number" min="0" step="0.01" value={amount} onChange={e => setAmount(e.target.value)} /></Field>
    <Field name="GST (₹)"><input type="number" min="0" step="0.01" value={tax} onChange={e => setTax(e.target.value)} /></Field>
    <Field name="Due date"><input type="date" value={due} onChange={e => setDue(e.target.value)} /></Field>
    <button className="primary-cta" disabled={!no.trim() || amount === ''} onClick={() => run(() => call(`/admin/procurements/${doc.id}/bills`, { method: 'POST', body: { vendor_invoice_number: no.trim(), amount: Number(amount), tax_total: Number(tax || 0), due_date: due || null } }), 'Bill entered. It now needs approval.')}>Create bill</button>
  </div>;
}

function BillActions({ doc, run, call, only }) {
  const bills = doc.bills.filter(b => b.status !== 'rejected' && (!only || only.includes(b.status)));
  return <div className="erp-form">{bills.map(b => {
    const net = Number(b.amount) + Number(b.tax_total) - Number(b.debit_note_total || 0);
    const left = Math.max(net - Number(b.paid_total || 0), 0);
    return <div className="erp-bill" key={b.id}>
      <b>{b.reference}</b> <Badge s={b.status} /> <small>{b.vendor_invoice_number} · payable {money(net)} · paid {money(b.paid_total)}</small>
      {b.status === 'submitted' && <div className="erp-actions"><button className="primary-cta" onClick={() => run(() => call(`/admin/supplier-bills/${b.id}?status=approved`, { method: 'PATCH' }), 'Bill approved.')}>Approve</button><button className="outline-action" onClick={() => run(() => call(`/admin/supplier-bills/${b.id}?status=rejected`, { method: 'PATCH' }), 'Bill rejected.')}>Reject</button></div>}
      {['approved', 'partially_paid'].includes(b.status) && left > 0 && <button className="primary-cta" onClick={() => { const raw = window.prompt('Outstanding ' + money(left) + '. Amount to pay:', left.toFixed(2)); if (raw === null) return; const a = Number(raw); if (!(a > 0)) return; run(() => call(`/admin/supplier-bills/${b.id}/payments`, { method: 'POST', body: { amount: a, method: 'bank' } }), 'Payment recorded.'); }}>Pay vendor</button>}
    </div>;
  })}</div>;
}

function QuoteChoices({ doc, run, call }) {
  return <div className="erp-form"><p className="muted-note">Several quotations are on file. Choose the one to proceed with.</p>
    {doc.quotations.map(q => <div className="erp-bill" key={q.id}><b>{q.vendor_name}</b> <small>{money(q.total_value)} · {q.status ? label(q.status) : ''}</small>
      <button className="primary-cta" onClick={() => run(() => call(`/admin/procurements/${doc.id}/quotations/${q.id}/select`, { method: 'POST' }), 'Quotation selected.')}>Select</button></div>)}
  </div>;
}

function NextAction({ doc, ctx }) {
  const { run, call, warehouses, vendors } = ctx;
  const a = doc.next_action;
  const pendingQc = doc.receipts.find(r => r.status === 'inspection');
  if (a === 'approve') return <div className="erp-actions"><button className="primary-cta" onClick={() => run(() => call(`/admin/procurements/${doc.id}/approval`, { method: 'PATCH', body: { decision: 'approved' } }), 'Requisition approved and sent for quotation.')}>Approve</button><button className="outline-action" onClick={() => run(() => call(`/admin/procurements/${doc.id}/approval`, { method: 'PATCH', body: { decision: 'rejected' } }), 'Requisition rejected.')}>Reject</button></div>;
  if (a === 'quote') return <QuoteForm doc={doc} {...ctx} />;
  if (a === 'select_quote') return <><QuoteChoices doc={doc} {...ctx} /><QuoteForm doc={doc} {...ctx} /></>;
  if (a === 'make_po') return <button className="primary-cta" onClick={() => run(() => call(`/admin/procurements/${doc.id}/purchase-order`, { method: 'POST' }), j => 'Purchase order ' + j.purchase_order_reference + ' created.')}>Convert to purchase order</button>;
  if (a === 'ship') return <ShipForm doc={doc} {...ctx} />;
  if (a === 'receive') return <ReceiveForm doc={doc} {...ctx} />;
  if (a === 'inspect' && pendingQc) return <InspectForm doc={doc} receipt={pendingQc} {...ctx} />;
  if (a === 'bill') return <BillForm doc={doc} {...ctx} />;
  if (a === 'approve_bill') return <BillActions doc={doc} only={['submitted']} {...ctx} />;
  if (a === 'pay') return <BillActions doc={doc} only={['approved', 'partially_paid']} {...ctx} />;
  return <p className="muted-note">{a === 'done' ? 'This purchase is complete.' : 'Nothing further to do.'}</p>;
}

function NewRequisition({ vendors, onCreate, call, act }) {
  const [vendorId, setVendorId] = useState(''), [expected, setExpected] = useState(''), [lines, setLines] = useState([{ variant_id: '', quantity: 1 }]), [options, setOptions] = useState([]);
  useEffect(() => { (async () => { try { const j = await call('/admin/inventory/stock-levels'); const seen = new Map(); (j.items || []).forEach(r => { if (!seen.has(r.variant_id)) seen.set(r.variant_id, { id: r.variant_id, name: r.name + (r.sku ? ' · ' + r.sku : '') }); }); setOptions([...seen.values()]); } catch { } })(); }, []);
  const clean = lines.filter(l => l.variant_id && Number(l.quantity) > 0).map(l => ({ variant_id: Number(l.variant_id), quantity: Number(l.quantity) }));
  const setLine = (i, patch) => setLines(ls => ls.map((l, n) => n === i ? { ...l, ...patch } : l));
  return <div className="erp-form panel">
    <h3>New purchase requisition</h3>
    <Field name="Vendor"><select value={vendorId} onChange={e => setVendorId(e.target.value)}><option value="">Select vendor</option>{vendors.filter(v => v.status === 'active').map(v => <option key={v.id} value={v.id}>{v.name}</option>)}</select></Field>
    <Field name="Expected delivery"><input type="date" value={expected} onChange={e => setExpected(e.target.value)} /></Field>
    {lines.map((l, i) => <div className="erp-row" key={i}>
      <Field name="Product"><select value={l.variant_id} onChange={e => setLine(i, { variant_id: e.target.value })}><option value="">Select product</option>{options.map(o => <option key={o.id} value={o.id}>{o.name}</option>)}</select></Field>
      <Field name="Quantity"><input type="number" min="1" value={l.quantity} onChange={e => setLine(i, { quantity: e.target.value })} /></Field>
      {lines.length > 1 && <button type="button" className="outline-action" onClick={() => setLines(ls => ls.filter((_, n) => n !== i))}>Remove</button>}
    </div>)}
    <div className="erp-actions"><button type="button" className="outline-action" onClick={() => setLines(ls => [...ls, { variant_id: '', quantity: 1 }])}>+ Add line</button>
      <button className="primary-cta" disabled={!vendorId || !clean.length} onClick={async () => { const ok = await act(() => call('/admin/procurements', { method: 'POST', body: { vendor_id: Number(vendorId), items: clean, expected_date: expected || null } }), j => 'Requisition ' + j.reference + ' created and waiting for approval.'); if (ok) { setLines([{ variant_id: '', quantity: 1 }]); onCreate(); } }}>Create requisition</button></div>
  </div>;
}

function PurchaseDocs() {
  const { call, busy, error, notice, act } = useErp();
  const [docs, setDocs] = useState([]), [vendors, setVendors] = useState([]), [warehouses, setWarehouses] = useState([]);
  const [filter, setFilter] = useState('active'), [openId, setOpenId] = useState(null), [showNew, setShowNew] = useState(false);
  const load = () => act(async () => { const [d, v, w] = await Promise.all([call('/erp/purchase/documents'), call('/erp/vendors'), call('/admin/warehouses')]); setDocs(d.items || []); setVendors(v.items || []); setWarehouses(w.items || []); });
  useEffect(() => { load(); }, []);
  const run = async (fn, ok) => { const r = await act(fn, ok); if (r) { await act(async () => { const d = await call('/erp/purchase/documents'); setDocs(d.items || []); const w = await call('/admin/warehouses'); setWarehouses(w.items || []); }); } };
  const rows = docs.filter(d => filter === 'all' ? true : filter === 'active' ? !['done', 'closed'].includes(d.next_action) : ['done', 'closed'].includes(d.next_action));
  const ctx = { run, call, warehouses, vendors };
  return <section className="panel operations-manager">
    <div className="panel-heading"><div><h2>Purchase requisitions & orders</h2><p>One record per purchase, from request to payment. The highlighted action is what needs doing next.</p></div>
      <div className="moderation-controls"><select aria-label="Filter" value={filter} onChange={e => setFilter(e.target.value)}><option value="active">In progress</option><option value="closed">Completed</option><option value="all">Everything</option></select>
        <button className="outline-action" onClick={load} disabled={busy}>{busy ? 'Working…' : '↻ Refresh'}</button><button className="primary-cta" onClick={() => setShowNew(s => !s)}>{showNew ? 'Close' : '+ New requisition'}</button></div></div>
    <Feedback error={error} notice={notice} />
    {showNew && <NewRequisition vendors={vendors} call={call} act={act} onCreate={() => { setShowNew(false); load(); }} />}
    {!busy && !rows.length && <p className="muted-note">Nothing here yet. Create a requisition to start a purchase.</p>}
    {rows.map(d => <article key={d.id} className="pipe-card">
      <header><div><b>{d.pr_reference}</b>{d.po_reference && <span className="pipe-po"> → {d.po_reference}</span>}
        <small>{d.vendor_name} · {d.lines.length} item(s) · order value {money(d.order_value)} · expected {when(d.expected_date)}</small></div>
        <div className="erp-actions"><Badge s={d.status} /><button className="outline-action" onClick={() => setOpenId(openId === d.id ? null : d.id)}>{openId === d.id ? 'Hide' : 'Details'}</button></div></header>
      <p className="pipe-next"><b>Next:</b> {NEXT_LABEL[d.next_action] || d.next_action}</p>
      {openId === d.id && <div className="user-table-wrap"><table className="user-table"><thead><tr><th>Item</th><th>Rate</th><th>Ordered</th><th>Dispatched</th><th>Received</th><th>Accepted</th><th>Rejected</th></tr></thead>
        <tbody>{d.lines.map(l => <tr key={l.variant_id}><td>{l.name}<small>{l.sku}</small></td><td>{Number(l.unit_price) ? money(l.unit_price) : '—'}</td><td>{l.ordered}</td><td>{l.dispatched}</td><td>{l.received}</td><td>{l.accepted}</td><td>{l.rejected}</td></tr>)}</tbody></table>
        <p className="muted-note">{d.quotations.length} quotation(s) · {d.receipts.map(r => r.reference + ' (' + label(r.status) + ')').join(', ') || 'no GRN'} · {d.bills.map(b => b.reference + ' (' + label(b.status) + ')').join(', ') || 'no bill'}
          {d.vendor_returns.length > 0 && ' · returns: ' + d.vendor_returns.map(r => r.reference + ' (' + label(r.status) + ')').join(', ')}
          {d.debit_notes.length > 0 && ' · debit notes: ' + d.debit_notes.map(n => n.reference + ' ' + money(Number(n.amount) + Number(n.tax_total))).join(', ')}</p></div>}
      <NextAction doc={d} ctx={ctx} />
    </article>)}
  </section>;
}

function VendorForm({ initial, onSave, onCancel }) {
  const [f, setF] = useState(initial || { name: '', email: '', phone: '', gstin: '', pan: '', contact_person: '', state_code: '', address: '', payment_terms_days: 0 });
  const set = k => e => setF(x => ({ ...x, [k]: e.target.value }));
  return <form className="erp-form panel" onSubmit={e => { e.preventDefault(); onSave({ ...f, payment_terms_days: Number(f.payment_terms_days || 0) }); }}>
    <h3>{initial ? 'Edit vendor' : 'Register vendor'}</h3>
    <Field name="Vendor name"><input required value={f.name} onChange={set('name')} /></Field>
    <Field name="Email (the vendor signs in with this)"><input required type="email" value={f.email} onChange={set('email')} disabled={!!initial} /></Field>
    <Field name="Phone"><input value={f.phone || ''} onChange={set('phone')} /></Field>
    <Field name="Contact person"><input value={f.contact_person || ''} onChange={set('contact_person')} /></Field>
    <Field name="GSTIN"><input value={f.gstin || ''} onChange={set('gstin')} /></Field>
    <Field name="PAN"><input value={f.pan || ''} onChange={set('pan')} /></Field>
    <Field name="State code (e.g. 27)"><input value={f.state_code || ''} onChange={set('state_code')} /></Field>
    <Field name="Address"><input value={f.address || ''} onChange={set('address')} /></Field>
    <Field name="Payment terms (days)"><input type="number" min="0" max="365" value={f.payment_terms_days} onChange={set('payment_terms_days')} /></Field>
    <div className="erp-actions"><button className="primary-cta" type="submit">Save vendor</button><button type="button" className="outline-action" onClick={onCancel}>Cancel</button></div>
  </form>;
}

function ErpVendors() {
  const { call, busy, error, notice, act } = useErp();
  const [items, setItems] = useState([]), [search, setSearch] = useState(''), [form, setForm] = useState(null);
  const load = (q = search) => act(async () => { const j = await call('/erp/vendors?search=' + encodeURIComponent(q)); setItems(j.items || []); });
  useEffect(() => { load(''); }, []);
  async function save(body) {
    const editing = form && form.id;
    const ok = await act(() => editing ? call('/erp/vendors/' + form.id, { method: 'PUT', body: { ...body, email: undefined } }) : call('/admin/vendors', { method: 'POST', body }), editing ? 'Vendor updated.' : 'Vendor registered.');
    if (ok) { setForm(null); load(); }
  }
  const addressText = v => typeof v.address === 'object' && v.address ? (v.address.text || '') : (v.address || '');
  return <section className="panel operations-manager">
    <div className="panel-heading"><div><h2>Vendors</h2><p>Vendor master used by requisitions, purchase orders, bills and debit notes.</p></div>
      <div className="moderation-controls"><input aria-label="Search vendors" placeholder="Search name, email, GSTIN" value={search} onChange={e => setSearch(e.target.value)} onKeyDown={e => e.key === 'Enter' && load()} /><button className="outline-action" onClick={() => load()} disabled={busy}>Search</button><button className="primary-cta" onClick={() => setForm({})}>+ Register vendor</button></div></div>
    <Feedback error={error} notice={notice} />
    {form && <VendorForm initial={form.id ? { ...form, address: addressText(form) } : null} onSave={save} onCancel={() => setForm(null)} />}
    <div className="user-table-wrap"><table className="user-table"><thead><tr><th>Vendor</th><th>Contact</th><th>GSTIN</th><th>Terms</th><th>POs</th><th>Payable</th><th>Unapplied debit notes</th><th>Status</th><th /></tr></thead>
      <tbody>{items.map(v => <tr key={v.id}><td>{v.name}<small>{v.contact_person}</small></td><td>{v.email}<small>{v.phone}</small></td><td>{v.gstin || '—'}</td><td>{v.payment_terms_days}d</td><td>{v.purchase_orders}</td><td>{money(v.payable)}</td><td>{money(v.unapplied_debit_notes)}</td><td><Badge s={v.status} /></td>
        <td className="user-actions"><button className="outline-action" onClick={() => setForm(v)}>Edit</button><button className="outline-action" onClick={async () => { const ok = await act(() => call('/erp/vendors/' + v.id, { method: 'PUT', body: { status: v.status === 'active' ? 'inactive' : 'active' } }), 'Vendor status updated.'); if (ok) load(); }}>{v.status === 'active' ? 'Deactivate' : 'Activate'}</button></td></tr>)}</tbody></table></div>
    {!busy && !items.length && <p className="muted-note">No vendors yet. Register your first vendor to start purchasing.</p>}
  </section>;
}

function PurchaseReturns() {
  const { call, busy, error, notice, act } = useErp();
  const [returns, setReturns] = useState([]), [notes, setNotes] = useState([]);
  const load = () => act(async () => { const [r, n] = await Promise.all([call('/erp/purchase/vendor-returns'), call('/erp/purchase/debit-notes')]); setReturns(r.items || []); setNotes(n.items || []); });
  useEffect(() => { load(); }, []);
  return <section className="panel operations-manager">
    <div className="panel-heading"><div><h2>Vendor returns & debit notes</h2><p>Goods rejected at quality inspection are sent back here, with a debit note that reduces what you owe the vendor.</p></div><button className="outline-action" onClick={load} disabled={busy}>↻ Refresh</button></div>
    <Feedback error={error} notice={notice} />
    <h3>Returns to vendors</h3>
    <div className="user-table-wrap"><table className="user-table"><thead><tr><th>Return</th><th>Vendor</th><th>PO</th><th>Items</th><th>Debit note</th><th>Status</th><th /></tr></thead>
      <tbody>{returns.map(r => <tr key={r.id}><td>{r.reference}<small>{r.receipt_reference}</small></td><td>{r.vendor_name}</td><td>{r.purchase_order_reference || '—'}</td><td>{(r.items || []).reduce((s, i) => s + Number(i.quantity || 0), 0)} unit(s)</td><td>{r.debit_note_reference || '—'}<small>{r.debit_amount ? money(Number(r.debit_amount) + Number(r.debit_tax || 0)) : ''}</small></td><td><Badge s={r.status} /></td>
        <td>{r.status === 'pending_dispatch' && <button className="primary-cta" onClick={async () => { const carrier = window.prompt('Carrier / courier for the return:'); if (carrier === null) return; const tracking = window.prompt('Tracking / LR number (optional):') || ''; const ok = await act(() => call(`/erp/purchase/vendor-returns/${r.id}/dispatch`, { method: 'POST', body: { carrier, tracking_reference: tracking } }), 'Return marked as sent to vendor.'); if (ok) load(); }}>Mark sent</button>}</td></tr>)}</tbody></table></div>
    {!busy && !returns.length && <p className="muted-note">No rejected goods so far.</p>}
    <h3>Debit notes</h3>
    <div className="user-table-wrap"><table className="user-table"><thead><tr><th>Debit note</th><th>Vendor</th><th>PO</th><th>Amount</th><th>GST</th><th>Applied to bill</th><th>Status</th></tr></thead>
      <tbody>{notes.map(n => <tr key={n.id}><td>{n.reference}<small>{when(n.created_at)}</small></td><td>{n.vendor_name}</td><td>{n.purchase_order_reference || '—'}</td><td>{money(n.amount)}</td><td>{money(n.tax_total)}</td><td>{n.bill_reference || 'Not yet applied'}</td><td><Badge s={n.status} /></td></tr>)}</tbody></table></div>
  </section>;
}

function ErpPayables() {
  const { call, busy, error, notice, act } = useErp();
  const [items, setItems] = useState([]);
  const load = () => act(async () => { const j = await call('/erp/accounting/payables'); setItems(j.items || []); });
  useEffect(() => { load(); }, []);
  const run = async (fn, ok) => { const r = await act(fn, ok); if (r) load(); };
  return <section className="panel operations-manager">
    <div className="panel-heading"><div><h2>Vendor bills & payments</h2><p>Bills come from purchase orders after goods pass inspection. Debit notes are deducted automatically.</p></div><button className="outline-action" onClick={load} disabled={busy}>↻ Refresh</button></div>
    <Feedback error={error} notice={notice} />
    <div className="user-table-wrap"><table className="user-table"><thead><tr><th>Bill</th><th>Vendor</th><th>PO</th><th>Bill amount</th><th>Debit notes</th><th>Paid</th><th>Outstanding</th><th>Due</th><th>Status</th><th /></tr></thead>
      <tbody>{items.map(b => <tr key={b.id}><td>{b.reference}<small>{b.vendor_invoice_number}</small></td><td>{b.vendor_name}</td><td>{b.purchase_order_reference || '—'}</td><td>{money(Number(b.amount) + Number(b.tax_total))}</td><td>{money(b.debit_note_total)}</td><td>{money(b.paid_total)}</td><td>{money(b.outstanding)}</td><td>{when(b.due_date)}</td><td><Badge s={b.status} /></td>
        <td className="user-actions">{b.status === 'submitted' && <><button className="primary-cta" onClick={() => run(() => call(`/admin/supplier-bills/${b.id}?status=approved`, { method: 'PATCH' }), 'Bill approved.')}>Approve</button><button className="outline-action" onClick={() => run(() => call(`/admin/supplier-bills/${b.id}?status=rejected`, { method: 'PATCH' }), 'Bill rejected.')}>Reject</button></>}
          {['approved', 'partially_paid'].includes(b.status) && Number(b.outstanding) > 0 && <button className="primary-cta" onClick={() => { const raw = window.prompt('Outstanding ' + money(b.outstanding) + '. Amount to pay:', Number(b.outstanding).toFixed(2)); if (raw === null) return; const a = Number(raw); if (!(a > 0)) return; run(() => call(`/admin/supplier-bills/${b.id}/payments`, { method: 'POST', body: { amount: a, method: 'bank' } }), 'Payment recorded.'); }}>Pay</button>}</td></tr>)}</tbody></table></div>
    {!busy && !items.length && <p className="muted-note">No vendor bills yet.</p>}
  </section>;
}

export function ErpPurchase({ tab }) {
  if (tab === 'vendors') return <ErpVendors />;
  if (tab === 'returns') return <PurchaseReturns />;
  if (tab === 'supplier-payments') return <ErpPayables />;
  return <PurchaseDocs />;
}

/* ------------------------------------------------------------------ SALES */

const ORDER_FLOW = ['placed', 'confirmed', 'processing', 'packed', 'shipped', 'out_for_delivery', 'delivered'];
const ORDER_STEP_LABEL = { confirmed: 'Confirm order', processing: 'Start processing', packed: 'Mark packed', shipped: 'Mark dispatched', out_for_delivery: 'Out for delivery', delivered: 'Mark delivered' };

export function ErpSalesOrders() {
  const { call, busy, error, notice, act } = useErp();
  const [items, setItems] = useState([]), [counts, setCounts] = useState({}), [status, setStatus] = useState(''), [search, setSearch] = useState('');
  const load = (s = status, q = search) => act(async () => { const j = await call('/erp/sales/orders?status=' + encodeURIComponent(s) + '&search=' + encodeURIComponent(q)); setItems(j.items || []); setCounts(j.counts || {}); });
  useEffect(() => { load(status); }, [status]);
  const move = async (o, target) => { const ok = await act(() => call('/admin/orders/' + o.id, { method: 'PATCH', body: { status: target } }), target === 'cancelled' ? 'Order cancelled and stock released.' : 'Order moved to ' + label(target) + '.'); if (ok) load(); };
  return <section className="panel operations-manager">
    <div className="panel-heading"><div><h2>Website orders</h2><p>Stock is reserved at checkout, leaves the warehouse when packed, a shipment appears in Logistics, and revenue is booked on delivery.</p></div>
      <div className="moderation-controls"><input placeholder="Search order or customer" value={search} onChange={e => setSearch(e.target.value)} onKeyDown={e => e.key === 'Enter' && load()} /><button className="outline-action" onClick={() => load()} disabled={busy}>↻</button></div></div>
    <div className="erp-chips"><button className={!status ? 'selected' : ''} onClick={() => setStatus('')}>All</button>{[...ORDER_FLOW, 'cancelled'].map(s => <button key={s} className={status === s ? 'selected' : ''} onClick={() => setStatus(s)}>{label(s)} ({counts[s] || 0})</button>)}</div>
    <Feedback error={error} notice={notice} />
    <div className="user-table-wrap"><table className="user-table"><thead><tr><th>Order</th><th>Customer</th><th>Items</th><th>Stock</th><th>Shipment</th><th>Invoice</th><th>Total</th><th>Status</th><th /></tr></thead>
      <tbody>{items.map(o => { const next = ORDER_FLOW[ORDER_FLOW.indexOf(o.status) + 1]; const open = !['delivered', 'cancelled'].includes(o.status);
        return <tr key={o.id}><td>{o.order_number}<small>{when(o.created_at)}</small></td><td>{o.customer_name || '—'}<small>{o.phone}</small></td>
          <td>{(o.items || []).map(i => i.name + ' × ' + i.quantity).join(', ')}</td>
          <td>{(o.stock || []).length ? [...new Set(o.stock.map(s => label(s.status)))].join(', ') : 'Not tracked'}<small>{(o.stock || [])[0]?.warehouse}</small></td>
          <td>{o.shipment ? label(o.shipment.status) : '—'}<small>{o.shipment?.tracking_number}</small></td>
          <td>{o.invoice ? o.invoice.number : '—'}<small>{o.invoice ? label(o.invoice.status) : ''}</small></td><td>{money(o.total)}<small>{label(o.payment_status)}</small></td><td><Badge s={o.status} /></td>
          <td className="user-actions">{open && next && <button className="primary-cta" onClick={() => move(o, next)}>{ORDER_STEP_LABEL[next]}</button>}{open && <button className="outline-action" onClick={() => window.confirm('Cancel order ' + o.order_number + '? Reserved stock will be released.') && move(o, 'cancelled')}>Cancel</button>}</td></tr>; })}</tbody></table></div>
    {!busy && !items.length && <p className="muted-note">No orders match.</p>}
  </section>;
}

export function ErpCustomers() {
  const { call, busy, error, notice, act } = useErp();
  const [items, setItems] = useState([]), [search, setSearch] = useState(''), [form, setForm] = useState(null);
  const load = (q = search) => act(async () => { const j = await call('/erp/customers?search=' + encodeURIComponent(q)); setItems(j.items || []); });
  useEffect(() => { load(''); }, []);
  const blank = { name: '', phone: '', email: '', gstin: '', state_code: '', credit_days: 0, address: '' };
  const text = c => typeof c.billing_address === 'object' && c.billing_address ? (c.billing_address.text || '') : '';
  const set = k => e => setForm(f => ({ ...f, [k]: e.target.value }));
  async function save(e) {
    e.preventDefault();
    const body = { name: form.name, phone: form.phone || '', email: form.email || '', gstin: form.gstin || '', state_code: form.state_code || '', credit_days: Number(form.credit_days || 0), address: form.address || '' };
    const ok = await act(() => form.id ? call('/erp/customers/' + form.id, { method: 'PUT', body }) : call('/erp/customers', { method: 'POST', body }), form.id ? 'Customer updated.' : 'Customer created.');
    if (ok) { setForm(null); load(); }
  }
  return <section className="panel operations-manager">
    <div className="panel-heading"><div><h2>Customers</h2><p>Customer master shared by website orders, POS and invoices. Website customers are added automatically at their first order.</p></div>
      <div className="moderation-controls"><input placeholder="Search name, email, phone, GSTIN" value={search} onChange={e => setSearch(e.target.value)} onKeyDown={e => e.key === 'Enter' && load()} /><button className="outline-action" onClick={() => load()} disabled={busy}>Search</button><button className="primary-cta" onClick={() => setForm({ ...blank })}>+ New customer</button></div></div>
    <Feedback error={error} notice={notice} />
    {form && <form className="erp-form panel" onSubmit={save}><h3>{form.id ? 'Edit customer' : 'New customer'}</h3>
      <Field name="Name"><input required value={form.name} onChange={set('name')} /></Field><Field name="Phone"><input value={form.phone || ''} onChange={set('phone')} /></Field>
      <Field name="Email"><input type="email" value={form.email || ''} onChange={set('email')} /></Field><Field name="GSTIN"><input value={form.gstin || ''} onChange={set('gstin')} /></Field>
      <Field name="State code (e.g. 27)"><input value={form.state_code || ''} onChange={set('state_code')} /></Field><Field name="Credit days"><input type="number" min="0" max="365" value={form.credit_days} onChange={set('credit_days')} /></Field>
      <Field name="Billing address"><input value={form.address || ''} onChange={set('address')} /></Field>
      <div className="erp-actions"><button className="primary-cta" type="submit">Save customer</button><button type="button" className="outline-action" onClick={() => setForm(null)}>Cancel</button></div></form>}
    <div className="user-table-wrap"><table className="user-table"><thead><tr><th>Customer</th><th>Contact</th><th>GSTIN</th><th>Credit</th><th>Web orders</th><th>Invoiced</th><th>Outstanding</th><th /></tr></thead>
      <tbody>{items.map(c => <tr key={c.id}><td>{c.name}<small>{when(c.created_at)}</small></td><td>{c.email || '—'}<small>{c.phone}</small></td><td>{c.gstin || '—'}</td><td>{c.credit_days}d</td><td>{c.website_orders}</td><td>{money(c.invoiced)}</td><td>{money(c.outstanding)}</td>
        <td><button className="outline-action" onClick={() => setForm({ ...c, address: text(c) })}>Edit</button></td></tr>)}</tbody></table></div>
    {!busy && !items.length && <p className="muted-note">No customers yet.</p>}
  </section>;
}

/* ------------------------------------------------------------------ LOGISTICS */

const SHIP_NEXT = { created: 'packed', packed: 'in_transit', in_transit: 'out_for_delivery', out_for_delivery: 'delivered' };
const SHIP_LABEL = { packed: 'Mark packed', in_transit: 'Dispatch', out_for_delivery: 'Out for delivery', delivered: 'Mark delivered' };

export function ErpLogistics({ tab }) {
  const { call, busy, error, notice, act } = useErp();
  const [items, setItems] = useState([]), [draft, setDraft] = useState({});
  const load = () => act(async () => { const j = await call('/erp/logistics/shipments'); setItems(j.items || []); });
  useEffect(() => { load(); }, []);
  const patch = async (s, body, ok) => { const r = await act(() => call('/erp/logistics/shipments/' + s.id, { method: 'PATCH', body }), ok); if (r) { setDraft(d => ({ ...d, [s.id]: undefined })); load(); } };
  const rows = tab === 'tracking' ? items.filter(s => ['in_transit', 'out_for_delivery'].includes(s.status)) : items;
  return <section className="panel operations-manager">
    <div className="panel-heading"><div><h2>{tab === 'tracking' ? 'Delivery tracking' : 'Shipments'}</h2><p>Shipments are created when a website order is packed. Moving a shipment forward updates the customer’s order, stock and accounting.</p></div><button className="outline-action" onClick={load} disabled={busy}>↻ Refresh</button></div>
    <Feedback error={error} notice={notice} />
    <div className="user-table-wrap"><table className="user-table"><thead><tr><th>Order</th><th>Customer</th><th>Deliver to</th><th>Carrier</th><th>Tracking</th><th>Status</th><th /></tr></thead>
      <tbody>{rows.map(s => { const d = draft[s.id] || { carrier: s.carrier || '', tracking_number: s.tracking_number || '' }; const next = SHIP_NEXT[s.status] || (s.status === 'exception' ? 'in_transit' : null); const closed = ['delivered', 'cancelled'].includes(s.status);
        return <tr key={s.id}><td>{s.order_number || '#' + s.order_id}<small>{s.order_total ? money(s.order_total) : ''}</small></td><td>{s.customer_name || '—'}<small>{s.phone}</small></td><td>{s.address || '—'}</td>
          <td>{closed ? (s.carrier || '—') : <input value={d.carrier} onChange={e => setDraft(x => ({ ...x, [s.id]: { ...d, carrier: e.target.value } }))} />}</td>
          <td>{closed ? (s.tracking_number || '—') : <input value={d.tracking_number} onChange={e => setDraft(x => ({ ...x, [s.id]: { ...d, tracking_number: e.target.value } }))} />}</td><td><Badge s={s.status} /></td>
          <td className="user-actions">{!closed && <button className="outline-action" onClick={() => patch(s, { carrier: d.carrier, tracking_number: d.tracking_number }, 'Shipment details saved.')}>Save</button>}
            {next && <button className="primary-cta" onClick={() => patch(s, { status: next, carrier: d.carrier, tracking_number: d.tracking_number }, next === 'delivered' ? 'Delivered. The order is complete and the sale is booked in accounting.' : 'Shipment moved to ' + label(next) + '.')}>{SHIP_LABEL[next]}</button>}
            {!closed && s.status !== 'exception' && <button className="outline-action" onClick={() => patch(s, { status: 'exception' }, 'Shipment flagged as an exception.')}>Exception</button>}</td></tr>; })}</tbody></table></div>
    {!busy && !rows.length && <p className="muted-note">{tab === 'tracking' ? 'Nothing is out for delivery right now.' : 'No shipments yet. They appear here when a website order is packed.'}</p>}
  </section>;
}

/* ------------------------------------------------------------------ ACCOUNTING */

const AGE_LABEL = { current: 'Not yet due', d1_30: '1–30 days', d31_60: '31–60 days', d61_90: '61–90 days', d90_plus: '90+ days' };

function Aging({ title, block, parties, partyTitle }) {
  const max = Math.max(1, ...Object.values(block.aging).map(Number));
  return <div className="panel erp-card"><h3>{title}</h3>
    <div className="erp-kpis"><div><small>Total outstanding</small><b>{money(block.total)}</b></div><div><small>Overdue</small><b>{money(block.overdue)}</b></div></div>
    {Object.entries(block.aging).map(([k, v]) => <div className="erp-bar" key={k}><span>{AGE_LABEL[k]}</span><i style={{ width: Math.round((Number(v) / max) * 100) + '%' }} /><b>{money(v)}</b></div>)}
    <p className="muted-note">{Object.entries(block.by_status).map(([k, v]) => label(k) + ': ' + v).join(' · ')}</p>
    {parties.length > 0 && <><h4>{partyTitle}</h4>{parties.map(p => <div className="erp-bar plain" key={p.name}><span>{p.name}</span><b>{money(p.amount)}</b></div>)}</>}
  </div>;
}

function AccountingDashboard() {
  const { call, busy, error, act } = useErp();
  const [d, setD] = useState(null), [ar, setAr] = useState([]);
  const load = () => act(async () => { const [a, b] = await Promise.all([call('/erp/accounting/dashboard'), call('/erp/accounting/receivables')]); setD(a); setAr(b.items || []); });
  useEffect(() => { load(); }, []);
  const diff = d ? [Number(d.reconciliation.receivable_documents_vs_ledger), Number(d.reconciliation.payable_documents_vs_ledger)] : [0, 0];
  return <section className="panel operations-manager">
    <div className="panel-heading"><div><h2>Receivables & payables</h2><p>What customers owe you, what you owe vendors, and the status of every invoice and bill.</p></div><button className="outline-action" onClick={load} disabled={busy}>↻ Refresh</button></div>
    <Feedback error={error} />
    {d && <>
      <div className="erp-grid">
        <Aging title="Receivable (customers owe you)" block={d.receivable} parties={d.receivable.top_customers} partyTitle="Top customers by balance" />
        <Aging title="Payable (you owe vendors)" block={d.payable} parties={d.payable.top_vendors} partyTitle="Top vendors by balance" />
      </div>
      {d.payable.bills_to_approve > 0 && <p className="review-feedback">{d.payable.bills_to_approve} vendor bill(s) are waiting for approval.</p>}
      <div className="erp-kpis wide">
        <div><small>Credit notes issued</small><b>{d.notes.credit_notes.count} · {money(d.notes.credit_notes.total)}</b></div>
        <div><small>Debit notes received</small><b>{d.notes.debit_notes.count} · {money(d.notes.debit_notes.total)}</b></div>
        <div><small>Unapplied debit notes</small><b>{money(d.notes.debit_notes.unapplied)}</b></div>
        <div><small>Cash + bank</small><b>{money(Number(d.ledger.cash) + Number(d.ledger.bank))}</b></div>
        <div><small>Inventory value</small><b>{money(d.ledger.inventory)}</b></div>
        <div><small>GST payable (output − input)</small><b>{money(Number(d.ledger.output_gst) - Number(d.ledger.input_gst))}</b></div>
      </div>
      {(Math.abs(diff[0]) >= 0.01 || Math.abs(diff[1]) >= 0.01) && <p className="review-feedback error">Ledger check: documents differ from the ledger by {money(diff[0])} on receivables and {money(diff[1])} on payables. Pending (unconfirmed) invoices or unposted bills usually explain this.</p>}
    </>}
    <h3>Customer invoices</h3>
    <div className="user-table-wrap"><table className="user-table"><thead><tr><th>Invoice</th><th>Customer</th><th>Channel</th><th>Total</th><th>Received</th><th>Credit notes</th><th>Outstanding</th><th>Age</th><th>Status</th></tr></thead>
      <tbody>{ar.map(i => <tr key={i.kind + i.id}><td>{i.reference}</td><td>{i.customer_name || '—'}</td><td>{label(i.channel)}</td><td>{money(i.total)}</td><td>{money(i.received)}</td><td>{money(i.credit_total)}</td><td>{money(i.outstanding)}</td><td>{i.age_days ?? 0}d</td><td><Badge s={i.status === 'bill_created' ? i.payment_status : i.status} /></td></tr>)}</tbody></table></div>
    {!busy && !ar.length && <p className="muted-note">No invoices yet. Delivered website orders and POS sales appear here.</p>}
  </section>;
}

function NotesRegister() {
  const { call, busy, error, act } = useErp();
  const [items, setItems] = useState([]);
  useEffect(() => { act(async () => { const j = await call('/erp/accounting/notes'); setItems(j.items || []); }); }, []);
  return <section className="panel operations-manager">
    <div className="panel-heading"><div><h2>Credit & debit notes</h2><p>Credit notes reduce what a customer owes (sales returns). Debit notes reduce what you owe a vendor (purchase returns).</p></div></div>
    <Feedback error={error} />
    <div className="user-table-wrap"><table className="user-table"><thead><tr><th>Note</th><th>Type</th><th>Party</th><th>Against</th><th>Source return</th><th>Amount</th><th>GST</th><th>Date</th><th>Status</th></tr></thead>
      <tbody>{items.map(n => <tr key={n.kind + n.reference}><td>{n.reference}</td><td>{n.kind === 'credit_note' ? 'Credit note (sales)' : 'Debit note (purchase)'}</td><td>{n.party || 'Customer'}</td><td>{n.against || '—'}</td><td>{n.source || '—'}</td><td>{money(n.amount)}</td><td>{money(n.tax_total)}</td><td>{when(n.created_at)}</td><td><Badge s={n.status} /></td></tr>)}</tbody></table></div>
    {!busy && !items.length && <p className="muted-note">No notes yet. They are raised automatically from sales returns and rejected purchase goods.</p>}
  </section>;
}

export function ErpAccounting({ tab }) {
  if (tab === 'notes') return <NotesRegister />;
  if (tab === 'payables') return <ErpPayables />;
  return <AccountingDashboard />;
}
