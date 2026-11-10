import OrganisationPolicyPanel from "../shared/OrganisationPolicyPanel.jsx";
import PurchasingRequestsWorkspace from "./PurchasingRequestsWorkspace.jsx";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import "./PurchasingWorkspace.css";
import { apiRequest } from "../../services/api.js";
import { toLocalDateInputValue } from "./dateInput.js";

const money = v => new Intl.NumberFormat("en-IN", { style: "currency", currency: "INR" }).format(Number(v || 0));
const label = v => String(v || "").replaceAll("_", " ").replace(/\b\w/g, c => c.toUpperCase());
const emptySupplier = { name: "", contact_name: "", phone: "", email: "", gstin: "", address: "" };
const emptyLine = { variant_id: "", quantity: "1", unit_cost: "" };

export default function PurchasingWorkspace({ onBack }) {
  const [tab, setTab] = useState("overview");
  const [orderSearch, setOrderSearch] = useState("");
  const [orderStatusFilter, setOrderStatusFilter] = useState("all");
  const [supplierSearch, setSupplierSearch] = useState("");
  const [suppliers, setSuppliers] = useState([]);
  const [locations, setLocations] = useState([]);
  const [variants, setVariants] = useState([]);
  const [orders, setOrders] = useState([]);
  const [supplierForm, setSupplierForm] = useState(emptySupplier);
  const [supplierEditId, setSupplierEditId] = useState(null);
  const [orderEditId, setOrderEditId] = useState(null);
  const [supplierId, setSupplierId] = useState("");
  const [locationId, setLocationId] = useState("");
  const [notes, setNotes] = useState("");
  const [lines, setLines] = useState([{ ...emptyLine }]);
  const [selected, setSelected] = useState(null);
  const [detail, setDetail] = useState(null);
  const [receipts, setReceipts] = useState({});
  const [receiptMeta, setReceiptMeta] = useState({});
  const [receiptHistory, setReceiptHistory] = useState([]);
  const [grnHistory, setGrnHistory] = useState([]);
  const [grnDetail, setGrnDetail] = useState(null);
  const [qcQuantities, setQcQuantities] = useState({});
  const [qcDisposition, setQcDisposition] = useState("accepted");
  const [qcReason, setQcReason] = useState("");
  const qcAttempt = useRef(null);
  const receiptAttempt = useRef(null);
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [supplierInvoices, setSupplierInvoices] = useState([]);
  const [supplierReturns, setSupplierReturns] = useState([]);
  const [returnGrns, setReturnGrns] = useState([]);
  const [returnGrnDetail, setReturnGrnDetail] = useState(null);
  const [returnSupplierInvoiceId, setReturnSupplierInvoiceId] = useState("");
  const [returnReason, setReturnReason] = useState("");
  const [invoiceGrnDetail, setInvoiceGrnDetail] = useState(null);
  const [invoiceNumber, setInvoiceNumber] = useState("");
  const [invoiceDate, setInvoiceDate] = useState(() => toLocalDateInputValue());
  const [invoiceDueDate, setInvoiceDueDate] = useState("");
  const invoiceTaxRate = "18";
  const [invoiceTaxMode, setInvoiceTaxMode] = useState("intra");
  const [invoiceQuantities, setInvoiceQuantities] = useState({});
  const [invoiceRates, setInvoiceRates] = useState({});
  const [invoiceGstRates, setInvoiceGstRates] = useState({});
  const [invoiceHsnSac, setInvoiceHsnSac] = useState({});
  const [invoiceSupplierGstin, setInvoiceSupplierGstin] = useState("");
  const [invoiceFreight, setInvoiceFreight] = useState("0");
  const [invoiceDiscount, setInvoiceDiscount] = useState("0");
  const [invoiceCess, setInvoiceCess] = useState("0");
  const [returnQuantities, setReturnQuantities] = useState({});
  const [paymentVoucherIds, setPaymentVoucherIds] = useState({});
  const [paymentAmounts, setPaymentAmounts] = useState({});
  const [returnVoucherIds, setReturnVoucherIds] = useState({});
  const [returnDebitNotes, setReturnDebitNotes] = useState({});
  const [returnDebitDates, setReturnDebitDates] = useState({});
  const [financeLoading, setFinanceLoading] = useState(false);

  const load = useCallback(async () => {
    setLoading(true); setError("");
    try {
      const [s, l, p, v] = await Promise.all([
        apiRequest("/purchasing/suppliers?limit=500"),
        apiRequest("/inventory/locations?limit=500"),
        apiRequest("/purchasing/orders?limit=200"),
        apiRequest("/catalogue/variants?limit=500"),
      ]);
      setSuppliers(s.items || []); setLocations(l.items || []); setOrders(p.items || []); setVariants(v.items || []);
    } catch (e) { setError(e.message || "Unable to load purchasing data."); }
    finally { setLoading(false); }
  }, []);
  useEffect(() => { load(); }, [load]);

  const loadSupplierFinance = useCallback(async () => {
    setFinanceLoading(true); setError("");
    try {
      const [invoices, returns, grns] = await Promise.all([
        apiRequest("/purchasing/supplier-invoices?limit=200"),
        apiRequest("/purchasing/supplier-returns?limit=200"),
        apiRequest("/purchasing/grns?limit=200"),
      ]);
      setSupplierInvoices(invoices.items || []);
      setSupplierReturns(returns.items || []);
      setReturnGrns(grns.items || []);
    } catch (e) { setError(e.message || "Unable to load supplier invoices and returns."); }
    finally { setFinanceLoading(false); }
  }, []);
  useEffect(() => {
    if (tab === "invoices" || tab === "returns") loadSupplierFinance();
  }, [tab, loadSupplierFinance]);

  async function approveSupplierInvoice(invoice) {
    if (!window.confirm("Approve matched supplier invoice " + invoice.invoice_number + " and post its AP/GRNI voucher?")) return;
    setSaving(true); setError(""); setNotice("");
    try {
      const result = await apiRequest("/purchasing/supplier-invoices/" + invoice.id + "/approve", { method: "POST" });
      if (result.approval_pending) {
        setNotice("Approval stage " + result.approved_stage + " of " + result.required_stages + " recorded. A different eligible approver must complete the next stage.");
      } else {
        setNotice("Invoice approved. Accounting voucher #" + result.accounting_voucher_id + " posted.");
      }
      await loadSupplierFinance();
    } catch (e) { setError(e.message || "Unable to approve supplier invoice."); }
    finally { setSaving(false); }
  }

  async function rejectSupplierInvoice(invoice) {
    const reason = window.prompt("Why is supplier invoice " + invoice.invoice_number + " being rejected?");
    if (reason === null) return;
    if (reason.trim().length < 3) { setError("Enter a rejection reason of at least 3 characters."); return; }
    setSaving(true); setError(""); setNotice("");
    try {
      await apiRequest("/purchasing/supplier-invoices/" + invoice.id + "/reject", {
        method: "POST", body: JSON.stringify({ reason: reason.trim() })
      });
      setNotice("Supplier invoice " + invoice.invoice_number + " rejected with a recorded reason.");
      await loadSupplierFinance();
    } catch (e) { setError(e.message || "Unable to reject supplier invoice."); }
    finally { setSaving(false); }
  }

  async function resolveSupplierInvoiceVariance(invoice) {
    const reason = window.prompt("Record the owner/admin review rationale for the price variance. Resolution is allowed only when invoice net GRNI matches received stock value.");
    if (reason === null) return;
    if (reason.trim().length < 3) { setError("Enter a review rationale of at least 3 characters."); return; }
    setSaving(true); setError(""); setNotice("");
    try {
      await apiRequest("/purchasing/supplier-invoices/" + invoice.id + "/resolve-variance", {
        method: "POST", body: JSON.stringify({ reason: reason.trim() })
      });
      setNotice("Price variance reviewed and matched to received GRNI. Approve the invoice separately to post AP.");
      await loadSupplierFinance();
    } catch (e) { setError(e.message || "Unable to resolve supplier invoice variance."); }
    finally { setSaving(false); }
  }

  async function allocateSupplierPayment(invoice) {
    const voucherId = Number(paymentVoucherIds[invoice.id]);
    const amount = Number(paymentAmounts[invoice.id]);
    if (!Number.isInteger(voucherId) || voucherId <= 0 || !Number.isFinite(amount) || amount <= 0) {
      setError("Enter a valid posted payment voucher ID and allocation amount."); return;
    }
    setSaving(true); setError(""); setNotice("");
    try {
      await apiRequest("/purchasing/supplier-invoices/" + invoice.id + "/payment-allocations", {
        method: "POST", body: JSON.stringify({ accounting_voucher_id: voucherId, allocated_amount: amount })
      });
      setNotice("Payment allocation recorded against " + invoice.invoice_number + ".");
      await loadSupplierFinance();
    } catch (e) { setError(e.message || "Unable to allocate supplier payment."); }
    finally { setSaving(false); }
  }

  async function advanceSupplierReturn(ret, action) {
    const labels = { submit: "submitted", approve: "approved", dispatch: "dispatched" };
    if (action === "approve" && !window.confirm("Approve supplier return " + ret.return_number + "?")) return;
    setSaving(true); setError(""); setNotice("");
    try {
      const result = await apiRequest("/purchasing/supplier-returns/" + ret.id + "/" + action, { method: "POST" });
      setNotice(result.approval_pending
        ? "Supplier return approval stage " + result.approved_stage + " of " + result.required_stages + " recorded. A different eligible approver must complete the next stage."
        : "Supplier return " + labels[action] + ". Status: " + label(result.status) + ".");
      await loadSupplierFinance();
    } catch (e) { setError(e.message || "Unable to update supplier return."); }
    finally { setSaving(false); }
  }

  async function createSupplier(e) {
    e.preventDefault(); setSaving(true); setError(""); setNotice("");
    try {
      const payload = { ...supplierForm };
      for (const k of ["contact_name", "phone", "email", "gstin", "address"]) payload[k] = payload[k].trim() || null;
      const saved = await apiRequest(supplierEditId ? "/purchasing/suppliers/" + supplierEditId : "/purchasing/suppliers", { method: supplierEditId ? "PUT" : "POST", body: JSON.stringify(payload) });
      setSupplierForm(emptySupplier); setSupplierEditId(null); setSupplierId(String(saved.id)); setNotice(supplierEditId ? "Supplier updated." : "Supplier created."); await load();
    } catch (e) { setError(e.message || "Unable to create supplier."); }
    finally { setSaving(false); }
  }

  function editSupplier(supplier) {
    setSupplierEditId(supplier.id);
    setSupplierForm({ name: supplier.name || "", contact_name: supplier.contact_name || "", phone: supplier.phone || "", email: supplier.email || "", gstin: supplier.gstin || "", address: supplier.address || "" });
    setError(""); setNotice("");
    window.scrollTo({ top: 0, behavior: "smooth" });
  }

  function editDraftOrder(order) {
    if (order.status !== "draft") return;
    setOrderEditId(order.id); setSupplierId(String(order.supplier_id)); setLocationId(String(order.location_id));
    setNotes(order.notes || "");
    setLines((order.lines || []).map(line => ({ variant_id: String(line.variant_id), quantity: String(line.quantity_ordered), unit_cost: String(line.unit_cost) })));
    setTab("orders"); setError(""); setNotice("Editing draft " + order.purchase_number + ".");
    window.scrollTo({ top: 0, behavior: "smooth" });
  }

  function setLine(index, key, value) {
    setLines(old => old.map((line, i) => i === index ? { ...line, [key]: value } : line));
  }

  async function createOrder(e) {
    e.preventDefault(); setSaving(true); setError(""); setNotice("");
    try {
      const payload = {
        supplier_id: Number(supplierId), location_id: Number(locationId), notes: notes.trim() || null,
        lines: lines.map(line => ({ variant_id: Number(line.variant_id), quantity: Number(line.quantity), unit_cost: Number(line.unit_cost) })),
      };
      if (!payload.supplier_id || !payload.location_id || payload.lines.some(line => !line.variant_id || !Number.isFinite(line.quantity) || line.quantity <= 0 || !Number.isFinite(line.unit_cost) || line.unit_cost < 0)) {
        throw new Error("Select a supplier, location, catalogue variant, quantity and valid unit cost for each line.");
      }
      const po = await apiRequest(orderEditId ? "/purchasing/orders/" + orderEditId : "/purchasing/orders", { method: orderEditId ? "PUT" : "POST", body: JSON.stringify(payload) });
      setNotice(orderEditId ? "Draft purchase order " + po.purchase_number + " updated." : "Purchase order " + po.purchase_number + " created."); setOrderEditId(null); setNotes(""); setLines([{ ...emptyLine }]); await load(); await openOrder(po.id);
    } catch (e) { setError(e.message || "Unable to create purchase order."); }
    finally { setSaving(false); }
  }

  async function openOrder(id) {
    setSelected(id); setError("");
    try {
      const data = await apiRequest("/purchasing/orders/" + id);
      setDetail(data);
      try {
        const history = await apiRequest("/purchasing/orders/" + id + "/receipts");
        setReceiptHistory(history.items || []);
      } catch {
        // Legacy movement history is supplementary.
        setReceiptHistory([]);
      }
      try { const grns = await apiRequest("/purchasing/grns?purchase_order_id=" + id); setGrnHistory(grns.items || []); }
      catch { setGrnHistory([]); }
      setReceipts(old => {
        const next = { ...old };
        for (const line of data.lines || []) if (next[line.line_id] === undefined) next[line.line_id] = String(line.quantity_open || "");
        return next;
      });
    } catch (e) { setError(e.message || "Unable to load purchase order details."); }
  }

  async function cancelOrder() {
    if (!detail || !window.confirm("Cancel the unreceived remainder of " + detail.purchase_number + "? Received stock will remain in inventory.")) return;
    setSaving(true); setError(""); setNotice("");
    try {
      const result = await apiRequest("/purchasing/orders/" + detail.id + "/cancel", { method: "POST" });
      setNotice(result.message || "Purchase order cancelled."); await load(); await openOrder(detail.id);
    } catch (e) { setError(e.message || "Unable to cancel purchase order."); }
    finally { setSaving(false); }
  }

  async function approveOrder() {
    if (!detail) return;
    setSaving(true); setError(""); setNotice("");
    try {
      const result = await apiRequest("/purchasing/orders/" + detail.id + "/approve", { method: "POST" });
      setNotice(result.message || "Purchase order approved."); await load(); await openOrder(detail.id);
    } catch (e) { setError(e.message || "Unable to approve purchase order."); }
    finally { setSaving(false); }
  }

  async function receiveGoods(e) {
    e.preventDefault(); if (!detail) return;
    const receiptLines = (detail.lines || []).filter(line => Number(receipts[line.line_id]) > 0).map(line => ({ line_id: line.line_id, quantity: Number(receipts[line.line_id]), batch_code: receiptMeta[line.line_id]?.batch_code || null, manufacture_date: receiptMeta[line.line_id]?.manufacture_date || null, expiry_date: receiptMeta[line.line_id]?.expiry_date || null }));
    if (!receiptLines.length) { setError("Enter a received quantity for at least one open line."); return; }
    const note = "Goods receipt recorded in purchasing workspace";
    const signature = JSON.stringify({ purchase_order_id: detail.id, lines: receiptLines, note });
    if (!receiptAttempt.current || receiptAttempt.current.signature !== signature) {
      const key = globalThis.crypto?.randomUUID?.() || "xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx".replace(/[xy]/g, ch => {
        const value = Math.random() * 16 | 0;
        return (ch === "x" ? value : (value & 3 | 8)).toString(16);
      });
      receiptAttempt.current = { signature, key };
    }
    setSaving(true); setError(""); setNotice("");
    try {
      const result = await apiRequest("/purchasing/orders/" + detail.id + "/grns", { method: "POST", body: JSON.stringify({ idempotency_key: receiptAttempt.current.key, lines: receiptLines, note }) });
      receiptAttempt.current = null;
      setNotice("GRN " + result.grn_number + " recorded. Stock remains unavailable until Quality Control accepts it."); await load(); await openOrder(detail.id);
    } catch (e) { setError(e.message || "Unable to record goods receipt. Retry without changing quantities to safely resume the same receipt."); }
    finally { setSaving(false); }
  }


  async function openGRN(id) {
    setGrnDetail(null); setError("");
    try {
      const data = await apiRequest("/purchasing/grns/" + id);
      setGrnDetail(data);
      const next = {};
      for (const line of data.lines || []) next[line.id] = String(Math.max(0, Number(line.received_quantity) - Number(line.accepted_quantity) - Number(line.rejected_quantity) - Number(line.damaged_quantity) - Number(line.quarantined_quantity)));
      setQcQuantities(next); setQcReason(""); qcAttempt.current = null;
    } catch (e) { setError(e.message || "Unable to load GRN quality details."); }
  }

  async function submitQC(e) {
    e.preventDefault(); if (!grnDetail) return;
    const lines = (grnDetail.lines || []).filter(line => Number(qcQuantities[line.id]) > 0).map(line => ({ goods_receipt_line_id: line.id, disposition: qcDisposition, quantity: Number(qcQuantities[line.id]), reason: qcReason.trim() || null }));
    if (!lines.length) { setError("Enter a quantity to inspect for at least one GRN line."); return; }
    const signature = JSON.stringify({ grn_id: grnDetail.id, lines });
    if (!qcAttempt.current || qcAttempt.current.signature !== signature) {
      const key = globalThis.crypto?.randomUUID?.() || "xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx".replace(/[xy]/g, ch => { const value = Math.random() * 16 | 0; return (ch === "x" ? value : (value & 3 | 8)).toString(16); });
      qcAttempt.current = { signature, key };
    }
    setSaving(true); setError(""); setNotice("");
    try {
      const result = await apiRequest("/purchasing/grns/" + grnDetail.id + "/qc", { method: "POST", body: JSON.stringify({ idempotency_key: qcAttempt.current.key, lines }) });
      qcAttempt.current = null; setNotice("Quality inspection saved. GRN status: " + label(result.status) + ".");
      await openGRN(grnDetail.id); await openOrder(detail.id);
    } catch (e) { setError(e.message || "Unable to save QC. Retry without changing quantities to safely resume."); }
    finally { setSaving(false); }
  }

  async function selectInvoiceGrn(grnId) {
    setInvoiceGrnDetail(null); setInvoiceQuantities({}); setInvoiceRates({}); setInvoiceGstRates({}); setInvoiceHsnSac({}); setError("");
    if (!grnId) return;
    try {
      const detail = await apiRequest("/purchasing/grns/" + grnId);
      setInvoiceGrnDetail(detail);
      setInvoiceRates(Object.fromEntries((detail.lines || []).map(line => [line.id, String(line.unit_cost || "0")])));
      setInvoiceGstRates(Object.fromEntries((detail.lines || []).map(line => [line.id, invoiceTaxRate])));
      const supplier = suppliers.find(item => Number(item.id) === Number(detail.supplier_id));
      setInvoiceSupplierGstin(supplier?.gstin || "");
    } catch (e) { setError(e.message || "Unable to load GRN for supplier invoice."); }
  }

  async function createSupplierInvoice(e) {
    e.preventDefault();
    if (!invoiceGrnDetail || !invoiceNumber.trim() || !invoiceDate) {
      setError("Select an accepted GRN and enter the supplier invoice number and date."); return;
    }
    const round2 = value => Math.round((value + Number.EPSILON) * 100) / 100;
    const lines = (invoiceGrnDetail.lines || []).filter(line => Number(invoiceQuantities[line.id]) > 0).map(line => {
      const quantity = Number(invoiceQuantities[line.id]);
      const unitRate = Number(invoiceRates[line.id]);
      const taxable = round2(quantity * unitRate);
      const lineRate = Number(invoiceGstRates[line.id] ?? invoiceTaxRate);
      const tax = round2(taxable * lineRate / 100);
      return {
        purchase_order_line_id: line.purchase_order_line_id, goods_receipt_line_id: line.id,
        quantity, unit_rate: unitRate, taxable_value: taxable, gst_rate: lineRate,
        cgst_amount: invoiceTaxMode === "intra" ? round2(tax / 2) : 0,
        sgst_amount: invoiceTaxMode === "intra" ? round2(tax - round2(tax / 2)) : 0,
        igst_amount: invoiceTaxMode === "inter" ? tax : 0,
        hsn_sac: invoiceHsnSac[line.id]?.trim() || null
      };
    });
    if (!lines.length || lines.some(line => !Number.isFinite(line.unit_rate) || line.unit_rate < 0 || !Number.isFinite(line.gst_rate) || line.gst_rate < 0 || line.gst_rate > 100)) {
      setError("Enter valid invoiced quantities, unit rates and GST rates for at least one accepted GRN line."); return;
    }
    const taxable = round2(lines.reduce((sum, line) => sum + line.taxable_value, 0));
    const cgst = round2(lines.reduce((sum, line) => sum + line.cgst_amount, 0));
    const sgst = round2(lines.reduce((sum, line) => sum + line.sgst_amount, 0));
    const igst = round2(lines.reduce((sum, line) => sum + line.igst_amount, 0));
    const cess = Number(invoiceCess || 0), freight = Number(invoiceFreight || 0), discount = Number(invoiceDiscount || 0);
    const total = round2(taxable + cgst + sgst + igst + cess + freight - discount);
    if (total <= 0 || [cess, freight, discount].some(value => !Number.isFinite(value) || value < 0)) {
      setError("Check invoice cess, freight, discount and total."); return;
    }
    setSaving(true); setError(""); setNotice("");
    try {
      const result = await apiRequest("/purchasing/supplier-invoices", {
        method: "POST", body: JSON.stringify({
          purchase_order_id: invoiceGrnDetail.purchase_order_id, invoice_number: invoiceNumber.trim(),
          invoice_date: invoiceDate, due_date: invoiceDueDate || null, supplier_gstin: invoiceSupplierGstin.trim() || null, taxable_value: taxable,
          cgst_amount: cgst, sgst_amount: sgst, igst_amount: igst, cess_amount: cess,
          freight_amount: freight, discount_amount: discount, invoice_total: total, lines
        })
      });
      setNotice("Supplier invoice " + result.invoice_number + " recorded as " + label(result.match_status) + ".");
      setInvoiceNumber(""); setInvoiceDueDate(""); setInvoiceGrnDetail(null); setInvoiceQuantities({}); setInvoiceSupplierGstin("");
      await loadSupplierFinance();
    } catch (e) { setError(e.message || "Unable to record supplier invoice."); }
    finally { setSaving(false); }
  }

  async function selectReturnGrn(grnId) {
    setReturnGrnDetail(null); setReturnQuantities({}); setReturnSupplierInvoiceId(""); setError("");
    if (!grnId) return;
    try {
      const detail = await apiRequest("/purchasing/grns/" + grnId);
      setReturnGrnDetail(detail);
      const eligibleInvoices = supplierInvoices.filter(invoice => Number(invoice.purchase_order_id) === Number(detail.purchase_order_id) && invoice.match_status === "approved");
      if (eligibleInvoices.length === 1) setReturnSupplierInvoiceId(String(eligibleInvoices[0].id));
    } catch (e) { setError(e.message || "Unable to load GRN for supplier return."); }
  }

  async function createSupplierReturn(e) {
    e.preventDefault();
    if (!returnGrnDetail || !returnSupplierInvoiceId) { setError("Select an accepted GRN and its approved supplier invoice."); return; }
    const lines = (returnGrnDetail.lines || []).filter(line => Number(returnQuantities[line.id]) > 0)
      .map(line => ({ goods_receipt_line_id: line.id, quantity: Number(returnQuantities[line.id]) }));
    if (!lines.length || !returnReason.trim()) { setError("Enter a return reason and at least one return quantity."); return; }
    setSaving(true); setError(""); setNotice("");
    try {
      const result = await apiRequest("/purchasing/supplier-returns", {
        method: "POST", body: JSON.stringify({
          goods_receipt_id: returnGrnDetail.id, supplier_invoice_id: Number(returnSupplierInvoiceId), reason: returnReason.trim(), lines
        })
      });
      setNotice("Supplier return " + result.return_number + " created as draft.");
      setReturnReason(""); setReturnGrnDetail(null); setReturnQuantities({}); setReturnSupplierInvoiceId("");
      await loadSupplierFinance();
    } catch (e) { setError(e.message || "Unable to create supplier return."); }
    finally { setSaving(false); }
  }

  async function confirmSupplierReturnCredit(ret) {
    const voucherId = Number(returnVoucherIds[ret.id]);
    const debitNote = String(returnDebitNotes[ret.id] || "").trim();
    const debitDate = returnDebitDates[ret.id];
    if (!Number.isInteger(voucherId) || voucherId <= 0 || !debitNote || !debitDate) {
      setError("Enter the posted debit-note voucher ID, debit-note number and date."); return;
    }
    setSaving(true); setError(""); setNotice("");
    try {
      const result = await apiRequest("/purchasing/supplier-returns/" + ret.id + "/credit", {
        method: "POST", body: JSON.stringify({ accounting_voucher_id: voucherId, debit_note_number: debitNote, debit_note_date: debitDate })
      });
      setNotice("Supplier return credit confirmed against debit note " + result.debit_note_number + ".");
      await loadSupplierFinance();
    } catch (e) { setError(e.message || "Unable to confirm supplier return credit."); }
    finally { setSaving(false); }
  }

  const visibleOrders = useMemo(() => orders.filter(po => {
    const statusMatch = orderStatusFilter === "all" || po.status === orderStatusFilter;
    const q = orderSearch.trim().toLowerCase();
    const searchMatch = !q || [po.purchase_number, po.supplier_name, po.location_name, po.status]
      .some(value => String(value || "").toLowerCase().includes(q));
    return statusMatch && searchMatch;
  }), [orders, orderStatusFilter, orderSearch]);
  const openOrders = orders.filter(po => ["ordered", "partially_received"].includes(po.status));
  const draftOrders = orders.filter(po => po.status === "draft");
  const receivedOrders = orders.filter(po => po.status === "received");
  const totalOpenValue = orders.filter(po => !["received", "cancelled"].includes(po.status))
    .reduce((sum, po) => sum + Number(po.subtotal || 0), 0);
  const visibleSuppliers = suppliers.filter(s => [s.name, s.contact_name, s.phone, s.email, s.gstin].some(v => String(v || "").toLowerCase().includes(supplierSearch.trim().toLowerCase())));

  return <section className="sb-workspace sb-purchasing">
    <button className="sb-back" type="button" onClick={onBack}>← All workspaces</button>
    <p className="sb-eyebrow">OPERATIONS · PURCHASING</p><h1>Purchasing</h1>
    <p>Control supplier purchasing, approvals, purchase orders and goods receipts with live inventory posting.</p>
    {error && <p className="sb-alert" role="alert">{error}</p>}{notice && <p className="sb-success" role="status">{notice}</p>}
    <div className="sb-purchasing-kpis">
      <article><span>Active suppliers</span><strong>{suppliers.length}</strong><small>Approved supplier records</small></article>
      <article><span>Open purchase orders</span><strong>{openOrders.length}</strong><small>Ordered or partially received</small></article>
      <article><span>Awaiting approval</span><strong>{draftOrders.length}</strong><small>Draft orders</small></article>
      <article><span>Received orders</span><strong>{receivedOrders.length}</strong><small>Fully received</small></article>
      <article className="is-highlight"><span>Open PO value</span><strong>{money(totalOpenValue)}</strong><small>Excludes cancelled and received POs</small></article>
    </div>
    <div className="sb-customer-tabs" role="tablist" aria-label="Purchasing workspace">
      <button type="button" role="tab" aria-selected={tab === "overview"} className={tab === "overview" ? "is-active" : ""} onClick={() => setTab("overview")}>Overview</button>
      <button type="button" role="tab" aria-selected={tab === "requests"} className={tab === "requests" ? "is-active" : ""} onClick={() => setTab("requests")}>Requisitions & RFQs</button>
      <button type="button" role="tab" aria-selected={tab === "orders"} className={tab === "orders" ? "is-active" : ""} onClick={() => setTab("orders")}>Purchase orders <span>{orders.length}</span></button>
      <button type="button" role="tab" aria-selected={tab === "suppliers"} className={tab === "suppliers" ? "is-active" : ""} onClick={() => setTab("suppliers")}>Suppliers <span>{suppliers.length}</span></button>
      <button type="button" role="tab" aria-selected={tab === "invoices"} className={tab === "invoices" ? "is-active" : ""} onClick={() => setTab("invoices")}>Supplier invoices</button>
      <button type="button" role="tab" aria-selected={tab === "returns"} className={tab === "returns" ? "is-active" : ""} onClick={() => setTab("returns")}>Supplier returns</button>
    </div>
    {tab === "overview" ? <>
      <section className="sb-purchasing-overview">
        <div className="sb-purchasing-overview-head"><div><h2>Procurement workflow</h2><p>Follow each order from request through receipt and inventory posting.</p></div><button className="sb-primary" type="button" onClick={() => setTab("orders")}>Create / manage purchase orders</button></div>
        <div className="sb-purchasing-steps">
          {["Requisition", "Approval", "Supplier RFQ", "Quotation award", "Purchase order", "GRN & QC", "Inventory posting", "Invoice & AP"].map((step, index) => <div key={step}><span>{String(index + 1).padStart(2, "0")}</span><strong>{step}</strong></div>)}
        </div>
        <div className="sb-purchasing-overview-columns">
          <div className="sb-purchasing-panel"><h3>Orders requiring attention</h3>
            {draftOrders.length || openOrders.length ? [...draftOrders, ...openOrders].slice(0, 6).map(po => <button type="button" className="sb-purchasing-attention-row" key={po.id} onClick={() => { setTab("orders"); openOrder(po.id); }}><span><strong>{po.purchase_number}</strong><small>{po.supplier_name}</small></span><em>{label(po.status)}</em></button>) : <p className="sb-empty">No outstanding purchase orders.</p>}
          </div>
          <div className="sb-purchasing-panel"><h3>Quick actions</h3>
            <button type="button" onClick={() => setTab("suppliers")}>＋ Add / review suppliers</button>
            <button type="button" onClick={() => setTab("requests")}>＋ Create purchase requisition / RFQ</button>
            <button type="button" onClick={() => setTab("orders")}>＋ Create purchase order</button>
            <p className="sb-muted">Goods receipts and accepted QC quantities update the existing inventory movement and cost-layer ledgers transactionally.</p>
          </div>
        </div>
        <p className="sb-purchasing-boundary"><strong>Operational boundary:</strong> supplier payment allocation reconciles an already-posted Accounting payment voucher; it does not initiate a bank transfer. Landed-cost allocation remains a separately controlled valuation workflow and is not yet represented as completed.</p>
      </section>
    </> : tab === "requests" ? <PurchasingRequestsWorkspace suppliers={suppliers} locations={locations} variants={variants} onPurchaseOrderCreated={async po => { setTab("orders"); await load(); await openOrder(po.id); setNotice(`Quotation awarded. Draft PO ${po.purchase_number} created and still requires purchase approval.`); }} /> : tab === "suppliers" ? <>
      <form className="sb-customer-form" onSubmit={createSupplier}>
        <h2>{supplierEditId ? "Edit supplier" : "Add supplier"}</h2><div className="sb-customer-fields">
          <label>Supplier name *<input required maxLength="200" value={supplierForm.name} onChange={e => setSupplierForm(o => ({ ...o, name: e.target.value }))} /></label>
          <label>Contact person<input maxLength="200" value={supplierForm.contact_name} onChange={e => setSupplierForm(o => ({ ...o, contact_name: e.target.value }))} /></label>
          <label>Phone<input maxLength="30" value={supplierForm.phone} onChange={e => setSupplierForm(o => ({ ...o, phone: e.target.value }))} /></label>
          <label>Email<input type="email" maxLength="254" value={supplierForm.email} onChange={e => setSupplierForm(o => ({ ...o, email: e.target.value }))} /></label>
          <label>GSTIN<input minLength="15" maxLength="15" value={supplierForm.gstin} onChange={e => setSupplierForm(o => ({ ...o, gstin: e.target.value.toUpperCase() }))} /></label>
          <label>Address<input maxLength="1000" value={supplierForm.address} onChange={e => setSupplierForm(o => ({ ...o, address: e.target.value }))} /></label>
        </div><button className="sb-primary" type="submit" disabled={saving}>{saving ? "Saving…" : supplierEditId ? "Save supplier" : "Create supplier"}</button>{supplierEditId && <button type="button" onClick={() => { setSupplierEditId(null); setSupplierForm(emptySupplier); }}>Cancel edit</button>}
      </form>
      <label className="sb-customer-search">Search suppliers<input type="search" value={supplierSearch} onChange={e => setSupplierSearch(e.target.value)} placeholder="Name, phone, email or GSTIN" /></label><div className="sb-customer-list">{visibleSuppliers.map(s => <article className="sb-customer-card" key={s.id}><div className="sb-customer-avatar">{s.name.slice(0,1).toUpperCase()}</div><div className="sb-customer-info"><strong>{s.name}</strong><small>{s.contact_name || "No contact"} · {s.phone || "No phone"}</small><small>{s.email || "No email"}{s.gstin ? " · GSTIN " + s.gstin : ""}</small></div><span className="sb-order-status status-delivered">Active</span><button type="button" onClick={() => editSupplier(s)}>Edit</button></article>)}</div>
    </> : tab === "invoices" ? <>
      <div className="sb-customer-toolbar"><h2>Supplier invoices & payments</h2><button type="button" onClick={loadSupplierFinance} disabled={financeLoading}>{financeLoading ? "Loading…" : "Refresh"}</button></div>
      <p className="sb-muted">Record supplier invoices against QC-accepted, uninvoiced GRN quantities. Approval posts AP/GRNI and input GST. Payment allocation only reconciles an already-posted Accounting payment voucher; it does not initiate a bank transfer.</p>
      <form className="sb-customer-form" onSubmit={createSupplierInvoice}>
        <h3>Record supplier invoice</h3>
        <label>Accepted GRN<select value={invoiceGrnDetail?.id || ""} onChange={e => selectInvoiceGrn(e.target.value)}><option value="">Choose GRN</option>{returnGrns.filter(g => ["accepted", "partially_accepted"].includes(g.status)).map(g => <option key={g.id} value={g.id}>{g.grn_number} · {g.supplier_name} · {g.purchase_number}</option>)}</select></label>
        <div className="sb-customer-fields">
          <label>Supplier invoice number *<input required maxLength="100" value={invoiceNumber} onChange={e => setInvoiceNumber(e.target.value)} /></label>
          <label>Supplier GSTIN<input minLength="15" maxLength="15" value={invoiceSupplierGstin} onChange={e => setInvoiceSupplierGstin(e.target.value.toUpperCase())} /></label>
          <label>Invoice date *<input required type="date" value={invoiceDate} onChange={e => setInvoiceDate(e.target.value)} /></label>
          <label>Due date<input type="date" min={invoiceDate} value={invoiceDueDate} onChange={e => setInvoiceDueDate(e.target.value)} /></label>
          <label>GST type<select value={invoiceTaxMode} onChange={e => setInvoiceTaxMode(e.target.value)}><option value="intra">Intra-state (CGST + SGST)</option><option value="inter">Inter-state (IGST)</option></select></label>
        </div>
        {invoiceGrnDetail && <div className="sb-purchase-detail-lines">{invoiceGrnDetail.lines.filter(line => Number(line.accepted_quantity) > 0).map(line => <div className="sb-purchase-detail-line" key={line.id}>
          <div><strong>{line.product_name} · {line.sku}</strong><small>Accepted {line.accepted_quantity} · GRN batch {line.batch_code || "—"}</small></div>
          <label>Invoice qty<input type="number" min="0" max={Number(line.accepted_quantity)} step="0.001" value={invoiceQuantities[line.id] || ""} onChange={e => setInvoiceQuantities(old => ({ ...old, [line.id]: e.target.value }))} /></label>
          <label>Unit rate ₹<input type="number" min="0" step="0.01" value={invoiceRates[line.id] ?? ""} onChange={e => setInvoiceRates(old => ({ ...old, [line.id]: e.target.value }))} /></label>
          <label>GST rate %<input type="number" min="0" max="100" step="0.01" value={invoiceGstRates[line.id] ?? invoiceTaxRate} onChange={e => setInvoiceGstRates(old => ({ ...old, [line.id]: e.target.value }))} /></label>
          <label>HSN/SAC<input maxLength="8" value={invoiceHsnSac[line.id] || ""} onChange={e => setInvoiceHsnSac(old => ({ ...old, [line.id]: e.target.value.toUpperCase() }))} /></label>
        </div>)}</div>}
        <div className="sb-customer-fields">
          <label>Freight ₹<input type="number" min="0" step="0.01" value={invoiceFreight} onChange={e => setInvoiceFreight(e.target.value)} /></label>
          <label>Discount ₹<input type="number" min="0" step="0.01" value={invoiceDiscount} onChange={e => setInvoiceDiscount(e.target.value)} /></label>
          <label>Cess ₹<input type="number" min="0" step="0.01" value={invoiceCess} onChange={e => setInvoiceCess(e.target.value)} /></label>
        </div>
        <p className="sb-muted">Invoice totals are calculated from the entered quantities, rates, GST, freight, discount and cess. Cess invoices can be recorded, but approval remains blocked until a configured input-cess ledger exists.</p>
        <button className="sb-primary" type="submit" disabled={saving || !invoiceGrnDetail}>{saving ? "Saving…" : "Record supplier invoice"}</button>
      </form>
      {financeLoading ? <p className="sb-empty">Loading supplier invoices…</p> : supplierInvoices.length ? <div className="sb-customer-list">
        {supplierInvoices.map(invoice => <article className="sb-order-card" key={invoice.id}>
          <div className="sb-order-open"><span><strong>{invoice.invoice_number}</strong><small>{invoice.supplier_name} · {invoice.purchase_number} · {invoice.invoice_date}</small></span><span className="sb-order-total">{money(invoice.invoice_total)}<small>Paid {money(invoice.paid_amount)}</small></span><span className={"sb-order-status status-" + invoice.match_status}>{label(invoice.match_status)}</span></div>
          <div className="sb-purchase-detail-line">
            {invoice.match_status === "matched" && <button className="sb-primary" type="button" disabled={saving} onClick={() => approveSupplierInvoice(invoice)}>Approve & post AP/GRNI</button>}
            {["variance", "blocked", "matched"].includes(invoice.match_status) && <button type="button" disabled={saving} onClick={() => rejectSupplierInvoice(invoice)}>Reject invoice</button>}
            {invoice.match_status === "variance" && <><button type="button" disabled={saving} onClick={() => resolveSupplierInvoiceVariance(invoice)}>Resolve reviewed variance</button><small>Resolution is allowed only if invoice net GRNI equals the received stock value. Otherwise reject or correct the invoice.</small></>}
            {invoice.match_status === "blocked" && <small>Invoice net GRNI differs from the received stock value. Approval is blocked until the invoice is corrected or the accounting policy is reviewed.</small>}
            {invoice.match_status === "approved" && <><label>Posted payment voucher ID<input type="number" min="1" value={paymentVoucherIds[invoice.id] || ""} onChange={e => setPaymentVoucherIds(old => ({ ...old, [invoice.id]: e.target.value }))} /></label><label>Allocate amount ₹<input type="number" min="0.01" step="0.01" value={paymentAmounts[invoice.id] || ""} onChange={e => setPaymentAmounts(old => ({ ...old, [invoice.id]: e.target.value }))} /></label><button type="button" disabled={saving} onClick={() => allocateSupplierPayment(invoice)}>Allocate payment</button></>}
          </div>
        </article>)}
      </div> : <p className="sb-empty">No supplier invoices recorded yet. Record and match invoices through the purchasing API before approving them.</p>}
    </> : tab === "returns" ? <>
      <div className="sb-customer-toolbar"><h2>Supplier returns</h2><button type="button" onClick={loadSupplierFinance} disabled={financeLoading}>{financeLoading ? "Loading…" : "Refresh"}</button></div>
      <p className="sb-muted">Create returns against QC-accepted GRN batches. Dispatch removes only unreserved remaining valued stock. Credit confirmation requires a posted supplier debit-note voucher that matches the returned inventory valuation excluding GST.</p>
      <form className="sb-customer-form" onSubmit={createSupplierReturn}>
        <h3>Create supplier return</h3>
        <label>Accepted GRN<select value={returnGrnDetail?.id || ""} onChange={e => selectReturnGrn(e.target.value)}><option value="">Choose GRN</option>{returnGrns.filter(g => ["accepted", "partially_accepted"].includes(g.status)).map(g => <option key={g.id} value={g.id}>{g.grn_number} · {g.supplier_name} · {g.purchase_number}</option>)}</select></label>
        {returnGrnDetail && <label>Approved supplier invoice<select required value={returnSupplierInvoiceId} onChange={e => setReturnSupplierInvoiceId(e.target.value)}><option value="">Choose approved invoice</option>{supplierInvoices.filter(invoice => Number(invoice.purchase_order_id) === Number(returnGrnDetail.purchase_order_id) && invoice.match_status === "approved").map(invoice => <option key={invoice.id} value={invoice.id}>{invoice.invoice_number} · {invoice.supplier_name} · {money(invoice.invoice_total)}</option>)}</select></label>}
        {returnGrnDetail && <div className="sb-purchase-detail-lines">{returnGrnDetail.lines.filter(line => Number(line.accepted_quantity) > 0).map(line => <div className="sb-purchase-detail-line" key={line.id}>
          <div><strong>{line.product_name} · {line.sku}</strong><small>QC accepted {line.accepted_quantity} · batch {line.batch_code || "—"} · expiry {line.expiry_date || "—"}</small></div>
          <label>Return quantity<input type="number" min="0" max={Number(line.accepted_quantity)} step="0.001" value={returnQuantities[line.id] || ""} onChange={e => setReturnQuantities(old => ({ ...old, [line.id]: e.target.value }))} /></label>
        </div>)}</div>}
        <label>Return reason<input required maxLength="2000" value={returnReason} onChange={e => setReturnReason(e.target.value)} /></label>
        <button className="sb-primary" type="submit" disabled={saving || !returnGrnDetail || !returnSupplierInvoiceId}>{saving ? "Saving…" : "Create draft supplier return"}</button>
      </form>
      {financeLoading ? <p className="sb-empty">Loading supplier returns…</p> : supplierReturns.length ? <div className="sb-customer-list">
        {supplierReturns.map(ret => <article className="sb-order-card" key={ret.id}>
          <div className="sb-order-open"><span><strong>{ret.return_number}</strong><small>{ret.supplier_name} · {ret.purchase_number} · {ret.line_count} lines</small></span><span className={"sb-order-status status-" + ret.status}>{label(ret.status)}</span></div>
          <p className="sb-muted">{ret.reason}</p>
          <div className="sb-purchase-detail-line">
            {ret.status === "draft" && <button type="button" disabled={saving} onClick={() => advanceSupplierReturn(ret, "submit")}>Submit return</button>}
            {ret.status === "submitted" && <button className="sb-primary" type="button" disabled={saving} onClick={() => advanceSupplierReturn(ret, "approve")}>Approve return</button>}
            {ret.status === "approved" && <button type="button" disabled={saving} onClick={() => advanceSupplierReturn(ret, "dispatch")}>Dispatch return stock</button>}
            {ret.status === "dispatched" && <><label>Posted debit-note voucher ID<input type="number" min="1" value={returnVoucherIds[ret.id] || ""} onChange={e => setReturnVoucherIds(old => ({ ...old, [ret.id]: e.target.value }))} /></label><label>Debit-note number<input maxLength="100" value={returnDebitNotes[ret.id] || ""} onChange={e => setReturnDebitNotes(old => ({ ...old, [ret.id]: e.target.value }))} /></label><label>Debit-note date<input type="date" value={returnDebitDates[ret.id] || ""} onChange={e => setReturnDebitDates(old => ({ ...old, [ret.id]: e.target.value }))} /></label><button type="button" disabled={saving} onClick={() => confirmSupplierReturnCredit(ret)}>Confirm supplier credit</button></>}
            {ret.status === "credited" && <small>Debit note {ret.debit_note_number || "recorded"} confirmed.</small>}
          </div>
        </article>)}
      </div> : <p className="sb-empty">No supplier returns recorded yet. Create a return against an accepted GRN batch through the return workflow.</p>}
    </> : <>
      <form className="sb-customer-form" onSubmit={createOrder}>
        <h2>{orderEditId ? "Edit draft purchase order" : "Create purchase order"}</h2><div className="sb-customer-fields">
          <label>Supplier *<select required value={supplierId} onChange={e => setSupplierId(e.target.value)}><option value="">Choose supplier</option>{suppliers.map(s => <option key={s.id} value={s.id}>{s.name}</option>)}</select></label>
          <label>Receive into location *<select required value={locationId} onChange={e => setLocationId(e.target.value)}><option value="">Choose location</option>{locations.map(l => <option key={l.id} value={l.id}>{l.name}</option>)}</select></label>
          <label className="sb-span-all">Notes<input maxLength="2000" value={notes} onChange={e => setNotes(e.target.value)} /></label>
        </div>
        <div className="sb-purchase-lines"><div className="sb-purchase-lines-head"><strong>Order lines</strong><button type="button" onClick={() => setLines(old => [...old, { ...emptyLine }])}>+ Add line</button></div>
          {lines.map((line, i) => <div className="sb-purchase-line" key={i}>
            <label>Product variant *<select required value={line.variant_id} onChange={e => setLine(i, "variant_id", e.target.value)}><option value="">Choose variant</option>{variants.map(v => <option key={v.id} value={v.id}>{v.product_name || v.name || ("Product " + v.product_id)} · {v.sku || ("Variant " + v.id)}</option>)}</select></label>
            <label>Quantity<input required type="number" min="0.001" step="0.001" value={line.quantity} onChange={e => setLine(i, "quantity", e.target.value)} /></label>
            <label>Unit cost ₹<input required type="number" min="0" step="0.01" value={line.unit_cost} onChange={e => setLine(i, "unit_cost", e.target.value)} /></label>
            {lines.length > 1 && <button type="button" className="sb-remove-line" onClick={() => setLines(old => old.filter((_, n) => n !== i))} aria-label={"Remove line " + (i + 1)}>×</button>}
          </div>)}
          <p className="sb-purchase-total">Estimated subtotal <strong>{money(lines.reduce((sum, line) => sum + Math.max(0, Number(line.quantity) || 0) * Math.max(0, Number(line.unit_cost) || 0), 0))}</strong></p>
        </div>
        <button className="sb-primary" type="submit" disabled={saving || !suppliers.length || !locations.length}>{saving ? "Saving…" : orderEditId ? "Save draft changes" : "Create purchase order"}</button>{orderEditId && <button type="button" onClick={() => { setOrderEditId(null); setSupplierId(""); setLocationId(""); setNotes(""); setLines([{ ...emptyLine }]); }}>Cancel edit</button>}
        {!suppliers.length && <small>Add a supplier first. </small>}{!locations.length && <small>Create an active inventory location first.</small>}
      </form>
      <div className="sb-customer-toolbar"><label>Search purchase orders<input type="search" value={orderSearch} onChange={e => setOrderSearch(e.target.value)} placeholder="PO number, supplier or location" /></label><label>Filter orders<select value={orderStatusFilter} onChange={e => setOrderStatusFilter(e.target.value)}><option value="all">All statuses</option><option value="ordered">Ordered</option><option value="partially_received">Partially received</option><option value="received">Received</option><option value="cancelled">Cancelled</option><option value="draft">Draft</option></select></label><span>{visibleOrders.length} shown of {orders.length}</span><button type="button" onClick={load} disabled={loading}>{loading ? "Loading…" : "Refresh orders"}</button></div>
      {loading ? <p className="sb-empty">Loading purchase orders…</p> : visibleOrders.length ? <div className="sb-customer-list">{visibleOrders.map(po => <article className={"sb-order-card " + (selected === po.id ? "is-selected" : "")} key={po.id}>
        <button type="button" className="sb-order-open" onClick={() => openOrder(po.id)}><span><strong>{po.purchase_number}</strong><small>{po.supplier_name} · {po.location_name}</small></span><span className="sb-order-total">{money(po.subtotal)}<small>{po.line_count} lines</small></span><span className={"sb-order-status status-" + po.status}>{label(po.status)}</span></button>
        {selected === po.id && detail && <div className="sb-purchase-detail"><h3>{detail.purchase_number} · {detail.status === "draft" ? "Approval required" : "Goods receipt"}</h3>{detail.status === "draft" && <div className="sb-purchase-approval"><button type="button" onClick={() => editDraftOrder(detail)}>Edit draft</button><p className="sb-muted">Draft orders cannot receive stock until approved.</p><button className="sb-primary" type="button" onClick={approveOrder} disabled={saving}>{saving ? "Saving…" : "Approve purchase order"}</button></div>}{receiptHistory.length > 0 && <section className="sb-purchase-receipt-history" aria-label="Goods receipt history"><h4>Goods receipt history</h4>{receiptHistory.map(receipt => <article key={receipt.idempotency_key}><div><strong>{new Date(receipt.received_at).toLocaleString()}</strong><small>Receipt {receipt.idempotency_key.slice(0, 8)} · {receipt.note || "No note"}</small></div><ul>{receipt.lines.map(line => <li key={line.movement_id}>{line.product_name} ({line.sku}) — {line.quantity}</li>)}</ul></article>)}</section>}<div className="sb-purchase-detail-lines">{detail.lines.map(line => <div className="sb-purchase-detail-line" key={line.line_id}><div><strong>{line.product_name}</strong><small>SKU {line.sku} · ordered {line.quantity_ordered} · received {line.quantity_received} · open {line.quantity_open}</small></div><label>Receive qty<input type="number" min="0" max={Number(line.quantity_open)} step="0.001" disabled={Number(line.quantity_open) <= 0 || detail.status === "cancelled" || detail.status === "received"} value={receipts[line.line_id] ?? ""} onChange={e => setReceipts(old => ({ ...old, [line.line_id]: e.target.value }))} /></label>
            <label>Batch / lot<input maxLength="120" value={receiptMeta[line.line_id]?.batch_code || ""} onChange={e => setReceiptMeta(old => ({ ...old, [line.line_id]: { ...old[line.line_id], batch_code: e.target.value } }))} /></label>
            <label>Manufactured<input type="date" value={receiptMeta[line.line_id]?.manufacture_date || ""} onChange={e => setReceiptMeta(old => ({ ...old, [line.line_id]: { ...old[line.line_id], manufacture_date: e.target.value } }))} /></label>
            <label>Expiry<input type="date" value={receiptMeta[line.line_id]?.expiry_date || ""} onChange={e => setReceiptMeta(old => ({ ...old, [line.line_id]: { ...old[line.line_id], expiry_date: e.target.value } }))} /></label></div>)}</div>
          {grnHistory.length > 0 && <section className="sb-purchase-receipt-history" aria-label="Goods receipt notes and quality control">
            <h4>Goods receipt notes / Quality Control</h4>
            {grnHistory.map(grn => <article key={grn.id}><div><strong>{grn.grn_number}</strong><small>{label(grn.status)} · {new Date(grn.received_at).toLocaleString()}</small></div><button type="button" onClick={() => openGRN(grn.id)}>Inspect / record QC</button></article>)}
          </section>}
          {grnDetail && <section className="sb-purchase-receipt-history" aria-label="Quality inspection">
            <h4>{grnDetail.grn_number} · Quality inspection</h4>
            <p className="sb-muted">Only accepted quantities are posted to saleable stock. Rejected, damaged and quarantined quantities remain out of available inventory.</p>
            <div className="sb-purchase-detail-lines">{grnDetail.lines.map(line => <div className="sb-purchase-detail-line" key={line.id}>
              <div><strong>{line.product_name} · {line.sku}</strong><small>Received {line.received_quantity} · accepted {line.accepted_quantity} · rejected {line.rejected_quantity} · damaged {line.damaged_quantity} · quarantined {line.quarantined_quantity}</small><small>Batch {line.batch_code || "—"} · expiry {line.expiry_date || "—"}</small></div>
              <label>Inspect quantity<input type="number" min="0" max={Math.max(0, Number(line.received_quantity)-Number(line.accepted_quantity)-Number(line.rejected_quantity)-Number(line.damaged_quantity)-Number(line.quarantined_quantity))} step="0.001" value={qcQuantities[line.id] ?? "0"} onChange={e => setQcQuantities(old => ({ ...old, [line.id]: e.target.value }))} /></label>
            </div>)}</div>
            <form onSubmit={submitQC}>
              <label>Disposition<select value={qcDisposition} onChange={e => setQcDisposition(e.target.value)}><option value="accepted">Accepted — release to saleable stock</option><option value="rejected">Rejected</option><option value="damaged">Damaged</option><option value="quarantined">Quarantined</option></select></label>
              <label>Inspection note<input maxLength="1000" value={qcReason} onChange={e => setQcReason(e.target.value)} /></label>
              <button className="sb-primary" type="submit" disabled={saving}>{saving ? "Saving…" : "Save QC disposition"}</button>
            </form>
          </section>}
          {detail.status !== "received" && detail.status !== "cancelled" && <form onSubmit={receiveGoods}><button className="sb-primary" type="submit" disabled={saving}>{saving ? "Saving…" : "Record GRN (awaiting QC)"}</button></form>}
          {(detail.status === "ordered" || detail.status === "partially_received") && <button type="button" className="sb-remove-line" onClick={cancelOrder} disabled={saving}>{saving ? "Saving…" : "Cancel remaining quantities"}</button>}
          {detail.status === "cancelled" && <p className="sb-muted">Cancelled. Any goods received before cancellation remain in inventory.</p>}
        </div>}
      </article>)}</div> : <p className="sb-empty">{orders.length ? "No purchase orders match this status." : "No purchase orders yet."}</p>}
    </>}
    <OrganisationPolicyPanel domain="purchase" />
  </section>;
}
