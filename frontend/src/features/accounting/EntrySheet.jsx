import { useMemo, useState } from "react";
import {
  ArrowLeftRight, BookOpen, FileMinus, FilePlus, HandCoins, Landmark, Plus, ReceiptIndianRupee,
  ShoppingBag, ShoppingCart, Trash2, Wallet,
} from "lucide-react";
import { accountingApi, GST_RATES, VOUCHER_TYPES, errorText, isoToday, money, newIdempotencyKey, num } from "./accountingApi.js";
import { AccountSelect, Alert, Field, Sheet } from "./AccountingUi.jsx";

export const ENTRY_TYPES = [
  { key: "sales", icon: ShoppingBag, hint: "Bill a customer with GST" },
  { key: "purchase", icon: ShoppingCart, hint: "Record a supplier bill and input GST" },
  { key: "expense", icon: Wallet, hint: "Rent, salary, electricity and other costs" },
  { key: "receipt", icon: HandCoins, hint: "Money received from a customer" },
  { key: "payment", icon: ReceiptIndianRupee, hint: "Money paid to a supplier" },
  { key: "contra", icon: ArrowLeftRight, hint: "Cash deposit, withdrawal or transfer" },
  { key: "credit_note", icon: FileMinus, hint: "Customer return or sales discount" },
  { key: "debit_note", icon: FilePlus, hint: "Return goods to a supplier" },
  { key: "journal", icon: BookOpen, hint: "Adjustments with any debit and credit" },
  { key: "opening", icon: Landmark, hint: "Starting balances when you begin" },
];

const INVOICE_KINDS = new Set(["sales", "purchase", "credit_note", "debit_note"]);
const isMoney = (a) => a.sub_type === "cash" || a.sub_type === "bank";
const byCode = (accounts, code) => (accounts || []).find((a) => a.code === code)?.id || "";
const round2 = (n) => Math.round((n + Number.EPSILON) * 100) / 100;

export function EntryTypePicker({ onPick }) {
  return (
    <div className="acc-type-grid">
      {ENTRY_TYPES.map(({ key, icon: Icon, hint }) => (
        <button key={key} type="button" className="acc-type" onClick={() => onPick(key)}>
          <span className={`acc-avatar ${VOUCHER_TYPES[key].tone}`}><Icon size={18} aria-hidden="true" /></span>
          <strong>{VOUCHER_TYPES[key].label}</strong>
          <small>{hint}</small>
        </button>
      ))}
    </div>
  );
}

/** Bottom sheet for creating any accounting entry. Calls onPosted(voucher) after a successful post. */
export default function EntrySheet({ initialType = "", accounts, settings, onClose, onPosted }) {
  const [type, setType] = useState(initialType);
  const title = type ? `New ${VOUCHER_TYPES[type].label.toLowerCase()}` : "New entry";
  if (!type) {
    return <Sheet title={title} onClose={onClose}><EntryTypePicker onPick={setType} /></Sheet>;
  }
  const Form = INVOICE_KINDS.has(type) ? InvoiceForm : type === "journal" || type === "opening" ? JournalForm : SimpleForm;
  return <Form key={type} type={type} accounts={accounts} settings={settings} onClose={onClose} onPosted={onPosted} onBack={initialType ? null : () => setType("")} title={title} />;
}

function useSubmit(onPosted) {
  const [idempotencyKey] = useState(newIdempotencyKey);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const submit = async (call) => {
    setBusy(true);
    setError("");
    try {
      const voucher = await call(idempotencyKey);
      onPosted(voucher);
    } catch (err) {
      setError(errorText(err));
    } finally {
      setBusy(false);
    }
  };
  return { busy, error, setError, submit };
}

