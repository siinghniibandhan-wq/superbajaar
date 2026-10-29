import { useCallback,useEffect,useState } from "react";
import { apiRequest } from "../../services/api.js";
const statuses=["pending","packed","assigned","dispatched","in_transit","delivered","failed","returned","cancelled"];
const next={pending:["packed","cancelled"],packed:["assigned","cancelled"],assigned:["dispatched","cancelled"],dispatched:["in_transit","delivered","failed"],in_transit:["delivered","failed","returned"],failed:["assigned","returned"],delivered:[],returned:[],cancelled:[]};
const label=s=>String(s||"").replaceAll("_"," ").replace(/\b\w/g,c=>c.toUpperCase());
export default function DeliveryWorkspace({onBack}){
 const [items,setItems]=useState([]),[orders,setOrders]=useState([]),[locations,setLocations]=useState([]);
 const [status,setStatus]=useState(""),[search,setSearch]=useState(""),[loading,setLoading]=useState(false),[saving,setSaving]=useState(false),[busy,setBusy]=useState(null),[error,setError]=useState(""),[notice,setNotice]=useState("");
 const [form,setForm]=useState({order_id:"",delivery_pin:"",recipient_name:"",recipient_phone:"",address:"",location_id:"",delivery_notes:""});
 const [edits,setEdits]=useState({}),[histories,setHistories]=useState({}),[historyBusy,setHistoryBusy]=useState(null);
 const load=useCallback(async()=>{setLoading(true);setError("");try{
  const q=new URLSearchParams({limit:"200"});if(status)q.set("status",status);if(search.trim())q.set("search",search.trim());
  const [d,o,l]=await Promise.all([apiRequest("/delivery/shipments?"+q),apiRequest("/orders?limit=200"),apiRequest("/inventory/locations?limit=500")]);
  setItems(d.items||[]);setOrders((o.items||[]).filter(x=>!["cancelled","delivered"].includes(x.status)));setLocations(l.items||[]);
 }catch(e){setError(e.message||"Unable to load delivery records.");}finally{setLoading(false);}},[status,search]);
 useEffect(()=>{load();},[load]);
 function setField(k,v){setForm(old=>({...old,[k]:v}));}
 async function create(e){e.preventDefault();setSaving(true);setError("");setNotice("");try{
  await apiRequest("/delivery/shipments",{method:"POST",body:JSON.stringify({...form,order_id:Number(form.order_id),location_id:form.location_id?Number(form.location_id):null,delivery_notes:form.delivery_notes||null})});
  setForm({order_id:"",delivery_pin:"",recipient_name:"",recipient_phone:"",address:"",location_id:"",delivery_notes:""});setNotice("Shipment created.");await load();
 }catch(e){setError(e.message||"Unable to create shipment.");}finally{setSaving(false);}}
 async function toggleHistory(item){
  if(histories[item.id]){setHistories(old=>({...old,[item.id]:null}));return;}
  setHistoryBusy(item.id);setError("");
  try{
   const result=await apiRequest("/delivery/shipments/"+item.id+"/history?limit=100");
   setHistories(old=>({...old,[item.id]:result.items||[]}));
  }catch(e){setError(e.message||"Unable to load shipment history.");}
  finally{setHistoryBusy(null);}
 }
 async function update(item,nextStatus){setBusy(item.id);setError("");setNotice("");try{
  const edit=edits[item.id]||{};await apiRequest("/delivery/shipments/"+item.id+"/status",{method:"PATCH",body:JSON.stringify({status:nextStatus,tracking_reference:edit.tracking_reference||null,assigned_to:edit.assigned_to||null,note:edit.note||null})});
  setNotice(item.shipment_reference+" updated to "+label(nextStatus)+".");await load();
 }catch(e){setError(e.message||"Unable to update shipment.");}finally{setBusy(null);}}
 return <section className="sb-workspace sb-delivery"><button className="sb-back" type="button" onClick={onBack}>← All workspaces</button>
  <p className="sb-eyebrow">OPERATIONS · DELIVERY</p><h1>Delivery</h1><p>Create shipments, assign delivery responsibility, record tracking/status updates and review each shipment's status history. Carrier integrations are not enabled.</p>
  {error&&<p className="sb-alert" role="alert">{error}</p>}{notice&&<p className="sb-success" role="status">{notice}</p>}
  <form className="sb-delivery-form" onSubmit={create}><h2>Create shipment</h2><div className="sb-delivery-fields">
   <label>Order<select required value={form.order_id} onChange={e=>{const order=orders.find(o=>String(o.id)===e.target.value);setField("order_id",e.target.value);if(order?.delivery_pin)setField("delivery_pin",order.delivery_pin);if(order?.customer_name)setField("recipient_name",order.customer_name);if(order?.customer_phone)setField("recipient_phone",order.customer_phone);}}><option value="">Choose order</option>{orders.map(o=><option key={o.id} value={o.id}>{o.order_number} · {o.customer_name}</option>)}</select></label>
   <label>Delivery PIN<input required pattern="[0-9]{6}" maxLength="6" value={form.delivery_pin} onChange={e=>setField("delivery_pin",e.target.value)}/></label>
   <label>Recipient name<input required maxLength="200" value={form.recipient_name} onChange={e=>setField("recipient_name",e.target.value)}/></label>
   <label>Phone<input required minLength="7" maxLength="20" value={form.recipient_phone} onChange={e=>setField("recipient_phone",e.target.value)}/></label>
   <label className="sb-span-all">Delivery address<textarea required minLength="5" maxLength="1000" rows="2" value={form.address} onChange={e=>setField("address",e.target.value)}/></label>
   <label>Stock location (optional)<select value={form.location_id} onChange={e=>setField("location_id",e.target.value)}><option value="">Not assigned</option>{locations.map(l=><option key={l.id} value={l.id}>{l.name}</option>)}</select></label>
   <label>Delivery notes<input maxLength="1000" value={form.delivery_notes} onChange={e=>setField("delivery_notes",e.target.value)}/></label>
  </div><button className="sb-primary" type="submit" disabled={saving||!orders.length}>{saving?"Saving…":"Create shipment"}</button>{!orders.length&&<small>No eligible orders. Create an order first.</small>}</form>
  <div className="sb-delivery-toolbar"><input placeholder="Search shipment, order, recipient or PIN" aria-label="Search shipments" value={search} onChange={e=>setSearch(e.target.value)}/><select aria-label="Filter shipment status" value={status} onChange={e=>setStatus(e.target.value)}><option value="">All statuses</option>{statuses.map(s=><option key={s} value={s}>{label(s)}</option>)}</select><button type="button" onClick={load} disabled={loading}>{loading?"Loading…":"Refresh"}</button></div>
  {loading?<p className="sb-empty">Loading shipments…</p>:items.length?<div className="sb-orders-list">{items.map(item=><article className="sb-order-card" key={item.id}><div className="sb-delivery-row"><div><strong>{item.shipment_reference}</strong><small>{item.order_number} · {item.recipient_name} · PIN {item.delivery_pin}</small><small>{item.address}</small></div><span className={"sb-order-status status-"+item.status}>{label(item.status)}</span></div>
   <div className="sb-delivery-edit"><label>Assigned to<input value={edits[item.id]?.assigned_to??item.assigned_to??""} onChange={e=>setEdits(old=>({...old,[item.id]:{...old[item.id],assigned_to:e.target.value}}))} placeholder="Driver / courier name"/></label><label>Tracking reference<input value={edits[item.id]?.tracking_reference??item.tracking_reference??""} onChange={e=>setEdits(old=>({...old,[item.id]:{...old[item.id],tracking_reference:e.target.value}}))} placeholder="Tracking ID"/></label><label>Update status<select value="" disabled={busy===item.id||!(next[item.status]||[]).length} onChange={e=>e.target.value&&update(item,e.target.value)}><option value="">{(next[item.status]||[]).length?"Choose next status":"No further changes"}</option>{(next[item.status]||[]).map(s=><option key={s} value={s}>{label(s)}</option>)}</select></label></div>
   <div className="sb-delivery-history"><button type="button" onClick={()=>toggleHistory(item)} disabled={historyBusy===item.id}>{historyBusy===item.id?"Loading history…":histories[item.id]?"Hide status history":"View status history"}</button>
   {histories[item.id]&&<div className="sb-delivery-history-list">{histories[item.id].length?histories[item.id].map(entry=><div className="sb-delivery-history-entry" key={entry.id}><strong>{entry.from_status?label(entry.from_status)+" → ": ""}{label(entry.to_status)}</strong><small>{entry.changed_at?new Date(entry.changed_at).toLocaleString():""}</small>{entry.note&&<p>{entry.note}</p>}</div>):<p className="sb-muted">No status changes have been recorded yet.</p>}</div>}
   </div>
  </article>)}</div>:<p className="sb-empty">No shipments found.</p>}
 </section>;
}
