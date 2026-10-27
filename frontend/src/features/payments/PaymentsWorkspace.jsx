import { useCallback, useEffect, useState } from "react";
import { apiRequest } from "../../services/api.js";
const statuses=["pending","authorized","captured","failed","cancelled","refunded"];
const methods=["upi","card","netbanking","cod","wallet","bank_transfer","other"];
const next={pending:["authorized","captured","failed","cancelled"],authorized:["captured","failed","cancelled"],captured:["refunded"],failed:[],cancelled:[],refunded:[]};
const label=s=>String(s||"").replaceAll("_"," ").replace(/\b\w/g,c=>c.toUpperCase());
const money=v=>new Intl.NumberFormat("en-IN",{style:"currency",currency:"INR"}).format(Number(v||0));
export default function PaymentsWorkspace({onBack}){
 const [items,setItems]=useState([]),[total,setTotal]=useState(0),[orders,setOrders]=useState([]);
 const [status,setStatus]=useState(""),[method,setMethod]=useState(""),[search,setSearch]=useState("");
 const [orderId,setOrderId]=useState(""),[payMethod,setPayMethod]=useState("upi"),[amount,setAmount]=useState(""),[providerRef,setProviderRef]=useState("");
 const [loading,setLoading]=useState(false),[saving,setSaving]=useState(false),[busy,setBusy]=useState(null),[error,setError]=useState(""),[notice,setNotice]=useState("");
 const load=useCallback(async()=>{
  setLoading(true);setError("");
  try{const q=new URLSearchParams({limit:"200"});if(status)q.set("status",status);if(method)q.set("method",method);if(search.trim())q.set("search",search.trim());
   const [p,o]=await Promise.all([apiRequest("/payments?"+q.toString()),apiRequest("/orders?limit=200")]);
   setItems(p.items||[]);setTotal(p.total||0);setOrders((o.items||[]).filter(x=>x.status!=="cancelled"));
  }catch(e){setError(e.message||"Unable to load payment records.");}finally{setLoading(false);}
 },[status,method,search]);
 useEffect(()=>{load();},[load]);
 async function create(e){e.preventDefault();setSaving(true);setError("");setNotice("");
  if(!orderId||!amount.trim()||!Number.isFinite(Number(amount))||Number(amount)<=0){setError("Choose an order and enter a positive payment amount.");setSaving(false);return;}
  try{await apiRequest("/payments",{method:"POST",body:JSON.stringify({order_id:Number(orderId),method:payMethod,amount:Number(amount),status:"pending",provider_reference:providerRef.trim()||null})});
   setOrderId("");setAmount("");setProviderRef("");setNotice("Payment record created as pending. No gateway charge was initiated.");await load();
  }catch(e){setError(e.message||"Unable to create payment record.");}finally{setSaving(false);}
 }
 async function update(item,value){setBusy(item.id);setError("");setNotice("");
  try{await apiRequest("/payments/"+item.id+"/status",{method:"PATCH",body:JSON.stringify({status:value})});setNotice(item.payment_reference+" updated to "+label(value)+".");await load();}
  catch(e){setError(e.message||"Unable to update payment.");}finally{setBusy(null);}
 }
 return <section className="sb-workspace sb-payments">
  <button className="sb-back" type="button" onClick={onBack}>← All workspaces</button>
  <p className="sb-eyebrow">COMMERCE · PAYMENTS</p><h1>Payments & Refunds</h1>
  <p>Record and reconcile payment states against orders. This workspace does not charge cards or connect to Razorpay or another gateway.</p>
  {error&&<p className="sb-alert" role="alert">{error}</p>}{notice&&<p className="sb-success" role="status">{notice}</p>}
  <form className="sb-payment-form" onSubmit={create}><h2>Record payment</h2>
   <div className="sb-payment-fields">
    <label>Order<select required value={orderId} onChange={e=>{setOrderId(e.target.value);const o=orders.find(x=>String(x.id)===e.target.value);if(o)setAmount(String(o.total));}}><option value="">Choose order</option>{orders.map(o=><option key={o.id} value={o.id}>{o.order_number} · {o.customer_name} · {money(o.total)}</option>)}</select></label>
    <label>Method<select value={payMethod} onChange={e=>setPayMethod(e.target.value)}>{methods.map(m=><option key={m} value={m}>{label(m)}</option>)}</select></label>
    <label>Amount ₹<input type="number" min="0.01" step="0.01" required value={amount} onChange={e=>setAmount(e.target.value)}/></label>
    <label>Provider reference (optional)<input maxLength="200" value={providerRef} onChange={e=>setProviderRef(e.target.value)} placeholder="Transaction / gateway reference"/></label>
   </div>
   <button className="sb-primary" type="submit" disabled={saving}>{saving?"Saving…":"Create pending record"}</button>
  </form>
  <div className="sb-payment-toolbar"><input aria-label="Search payments" placeholder="Search payment, order or provider reference" value={search} onChange={e=>setSearch(e.target.value)}/><select aria-label="Filter payment status" value={status} onChange={e=>setStatus(e.target.value)}><option value="">All statuses</option>{statuses.map(s=><option key={s} value={s}>{label(s)}</option>)}</select><select aria-label="Filter payment method" value={method} onChange={e=>setMethod(e.target.value)}><option value="">All methods</option>{methods.map(m=><option key={m} value={m}>{label(m)}</option>)}</select><button type="button" onClick={load} disabled={loading}>{loading?"Loading…":"Refresh"}</button></div>
  <p className="sb-orders-count">{total} payment records</p>
  {loading?<p className="sb-empty">Loading payments…</p>:items.length?<div className="sb-orders-list">{items.map(item=><article className="sb-order-card" key={item.id}><div className="sb-payment-row"><div><strong>{item.payment_reference}</strong><small>{item.order_number} · {label(item.method)}{item.provider_reference?" · Ref "+item.provider_reference:""}</small></div><strong>{money(item.amount)}</strong><span className={"sb-order-status status-"+item.status}>{label(item.status)}</span></div><div className="sb-order-actions"><label>Update state<select value="" disabled={busy===item.id||!(next[item.status]||[]).length} onChange={e=>e.target.value&&update(item,e.target.value)}><option value="">{(next[item.status]||[]).length?"Choose next state":"No further changes"}</option>{(next[item.status]||[]).map(s=><option key={s} value={s}>{label(s)}</option>)}</select></label></div></article>)}</div>:<p className="sb-empty">{error?"Payment records could not be loaded.":"No payment records found."}</p>}
 </section>;
}