function SheetFooter({ onBack, onClose, busy, label, disabled }) {
  return (
    <>
      {onBack && <button type="button" className="acc-btn" onClick={onBack} disabled={busy}>Back</button>}
      <span className="acc-spacer acc-hide-mobile" />
      <button type="button" className="acc-btn" onClick={onClose} disabled={busy}>Cancel</button>
      <button type="submit" form="acc-entry-form" className="acc-btn primary" disabled={busy || disabled}>{busy ? "Posting…" : label}</button>
    </>
  );
}

/* ---------------------------------------------------------------- invoices */

const blankItem = () => ({ description: "", account_id: "", hsn_sac: "", quantity: "1", rate: "", discount: "", gst_rate: "18" });

function InvoiceForm({ type, accounts, settings, onClose, onPosted, onBack, title }) {
  const salesSide = type === "sales" || type === "credit_note";
  const [form, setForm] = useState({
    voucher_date: isoToday(), party_name: "", party_gstin: "", place_of_supply: settings?.default_supply || "intra",
    settlement: "credit", against_receipt: false, round_off: true, reference: "", due_date: "", narration: "",
  });
  const [items, setItems] = useState([blankItem()]);
  const { busy, error, setError, submit } = useSubmit(onPosted);
  const set = (key) => (event) => setForm((f) => ({ ...f, [key]: event.target.type === "checkbox" ? event.target.checked : event.target.value }));
  const setItem = (index, key, value) => setItems((list) => list.map((item, i) => (i === index ? { ...item, [key]: value } : item)));

  const preview = useMemo(() => {
    let taxable = 0, cgst = 0, sgst = 0, igst = 0;
    items.forEach((item) => {
      const value = round2(num(item.quantity) * num(item.rate)) - num(item.discount);
      const tax = round2((value * num(item.gst_rate)) / 100);
      taxable += value;
      if (form.place_of_supply === "inter") igst += tax;
      else { const half = round2(tax / 2); cgst += half; sgst += tax - half; }
    });
    const gross = round2(taxable + cgst + sgst + igst);
    const grand = form.round_off ? Math.round(gross) : gross;
    return { taxable, cgst, sgst, igst, gross, roundOff: round2(grand - gross), grand };
  }, [items, form.place_of_supply, form.round_off]);

  const itemAccountFilter = salesSide ? (a) => a.account_type === "income" : (a) => ["asset", "expense"].includes(a.account_type) && !isMoney(a) && a.sub_type !== "tax_input" && a.sub_type !== "receivable";
  const partyLabel = salesSide ? "Customer name" : "Supplier name";
  const defaultItemNote = type === "sales" ? "Sales (4000)" : type === "credit_note" ? "Sales returns (4010)" : form.against_receipt ? "Goods received not invoiced (2050)" : "Inventory (1200)";

  const onSubmit = (event) => {
    event.preventDefault();
    if (preview.grand <= 0) { setError("Add at least one line with a value greater than zero."); return; }
    submit((key) => accountingApi.createInvoice({
      invoice_type: type,
      voucher_date: form.voucher_date,
      party_name: form.party_name.trim(),
      party_gstin: form.party_gstin.trim() || null,
      place_of_supply: form.place_of_supply,
      settlement: form.settlement,
      against_receipt: type === "purchase" ? form.against_receipt : false,
      round_off: form.round_off,
      reference: form.reference.trim() || null,
      due_date: form.settlement === "credit" && form.due_date ? form.due_date : null,
      narration: form.narration.trim() || null,
      idempotency_key: key,
      lines: items.filter((item) => item.description.trim() || num(item.rate) > 0).map((item) => ({
        description: item.description.trim() || "Item",
        account_id: item.account_id || null,
        hsn_sac: item.hsn_sac.trim() || null,
        quantity: item.quantity || "1",
        rate: item.rate || "0",
        discount: item.discount || "0",
        gst_rate: item.gst_rate,
      })),
    }));
  };

  return (
    <Sheet wide title={title} onClose={onClose} footer={<SheetFooter onBack={onBack} onClose={onClose} busy={busy} label={`Post ${money(preview.grand)}`} />}>
      <form id="acc-entry-form" onSubmit={onSubmit} className="acc-stack">
        <Alert>{error}</Alert>
        <div className="acc-form-grid">
          <Field label={partyLabel}><input value={form.party_name} onChange={set("party_name")} required maxLength={200} placeholder={salesSide ? "e.g. Walk-in customer" : "e.g. Patna Wholesale Traders"} /></Field>
          <Field label="Date"><input type="date" value={form.voucher_date} onChange={set("voucher_date")} required /></Field>
          <Field label="Party GSTIN (optional)" hint="Leave blank for unregistered / B2C"><input value={form.party_gstin} onChange={set("party_gstin")} maxLength={15} placeholder="10ABCDE1234F1Z5" style={{ textTransform: "uppercase" }} /></Field>
          <Field label="Place of supply" hint={form.place_of_supply === "inter" ? "IGST will be charged" : "CGST + SGST will be charged"}>
            <select value={form.place_of_supply} onChange={set("place_of_supply")}>
              <option value="intra">Within state (CGST + SGST)</option>
              <option value="inter">Other state (IGST)</option>
            </select>
          </Field>
          <Field label={salesSide ? "Received by" : "Paid by"}>
            <select value={form.settlement} onChange={set("settlement")}>
              <option value="credit">On credit ({salesSide ? "customer owes" : "we owe supplier"})</option>
              <option value="cash">Cash</option>
              <option value="bank">Bank</option>
              <option value="upi">UPI</option>
              <option value="card">Card</option>
            </select>
          </Field>
          {form.settlement === "credit"
            ? <Field label="Due date (optional)"><input type="date" value={form.due_date} min={form.voucher_date} onChange={set("due_date")} /></Field>
            : <Field label="Reference (optional)"><input value={form.reference} onChange={set("reference")} maxLength={100} placeholder="Bill / UTR number" /></Field>}
          {form.settlement === "credit" && <Field label="Reference (optional)"><input value={form.reference} onChange={set("reference")} maxLength={100} placeholder={salesSide ? "Order / challan number" : "Supplier bill number"} /></Field>}
          {type === "purchase" && (
            <label className="acc-switch wide"><input type="checkbox" checked={form.against_receipt} onChange={set("against_receipt")} /> Stock already received through Purchasing (clear goods-received account instead of adding inventory again)</label>
          )}
        </div>

        <div className="acc-card-head" style={{ margin: "6px 0 0" }}>
          <div><h2>Items</h2><p>Lines without an account post to {defaultItemNote}.</p></div>
          <button type="button" className="acc-btn small" onClick={() => setItems((list) => [...list, blankItem()])}><Plus size={14} /> Add line</button>
        </div>
        <div className="acc-lines">
          {items.map((item, index) => (
            <div className="acc-line" key={index}>
              <div className="acc-line-row inv">
                <Field label="Description"><input value={item.description} onChange={(e) => setItem(index, "description", e.target.value)} maxLength={300} required placeholder="Item or service" /></Field>
                <Field label="HSN/SAC"><input value={item.hsn_sac} onChange={(e) => setItem(index, "hsn_sac", e.target.value.replace(/\D/g, ""))} inputMode="numeric" maxLength={8} /></Field>
                <Field label="Qty"><input type="number" min="0.001" step="0.001" value={item.quantity} onChange={(e) => setItem(index, "quantity", e.target.value)} required /></Field>
                <Field label="Rate (₹, before GST)"><input type="number" min="0" step="0.01" value={item.rate} onChange={(e) => setItem(index, "rate", e.target.value)} required /></Field>
                <Field label="Discount ₹"><input type="number" min="0" step="0.01" value={item.discount} onChange={(e) => setItem(index, "discount", e.target.value)} /></Field>
                <Field label="GST %">
                  <select value={item.gst_rate} onChange={(e) => setItem(index, "gst_rate", e.target.value)}>{GST_RATES.map((r) => <option key={r} value={r}>{r}%</option>)}</select>
                </Field>
                <button type="button" className="acc-icon-btn" aria-label={`Remove line ${index + 1}`} disabled={items.length === 1} onClick={() => setItems((list) => list.filter((_, i) => i !== index))}><Trash2 size={16} /></button>
              </div>
              <div className="acc-line-row inv2">
                <Field label="Account (optional)">
                  <AccountSelect accounts={accounts} value={item.account_id} onChange={(v) => setItem(index, "account_id", v)} filter={itemAccountFilter} placeholder={`Default: ${defaultItemNote}`} />
                </Field>
                <div className="acc-row-amt" style={{ alignSelf: "center" }}>{money(round2(num(item.quantity) * num(item.rate)) - num(item.discount))}<small>taxable value</small></div>
              </div>
            </div>
          ))}
        </div>

        <div className="acc-form-grid">
          <Field label="Notes (optional)"><textarea value={form.narration} onChange={set("narration")} maxLength={1000} /></Field>
          <div className="acc-totals" aria-live="polite">
            <div><span>Taxable value</span><strong>{money(preview.taxable)}</strong></div>
            {form.place_of_supply === "inter"
              ? <div><span>IGST</span><span>{money(preview.igst)}</span></div>
              : <><div><span>CGST</span><span>{money(preview.cgst)}</span></div><div><span>SGST</span><span>{money(preview.sgst)}</span></div></>}
            <label className="acc-switch" style={{ justifyContent: "space-between" }}><span>Round off</span><span><input type="checkbox" checked={form.round_off} onChange={set("round_off")} /> {money(preview.roundOff)}</span></label>
            <div className="grand"><span>Total</span><span>{money(preview.grand)}</span></div>
            <small className="acc-muted">Preview. The server recalculates GST and the final total when posting.</small>
          </div>
        </div>
      </form>
    </Sheet>
  );
}

