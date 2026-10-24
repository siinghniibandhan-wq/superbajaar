import React, { useEffect, useMemo, useState } from 'react';
import { createRoot } from 'react-dom/client';
import './styles.css';

const configuredApiBase = (import.meta.env.VITE_API_BASE_URL || '').trim().replace(/\/$/, '');
const API_BASE = (() => {
  // Keep the storefront usable during initial testing even if Amplify's env var
  // has not been configured yet. Accept either the host or the full /api base.
  const candidate = configuredApiBase || 'https://superappkart.duckdns.org/api';
  return candidate.endsWith('/api') ? candidate : candidate + '/api';
})();
const endpoint = (path) => `${API_BASE}${path}`;
const money = (value, currency = 'INR') => value == null
  ? 'Price unavailable'
  : new Intl.NumberFormat('en-IN', { style: 'currency', currency, maximumFractionDigits: 2 }).format(Number(value));

function normaliseProducts(payload) {
  const rows = Array.isArray(payload) ? payload : (payload?.items || payload?.products || []);
  const grouped = new Map();
  for (const row of rows) {
    const id = row.product_id ?? row.id ?? row.product_code ?? row.sku;
    if (id == null) continue;
    if (!grouped.has(id)) grouped.set(id, {
      id, name: row.name || row.product_name || 'Unnamed product',
      code: row.product_code || '', brand: row.brand || '',
      category: row.category || row.category_name || 'Everyday essentials',
      description: row.description || '', isBestseller: Boolean(row.is_bestseller || row.bestseller), variants: []
    });
    const product = grouped.get(id);
    const variantId = row.variant_id ?? row.sku ?? id;
    if (!product.variants.some(v => String(v.id) === String(variantId))) {
      product.variants.push({
        id: variantId, sku: row.sku || '', barcode: row.barcode || '',
        attributes: row.variant_attributes || null,
        price: row.selling_price, mrp: row.mrp, currency: row.currency || 'INR',
        stock: Number(row.available_quantity ?? row.stock_quantity ?? 0)
      });
    }
  }
  return [...grouped.values()];
}

function variantLabel(variant) {
  const attrs = variant.attributes;
  if (attrs && typeof attrs === 'object') {
    const text = Object.entries(attrs).map(([key, value]) => `${key}: ${value}`).join(' · ');
    if (text) return text;
  }
  if (typeof attrs === 'string' && attrs.trim()) return attrs;
  return variant.sku || 'Standard option';
}

