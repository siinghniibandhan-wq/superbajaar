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
      description: row.description || '', variants: []
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

  const categories = useMemo(() => ['All', ...new Set(products.map(p => p.category).filter(Boolean))], [products]);
  const visibleProducts = useMemo(() => {
    const term = query.trim().toLowerCase();
    return products.filter(p => (selectedCategory === 'All' || p.category === selectedCategory) &&
      (!term || [p.name, p.brand, p.category, p.code, ...p.variants.map(v => v.sku)]
        .some(value => String(value || '').toLowerCase().includes(term))));
  }, [products, query, selectedCategory]);

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
        {products.length > 0 && <div className="category-row" aria-label="Filter by category">
          {categories.map(category => <button key={category} className={selectedCategory === category ? 'category-chip active' : 'category-chip'} onClick={() => setSelectedCategory(category)}>{category}<span>{category === 'All' ? products.length : products.filter(p => p.category === category).length}</span></button>)}
        </div>}
        {loading && <div className="catalogue-state"><div className="loader" /><h3>Finding your everyday favourites</h3><p>Loading the latest catalogue information…</p></div>}
        {!loading && error && <div className="catalogue-state error-state"><div className="state-symbol">↻</div><h3>We couldn't load the catalogue</h3><p>{error}</p><button className="primary-link button-link" onClick={() => loadProducts(query, pincode)}>Try again <span>↗</span></button></div>}
        {!loading && !error && products.length === 0 && <div className="catalogue-state"><div className="state-symbol">✳</div><h3>Your next favourite starts here</h3><p>No published products were returned by the catalogue. When products are available, they will appear here automatically.</p><button className="secondary-button" onClick={() => loadProducts('', '')}>Refresh catalogue</button></div>}
        {!loading && !error && products.length > 0 && visibleProducts.length === 0 && <div className="catalogue-state"><div className="state-symbol">⌕</div><h3>No matches found</h3><p>Try another search or choose a different category.</p><button className="secondary-button" onClick={() => { setQuery(''); setSelectedCategory('All'); }}>Clear filters</button></div>}
        {!loading && !error && visibleProducts.length > 0 && <div className="product-grid">
          {visibleProducts.map(product => {
            const variant = selectedVariant(product);
            return <article className="product-card" key={product.id}>
              <button className="product-image" onClick={() => setDetail(product)} aria-label={`View details for ${product.name}`}>
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

createRoot(document.getElementById('root')).render(<App />);
