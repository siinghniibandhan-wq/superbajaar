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
      description: row.description || '', isBestseller: Boolean(row.is_bestseller || row.bestseller), isNewArrival: Boolean(row.is_new_arrival || row.new_arrival || row.is_new), variants: []
    });
    const product = grouped.get(id);
    const variantId = row.variant_id ?? row.sku ?? id;
    if (!product.variants.some(v => String(v.id) === String(variantId))) {
      product.variants.push({
        id: variantId, sku: row.sku || '', barcode: row.barcode || '',
        attributes: row.variant_attributes || null,
        price: row.selling_price, mrp: row.mrp, lowest30: row.lowest_selling_price_30d, currency: row.currency || 'INR', imageUrl: row.image_url || row.image || '',
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

function ProductDisplayTemplate({ product, variant, attributes, variantImage, variantAttributes, selectedVariants, setSelectedVariants, productQty, setProductQty, money, onBack, onAddToBag }) {
  return <div className="product-detail-layout">
    <div className="product-detail-gallery">
      <div className="product-main-image">{variantImage ? <img src={variantImage} alt={product.name} /> : <div className="image-monogram">SB<span>✦</span></div>}</div>
      <div className="product-gallery-note">{variantImage ? 'Product image' : 'Product image not supplied by catalogue'}</div>
    </div>
    <section className="product-detail-info">
      <button className="product-back-link" onClick={onBack}>← Back to shop</button>
      <p className="eyebrow">{product.category}</p><h1>{product.name}</h1>
      {product.brand && <p className="product-detail-brand">Brand: <strong>{product.brand}</strong></p>}
      <div className="product-detail-price"><strong>{money(variant?.price, variant?.currency)}</strong>{variant?.mrp != null && Number(variant.mrp)>Number(variant.price) && <del>{money(variant.mrp,variant.currency)}</del>}</div>
      {variant?.lowest30 != null && <p className="price-history">Lowest selling price · 30 days: <b>{money(variant.lowest30,variant.currency)}</b></p>}
      <p className="product-detail-stock">{variant?.stock > 0 ? 'In stock · ' + variant.stock + ' available' : 'Availability not confirmed'}</p>
      {product.variants.length > 1 && <div className="product-variant-selectors"><h2>Choose options</h2>{[...new Set(product.variants.flatMap(v => variantAttributes(v).map(attr => attr.key)))].map(attributeName => {
        const values = [...new Map(product.variants.flatMap(v => variantAttributes(v).filter(attr => attr.key === attributeName).map(attr => [String(attr.value), { value: attr.value, variantId: v.id }]))).values()];
        if (!values.length) return null;
        const selectedAttr = variantAttributes(variant).find(attr => attr.key === attributeName);
        return <label key={attributeName}>{attributeName}<select aria-label={'Choose '+attributeName} value={String(selectedAttr?.value ?? '')} onChange={e => { const match = product.variants.find(v => variantAttributes(v).some(attr => attr.key === attributeName && String(attr.value) === e.target.value)); if (match) setSelectedVariants(prev => ({...prev,[product.id]:String(match.id)})); }}>{values.map(option => <option key={String(option.value)} value={String(option.value)}>{option.value}</option>)}</select></label>;
      })}</div>}
      {attributes.length > 0 && <div className="product-attributes"><h2>Selected option details</h2>{attributes.map((attr,i)=><div className="product-attribute-row" key={attr.key+'-'+i}><span>{attr.key}</span><strong>{attr.value}</strong></div>)}</div>}
      <div className="product-quantity-control"><span>Quantity</span><div><button type="button" onClick={() => setProductQty(q=>Math.max(1,q-1))} aria-label="Decrease quantity">−</button><strong>{productQty}</strong><button type="button" onClick={() => setProductQty(q=>Math.min(99,q+1))} aria-label="Increase quantity">＋</button></div></div>
      <button className="add-cart-button product-add-button" onClick={() => onAddToBag(productQty)}>＋ Add to bag</button>
      <section className="product-description"><h2>Product details</h2><p>{product.description || 'Detailed product information has not been provided in the live catalogue yet.'}</p><div className="product-detail-facts"><div><span>Category</span><strong>{product.category || 'Not provided'}</strong></div><div><span>SKU</span><strong>{variant?.sku || 'Not provided'}</strong></div><div><span>Brand</span><strong>{product.brand || 'Not provided'}</strong></div>{attributes.map((attr,i)=><div key={attr.key+'-fact-'+i}><span>{attr.key}</span><strong>{attr.value}</strong></div>)}</div></section>
    </section>
  </div>;
}

function App() {
  const [theme] = useState('soft');
  const routeFromPath = () => { const path = window.location.pathname; if (path.startsWith('/product/')) return 'product'; if (path === '/shop' || path === '/catalogue') return 'shop'; return 'home'; };
  const [activePage, setActivePage] = useState(routeFromPath);
  const [routeProductId, setRouteProductId] = useState(() => window.location.pathname.startsWith('/product/') ? decodeURIComponent(window.location.pathname.split('/')[2] || '') : '');
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
  const [cart, setCart] = useState(() => { try { return JSON.parse(localStorage.getItem('sb-cart') || '[]'); } catch { return []; } });
  const [cartOpen, setCartOpen] = useState(false);
  const [productQty, setProductQty] = useState(1);
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
  useEffect(() => { const onPopState = () => { const path = window.location.pathname; setActivePage(path.startsWith('/product/') ? 'product' : (path === '/shop' || path === '/catalogue') ? 'shop' : 'home'); setRouteProductId(path.startsWith('/product/') ? decodeURIComponent(path.split('/')[2] || '') : ''); setDetail(null); window.scrollTo(0, 0); }; window.addEventListener('popstate', onPopState); return () => window.removeEventListener('popstate', onPopState); }, []);
  function navigate(path, page, productId = '') { window.history.pushState({}, '', path); setActivePage(page); setRouteProductId(String(productId)); setDetail(null); window.scrollTo({ top: 0, behavior: 'auto' }); }
  function goShop(search = '') { setQuery(search); setSelectedCategory('All'); setBrandFilter(''); navigate('/shop', 'shop'); loadProducts(search, pincode); }
  useEffect(() => { try { localStorage.setItem('sb-cart', JSON.stringify(cart)); } catch {} }, [cart]);
  const cartCount = cart.reduce((sum, item) => sum + item.quantity, 0);
  const cartTotal = cart.reduce((sum, item) => sum + Number(item.price || 0) * item.quantity, 0);
  function addToCart(product, variant) {
    if (variant.price == null || Number(variant.price) <= 0) { setNotice('Selling price is not available for this product yet.'); return; }
    const key = String(product.id) + ':' + String(variant.id);
    setCart(previous => { const existing = previous.find(item => item.key === key); if (existing) return previous.map(item => item.key === key ? { ...item, quantity: item.quantity + 1 } : item); return [...previous, { key, name: product.name, option: variantLabel(variant), price: Number(variant.price), currency: variant.currency, quantity: 1 }]; });
    setNotice(product.name + ' added to your bag.');
  }
  function changeCartQuantity(key, delta) { setCart(previous => previous.map(item => item.key === key ? { ...item, quantity: item.quantity + delta } : item).filter(item => item.quantity > 0)); }
  useEffect(() => { try { localStorage.setItem('sb-recently-viewed', JSON.stringify(recentlyViewed.slice(0, 12))); } catch {} }, [recentlyViewed]);
  function openProduct(product) { setProductQty(1); setRecentlyViewed(previous => [product.id, ...previous.filter(id => String(id) !== String(product.id))].slice(0, 12)); navigate('/product/' + encodeURIComponent(product.id), 'product', product.id); }
  const recentlyViewedProducts = recentlyViewed.map(id => products.find(product => String(product.id) === String(id))).filter(Boolean);
  const bestsellerProducts = products.filter(product => product.isBestseller);
  const newArrivalProducts = products.filter(product => product.isNewArrival);
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
  const routeProduct = products.find(product => String(product.id) === String(routeProductId)) || null;
  const variantAttributes = variant => { const attrs = variant?.attributes; if (attrs && typeof attrs === 'object') return Object.entries(attrs).filter(([, value]) => value != null && String(value).trim()).map(([key, value]) => ({ key, value })); if (typeof attrs === 'string' && attrs.trim()) return attrs.split(/[;,|]/).map(part => { const [key, ...rest] = part.split(/[:=]/); return { key: rest.length ? key.trim() : 'Option', value: (rest.length ? rest.join(':') : key).trim() }; }).filter(item => item.value); return []; };
  const currentVariant = routeProduct ? selectedVariant(routeProduct) : null;
  const variantImage = currentVariant?.imageUrl || routeProduct?.variants.find(v => v.imageUrl)?.imageUrl || ''; 

  return <div className="app" data-theme={theme}>
    <div className="announcement"><span className="announcement-dot" /> Everyday essentials, all in one place <span className="announcement-note">Your Everyday Super Store</span></div>
    <header className="header">
      <a className="brand" href="#home" aria-label="Super Bajaar home" onClick={e => { e.preventDefault(); navigate('/', 'home'); }}>
        <span className="brand-mark" aria-hidden="true"><svg viewBox="0 0 48 48" focusable="false" aria-hidden="true"><defs><linearGradient id="sbBagGradient" x1="0" y1="0" x2="1" y2="1"><stop offset="0%" stopColor="#5420d4"/><stop offset="55%" stopColor="#8129db"/><stop offset="100%" stopColor="#ff8739"/></linearGradient></defs><path d="M18 15V12a6 6 0 0 1 12 0v4" fill="none" stroke="#7fc4ff" strokeWidth="3.6" strokeLinecap="round"/><rect x="7" y="15" width="34" height="29" rx="7" fill="url(#sbBagGradient)"/><path d="M14 22c.7 6.2 4.7 10 10 10s9.3-3.8 10-10" fill="none" stroke="#fff" strokeWidth="3.2" strokeLinecap="round"/></svg></span>
        <span className="brand-word">Super <span>Bajaar</span><small>Your Everyday Super Store</small></span>
      </a>
      <form className="search" role="search" onSubmit={e => { e.preventDefault(); goShop(query); }}>
        <span className="search-icon" aria-hidden="true">⌕</span>
        <input aria-label="Search products" placeholder="Search products, brands or SKU" value={query} onChange={e => setQuery(e.target.value)} />
        {query && <button className="clear-search" type="button" aria-label="Clear search" onClick={() => setQuery('')}>×</button>}
        <button type="submit">Search</button>
      </form>
      
      <div className="header-actions">
        <button className="header-link" onClick={() => setNotice('Customer accounts will be enabled when the authentication flow is ready.')}>Account</button>
        <button className="cart-button" onClick={() => setCartOpen(true)}>Bag <span>{cartCount}</span></button>
      </div>
    </header>

    <nav className="category-navigation" aria-label="Shop categories">
      <div className="category-card-track">
        {[
          { name: 'Grocery', image: 'photo-1542838132-92c53300491e', terms: ['grocery', 'groceries', 'grocery & staples', 'staples'] },
          { name: 'Fresh Products', image: 'photo-1610832958506-aa56368176cf', terms: ['fresh products', 'fresh', 'fruits', 'vegetables', 'produce'] },
          { name: 'Fashion', image: 'photo-1483985988355-763728e1935b', terms: ['fashion', 'clothing', 'apparel'] },
          { name: 'Electronics', image: 'photo-1498049794561-7780e7231661', terms: ['electronics', 'electronic'] },
          { name: 'Home Essentials', image: 'photo-1616486338812-3dadae4b4ace', terms: ['home essentials', 'home', 'household'] },
          { name: 'Pharmacy', image: 'photo-1576602976047-174e57a47881', terms: ['pharmacy', 'health', 'personal care', 'medicine'] },
          { name: 'Pet Care', image: 'photo-1548199973-03cce0bbc87b', terms: ['pet care', 'pet'] }
        ].map(category => (
          <button type="button" className="category-image-card" key={category.name} onClick={() => {
            navigate('/shop', 'shop');
            const match = categories.find(existing => category.terms.some(term => existing.toLowerCase().includes(term)));
            navigate('/shop', 'shop');
            if (match) {
              setSelectedCategory(match);
              setQuery('');
              setBrandFilter('');
              window.scrollTo({top:0,behavior:'smooth'});
            } else {
              setSelectedCategory('All');
              setQuery(category.name);
              loadProducts(category.name, pincode);
              window.scrollTo({top:0,behavior:'smooth'});
            }
          }}>
            <span className="category-card-image" style={{backgroundImage: `url(https://images.unsplash.com/${category.image}?auto=format&fit=crop&w=360&q=80)`}} role="img" aria-label={category.name} />
            <span className="category-card-label">{category.name}</span>
          </button>
        ))}
      </div>
    </nav>

    {activePage !== 'product' && <main>
      {activePage === 'home' && <section className="hero">
        <div className="hero-copy">
          <div className="hero-kicker"><span>THE EVERYDAY EDIT</span><i /></div>
          <h1>Good finds.<br /><span>Better everyday.</span></h1>
          <p>Discover your everyday favourites with a simpler, brighter shopping experience. Prices and availability come from the live catalogue.</p>
          <button type="button" className="primary-link" onClick={() => goShop('')}>Explore the catalogue <span aria-hidden="true">↗</span></button>
          <div className="hero-proof"><span>✦ Thoughtful essentials</span><span>✓ Real catalogue data</span></div>
        </div>
        <div className="hero-art" aria-hidden="true">
          <div className="hero-halo halo-one" /><div className="hero-halo halo-two" />
          <div className="hero-bag"><span className="bag-handle" /><b>SB</b><i>✦</i></div>
          <div className="floating-note"><span>YOUR DAY,</span><b>made easier.</b><small>Everyday shopping, simplified.</small></div>
          <div className="sparkle sparkle-one">✦</div><div className="sparkle sparkle-two">✳</div>
        </div>
      </section>}

      {activePage === 'home' && <section className="service-card" aria-labelledby="service-title">
        <div className="service-icon" aria-hidden="true">⌖</div>
        <div className="service-copy"><h2 id="service-title">Shopping in your area?</h2><p>Check delivery availability for your PIN code.</p></div>
        <form onSubmit={checkServiceability} className="service-form">
          <span aria-hidden="true">＋91</span>
          <input inputMode="numeric" autoComplete="postal-code" aria-label="6-digit PIN code" maxLength={6} placeholder="Enter 6-digit PIN" value={pincode} onChange={e => setPincode(e.target.value.replace(/\D/g, ''))} />
          <button type="submit">Check availability</button>
        </form>
      </section>}
      {notice && <div className="notice" role="status"><span>ⓘ</span><p>{notice}</p><button aria-label="Dismiss message" onClick={() => setNotice('')}>×</button></div>}

      <section id="catalogue" className="catalogue" style={{display: activePage === 'product' ? 'none' : undefined}}>
        <div className="section-heading">
          <div><p className="eyebrow">{activePage === 'home' ? 'PICKED FOR EVERYDAY' : 'THE FULL COLLECTION'}</p><h2>{activePage === 'home' ? 'Discover your favourites' : 'Shop all products'}<span>.</span></h2><p>{activePage === 'home' ? 'Bestsellers, new arrivals and products you recently viewed.' : 'Browse the complete live catalogue and choose the variant that suits you.'}</p></div>
          <div className="heading-tools">
            <div className={`api-status status-${apiState}`}><i />{apiState === 'connected' ? 'Live catalogue connected' : apiState === 'connecting' ? 'Connecting to catalogue' : apiState === 'unconfigured' ? 'API setup required' : 'Catalogue unavailable'}</div>
          </div>
        </div>

        {activePage === 'home' && products.length > 0 && (
          <div className="home-discovery">
            <section className="discovery-section" aria-labelledby="bestsellers-title">
              <div className="discovery-heading">
                <div>
                  <p className="eyebrow">CUSTOMER FAVOURITES</p>
                  <h2 id="bestsellers-title">Bestsellers<span>.</span></h2>
                  <p>Products customers are choosing most.</p>
                </div>
                <span className="discovery-icon">★</span>
              </div>
              {bestsellerProducts.length > 0 ? (
                <div className="discovery-row">
                  {bestsellerProducts.slice(0, 8).map(product => (
                    <button className="discovery-product" key={product.id} onClick={() => openProduct(product)}>
                      <span className="discovery-product-art">SB<span>✦</span></span>
                      <b>{product.name}</b>
                      <small>{product.brand || product.category}</small>
                      <strong>{money(selectedVariant(product).price, selectedVariant(product).currency)}</strong>
                    </button>
                  ))}
                </div>
              ) : (
                <p className="discovery-empty">Bestsellers will appear here once sales or bestseller labels are available in the catalogue. We won't guess which products sell most.</p>
              )}
            </section>
            <section className="discovery-section" aria-labelledby="new-arrivals-title">
              <div className="discovery-heading">
                <div>
                  <p className="eyebrow">JUST LANDED</p>
                  <h2 id="new-arrivals-title">New arrivals<span>.</span></h2>
                  <p>Fresh additions marked as new in the product catalogue.</p>
                </div>
                <span className="discovery-icon">✧</span>
              </div>
              {newArrivalProducts.length > 0 ? (
                <div className="discovery-row">
                  {newArrivalProducts.slice(0, 8).map(product => (
                    <button className="discovery-product" key={product.id} onClick={() => openProduct(product)}>
                      <span className="discovery-product-art">NEW<span>✦</span></span>
                      <b>{product.name}</b>
                      <small>{product.brand || product.category}</small>
                      <strong>{money(selectedVariant(product).price, selectedVariant(product).currency)}</strong>
                    </button>
                  ))}
                </div>
              ) : (
                <p className="discovery-empty">New products will appear here when they are marked as new arrivals in the catalogue.</p>
              )}
            </section>
            {recentlyViewedProducts.length > 0 && (
              <section className="discovery-section" aria-labelledby="recent-title">
                <div className="discovery-heading">
                  <div>
                    <p className="eyebrow">PICK UP WHERE YOU LEFT OFF</p>
                    <h2 id="recent-title">Recently viewed<span>.</span></h2>
                    <p>Your recently opened products, saved on this device.</p>
                  </div>
                  <span className="discovery-icon">◷</span>
                </div>
                <div className="discovery-row">
                  {recentlyViewedProducts.map(product => (
                    <button className="discovery-product" key={product.id} onClick={() => openProduct(product)}>
                      <span className="discovery-product-art">SB<span>✦</span></span>
                      <b>{product.name}</b>
                      <small>{product.brand || product.category}</small>
                      <strong>{money(selectedVariant(product).price, selectedVariant(product).currency)}</strong>
                    </button>
                  ))}
                </div>
              </section>
            )}
          </div>
        )}
        {activePage === 'shop' && products.length > 0 && <div className="category-row" aria-label="Filter by category">
          {categories.map(category => <button key={category} className={selectedCategory === category ? 'category-chip active' : 'category-chip'} onClick={() => setSelectedCategory(category)}>{category}<span>{category === 'All' ? products.length : products.filter(p => p.category === category).length}</span></button>)}
        </div>}
        {loading && <div className="catalogue-state"><div className="loader" /><h3>Finding your everyday favourites</h3><p>Loading the latest catalogue information…</p></div>}
        {!loading && error && <div className="catalogue-state error-state"><div className="state-symbol">↻</div><h3>We couldn't load the catalogue</h3><p>{error}</p><button className="primary-link button-link" onClick={() => loadProducts(query, pincode)}>Try again <span>↗</span></button></div>}
        {activePage === 'shop' && !loading && !error && products.length === 0 && <div className="catalogue-state"><div className="state-symbol">✳</div><h3>Your next favourite starts here</h3><p>No published products were returned by the catalogue. When products are available, they will appear here automatically.</p><button className="secondary-button" onClick={() => loadProducts('', '')}>Refresh catalogue</button></div>}
        {activePage === 'shop' && !loading && !error && products.length > 0 && visibleProducts.length === 0 && <div className="catalogue-state"><div className="state-symbol">⌕</div><h3>No matches found</h3><p>Try another search or choose a different category.</p><button className="secondary-button" onClick={() => { setQuery(''); setSelectedCategory('All'); setBrandFilter(''); }}>Clear filters</button></div>}
        {activePage === 'shop' && !loading && !error && visibleProducts.length > 0 && <div id="catalogue-grid" className="product-grid">
          {visibleProducts.map(product => {
            const variant = selectedVariant(product);
            return <article className="product-card" key={product.id}>
              <button className="product-image" onClick={() => openProduct(product)} aria-label={`View details for ${product.name}`}>
                {variant.imageUrl ? <img src={variant.imageUrl} alt={product.name} loading="lazy" /> : <span className="image-monogram">SB<span>✦</span></span>}<span className="image-caption">{product.category}</span>
              </button>
              <div className="product-info">
                <div className="product-meta"><span>{product.brand || product.category}</span>{variant.stock > 0 && <span className="stock-badge">In stock</span>}</div>
                <button className="product-title" onClick={() => openProduct(product)}>{product.name}</button>
                {product.variants.length > 1 && <label className="variant-select">Choose option
                  <select aria-label={`Choose variant for ${product.name}`} value={String(variant.id)} onChange={e => setSelectedVariants(prev => ({ ...prev, [product.id]: e.target.value }))}>
                    {product.variants.map(v => <option key={v.id} value={String(v.id)}>{variantLabel(v)}</option>)}
                  </select>
                </label>}
                <div className="product-price"><strong>{money(variant.price, variant.currency)}</strong>{variant.mrp != null && Number(variant.mrp) > Number(variant.price) && <del>{money(variant.mrp, variant.currency)}</del>}</div>{variant.lowest30 != null && <div className="price-history">Lowest selling price · 30 days: <b>{money(variant.lowest30, variant.currency)}</b></div>}
                <div className="product-stock">{variant.stock > 0 ? `${variant.stock} available` : 'Availability not confirmed'}</div>
                <button className="add-cart-button" onClick={() => addToCart(product, variant)}>＋ Add to bag</button><button className="details-button" onClick={() => openProduct(product)}>View details <span>↗</span></button>
              </div>
            </article>;
          })}
        </div>}
        {activePage === 'shop' && products.length > 0 && <p className="catalogue-footnote">Showing real catalogue records only. Price and availability are subject to backend confirmation.</p>}
      </section>

      {activePage === 'home' && <section className="promise-grid" aria-label="Shopping principles">
        <div><span className="promise-icon">✦</span><div><b>Everyday essentials</b><p>A considered catalogue for the things you need.</p></div></div>
        <div><span className="promise-icon">⌖</span><div><b>Local availability</b><p>Delivery checks rely on actual service-area data.</p></div></div>
        <div><span className="promise-icon">✓</span><div><b>Clear product details</b><p>Prices and stock are sourced from the backend.</p></div></div>
      </section>}
    </main>}

    {activePage === 'product' && (
      <main className="product-page">
        {!routeProduct ? <section className="catalogue-state"><h2>Product not found</h2><p>This product is not in the current catalogue results.</p><button className="primary-link button-link" onClick={() => goShop('')}>Back to shop <span>↗</span></button></section> : (() => {
          const product = routeProduct; const variant = currentVariant; const attributes = variantAttributes(variant);
          const optionGroups = attributes.reduce((groups, attr) => { const key = attr.key.toLowerCase(); if (!groups[key]) groups[key] = { label: attr.key, options: [] }; if (!groups[key].options.some(v => String(v.value) === String(attr.value))) groups[key].options.push({ value: attr.value, variantId: variant.id }); return groups; }, {});
          return <ProductDisplayTemplate product={product} variant={variant} attributes={attributes} variantImage={variantImage} variantAttributes={variantAttributes} selectedVariants={selectedVariants} setSelectedVariants={setSelectedVariants} productQty={productQty} setProductQty={setProductQty} money={money} onBack={() => goShop('')} onAddToBag={(qty) => { for(let i=0;i<qty;i++) addToCart(product,variant); }} />;
          /* return <div className="product-detail-layout">
            <div className="product-detail-gallery">
              <div className="product-main-image">{variantImage ? <img src={variantImage} alt={product.name} /> : <div className="image-monogram">SB<span>✦</span></div>}</div>
              <div className="product-gallery-note">{variantImage ? 'Product image' : 'Product image not supplied by catalogue'}</div>
            </div>
            <section className="product-detail-info">
              <button className="product-back-link" onClick={() => goShop('')}>← Back to shop</button>
              <p className="eyebrow">{product.category}</p><h1>{product.name}</h1>
              {product.brand && <p className="product-detail-brand">Brand: <strong>{product.brand}</strong></p>}
              <div className="product-detail-price"><strong>{money(variant?.price, variant?.currency)}</strong>{variant?.mrp != null && Number(variant.mrp)>Number(variant.price) && <del>{money(variant.mrp,variant.currency)}</del>}</div>
              {variant?.lowest30 != null && <p className="price-history">Lowest selling price · 30 days: <b>{money(variant.lowest30,variant.currency)}</b></p>}
              <p className="product-detail-stock">{variant?.stock > 0 ? 'In stock · ' + variant.stock + ' available' : 'Availability not confirmed'}</p>
              {product.variants.length > 1 && <div className="product-variant-selectors"><h2>Choose options</h2>{[...new Set(product.variants.flatMap(v => variantAttributes(v).map(attr => attr.key)))].map(attributeName => {
                const values = [...new Map(product.variants.flatMap(v => variantAttributes(v).filter(attr => attr.key === attributeName).map(attr => [String(attr.value), { value: attr.value, variantId: v.id }]))).values()];
                if (!values.length) return null;
                const selectedAttr = variantAttributes(variant).find(attr => attr.key === attributeName);
                return <label key={attributeName}>{attributeName}<select aria-label={'Choose '+attributeName} value={String(selectedAttr?.value ?? '')} onChange={e => { const match = product.variants.find(v => variantAttributes(v).some(attr => attr.key === attributeName && String(attr.value) === e.target.value)); if (match) setSelectedVariants(prev => ({...prev,[product.id]:String(match.id)})); }}>{values.map(option => <option key={String(option.value)} value={String(option.value)}>{option.value}</option>)}</select></label>;
              })}</div>}
              {attributes.length > 0 && <div className="product-attributes"><h2>Selected option details</h2>{attributes.map((attr,i)=><div className="product-attribute-row" key={attr.key+'-'+i}><span>{attr.key}</span><strong>{attr.value}</strong></div>)}</div>}
              <div className="product-quantity-control"><span>Quantity</span><div><button type="button" onClick={() => setProductQty(q=>Math.max(1,q-1))} aria-label="Decrease quantity">−</button><strong>{productQty}</strong><button type="button" onClick={() => setProductQty(q=>Math.min(99,q+1))} aria-label="Increase quantity">＋</button></div></div>
              <button className="add-cart-button product-add-button" onClick={() => { for(let i=0;i<productQty;i++) addToCart(product,variant); }}>＋ Add to bag</button>
              <section className="product-description"><h2>Product details</h2><p>{product.description || 'Detailed product information has not been provided in the live catalogue yet.'}</p><div className="product-detail-facts"><div><span>Category</span><strong>{product.category || 'Not provided'}</strong></div><div><span>SKU</span><strong>{variant?.sku || 'Not provided'}</strong></div><div><span>Brand</span><strong>{product.brand || 'Not provided'}</strong></div>{attributes.map((attr,i)=><div key={attr.key+'-fact-'+i}><span>{attr.key}</span><strong>{attr.value}</strong></div>)}</div></section>
            </section>
          </div>; */
        })()}
      </main>
    )}

    <footer className="site-footer">
      <div className="footer-main">
        <div className="footer-brand-column">
          <a className="brand footer-brand" href="#home" aria-label="Super Bajaar home" onClick={e => { e.preventDefault(); navigate('/', 'home'); }}>
            <span className="brand-mark" aria-hidden="true"><svg viewBox="0 0 48 48" focusable="false" aria-hidden="true"><defs><linearGradient id="sbBagGradient" x1="0" y1="0" x2="1" y2="1"><stop offset="0%" stopColor="#5420d4"/><stop offset="55%" stopColor="#8129db"/><stop offset="100%" stopColor="#ff8739"/></linearGradient></defs><path d="M18 15V12a6 6 0 0 1 12 0v4" fill="none" stroke="#7fc4ff" strokeWidth="3.6" strokeLinecap="round"/><rect x="7" y="15" width="34" height="29" rx="7" fill="url(#sbBagGradient)"/><path d="M14 22c.7 6.2 4.7 10 10 10s9.3-3.8 10-10" fill="none" stroke="#fff" strokeWidth="3.2" strokeLinecap="round"/></svg></span>
            <span className="brand-word">Super <span>Bajaar</span><small>Your Everyday Super Store</small></span>
          </a>
          <p>Everyday essentials, thoughtfully brought together. A simpler way to shop for your day.</p>
        </div>
        <div className="footer-links">
          <div><h3>Shop</h3>
            <button onClick={() => navigate('/', 'home')}>Home</button>
            <button onClick={() => { goShop(''); }}>Shop all products</button>
            <button onClick={() => { setCartOpen(true); window.scrollTo({top:0,behavior:'smooth'}); }}>Shopping bag ({cartCount})</button>
          </div>
          <div><h3>Customer help</h3>
            <button onClick={() => { document.getElementById('service-title')?.scrollIntoView({behavior:'smooth',block:'center'}); }}>Delivery availability</button>
            <button onClick={() => setNotice('For product questions, please use the product details available in the catalogue. Customer support contact details will be added once confirmed.')}>Product help</button>
            <button onClick={() => setNotice('Online checkout and payment are not connected yet. Your shopping bag is saved on this device.')}>Orders & payments</button>
          </div>
          <div className="footer-trust"><h3>Our promise</h3><p><span>✓</span> Catalogue-led product details</p><p><span>✓</span> Clear pricing when provided</p><p><span>✓</span> Delivery checks by PIN code</p></div>
        </div>
        <a className="back-top" href="#home" onClick={e => { e.preventDefault(); window.scrollTo({top:0,behavior:'smooth'}); }}>Back to top ↑</a>
      </div>
      <div className="footer-bottom"><span>© {new Date().getFullYear()} Super Bajaar. All rights reserved.</span><span>Your Everyday Super Store</span><span>Made for everyday living <b>✦</b></span></div>
    </footer>

    {cartOpen && <div className="modal-backdrop" role="presentation" onMouseDown={e => { if (e.target === e.currentTarget) setCartOpen(false); }}>
      <section className="cart-modal" role="dialog" aria-modal="true" aria-labelledby="cart-title">
        <button className="modal-close" aria-label="Close bag" onClick={() => setCartOpen(false)}>×</button>
        <p className="eyebrow">YOUR SELECTION</p><h2 id="cart-title">Shopping bag ({cartCount})</h2>
        {!cart.length ? <p className="cart-note">Your bag is empty. Add something from the catalogue.</p> : <>
          <div className="cart-items">{cart.map(item => <article className="cart-item" key={item.key}>
            <div><b>{item.name}</b><small>{item.option}</small><strong>{money(item.price, item.currency)}</strong></div>
            <div className="quantity-control"><button onClick={() => changeCartQuantity(item.key,-1)} aria-label="Decrease quantity">−</button><span>{item.quantity}</span><button onClick={() => changeCartQuantity(item.key,1)} aria-label="Increase quantity">＋</button></div>
            <button className="remove-item" onClick={() => setCart(previous => previous.filter(row => row.key !== item.key))}>Remove</button>
          </article>)}</div>
          <div className="cart-total"><span>Subtotal</span><strong>{money(cartTotal)}</strong></div>
          <p className="cart-note">Bag saved on this device. Online checkout and payment are not connected yet.</p>
        </>}
        <button className="primary-link button-link" onClick={() => setCartOpen(false)}>Continue shopping <span>↗</span></button>
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
  const [editing, setEditing] = useState(null);
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
      const target = editing ? `/admin/products/${editing.product_id}/variants/${editing.variant_id}` : '/admin/products';
      const response = await fetch(endpoint(target),{method:editing?'PUT':'POST',headers:{'Content-Type':'application/json',Authorization:'Bearer '+token},body:JSON.stringify(payload)});
      const data = await response.json().catch(()=>({}));
      if(!response.ok) {
        if(response.status === 401) {
          setToken('');
          setItems([]);
          try { sessionStorage.removeItem('sb-admin-token'); } catch {}
          throw new Error('Your admin session has expired. Please sign in again.');
        }
        throw new Error(data.detail || 'Could not save product');
      }
      setMessage(editing ? 'Product updated successfully.' : 'Product saved successfully. Active products are eligible for storefront display. No stock was added.');
      setEditing(null);
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
      {tab==='add' ? <form className="admin-product-form" onSubmit={saveProduct}><div className="admin-form-heading"><h2>{editing?'Edit product':'Product information'}</h2><p>Required fields are marked with *.</p></div>
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
        <div className="admin-form-actions"><button type="button" className="secondary-button" onClick={()=>{setEditing(null);setForm({name:'',product_code:'',sku:'',brand:'',category:'Grocery & Staples',description:'',selling_price:'',mrp:'',currency:'INR',active:true});}}>Clear form</button>{editing&&<button type="button" className="secondary-button" onClick={()=>{setEditing(null);setForm({name:'',product_code:'',sku:'',brand:'',category:'Grocery & Staples',description:'',selling_price:'',mrp:'',currency:'INR',active:true});}}>Cancel edit</button>}<button className="add-cart-button" disabled={busy}>{busy?(editing?'Updating…':'Saving…'):(editing?'Update product':'Save product')}</button></div>
      </form> : <section className="admin-product-list"><div className="admin-form-heading"><h2>All products</h2><button className="secondary-button" onClick={()=>loadAdminProducts()}>Refresh list</button></div>{items.length===0?<p>No product records returned.</p>:<div className="admin-table-wrap"><table><thead><tr><th>Product</th><th>SKU</th><th>Category</th><th>Selling price</th><th>Product status</th><th>Variant status</th><th>Visibility</th><th>Action</th></tr></thead><tbody>{items.map(item=><tr key={item.variant_id}><td><b>{item.name}</b><small>{item.product_code}</small></td><td>{item.sku}</td><td>{item.category||'—'}</td><td>{money(item.selling_price,item.currency)}</td><td>{item.product_status}</td><td>{item.variant_status}</td><td>{item.product_status==='active'&&item.variant_status==='active'?'Storefront eligible':'Not eligible'}</td><td><button type="button" className="secondary-button" onClick={()=>{setEditing({product_id:item.product_id,variant_id:item.variant_id});setForm({name:item.name||'',product_code:item.product_code||'',sku:item.sku||'',brand:item.brand||'',category:item.category||'General',description:item.description||'',selling_price:item.selling_price==null?'':String(item.selling_price),mrp:item.mrp==null?'':String(item.mrp),currency:item.currency||'INR',active:item.product_status==='active'&&item.variant_status==='active'});setTab('add');setMessage('Editing '+item.name);}}>Edit</button></td></tr>)}</tbody></table></div>}</section>}
    </main>}
  </div>;
}


function Root() { return window.location.pathname.startsWith('/admin') ? <AdminPanel /> : <App />; }

createRoot(document.getElementById('root')).render(<Root />);
