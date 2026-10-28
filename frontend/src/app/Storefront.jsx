import { useEffect, useMemo, useState } from "react";
import { Heart, ShoppingBag, Search, Sparkles, Flame, Clock3, ChevronLeft, ChevronRight } from "lucide-react";
import { apiRequest } from "../services/api.js";
import "./storefront.css";

const categoryOrder = [
  "Grocery", "Fresh Daily", "Fashion", "Personal Care", "Electronics",
  "Home Appliances", "Pet Care", "Gifting", "Pooja Essentials",
  "Automobiles", "Toys & Sports", "Pharmacy",
];
const categoryArt = {
  "Grocery": { icon: "🛒", tone: "lavender", detail: "Everyday groceries" },
  "Fresh Daily": { icon: "🥬", tone: "green", detail: "Fresh picks, every day" },
  "Fashion": { icon: "👕", tone: "peach", detail: "Style for everyone" },
  "Personal Care": { icon: "🧴", tone: "blue", detail: "Care for every day" },
  "Electronics": { icon: "🎧", tone: "lavender", detail: "Smart picks, every day" },
  "Home Appliances": { icon: "🏠", tone: "yellow", detail: "For a happier home" },
  "Pet Care": { icon: "🐾", tone: "green", detail: "Little things for pets" },
  "Gifting": { icon: "🎁", tone: "peach", detail: "Gifts for every moment" },
  "Pooja Essentials": { icon: "🪔", tone: "yellow", detail: "For your traditions" },
  "Automobiles": { icon: "🚗", tone: "blue", detail: "Everyday auto essentials" },
  "Toys & Sports": { icon: "⚽", tone: "lavender", detail: "Play, move, explore" },
  "Pharmacy": { icon: "💊", tone: "green", detail: "Health and wellness" },
};
const art = categoryOrder.map(name => categoryArt[name]);
const money = value => new Intl.NumberFormat("en-IN", { style: "currency", currency: "INR", maximumFractionDigits: 2 }).format(Number(value || 0));

