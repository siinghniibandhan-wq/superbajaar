import React, { useEffect, useState } from 'react';
import { createRoot } from 'react-dom/client';
import './styles.css';

const API_BASE = (import.meta.env.VITE_API_BASE_URL || '').replace(/\/$/, '');
const endpoint = (path) => `${API_BASE}${path}`;

function App() {
  const [theme, setTheme] = useState('soft');
  const [query, setQuery] = useState('');
  const [pincode, setPincode] = useState('');
  const [products, setProducts] = useState([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');
  const [apiConfigured, setApiConfigured] = useState(Boolean(API_BASE));

  async function loadProducts(search = query, pin = pincode) {
    setLoading(true); setError(''); setNotice('');
    try {
      const params = new URLSearchParams();
      if (search.trim()) params.set('search', search.trim());
      if (pin.trim()) params.set('pincode', pin.trim());
      const response = await fetch(endpoint('/products?' + params.toString()));
      if (!response.ok) throw new Error('Catalogue API returned ' + response.status);
      const payload = await response.json();
      setProducts(Array.isArray(payload) ? payload : (payload.items || payload.products || []));
      setApiConfigured(true);
    } catch (e) {
      setProducts([]);
      setError(API_BASE ? 'Unable to load products. Check the backend API and try again.' : 'Backend API is not configured yet. Add VITE_API_BASE_URL when the backend is ready.');
    } finally { setLoading(false); }
  }

  useEffect(() => { if (API_BASE) loadProducts('', ''); }, []);

  async function checkServiceability(e) {
    e.preventDefault();
    if (!/^\d{6}$/.test(pincode)) { setNotice('Enter a valid 6-digit PIN code.'); return; }
    try {
      const response = await fetch(endpoint('/serviceability?pincode=' + encodeURIComponent(pincode)));
      if (!response.ok) throw new Error('Serviceability check failed');
      const data = await response.json();
      setNotice(data.serviceable ? 'Delivery service is available for this PIN code.' : 'Delivery availability will be confirmed by the backend.');
      await loadProducts(query, pincode);
    } catch { setNotice('PIN-code serviceability will be available after the backend is connected.'); }
  }

  return <div className="app" data-theme={theme}>
    <div className="announcement">Your Everyday Super Store <span>•</span> A better way to shop</div>
    <header className="header">
      <a className="brand" href="#"><span className="brand-mark">S</span><span>super<span className="brand-accent">bajaar</span><small>Your Everyday Super Store</small></span></a>
      <form className="search" onSubmit={e => {e.preventDefault(); loadProducts();}}><input aria-label="Search products" placeholder="Search products, brands and more" value={query} onChange={e=>setQuery(e.target.value)}/><button type="submit">Search</button></form>
      <div className="header-actions"><button className="ghost" onClick={()=>setNotice('Customer accounts will be enabled when authentication is implemented.')}>Account</button><button className="cart" onClick={()=>setNotice('Cart API will be connected in the next development phase.')}>Cart <span>0</span></button></div>
    </header>
    <main>
      <section className="hero"><div className="hero-copy"><p className="eyebrow">EVERYDAY ESSENTIALS, MADE SIMPLE</p><h1>Good finds.<br/><span>Better everyday.</span></h1><p>Explore your everyday favourites in one convenient place. Product availability and pricing will come from the live catalogue.</p><a href="#catalogue" className="primary-link">Explore catalogue <span>↗</span></a></div><div className="hero-art" aria-hidden="true"><div className="orb orb-one"></div><div className="orb orb-two"></div><div className="hero-bag">S<span>+</span></div><div className="float-card">Everyday<br/><b>made easier</b></div></div></section>
      <section className="service"><div><b>Check delivery availability</b><p>Enter your PIN code to check serviceability.</p></div><form onSubmit={checkServiceability}><input inputMode="numeric" maxLength="6" placeholder="6-digit PIN code" value={pincode} onChange={e=>setPincode(e.target.value.replace(/\D/g,''))}/><button type="submit">Check</button></form></section>
      {notice && <p className="notice" role="status">{notice}</p>}
      <section id="catalogue" className="catalogue"><div className="section-heading"><div><p className="eyebrow">THE SUPER BAJAAR EDIT</p><h2>Shop the catalogue</h2><p>Live products will appear here once the backend is connected.</p></div><div className="theme-switch"><span>Theme</span>{['soft','light','dark'].map(t=><button key={t} className={theme===t?'selected':''} onClick={()=>setTheme(t)}>{t[0].toUpperCase()+t.slice(1)}</button>)}</div></div>
        {loading && <div className="state-card">Loading catalogue…</div>}
        {!loading && error && <div className="state-card"><b>Catalogue connection pending</b><p>{error}</p><button onClick={()=>loadProducts()}>Retry</button></div>}
        {!loading && !error && products.length===0 && <div className="empty-state"><div className="empty-icon">✳</div><h3>Your next favourite starts here</h3><p>No catalogue items were returned. Connect the product API or add products through the admin backend.</p></div>}
        {products.length>0 && <div className="product-grid">{products.map(p=><article className="product-card" key={p.id || p.sku}><div className="product-image">{p.image_url || p.image ? <img src={p.image_url || p.image} alt={p.name || 'Product'}/> : <span>SB</span>}</div><div className="product-info"><small>{p.category_name || p.category || 'Everyday essentials'}</small><h3>{p.name || p.product_name}</h3><p className="sku">{p.sku || p.default_code || ''}</p><div className="price">{p.selling_price != null ? '₹'+Number(p.selling_price).toLocaleString('en-IN') : p.price != null ? '₹'+Number(p.price).toLocaleString('en-IN') : 'Price unavailable'}</div><button onClick={()=>setNotice('Cart integration will be enabled with the order API.')}>View product</button></div></article>)}</div>}
      </section>
      <section className="promise-grid"><div><span>01</span><b>Useful everyday picks</b><p>A clear catalogue built around your needs.</p></div><div><span>02</span><b>Local availability</b><p>Availability checked against real service-area and stock data.</p></div><div><span>03</span><b>Transparent information</b><p>Product, pricing and seller details supplied by the backend.</p></div></section>
    </main>
    <footer><a className="brand footer-brand" href="#"><span className="brand-mark">S</span><span>super<span className="brand-accent">bajaar</span><small>Your Everyday Super Store</small></span></a><p>Thoughtful shopping for everyday life.</p><div className="footer-bottom"><span>© {new Date().getFullYear()} Super Bajaar</span><span>Website-first commerce platform</span></div></footer>
  </div>;
}
createRoot(document.getElementById('root')).render(<App />);
