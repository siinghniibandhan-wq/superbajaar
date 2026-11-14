import { useCallback, useEffect, useState } from "react";
import { apiRequest } from "../../services/api.js";

const money = value => new Intl.NumberFormat("en-IN",{style:"currency",currency:"INR"}).format(Number(value||0));
const empty = { supplier_id:"", location_id:"", title:"", start_date:new Date().toISOString().slice(0,10), end_date:"", currency:"INR", max_contract_value:"", lines:[{variant_id:"",agreed_quantity:"",agreed_unit_cost:""}] };

export default function BlanketOrdersWorkspace({ suppliers=[], locations=[], variants=[], onPurchaseOrderCreated }) {
  const [items,setItems]=useState([]);
  const [selected,setSelected]=useState(null);
  const [form,setForm]=useState(empty);
  const [releaseQty,setReleaseQty]=useState({});
  const [busy,setBusy]=useState(false);
  const [error,setError]=useState("");
  const [notice,setNotice]=useState("");
  const load=useCallback(async()=>{try{const result=await apiRequest("/purchasing/blanket-orders?limit=200");setItems(result.items||[]);}catch(e){setError(e.message||"Unable to load blanket orders.");}},[]);
  useEffect(()=>{load();},[load]);
  async function create(e){
    e.preventDefault();setBusy(true);setError("");setNotice("");
    try{
      const payload={...form,supplier_id:Number(form.supplier_id),location_id:Number(form.location_id),max_contract_value:form.max_contract_value?Number(form.max_contract_value):null,
        lines:form.lines.map(line=>({variant_id:Number(line.variant_id),agreed_quantity:line.agreed_quantity?Number(line.agreed_quantity):null,agreed_unit_cost:Number(line.agreed_unit_cost)}))};
      if(!payload.supplier_id||!payload.location_id||payload.lines.some(x=>!x.variant_id||!Number.isFinite(x.agreed_unit_cost)||x.agreed_unit_cost<0))throw new Error("Complete supplier, location and each item’s agreed rate.");
      const result=await apiRequest("/purchasing/blanket-orders",{method:"POST",body:JSON.stringify(payload)});
      setForm(empty);setNotice("Blanket agreement "+result.blanket_number+" created as draft. Submit it for approval.");await load();
    }catch(e){setError(e.message||"Unable to create blanket agreement.");}finally{setBusy(false);}
  }
  async function open(id){setError("");try{const result=await apiRequest("/purchasing/blanket-orders/"+id);setSelected(result);const next={};for(const line of result.lines||[])next[line.blanket_line_id]="";setReleaseQty(next);}catch(e){setError(e.message||"Unable to load agreement.");}}
  async function action(path,message){setBusy(true);setError("");setNotice("");try{await apiRequest(path,{method:"POST",body:"{}"});setNotice(message);await load();if(selected)await open(selected.id);}catch(e){setError(e.message||"Action failed.");}finally{setBusy(false);}}
  async function release(e){
    e.preventDefault();if(!selected)return;
    const lines=selected.lines.filter(line=>Number(releaseQty[line.blanket_line_id])>0).map(line=>({blanket_line_id:line.blanket_line_id,quantity:Number(releaseQty[line.blanket_line_id])}));
    if(!lines.length){setError("Enter a release quantity for at least one agreement line.");return;}
    setBusy(true);setError("");setNotice("");
    try{const result=await apiRequest("/purchasing/blanket-orders/"+selected.id+"/releases",{method:"POST",body:JSON.stringify({lines})});setNotice(result.message);await load();await open(selected.id);if(onPurchaseOrderCreated)await onPurchaseOrderCreated(result.purchase_order);}
    catch(e){setError(e.message||"Unable to create release purchase order.");}finally{setBusy(false);}
  }
  function updateLine(index,key,value){setForm(old=>({...old,lines:old.lines.map((line,i)=>i===index?{...line,[key]:value}:line)}));}
  return <section className="sb-blanket-workspace">
    <div className="sb-purchasing-overview-head"><div><h2>Blanket purchase agreements</h2><p>Agree supplier pricing and quantities for a validity period, then release individual purchase orders as needed.</p></div></div>
    {error&&<p className="sb-alert" role="alert">{error}</p>}{notice&&<p className="sb-success" role="status">{notice}</p>}
    <form className="sb-customer-form" onSubmit={create}>
      <h3>Create blanket agreement</h3><div className="sb-customer-fields">
        <label>Supplier *<select required value={form.supplier_id} onChange={e=>setForm(o=>({...o,supplier_id:e.target.value}))}><option value="">Choose supplier</option>{suppliers.map(x=><option key={x.id} value={x.id}>{x.name}</option>)}</select></label>
        <label>Receiving location *<select required value={form.location_id} onChange={e=>setForm(o=>({...o,location_id:e.target.value}))}><option value="">Choose location</option>{locations.map(x=><option key={x.id} value={x.id}>{x.name}</option>)}</select></label>
        <label className="sb-span-all">Agreement title *<input required minLength="3" maxLength="200" value={form.title} onChange={e=>setForm(o=>({...o,title:e.target.value}))} placeholder="e.g. Annual packaging supply agreement"/></label>
        <label>Valid from *<input required type="date" value={form.start_date} onChange={e=>setForm(o=>({...o,start_date:e.target.value}))}/></label>
        <label>Valid until *<input required type="date" min={form.start_date} value={form.end_date} onChange={e=>setForm(o=>({...o,end_date:e.target.value}))}/></label>
        <label>Currency<input value={form.currency} maxLength="3" onChange={e=>setForm(o=>({...o,currency:e.target.value.toUpperCase()}))}/></label>
        <label>Maximum contract value (optional)<input type="number" min="0.01" step="0.01" value={form.max_contract_value} onChange={e=>setForm(o=>({...o,max_contract_value:e.target.value}))}/></label>
      </div>
      <div className="sb-purchase-lines"><div className="sb-purchase-lines-head"><strong>Agreed items and rates</strong><button type="button" onClick={()=>setForm(o=>({...o,lines:[...o.lines,{variant_id:"",agreed_quantity:"",agreed_unit_cost:""}]}))}>+ Add item</button></div>
        {form.lines.map((line,i)=><div className="sb-purchase-line" key={i}>
          <label>Product variant *<select required value={line.variant_id} onChange={e=>updateLine(i,"variant_id",e.target.value)}><option value="">Choose variant</option>{variants.map(v=><option key={v.id} value={v.id}>{v.product_name||v.name||("Product "+v.product_id)} · {v.sku||("Variant "+v.id)}</option>)}</select></label>
          <label>Agreed quantity limit<input type="number" min="0.001" step="0.001" placeholder="Unlimited" value={line.agreed_quantity} onChange={e=>updateLine(i,"agreed_quantity",e.target.value)}/></label>
          <label>Agreed unit rate ₹ *<input required type="number" min="0" step="0.01" value={line.agreed_unit_cost} onChange={e=>updateLine(i,"agreed_unit_cost",e.target.value)}/></label>
          {form.lines.length>1&&<button type="button" className="sb-remove-line" onClick={()=>setForm(o=>({...o,lines:o.lines.filter((_,n)=>n!==i)}))} aria-label={"Remove item "+(i+1)}>×</button>}
        </div>)}
      </div><button className="sb-primary" type="submit" disabled={busy||!suppliers.length||!locations.length}>{busy?"Saving…":"Create draft blanket agreement"}</button>
    </form>
    <h3>Existing agreements</h3>
    {items.length?<div className="sb-customer-list">{items.map(item=><article className="sb-order-card" key={item.id}>
      <button type="button" className="sb-order-open" onClick={()=>open(item.id)}><span><strong>{item.blanket_number} · {item.title}</strong><small>{item.supplier_name} · {item.location_name} · {item.start_date} to {item.end_date}</small></span><span className={"sb-order-status status-"+item.status}>{item.status.replaceAll("_"," ")}</span><span>{item.release_count} releases</span></button>
    </article>)}</div>:<p className="sb-empty">No blanket agreements created yet.</p>}
    {selected&&<section className="sb-purchase-detail"><h3>{selected.blanket_number} · {selected.title}</h3><p>{selected.supplier_name} · {selected.location_name} · {selected.start_date} to {selected.end_date}</p><p>Status: <strong>{selected.status}</strong>{selected.max_contract_value? " · Contract cap "+money(selected.max_contract_value):""}</p>
      <div className="sb-purchase-detail-lines">{selected.lines.map(line=><div className="sb-purchase-detail-line" key={line.blanket_line_id}><div><strong>{line.product_name} · {line.sku}</strong><small>Agreed rate {money(line.agreed_unit_cost)} · {line.released_quantity} released / {line.agreed_quantity??"unlimited"} agreed</small></div>{selected.status==="active"&&<label>Release quantity<input type="number" min="0" max={line.agreed_quantity==null?undefined:Math.max(0,Number(line.agreed_quantity)-Number(line.released_quantity))} step="0.001" value={releaseQty[line.blanket_line_id]||""} onChange={e=>setReleaseQty(o=>({...o,[line.blanket_line_id]:e.target.value}))}/></label>}</div>)}</div>
      {selected.status==="draft"&&<button className="sb-primary" type="button" disabled={busy} onClick={()=>action("/purchasing/blanket-orders/"+selected.id+"/submit","Agreement submitted for configured Purchase approval.")}>Submit for approval</button>}
      {selected.status==="submitted"&&<button className="sb-primary" type="button" disabled={busy} onClick={()=>action("/purchasing/blanket-orders/"+selected.id+"/approve","Approval stage recorded. Refresh to see whether the agreement is active or needs another approver.")}>Record approval stage</button>}
      {selected.status==="active"&&<form onSubmit={release}><button className="sb-primary" type="submit" disabled={busy}>Create release purchase order</button><p className="sb-muted">Each release creates a normal draft PO at the agreed rates. Existing PO approval, GRN, QC, inventory and invoice controls remain mandatory.</p></form>}
      <h4>Release history</h4>{selected.releases.length?<ul>{selected.releases.map(r=><li key={r.id}>{r.release_number} · {r.purchase_number} · {r.status} · {money(r.subtotal)}</li>)}</ul>:<p className="sb-empty">No releases yet.</p>}
    </section>}
  </section>;
}
