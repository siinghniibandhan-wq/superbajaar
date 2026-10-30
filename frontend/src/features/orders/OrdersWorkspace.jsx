import { useCallback, useEffect, useMemo, useState } from "react";
import { apiRequest } from "../../services/api.js";

const statuses = ["placed","confirmed","processing","ready_for_dispatch","dispatched","delivered","cancelled"];
const nextStatuses = {
  placed:["confirmed","cancelled"], confirmed:["processing","cancelled"],
  processing:["ready_for_dispatch","cancelled"], ready_for_dispatch:["dispatched","cancelled"],
  dispatched:["delivered"], draft:["placed","cancelled"], delivered:[], cancelled:[]
};
const label = value => String(value || "").replaceAll("_"," ").replace(/\b\w/g, c => c.toUpperCase());
const money = value => new Intl.NumberFormat("en-IN",{style:"currency",currency:"INR"}).format(Number(value || 0));

export default function OrdersWorkspace({ onBack }) {
  const [orders,setOrders] = useState([]);
  const [total,setTotal] = useState(0);
  const [status,setStatus] = useState("");
  const [channel,setChannel] = useState("");
  const [search,setSearch] = useState("");
  const [loading,setLoading] = useState(false);
  const [busy,setBusy] = useState(null);
  const [error,setError] = useState("");
  const [notice,setNotice] = useState("");
  const [selected,setSelected] = useState(null);
  const [detail,setDetail] = useState(null);
  const [detailLoading,setDetailLoading] = useState(false);
  const [history,setHistory] = useState(null);
  const [historyLoading,setHistoryLoading] = useState(false);
  const [showCreate,setShowCreate] = useState(false);
  const [manualPin,setManualPin] = useState("");
  const [pinChecked,setPinChecked] = useState(false);
  const [pinBusy,setPinBusy] = useState(false);
  const [pinMessage,setPinMessage] = useState("");
  const [manualVariants,setManualVariants] = useState([]);
  const [manualCart,setManualCart] = useState([]);
  const [manualCustomer,setManualCustomer] = useState({name:"",phone:"",notes:""});
  const [manualSaving,setManualSaving] = useState(false);
  const [manualNotice,setManualNotice] = useState("");
  const [manualError,setManualError] = useState("");
  const manualTotal = useMemo(()=>manualCart.reduce((sum,line)=>sum+Number(line.selling_price||0)*line.quantity,0),[manualCart]);
  const load = useCallback(async () => {
    setLoading(true); setError("");
    try {
      const params = new URLSearchParams({limit:"200"});
      if(status) params.set("status",status);
      if(channel) params.set("channel",channel);
      if(search.trim()) params.set("search",search.trim());
      const result = await apiRequest("/orders?"+params.toString());
      setOrders(result.items || []); setTotal(result.total || 0);
    } catch(e) { setError(e.message || "Unable to load orders."); }
    finally { setLoading(false); }
  },[status,channel,search]);
  useEffect(()=>{load();},[load]);
  async function openOrder(order) {
    setSelected(order.id); setDetail(null); setDetailLoading(true);
    try { setDetail(await apiRequest("/orders/"+order.id)); }
    catch(e) { setError(e.message || "Unable to load order details."); }
    finally { setDetailLoading(false); }
  }
  async function toggleHistory(order) {
    if (history?.order_id === order.id) { setHistory(null); return; }
    setHistoryLoading(true); setError("");
    try { setHistory(await apiRequest("/orders/"+order.id+"/history?limit=100")); }
    catch(e) { setError(e.message || "Unable to load order status history."); }
    finally { setHistoryLoading(false); }
  }
  async function checkManualPin(event) {
    event.preventDefault();
    setPinBusy(true); setPinMessage(""); setManualError("");
    try {
      const result = await apiRequest("/delivery/serviceability/"+manualPin.trim());
      if (!result.serviceable) {
        setPinChecked(false);
        setPinMessage(result.message || "No active fulfilment location serves this PIN.");
        return;
      }
      const catalogue = await apiRequest("/catalogue/variants?limit=500");
      setManualVariants((catalogue.items || []).filter(item=>item.is_active !== false));
      setPinChecked(true);
      setPinMessage("PIN is serviceable. Add products; the system will select a location that can fulfil every item.");
    } catch(e) {
      setPinChecked(false);
      setManualError(e.message || "Unable to verify this PIN.");
    } finally { setPinBusy(false); }
  }
  function addManualVariant(variant) {
    setManualCart(old=>{
      const existing=old.find(line=>line.id===variant.id);
      return existing ? old.map(line=>line.id===variant.id?{...line,quantity:line.quantity+1}:line) : [...old,{...variant,quantity:1}];
    });
  }
  function updateManualQuantity(id,value) {
    const quantity=Number(value);
    setManualCart(old=>quantity<=0?old.filter(line=>line.id!==id):old.map(line=>line.id===id?{...line,quantity:Math.min(100000,Math.floor(quantity))}:line));
  }
  async function createManualOrder(event) {
    event.preventDefault();
    setManualSaving(true); setManualError(""); setManualNotice("");
    try {
      const order=await apiRequest("/orders",{method:"POST",body:JSON.stringify({
        channel:"manual",customer_name:manualCustomer.name.trim(),customer_phone:manualCustomer.phone.trim()||null,
        delivery_pin:manualPin.trim(),notes:manualCustomer.notes.trim()||null,
        lines:manualCart.map(line=>({variant_id:line.id,quantity:line.quantity}))
      })});
      setManualNotice("Order "+order.order_number+" created. Fulfilment location: "+(order.fulfilment_location?.name || "to be confirmed at shipment creation")+".");
      setShowCreate(false); setPinChecked(false); setManualPin(""); setManualCart([]);
      setManualCustomer({name:"",phone:"",notes:""});
      await load();
    } catch(e) { setManualError(e.message || "Manual order could not be created."); }
    finally { setManualSaving(false); }
  }
  async function updateStatus(order,next) {
    setBusy(order.id); setError(""); setNotice("");
    try {
      await apiRequest("/orders/"+order.id+"/status",{method:"PATCH",body:JSON.stringify({status:next})});
      setNotice(order.order_number+" updated to "+label(next)+".");
      await load();
      if(selected===order.id) await openOrder({...order,status:next});
    } catch(e) { setError(e.message || "Unable to update order."); }
    finally { setBusy(null); }
  }
  return <section className="sb-workspace sb-orders">
    <button className="sb-back" type="button" onClick={onBack}>← All workspaces</button>
    <p className="sb-eyebrow">COMMERCE · ORDER MANAGEMENT</p><h1>Orders</h1>
    <p>Website, POS and manual orders in one order workspace. Status changes follow the permitted order lifecycle.</p>
    <div className="sb-orders-toolbar">
      <button type="button" className="sb-primary" onClick={()=>{setShowCreate(v=>!v);setManualError("");setManualNotice("");}}>{showCreate?"Close manual order":"＋ Create manual order"}</button>
      <input aria-label="Search orders" placeholder="Search order, customer or PIN" value={search} onChange={e=>setSearch(e.target.value)}/>
      <select aria-label="Filter order status" value={status} onChange={e=>setStatus(e.target.value)}><option value="">All statuses</option>{statuses.map(s=><option key={s} value={s}>{label(s)}</option>)}</select>
      <select aria-label="Filter order channel" value={channel} onChange={e=>setChannel(e.target.value)}><option value="">All channels</option><option value="website">Website</option><option value="pos">POS</option><option value="manual">Manual</option></select>
      <button type="button" onClick={load} disabled={loading}>{loading?"Loading…":"Refresh"}</button>
    </div>
    {error && <p className="sb-alert" role="alert">{error}</p>}
    {manualNotice && <p className="sb-success" role="status">{manualNotice}</p>}
    {showCreate && <section className="sb-data-card sb-manual-order">
      <h2>Create manual order</h2>
      <p>Enter the delivery PIN first. The order is created only if an active location serving that PIN can fulfil every item.</p>
      {manualError && <p className="sb-alert" role="alert">{manualError}</p>}
      <form className="sb-form" onSubmit={pinChecked?createManualOrder:checkManualPin}>
        <label>Customer delivery PIN<input required inputMode="numeric" pattern="[0-9]{6}" maxLength="6" value={manualPin} disabled={pinChecked} onChange={e=>setManualPin(e.target.value.replace(/\D/g,""))} placeholder="6-digit PIN code"/></label>
        {!pinChecked && <button className="sb-primary" type="submit" disabled={pinBusy || manualPin.length!==6}>{pinBusy?"Checking PIN…":"Check PIN & continue"}</button>}
        {pinMessage && <p className="sb-muted" role="status">{pinMessage}</p>}
        {pinChecked && <>
          <label>Customer name<input required minLength="1" maxLength="200" value={manualCustomer.name} onChange={e=>setManualCustomer(v=>({...v,name:e.target.value}))}/></label>
          <label>Phone (optional)<input maxLength="20" value={manualCustomer.phone} onChange={e=>setManualCustomer(v=>({...v,phone:e.target.value}))}/></label>
          <label>Order notes (optional)<textarea maxLength="2000" value={manualCustomer.notes} onChange={e=>setManualCustomer(v=>({...v,notes:e.target.value}))}/></label>
          <h3>Add products</h3>
          <div className="sb-orders-toolbar"><select aria-label="Select product variant" defaultValue="" onChange={e=>{const v=manualVariants.find(item=>String(item.id)===e.target.value);if(v)addManualVariant(v);e.target.value="";}}><option value="">Choose a product / variant</option>{manualVariants.map(v=><option key={v.id} value={v.id}>{v.product_name||v.name||v.sku} · {v.sku} · {money(v.selling_price)}</option>)}</select></div>
          {manualCart.map(line=><div className="sb-order-actions" key={line.id}><span>{line.product_name||line.name||line.sku} · {line.sku}</span><label>Qty<input type="number" min="0" max="100000" value={line.quantity} onChange={e=>updateManualQuantity(line.id,e.target.value)}/></label><strong>{money(Number(line.selling_price||0)*line.quantity)}</strong></div>)}
          <p><strong>Order total: {money(manualTotal)}</strong></p>
          <p className="sb-muted">The backend checks current unreserved stock across all items and chooses the eligible location with the highest available stock. No stock is reserved by this step.</p>
          <button className="sb-primary" type="submit" disabled={manualSaving || !manualCustomer.name.trim() || !manualCart.length}>{manualSaving?"Creating order…":"Create manual order"}</button>
          <button type="button" onClick={()=>{setPinChecked(false);setPinMessage("");setManualCart([]);}}>Change PIN</button>
        </>}
      </form>
    </section>}
    {notice && <p className="sb-success" role="status">{notice}</p>}
    <div className="sb-orders-count">{total} matching orders</div>
    {loading ? <p className="sb-empty">Loading orders…</p> : orders.length ? <div className="sb-orders-list">{orders.map(order=><article className={`sb-order-card ${selected===order.id?"is-selected":""}`} key={order.id}>
      <button className="sb-order-open" type="button" onClick={()=>openOrder(order)}>
        <span><strong>{order.order_number}</strong><small>{order.customer_name} · {label(order.channel)} · {new Date(order.created_at).toLocaleString("en-IN")}</small></span>
        <span className="sb-order-total">{money(order.total)}<small>{order.line_count} line(s)</small></span>
        <span className={`sb-order-status status-${order.status}`}>{label(order.status)}</span>
      </button>
      <div className="sb-order-actions"><label>Update status<select aria-label={"Update status for "+order.order_number} value="" disabled={busy===order.id || !(nextStatuses[order.status]||[]).length} onChange={e=>{if(e.target.value)updateStatus(order,e.target.value)}}><option value="">{(nextStatuses[order.status]||[]).length?"Choose next status":"No further changes"}</option>{(nextStatuses[order.status]||[]).map(s=><option key={s} value={s}>{label(s)}</option>)}</select></label></div>
      {selected===order.id && <div className="sb-order-detail">{detailLoading ? <p>Loading order details…</p> : detail ? <>
        <h3>Order details</h3><p>{detail.customer_name}{detail.customer_phone?" · "+detail.customer_phone:""}{detail.delivery_pin?" · PIN "+detail.delivery_pin:""}</p>
        <ul>{(detail.lines||[]).map(line=><li key={line.id}><span>{line.product_name} <small>({line.sku}) × {line.quantity}</small></span><strong>{money(line.line_total)}</strong></li>)}</ul>
        {detail.notes && <p>Notes: {detail.notes}</p>}
      </> : null}
      <div className="sb-order-history"><button type="button" onClick={()=>toggleHistory(order)} disabled={historyLoading}>{historyLoading?"Loading history…":history?.order_id===order.id?"Hide status history":"View status history"}</button>
      {history?.order_id===order.id&&<div className="sb-order-history-list">{history.items?.length?history.items.map(entry=><div key={entry.id}><strong>{label(entry.from_status||"created")} → {label(entry.to_status)}</strong><small>{entry.changed_at?new Date(entry.changed_at).toLocaleString("en-IN"):""}</small></div>):<p className="sb-muted">No status changes recorded yet.</p>}</div>}
      </div>
    </div>}
    </article>)}</div> : <p className="sb-empty">{error ? "Orders could not be loaded." : "No orders found for these filters."}</p>}
  </section>;
}