/* ---------------------------------------------- receipt / payment / expense / contra */

const SIMPLE_COPY = {
  receipt: { from: "Received from (credit)", to: "Received into", party: "Customer / payer", fromDefault: "1100" },
  payment: { from: "Paid from", to: "Paid to (debit)", party: "Supplier / payee", toDefault: "2000" },
  expense: { from: "Paid from", to: "Expense account", party: "Paid to (optional)" },
  contra: { from: "From account", to: "To account", party: null },
};

function SimpleForm({ type, accounts, onClose, onPosted, onBack, title }) {
  const copy = SIMPLE_COPY[type];
  const cash = byCode(accounts, "1000");
  const [form, setForm] = useState({
    voucher_date: isoToday(), amount: "", party_name: "", reference: "", narration: "",
    debit_account: type === "payment" ? byCode(accounts, copy.toDefault) : type === "receipt" ? cash : type === "contra" ? byCode(accounts, "1010") : "",
    credit_account: type === "receipt" ? byCode(accounts, copy.fromDefault) : cash,
  });
  const { busy, error, setError, submit } = useSubmit(onPosted);
  const set = (key) => (event) => setForm((f) => ({ ...f, [key]: event.target.value }));
  const setAcc = (key) => (value) => setForm((f) => ({ ...f, [key]: value }));

  const debitFilter = type === "expense" ? (a) => a.account_type === "expense"
    : type === "receipt" || type === "contra" ? isMoney
      : (a) => !isMoney(a);
  const creditFilter = type === "receipt" ? (a) => !isMoney(a)
    : type === "expense" ? (a) => isMoney(a) || a.sub_type === "payable"
      : isMoney;

  const onSubmit = (event) => {
    event.preventDefault();
    const amount = num(form.amount);
    if (amount <= 0) { setError("Enter an amount greater than zero."); return; }
    if (!form.debit_account || !form.credit_account) { setError("Choose both accounts."); return; }
    if (form.debit_account === form.credit_account) { setError("Choose two different accounts."); return; }
    const partyType = type === "receipt" ? "customer" : type === "payment" ? "supplier" : form.party_name.trim() ? "other" : null;
    submit((key) => accountingApi.createVoucher({
      voucher_type: type, voucher_date: form.voucher_date,
      narration: form.narration.trim() || null, reference: form.reference.trim() || null,
      party_type: partyType, party_name: form.party_name.trim() || null, idempotency_key: key,
      lines: [
        { account_id: form.debit_account, debit: amount.toFixed(2), credit: "0", narration: form.narration.trim() || null },
        { account_id: form.credit_account, debit: "0", credit: amount.toFixed(2), narration: form.party_name.trim() || null },
      ],
    }));
  };

  // Show "from" first for payment/expense/contra; "received into" first for receipts.
  const debitField = <Field label={copy.to}><AccountSelect accounts={accounts} value={form.debit_account} onChange={setAcc("debit_account")} filter={debitFilter} required /></Field>;
  const creditField = <Field label={copy.from}><AccountSelect accounts={accounts} value={form.credit_account} onChange={setAcc("credit_account")} filter={creditFilter} required /></Field>;

  return (
    <Sheet title={title} onClose={onClose} footer={<SheetFooter onBack={onBack} onClose={onClose} busy={busy} label={`Post ${money(form.amount)}`} />}>
      <form id="acc-entry-form" onSubmit={onSubmit} className="acc-stack">
        <Alert>{error}</Alert>
        <Field label="Amount (₹)"><input className="acc-input" style={{ height: 56, fontSize: 24, fontWeight: 800 }} type="number" min="0.01" step="0.01" inputMode="decimal" value={form.amount} onChange={set("amount")} required autoFocus /></Field>
        <div className="acc-form-grid">
          {type === "receipt" ? <>{debitField}{creditField}</> : <>{creditField}{debitField}</>}
          <Field label="Date"><input type="date" value={form.voucher_date} onChange={set("voucher_date")} required /></Field>
          <Field label="Reference (optional)"><input value={form.reference} onChange={set("reference")} maxLength={100} placeholder="UTR / cheque / bill no." /></Field>
          {copy.party && <Field label={copy.party} className="wide"><input value={form.party_name} onChange={set("party_name")} maxLength={200} required={type === "receipt" || type === "payment"} /></Field>}
          <Field label="Narration (optional)" className="wide"><textarea value={form.narration} onChange={set("narration")} maxLength={1000} /></Field>
        </div>
        {(type === "receipt" || type === "payment") && <p className="acc-muted">Use the same party name as on the invoice or bill so the outstanding balance clears in Parties.</p>}
      </form>
    </Sheet>
  );
}

