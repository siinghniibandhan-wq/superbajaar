import { useEffect, useState } from "react";
import { apiRequest } from "../../services/api.js";

const moneyQty = value => Number(value || 0).toLocaleString("en-IN", { maximumFractionDigits: 3 });
const label = value => String(value || "").replaceAll("_", " ").replace(/\b\w/g, c => c.toUpperCase());

export default function FulfilmentWorkspace({ onBack }) {
  const [shipments,setShipments] = useState([]);
  const [tasks,setTasks] = useState([]);
  const [selected,setSelected] = useState(null);
  const [lines,setLines] = useState({});
  const [packages,setPackages] = useState([]);
  const [returns,setReturns] = useState([]);
  const [locations,setLocations] = useState([]);
  const [dispositions,setDispositions] = useState({});
  const [returnShipment,setReturnShipment] = useState("");
  const [returnReason,setReturnReason] = useState("");
  const [returnOrderLines,setReturnOrderLines] = useState([]);
  const [returnQuantities,setReturnQuantities] = useState({});
  const [selectedReturn,setSelectedReturn] = useState(null);
  const [busy,setBusy] = useState(false);
  const [error,setError] = useState("");
  const [notice,setNotice] = useState("");

  async function load() {
    setBusy(true); setError("");
    try {
      const [s,t,r,l] = await Promise.all([
        apiRequest("/delivery/shipments?limit=200"),
        apiRequest("/fulfilment/pick-tasks?limit=200"),
        apiRequest("/fulfilment/returns?limit=100"),
        apiRequest("/inventory/locations?limit=500")
      ]);
      setShipments(s.items || []); setTasks(t.items || []); setReturns(r.items || []); setLocations(l.items || []);
    } catch(e) { setError(e.message || "Unable to load Fulfilment."); }
    finally { setBusy(false); }
  }
  useEffect(() => { load(); }, []);

  async function openTask(id) {
    setError(""); setNotice("");
    try {
      const t = await apiRequest("/fulfilment/pick-tasks/" + id);
      setSelected(t); setPackages(t.packages || []);
      setLines(Object.fromEntries((t.lines || []).map(line => [line.id, {
        picked_quantity:String(line.picked_quantity ?? 0),
        short_quantity:String(line.short_quantity ?? 0),
        short_reason:line.short_reason || ""
      }])));
    } catch(e) { setError(e.message || "Unable to open pick task."); }
  }
  async function createTask(shipment) {
    setBusy(true); setError(""); setNotice("");
    try {
      const t = await apiRequest("/fulfilment/shipments/" + shipment.id + "/pick-task",{method:"POST"});
      setNotice("Pick task created for " + shipment.shipment_reference + ".");
      await load(); await openTask(t.id);
    } catch(e) { setError(e.message || "Unable to create pick task."); }
    finally { setBusy(false); }
  }
  async function saveLine(line) {
    const value=lines[line.id] || {};
    setBusy(true); setError(""); setNotice("");
    try {
      await apiRequest("/fulfilment/pick-tasks/" + selected.id + "/lines/" + line.id,{method:"PATCH",body:JSON.stringify({
        picked_quantity:value.picked_quantity,short_quantity:value.short_quantity,short_reason:value.short_reason || null
      })});
      setNotice("Pick line saved. Inventory balances are unchanged until dispatch.");
      await openTask(selected.id); await load();
    } catch(e) { setError(e.message || "Unable to save pick line."); }
    finally { setBusy(false); }
  }
  async function completePick() {
    setBusy(true); setError(""); setNotice("");
    try {
      await apiRequest("/fulfilment/pick-tasks/" + selected.id + "/complete",{method:"POST"});
      setNotice("Picking completed. Create packages for picked quantities.");
      await openTask(selected.id); await load();
    } catch(e) { setError(e.message || "Unable to complete picking."); }
    finally { setBusy(false); }
  }
  async function createPackage() {
    const picked=(selected.lines || []).map(line=>({...line,remaining_to_pack:Number(line.picked_quantity)-Number(line.packed_quantity||0)})).filter(line=>line.remaining_to_pack>0);
    if(!picked.length){setError("There are no picked quantities to pack.");return;}
    setBusy(true); setError(""); setNotice("");
    try {
      const nextNo=(selected.packages || []).length+1;
      await apiRequest("/fulfilment/shipments/" + selected.shipment_id + "/packages",{method:"POST",body:JSON.stringify({
        package_number:"PKG-" + selected.shipment_id + "-" + nextNo,
        lines:picked.map(line=>({pick_task_line_id:line.id,order_line_id:line.order_line_id,quantity:line.remaining_to_pack}))
      })});
      setNotice("Package created. Seal it after checking the contents.");
      await openTask(selected.id);
    } catch(e) { setError(e.message || "Unable to create package."); }
    finally { setBusy(false); }
  }
  async function loadReturnOrder(shipmentId) {
    setReturnShipment(shipmentId); setReturnOrderLines([]); setReturnQuantities({});
    if(!shipmentId) return;
    const shipment=shipments.find(x=>String(x.id)===String(shipmentId));
    if(!shipment) return;
    try {
      const order=await apiRequest("/orders/"+shipment.order_id);
      setReturnOrderLines(order.lines || []);
      setReturnQuantities(Object.fromEntries((order.lines || []).map(line=>[line.id,""])));
    } catch(e) { setError(e.message || "Unable to load order lines for return."); }
  }
  async function submitReturn() {
    const shipment=shipments.find(x=>String(x.id)===String(returnShipment));
    const lines=returnOrderLines.filter(line=>Number(returnQuantities[line.id])>0)
      .map(line=>({order_line_id:line.id,quantity:returnQuantities[line.id]}));
    if(!shipment || !returnReason.trim() || !lines.length){setError("Select a shipment, enter a reason and at least one return quantity.");return;}
    setBusy(true); setError(""); setNotice("");
    try {
      await apiRequest("/fulfilment/shipments/"+shipment.id+"/returns",{method:"POST",body:JSON.stringify({reason:returnReason,lines})});
      setReturnReason(""); setReturnShipment(""); setReturnOrderLines([]); setReturnQuantities({});
      setNotice("Return request recorded. Physical receipt and inspection are next.");
      await load();
    } catch(e) { setError(e.message || "Unable to create return."); }
    finally { setBusy(false); }
  }
  async function openReturn(id) {
    try { setSelectedReturn(await apiRequest("/fulfilment/returns/"+id)); }
    catch(e) { setError(e.message || "Unable to open return."); }
  }
  async function receiveReturn(id) {
    setBusy(true); setError("");
    try { await apiRequest("/fulfilment/returns/"+id+"/receive",{method:"POST"}); setSelectedReturn(await apiRequest("/fulfilment/returns/"+id)); await load(); }
    catch(e) { setError(e.message || "Unable to receive return."); }
    finally { setBusy(false); }
  }
  async function inspectReturnLine(line,status) {
    setBusy(true); setError("");
    try {
      await apiRequest("/fulfilment/returns/"+selectedReturn.id+"/lines/"+line.id+"/inspection",{method:"PATCH",body:JSON.stringify({
        received_quantity:line.received_quantity,inspection_status:status,inspection_note:line.inspection_note || null
      })});
      setSelectedReturn(await apiRequest("/fulfilment/returns/"+selectedReturn.id)); await load();
    } catch(e) { setError(e.message || "Unable to save inspection."); }
    finally { setBusy(false); }
  }
  async function postDisposition(line) {
    const choice=dispositions[line.id] || {};
    if(!choice.disposition){setError("Select a return disposition.");return;}
    const needsLocation=choice.disposition !== "write_off";
    if(needsLocation && !choice.location_id){setError("Select the controlled destination location.");return;}
    setBusy(true); setError(""); setNotice("");
    try {
      const body={disposition:choice.disposition,location_id:needsLocation?Number(choice.location_id):null};
      const result=await apiRequest("/fulfilment/returns/"+selectedReturn.id+"/lines/"+line.id+"/disposition",{method:"POST",body:JSON.stringify(body)});
      setNotice("Return disposition posted. Original stock cost and Accounting are reconciled.");
      setSelectedReturn(await apiRequest("/fulfilment/returns/"+selectedReturn.id)); await load();
    } catch(e) { setError(e.message || "Unable to post return disposition."); }
    finally { setBusy(false); }
  }

  async function sealPackage(id) {
    setBusy(true); setError(""); setNotice("");
    try {
      await apiRequest("/fulfilment/packages/" + id + "/seal",{method:"PATCH"});
      setNotice("Package sealed.");
      await openTask(selected.id); await load();
    } catch(e) { setError(e.message || "Unable to seal package."); }
    finally { setBusy(false); }
  }

  return <section className="sb-workspace">
    <button className="sb-back" type="button" onClick={onBack}>← All workspaces</button>
    <p className="sb-eyebrow">OPERATIONS · WAREHOUSE EXECUTION</p><h1>Fulfilment</h1>
    <p>Pick reserved order quantities, record short picks, pack and seal packages, then hand over to Delivery for dispatch. Picking and packing never decrement stock.</p>
    {error && <div className="sb-alert" role="alert">{error}</div>}
    {notice && <div className="sb-notice" role="status">{notice}</div>}
    <div className="sb-dashboard-actions"><button type="button" onClick={load} disabled={busy}>{busy?"Working…":"Refresh"}</button></div>
    <div className="sb-kpi-grid">
      <article><small>Active shipments</small><strong>{shipments.filter(x=>!["delivered","cancelled","returned"].includes(x.status)).length}</strong></article>
      <article><small>Pick tasks</small><strong>{tasks.length}</strong></article>
      <article><small>Open returns</small><strong>{returns.filter(x=>!["closed","rejected"].includes(x.status)).length}</strong></article>
    </div>
    <h2>Pick queue</h2>
    <div className="sb-orders-list">
      {shipments.filter(s=>!["delivered","cancelled","returned"].includes(s.status)).map(s=>{
        const task=tasks.find(t=>Number(t.shipment_id)===Number(s.id));
        return <article className="sb-order-card" key={s.id}>
          <div className="sb-delivery-row"><div><strong>{s.shipment_reference}</strong><small>{s.order_number} · {s.recipient_name}</small></div><span className={"sb-order-status status-"+s.status}>{label(s.status)}</span></div>
          {task ? <button type="button" onClick={()=>openTask(task.id)}>Open pick task · {label(task.status)}</button>
            : <button type="button" disabled={busy} onClick={()=>createTask(s)}>Create pick task</button>}
        </article>;
      })}
      {!shipments.length && <p className="sb-empty">No shipments found.</p>}
    </div>
    {selected && <section className="sb-order-card" style={{marginTop:24,padding:18}}>
      <div className="sb-delivery-row"><div><h2>Pick task #{selected.id}</h2><small>{selected.shipment_reference} · {selected.order_number}</small></div><span className="sb-order-status">{label(selected.status)}</span></div>
      <h3>Pick verification</h3>
      {(selected.lines || []).map(line=><div key={line.id} className="sb-delivery-edit" style={{marginBottom:10}}>
        <div><strong>{line.product_name}</strong><small>{line.sku} · {line.location_name} · Requested {moneyQty(line.requested_quantity)} · Packed {moneyQty(line.packed_quantity)}</small></div>
        <label>Picked<input type="number" min="0" max={line.requested_quantity} step="0.001" value={lines[line.id]?.picked_quantity ?? "0"} disabled={["completed","short","cancelled"].includes(selected.status)} onChange={e=>setLines(old=>({...old,[line.id]:{...old[line.id],picked_quantity:e.target.value}}))}/></label>
        <label>Short quantity<input type="number" min="0" max={line.requested_quantity} step="0.001" value={lines[line.id]?.short_quantity ?? "0"} disabled={["completed","short","cancelled"].includes(selected.status)} onChange={e=>setLines(old=>({...old,[line.id]:{...old[line.id],short_quantity:e.target.value}}))}/></label>
        <label>Short reason<input value={lines[line.id]?.short_reason ?? ""} disabled={["completed","short","cancelled"].includes(selected.status)} onChange={e=>setLines(old=>({...old,[line.id]:{...old[line.id],short_reason:e.target.value}}))}/></label>
        {!["completed","short","cancelled"].includes(selected.status) && <button type="button" disabled={busy} onClick={()=>saveLine(line)}>Save line</button>}
      </div>)}
      {!["completed","short","cancelled"].includes(selected.status) && <button type="button" disabled={busy} onClick={completePick}>Complete picking</button>}
      <h3>Packages</h3>
      {(packages || []).map(p=><div key={p.id} className="sb-delivery-row"><strong>{p.package_number}</strong><span>{label(p.status)}</span>{p.status==="draft" && <button type="button" disabled={busy} onClick={()=>sealPackage(p.id)}>Seal package</button>}</div>)}
      {["completed","short"].includes(selected.status) && <button type="button" disabled={busy} onClick={createPackage}>Create package from picked quantities</button>}
      <p className="sb-notice"><strong>Stock control</strong><span>Pick and pack records do not change on-hand or reserved stock. Physical issue and COGS must be recorded through the authorised Inventory dispatch workflow.</span></p>
    </section>}
    <h2>Returns & inspection</h2>
    <article className="sb-order-card" style={{padding:16,marginBottom:14}}>
      <label>Shipment<select value={returnShipment} onChange={e=>loadReturnOrder(e.target.value)}><option value="">Select a dispatched shipment</option>{shipments.filter(s=>["delivered","returned","failed","in_transit"].includes(s.status)).map(s=><option key={s.id} value={s.id}>{s.shipment_reference} · {s.order_number}</option>)}</select></label>
      <label>Return reason<input value={returnReason} onChange={e=>setReturnReason(e.target.value)} placeholder="Reason for return"/></label>
      {returnOrderLines.map(line=><label key={line.id}>{line.product_name || line.sku} · max ordered {moneyQty(line.quantity)}<input type="number" min="0" max={line.quantity} step="0.001" value={returnQuantities[line.id] || ""} onChange={e=>setReturnQuantities(old=>({...old,[line.id]:e.target.value}))}/></label>)}
      <button type="button" disabled={busy || !returnShipment} onClick={submitReturn}>Create return request</button>
    </article>
    <div className="sb-orders-list">{returns.map(r=><article className="sb-order-card" key={r.id}><strong>{r.return_number}</strong><small>{r.order_number} · {r.shipment_reference}</small><span>{label(r.status)}</span><p>{r.reason}</p><button type="button" onClick={()=>openReturn(r.id)}>Open return</button></article>)}{!returns.length&&<p className="sb-empty">No return requests recorded.</p>}</div>
    {selectedReturn && <article className="sb-order-card" style={{padding:16,marginTop:14}}>
      <h3>{selectedReturn.return_number} · {label(selectedReturn.status)}</h3><p>{selectedReturn.reason}</p>
      {selectedReturn.status==="requested" && <button type="button" disabled={busy} onClick={()=>receiveReturn(selectedReturn.id)}>Confirm physical receipt</button>}
      {selectedReturn.lines.map(line=><div key={line.id} className="sb-order-card" style={{padding:12,marginBottom:10}}>
        <div className="sb-delivery-row"><span><strong>{line.product_name}</strong><small>{line.sku} · Requested {moneyQty(line.requested_quantity)} · Received {moneyQty(line.received_quantity)}</small></span><span>{label(line.inspection_status)}</span></div>
        {selectedReturn.status==="inspection" && line.inspection_status==="pending" && <div className="sb-dashboard-actions"><button type="button" disabled={busy} onClick={()=>inspectReturnLine(line,"accepted")}>Accept</button><button type="button" disabled={busy} onClick={()=>inspectReturnLine(line,"damaged")}>Damaged</button><button type="button" disabled={busy} onClick={()=>inspectReturnLine(line,"quarantined")}>Quarantine</button><button type="button" disabled={busy} onClick={()=>inspectReturnLine(line,"rejected")}>Reject</button></div>}
        {line.disposition_posted_at ? <p className="sb-notice"><strong>{label(line.disposition)} posted</strong><span>{line.accounting_voucher_id ? "Accounting voucher #"+line.accounting_voucher_id : "No inventory value was recognised for this write-off."}</span></p>
          : selectedReturn.status==="approved" && <div className="sb-delivery-edit">
            <label>Disposition<select value={dispositions[line.id]?.disposition || ""} onChange={e=>setDispositions(old=>({...old,[line.id]:{...old[line.id],disposition:e.target.value,location_id:""}}))}><option value="">Select disposition</option><option value="restock">Restock (sellable)</option><option value="quarantine">Quarantine (non-fulfillable)</option><option value="repair">Repair (non-fulfillable)</option><option value="write_off">Write off</option></select></label>
            {dispositions[line.id]?.disposition && dispositions[line.id].disposition!=="write_off" && <label>Destination location<select value={dispositions[line.id]?.location_id || ""} onChange={e=>setDispositions(old=>({...old,[line.id]:{...old[line.id],location_id:e.target.value}}))}><option value="">Select location</option>{locations.filter(x=>x.is_active && (dispositions[line.id].disposition==="restock" ? x.is_fulfillable : !x.is_fulfillable)).map(x=><option key={x.id} value={x.id}>{x.name}</option>)}</select></label>}
            <button type="button" disabled={busy || !dispositions[line.id]?.disposition} onClick={()=>postDisposition(line)}>Post disposition & Accounting</button>
          </div>}
      </div>)}
      <p className="sb-notice"><strong>Controlled return posting</strong><span>Restock, quarantine and repair preserve the original dispatch valuation and reverse COGS through approved Finance mappings. Holding locations are excluded from normal order reservation.</span></p>
    </article>}
  </section>;
}
