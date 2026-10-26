import React, { useEffect, useMemo, useState } from 'react';
import { createRoot } from 'react-dom/client';
import './styles.css';

const API = (import.meta.env.VITE_API_BASE_URL || 'https://superappkart.duckdns.org/api').replace(/\/$/, '');
const API_PATH = path => API.endsWith('/api') ? API + path : API + '/api' + path;
async function fetchWithTimeout(url, options = {}, timeoutMs = 15000) {
 const controller = new AbortController();
 const timeout = setTimeout(() => controller.abort(), timeoutMs);
 try { return await fetch(url, {...options, signal: controller.signal}); }
 catch (error) {
  if (error?.name === 'AbortError') throw Error('Request timed out. Check the product list before trying again to avoid creating a duplicate.');
  throw error;
 } finally { clearTimeout(timeout); }
}
const NAV = [
 {id:'overview',label:'Overview',icon:'◫',group:'WORKSPACE'},
 {id:'orders',label:'Sales & POS',icon:'▤',group:'BUSINESS'},
 {id:'products',label:'Inventory',icon:'▦',group:'BUSINESS'},
 {id:'purchases',label:'Purchase',icon:'⇄',group:'BUSINESS'},
 {id:'logistics',label:'Logistics',icon:'⌁',group:'BUSINESS'},
 {id:'accounting',label:'Accounting',icon:'₹',group:'BUSINESS'},
 {id:'employees',label:'HR & Payroll',icon:'♙',group:'PEOPLE'},
 {id:'settings',label:'Store customisation',icon:'⚙',group:'SYSTEM'}
];
const MODULE_TABS = {
 orders:[['overview','Overview'],['sale','Sale'],['pos-desk','POS'],['customers','Customers'],['invoices','Invoices'],['returns','Returns & Refunds']],
 products:[['overview','Overview'],['catalogue','Products'],['attributes','Attributes'],['stock','Stock Levels'],['warehouses','Warehouses & Locations'],['grn','Goods Receipt (GRN)'],['transfers','Internal Transfers'],['categories','Categories']],
 purchases:[['overview','Overview'],['workspace','Purchase Orders'],['vendors','Vendors'],['supplier-payments','Supplier Payments']],
 logistics:[['overview','Overview'],['workspace','Shipments'],['routes','Routes & Drivers'],['tracking','Delivery Tracking']],
 accounting:[['overview','Overview'],['accounts','Chart of Accounts'],['bills','Bills & Receivables'],['journals','Journal Entries'],['reports','Financial Reports'],['gst','GST']],
 employees:[['overview','Overview'],['workspace','Employees'],['attendance','Attendance'],['leave','Leave'],['payroll','Payroll']],
 settings:[['overview','Overview'],['general','General'],['appearance','Website Appearance'],['catalogue','Catalogue'],['loyalty','Loyalty'],['access','Users & Access']]
};

function App() {
  const [view, setView] = useState('store');
  const [nav, setNav] = useState('overview');
  const [activeTab, setActiveTab] = useState('overview');

  return (
    <div className="app-container">
      {view === 'store' ? (
        <div style={{minHeight:'100vh',background:'#0d1117',color:'#f0f6fc',padding:'24px'}}>
          <header style={{display:'flex',justifyContent:'space-between',alignItems:'center',marginBottom:'32px',borderBottom:'1px solid #30363d',paddingBottom:'16px'}}>
            <h1 style={{margin:0,fontSize:'24px',fontWeight:700,color:'#58a6ff'}}>🛍️ Super Bajaar</h1>
            <button style={{padding:'8px 16px',background:'#238636',color:'#fff',border:'none',borderRadius:'6px',cursor:'pointer',fontWeight:600}} onClick={()=>setView('admin')}>Go to Admin Dashboard →</button>
          </header>
          <main>
            <h2>Welcome to Super Bajaar Storefront</h2>
            <p style={{color:'#8b949e'}}>Catalogue loading directly from existing database.</p>
          </main>
        </div>
      ) : (
        <div style={{display:'flex',minHeight:'100vh',background:'#0d1117',color:'#f0f6fc'}}>
          <aside style={{width:'240px',borderRight:'1px solid #30363d',padding:'20px 12px'}}>
            <div style={{display:'flex',alignItems:'center',gap:'8px',marginBottom:'24px',paddingLeft:'8px'}}>
              <span style={{fontSize:'20px'}}>🛍️</span>
              <strong style={{fontSize:'16px'}}>Super Bajaar</strong>
            </div>
            <nav style={{display:'flex',flexDirection:'column',gap:'4px'}}>
              {NAV.map(item=>(
                <button key={item.id} onClick={()=>{setNav(item.id);setActiveTab(MODULE_TABS[item.id]?.[0]?.[0]||'overview');}} style={{display:'flex',alignItems:'center',gap:'10px',padding:'10px 12px',background:nav===item.id?'#21262d':'transparent',color:nav===item.id?'#58a6ff':'#c9d1d9',border:'none',borderRadius:'6px',cursor:'pointer',textAlign:'left',width:'100%',fontWeight:nav===item.id?600:400}}>
                  <span>{item.icon}</span>
                  <span>{item.label}</span>
                </button>
              ))}
            </nav>
            <div style={{marginTop:'32px',borderTop:'1px solid #30363d',paddingTop:'16px'}}>
              <button style={{width:'100%',padding:'8px',background:'transparent',color:'#8b949e',border:'1px solid #30363d',borderRadius:'6px',cursor:'pointer'}} onClick={()=>setView('store')}>← Back to Store</button>
            </div>
          </aside>
          <main style={{flex:1,padding:'24px'}}>
            <header style={{marginBottom:'24px'}}>
              <h2 style={{margin:0,fontSize:'22px'}}>{NAV.find(n=>n.id===nav)?.label||'Dashboard'}</h2>
              <div style={{display:'flex',gap:'8px',marginTop:'16px',borderBottom:'1px solid #30363d',paddingBottom:'8px'}}>
                {(MODULE_TABS[nav]||[['overview','Overview']]).map(([tid,tlabel])=>(
                  <button key={tid} onClick={()=>setActiveTab(tid)} style={{padding:'6px 14px',background:activeTab===tid?'#30363d':'transparent',color:activeTab===tid?'#f0f6fc':'#8b949e',border:'none',borderRadius:'4px',cursor:'pointer',fontWeight:500}}>{tlabel}</button>
                ))}
              </div>
            </header>
            <section style={{background:'#161b22',border:'1px solid #30363d',borderRadius:'8px',padding:'24px'}}>
              <h3>Active View: {activeTab.toUpperCase()}</h3>
              <p style={{color:'#8b949e'}}>Module {nav} is active and ready.</p>
            </section>
          </main>
        </div>
      )}
    </div>
  );
}

const rootElement = document.getElementById('root');
if (rootElement) {
  createRoot(rootElement).render(<App />);
}