/* --------------------------------------------------------- journal / opening */

const blankLine = () => ({ account_id: "", debit: "", credit: "", narration: "" });

function JournalForm({ type, accounts, onClose, onPosted, onBack, title }) {
  const [form, setForm] = useState({ voucher_date: isoToday(), narration: "", reference: "" });
  const [lines, setLines] = useState([blankLine(), blankLine()]);
  const { busy, error, setError, submit } = useSubmit(onPosted);
  const setLine = (index, key, value) => setLines((list) => list.map((line, i) => {
    if (i !== index) return line;
    const next = { ...line, [key]: value };
    // A line is either a debit or a credit.
    if (key === "debit" && num(value) > 0) next.credit = "";
    if (key === "credit" && num(value) > 0) next.debit = "";
    return next;
  }));
  const debit = round2(lines.reduce((s, l) => s + num(l.debit), 0));
  const credit = round2(lines.reduce((s, l) => s + num(l.credit), 0));
  const diff = round2(debit - credit);
  const openingEquity = byCode(accounts, "3900");

  const balanceWithOpening = () => {
    if (!diff || !openingEquity) return;
    setLines((list) => [...list.filter((l) => l.account_id || num(l.debit) || num(l.credit)), {
      account_id: openingEquity, debit: diff < 0 ? Math.abs(diff).toFixed(2) : "", credit: diff > 0 ? diff.toFixed(2) : "", narration: "Opening balance difference",
    }]);
  };

  const onSubmit = (event) => {
    event.preventDefault();
    const used = lines.filter((l) => l.account_id && (num(l.debit) > 0 || num(l.credit) > 0));
    if (used.length < 2) { setError("Add at least two lines with an account and an amount."); return; }
    if (diff !== 0) { setError(`Debits and credits differ by ${money(Math.abs(diff))}.`); return; }
    submit((key) => accountingApi.createVoucher({
      voucher_type: type, voucher_date: form.voucher_date, narration: form.narration.trim() || null,
      reference: form.reference.trim() || null, idempotency_key: key,
      lines: used.map((l) => ({ account_id: l.account_id, debit: num(l.debit).toFixed(2), credit: num(l.credit).toFixed(2), narration: l.narration.trim() || null })),
    }));
  };

  return (
    <Sheet wide title={title} onClose={onClose} footer={<SheetFooter onBack={onBack} onClose={onClose} busy={busy} label="Post entry" disabled={diff !== 0 || debit === 0} />}>
      <form id="acc-entry-form" onSubmit={onSubmit} className="acc-stack">
        <Alert>{error}</Alert>
        {type === "opening" && <Alert tone="info">Enter each balance on its normal side (assets as debit; loans, capital and supplier dues as credit). Use the button below to put any difference into Opening balance equity (3900).</Alert>}
        <div className="acc-form-grid">
          <Field label="Date"><input type="date" value={form.voucher_date} onChange={(e) => setForm((f) => ({ ...f, voucher_date: e.target.value }))} required /></Field>
          <Field label="Reference (optional)"><input value={form.reference} onChange={(e) => setForm((f) => ({ ...f, reference: e.target.value }))} maxLength={100} /></Field>
          <Field label="Narration" className="wide"><input value={form.narration} onChange={(e) => setForm((f) => ({ ...f, narration: e.target.value }))} maxLength={1000} placeholder="Why this entry is being made" /></Field>
        </div>
        <div className="acc-lines">
          {lines.map((line, index) => (
            <div className="acc-line" key={index}>
              <div className="acc-line-row">
                <Field label={`Account ${index + 1}`}><AccountSelect accounts={accounts} value={line.account_id} onChange={(v) => setLine(index, "account_id", v)} /></Field>
                <Field label="Debit ₹"><input type="number" min="0" step="0.01" value={line.debit} onChange={(e) => setLine(index, "debit", e.target.value)} /></Field>
                <Field label="Credit ₹"><input type="number" min="0" step="0.01" value={line.credit} onChange={(e) => setLine(index, "credit", e.target.value)} /></Field>
                <button type="button" className="acc-icon-btn" aria-label={`Remove line ${index + 1}`} disabled={lines.length <= 2} onClick={() => setLines((list) => list.filter((_, i) => i !== index))}><Trash2 size={16} /></button>
              </div>
              <input className="acc-input" aria-label={`Line ${index + 1} note`} placeholder="Line note (optional)" value={line.narration} maxLength={300} onChange={(e) => setLine(index, "narration", e.target.value)} />
            </div>
          ))}
        </div>
        <div className="acc-toolbar">
          <button type="button" className="acc-btn small" onClick={() => setLines((list) => [...list, blankLine()])}><Plus size={14} /> Add line</button>
          {type === "opening" && diff !== 0 && <button type="button" className="acc-btn small" onClick={balanceWithOpening}>Balance with opening equity</button>}
        </div>
        <div className="acc-totals">
          <div><span>Total debit</span><strong>{money(debit)}</strong></div>
          <div><span>Total credit</span><strong>{money(credit)}</strong></div>
          <div className="grand"><span>Difference</span><span className={diff === 0 ? "acc-balance-ok" : "acc-balance-bad"}>{diff === 0 ? "Balanced" : money(Math.abs(diff))}</span></div>
        </div>
      </form>
    </Sheet>
  );
}
