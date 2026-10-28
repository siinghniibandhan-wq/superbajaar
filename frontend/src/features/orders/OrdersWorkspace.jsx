import { useCallback, useEffect, useState } from "react";
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
      <input aria-label="Search orders" placeholder="Search order, customer or PIN" value={search} onChange={e=>setSearch(e.target.value)}/>
      <select aria-label="Filter order status" value={status} onChange={e=>setStatus(e.target.value)}><option value="">All statuses</option>{statuses.map(s=><option key={s} value={s}>{label(s)}</option>)}</select>
      <select aria-label="Filter order channel" value={channel} onChange={e=>setChannel(e.target.value)}><option value="">All channels</option><option value="website">Website</option><option value="pos">POS</option><option value="manual">Manual</option></select>
      <button type="button" onClick={load} disabled={loading}>{loading?"Loading…":"Refresh"}</button>
    </div>
    {error && <p className="sb-alert" role="alert">{error}</p>}
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
