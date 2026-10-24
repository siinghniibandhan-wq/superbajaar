import React, { useEffect, useMemo, useState } from 'react';
import { createRoot } from 'react-dom/client';
import './styles.css';

const API_BASE = (import.meta.env.VITE_API_BASE_URL || '').replace(/\/$/, '');

function App() {
  const [products, setProducts] = useState([]);
  const [categories, setCategories] = useState(['All']);
  const [category, setCategory] = useState('All');
  const [search, setSearch] = useState('');
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  async function loadCatalogue() {
    setLoading(true);
    setError('');
    try {
      const response = await fetch(`${API_BASE}/api/products?limit=100`, { headers: { Accept: 'application/json' } });
      if (!response.ok) throw new Error(`Catalogue request failed (${response.status})`);
      const payload = await response.json();
      const rows = Array.isArray(payload) ? payload : (payload.items || payload.products || []);
      setProducts(rows);
      let names = [...new Set(rows.map((p) => p.category).filter(Boolean))].sort((a, b) => a.localeCompare(b));
      try {
        const categoryResponse = await fetch(`${API_BASE}/api/categories`, { headers: { Accept: 'application/json' } });
        if (categoryResponse.ok) {
          const categoryPayload = await categoryResponse.json();
          const savedNames = (categoryPayload.items || []).map((item) => item.name).filter(Boolean);
          if (savedNames.length) names = [...new Set(savedNames)].sort((a, b) => a.localeCompare(b));
        }
      } catch { /* Product categories remain a fallback if the category endpoint is unavailable. */ }
      setCategories(['All', ...names]);
    } catch (e) {
      setError('We could not load the live catalogue. Please try again shortly.');
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    loadCatalogue();
    const refresh = () => loadCatalogue();
    window.addEventListener('focus', refresh);
    return () => window.removeEventListener('focus', refresh);
  }, []);

  const visibleProducts = useMemo(() => products.filter((p) => {
    const matchesCategory = category === 'All' || p.category === category;
    const term = search.trim().toLowerCase();
    const matchesSearch = !term || [p.name, p.brand, p.description, p.category].some((v) => String(v || '').toLowerCase().includes(term));
    return matchesCategory && matchesSearch;
  }), [products, category, search]);

  return <div className="app-shell">
    <header className="topbar"><a className="brand" href="#top" aria-label="Super Bajaar home"><span className="brand-mark">S</span><span>Super <b>Bajaar</b><small>Your Everyday Super Store</small></span></a><a className="admin-link" href="#catalogue">Shop</a></header>
    <main id="top">
      <section className="hero"><div className="hero-copy"><span className="eyebrow">EVERYDAY ESSENTIALS, MADE EASY</span><h1>Your everyday<br/><em>super store.</em></h1><p>Find what you need, all in one place.</p><a className="hero-button" href="#catalogue">Explore products <span aria-hidden="true">→</span></a></div><div className="hero-art" aria-hidden="true"><div className="art-circle circle-one"></div><div className="art-circle circle-two"></div><div className="basket">🛍️</div><span className="spark spark-one">✦</span><span className="spark spark-two">✳</span></div></section>
      <section id="catalogue" className="catalogue"><div className="section-heading"><div><span className="eyebrow">THE COLLECTION</span><h2>Shop the catalogue</h2></div><span className="count">{loading ? 'Loading…' : `${visibleProducts.length} products`}</span></div>
        <div className="catalogue-tools"><label className="search-box"><span aria-hidden="true">⌕</span><input value={search} onChange={(e) => setSearch(e.target.value)} placeholder="Search products" aria-label="Search products"/></label><div className="category-list" aria-label="Product categories">{categories.map((name) => <button key={name} className={category === name ? 'category active' : 'category'} onClick={() => setCategory(name)}>{name}</button>)}</div></div>
        {loading ? <div className="state-card"><span className="loader"></span><p>Loading products from the live catalogue…</p></div> : error ? <div className="state-card"><h3>Catalogue unavailable</h3><p>{error}</p><button className="retry-button" onClick={loadCatalogue}>Try again</button></div> : visibleProducts.length === 0 ? <div className="state-card"><div className="empty-icon">⌕</div><h3>{products.length ? 'No matching products' : 'Your catalogue will appear here'}</h3><p>{products.length ? 'Try another search or category.' : 'Products saved in your connected database will appear here. No sample products are added.'}</p></div> : <div className="product-grid">{visibleProducts.map((p, i) => <article className="product-card" key={p.variant_id || p.id || p.product_id || p.sku || i}><div className="product-image">{(p.image_url || p.imageUrl || p.image) ? <img src={p.image_url || p.imageUrl || p.image} alt={p.name || 'Product'} loading="lazy"/> : <div className="image-placeholder"><span>SB</span></div>}{p.category && <span className="product-category">{p.category}</span>}</div><div className="product-info"><h3>{p.name || 'Product'}</h3>{p.brand && <p className="brand-name">{p.brand}</p>}<div className="price-row"><strong>{new Intl.NumberFormat('en-IN',{style:'currency',currency:p.currency || 'INR',maximumFractionDigits:2}).format(Number(p.selling_price ?? p.price ?? 0))}</strong>{p.mrp && Number(p.mrp)>Number(p.selling_price ?? p.price ?? 0) && <del>{new Intl.NumberFormat('en-IN',{style:'currency',currency:p.currency || 'INR',maximumFractionDigits:2}).format(Number(p.mrp))}</del>}</div></div></article>)}</div>}
      </section>
    </main><footer><a className="brand footer-brand" href="#top"><span className="brand-mark">S</span><span>Super <b>Bajaar</b><small>Your Everyday Super Store</small></span></a><p>Everyday shopping, made simpler.</p></footer>
  </div>;
}

createRoot(document.getElementById('root')).render(<React.StrictMode><App /></React.StrictMode>);
