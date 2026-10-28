import { useCallback, useEffect, useMemo, useState } from "react";
import { apiRequest } from "../../services/api.js";

export default function LoyaltyWorkspace({ onBack }) {
  const [customers,setCustomers]=useState([]),[orders,setOrders]=useState([]);
  const [search,setSearch]=useState(""),[loading,setLoading]=useState(true),[error,setError]=useState("");
  const load=useCallback(async()=>{setLoading(true);setError("");try{const results=await Promise.all([apiRequest("/customers?limit=500"),apiRequest("/orders?limit=500")]);setCustomers(results[0].items||[]);setOrders(results[1].items||[]);}catch(e){setError(e.message||"Unable to load loyalty data.");}finally{setLoading(false);}},[]);
  useEffect(()=>{load();},[load]);
  const spend=useMemo(()=>{const m={};orders.forEach(o=>{if(!["cancelled"].includes(o.status)){const k=o.customer_phone||o.customer_name||"";m[k]=(m[k]||0)+Number(o.total||o.subtotal||0);}});return m;},[orders]);
  const rows=customers.filter(c=>(c.name+" "+(c.phone||"")+" "+(c.email||"")).toLowerCase().includes(search.toLowerCase()));
  const totalSpend=Object.values(spend).reduce((a,b)=>a+b,0);
  return <section className="sb-workspace"><button className="sb-back" onClick={onBack} type="button">← All workspaces</button><p className="sb-eyebrow">CUSTOMERS · RETENTION</p><h1>Loyalty & Rewards</h1><p>Customer activity and spend are derived from existing customer and order records. No points or rewards are issued or stored by this screen.</p>
  <div className="sb-report-kpis"><article><small>Customers</small><strong>{customers.length}</strong></article><article><small>Orders reviewed</small><strong>{orders.length}</strong></article><article><small>Order value reviewed</small><strong>₹{totalSpend.toLocaleString("en-IN",{maximumFractionDigits:2})}</strong></article></div>
  {error&&<p className="sb-alert" role="alert">{error}</p>}<div className="sb-data-heading"><h2>Customer activity</h2><div><input aria-label="Search customers" placeholder="Search name, phone or email" value={search} onChange={e=>setSearch(e.target.value)}/><button onClick={load} type="button" disabled={loading}>Refresh</button></div></div>
  {loading?<p className="sb-empty">Loading customer activity…</p>:<div className="sb-table-wrap"><table><thead><tr><th>Customer</th><th>Phone</th><th>Email</th><th>Order value</th></tr></thead><tbody>{rows.map(c=><tr key={c.id}><td>{c.name}</td><td>{c.phone||"—"}</td><td>{c.email||"—"}</td><td>₹{Number(spend[c.phone||c.name]||0).toLocaleString("en-IN",{maximumFractionDigits:2})}</td></tr>)}</tbody></table>{!rows.length&&<p className="sb-empty">No matching customers.</p>}</div>}
  <div className="sb-notice"><strong>Reward issuance is not enabled</strong><span>The current database/API has no loyalty ledger, points balance, redemption, or expiry endpoints. This workspace does not invent balances or alter customer records.</span></div></section>;
}
