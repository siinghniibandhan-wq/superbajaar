import OrganisationPolicyPanel from "../shared/OrganisationPolicyPanel.jsx";
import { useEffect, useRef, useState } from "react";
import { apiRequest } from "../../services/api.js";
import "../catalogue/catalogue.css";
import "./InventoryWorkspace.css";

function makeIdempotencyUuid() {
  if (globalThis.crypto?.randomUUID) return globalThis.crypto.randomUUID();
  return "xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx".replace(/[xy]/g, char => {
    const value = Math.floor(Math.random() * 16);
    return (char === "x" ? value : (value & 0x3) | 0x8).toString(16);
  });
}

export default function InventoryWorkspace({ onBack }) {
  const [locations, setLocations] = useState([]);
  const [establishments, setEstablishments] = useState([]);
  const [locationAssignments, setLocationAssignments] = useState({});
  const [products, setProducts] = useState([]);
  const [variants, setVariants] = useState([]);
  const [balances, setBalances] = useState([]);
  const [movements, setMovements] = useState([]);
  const [approvalRequests, setApprovalRequests] = useState([]);
  const [costLayers, setCostLayers] = useState([]);
  const [costReconciliation, setCostReconciliation] = useState([]);
  const [overview, setOverview] = useState(null);
  const [productId, setProductId] = useState("");
  const [form, setForm] = useState({ variant_id: "", location_id: "", quantity: "", unit_cost: "", adjustment_type: "opening_valuation", batch_code: "", expiry_date: "", note: "" });
  const [issueForm, setIssueForm] = useState({ variant_id: "", location_id: "", quantity: "", note: "", reason_type: "issue", allocation_method: "fifo" });
  const [countForm, setCountForm] = useState({ variant_id: "", location_id: "", counted_quantity: "", unit_cost: "", batch_code: "", expiry_date: "", allocation_method: "fifo", note: "" });
  const [transferForm, setTransferForm] = useState({ variant_id: "", source_location_id: "", destination_location_id: "", quantity: "", note: "" });
  const [locationEditId, setLocationEditId] = useState(null);
  const [locationForm, setLocationForm] = useState({ name: "", location_type: "warehouse", pin_code: "", is_fulfillable: true });
  const [internalFacilityId, setInternalFacilityId] = useState("");
  const [internalLocations, setInternalLocations] = useState([]);
  const [internalLocationForm, setInternalLocationForm] = useState({ parent_id: "", code: "", name: "", location_type: "receiving" });
  const [internalLocationEditId, setInternalLocationEditId] = useState(null);
  const [returns, setReturns] = useState([]);
  const [selectedReturn, setSelectedReturn] = useState(null);
  const [returnLoading, setReturnLoading] = useState(false);
  const [returnReleaseLocationId, setReturnReleaseLocationId] = useState("");
  const [returnReleaseReason, setReturnReleaseReason] = useState("");
  const [returnReleaseBusyId, setReturnReleaseBusyId] = useState(null);
  const returnReleaseAttempts = useRef({});
  const [quarantineGrns, setQuarantineGrns] = useState([]);
  const [expiredStock, setExpiredStock] = useState([]);
  const [expiredQuarantineLocationId, setExpiredQuarantineLocationId] = useState("");
  const [expiredQuarantineReason, setExpiredQuarantineReason] = useState("");
  const [expiredQuarantineBusyKey, setExpiredQuarantineBusyKey] = useState(null);
  const expiredQuarantineAttempts = useRef({});
  const [selectedQuarantineGrn, setSelectedQuarantineGrn] = useState(null);
  const [quarantineReleaseQuantities, setQuarantineReleaseQuantities] = useState({});
  const [quarantineReleaseReasons, setQuarantineReleaseReasons] = useState({});
  const quarantineReleaseAttempt = useRef(null);
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");
  const [busy, setBusy] = useState(false);
  const [activeSection, setActiveSection] = useState("overview");

  async function loadBase() {
    try {
      const [l, p, b, m, c, cr, ar, o] = await Promise.all([
        apiRequest("/inventory/locations"),
        apiRequest("/catalogue/products?status=all"),
        apiRequest("/inventory/balances"),
        apiRequest("/inventory/movements"),
        apiRequest("/inventory/cost-layers"),
        apiRequest("/inventory/cost-layer-reconciliation"),
        apiRequest("/inventory/approval-requests"),
        apiRequest("/inventory/overview"),
      ]);
      setLocations(l.items || []); setInternalFacilityId(current => current || String(l.items?.[0]?.id || "")); setProducts(p.items || []); setBalances(b.items || []); setMovements(m.items || []); setCostLayers(c.items || []); setCostReconciliation(cr.items || []); setApprovalRequests(ar.items || []); setOverview(o);
      apiRequest("/hr/establishments").then(result => setEstablishments(result.items || [])).catch(() => setEstablishments([]));
    } catch (e) { setError(e.message || "Inventory API unavailable."); }
  }
  useEffect(() => { loadBase(); }, []);
  useEffect(() => {
    if (!internalFacilityId) { setInternalLocations([]); return; }
    apiRequest("/inventory/internal-locations?facility_id=" + internalFacilityId)
      .then(result => setInternalLocations(result.items || []))
      .catch(e => setError(e.message || "Unable to load warehouse storage locations."));
  }, [internalFacilityId]);
  useEffect(() => {
    if (activeSection !== "returns") return;
    setReturnLoading(true);
    Promise.all([
      apiRequest("/fulfilment/returns?limit=100"),
      apiRequest("/purchasing/grns?quarantined_only=true&limit=100"),
      apiRequest("/inventory/expired-stock?limit=100"),
    ]).then(([returnResult, grnResult, expiredResult]) => {
      setReturns(returnResult.items || []);
      setQuarantineGrns(grnResult.items || []);
      setExpiredStock(expiredResult.items || []);
    }).catch(e => setError(e.message || "Unable to load return and quarantine records."))
      .finally(() => setReturnLoading(false));
  }, [activeSection]);

  async function saveInternalLocation(event) {
    event.preventDefault(); setBusy(true); setError(""); setMessage("");
    try {
      const payload = {
        parent_id: internalLocationForm.parent_id ? Number(internalLocationForm.parent_id) : null,
        code: internalLocationForm.code.trim(), name: internalLocationForm.name.trim(),
        location_type: internalLocationForm.location_type,
      };
      if (!payload.code || !payload.name || !internalFacilityId) throw new Error("Choose a facility and enter a code and name.");
      await apiRequest(internalLocationEditId ? "/inventory/internal-locations/" + internalLocationEditId : "/inventory/internal-locations", {
        method: internalLocationEditId ? "PUT" : "POST",
        body: JSON.stringify(internalLocationEditId ? { ...payload, is_active: true } : { ...payload, facility_id: Number(internalFacilityId) }),
      });
      setInternalLocationForm({ parent_id: "", code: "", name: "", location_type: "receiving" });
      setInternalLocationEditId(null);
      const result = await apiRequest("/inventory/internal-locations?facility_id=" + internalFacilityId);
      setInternalLocations(result.items || []);
      setMessage(internalLocationEditId ? "Storage location updated." : "Storage location created.");
    } catch (e) { setError(e.message || "Unable to save warehouse storage location."); }
    finally { setBusy(false); }
  }

  function editInternalLocation(location) {
    setInternalLocationEditId(location.id);
    setInternalLocationForm({ parent_id: location.parent_id ? String(location.parent_id) : "", code: location.code, name: location.name, location_type: location.location_type });
    setError(""); setMessage("");
  }

  async function createReplenishmentRequisition(balance) {
    const quantityInput = window.prompt(`Enter the quantity to request for ${balance.sku} at ${balance.location_name}:`);
    if (quantityInput === null) return;
    const quantity = Number(quantityInput);
    if (!Number.isFinite(quantity) || quantity <= 0) { setError("Replenishment quantity must be greater than zero."); return; }
    const justification = window.prompt("Why is this stock required?");
    if (justification === null) return;
    if (justification.trim().length < 3) { setError("Enter a replenishment justification of at least 3 characters."); return; }
    setBusy(true); setError(""); setMessage("");
    try {
      const request = await apiRequest("/purchasing/requisitions", {
        method: "POST",
        body: JSON.stringify({
          location_id: Number(balance.location_id), department: "Inventory", cost_centre: null,
          required_by: null, justification: justification.trim(),
          lines: [{ variant_id: Number(balance.variant_id), quantity, estimated_unit_cost: null,
            specification: "Replenishment request initiated from the Inventory watchlist" }],
        }),
      });
      setMessage(`Draft purchase requisition ${request.requisition_number} created for ${balance.sku}. Submit it for the configured approval workflow in Purchasing.`);
    } catch (e) { setError(e.message || "Unable to create replenishment requisition."); }
    finally { setBusy(false); }
  }

  async function openInventoryReturn(returnId) {
    setSelectedReturn(null); setError("");
    try { setSelectedReturn(await apiRequest("/fulfilment/returns/" + returnId)); }
    catch (e) { setError(e.message || "Unable to load return detail."); }
  }

  async function releaseCustomerReturnQuarantine(returnLine) {
    if (!selectedReturn) return;
    if (!returnReleaseLocationId || returnReleaseReason.trim().length < 3) {
      setError("Choose an active saleable destination and enter a release reason of at least 3 characters."); return;
    }
    const payload = { destination_location_id: Number(returnReleaseLocationId), reason: returnReleaseReason.trim() };
    const signature = JSON.stringify({ return_id: selectedReturn.id, line_id: returnLine.id, ...payload });
    if (!returnReleaseAttempts.current[returnLine.id] || returnReleaseAttempts.current[returnLine.id].signature !== signature) {
      returnReleaseAttempts.current[returnLine.id] = {
        signature, key: makeIdempotencyUuid(),
      };
    }
    setReturnReleaseBusyId(returnLine.id); setError(""); setMessage("");
    try {
      const result = await apiRequest(`/fulfilment/returns/${selectedReturn.id}/lines/${returnLine.id}/release-quarantine`, {
        method: "POST", body: JSON.stringify({ ...payload, idempotency_key: returnReleaseAttempts.current[returnLine.id].key }),
      });
      setMessage(`Return line ${returnLine.id}: ${result.released_quantity} units moved to saleable stock. ${Number(result.expired_quantity_not_released || 0) > 0 ? `${result.expired_quantity_not_released} expired units remain quarantined.` : ""}`);
      const [detail, balanceResult] = await Promise.all([
        apiRequest(`/fulfilment/returns/${selectedReturn.id}`), apiRequest("/inventory/balances?limit=500"),
      ]);
      setSelectedReturn(detail); setBalances(balanceResult.items || []);
      delete returnReleaseAttempts.current[returnLine.id];
    } catch (e) { setError(e.message || "Unable to release customer-return quarantine stock."); }
    finally { setReturnReleaseBusyId(null); }
  }

  async function quarantineExpiredStock(item) {
    if (!expiredQuarantineLocationId || expiredQuarantineReason.trim().length < 3) {
      setError("Choose an active non-fulfillable quarantine location and enter a reason of at least 3 characters."); return;
    }
    const payload = { variant_id: Number(item.variant_id), source_location_id: Number(item.location_id), quarantine_location_id: Number(expiredQuarantineLocationId), reason: expiredQuarantineReason.trim() };
    const signature = JSON.stringify(payload);
    const key = `${item.variant_id}:${item.location_id}`;
    if (!expiredQuarantineAttempts.current[key] || expiredQuarantineAttempts.current[key].signature !== signature) {
      expiredQuarantineAttempts.current[key] = { signature, idempotency_key: makeIdempotencyUuid() };
    }
    setExpiredQuarantineBusyKey(key); setError(""); setMessage("");
    try {
      const result = await apiRequest("/inventory/quarantine-expired", {
        method: "POST", body: JSON.stringify({ ...payload, idempotency_key: expiredQuarantineAttempts.current[key].idempotency_key }),
      });
      const [expiredResult, balanceResult] = await Promise.all([
        apiRequest("/inventory/expired-stock?limit=100"), apiRequest("/inventory/balances?limit=500"),
      ]);
      setExpiredStock(expiredResult.items || []); setBalances(balanceResult.items || []);
      delete expiredQuarantineAttempts.current[key];
      setMessage(`${result.quarantined_quantity} expired units moved to non-fulfillable quarantine. The original expiry and cost-layer history is preserved.`);
    } catch (e) { setError(e.message || "Unable to quarantine expired stock."); }
    finally { setExpiredQuarantineBusyKey(null); }
  }

  async function openQuarantineGrn(grnId) {
    setSelectedQuarantineGrn(null); setError("");
    try {
      const detail = await apiRequest("/purchasing/grns/" + grnId);
      setSelectedQuarantineGrn(detail);
      setQuarantineReleaseQuantities(Object.fromEntries((detail.lines || []).map(line => [line.id, ""])));
      setQuarantineReleaseReasons(Object.fromEntries((detail.lines || []).map(line => [line.id, ""])));
    } catch (e) { setError(e.message || "Unable to load quarantined GRN detail."); }
  }

  async function releaseQuarantinedStock(event) {
    event.preventDefault();
    if (!selectedQuarantineGrn) return;
    const lines = (selectedQuarantineGrn.lines || []).filter(line => Number(quarantineReleaseQuantities[line.id]) > 0).map(line => ({
      goods_receipt_line_id: line.id,
      quantity: Number(quarantineReleaseQuantities[line.id]),
      reason: String(quarantineReleaseReasons[line.id] || "").trim(),
    }));
    if (!lines.length || lines.some(line => !Number.isFinite(line.quantity) || line.quantity <= 0 || line.reason.length < 3)) {
      setError("Enter a positive release quantity and a reason of at least 3 characters for every selected GRN line."); return;
    }
    const signature = JSON.stringify({ grn_id: selectedQuarantineGrn.id, lines });
    if (!quarantineReleaseAttempt.current || quarantineReleaseAttempt.current.signature !== signature) {
      quarantineReleaseAttempt.current = { signature, key: makeIdempotencyUuid() };
    }
    setBusy(true); setError(""); setMessage("");
    try {
      const result = await apiRequest("/purchasing/grns/" + selectedQuarantineGrn.id + "/release-quarantine", {
        method: "POST", body: JSON.stringify({ idempotency_key: quarantineReleaseAttempt.current.key, lines }),
      });
      quarantineReleaseAttempt.current = null;
      setMessage(result.replayed ? "Quarantine release retry confirmed; no duplicate stock was posted." : "Quarantined quantity released to saleable stock with cost layers and Accounting references.");
      const [detail, list] = await Promise.all([
        apiRequest("/purchasing/grns/" + selectedQuarantineGrn.id),
        apiRequest("/purchasing/grns?quarantined_only=true&limit=100"),
      ]);
      setSelectedQuarantineGrn(detail); setQuarantineGrns(list.items || []);
      setQuarantineReleaseQuantities(Object.fromEntries((detail.lines || []).map(line => [line.id, ""])));
      setQuarantineReleaseReasons(Object.fromEntries((detail.lines || []).map(line => [line.id, ""])));
    } catch (e) { setError(e.message || "Unable to release quarantined stock."); }
    finally { setBusy(false); }
  }
  useEffect(() => {
    if (!productId) { setVariants([]); return; }
    apiRequest("/catalogue/products/" + productId + "/variants")
      .then(result => setVariants(result.items || []))
      .catch(e => setError(e.message || "Unable to load variants."));
  }, [productId]);

  async function assignLocationEstablishment(locationId) {
    const establishmentId = locationAssignments[locationId];
    if (!establishmentId) { setError("Choose a legal establishment before assigning this location."); return; }
    setBusy(true); setError(""); setMessage("");
    try {
      await apiRequest("/inventory/locations/" + locationId + "/establishment", {
        method: "PUT", body: JSON.stringify({ establishment_id: Number(establishmentId) }),
      });
      setMessage("Legal establishment assigned to stock location.");
      await loadBase();
    } catch (e) { setError(e.message || "Unable to assign the legal establishment."); }
    finally { setBusy(false); }
  }

  async function createLocation(event) {
    event.preventDefault(); setBusy(true); setError(""); setMessage("");
    try {
      await apiRequest("/inventory/locations", { method: "POST", body: JSON.stringify({
        name: locationForm.name, location_type: locationForm.location_type, pin_code: locationForm.pin_code || null,
        is_fulfillable: locationForm.is_fulfillable,
      })});
      setLocationForm({ name: "", location_type: "warehouse", pin_code: "", is_fulfillable: true });
      setMessage(locationEditId ? "Facility profile updated." : "Warehouse / store profile created."); await loadBase();
    } catch (e) { setError(e.message || "Unable to create stock location."); }
    finally { setBusy(false); }
  }


  function editFacilityProfile(location) {
    const profile = location.profile || {};
    setLocationEditId(location.id);
    setLocationForm({
      name: location.name, location_type: location.location_type, pin_code: profile.pin_code || location.pin_code || "",
      is_fulfillable: location.is_fulfillable !== false, facility_code: location.facility_code || "",
      address_line1: profile.address_line1 || location.address_line1 || "", address_line2: profile.address_line2 || location.address_line2 || "",
      city: profile.city || location.city || "", district: profile.district || location.district || "",
      state: profile.state || location.state || "", country: profile.country || "India",
      manager_name: profile.manager_name || "", contact_phone: profile.contact_phone || "",
      contact_email: profile.contact_email || "", emergency_contact: profile.emergency_contact || "",
      capacity: profile.capacity ?? "", capacity_unit: profile.capacity_unit || "",
      operating_days: profile.operating_days || [], opening_time: profile.opening_time || "", closing_time: profile.closing_time || "",
      receives_stock: profile.receives_stock !== false, dispatches_stock: profile.dispatches_stock !== false,
      gstin: profile.gstin || "", licence_reference: profile.licence_reference || "",
    });
    setError(""); setMessage("");
  }

  async function submit(event) {
    event.preventDefault(); setBusy(true); setError(""); setMessage("");
    try {
      await apiRequest("/inventory/adjustments", { method: "POST", body: JSON.stringify({
        variant_id: Number(form.variant_id), location_id: Number(form.location_id),
        quantity: Number(form.quantity), unit_cost: Number(form.unit_cost), adjustment_type: form.adjustment_type,
        batch_code: form.batch_code || null, expiry_date: form.expiry_date || null, note: form.note,
      })});
      setForm(v => ({ ...v, quantity: "", unit_cost: "", batch_code: "", expiry_date: "", note: "" }));
      setMessage("Stock receipt adjustment recorded."); await loadBase();
    } catch (e) { setError(e.message || "Stock adjustment failed."); }
    finally { setBusy(false); }
  }


  async function submitIssue(event) {
    event.preventDefault(); setBusy(true); setError(""); setMessage("");
    try {
      await apiRequest("/inventory/issues", { method: "POST", body: JSON.stringify({
        variant_id: Number(issueForm.variant_id), location_id: Number(issueForm.location_id),
        quantity: Number(issueForm.quantity), note: issueForm.note, reason_type: issueForm.reason_type,
        allocation_method: issueForm.allocation_method,
      })});
      setIssueForm(v => ({ ...v, quantity: "", note: "" }));
      setMessage(issueForm.reason_type === "scrap" ? "Scrap recorded and stock reduced." : "Stock issue recorded. Reserved units were protected."); await loadBase();
    } catch (e) { setError(e.message || "Stock issue failed."); }
    finally { setBusy(false); }
  }


  async function submitCount(event) {
    event.preventDefault(); setBusy(true); setError(""); setMessage("");
    try {
      const result = await apiRequest("/inventory/counts", { method: "POST", body: JSON.stringify({
        variant_id: Number(countForm.variant_id), location_id: Number(countForm.location_id),
        counted_quantity: Number(countForm.counted_quantity),
        unit_cost: countForm.unit_cost === "" ? null : Number(countForm.unit_cost),
        batch_code: countForm.batch_code || null, expiry_date: countForm.expiry_date || null,
        allocation_method: countForm.allocation_method, note: countForm.note,
      })});
      setCountForm(v => ({ ...v, counted_quantity: "", note: "" }));
      setMessage("Physical count saved. Variance: " + result.variance + " units."); await loadBase();
    } catch (e) { setError(e.message || "Physical count failed."); }
    finally { setBusy(false); }
  }

  async function submitTransfer(event) {
    event.preventDefault(); setBusy(true); setError(""); setMessage("");
    try {
      await apiRequest("/inventory/transfers", { method: "POST", body: JSON.stringify({
        variant_id: Number(transferForm.variant_id), source_location_id: Number(transferForm.source_location_id),
        destination_location_id: Number(transferForm.destination_location_id),
        quantity: Number(transferForm.quantity), note: transferForm.note,
      })});
      setTransferForm(v => ({ ...v, quantity: "", note: "" }));
      setMessage("Stock transfer completed and both location movements recorded."); await loadBase();
    } catch (e) { setError(e.message || "Stock transfer failed."); }
    finally { setBusy(false); }
  }


  async function submitInventoryApproval(eventType, locationId, payload) {
    setBusy(true); setError(""); setMessage("");
    try {
      await apiRequest("/inventory/approval-requests", {
        method: "POST",
        body: JSON.stringify({ event_type: eventType, location_id: Number(locationId), payload }),
      });
      setMessage("Inventory operation submitted for approval. No stock has moved.");
      const result = await apiRequest("/inventory/approval-requests");
      setApprovalRequests(result.items || []);
    } catch (e) { setError(e.message || "Unable to submit inventory approval request."); }
    finally { setBusy(false); }
  }

  async function decideInventoryApproval(id, decision) {
    const reason = window.prompt(decision === "approved" ? "Approval reason / review note:" : "Reason for rejecting this inventory operation:");
    if (reason === null) return;
    if (reason.trim().length < 3) { setError("Enter a reason of at least 3 characters."); return; }
    setBusy(true); setError(""); setMessage("");
    try {
      const result = await apiRequest("/inventory/approval-requests/" + id + "/decision", {
        method: "POST", body: JSON.stringify({ decision, reason: reason.trim() }),
      });
      setMessage("Inventory request #" + id + " is now " + result.status + ".");
      const refreshed = await apiRequest("/inventory/approval-requests");
      setApprovalRequests(refreshed.items || []);
    } catch (e) { setError(e.message || "Unable to record inventory decision."); }
    finally { setBusy(false); }
  }

  const inventoryTotals = overview?.totals || {};
  const totalOnHand = Number(inventoryTotals.on_hand || 0);
  const totalReserved = Number(inventoryTotals.reserved || 0);
  const totalAvailable = Number(inventoryTotals.available || 0);
  const pendingApprovalCount = Number(inventoryTotals.pending_approvals || 0);
  const movementGroups = (overview?.movement_groups || []).map(row => ({ name: String(row.movement_type || "other").replaceAll("_", " "), total: Number(row.total || 0) }));
  const stockByLocation = (overview?.stock_by_location || []).map(row => ({ id: row.location_id, name: row.location_name || ("Location " + row.location_id), total: Number(row.on_hand || 0) }));
  const maxLocationStock = Math.max(1, ...stockByLocation.map(row => row.total));

  return <section className="sb-workspace">
    <button className="sb-back" type="button" onClick={onBack}>← All workspaces</button>
    <p className="sb-eyebrow">STOCK CONTROL</p><h1>Inventory</h1>
    <p>Manage stock locations, receipt adjustments, stock issues, inter-location transfers, balances and movement history.</p>
    {error && <p className="sb-alert" role="alert">{error}</p>}
    {message && <p className="sb-success" role="status">{message}</p>}
    <nav className="inventory-section-nav" aria-label="Inventory sections">
      {[["overview","Overview"],["locations","Locations"],["operations","Stock operations"],["approvals","Approvals"],["stock","Stock & valuation"],["returns","Returns & quarantine"],["policy","Control policy"]].map(([key,label])=><button key={key} type="button" className={activeSection===key?"active":""} aria-pressed={activeSection===key} onClick={()=>setActiveSection(key)}>{label}</button>)}
    </nav>
    {activeSection === "locations" && <div className="inventory-section"><form className="sb-form" onSubmit={createLocation}>
      <h2>{locationEditId ? "Complete / edit facility profile" : "Create warehouse or store"}</h2>
      <div className="sb-form-grid">
        <label>Location name<input required maxLength="160" value={locationForm.name} onChange={e=>setLocationForm(v=>({...v,name:e.target.value}))}/></label>
        <label>Type<select value={locationForm.location_type} onChange={e=>setLocationForm(v=>({...v,location_type:e.target.value}))}><option value="warehouse">Warehouse</option><option value="store">Store</option><option value="dark_store">Dark store</option></select></label>
        <label>PIN code (optional)<input inputMode="numeric" pattern="[0-9]{6}" maxLength="6" value={locationForm.pin_code} onChange={e=>setLocationForm(v=>({...v,pin_code:e.target.value}))}/></label>
        <label className="sb-span-all"><input type="checkbox" checked={locationForm.is_fulfillable} onChange={e=>setLocationForm(v=>({...v,is_fulfillable:e.target.checked}))}/> Eligible for order reservation and normal fulfilment</label>
      </div>
      <button className="sb-primary" disabled={busy} type="submit">{busy ? "Saving…" : locationEditId ? "Save facility profile" : locationForm.location_type === "warehouse" ? "Create warehouse" : locationForm.location_type === "dark_store" ? "Create dark store" : "Create store"}</button>
    </form>
    <div className="sb-data-card">
      <h2>Warehouse / store ownership ({locations.length})</h2>
      <p className="sb-muted">Every stock location used by controlled Purchase or Inventory workflows must be assigned to its legal establishment. Existing unassigned locations are blocked from those operations until assigned.</p>
      {locations.length ? locations.map(location => <div className="sb-form-grid" key={location.id}>
        <div><strong>{location.name}</strong><p className="sb-muted">{location.location_type} · {location.profile_status === "complete" ? "Profile complete" : "Profile incomplete"} · Code: {location.facility_code || "Not assigned"}</p><p className="sb-muted">{location.profile?.address_line1 || location.address_line1 || "Address not recorded"}{location.profile?.city || location.city ? ", " + (location.profile?.city || location.city) : ""}{location.profile?.state || location.state ? ", " + (location.profile?.state || location.state) : ""}</p><button className="sb-secondary" type="button" onClick={()=>editFacilityProfile(location)}>Edit / complete profile</button></div>
        <label>{location.name} · {location.location_type} · {location.is_fulfillable ? "Fulfilment stock" : "Quarantine / repair holding"}
          <select value={locationAssignments[location.id] || ""} onChange={e=>setLocationAssignments(old=>({...old,[location.id]:e.target.value}))}>
            <option value="">Not assigned</option>
            {establishments.map(item=><option key={item.id} value={item.id}>{item.display_name} ({item.code})</option>)}
          </select>
        </label>
        <button className="sb-secondary" type="button" disabled={busy || !locationAssignments[location.id] || String(location.establishment_id || "") === String(locationAssignments[location.id])} onClick={()=>assignLocationEstablishment(location.id)}>Save assignment</button>
      </div>) : <p className="sb-empty">No stock locations yet.</p>}
    </div>
      <div className="sb-data-card">
        <h2>Warehouse storage locations</h2>
        <p className="sb-muted">Create storage locations inside the selected warehouse, such as receiving areas, zones, racks, shelves, bins, picking, packing, dispatch, quarantine and repair areas. These organise physical handling; stock balances remain warehouse-level until a separately approved bin-ledger design exists.</p>
        <div className="sb-form-grid">
          <label>Warehouse<select value={internalFacilityId} onChange={e=>{setInternalFacilityId(e.target.value);setInternalLocationEditId(null);setInternalLocationForm({parent_id:"",code:"",name:"",location_type:"receiving"});}}><option value="">Choose facility</option>{locations.map(location=><option key={location.id} value={location.id}>{location.name}</option>)}</select></label>
        </div>
        <form className="sb-form" onSubmit={saveInternalLocation}>
          <h3>{internalLocationEditId ? "Edit storage location" : "Create storage location"}</h3>
          <div className="sb-form-grid">
            <label>Parent storage location<select value={internalLocationForm.parent_id} onChange={e=>setInternalLocationForm(v=>({...v,parent_id:e.target.value}))}><option value="">No parent (top level)</option>{internalLocations.filter(item=>String(item.id)!==String(internalLocationEditId)).map(item=><option key={item.id} value={item.id}>{item.code} · {item.name} ({item.location_type})</option>)}</select></label>
            <label>Location code<input required maxLength="40" value={internalLocationForm.code} onChange={e=>setInternalLocationForm(v=>({...v,code:e.target.value.toUpperCase()}))}/></label>
            <label>Location name<input required maxLength="120" value={internalLocationForm.name} onChange={e=>setInternalLocationForm(v=>({...v,name:e.target.value}))}/></label>
            <label>Location type<select value={internalLocationForm.location_type} onChange={e=>setInternalLocationForm(v=>({...v,location_type:e.target.value}))}>{["receiving","storage","rack","shelf","bin","picking","packing","dispatch","quarantine","repair"].map(type=><option key={type} value={type}>{type.replaceAll("_"," ").replace(/\b\w/g,c=>c.toUpperCase())}</option>)}</select></label>
          </div>
          <button className="sb-primary" type="submit" disabled={busy || !internalFacilityId}>{busy ? "Saving…" : internalLocationEditId ? "Save storage location" : "Create storage location"}</button>
          {internalLocationEditId && <button className="sb-secondary" type="button" onClick={()=>{setInternalLocationEditId(null);setInternalLocationForm({parent_id:"",code:"",name:"",location_type:"receiving"});}}>Cancel edit</button>}
        </form>
        {internalLocations.length ? <div className="sb-table-wrap"><table><thead><tr><th>Code</th><th>Location</th><th>Type</th><th>Parent</th><th>Action</th></tr></thead><tbody>{internalLocations.map(item=><tr key={item.id}><td>{item.code}</td><td>{item.name}</td><td>{item.location_type}</td><td>{internalLocations.find(parent=>parent.id===item.parent_id)?.name || "—"}</td><td><button type="button" onClick={()=>editInternalLocation(item)}>Edit</button></td></tr>)}</tbody></table></div> : <p className="sb-empty">No internal locations have been created for this facility.</p>}
      </div>
    </div>}
    {activeSection === "overview" && <div className="inventory-section inventory-analytics">
      <div className="inventory-analytics-heading">
        <div><h2>Inventory analytics</h2><p className="sb-muted">Live operational view from stock balances, movement history, approvals and valuation records.</p></div>
        <button className="sb-secondary" type="button" disabled={busy} onClick={loadBase}>Refresh analytics</button>
      </div>
      <div className="inventory-analytics-metrics">
        <article><small>Units on hand</small><strong>{overview ? totalOnHand.toLocaleString("en-IN") : "—"}</strong><span>Full-dataset total across {locations.length} stock locations</span></article>
        <article><small>Reserved units</small><strong>{overview ? totalReserved.toLocaleString("en-IN") : "—"}</strong><span>Full-dataset reserved quantity</span></article>
        <article><small>Available units</small><strong>{overview ? totalAvailable.toLocaleString("en-IN") : "—"}</strong><span>Full-dataset on-hand less reserved</span></article>
        <article><small>Movement records</small><strong>{overview ? Number(inventoryTotals.movements || 0).toLocaleString("en-IN") : "—"}</strong><span>All recorded inventory movements</span></article>
        <article><small>Pending approvals</small><strong>{overview ? pendingApprovalCount.toLocaleString("en-IN") : "—"}</strong><span>All pending approval requests</span></article>
        <article><small>Cost layers</small><strong>{overview ? Number(inventoryTotals.active_cost_layers || 0).toLocaleString("en-IN") : "—"}</strong><span>All active inventory valuation layers</span></article>
      </div>
      <div className="inventory-analytics-grid">
        <section className="sb-data-card">
          <h2>Stock by location</h2>
          {stockByLocation.length ? <div className="inventory-analytics-bars">{stockByLocation.map(row => <div className="inventory-analytics-bar" key={row.id}><div><span>{row.name}</span><strong>{row.total.toLocaleString("en-IN")}</strong></div><i><b style={{ width: Math.max(2, row.total / maxLocationStock * 100) + "%" }} /></i></div>)}</div> : <p className="sb-empty">No stock balance records are available yet.</p>}
        </section>
        <section className="sb-data-card">
          <h2>Movement mix</h2>
          {movementGroups.length ? <div className="inventory-analytics-list">{movementGroups.map(row => <div key={row.name}><span>{row.name.replace(/\b\w/g, value => value.toUpperCase())}</span><strong>{row.total.toLocaleString("en-IN")}</strong></div>)}</div> : <p className="sb-empty">No inventory movements are recorded yet.</p>}
        </section>
        <section className="sb-data-card">
          <h2>Valuation & controls</h2>
          <div className="inventory-analytics-list">
            <div><span>Cost reconciliation records</span><strong>{overview ? Number(inventoryTotals.reconciliation_records || 0).toLocaleString("en-IN") : "—"}</strong></div>
            <div><span>Balances requiring valuation review</span><strong>{overview ? Number(inventoryTotals.mismatched_records || 0).toLocaleString("en-IN") : "—"}</strong></div>
            <div><span>Approval requests</span><strong>{overview ? Number(inventoryTotals.total_approval_requests || 0).toLocaleString("en-IN") : "—"}</strong></div>
            <div><span>Locations requiring assignment</span><strong>{locations.filter(row => !row.establishment_id).length.toLocaleString("en-IN")}</strong></div>
          </div>
          <p className="sb-muted">Counts are full-dataset aggregates. Valuation review counts compare operational on-hand quantities with remaining cost-layer quantities; they are not monetary valuation totals.</p>
        </section>
      </div>
    </div>}
    {activeSection === "operations" && <div className="inventory-section"><form className="sb-form" onSubmit={submit}>
      <h2>Value or add stock</h2>
      <p className="sb-muted">Opening valuation assigns cost to existing unvalued on-hand stock without increasing quantity. Opening balance and stock gain add new quantity. Every entry requires an explicit unit cost.</p>
      <div className="sb-form-grid">
        <label>Product<select required value={productId} onChange={e=>{setProductId(e.target.value);setForm(v=>({...v,variant_id:""}));}}><option value="">Choose product</option>{products.map(p=><option key={p.id} value={p.id}>{p.name}</option>)}</select></label>
        <label>Variant / SKU<select required value={form.variant_id} onChange={e=>setForm(v=>({...v,variant_id:e.target.value}))}><option value="">Choose variant</option>{variants.map(v=><option key={v.id} value={v.id}>{v.sku} · ₹{v.selling_price}</option>)}</select></label>
        <label>Stock location<select required value={form.location_id} onChange={e=>setForm(v=>({...v,location_id:e.target.value}))}><option value="">Choose location</option>{locations.map(l=><option key={l.id} value={l.id}>{l.name} ({l.location_type})</option>)}</select></label>
        <label>Quantity to add<input required type="number" min="0.001" step="0.001" value={form.quantity} onChange={e=>setForm(v=>({...v,quantity:e.target.value}))}/></label>
        <label>Adjustment purpose<select value={form.adjustment_type} onChange={e=>setForm(v=>({...v,adjustment_type:e.target.value}))}><option value="opening_valuation">Value existing unvalued stock (quantity unchanged)</option><option value="opening_balance">Add opening stock balance</option><option value="stock_gain">Stock gain / found stock</option></select></label>
        <label>Unit cost (₹)<input required type="number" min="0" step="0.0001" value={form.unit_cost} onChange={e=>setForm(v=>({...v,unit_cost:e.target.value}))}/></label>
        <label>Batch / lot code<input maxLength="100" value={form.batch_code} onChange={e=>setForm(v=>({...v,batch_code:e.target.value}))}/></label>
        <label>Expiry date<input type="date" value={form.expiry_date} onChange={e=>setForm(v=>({...v,expiry_date:e.target.value}))}/></label>
        <label className="sb-span-all">Reason / reference<input required minLength="3" maxLength="500" value={form.note} onChange={e=>setForm(v=>({...v,note:e.target.value}))}/></label>
      </div>
      <button className="sb-primary" disabled={busy || !locations.length} type="submit">{busy ? "Saving…" : "Record adjustment"}</button>
      <button className="sb-secondary" type="button" disabled={busy || !form.location_id || !form.variant_id || !form.quantity || !form.note} onClick={()=>submitInventoryApproval(form.adjustment_type,form.location_id,{variant_id:Number(form.variant_id),location_id:Number(form.location_id),quantity:Number(form.quantity),unit_cost:Number(form.unit_cost),adjustment_type:form.adjustment_type,batch_code:form.batch_code||null,expiry_date:form.expiry_date||null,note:form.note})}>Submit adjustment for approval</button>
      {!locations.length && <p className="sb-muted">No active stock locations are configured.</p>}
    </form>
    <form className="sb-form" onSubmit={submitIssue}>
      <h2>Issue / reduce stock</h2>
      <p className="sb-muted">Issue or scrap stock. On-hand stock cannot fall below reserved units; every reduction is recorded in movement history.</p>
      <div className="sb-form-grid">
        <label>Product<select required value={productId} onChange={e=>{setProductId(e.target.value);setIssueForm(v=>({...v,variant_id:""}));}}><option value="">Choose product</option>{products.map(p=><option key={p.id} value={p.id}>{p.name}</option>)}</select></label>
        <label>Variant / SKU<select required value={issueForm.variant_id} onChange={e=>setIssueForm(v=>({...v,variant_id:e.target.value}))}><option value="">Choose variant</option>{variants.map(v=><option key={v.id} value={v.id}>{v.sku} · ₹{v.selling_price}</option>)}</select></label>
        <label>Stock location<select required value={issueForm.location_id} onChange={e=>setIssueForm(v=>({...v,location_id:e.target.value}))}><option value="">Choose location</option>{locations.map(l=><option key={l.id} value={l.id}>{l.name}</option>)}</select></label>
        <label>Action<select value={issueForm.reason_type} onChange={e=>setIssueForm(v=>({...v,reason_type:e.target.value}))}><option value="issue">Issue / remove stock</option><option value="scrap">Scrap / damaged stock</option></select></label>
        <label>Quantity<input required type="number" min="0.001" step="0.001" value={issueForm.quantity} onChange={e=>setIssueForm(v=>({...v,quantity:e.target.value}))}/></label>
        <label>Cost allocation<select value={issueForm.allocation_method} onChange={e=>setIssueForm(v=>({...v,allocation_method:e.target.value}))}><option value="fifo">FIFO</option><option value="fefo">FEFO (earliest expiry first)</option></select></label>
        <label className="sb-span-all">Reason / reference<input required minLength="3" maxLength="500" value={issueForm.note} onChange={e=>setIssueForm(v=>({...v,note:e.target.value}))}/></label>
      </div>
      <button className="sb-primary" disabled={busy || !locations.length} type="submit">{busy ? "Saving…" : "Issue stock"}</button>
      <button className="sb-secondary" type="button" disabled={busy || !issueForm.location_id || !issueForm.variant_id || !issueForm.quantity || !issueForm.note} onClick={()=>submitInventoryApproval(issueForm.reason_type==="scrap"?"scrap":"issue",issueForm.location_id,{variant_id:Number(issueForm.variant_id),location_id:Number(issueForm.location_id),quantity:Number(issueForm.quantity),note:issueForm.note,reason_type:issueForm.reason_type,allocation_method:issueForm.allocation_method})}>Submit issue for approval</button>
    </form>
    <form className="sb-form" onSubmit={submitCount}>
      <h2>Physical inventory count</h2>
      <p className="sb-muted">Enter the physically counted quantity. The system records the variance and will not allow a count below reserved stock.</p>
      <div className="sb-form-grid">
        <label>Product<select required value={productId} onChange={e=>{setProductId(e.target.value);setCountForm(v=>({...v,variant_id:""}));}}><option value="">Choose product</option>{products.map(p=><option key={p.id} value={p.id}>{p.name}</option>)}</select></label>
        <label>Variant / SKU<select required value={countForm.variant_id} onChange={e=>setCountForm(v=>({...v,variant_id:e.target.value}))}><option value="">Choose variant</option>{variants.map(v=><option key={v.id} value={v.id}>{v.sku} · ₹{v.selling_price}</option>)}</select></label>
        <label>Stock location<select required value={countForm.location_id} onChange={e=>setCountForm(v=>({...v,location_id:e.target.value}))}><option value="">Choose location</option>{locations.map(l=><option key={l.id} value={l.id}>{l.name}</option>)}</select></label>
        <label>Physically counted quantity<input required type="number" min="0" step="0.001" value={countForm.counted_quantity} onChange={e=>setCountForm(v=>({...v,counted_quantity:e.target.value}))}/></label>
        <label>Unit cost if count increases (₹)<input type="number" min="0" step="0.0001" value={countForm.unit_cost} onChange={e=>setCountForm(v=>({...v,unit_cost:e.target.value}))}/></label>
        <label>Batch / lot code for increase<input maxLength="100" value={countForm.batch_code} onChange={e=>setCountForm(v=>({...v,batch_code:e.target.value}))}/></label>
        <label>Expiry date for increase<input type="date" value={countForm.expiry_date} onChange={e=>setCountForm(v=>({...v,expiry_date:e.target.value}))}/></label>
        <label>Cost allocation for decrease<select value={countForm.allocation_method} onChange={e=>setCountForm(v=>({...v,allocation_method:e.target.value}))}><option value="fifo">FIFO</option><option value="fefo">FEFO</option></select></label>
        <label className="sb-span-all">Count notes / reference<input required minLength="3" maxLength="500" value={countForm.note} onChange={e=>setCountForm(v=>({...v,note:e.target.value}))}/></label>
      </div>
      <button className="sb-primary" disabled={busy || !locations.length} type="submit">{busy ? "Saving…" : "Reconcile physical count"}</button>
      <button className="sb-secondary" type="button" disabled={busy || !countForm.location_id || !countForm.variant_id || countForm.counted_quantity==="" || !countForm.note} onClick={()=>submitInventoryApproval("physical_count",countForm.location_id,{variant_id:Number(countForm.variant_id),location_id:Number(countForm.location_id),counted_quantity:Number(countForm.counted_quantity),unit_cost:countForm.unit_cost===""?null:Number(countForm.unit_cost),batch_code:countForm.batch_code||null,expiry_date:countForm.expiry_date||null,allocation_method:countForm.allocation_method,note:countForm.note})}>Submit count for approval</button>
    </form>
    <form className="sb-form" onSubmit={submitTransfer}>
      <h2>Transfer stock between locations</h2>
      <p className="sb-muted">Source stock is reduced and destination stock increased in one database transaction. Reserved units are not transferable.</p>
      <div className="sb-form-grid">
        <label>Product<select required value={productId} onChange={e=>{setProductId(e.target.value);setTransferForm(v=>({...v,variant_id:""}));}}><option value="">Choose product</option>{products.map(p=><option key={p.id} value={p.id}>{p.name}</option>)}</select></label>
        <label>Variant / SKU<select required value={transferForm.variant_id} onChange={e=>setTransferForm(v=>({...v,variant_id:e.target.value}))}><option value="">Choose variant</option>{variants.map(v=><option key={v.id} value={v.id}>{v.sku} · ₹{v.selling_price}</option>)}</select></label>
        <label>From location<select required value={transferForm.source_location_id} onChange={e=>setTransferForm(v=>({...v,source_location_id:e.target.value}))}><option value="">Choose source</option>{locations.map(l=><option key={l.id} value={l.id}>{l.name}</option>)}</select></label>
        <label>To location<select required value={transferForm.destination_location_id} onChange={e=>setTransferForm(v=>({...v,destination_location_id:e.target.value}))}><option value="">Choose destination</option>{locations.filter(l=>l.is_fulfillable !== false && String(l.id)!==transferForm.source_location_id).map(l=><option key={l.id} value={l.id}>{l.name}</option>)}</select></label>
        <label>Quantity to transfer<input required type="number" min="0.001" step="0.001" value={transferForm.quantity} onChange={e=>setTransferForm(v=>({...v,quantity:e.target.value}))}/></label>
        <label className="sb-span-all">Reason / reference<input required minLength="3" maxLength="500" value={transferForm.note} onChange={e=>setTransferForm(v=>({...v,note:e.target.value}))}/></label>
      </div>
      <button className="sb-primary" disabled={busy || locations.length < 2} type="submit">{busy ? "Saving…" : "Transfer stock"}</button>
      <button className="sb-secondary" type="button" disabled={busy || !transferForm.source_location_id || !transferForm.destination_location_id || !transferForm.variant_id || !transferForm.quantity || !transferForm.note} onClick={()=>submitInventoryApproval("transfer",transferForm.source_location_id,{variant_id:Number(transferForm.variant_id),source_location_id:Number(transferForm.source_location_id),destination_location_id:Number(transferForm.destination_location_id),quantity:Number(transferForm.quantity),note:transferForm.note})}>Submit transfer for approval</button>
      {locations.length < 2 && <p className="sb-muted">Create at least two active locations to transfer stock.</p>}
    </form>
    </div>}
    {activeSection === "approvals" && <div className="inventory-section"><div className="sb-data-card">
      <h2>Inventory approval queue ({approvalRequests.length})</h2>
      <p className="sb-muted">Requests are bound to their submitted payload and policy version. Requesters cannot approve their own operations. Once all stages approve, the requester must submit the unchanged operation again to post it.</p>
      {approvalRequests.length ? approvalRequests.map(item=><div className="sb-form-grid" key={item.id}>
        <div><strong>#{item.id} · {item.event_type}</strong><p className="sb-muted">{item.location_name} · {item.status} · {item.created_by_email}</p>
          {(item.decisions||[]).map(d=><p className="sb-muted" key={d.stage_sequence}>Stage {d.stage_sequence}: {d.decision} — {d.actor_email}</p>)}</div>
        {item.can_decide && <div><button className="sb-secondary" type="button" disabled={busy} onClick={()=>decideInventoryApproval(item.id,"approved")}>Approve next stage</button> <button className="sb-secondary" type="button" disabled={busy} onClick={()=>decideInventoryApproval(item.id,"rejected")}>Reject</button></div>}
      </div>) : <p className="sb-empty">No inventory approval requests.</p>}
    </div>
    </div>}
    {activeSection === "stock" && <div className="inventory-section"><div className="sb-data-card">
      <h2>Replenishment watchlist</h2>
      <p className="sb-muted">Balances with 5 or fewer available units. Review these and raise purchase orders in Purchasing; no orders are created automatically.</p>
      {balances.filter(b => Number(b.available ?? (Number(b.on_hand || 0) - Number(b.reserved || 0))) <= 5).length ? <div className="sb-table-wrap"><table><thead><tr><th>SKU</th><th>Location</th><th>Available</th><th>On hand</th><th>Action</th></tr></thead><tbody>{balances.filter(b => Number(b.available ?? (Number(b.on_hand || 0) - Number(b.reserved || 0))) <= 5).map((b,i)=><tr key={"replenish-"+b.variant_id+"-"+b.location_id+"-"+i}><td>{b.sku}</td><td>{b.location_name}</td><td>{b.available ?? (Number(b.on_hand || 0) - Number(b.reserved || 0))}</td><td>{b.on_hand}</td><td><button type="button" disabled={busy} onClick={()=>createReplenishmentRequisition(b)}>Create purchase request</button></td></tr>)}</tbody></table></div> : <p className="sb-empty">No balances currently meet the replenishment threshold.</p>}
    </div>
    <div className="sb-data-card"><div className="sb-data-heading"><h2>Stock balances ({balances.length})</h2><button type="button" onClick={loadBase}>Refresh</button></div>
      {balances.length ? <div className="sb-table-wrap"><table><thead><tr><th>SKU</th><th>Location</th><th>On hand</th><th>Reserved</th><th>Available</th></tr></thead><tbody>{balances.map((b,i)=><tr key={b.variant_id+"-"+b.location_id+"-"+i}><td>{b.sku}</td><td>{b.location_name}</td><td>{b.on_hand}</td><td>{b.reserved}</td><td>{b.available}</td></tr>)}</tbody></table></div> : <p className="sb-empty">No stock balances found.</p>}
    </div>
    <div className="sb-data-card"><h2>Cost reconciliation ({costReconciliation.length})</h2>
      <p className="sb-muted">Compare physical on-hand quantity with valued receipt layers. Any non-zero difference requires investigation; do not issue unvalued stock.</p>
      {costReconciliation.length ? <div className="sb-table-wrap"><table><thead><tr><th>SKU</th><th>Location</th><th>On hand</th><th>Valued</th><th>Expired</th><th>Unvalued / excess</th></tr></thead><tbody>{costReconciliation.map(row=><tr key={row.variant_id+"-"+row.location_id}><td>{row.sku}</td><td>{row.location_name}</td><td>{row.on_hand}</td><td>{row.valued_quantity}</td><td>{row.expired_quantity}</td><td>{row.unvalued_or_overvalued_quantity}</td></tr>)}</tbody></table></div> : <p className="sb-empty">No stock balances to reconcile.</p>}
    </div>
    <div className="sb-data-card"><h2>Cost layers ({costLayers.length})</h2>
      <p className="sb-muted">Remaining stock value is based on recorded receipt costs. Expired batches are excluded from FIFO/FEFO issues.</p>
      {costLayers.length ? <div className="sb-table-wrap"><table><thead><tr><th>SKU</th><th>Location</th><th>Batch</th><th>Expiry</th><th>Remaining</th><th>Unit cost</th><th>Value</th></tr></thead><tbody>{costLayers.map(layer=><tr key={layer.id}><td>{layer.sku}</td><td>{layer.location_name}</td><td>{layer.batch_code || "—"}</td><td>{layer.expiry_date || "—"}</td><td>{layer.remaining_quantity}</td><td>₹{layer.unit_cost}</td><td>₹{layer.remaining_value}</td></tr>)}</tbody></table></div> : <p className="sb-empty">No valued receipt layers found. Existing stock needs an approved opening valuation before it can be issued.</p>}
    </div>
    <div className="sb-data-card"><h2>Recent movements ({movements.length})</h2>
      {movements.length ? <div className="sb-table-wrap"><table><thead><tr><th>Date</th><th>Variant ID</th><th>Location ID</th><th>Type</th><th>Quantity</th><th>Note</th></tr></thead><tbody>{movements.map(m=><tr key={m.id}><td>{new Date(m.created_at).toLocaleString()}</td><td>{m.variant_id}</td><td>{m.location_id}</td><td>{m.movement_type}</td><td>{m.quantity}</td><td>{m.note}</td></tr>)}</tbody></table></div> : <p className="sb-empty">No inventory movements found.</p>}
    </div>
    </div>}
    {activeSection === "returns" && <div className="inventory-section">
      <div className="sb-data-card">
        <div className="sb-data-heading"><h2>Customer returns & disposition</h2><button type="button" disabled={returnLoading} onClick={()=>{setSelectedReturn(null);setSelectedQuarantineGrn(null);setReturnLoading(true);Promise.all([apiRequest("/fulfilment/returns?limit=100"),apiRequest("/purchasing/grns?quarantined_only=true&limit=100"),apiRequest("/inventory/expired-stock?limit=100")]).then(([r,g,x])=>{setReturns(r.items||[]);setQuarantineGrns(g.items||[]);setExpiredStock(x.items||[]);}).catch(e=>setError(e.message||"Unable to refresh inventory return queues.")).finally(()=>setReturnLoading(false));}}>{returnLoading ? "Loading…" : "Refresh"}</button></div>
        <p className="sb-muted">Inventory visibility for returns managed by Fulfilment. Inspection and disposition remain owned by the Fulfilment workflow so stock cannot be posted twice.</p>
        {returns.length ? returns.map(item=><button type="button" className="sb-purchasing-attention-row" key={item.id} onClick={()=>openInventoryReturn(item.id)}><span><strong>{item.return_number}</strong><small>{item.order_number} · {item.shipment_reference} · {item.line_count} lines</small></span><em>{item.status}</em></button>) : <p className="sb-empty">{returnLoading ? "Loading customer returns…" : "No customer returns recorded."}</p>}
      </div>
      {selectedReturn && <div className="sb-data-card"><h2>{selectedReturn.return_number} · {selectedReturn.order_number}</h2><p className="sb-muted">{selectedReturn.reason} · {selectedReturn.status}</p><div className="sb-table-wrap"><table><thead><tr><th>SKU</th><th>Product</th><th>Requested</th><th>Received</th><th>Inspection</th><th>Disposition</th><th>Quarantine remaining</th><th>Released to saleable</th><th>Posted</th><th>Action</th></tr></thead><tbody>{(selectedReturn.lines||[]).map(line=><tr key={line.id}><td>{line.sku}</td><td>{line.product_name}</td><td>{line.requested_quantity}</td><td>{line.received_quantity}</td><td>{line.inspection_status}</td><td>{line.disposition || "Pending"}</td><td>{line.quarantine_remaining_quantity || 0}{Number(line.quarantine_remaining_quantity)>Number(line.quarantine_releasable_quantity || 0) ? " (expired blocked)" : ""}</td><td>{line.quarantine_released_quantity || 0}</td><td>{line.disposition_posted_at ? "Yes" : "No"}</td><td>{line.disposition === "quarantine" && Number(line.quarantine_releasable_quantity)>0 ? <button type="button" disabled={returnReleaseBusyId === line.id || !returnReleaseLocationId || returnReleaseReason.trim().length<3} onClick={()=>releaseCustomerReturnQuarantine(line)}>{returnReleaseBusyId === line.id ? "Releasing…" : "Release"}</button> : "—"}</td></tr>)}</tbody></table></div><div className="sb-form-grid"><label>Saleable destination<select value={returnReleaseLocationId} onChange={e=>setReturnReleaseLocationId(e.target.value)}><option value="">Choose active store / warehouse</option>{locations.filter(location=>location.is_active!==false && location.is_fulfillable!==false).map(location=><option key={location.id} value={location.id}>{location.name}</option>)}</select></label><label>Reinspection / release reason<input maxLength="1000" value={returnReleaseReason} onChange={e=>setReturnReleaseReason(e.target.value)} placeholder="QC reinspection passed; packaging intact"/></label></div><p className="sb-muted">Return disposition is first posted by Fulfilment. Release moves only non-expired remaining quarantine cost layers within the same legal establishment; expired quantities remain blocked. Inventory movement and cost-layer provenance are retained.</p></div>}
      <div className="sb-data-card">
        <h2>Supplier receipt quarantine</h2>
        <p className="sb-muted">Review supplier GRN quantities awaiting release. A release moves only previously quarantined units into accepted stock, creates their cost layers and posts the configured inventory/GRNI accounting event. Every release requires a reason and is idempotent.</p>
        {quarantineGrns.length ? quarantineGrns.map(grn=><button type="button" className="sb-purchasing-attention-row" key={grn.id} onClick={()=>openQuarantineGrn(grn.id)}><span><strong>{grn.grn_number}</strong><small>{grn.supplier_name} · {grn.purchase_number} · {grn.quarantined_quantity} quarantined</small></span><em>{grn.status}</em></button>) : <p className="sb-empty">No supplier GRN quantities are currently quarantined.</p>}
      </div>
      <div className="sb-data-card">
        <h2>Expired stock quarantine</h2>
        <p className="sb-muted">Expired layers are excluded from FIFO/FEFO sale allocation. Move them out of a fulfilable facility into a non-fulfillable quarantine location. The transfer preserves original batch, expiry, cost and layer provenance; it does not write off the stock.</p>
        <div className="sb-form-grid"><label>Quarantine destination<select value={expiredQuarantineLocationId} onChange={e=>setExpiredQuarantineLocationId(e.target.value)}><option value="">Choose non-fulfillable location</option>{locations.filter(location=>location.is_active!==false && location.is_fulfillable===false).map(location=><option key={location.id} value={location.id}>{location.name}</option>)}</select></label><label>Quarantine reason<input maxLength="1000" value={expiredQuarantineReason} onChange={e=>setExpiredQuarantineReason(e.target.value)} placeholder="Expired as of inspection date"/></label></div>
        {expiredStock.length ? <div className="sb-table-wrap"><table><thead><tr><th>SKU</th><th>Product</th><th>Source facility</th><th>Expired qty</th><th>Earliest expiry</th><th>Value ₹</th><th>Action</th></tr></thead><tbody>{expiredStock.map(item=>{const key=`${item.variant_id}:${item.location_id}`;return <tr key={key}><td>{item.sku}</td><td>{item.product_name}</td><td>{item.location_name}</td><td>{item.expired_quantity}</td><td>{item.earliest_expiry}</td><td>{Number(item.expired_value||0).toLocaleString("en-IN",{minimumFractionDigits:2,maximumFractionDigits:2})}</td><td><button type="button" disabled={expiredQuarantineBusyKey===key || !expiredQuarantineLocationId || expiredQuarantineReason.trim().length<3} onClick={()=>quarantineExpiredStock(item)}>{expiredQuarantineBusyKey===key ? "Moving…" : "Quarantine all expired"}</button></td></tr>;})}</tbody></table></div> : <p className="sb-empty">No expired stock remains in active fulfilable locations.</p>}
      </div>
      {selectedQuarantineGrn && <div className="sb-data-card"><h2>{selectedQuarantineGrn.grn_number} · Quarantine release</h2><p className="sb-muted">{selectedQuarantineGrn.status} · Only quantities currently in quarantine can be released. Accepted stock is posted at its recorded receipt unit cost.</p>
        <form className="sb-form" onSubmit={releaseQuarantinedStock}>
          {(selectedQuarantineGrn.lines||[]).filter(line=>Number(line.quarantined_quantity)>0).map(line=><div className="sb-form-grid" key={line.id}>
            <div><strong>{line.product_name} · {line.sku}</strong><p className="sb-muted">Batch {line.batch_code || "—"} · Expiry {line.expiry_date || "—"} · Quarantined {line.quarantined_quantity} · Unit cost ₹{line.unit_cost}</p></div>
            <label>Release quantity<input type="number" min="0" max={Number(line.quarantined_quantity)} step="0.001" value={quarantineReleaseQuantities[line.id] || ""} onChange={e=>setQuarantineReleaseQuantities(old=>({...old,[line.id]:e.target.value}))}/></label>
            <label>Inspection / release reason<input required minLength="3" maxLength="1000" value={quarantineReleaseReasons[line.id] || ""} onChange={e=>setQuarantineReleaseReasons(old=>({...old,[line.id]:e.target.value}))}/></label>
          </div>)}
          <button className="sb-primary" type="submit" disabled={busy || !(selectedQuarantineGrn.lines||[]).some(line=>Number(line.quarantined_quantity)>0)}>{busy ? "Posting…" : "Release selected quarantined stock"}</button>
        </form>
      </div>}
    </div>}
    {activeSection === "policy" && <div className="inventory-section"><OrganisationPolicyPanel domain="inventory" /></div>}
  </section>;
}
