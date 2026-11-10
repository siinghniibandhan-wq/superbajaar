import { useCallback, useEffect, useMemo, useState } from "react";
import { apiRequest } from "../../services/api.js";

const money = value => new Intl.NumberFormat("en-IN", { style: "currency", currency: "INR" }).format(Number(value || 0));
const title = value => String(value || "—").replaceAll("_", " ").replace(/\b\w/g, char => char.toUpperCase());
const blankLine = () => ({ variant_id: "", quantity: "1", estimated_unit_cost: "", specification: "" });

export default function PurchasingRequestsWorkspace({ suppliers = [], locations = [], variants = [], onPurchaseOrderCreated }) {
  const [requisitions, setRequisitions] = useState([]);
  const [rfqs, setRfqs] = useState([]);
  const [selectedRequisition, setSelectedRequisition] = useState(null);
  const [selectedRfq, setSelectedRfq] = useState(null);
  const [locationId, setLocationId] = useState("");
  const [department, setDepartment] = useState("");
  const [costCentre, setCostCentre] = useState("");
  const [requiredBy, setRequiredBy] = useState("");
  const [justification, setJustification] = useState("");
  const [requestLines, setRequestLines] = useState([blankLine()]);
  const [rfqSupplierIds, setRfqSupplierIds] = useState([]);
  const [rfqDueAt, setRfqDueAt] = useState("");
  const [rfqTerms, setRfqTerms] = useState("");
  const [quotationNumber, setQuotationNumber] = useState("");
  const [quotationSupplierId, setQuotationSupplierId] = useState("");
  const [quotationValidUntil, setQuotationValidUntil] = useState("");
  const [quotationLeadTime, setQuotationLeadTime] = useState("");
  const [quotationFreight, setQuotationFreight] = useState("0");
  const [quotationDiscount, setQuotationDiscount] = useState("0");
  const [quotationTax, setQuotationTax] = useState("0");
  const [quotationPaymentTerms, setQuotationPaymentTerms] = useState("");
  const [quotationDeliveryTerms, setQuotationDeliveryTerms] = useState("");
  const [quotationLines, setQuotationLines] = useState({});
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");

  const loadLists = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      const [requestResult, rfqResult] = await Promise.all([
        apiRequest("/purchasing/requisitions?limit=200"),
        apiRequest("/purchasing/rfqs?limit=200"),
      ]);
      setRequisitions(requestResult.items || []);
      setRfqs(rfqResult.items || []);
    } catch (err) {
      setError(err.message || "Unable to load requisitions and RFQs.");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { loadLists(); }, [loadLists]);

  const approvedRequisitions = useMemo(() => requisitions.filter(item => ["approved", "partially_ordered"].includes(item.status)), [requisitions]);

  function updateRequestLine(index, field, value) {
    setRequestLines(current => current.map((line, lineIndex) => lineIndex === index ? { ...line, [field]: value } : line));
  }

  async function createRequisition(event) {
    event.preventDefault();
    setSaving(true); setError(""); setNotice("");
    try {
      const payload = {
        location_id: Number(locationId),
        department: department.trim() || null,
        cost_centre: costCentre.trim() || null,
        required_by: requiredBy || null,
        justification: justification.trim(),
        lines: requestLines.map(line => ({
          variant_id: Number(line.variant_id),
          quantity: Number(line.quantity),
          estimated_unit_cost: line.estimated_unit_cost === "" ? null : Number(line.estimated_unit_cost),
          specification: line.specification.trim() || null,
        })),
      };
      if (!payload.location_id || !payload.justification || payload.lines.some(line => !line.variant_id || !Number.isFinite(line.quantity) || line.quantity <= 0 || (line.estimated_unit_cost !== null && (!Number.isFinite(line.estimated_unit_cost) || line.estimated_unit_cost < 0)))) {
        throw new Error("Choose a location and variant, enter positive quantities, valid estimated costs and a justification.");
      }
      const created = await apiRequest("/purchasing/requisitions", { method: "POST", body: JSON.stringify(payload) });
      setNotice(`Requisition ${created.requisition_number} created as a draft.`);
      setLocationId(""); setDepartment(""); setCostCentre(""); setRequiredBy(""); setJustification(""); setRequestLines([blankLine()]);
      await loadLists();
      await openRequisition(created.id);
    } catch (err) {
      setError(err.message || "Unable to create requisition.");
    } finally { setSaving(false); }
  }

  async function openRequisition(id) {
    setError("");
    try {
      const detail = await apiRequest(`/purchasing/requisitions/${id}`);
      setSelectedRequisition(detail);
    } catch (err) { setError(err.message || "Unable to load requisition."); }
  }

  async function submitRequisition() {
    if (!selectedRequisition) return;
    setSaving(true); setError(""); setNotice("");
    try {
      await apiRequest(`/purchasing/requisitions/${selectedRequisition.id}/submit`, { method: "POST" });
      setNotice(`${selectedRequisition.requisition_number} submitted for configured approval.`);
      await loadLists(); await openRequisition(selectedRequisition.id);
    } catch (err) { setError(err.message || "Unable to submit requisition."); }
    finally { setSaving(false); }
  }

  async function decideRequisition(decision) {
    if (!selectedRequisition) return;
    const reason = decision === "reject" ? window.prompt("Enter the reason for rejecting this requisition:") : window.prompt("Approval note (optional):") || "";
    if (reason === null) return;
    if (decision === "reject" && reason.trim().length < 3) { setError("A rejection reason of at least 3 characters is required."); return; }
    setSaving(true); setError(""); setNotice("");
    try {
      const result = await apiRequest(`/purchasing/requisitions/${selectedRequisition.id}/decision?decision=${decision}`, {
        method: "POST", body: JSON.stringify({ reason: reason.trim() || null }),
      });
      setNotice(result.status === "approved" ? "Requisition approved." : `Requisition ${title(result.status).toLowerCase()}.`);
      await loadLists(); await openRequisition(selectedRequisition.id);
    } catch (err) { setError(err.message || "Unable to record requisition decision."); }
    finally { setSaving(false); }
  }

  async function createRfq(event) {
    event.preventDefault();
    if (!selectedRequisition) return;
    setSaving(true); setError(""); setNotice("");
    try {
      const created = await apiRequest("/purchasing/rfqs", {
        method: "POST",
        body: JSON.stringify({
          requisition_id: selectedRequisition.id,
          supplier_ids: rfqSupplierIds.map(Number),
          response_due_at: rfqDueAt ? new Date(rfqDueAt).toISOString() : null,
          terms: rfqTerms.trim() || null,
        }),
      });
      setNotice(`RFQ ${created.rfq_number} created. Issue it when the invitation details are ready.`);
      setRfqSupplierIds([]); setRfqDueAt(""); setRfqTerms("");
      await loadLists(); await openRfq(created.id);
    } catch (err) { setError(err.message || "Unable to create RFQ."); }
    finally { setSaving(false); }
  }

  async function openRfq(id) {
    setError("");
    try {
      const detail = await apiRequest(`/purchasing/rfqs/${id}`);
      setSelectedRfq(detail);
      setQuotationLines(Object.fromEntries((detail.lines || []).map(line => [line.variant_id, {
        quantity: String(line.quantity), unit_price: "", hsn_sac: "", gst_rate: "",
      }])));
      setQuotationSupplierId(""); setQuotationNumber(""); setQuotationValidUntil(""); setQuotationLeadTime("");
      setQuotationFreight("0"); setQuotationDiscount("0"); setQuotationTax("0");
      setQuotationPaymentTerms(""); setQuotationDeliveryTerms("");
    } catch (err) { setError(err.message || "Unable to load RFQ details."); }
  }

  async function issueRfq() {
    if (!selectedRfq) return;
    setSaving(true); setError(""); setNotice("");
    try {
      await apiRequest(`/purchasing/rfqs/${selectedRfq.id}/issue`, { method: "POST" });
      setNotice(`${selectedRfq.rfq_number} issued to its invited suppliers.`);
      await loadLists(); await openRfq(selectedRfq.id);
    } catch (err) { setError(err.message || "Unable to issue RFQ."); }
    finally { setSaving(false); }
  }

  async function recordQuotation(event) {
    event.preventDefault();
    if (!selectedRfq) return;
    setSaving(true); setError(""); setNotice("");
    try {
      const lines = (selectedRfq.lines || []).map(line => {
        const quote = quotationLines[line.variant_id] || {};
        return {
          variant_id: Number(line.variant_id), quantity: Number(line.quantity), unit_price: Number(quote.unit_price),
          hsn_sac: quote.hsn_sac.trim() || null,
          gst_rate: quote.gst_rate === "" ? null : Number(quote.gst_rate),
        };
      });
      if (!quotationSupplierId || !quotationNumber.trim() || lines.some(line => !Number.isFinite(line.unit_price) || line.unit_price < 0 || (line.gst_rate !== null && (!Number.isFinite(line.gst_rate) || line.gst_rate < 0 || line.gst_rate > 100)))) {
        throw new Error("Choose an invited supplier, enter its quotation number and valid unit prices / GST rates for every RFQ line.");
      }
      const created = await apiRequest("/purchasing/quotations", {
        method: "POST",
        body: JSON.stringify({
          rfq_id: selectedRfq.id, supplier_id: Number(quotationSupplierId), quotation_number: quotationNumber.trim(),
          valid_until: quotationValidUntil || null,
          lead_time_days: quotationLeadTime === "" ? null : Number(quotationLeadTime),
          freight_amount: Number(quotationFreight), discount_amount: Number(quotationDiscount), tax_amount: Number(quotationTax),
          payment_terms: quotationPaymentTerms.trim() || null, delivery_terms: quotationDeliveryTerms.trim() || null, lines,
        }),
      });
      setNotice(`Quotation ${created.quotation_number} recorded against ${selectedRfq.rfq_number}.`);
      await loadLists(); await openRfq(selectedRfq.id);
    } catch (err) { setError(err.message || "Unable to record supplier quotation."); }
    finally { setSaving(false); }
  }

  async function awardQuotation(quotation) {
    if (!selectedRfq || !window.confirm(`Award quotation ${quotation.quotation_number} and create a draft purchase order?`)) return;
    setSaving(true); setError(""); setNotice("");
    try {
      const po = await apiRequest(`/purchasing/rfqs/${selectedRfq.id}/award`, {
        method: "POST", body: JSON.stringify({ quotation_id: quotation.id }),
      });
      await loadLists(); await openRfq(selectedRfq.id);
      if (onPurchaseOrderCreated) onPurchaseOrderCreated(po.id);
      setNotice(`Quotation awarded. Draft PO ${po.purchase_number} created and still requires purchase approval.`);
    } catch (err) { setError(err.message || "Unable to award quotation."); }
    finally { setSaving(false); }
  }

  return <section className="sb-purchasing-requests" aria-label="Purchase requisitions and requests for quotation">
    {error && <p className="sb-alert" role="alert">{error}</p>}
    {notice && <p className="sb-success" role="status">{notice}</p>}
    <div className="sb-purchasing-overview-columns">
      <form className="sb-customer-form" onSubmit={createRequisition}>
        <h2>Create purchase requisition</h2>
        <p className="sb-muted">Create a purchase request first. Submission binds the active establishment approval policy; approval is performed by an eligible different approver.</p>
        <div className="sb-customer-fields">
          <label>Receive into location *<select required value={locationId} onChange={event => setLocationId(event.target.value)}><option value="">Choose location</option>{locations.map(location => <option key={location.id} value={location.id}>{location.name}</option>)}</select></label>
          <label>Department<input maxLength="120" value={department} onChange={event => setDepartment(event.target.value)} placeholder="Department / team" /></label>
          <label>Cost centre<input maxLength="120" value={costCentre} onChange={event => setCostCentre(event.target.value)} /></label>
          <label>Required by<input type="date" value={requiredBy} onChange={event => setRequiredBy(event.target.value)} /></label>
          <label className="sb-span-all">Business justification *<textarea required minLength={3} maxLength={5000} value={justification} onChange={event => setJustification(event.target.value)} /></label>
        </div>
        <div className="sb-purchase-lines">
          <div className="sb-purchase-lines-head"><strong>Requested items</strong><button type="button" onClick={() => setRequestLines(lines => [...lines, blankLine()])}>+ Add item</button></div>
          {requestLines.map((line, index) => <div className="sb-purchase-line" key={index}>
            <label>Variant *<select required value={line.variant_id} onChange={event => updateRequestLine(index, "variant_id", event.target.value)}><option value="">Choose variant</option>{variants.map(variant => <option key={variant.id} value={variant.id}>{variant.product_name || variant.name || `Product ${variant.product_id}`} · {variant.sku || `Variant ${variant.id}`}</option>)}</select></label>
            <label>Quantity *<input required type="number" min="0.001" step="0.001" value={line.quantity} onChange={event => updateRequestLine(index, "quantity", event.target.value)} /></label>
            <label>Estimated unit cost ₹<input type="number" min="0" step="0.01" value={line.estimated_unit_cost} onChange={event => updateRequestLine(index, "estimated_unit_cost", event.target.value)} /></label>
            <label>Specification<input maxLength="2000" value={line.specification} onChange={event => updateRequestLine(index, "specification", event.target.value)} /></label>
            {requestLines.length > 1 && <button type="button" className="sb-remove-line" onClick={() => setRequestLines(lines => lines.filter((_, lineIndex) => lineIndex !== index))} aria-label={`Remove request item ${index + 1}`}>×</button>}
          </div>)}
        </div>
        <button className="sb-primary" type="submit" disabled={saving || !locations.length || !variants.length}>{saving ? "Saving…" : "Create draft requisition"}</button>
      </form>
      <div className="sb-purchasing-panel">
        <div className="sb-customer-toolbar"><h2>Requisitions</h2><button type="button" onClick={loadLists} disabled={loading}>{loading ? "Loading…" : "Refresh"}</button></div>
        {requisitions.length ? requisitions.map(item => <button type="button" className="sb-purchasing-attention-row" key={item.id} onClick={() => openRequisition(item.id)}><span><strong>{item.requisition_number}</strong><small>{item.department || "No department"} · {item.location_name} · {item.line_count} items</small></span><em>{title(item.status)}</em></button>) : <p className="sb-empty">{loading ? "Loading requisitions…" : "No requisitions recorded yet."}</p>}
      </div>
    </div>

    {selectedRequisition && <section className="sb-purchasing-panel" aria-label="Selected requisition details">
      <div className="sb-customer-toolbar"><div><h2>{selectedRequisition.requisition_number}</h2><p className="sb-muted">{selectedRequisition.requester_email} · {selectedRequisition.location_name} · {title(selectedRequisition.status)}</p></div><button type="button" onClick={() => setSelectedRequisition(null)}>Close</button></div>
      <p>{selectedRequisition.justification}</p>
      <div className="sb-purchase-detail-lines">{(selectedRequisition.lines || []).map(line => <div className="sb-purchase-detail-line" key={line.id}><strong>{line.product_name} · {line.sku}</strong><span>Qty {line.quantity} · Estimate {line.estimated_unit_cost == null ? "Not provided" : money(line.estimated_unit_cost)}</span><small>{line.specification || "No specification"}</small></div>)}</div>
      {selectedRequisition.status === "draft" && <button className="sb-primary" type="button" onClick={submitRequisition} disabled={saving}>Submit for approval</button>}
      {selectedRequisition.status === "submitted" && <div className="sb-purchase-approval"><button className="sb-primary" type="button" onClick={() => decideRequisition("approve")} disabled={saving}>Approve next configured stage</button><button type="button" onClick={() => decideRequisition("reject")} disabled={saving}>Reject with reason</button><small>Approval rules, creator separation and eligible roles are enforced by the backend.</small></div>}
      {approvedRequisitions.some(item => item.id === selectedRequisition.id) && <form className="sb-customer-form" onSubmit={createRfq}>
        <h3>Create supplier RFQ</h3>
        <p className="sb-muted">Invite suppliers to quote the approved requisition. Awarding a quotation creates a draft PO that still requires its own approval.</p>
        <div className="sb-customer-fields">
          <label>Response due<input type="datetime-local" value={rfqDueAt} onChange={event => setRfqDueAt(event.target.value)} /></label>
          <label className="sb-span-all">Commercial / delivery terms<textarea maxLength={5000} value={rfqTerms} onChange={event => setRfqTerms(event.target.value)} /></label>
        </div>
        <fieldset><legend>Invite suppliers *</legend>{suppliers.filter(supplier => supplier.is_active !== false).map(supplier => <label key={supplier.id}><input type="checkbox" checked={rfqSupplierIds.includes(String(supplier.id))} onChange={event => setRfqSupplierIds(current => event.target.checked ? [...current, String(supplier.id)] : current.filter(id => id !== String(supplier.id)))} /> {supplier.name}</label>)}</fieldset>
        <button className="sb-primary" type="submit" disabled={saving || !rfqSupplierIds.length}>Create RFQ</button>
      </form>}
    </section>}

    <div className="sb-purchasing-panel">
      <div className="sb-customer-toolbar"><h2>Requests for quotation</h2><button type="button" onClick={loadLists} disabled={loading}>Refresh RFQs</button></div>
      {rfqs.length ? rfqs.map(rfq => <button type="button" className="sb-purchasing-attention-row" key={rfq.id} onClick={() => openRfq(rfq.id)}><span><strong>{rfq.rfq_number}</strong><small>{rfq.supplier_count} suppliers · {rfq.quotation_count} quotations</small></span><em>{title(rfq.status)}</em></button>) : <p className="sb-empty">No RFQs recorded yet.</p>}
    </div>

    {selectedRfq && <section className="sb-purchasing-panel" aria-label="Selected RFQ details">
      <div className="sb-customer-toolbar"><div><h2>{selectedRfq.rfq_number}</h2><p className="sb-muted">Requisition #{selectedRfq.requisition_id} · {title(selectedRfq.status)}</p></div><button type="button" onClick={() => setSelectedRfq(null)}>Close</button></div>
      <p>{selectedRfq.terms || "No additional terms recorded."}</p>
      <div className="sb-purchase-detail-lines">{(selectedRfq.lines || []).map(line => <div className="sb-purchase-detail-line" key={line.id}><strong>{line.product_name} · {line.sku}</strong><span>Quantity {line.quantity}</span></div>)}</div>
      <h3>Invited suppliers</h3>
      {(selectedRfq.suppliers || []).map(supplier => <p key={supplier.supplier_id}>{supplier.name} · {title(supplier.response_status)}</p>)}
      {selectedRfq.status === "draft" && <button className="sb-primary" type="button" onClick={issueRfq} disabled={saving}>Issue RFQ to invited suppliers</button>}
      {selectedRfq.status === "issued" || selectedRfq.status === "evaluation" ? <form className="sb-customer-form" onSubmit={recordQuotation}>
        <h3>Record supplier quotation</h3>
        <p className="sb-muted">Use this form to record a quotation received outside the system. It does not send an email or claim supplier portal delivery.</p>
        <div className="sb-customer-fields">
          <label>Invited supplier *<select required value={quotationSupplierId} onChange={event => setQuotationSupplierId(event.target.value)}><option value="">Choose supplier</option>{(selectedRfq.suppliers || []).filter(supplier => !selectedRfq.quotations?.some(quote => quote.supplier_id === supplier.supplier_id)).map(supplier => <option key={supplier.supplier_id} value={supplier.supplier_id}>{supplier.name}</option>)}</select></label>
          <label>Supplier quotation number *<input required maxLength="80" value={quotationNumber} onChange={event => setQuotationNumber(event.target.value)} /></label>
          <label>Valid until<input type="date" value={quotationValidUntil} onChange={event => setQuotationValidUntil(event.target.value)} /></label>
          <label>Lead time (days)<input type="number" min="0" max="3650" value={quotationLeadTime} onChange={event => setQuotationLeadTime(event.target.value)} /></label>
          <label>Freight ₹<input type="number" min="0" step="0.01" value={quotationFreight} onChange={event => setQuotationFreight(event.target.value)} /></label>
          <label>Discount ₹<input type="number" min="0" step="0.01" value={quotationDiscount} onChange={event => setQuotationDiscount(event.target.value)} /></label>
          <label>Tax amount ₹<input type="number" min="0" step="0.01" value={quotationTax} onChange={event => setQuotationTax(event.target.value)} /></label>
          <label>Payment terms<input maxLength="2000" value={quotationPaymentTerms} onChange={event => setQuotationPaymentTerms(event.target.value)} /></label>
          <label>Delivery terms<input maxLength="2000" value={quotationDeliveryTerms} onChange={event => setQuotationDeliveryTerms(event.target.value)} /></label>
        </div>
        <div className="sb-purchase-detail-lines">{(selectedRfq.lines || []).map(line => <div className="sb-purchase-detail-line" key={line.variant_id}>
          <strong>{line.product_name} · {line.sku} · Qty {line.quantity}</strong>
          <label>Unit price ₹<input required type="number" min="0" step="0.01" value={quotationLines[line.variant_id]?.unit_price || ""} onChange={event => setQuotationLines(current => ({ ...current, [line.variant_id]: { ...current[line.variant_id], unit_price: event.target.value } }))} /></label>
          <label>HSN/SAC<input maxLength="8" value={quotationLines[line.variant_id]?.hsn_sac || ""} onChange={event => setQuotationLines(current => ({ ...current, [line.variant_id]: { ...current[line.variant_id], hsn_sac: event.target.value } }))} /></label>
          <label>GST rate %<input type="number" min="0" max="100" step="0.01" value={quotationLines[line.variant_id]?.gst_rate || ""} onChange={event => setQuotationLines(current => ({ ...current, [line.variant_id]: { ...current[line.variant_id], gst_rate: event.target.value } }))} /></label>
        </div>)}</div>
        <button className="sb-primary" type="submit" disabled={saving || !(selectedRfq.suppliers || []).some(supplier => String(supplier.supplier_id) === quotationSupplierId)}>{saving ? "Saving…" : "Record quotation"}</button>
      </form> : null}
      <h3>Received quotations</h3>
      {(selectedRfq.quotations || []).length ? selectedRfq.quotations.map(quotation => <article className="sb-purchase-detail-line" key={quotation.id}>
        <div><strong>{quotation.quotation_number} · {quotation.supplier_name}</strong><small>{title(quotation.status)} · Valid until {quotation.valid_until || "not specified"} · Lead time {quotation.lead_time_days ?? "—"} days</small><small>Freight {money(quotation.freight_amount)} · Discount {money(quotation.discount_amount)} · Tax {money(quotation.tax_amount)}</small></div>
        <div>{(quotation.lines || []).map(line => <small key={line.variant_id}>{line.product_name} · {line.sku}: {line.quantity} × {money(line.unit_price)}</small>)}</div>
        {selectedRfq.status === "evaluation" && ["received", "under_review"].includes(quotation.status) && <button type="button" className="sb-primary" onClick={() => awardQuotation(quotation)} disabled={saving}>Award & create draft PO</button>}
      </article>) : <p className="sb-empty">No supplier quotations received yet.</p>}
    </section>}
  </section>;
}
