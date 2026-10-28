import { useEffect, useMemo, useState } from "react";
import { apiRequest } from "../services/api.js";
import "./storefront.css";

const art = [
  { icon: "🥑", tone: "green", detail: "Everyday essentials" },
  { icon: "👕", tone: "lavender", detail: "Style for everyone" },
  { icon: "🎧", tone: "blue", detail: "Smart picks, every day" },
  { icon: "🧴", tone: "peach", detail: "Care for every day" },
  { icon: "🍊", tone: "yellow", detail: "Freshness for your home" },
  { icon: "🐾", tone: "pink", detail: "Little things for pets" },
];
const money = value => new Intl.NumberFormat("en-IN", { style: "currency", currency: "INR", maximumFractionDigits: 2 }).format(Number(value || 0));

export default function Storefront() {
  const [categories, setCategories] = useState([]);
  const [products, setProducts] = useState([]);
  const [variants, setVariants] = useState([]);
  const [categoryId, setCategoryId] = useState("");
  const [search, setSearch] = useState("");
  const [cart, setCart] = useState([]);
  const [customer, setCustomer] = useState({ name: "", phone: "", pin: "" });
  const [loading, setLoading] = useState(true);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [order, setOrder] = useState(null);

  useEffect(() => {
    let active = true;
    Promise.all([
      apiRequest("/catalogue/categories"),
      apiRequest("/catalogue/products"),
      apiRequest("/catalogue/variants?limit=500"),
    ]).then(([c, p, v]) => {
      if (!active) return;
      setCategories(c.items || []);
      setProducts(p.items || []);
      setVariants(v.items || []);
      setError("");
    }).catch(e => { if (active) setError(e.message || "Unable to load the live catalogue."); })
      .finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, []);

  const productById = useMemo(() => new Map(products.map(p => [Number(p.id), p])), [products]);
  const visibleVariants = useMemo(() => {
    const term = search.trim().toLowerCase();
    return variants.filter(v => {
      const product = productById.get(Number(v.product_id));
      if (!product || (categoryId && String(product.category_id || "") !== categoryId)) return false;
      return !term || [v.product_name, product.name, v.sku, product.brand].some(x => String(x || "").toLowerCase().includes(term));
    });
  }, [variants, productById, categoryId, search]);
  const total = cart.reduce((sum, line) => sum + Number(line.selling_price || 0) * line.quantity, 0);
  const addToCart = variant => {
    setCart(old => {
      const found = old.find(line => line.id === variant.id);
      return found ? old.map(line => line.id === variant.id ? { ...line, quantity: Math.min(100000, line.quantity + 1) } : line)
        : [...old, { ...variant, quantity: 1 }];
    });
    setNotice("");
  };
  const setQuantity = (id, raw) => {
    const quantity = Math.floor(Number(raw));
    setCart(old => quantity <= 0 ? old.filter(line => line.id !== id)
      : old.map(line => line.id === id ? { ...line, quantity: Math.min(100000, quantity) } : line));
  };

  async function checkout(event) {
    event.preventDefault();
    if (!cart.length) { setError("Add at least one item to your basket."); return; }
    setSubmitting(true); setError(""); setNotice(""); setOrder(null);
    try {
      const created = await apiRequest("/orders", {
        method: "POST",
        skipAuth: true,
        body: JSON.stringify({
          channel: "website",
          customer_name: customer.name.trim(),
          customer_phone: customer.phone.trim() || null,
          delivery_pin: customer.pin.trim() || null,
          notes: "Website checkout",
          lines: cart.map(line => ({ variant_id: line.id, quantity: line.quantity })),
        }),
      });
      setOrder(created);
      setCart([]);
      setNotice("Your order has been placed. Online payment is not enabled yet.");
    } catch (e) {
      setError(e.message || "Checkout failed. Your basket has been kept so you can retry.");
    } finally { setSubmitting(false); }
  }

  return <main className="storefront">
    <div className="storefront-promo">Your everyday favourites, all in one place <span>✦</span> Shop smarter with Super Bajaar</div>
    <header className="storefront-header">
      <a className="storefront-brand" href="/" aria-label="Super Bajaar home"><span className="storefront-logo">S</span><span><strong>Super Bajaar</strong><small>Your Everyday Super Store</small></span></a>
      <nav className="storefront-nav" aria-label="Main navigation"><a href="#categories">Categories</a><a href="#products">Shop</a><a href="#why-us">Why Super Bajaar</a></nav>
      <div className="storefront-actions"><a className="storefront-admin-link" href="/admin">Admin login</a><a className="storefront-cart" href="#basket">Basket ({cart.reduce((n, line) => n + line.quantity, 0)}) ↗</a></div>
    </header>
    <section className="storefront-hero">
      <div className="storefront-hero-copy"><span className="storefront-kicker"><i /> YOUR EVERYDAY SUPER STORE</span><h1>Everyday shopping.<br /><em>Extraordinary</em> easy.</h1><p>From fresh finds to daily essentials, discover more of what you need in one colourful, convenient place.</p><a className="storefront-primary" href="#products">Shop live catalogue <span>→</span></a><div className="storefront-trust"><span>✦ Thoughtfully picked</span><span>✦ Made for everyday</span></div></div>
      <div className="storefront-hero-art" aria-label="Colourful shopping bags and everyday products" role="img"><div className="art-sun" /><div className="art-orbit orbit-one" /><div className="art-orbit orbit-two" /><div className="art-spark spark-one">✦</div><div className="art-spark spark-two">✳</div><div className="art-bag bag-purple"><span>S</span></div><div className="art-bag bag-orange"><span>♥</span></div><div className="art-box"><span>GOOD</span><strong>THINGS</strong></div><div className="art-leaf leaf-one">✦</div><div className="art-leaf leaf-two">✿</div><div className="art-caption">A little joy in every basket</div></div>
    </section>
    <section className="storefront-categories" id="categories">
      <div className="storefront-section-heading"><div><span className="storefront-kicker">FIND YOUR FAVOURITES</span><h2>Shop by category</h2></div><span className="storefront-heading-note">Choose a category to filter products.</span></div>
      <div className="storefront-category-grid">
        <button type="button" className={"storefront-category storefront-category-all " + (!categoryId ? "is-selected" : "")} onClick={() => setCategoryId("")}><span className="storefront-category-art tone-lavender"><span>✦</span><i>↗</i></span><strong>All categories</strong><small>Browse everything</small></button>
        {categories.map((category, index) => {
          const tile = art[index % art.length];
          return <button type="button" className={"storefront-category " + (String(category.id) === categoryId ? "is-selected" : "")} key={category.id} onClick={() => { setCategoryId(String(category.id)); document.getElementById("products")?.scrollIntoView({ behavior: "smooth" }); }}>
            <span className={"storefront-category-art tone-" + tile.tone}><span>{tile.icon}</span><i>↗</i></span><strong>{category.name}</strong><small>{category.description || tile.detail}</small>
          </button>;
        })}
      </div>
    </section>
    <section className="storefront-products" id="products">
      <div className="storefront-section-heading"><div><span className="storefront-kicker">READY WHEN YOU ARE</span><h2>{categoryId ? (categories.find(c => String(c.id) === categoryId)?.name || "Products") : "Shop products"}</h2></div><span className="storefront-heading-note">{visibleVariants.length} variants available</span></div>
      <label className="storefront-search">Search products or SKU<input value={search} onChange={e => setSearch(e.target.value)} placeholder="Try a product name or SKU" /></label>
      {error && <p className="storefront-alert" role="alert">{error}</p>}
      {loading ? <p className="storefront-empty">Loading live products…</p> : visibleVariants.length ? <div className="storefront-product-grid">{visibleVariants.map(variant => {
        const product = productById.get(Number(variant.product_id));
        const index = categories.findIndex(c => String(c.id) === String(product?.category_id));
        return <article className="storefront-product-card" key={variant.id}><div className="storefront-product-art"><span>{art[(index < 0 ? 0 : index) % art.length].icon}</span></div><small>{product?.brand || product?.name || "Super Bajaar"}</small><h3>{product?.name || variant.product_name || variant.sku}</h3><p className="storefront-sku">{variant.sku}</p><strong>{money(variant.selling_price)}</strong><button type="button" className="storefront-add" onClick={() => addToCart(variant)}>Add to basket +</button></article>;
      })}</div> : <p className="storefront-empty">{error ? "The live catalogue could not be loaded." : "No active products are available in this category yet."}</p>}
    </section>
    <section className="storefront-checkout" id="basket">
      <div><span className="storefront-kicker">YOUR BASKET</span><h2>Checkout</h2><p>Prices and order totals are calculated by the server. Online payment collection is not enabled yet.</p>{order && <p className="storefront-order-success" role="status">Order placed: <strong>{order.order_number}</strong> · {money(order.total)}</p>}</div>
      <div className="storefront-basket-lines">{cart.length ? cart.map(line => <div className="storefront-basket-line" key={line.id}><div><strong>{line.product_name || line.sku}</strong><small>{line.sku} · {money(line.selling_price)}</small></div><label>Qty<input type="number" min="0" max="100000" step="1" value={line.quantity} onChange={e => setQuantity(line.id, e.target.value)} /></label><strong>{money(line.selling_price * line.quantity)}</strong><button type="button" aria-label={"Remove " + line.sku} onClick={() => setCart(old => old.filter(x => x.id !== line.id))}>×</button></div>) : <p className="storefront-empty">Your basket is empty. Add a product to begin.</p>}<div className="storefront-basket-total"><span>Subtotal</span><strong>{money(total)}</strong></div>
        <form className="storefront-checkout-form" onSubmit={checkout}><label>Full name<input required minLength="1" maxLength="200" value={customer.name} onChange={e => setCustomer(v => ({ ...v, name: e.target.value }))} /></label><label>Phone (optional)<input maxLength="20" value={customer.phone} onChange={e => setCustomer(v => ({ ...v, phone: e.target.value }))} /></label><label>Delivery PIN (optional)<input inputMode="numeric" pattern="[0-9]{6}" maxLength="6" value={customer.pin} onChange={e => setCustomer(v => ({ ...v, pin: e.target.value }))} /></label><button type="submit" className="storefront-primary" disabled={submitting || !cart.length}>{submitting ? "Placing order…" : "Place order"}</button></form>
        {notice && <p className="storefront-order-success" role="status">{notice}</p>}{error && <p className="storefront-alert" role="alert">{error}</p>}
      </div>
    </section>
    <section className="storefront-benefits" id="why-us"><div><span className="benefit-icon">✦</span><strong>Everyday essentials</strong><small>All your regular picks in one place.</small></div><div><span className="benefit-icon">♡</span><strong>Made for your routine</strong><small>A simpler way to shop for home and family.</small></div><div><span className="benefit-icon">✳</span><strong>Discover something new</strong><small>Explore categories for every kind of day.</small></div></section>
    <footer className="storefront-footer"><a className="storefront-brand" href="/"><span className="storefront-logo">S</span><span><strong>Super Bajaar</strong><small>Your Everyday Super Store</small></span></a><span>Everyday made a little brighter.</span><a href="/admin">Business admin ↗</a></footer>
  </main>;
}