function App() {
  const [theme, setTheme] = useState(() => {
    try { return localStorage.getItem('sb-theme') || 'soft'; } catch { return 'soft'; }
  });
  const [query, setQuery] = useState('');
  const [pincode, setPincode] = useState('');
  const [products, setProducts] = useState([]);
  const [selectedCategory, setSelectedCategory] = useState('All');
  const [selectedVariants, setSelectedVariants] = useState({});
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');
  const [apiState, setApiState] = useState(API_BASE ? 'connecting' : 'unconfigured');
  const [detail, setDetail] = useState(null);
  const [recentlyViewed, setRecentlyViewed] = useState(() => { try { return JSON.parse(localStorage.getItem('sb-recently-viewed') || '[]'); } catch { return []; } });
  const [brandFilter, setBrandFilter] = useState('');

  const categories = useMemo(() => ['All', ...new Set(products.map(p => p.category).filter(Boolean))], [products]);
  const visibleProducts = useMemo(() => {
    const term = query.trim().toLowerCase();
    return products.filter(p => (!brandFilter || p.brand === brandFilter) && (selectedCategory === 'All' || p.category === selectedCategory) &&
      (!term || [p.name, p.brand, p.category, p.code, ...p.variants.map(v => v.sku)]
        .some(value => String(value || '').toLowerCase().includes(term))));
  }, [products, query, selectedCategory, brandFilter]);

  async function loadProducts(search = query, pin = pincode) {
    if (!API_BASE) {
      setApiState('unconfigured');
      setError('The storefront API URL is not configured. Set VITE_API_BASE_URL to the backend API base URL.');
      return;
    }
    setLoading(true);
    setError('');
    setNotice('');
    setApiState('connecting');
    try {
      const params = new URLSearchParams({ limit: '100' });
      if (search.trim()) params.set('search', search.trim());
      if (pin.trim()) params.set('pincode', pin.trim());
      const response = await fetch(endpoint('/products?' + params.toString()), { headers: { Accept: 'application/json' } });
      if (!response.ok) throw new Error(response.status === 503
        ? 'The catalogue is temporarily unavailable. Please try again shortly.'
        : `The catalogue request failed (HTTP ${response.status}).`);
      const payload = await response.json();
      const next = normaliseProducts(payload);
      setProducts(next);
      setSelectedVariants(previous => {
        const updated = { ...previous };
        for (const product of next) {
          const current = updated[product.id];
          const stillExists = product.variants.some(variant => String(variant.id) === String(current));
          if ((!current || !stillExists) && product.variants[0]) updated[product.id] = String(product.variants[0].id);
        }
        return updated;
      });
      setSelectedCategory('All');
      setBrandFilter('');
      setApiState('connected');
    } catch (e) {
      setError(e.message || 'Unable to load the catalogue. Check the connection and retry.');
      setApiState('error');
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => { if (API_BASE) loadProducts('', ''); }, []);
  useEffect(() => { try { localStorage.setItem('sb-theme', theme); } catch {} }, [theme]);
  useEffect(() => { try { localStorage.setItem('sb-recently-viewed', JSON.stringify(recentlyViewed.slice(0, 12))); } catch {} }, [recentlyViewed]);
  function openProduct(product) { setDetail(product); setRecentlyViewed(previous => [product.id, ...previous.filter(id => String(id) !== String(product.id))].slice(0, 12)); }
  const recentlyViewedProducts = recentlyViewed.map(id => products.find(product => String(product.id) === String(id))).filter(Boolean);
  const bestsellerProducts = products.filter(product => product.isBestseller);
  const brandGroups = [...new Set(products.map(product => product.brand).filter(Boolean))].map(brand => ({ brand, items: products.filter(product => product.brand === brand) }));

  async function checkServiceability(event) {
    event.preventDefault();
    if (!/^\d{6}$/.test(pincode)) {
      setNotice('Enter a valid 6-digit PIN code.');
      return;
    }
    if (!API_BASE) {
      setNotice('Delivery checks are unavailable until the backend API is configured.');
      return;
    }
    setNotice('');
    try {
      const response = await fetch(endpoint('/serviceability?pincode=' + encodeURIComponent(pincode)), { headers: { Accept: 'application/json' } });
      const data = await response.json().catch(() => ({}));
      if (!response.ok) throw new Error(data.detail || 'We could not verify delivery availability right now.');
      if (data.serviceable) {
        await loadProducts(query, pincode);
        setNotice(`Delivery is available for ${pincode}.`);
      } else {
        setNotice(`Delivery is not currently available for ${pincode}.`);
      }
    } catch (e) {
      setNotice(e.message || 'We could not verify delivery availability right now.');
    }
  }

  const selectedVariant = product => product.variants.find(v => String(v.id) === String(selectedVariants[product.id])) || product.variants[0];

  return <div className="app" data-theme={theme}>
    <div className="announcement"><span className="announcement-dot" /> Everyday essentials, all in one place <span className="announcement-note">Your Everyday Super Store</span></div>
    <header className="header">
      <a className="brand" href="#" aria-label="Super Bajaar home">
        <span className="brand-mark">S</span>
        <span className="brand-word">super<span>bajaar</span><small>Your Everyday Super Store</small></span>
      </a>
      <form className="search" role="search" onSubmit={e => { e.preventDefault(); loadProducts(query, pincode); }}>
        <span className="search-icon" aria-hidden="true">⌕</span>
        <input aria-label="Search products" placeholder="Search products, brands or SKU" value={query} onChange={e => setQuery(e.target.value)} />
        {query && <button className="clear-search" type="button" aria-label="Clear search" onClick={() => setQuery('')}>×</button>}
        <button type="submit">Search</button>
      </form>
      <div className="header-actions">
        <button className="header-link" onClick={() => setNotice('Customer accounts will be enabled when the authentication flow is ready.')}>Account</button>
        <button className="cart-button" onClick={() => setNotice('The catalogue is connected; cart and checkout require their backend endpoints.')}>Bag <span>0</span></button>
      </div>
    </header>

    <main>
      <section className="hero">
        <div className="hero-copy">
          <div className="hero-kicker"><span>THE EVERYDAY EDIT</span><i /></div>
          <h1>Good finds.<br /><span>Better everyday.</span></h1>
          <p>Discover your everyday favourites with a simpler, brighter shopping experience. Prices and availability come from the live catalogue.</p>
          <a href="#catalogue" className="primary-link">Explore the catalogue <span aria-hidden="true">↗</span></a>
          <div className="hero-proof"><span>✦ Thoughtful essentials</span><span>✓ Real catalogue data</span></div>
        </div>
        <div className="hero-art" aria-hidden="true">
          <div className="hero-halo halo-one" /><div className="hero-halo halo-two" />
          <div className="hero-bag"><span className="bag-handle" /><b>S</b><i>+</i></div>
          <div className="floating-note"><span>YOUR DAY,</span><b>made easier.</b><small>Everyday shopping, simplified.</small></div>
          <div className="sparkle sparkle-one">✦</div><div className="sparkle sparkle-two">✳</div>
        </div>
      </section>

      <section className="service-card" aria-labelledby="service-title">
        <div className="service-icon" aria-hidden="true">⌖</div>
        <div className="service-copy"><h2 id="service-title">Shopping in your area?</h2><p>Check delivery availability for your PIN code.</p></div>
        <form onSubmit={checkServiceability} className="service-form">
          <span aria-hidden="true">＋91</span>
          <input inputMode="numeric" autoComplete="postal-code" aria-label="6-digit PIN code" maxLength={6} placeholder="Enter 6-digit PIN" value={pincode} onChange={e => setPincode(e.target.value.replace(/\D/g, ''))} />
          <button type="submit">Check availability</button>
        </form>
      </section>
      {notice && <div className="notice" role="status"><span>ⓘ</span><p>{notice}</p><button aria-label="Dismiss message" onClick={() => setNotice('')}>×</button></div>}

      <section id="catalogue" className="catalogue">
        <div className="section-heading">
          <div><p className="eyebrow">PICKED FOR EVERYDAY</p><h2>Explore the catalogue<span>.</span></h2><p>Browse live products and choose the variant that suits you.</p></div>
          <div className="heading-tools">
            <div className="theme-switch" role="group" aria-label="Choose colour theme">
              {['soft', 'light', 'dark'].map(option => <button type="button" key={option} aria-pressed={theme === option} className={theme === option ? 'selected' : ''} onClick={() => setTheme(option)}>{option[0].toUpperCase() + option.slice(1)}</button>)}
            </div>
            <div className={`api-status status-${apiState}`}><i />{apiState === 'connected' ? 'Live catalogue connected' : apiState === 'connecting' ? 'Connecting to catalogue' : apiState === 'unconfigured' ? 'API setup required' : 'Catalogue unavailable'}</div>
          </div>
        </div>

        {products.length > 0 && <div className="home-discovery">
          <section className="discovery-section" aria-labelledby="bestsellers-title">
            <div className="discovery-heading"><div><p className="eyebrow">CUSTOMER FAVOURITES</p><h2 id="bestsellers-title">Bestsellers<span>.</span></h2><p>Products customers are choosing most.</p></div><span className="discovery-icon">★</span></div>
            {bestsellerProducts.length ? <div className="discovery-row">{bestsellerProducts.slice(0,8).map(product => <button className="discovery-product" key={product.id} onClick={() => openProduct(product)}><span className="discovery-product-art">SB<span>✦</span></span><b>{product.name}</b><small>{product.brand || product.category}</small><strong>{money(selectedVariant(product).price,selectedVariant(product).currency)}</strong></button>)}</div> : <p className="discovery-empty">Bestsellers will appear here once sales or bestseller labels are available in the catalogue. We won't guess which products sell most.</p>}
          </section>
          {brandGroups.length > 0 && <section className="discovery-section" aria-labelledby="brands-title"><div className="discovery-heading"><div><p className="eyebrow">SHOP YOUR FAVOURITES</p><h2 id="brands-title">Shop by brand<span>.</span></h2><p>Explore products from the brands in our catalogue.</p></div><span className="discovery-icon">✦</span></div><div className="brand-catalogue">{brandGroups.slice(0,12).map(group=><button className="brand-tile" key={group.brand} onClick={()=>{setQuery('');setSelectedCategory('All');setBrandFilter(group.brand);document.getElementById('catalogue-grid')?.scrollIntoView({behavior:'smooth'});}}><span className="brand-initial">{group.brand.trim().charAt(0).toUpperCase()}</span><span><b>{group.brand}</b><small>{group.items.length} {group.items.length===1?'product':'products'}</small></span><i>↗</i></button>)}</div></section>}
          {recentlyViewedProducts.length > 0 && <section className="discovery-section" aria-labelledby="recent-title"><div className="discovery-heading"><div><p className="eyebrow">PICK UP WHERE YOU LEFT OFF</p><h2 id="recent-title">Recently viewed<span>.</span></h2><p>Your recently opened products, saved on this device.</p></div><span className="discovery-icon">◷</span></div><div className="discovery-row">{recentlyViewedProducts.map(product=><button className="discovery-product" key={product.id} onClick={()=>openProduct(product)}><span className="discovery-product-art">SB<span>✦</span></span><b>{product.name}</b><small>{product.brand || product.category}</small><strong>{money(selectedVariant(product).price,selectedVariant(product).currency)}</strong></button>)}</div></section>}
        </div>}
        {products.length > 0 && <div className="category-row" aria-label="Filter by category">
          {categories.map(category => <button key={category} className={selectedCategory === category ? 'category-chip active' : 'category-chip'} onClick={() => setSelectedCategory(category)}>{category}<span>{category === 'All' ? products.length : products.filter(p => p.category === category).length}</span></button>)}
        </div>}
        {loading && <div className="catalogue-state"><div className="loader" /><h3>Finding your everyday favourites</h3><p>Loading the latest catalogue information…</p></div>}
        {!loading && error && <div className="catalogue-state error-state"><div className="state-symbol">↻</div><h3>We couldn't load the catalogue</h3><p>{error}</p><button className="primary-link button-link" onClick={() => loadProducts(query, pincode)}>Try again <span>↗</span></button></div>}
        {!loading && !error && products.length === 0 && <div className="catalogue-state"><div className="state-symbol">✳</div><h3>Your next favourite starts here</h3><p>No published products were returned by the catalogue. When products are available, they will appear here automatically.</p><button className="secondary-button" onClick={() => loadProducts('', '')}>Refresh catalogue</button></div>}
        {!loading && !error && products.length > 0 && visibleProducts.length === 0 && <div className="catalogue-state"><div className="state-symbol">⌕</div><h3>No matches found</h3><p>Try another search or choose a different category.</p><button className="secondary-button" onClick={() => { setQuery(''); setSelectedCategory('All'); setBrandFilter(''); }}>Clear filters</button></div>}
        {!loading && !error && visibleProducts.length > 0 && <div id="catalogue-grid" className="product-grid">
          {visibleProducts.map(product => {
            const variant = selectedVariant(product);
            return <article className="product-card" key={product.id}>
              <button className="product-image" onClick={() => openProduct(product)} aria-label={`View details for ${product.name}`}>
                <span className="image-monogram">SB<span>✦</span></span><span className="image-caption">{product.category}</span>
              </button>
              <div className="product-info">
                <div className="product-meta"><span>{product.brand || product.category}</span>{variant.stock > 0 && <span className="stock-badge">In stock</span>}</div>
                <button className="product-title" onClick={() => setDetail(product)}>{product.name}</button>
                {product.variants.length > 1 && <label className="variant-select">Choose option
                  <select aria-label={`Choose variant for ${product.name}`} value={String(variant.id)} onChange={e => setSelectedVariants(prev => ({ ...prev, [product.id]: e.target.value }))}>
                    {product.variants.map(v => <option key={v.id} value={String(v.id)}>{variantLabel(v)}</option>)}
                  </select>
                </label>}
                <div className="product-price"><strong>{money(variant.price, variant.currency)}</strong>{variant.mrp != null && Number(variant.mrp) > Number(variant.price) && <del>{money(variant.mrp, variant.currency)}</del>}</div>
                <div className="product-stock">{variant.stock > 0 ? `${variant.stock} available` : 'Availability not confirmed'}</div>
                <button className="details-button" onClick={() => setDetail(product)}>View details <span>↗</span></button>
              </div>
            </article>;
          })}
        </div>}
        {products.length > 0 && <p className="catalogue-footnote">Showing real catalogue records only. Price and availability are subject to backend confirmation.</p>}
      </section>

      <section className="promise-grid" aria-label="Shopping principles">
        <div><span className="promise-icon">✦</span><div><b>Everyday essentials</b><p>A considered catalogue for the things you need.</p></div></div>
        <div><span className="promise-icon">⌖</span><div><b>Local availability</b><p>Delivery checks rely on actual service-area data.</p></div></div>
        <div><span className="promise-icon">✓</span><div><b>Clear product details</b><p>Prices and stock are sourced from the backend.</p></div></div>
      </section>
    </main>

    <footer>
      <div className="footer-main">
        <a className="brand footer-brand" href="#"><span className="brand-mark">S</span><span className="brand-word">super<span>bajaar</span><small>Your Everyday Super Store</small></span></a>
        <p>Little things for everyday living. A simpler way to find what you need.</p>
        <a className="back-top" href="#">Back to top ↑</a>
      </div>
      <div className="footer-bottom"><span>© {new Date().getFullYear()} Super Bajaar</span><span>Your Everyday Super Store</span></div>
    </footer>

    {detail && <div className="modal-backdrop" role="presentation" onMouseDown={e => { if (e.target === e.currentTarget) setDetail(null); }}>
      <section className="detail-modal" role="dialog" aria-modal="true" aria-labelledby="detail-title">
        <button className="modal-close" aria-label="Close product details" onClick={() => setDetail(null)}>×</button>
        <div className="detail-art"><span className="image-monogram">SB<span>✦</span></span></div>
        <div className="detail-copy"><p className="eyebrow">{detail.category}</p><h2 id="detail-title">{detail.name}</h2>{detail.brand && <p className="detail-brand">{detail.brand}</p>}
          <p className="detail-description">{detail.description || 'Product details will be shown here when provided by the live catalogue.'}</p>
          {detail.variants.length > 1 && <label className="variant-select">Choose option<select value={String(selectedVariant(detail).id)} onChange={e => setSelectedVariants(prev => ({ ...prev, [detail.id]: e.target.value }))}>{detail.variants.map(v => <option key={v.id} value={String(v.id)}>{variantLabel(v)}</option>)}</select></label>}
          <div className="detail-price">{money(selectedVariant(detail).price, selectedVariant(detail).currency)}</div><p className="detail-sku">SKU: {selectedVariant(detail).sku || 'Not provided'} · Stock: {selectedVariant(detail).stock > 0 ? selectedVariant(detail).stock : 'Not confirmed'}</p>
          <div className="detail-notice">Cart and checkout will be enabled when the corresponding backend APIs are available.</div>
          <button className="primary-link button-link" onClick={() => setDetail(null)}>Continue browsing <span>↗</span></button>
        </div>
      </section>
    </div>}
  </div>;
}

function AdminPanel() {
  const [token, setToken] = useState(() => { try { return sessionStorage.getItem('sb-admin-token') || ''; } catch { return ''; } });
  const [username, setUsername] = useState('admin');
  const [password, setPassword] = useState('');
  const [items, setItems] = useState([]);
  const [tab, setTab] = useState('add');
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState('');
  const [form, setForm] = useState({name:'',product_code:'',sku:'',brand:'',category:'Grocery & Staples',description:'',selling_price:'',mrp:'',currency:'INR',active:true});
  const field = (key, value) => setForm(previous => ({...previous,[key]:value}));
  async function login(event) {
    event.preventDefault(); setBusy(true); setMessage('');
    try {
      const response = await fetch(endpoint('/admin/login'), {method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({username,password})});
      const data = await response.json().catch(()=>({}));
      if(!response.ok) throw new Error(data.detail || 'Admin sign-in failed');
      setToken(data.access_token); try { sessionStorage.setItem('sb-admin-token',data.access_token); } catch {} setPassword('');
      setMessage('Signed in successfully'); await loadAdminProducts(data.access_token);
    } catch(error) { setMessage(error.message); }
    finally { setBusy(false); }
  }
  async function loadAdminProducts(access=token) {
    try {
      const response = await fetch(endpoint('/admin/products'),{headers:{Authorization:'Bearer '+access,Accept:'application/json'}});
      const data = await response.json().catch(()=>({}));
      if(!response.ok) {
        if(response.status === 401) {
          setToken('');
          setItems([]);
          try { sessionStorage.removeItem('sb-admin-token'); } catch {}
          throw new Error('Your admin session has expired. Please sign in again.');
        }
        throw new Error(data.detail || 'Could not load products');
      }
      setItems(data.items || []);
    } catch(error) { setMessage(error.message); }
  }
  async function saveProduct(event) {
    event.preventDefault(); setBusy(true); setMessage('');
    try {
      const payload = {...form,selling_price:Number(form.selling_price),mrp:form.mrp===''?null:Number(form.mrp)};
      const response = await fetch(endpoint('/admin/products'),{method:'POST',headers:{'Content-Type':'application/json',Authorization:'Bearer '+token},body:JSON.stringify(payload)});
      const data = await response.json().catch(()=>({}));
      if(!response.ok) throw new Error(data.detail || 'Could not save product');
      setMessage('Product saved successfully. Active products are eligible for storefront display. No stock was added.');
      setForm({name:'',product_code:'',sku:'',brand:'',category:'Grocery & Staples',description:'',selling_price:'',mrp:'',currency:'INR',active:true});
      await loadAdminProducts();
    } catch(error) { setMessage(error.message); }
    finally { setBusy(false); }
  }
  function signOut(){setToken('');setItems([]);try { sessionStorage.removeItem('sb-admin-token'); } catch {} setMessage('Signed out');}
  useEffect(() => {
    if (token) loadAdminProducts(token);
  }, []);
  return <div className="admin-shell">
    <header className="admin-top"><a className="brand" href="/"><span className="brand-mark">S</span><span className="brand-word">super<span>bajaar</span><small>Product management</small></span></a><span className="admin-badge">ADMIN CONSOLE</span>{token && <button className="header-link" onClick={signOut}>Sign out</button>}</header>
    {!token ? <main className="admin-login-wrap"><form className="admin-login" onSubmit={login}><p className="eyebrow">RESTRICTED ACCESS</p><h1>Admin sign in</h1><p>Only authorised staff can manage the catalogue.</p><label>Admin ID<input autoComplete="username" value={username} onChange={e=>setUsername(e.target.value)} required /></label><label>Password<input type="password" autoComplete="current-password" value={password} onChange={e=>setPassword(e.target.value)} required /></label><button className="add-cart-button" disabled={busy}>{busy?'Signing in…':'Sign in securely'}</button>{message&&<p className="admin-message" role="status">{message}</p>}</form></main> : <main className="admin-main">
      <div className="admin-heading"><div><p className="eyebrow">SUPER BAJAAR OPERATIONS</p><h1>Admin dashboard</h1><p>Central workspace for product, inventory, purchasing, sales, finance, logistics and people operations.</p></div><div className="admin-count"><b>{items.length}</b><span>catalogue records</span></div></div><section className="admin-module-grid" aria-label="Admin modules">{[{icon:"▦",name:"Products",desc:"Product master, SKU, variants and pricing",status:"Available",active:true},{icon:"▤",name:"Inventory",desc:"Warehouses, stock ledger and adjustments",status:"Next phase"},{icon:"🛒",name:"Sales",desc:"Orders, fulfilment, invoices and returns",status:"Next phase"},{icon:"📥",name:"Purchase",desc:"Suppliers, purchase orders and GRN",status:"Next phase"},{icon:"⇢",name:"Logistics",desc:"Dispatch, tracking and delivery exceptions",status:"Next phase"},{icon:"₹",name:"Accounting",desc:"Ledger, receivables, payables and GST",status:"Next phase"},{icon:"♙",name:"Employees",desc:"Employee records, departments and roles",status:"Next phase"},{icon:"◷",name:"Attendance",desc:"Shifts, check-in/out and leave",status:"Next phase"},{icon:"▥",name:"Payroll",desc:"Salary runs, deductions and payslips",status:"Next phase"},{icon:"♧",name:"Customers & Suppliers",desc:"Profiles, contacts and transaction history",status:"Next phase"},{icon:"▧",name:"Reports",desc:"Sales, inventory, purchasing and finance",status:"Next phase"},{icon:"⚙",name:"Settings & Access",desc:"Users, permissions, taxes and numbering",status:"Next phase"}].map(module=><article key={module.name} className={"admin-module-card"+(module.active?" module-active":"")}><span className="admin-module-icon">{module.icon}</span><div><h2>{module.name}</h2><p>{module.desc}</p><span className="admin-module-status">{module.status}</span></div></article>)}</section>
      <div className="admin-tabs"><button className={tab==='add'?'active':''} onClick={()=>setTab('add')}>＋ Add product</button><button className={tab==='list'?'active':''} onClick={()=>{setTab('list');loadAdminProducts();}}>Product list ({items.length})</button></div>
      {message&&<p className="admin-message" role="status">{message}</p>}
      {tab==='add' ? <form className="admin-product-form" onSubmit={saveProduct}><div className="admin-form-heading"><h2>Product information</h2><p>Required fields are marked with *.</p></div>
        <div className="admin-form-grid">
          <label>Product name *<input value={form.name} onChange={e=>field('name',e.target.value)} maxLength={200} required /></label>
          <label>Product code *<input value={form.product_code} onChange={e=>field('product_code',e.target.value)} maxLength={80} required /></label>
          <label>SKU / variant code *<input value={form.sku} onChange={e=>field('sku',e.target.value)} maxLength={100} required /></label>
          <label>Brand<input value={form.brand} onChange={e=>field('brand',e.target.value)} maxLength={150} /></label>
          <label>Category *<input value={form.category} onChange={e=>field('category',e.target.value)} maxLength={100} required /></label>
          <label>Selling price (₹) *<input type="number" min="0" step="0.01" value={form.selling_price} onChange={e=>field('selling_price',e.target.value)} required /></label>
          <label>MRP (optional) ₹<input type="number" min="0" step="0.01" value={form.mrp} onChange={e=>field('mrp',e.target.value)} /></label>
          <label>Currency<select value={form.currency} onChange={e=>field('currency',e.target.value)}><option>INR</option><option>USD</option></select></label>
          <label className="admin-full">Detailed description<textarea rows="5" value={form.description} onChange={e=>field('description',e.target.value)} maxLength={5000} placeholder="Product details, ingredients/material, size, usage, care instructions, etc." /></label>
        </div>
        <div className="admin-publish-options"><label className="admin-check"><input type="checkbox" checked={form.active} onChange={e=>field('active',e.target.checked)} /> Product active</label><p>Active products are eligible for storefront display. Saving a product does not add stock; inventory will be managed through receiving and stock-movement workflows.</p></div>
        <div className="admin-form-actions"><button type="button" className="secondary-button" onClick={()=>setForm({name:'',product_code:'',sku:'',brand:'',category:'Grocery & Staples',description:'',selling_price:'',mrp:'',currency:'INR',active:true})}>Clear form</button><button className="add-cart-button" disabled={busy}>{busy?'Saving…':'Save product'}</button></div>
      </form> : <section className="admin-product-list"><div className="admin-form-heading"><h2>All products</h2><button className="secondary-button" onClick={()=>loadAdminProducts()}>Refresh list</button></div>{items.length===0?<p>No product records returned.</p>:<div className="admin-table-wrap"><table><thead><tr><th>Product</th><th>SKU</th><th>Category</th><th>Selling price</th><th>Product status</th><th>Variant status</th><th>Visibility</th></tr></thead><tbody>{items.map(item=><tr key={item.variant_id}><td><b>{item.name}</b><small>{item.product_code}</small></td><td>{item.sku}</td><td>{item.category||'—'}</td><td>{money(item.selling_price,item.currency)}</td><td>{item.product_status}</td><td>{item.variant_status}</td><td>{item.product_status==='active'&&item.variant_status==='active'?'Storefront eligible':'Not eligible'}</td></tr>)}</tbody></table></div>}</section>}
    </main>}
  </div>;
}


function Root() { return window.location.pathname.startsWith('/admin') ? <AdminPanel /> : <App />; }

createRoot(document.getElementById('root')).render(<Root />);