export default function Storefront() {
  const [categories, setCategories] = useState([]);
  const [products, setProducts] = useState([]);
  const [variants, setVariants] = useState([]);
  const [categoryId, setCategoryId] = useState("");
  const [routePath, setRoutePath] = useState(() => window.location.pathname.replace(/\/+$/, "") || "/");
  const [search, setSearch] = useState("");
  const [cart, setCart] = useState([]);
  const [wishlist, setWishlist] = useState(() => { try { return JSON.parse(window.localStorage.getItem("sb-wishlist") || "[]").filter(Number.isFinite); } catch { return []; } });
  const [recentlyViewed, setRecentlyViewed] = useState([]);
  const [customer, setCustomer] = useState({ name: "", phone: "", pin: "" });
  const [loading, setLoading] = useState(true);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [order, setOrder] = useState(null);

  useEffect(() => {
    try { setRecentlyViewed(JSON.parse(sessionStorage.getItem("sb-recently-viewed") || "[]")); } catch { setRecentlyViewed([]); }
  }, []);

  useEffect(() => {
    try { window.localStorage.setItem("sb-wishlist", JSON.stringify(wishlist)); } catch { /* Wishlist remains usable for this session if storage is unavailable. */ }
  }, [wishlist]);

  useEffect(() => {
    const syncPath = () => setRoutePath(window.location.pathname.replace(/\/+$/, "") || "/");
    window.addEventListener("popstate", syncPath);
    return () => window.removeEventListener("popstate", syncPath);
  }, []);

  useEffect(() => {
    const timer = window.setInterval(() => {
      if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) return;
      document.querySelectorAll(".storefront-carousel-track").forEach(track => {
        if (track.matches(":hover") || track.matches(":focus-within")) return;
        const card = track.querySelector(".storefront-product-card");
        if (!card) return;
        const styles = window.getComputedStyle(track);
        const gap = Number.parseFloat(styles.columnGap || styles.gap || "0") || 0;
        const step = card.getBoundingClientRect().width + gap;
        const max = track.scrollWidth - track.clientWidth;
        if (max <= 2) return;
        if (track.scrollLeft >= max - 8) track.scrollTo({ left: 0, behavior: "smooth" });
        else track.scrollBy({ left: step, behavior: "smooth" });
      });
    }, 5000);
    return () => window.clearInterval(timer);
  }, []);

  useEffect(() => {
    let active = true;
    const endpoints = [
      ["categories", () => apiRequest("/catalogue/categories", { skipAuth: true })],
      ["products", () => apiRequest("/catalogue/products", { skipAuth: true })],
      ["variants", () => apiRequest("/catalogue/variants?limit=500", { skipAuth: true })],
    ];
    // Load each resource independently: one failing request must not discard
    // successful catalogue data or hide which endpoint actually failed.
    Promise.allSettled(endpoints.map(([, load]) => load())).then(results => {
      if (!active) return;
      const failures = [];
      results.forEach((result, index) => {
        const [name] = endpoints[index];
        if (result.status === "rejected") {
          failures.push(`${name}: ${result.reason?.message || "request failed"}`);
          return;
        }
        const items = Array.isArray(result.value?.items) ? result.value.items : [];
        if (name === "categories") setCategories(items);
        if (name === "products") setProducts(items);
        if (name === "variants") setVariants(items);
      });
      setError(failures.length ? `Catalogue API issue — ${failures.join(" | ")}` : "");
    }).finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, []);

  const productById = useMemo(() => new Map(products.map(p => [Number(p.id), p])), [products]);
  const categorySlug = name => String(name || "").trim().toLowerCase().replace(/&/g, "and").replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "");
  const routeSlug = routePath.startsWith("/category/") ? routePath.slice("/category/".length).split("/")[0] : "";
  const routeCategoryName = categoryOrder.find(name => categorySlug(name) === routeSlug)
    || categories.find(category => categorySlug(category.name) === routeSlug)?.name || "";
  const isCategoryPage = Boolean(routeSlug);
  const isWishlistPage = routePath === "/wishlist";
  const openCategory = category => {
    const slug = categorySlug(category.name);
    window.history.pushState({}, "", "/category/" + slug);
    setRoutePath("/category/" + slug);
    setCategoryId(String(category.id));
    setSearch("");
    window.scrollTo({ top: 0, behavior: "smooth" });
  };
  const openShopHome = () => {
    window.history.pushState({}, "", "/");
    setRoutePath("/");
    setCategoryId("");
    setSearch("");
    window.scrollTo({ top: 0, behavior: "smooth" });
  };
  const openWishlist = () => {
    window.history.pushState({}, "", "/wishlist");
    setRoutePath("/wishlist");
    setCategoryId("");
    setSearch("");
    window.scrollTo({ top: 0, behavior: "smooth" });
  };
  const orderedCategories = useMemo(() => {
    const rank = new Map(categoryOrder.map((name, index) => [name.toLowerCase(), index]));
    return [...categories].sort((a, b) => {
      const ai = rank.get(String(a.name || "").trim().toLowerCase()) ?? categoryOrder.length;
      const bi = rank.get(String(b.name || "").trim().toLowerCase()) ?? categoryOrder.length;
      return ai - bi || String(a.name || "").localeCompare(String(b.name || ""));
    });
  }, [categories]);
  const displayCategories = useMemo(() => {
    const byName = new Map(categories.map(c => [String(c.name || "").trim().toLowerCase(), c]));
    const approved = categoryOrder.map(name => byName.get(name.toLowerCase()) || { id: "name:" + name, name, description: categoryArt[name].detail });
    const approvedNames = new Set(categoryOrder.map(name => name.toLowerCase()));
    return [...approved, ...orderedCategories.filter(c => !approvedNames.has(String(c.name || "").trim().toLowerCase()))];
  }, [categories, orderedCategories]);
  const visibleVariants = useMemo(() => {
    const term = search.trim().toLowerCase();
    return variants.filter(v => {
      const product = productById.get(Number(v.product_id));
      if (!product) return false;
      if (categoryId || routeCategoryName) {
        const selected = displayCategories.find(c => String(c.id) === categoryId)
          || displayCategories.find(c => String(c.name || "").trim().toLowerCase() === String(routeCategoryName).trim().toLowerCase());
        const productCategoryName = product.category_name || product.category || categories.find(c => String(c.id) === String(product.category_id))?.name || "";
        const targetName = routeCategoryName || selected?.name || "";
        const matches = (selected && String(product.category_id || "") === String(selected.id))
          || (targetName && String(productCategoryName).trim().toLowerCase() === String(targetName).trim().toLowerCase());
        if (!matches) return false;
      }
      return !term || [v.product_name, product.name, v.sku, product.brand].some(x => String(x || "").toLowerCase().includes(term));
    });
  }, [variants, productById, categoryId, routeCategoryName, search, displayCategories]);
  const displayedVariants = isWishlistPage ? visibleVariants.filter(v => wishlist.includes(v.id)) : visibleVariants;
  const rememberViewed = variant => {
    const entry = { variantId: variant.id, productId: variant.product_id, viewedAt: Date.now() };
    setRecentlyViewed(old => {
      const next = [entry, ...old.filter(item => Number(item.variantId) !== Number(variant.id))].slice(0, 12);
      try { sessionStorage.setItem("sb-recently-viewed", JSON.stringify(next)); } catch {}
      return next;
    });
  };
  const newArrivals = useMemo(() => [...visibleVariants].map(v => {
    const p = productById.get(Number(v.product_id)) || {};
    return { ...v, _created: Date.parse(p.created_at || p.created_on || p.createdAt || v.created_at || "") || 0 };
  }).filter(v => v._created > 0).sort((a,b) => b._created-a._created).slice(0,8), [visibleVariants, productById]);
  const bestSellers = useMemo(() => [...visibleVariants].map(v => {
    const p = productById.get(Number(v.product_id)) || {};
    return { ...v, _sales: Number(v.units_sold ?? v.sold_count ?? v.sales_count ?? p.units_sold ?? p.sold_count ?? p.sales_count ?? p.order_count ?? 0) };
  }).filter(v => v._sales > 0).sort((a,b) => b._sales-a._sales).slice(0,8), [visibleVariants, productById]);
  const recentVariants = useMemo(() => recentlyViewed.map(item => variants.find(v => Number(v.id) === Number(item.variantId))).filter(Boolean).slice(0,8), [recentlyViewed, variants]);
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

  function renderProductCard(variant) {
    const product = productById.get(Number(variant.product_id));
    const categoryName = product?.category_name || product?.category || orderedCategories.find(c => String(c.id) === String(product?.category_id))?.name;
    const tile = categoryArt[categoryName] || art[0];
    const saved = wishlist.includes(variant.id);
    return <article className="storefront-product-card" key={variant.id}>
      <div className="storefront-product-art"><span>{tile.icon}</span><button type="button" className={"storefront-wishlist " + (saved ? "is-saved" : "")} aria-label={(saved ? "Remove from" : "Add to") + " wishlist: " + (product?.name || variant.sku)} aria-pressed={saved} onClick={() => setWishlist(old => old.includes(variant.id) ? old.filter(id => id !== variant.id) : [...old, variant.id])}><Heart size={19} strokeWidth={1.9} fill={saved ? "currentColor" : "none"} /></button></div>
      <small>{product?.brand || product?.name || "Super Bajaar"}</small>
      <h3><button type="button" className="storefront-product-title" onClick={() => rememberViewed(variant)}>{product?.name || variant.product_name || variant.sku}</button></h3>
      <p className="storefront-sku">{variant.sku}</p><strong>{money(variant.selling_price)}</strong>
      <button type="button" className="storefront-add" onClick={() => addToCart(variant)}><ShoppingBag size={17} strokeWidth={2} /> Add to basket</button>
    </article>;
  }
  function renderDiscoverySection(title, subtitle, items, emptyText, icon) {
    const trackId = "carousel-" + title.toLowerCase().replace(/[^a-z0-9]+/g, "-");
    const moveTrack = direction => {
      const track = document.getElementById(trackId);
      const card = track?.querySelector(".storefront-product-card");
      if (!track || !card) return;
      const styles = window.getComputedStyle(track);
      const gap = Number.parseFloat(styles.columnGap || styles.gap || "0") || 0;
      track.scrollBy({ left: direction * (card.getBoundingClientRect().width + gap), behavior: "smooth" });
    };
    return <section className="storefront-discovery-section" id={title === "Best Sellers" ? "deals" : undefined}>
      <div className="storefront-section-heading storefront-carousel-heading">
        <div><span className="storefront-kicker">{icon} DISCOVER MORE</span><h2>{title}</h2><p>{subtitle}</p></div>
        <div className="storefront-carousel-controls" aria-label={title + " carousel controls"}>
          <button type="button" aria-label={"Previous " + title} onClick={() => moveTrack(-1)}><ChevronLeft size={20} /></button>
          <button type="button" aria-label={"Next " + title} onClick={() => moveTrack(1)}><ChevronRight size={20} /></button>
        </div>
      </div>
      {items.length ? <div className="storefront-carousel-track" id={trackId} tabIndex={0} aria-label={title + " products"}>{items.map(renderProductCard)}</div> : <p className="storefront-empty">{emptyText}</p>}
    </section>;
  }

  return <main className="storefront">
    <div className="storefront-promo">Your everyday favourites, all in one place <span>✦</span> Shop smarter with Super Bajaar</div>
    <header className="storefront-header">
      <a className="storefront-brand" href="/" onClick={event => { event.preventDefault(); openShopHome(); }} aria-label="Super Bajaar home"><span className="storefront-logo">S</span><span><strong>Super Bajaar <span className="storefront-crown" aria-hidden="true">♛</span></strong><small>Your Everyday Super Store</small></span></a>
      <label className="storefront-header-search"><span className="sr-only">Search products</span><input value={search} onChange={e => setSearch(e.target.value)} placeholder="Search groceries, fashion, electronics…" /><Search aria-hidden="true" size={19} /></label>
      <div className="storefront-actions"><span className="storefront-delivery"><small>Deliver to</small><strong>India ▾</strong></span><a className="storefront-icon-action" href="/wishlist" aria-label={`Open wishlist, ${wishlist.length} saved`} onClick={event => { event.preventDefault(); openWishlist(); }}><Heart size={22} strokeWidth={1.8} /><small>{wishlist.length}</small></a><a className="storefront-icon-action" href="#basket" aria-label="Shopping basket"><ShoppingBag size={22} strokeWidth={1.8} /><small>{cart.reduce((n, line) => n + line.quantity, 0)}</small></a><a className="storefront-admin-link" href="/admin">Admin</a></div>
    </header>
    <nav className="storefront-department-nav" aria-label="Shop departments"><a href="/#categories" onClick={event => { event.preventDefault(); openShopHome(); }}>☰ All Categories</a><a href="/#deals" onClick={event => { event.preventDefault(); openShopHome(); setTimeout(() => document.getElementById("deals")?.scrollIntoView({behavior:"smooth"}), 0); }}>Deals <Flame size={14} /></a><button type="button" onClick={openShopHome}>Shop All</button>{displayCategories.map(category => <a key={category.id} href={"/category/" + categorySlug(category.name)} aria-current={routeSlug === categorySlug(category.name) ? "page" : undefined}>{category.name}</a>)}</nav>
    {!isCategoryPage && !isWishlistPage && <section className="storefront-hero">
      <div className="storefront-hero-copy"><span className="storefront-kicker"><i /> YOUR EVERYDAY SUPER STORE</span><h1>Welcome to<br /><em>Super Bajaar</em></h1><p>Everything you need, all in one place. Explore everyday essentials and discover something new for your home and family.</p><a className="storefront-primary" href="#products">Shop Now <span>→</span></a><div className="storefront-trust"><span>✦ Thoughtfully picked</span><span>✦ Made for everyday</span></div></div>
      <div className="storefront-hero-art" aria-label="Colourful shopping bags and everyday products" role="img"><div className="art-sun" /><div className="art-orbit orbit-one" /><div className="art-orbit orbit-two" /><div className="art-spark spark-one">✦</div><div className="art-spark spark-two">✳</div><div className="art-bag bag-purple"><span>S</span></div><div className="art-bag bag-orange"><span>♥</span></div><div className="art-box"><span>GOOD</span><strong>THINGS</strong></div><div className="art-leaf leaf-one">✦</div><div className="art-leaf leaf-two">✿</div><div className="art-caption">A little joy in every basket</div></div>
    </section>}
    {!isCategoryPage && !isWishlistPage && <section className="storefront-categories" id="categories">
      <div className="storefront-section-heading"><div><span className="storefront-kicker">FIND YOUR FAVOURITES</span><h2>Shop by category</h2></div><span className="storefront-heading-note">Choose a category to filter products.</span></div>
      <div className="storefront-category-grid">

        {displayCategories.map((category, index) => {
          const tile = categoryArt[category.name] || art[index % art.length];
          return <button type="button" className={"storefront-category " + (String(category.id) === categoryId ? "is-selected" : "")} key={category.id} onClick={() => openCategory(category)}>
            <span className={"storefront-category-art tone-" + tile.tone}><span>{tile.icon}</span><i>↗</i></span><strong>{category.name}</strong><small>{category.description || tile.detail}</small>
          </button>;
        })}
      </div>
    </section>}
    <section className={"storefront-products " + (isCategoryPage ? "storefront-category-page" : "") + (isWishlistPage ? " storefront-wishlist-page" : "")} id="products">
      <div className="storefront-category-breadcrumb"><a href="/" onClick={event => {event.preventDefault(); openShopHome();}}>Home</a><span>/</span><span>{isWishlistPage ? "My Wishlist" : routeCategoryName || "Shop products"}</span></div><div className="storefront-section-heading"><div><span className="storefront-kicker">{isWishlistPage ? "YOUR SAVED FAVOURITES" : isCategoryPage ? "SHOP BY DEPARTMENT" : "TODAY’S PICKS"}</span><h1>{isWishlistPage ? "My Wishlist" : isCategoryPage ? routeCategoryName : categoryId ? (orderedCategories.find(c => String(c.id) === categoryId)?.name || "Products") : "Shop products"}</h1>{isWishlistPage && <p className="storefront-category-description">Your saved products, ready to revisit or add to your basket.</p>}{isCategoryPage && <p className="storefront-category-description">{categoryArt[routeCategoryName]?.detail || "Explore products in this department."}</p>}</div><span className="storefront-heading-note">{displayedVariants.length} {isWishlistPage ? "saved products" : "variants available"}</span></div>
      <label className="storefront-search">Search products or SKU<input value={search} onChange={e => setSearch(e.target.value)} placeholder="Try a product name or SKU" /></label>
      {error && <p className="storefront-alert" role="alert">{error}</p>}
      {loading ? <p className="storefront-empty">Loading live products…</p> : displayedVariants.length ? <div className="storefront-product-grid">{displayedVariants.map(renderProductCard)}</div> : isWishlistPage ? <div className="storefront-wishlist-empty"><span aria-hidden="true">♡</span><h2>Your wishlist is waiting</h2><p>Tap the heart on any product to save it here for later.</p><button type="button" className="storefront-primary" onClick={openShopHome}>Explore products</button></div> : <p className="storefront-empty">{error ? "The live catalogue could not be loaded." : "No active products are available in this category yet."}</p>}
    </section>
    {!isCategoryPage && !isWishlistPage && !loading && <div className="storefront-discovery">
      {renderDiscoverySection("Best Sellers", "Customer favourites, ranked by recorded sales", bestSellers, "Best Sellers will appear when real sales data is available.", <Flame size={18} />)}
      {renderDiscoverySection("New Arrivals", "Fresh additions to the catalogue", newArrivals, "New products will appear here when available.", <Sparkles size={18} />)}
      {renderDiscoverySection("Recently Viewed", "Pick up where you left off", recentVariants, "Products you open will appear here during this browsing session.", <Clock3 size={18} />)}
    </div>}
    {!isWishlistPage && <section className="storefront-checkout" id="basket">
      <div><span className="storefront-kicker">YOUR BASKET</span><h2>Checkout</h2><p>Prices and order totals are calculated by the server. Online payment collection is not enabled yet.</p>{order && <p className="storefront-order-success" role="status">Order placed: <strong>{order.order_number}</strong> · {money(order.total)}</p>}</div>
      <div className="storefront-basket-lines">{cart.length ? cart.map(line => <div className="storefront-basket-line" key={line.id}><div><strong>{line.product_name || line.sku}</strong><small>{line.sku} · {money(line.selling_price)}</small></div><label>Qty<input type="number" min="0" max="100000" step="1" value={line.quantity} onChange={e => setQuantity(line.id, e.target.value)} /></label><strong>{money(line.selling_price * line.quantity)}</strong><button type="button" aria-label={"Remove " + line.sku} onClick={() => setCart(old => old.filter(x => x.id !== line.id))}>×</button></div>) : <p className="storefront-empty">Your basket is empty. Add a product to begin.</p>}<div className="storefront-basket-total"><span>Subtotal</span><strong>{money(total)}</strong></div>
        <form className="storefront-checkout-form" onSubmit={checkout}><label>Full name<input required minLength="1" maxLength="200" value={customer.name} onChange={e => setCustomer(v => ({ ...v, name: e.target.value }))} /></label><label>Phone (optional)<input maxLength="20" value={customer.phone} onChange={e => setCustomer(v => ({ ...v, phone: e.target.value }))} /></label><label>Delivery PIN (optional)<input inputMode="numeric" pattern="[0-9]{6}" maxLength="6" value={customer.pin} onChange={e => setCustomer(v => ({ ...v, pin: e.target.value }))} /></label><button type="submit" className="storefront-primary" disabled={submitting || !cart.length}>{submitting ? "Placing order…" : "Place order"}</button></form>
        {notice && <p className="storefront-order-success" role="status">{notice}</p>}{error && <p className="storefront-alert" role="alert">{error}</p>}
      </div>
    </section>}
    {!isCategoryPage && !isWishlistPage && <section className="storefront-benefits" id="why-us"><div><span className="benefit-icon">✦</span><strong>Everyday essentials</strong><small>All your regular picks in one place.</small></div><div><span className="benefit-icon">♡</span><strong>Made for your routine</strong><small>A simpler way to shop for home and family.</small></div><div><span className="benefit-icon">✳</span><strong>Discover something new</strong><small>Explore categories for every kind of day.</small></div></section>}
    <footer className="storefront-footer"><a className="storefront-brand" href="/"><span className="storefront-logo">S</span><span><strong>Super Bajaar</strong><small>Your Everyday Super Store</small></span></a><span>Everyday made a little brighter.</span><a href="/admin">Business admin ↗</a></footer>
  </main>;
}
