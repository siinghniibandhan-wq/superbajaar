import { useEffect, useMemo, useState } from "react";
import { Heart, ShoppingBag, Search, Sparkles, Flame, Clock3, ChevronLeft, ChevronRight, UserRound, MapPin, X } from "lucide-react";
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
  const [wishlist, setWishlist] = useState(() => { try { return JSON.parse(window.localStorage.getItem("sb-wishlist") || "[]").map(Number).filter(Number.isFinite); } catch { return []; } });
  const [recentlyViewed, setRecentlyViewed] = useState([]);
  const [customer, setCustomer] = useState(() => { try { return { name: "", phone: "", pin: "", email: "", address: "", ...JSON.parse(window.localStorage.getItem("sb-customer-profile") || "{}") }; } catch { return { name: "", phone: "", pin: "", email: "", address: "" }; } });
  const [loading, setLoading] = useState(true);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [order, setOrder] = useState(null);
  const [selectedProduct, setSelectedProduct] = useState(null);
  const [deliveryOpen, setDeliveryOpen] = useState(false);
  const [deliveryPin, setDeliveryPin] = useState(() => { try { return window.localStorage.getItem("sb-delivery-pin") || ""; } catch { return ""; } });
  const [deliveryDraft, setDeliveryDraft] = useState(() => { try { return window.localStorage.getItem("sb-delivery-pin") || ""; } catch { return ""; } });
  const [deliveryMessage, setDeliveryMessage] = useState("");
  const [accountOpen, setAccountOpen] = useState(false);
  const [accountSection, setAccountSection] = useState("overview");
  const [canOpenAdmin, setCanOpenAdmin] = useState(false);

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
    if (!selectedProduct) return undefined;
    const closeOnEscape = event => { if (event.key === "Escape") setSelectedProduct(null); };
    window.addEventListener("keydown", closeOnEscape);
    return () => window.removeEventListener("keydown", closeOnEscape);
  }, [selectedProduct]);

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
    let token = "";
    try { token = window.localStorage.getItem("superbajaar.access_token") || ""; } catch {}
    if (!token) { setCanOpenAdmin(false); return () => { active = false; }; }
    apiRequest("/auth/me").then(result => {
      if (!active) return;
      const user = result?.user || result || {};
      const roles = [user.role, user.user_role, ...(Array.isArray(user.roles) ? user.roles : [])].map(value => String(value || "").toLowerCase());
      setCanOpenAdmin(roles.some(role => ["owner", "admin", "administrator", "super_admin", "superadmin"].includes(role)) || user.is_admin === true || user.is_superuser === true);
    }).catch(() => { if (active) setCanOpenAdmin(false); });
    return () => { active = false; };
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
  const isAccountPage = routePath === "/account";
  const isCheckoutPage = routePath === "/checkout";
  const infoSlug = routePath.startsWith("/pages/") ? routePath.slice("/pages/".length) : "";
  const isInfoPage = Boolean(infoSlug);
  const openCategory = category => {
    const slug = categorySlug(category.name);
    window.history.pushState({}, "", "/category/" + slug);
    setRoutePath("/category/" + slug);
    setCategoryId(String(category.id));
    setSearch("");
    window.scrollTo({ top: 0, behavior: "smooth" });
  };
  const openCheckout = () => {
    window.history.pushState({}, "", "/checkout");
    setRoutePath("/checkout");
    setCategoryId("");
    setSearch("");
    setAccountOpen(false);
    window.scrollTo({ top: 0, behavior: "smooth" });
  };
  const openInfoPage = slug => {
    window.history.pushState({}, "", "/pages/" + slug);
    setRoutePath("/pages/" + slug);
    setCategoryId(""); setSearch(""); setAccountOpen(false);
    window.scrollTo({ top: 0, behavior: "smooth" });
  };
  const openTicketCenter = () => {
    window.history.pushState({}, "", "/account");
    setRoutePath("/account"); setCategoryId(""); setSearch(""); setAccountOpen(false); setAccountSection("tickets");
    window.scrollTo({ top: 0, behavior: "smooth" });
  };
  const openShopHome = () => {
    window.history.pushState({}, "", "/");
    setRoutePath("/");
    setCategoryId("");
    setSearch("");
    window.scrollTo({ top: 0, behavior: "smooth" });
  };
  const saveDeliveryPin = async event => {
    event.preventDefault();
    if (!/^[1-9][0-9]{5}$/.test(deliveryDraft)) { setDeliveryMessage("Enter a valid six-digit Indian PIN code."); return; }
    setDeliveryMessage("Checking delivery availability…");
    try {
      const result = await apiRequest("/delivery/serviceability/" + deliveryDraft, { skipAuth: true });
      setDeliveryPin(deliveryDraft);
      setCustomer(old => ({ ...old, pin: deliveryDraft }));
      try { window.localStorage.setItem("sb-delivery-pin", deliveryDraft); } catch {}
      setDeliveryMessage(result.serviceable ? "Delivery is configured for " + deliveryDraft + "." : "Delivery is not configured for " + deliveryDraft + " yet.");
    } catch (reason) {
      setDeliveryMessage("Could not verify this PIN with the delivery service. " + (reason.message || "Please try again."));
    }
  };
  const openAccount = () => {
    window.history.pushState({}, "", "/account");
    setRoutePath("/account");
    setCategoryId(""); setSearch(""); setAccountOpen(false);
    window.scrollTo({ top: 0, behavior: "smooth" });
  };
  const saveCustomerProfile = event => {
    event.preventDefault();
    try { window.localStorage.setItem("sb-customer-profile", JSON.stringify(customer)); } catch {}
    setNotice("Your profile details have been saved on this device.");
    setError("");
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
  const displayedVariants = isWishlistPage ? visibleVariants.filter(v => wishlist.some(id => Number(id) === Number(v.id))) : visibleVariants;
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
          notes: ["Website checkout", customer.email.trim() ? "Email: " + customer.email.trim() : "", customer.address.trim() ? "Delivery address: " + customer.address.trim() : ""].filter(Boolean).join(" | "),
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
    const saved = wishlist.some(id => Number(id) === Number(variant.id));
    return <article className="storefront-product-card" key={variant.id}>
      <div className="storefront-product-art"><span>{tile.icon}</span><button type="button" className={"storefront-wishlist " + (saved ? "is-saved" : "")} aria-label={(saved ? "Remove from" : "Add to") + " wishlist: " + (product?.name || variant.sku)} aria-pressed={saved} onClick={() => setWishlist(old => old.some(id => Number(id) === Number(variant.id)) ? old.filter(id => Number(id) !== Number(variant.id)) : [...old, Number(variant.id)])}><Heart size={19} strokeWidth={1.9} fill={saved ? "currentColor" : "none"} /></button></div>
      <small>{product?.brand || product?.name || "Super Bajaar"}</small>
      <h3><button type="button" className="storefront-product-title" onClick={() => { rememberViewed(variant); setSelectedProduct(variant); }}>{product?.name || variant.product_name || variant.sku}</button></h3>
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
      <div className="storefront-actions"><button type="button" className="storefront-delivery" onClick={() => { setDeliveryDraft(deliveryPin); setDeliveryMessage(""); setDeliveryOpen(true); }} aria-haspopup="dialog"><small>Deliver to</small><strong><MapPin size={13} /> {deliveryPin || "Set PIN"} ▾</strong></button><a className="storefront-icon-action" href="/wishlist" aria-label={`Open wishlist, ${wishlist.length} saved`} onClick={event => { event.preventDefault(); openWishlist(); }}><Heart size={22} strokeWidth={1.8} /><small>{wishlist.length}</small></a><a className="storefront-icon-action" href="#basket" aria-label="Shopping basket" onClick={event => { event.preventDefault(); openCheckout(); }}><ShoppingBag size={22} strokeWidth={1.8} /><small>{cart.reduce((n, line) => n + line.quantity, 0)}</small></a><div className="storefront-account-wrap"><button type="button" className="storefront-account-button" aria-label="Open account menu" aria-expanded={accountOpen} onClick={() => setAccountOpen(value => !value)}><UserRound size={20} /><span>Account</span></button>{accountOpen && <div className="storefront-account-menu storefront-account-menu-desktop"><strong>Your account</strong><p>Enter your details at checkout to attach them to an order.</p><button type="button" onClick={openAccount}>My Account</button>{canOpenAdmin && <a href="/admin">Admin Console</a>}</div>}</div></div>
    </header>
    {accountOpen && <div className="storefront-account-sheet-backdrop" role="presentation" onClick={event => { if (event.target === event.currentTarget) setAccountOpen(false); }}><section className="storefront-account-sheet" role="dialog" aria-modal="true" aria-labelledby="storefront-account-sheet-title"><div className="storefront-account-sheet-handle" aria-hidden="true" /><div className="storefront-account-sheet-heading"><div><span className="storefront-kicker">SUPER BAJAAR</span><h2 id="storefront-account-sheet-title">Your account</h2></div><button type="button" className="storefront-modal-close" aria-label="Close account menu" onClick={() => setAccountOpen(false)}><X size={19} /></button></div><p>Manage your profile and shopping experience.</p><button type="button" className="storefront-account-sheet-action" onClick={openAccount}><span className="storefront-account-sheet-action-icon"><UserRound size={20} /></span><span><strong>My Account</strong><small>Contact and delivery details</small></span><span aria-hidden="true">›</span></button>{canOpenAdmin && <a className="storefront-account-sheet-action" href="/admin"><span className="storefront-account-sheet-action-icon">⌘</span><span><strong>Admin Console</strong><small>Store management</small></span><span aria-hidden="true">›</span></a>}</section></div>}
    <nav className="storefront-department-nav" aria-label="Shop departments"><a href="/#categories" onClick={event => { event.preventDefault(); openShopHome(); setTimeout(() => document.getElementById("categories")?.scrollIntoView({ behavior: "smooth" }), 0); }}>☰ All Categories</a><a href="/#deals" onClick={event => { event.preventDefault(); openShopHome(); setTimeout(() => document.getElementById("deals")?.scrollIntoView({behavior:"smooth"}), 0); }}>Deals <Flame size={14} /></a><button type="button" onClick={() => { openShopHome(); setTimeout(() => document.getElementById("products")?.scrollIntoView({ behavior: "smooth" }), 0); }}>Shop All</button>{displayCategories.map(category => <a key={category.id} href={"/category/" + categorySlug(category.name)} aria-current={routeSlug === categorySlug(category.name) ? "page" : undefined}>{category.name}</a>)}</nav>
    {!isCategoryPage && !isWishlistPage && !isAccountPage && !isCheckoutPage && <section className="storefront-hero">
      <div className="storefront-hero-copy"><span className="storefront-kicker"><i /> YOUR EVERYDAY SUPER STORE</span><h1>Welcome to<br /><em>Super Bajaar</em></h1><p>Everything you need, all in one place. Explore everyday essentials and discover something new for your home and family.</p><a className="storefront-primary" href="#products">Shop Now <span>→</span></a><div className="storefront-trust"><span>✦ Thoughtfully picked</span><span>✦ Made for everyday</span></div></div>
      <div className="storefront-hero-art" aria-label="Colourful shopping bags and everyday products" role="img"><div className="art-sun" /><div className="art-orbit orbit-one" /><div className="art-orbit orbit-two" /><div className="art-spark spark-one">✦</div><div className="art-spark spark-two">✳</div><div className="art-bag bag-purple"><span>S</span></div><div className="art-bag bag-orange"><span>♥</span></div><div className="art-box"><span>GOOD</span><strong>THINGS</strong></div><div className="art-leaf leaf-one">✦</div><div className="art-leaf leaf-two">✿</div><div className="art-caption">A little joy in every basket</div></div>
    </section>}
    {!isCategoryPage && !isWishlistPage && !isAccountPage && !isCheckoutPage && <section className="storefront-categories" id="categories">
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
    {isCheckoutPage && <section className="storefront-checkout-page"><div className="storefront-category-breadcrumb"><button type="button" onClick={openShopHome}>Home</button><span>/</span><span>Checkout</span></div><div className="storefront-checkout-page-heading"><span className="storefront-kicker">YOUR BASKET</span><h1>Checkout</h1><p>Review your items and delivery details before placing your order.</p></div>{error && <p className="storefront-alert" role="alert">{error}</p>}{notice && <p className="storefront-order-success" role="status">{notice}</p>}{order && <p className="storefront-order-success" role="status">Order placed: <strong>{order.order_number}</strong> · {money(order.total)}</p>}<section className="storefront-checkout" id="basket"><div><span className="storefront-kicker">ORDER SUMMARY</span><h2>Your basket</h2><p>Prices and order totals are calculated by the server. Online payment collection is not enabled yet.</p></div><div className="storefront-basket-lines">{cart.length ? cart.map(line => <div className="storefront-basket-line" key={line.id}><div><strong>{line.product_name || line.sku}</strong><small>{line.sku} · {money(line.selling_price)}</small></div><label>Qty<input type="number" min="0" max="100000" step="1" value={line.quantity} onChange={e => setQuantity(line.id, e.target.value)} /></label><strong>{money(line.selling_price * line.quantity)}</strong><button type="button" aria-label={"Remove " + line.sku} onClick={() => setCart(old => old.filter(x => x.id !== line.id))}>×</button></div>) : <div className="storefront-checkout-empty"><h3>Your basket is empty</h3><p>Add products to your basket before placing an order.</p><button type="button" className="storefront-primary" onClick={openShopHome}>Continue shopping</button></div>}<div className="storefront-basket-total"><span>Subtotal</span><strong>{money(total)}</strong></div>{cart.length>0 && <form className="storefront-checkout-form" onSubmit={checkout}><label>Full name<input required minLength="1" maxLength="200" value={customer.name} onChange={e => setCustomer(v => ({ ...v, name: e.target.value }))} /></label><label>Phone (optional)<input maxLength="20" value={customer.phone} onChange={e => setCustomer(v => ({ ...v, phone: e.target.value }))} /></label><label>Delivery PIN (optional)<input inputMode="numeric" pattern="[0-9]{6}" maxLength="6" value={customer.pin} onChange={e => setCustomer(v => ({ ...v, pin: e.target.value }))} /></label><button type="submit" className="storefront-primary" disabled={submitting || !cart.length}>{submitting ? "Placing order…" : "Place order"}</button></form>}</div></section></section>}
    {isAccountPage && <section className="storefront-account-page">
      <div className="storefront-category-breadcrumb"><button type="button" onClick={openShopHome}>Home</button><span>/</span><span>My Account</span></div>
      <div className="storefront-account-welcome"><span className="storefront-kicker">YOUR SUPER BAJAAR</span><h1>{customer.name.trim() ? `Hello, ${customer.name.trim().split(/\s+/)[0]}` : "My Account"}</h1><p>Manage your profile, purchases and support in one place.</p></div>
      <div className="storefront-account-layout">
        <nav className="storefront-account-nav" aria-label="Customer account sections">
          {[["overview","Overview","user-round"],["orders","My Orders","package"],["tickets","My Tickets","ticket"],["wishlist","My Wishlist","heart"],["addresses","Addresses","map-pin"],["security","Security","shield-check"]].map(([key,label])=><button key={key} type="button" className={accountSection===key?"is-active":""} onClick={()=>{if(key==="wishlist"){openWishlist();return;}setAccountSection(key);setNotice("");setError("");}}>{label}<span aria-hidden="true">›</span></button>)}
        </nav>
        <div className="storefront-account-panel">
          {accountSection==="overview" && <div className="storefront-account-section">
            <div className="storefront-account-section-heading"><div><h2>Personal details</h2><p>Your saved contact information.</p></div><span className="storefront-account-avatar">{customer.name.trim()?customer.name.trim().slice(0,1).toUpperCase():"S"}</span></div>
            {(customer.name||customer.email||customer.phone) ? <div className="storefront-account-summary">{customer.name&&<div><small>Full name</small><strong>{customer.name}</strong></div>}{customer.email&&<div><small>Email address</small><strong>{customer.email}</strong></div>}{customer.phone&&<div><small>Mobile number</small><strong>{customer.phone}</strong></div>}</div> : <p className="storefront-account-empty">Your profile is not filled in yet. Add your details below so they are ready at checkout.</p>}
            <form className="storefront-account-form" onSubmit={saveCustomerProfile}><label>Full name<input autoComplete="name" required maxLength="200" value={customer.name} onChange={event=>setCustomer(old=>({...old,name:event.target.value}))}/></label><label>Mobile number<input autoComplete="tel" maxLength="20" value={customer.phone} onChange={event=>setCustomer(old=>({...old,phone:event.target.value}))}/></label><label>Email address<input type="email" autoComplete="email" maxLength="254" value={customer.email} onChange={event=>setCustomer(old=>({...old,email:event.target.value}))}/></label><button className="storefront-primary" type="submit">Save profile</button><p className="storefront-account-note">Currently saved on this device only. A verified customer sign-in is needed to sync details across devices.</p></form>
          </div>}
          {accountSection==="orders" && <div className="storefront-account-section"><h2>My Orders</h2><p>View purchases, order details and delivery updates.</p><div className="storefront-account-empty-state"><span>📦</span><h3>Order history needs customer sign-in</h3><p>Orders are recorded by the store, but this portal does not yet have a secure customer identity to retrieve only your orders. We will not show unverified order records here.</p></div></div>}
          {accountSection==="tickets" && <div className="storefront-account-section"><h2>My Tickets</h2><p>Raise an issue and follow replies from the support team.</p><div className="storefront-account-empty-state"><span>🎫</span><h3>Customer ticket access needs to be connected</h3><p>The system has support-case records for store operations. A secure customer sign-in and ownership-checked ticket endpoints are required before customers can create or view their own tickets here.</p></div></div>}
          {accountSection==="addresses" && <div className="storefront-account-section"><h2>Addresses</h2><p>Manage your preferred delivery address and PIN code.</p><form className="storefront-account-form" onSubmit={saveCustomerProfile}><label>Delivery PIN<input inputMode="numeric" autoComplete="postal-code" pattern="[1-9][0-9]{5}" maxLength="6" value={customer.pin} onChange={event=>setCustomer(old=>({...old,pin:event.target.value.replace(/\\D/g,"").slice(0,6)}))}/></label><label className="storefront-account-address">Delivery address<textarea autoComplete="street-address" rows="3" maxLength="1000" value={customer.address} onChange={event=>setCustomer(old=>({...old,address:event.target.value}))}/></label><button className="storefront-primary" type="submit">Save address</button><p className="storefront-account-note">Address is currently saved on this device, not synced to a signed-in customer account.</p></form></div>}
          {accountSection==="security" && <div className="storefront-account-section"><h2>Security</h2><p>Protect your account and keep your contact details verified.</p><div className="storefront-security-list"><div><span><strong>Change password</strong><small>Change the password used to sign in.</small></span><button type="button" disabled>Not available yet</button></div><div><span><strong>Update mobile number</strong><small>Requires OTP verification of the new number.</small></span><button type="button" disabled>OTP setup required</button></div><div><span><strong>Update email address</strong><small>Requires verification of the new email address.</small></span><button type="button" disabled>Email verification required</button></div><div><span><strong>Login sessions</strong><small>Review and end active customer sessions.</small></span><button type="button" disabled>Customer sign-in required</button></div></div><p className="storefront-account-note">These actions are not enabled because customer authentication and verification are not implemented yet. We will not simulate security changes in the browser.</p></div>}
          {notice && <p className="storefront-order-success" role="status">{notice}</p>}
        </div>
      </div>
    </section>}
    {isInfoPage && <section className="storefront-info-page"><div className="storefront-category-breadcrumb"><button type="button" onClick={openShopHome}>Home</button><span>/</span><span>Information</span></div>
      {infoSlug === "about-us" && <><span className="storefront-kicker">OUR STORY</span><h1>About Super Bajaar</h1><p><strong>Super Bajaar</strong> is a retail brand owned and operated by <strong>KPMC Enterprises</strong>. Our aim is to make everyday shopping simpler by bringing daily essentials and multiple product categories together in one convenient place.</p><h2>Our brand</h2><p>Super Bajaar is the customer-facing shopping brand. KPMC Enterprises owns the brand and is responsible for its business operations. Product availability, prices, delivery options and applicable terms are displayed through the storefront and at checkout.</p><h2>Contact</h2><p>For customer assistance, email <a href="mailto:kpmcenterprise@gmail.com">kpmcenterprise@gmail.com</a> or call <a href="tel:+917644841104">+91 76448 41104</a>.</p></>}
      {infoSlug === "contact-us" && <><span className="storefront-kicker">WE ARE HERE TO HELP</span><h1>Customer Support</h1><p>Choose the channel that works best for you. For order-related issues, please include your order number when contacting us.</p><div className="storefront-contact-grid"><a href="tel:+917644841104"><strong>Call us</strong><span>+91 76448 41104</span></a><a href="https://wa.me/917644841104" target="_blank" rel="noreferrer"><strong>WhatsApp</strong><span>Chat with customer support</span></a><a href="mailto:kpmcenterprise@gmail.com"><strong>Email support</strong><span>kpmcenterprise@gmail.com</span></a><button type="button" onClick={openTicketCenter}><strong>Raise a ticket</strong><span>Open customer support in My Account</span></button></div><p className="storefront-info-note">Ticket creation and ticket-status tracking must be connected to the customer support backend before they can be submitted or tracked online.</p></>}
      {infoSlug === "privacy-policy" && <><span className="storefront-kicker">LEGAL INFORMATION</span><h1>Privacy Policy</h1><p>This policy describes how Super Bajaar, a brand owned by KPMC Enterprises, may handle information when you browse or shop through the website. The final policy should be reviewed against the actual production data flows before launch.</p><h2>Information you provide</h2><p>Information may include your name, phone number, email address, delivery address and PIN code, order details, support requests and messages you send us.</p><h2>How information is used</h2><p>Information is used to process orders, coordinate delivery, respond to support requests, maintain service quality, prevent misuse and meet applicable legal obligations.</p><h2>Storage and sharing</h2><p>Profile information currently saved in the browser may remain on that device. Information submitted through connected order or support services may be processed by the systems and service providers needed to operate the service. Do not enter information that is not needed for your request.</p><h2>Your choices and rights</h2><p>You may contact us to ask about your personal information or request correction or other action available under applicable law. Requests may require verification of identity.</p><h2>Contact</h2><p>Privacy queries: <a href="mailto:kpmcenterprise@gmail.com">kpmcenterprise@gmail.com</a>.</p><p className="storefront-info-note">This is a draft policy page. Confirm the production data inventory, retention periods, processors, grievance process and applicable legal requirements before treating it as the final published policy.</p></>}
      {infoSlug === "terms-and-conditions" && <><span className="storefront-kicker">PLEASE READ BEFORE ORDERING</span><h1>Terms &amp; Conditions</h1><p>Super Bajaar is a brand owned by KPMC Enterprises. By accessing the website or placing an order, you agree to use the service lawfully and provide accurate information needed to fulfil your order.</p><h2>Products, prices and availability</h2><p>Products are subject to availability. Prices, applicable charges and order totals shown at checkout may be updated before an order is accepted. An order may require confirmation by the store.</p><h2>Orders and payment</h2><p>Please review the basket and delivery details before placing an order. Available payment methods and payment status will be shown when supported. An order confirmation does not mean a payment has been collected unless the payment system confirms it.</p><h2>Delivery, cancellation, returns and refunds</h2><p>Delivery estimates and charges are described in the Shipping &amp; Delivery policy. Cancellation, returns and refunds are handled under the applicable policies and law.</p><h2>Responsible use</h2><p>Do not misuse the website, interfere with its operation, submit fraudulent orders or attempt to access another person's account or information.</p><h2>Contact</h2><p>Questions: <a href="mailto:kpmcenterprise@gmail.com">kpmcenterprise@gmail.com</a> or <a href="tel:+917644841104">+91 76448 41104</a>.</p><p className="storefront-info-note">These terms are a draft for review and should be checked for the actual business model, pricing, payment, cancellation and dispute-resolution processes before publication.</p></>}
      {infoSlug === "shipping-delivery" && <><span className="storefront-kicker">DELIVERY INFORMATION</span><h1>Shipping &amp; Delivery</h1><div className="storefront-policy-cards"><article><strong>Standard Delivery</strong><b>1–5 days</b><p>Estimated delivery window, subject to product availability, destination and service conditions.</p></article><article><strong>Express Delivery</strong><b>30 minutes to 1 day</b><p>Express delivery is available only for eligible products and serviceable locations.</p><small>Charge: ₹39 per order</small></article></div><h2>Important information</h2><p>Delivery estimates begin after the order is accepted and may vary due to location, stock, weather, operational constraints or other circumstances. Express delivery is not guaranteed for every PIN code or product. Any applicable delivery charge should be shown before the order is placed.</p><p>For delivery help, call <a href="tel:+917644841104">+91 76448 41104</a> or email <a href="mailto:kpmcenterprise@gmail.com">kpmcenterprise@gmail.com</a>.</p></>}
      {infoSlug === "returns-refunds" && <><span className="storefront-kicker">RETURNS &amp; REFUNDS</span><h1>Returns &amp; Refunds</h1><p>Returns are subject to verification of the order, item condition and the applicable return rules. Please contact support with your order number and the reason for the return before sending an item back.</p><h2>Verification</h2><p>Returned items will be checked to confirm that the return is genuine and meets the applicable return conditions. Some products may be non-returnable where permitted by applicable law and where clearly disclosed before purchase.</p><h2>Refund timing</h2><p>For genuine and verified returns approved for refund, the refund will be processed within <strong>2 working days</strong> after verification and approval. The time for the amount to appear in the original payment method may depend on the bank or payment provider.</p><h2>Request help</h2><p>Call <a href="tel:+917644841104">+91 76448 41104</a>, WhatsApp <a href="https://wa.me/917644841104" target="_blank" rel="noreferrer">+91 76448 41104</a>, or email <a href="mailto:kpmcenterprise@gmail.com">kpmcenterprise@gmail.com</a>.</p></>}
      {infoSlug === "grievance-redressal" && <><span className="storefront-kicker">CUSTOMER RIGHTS &amp; ESCALATION</span><h1>Grievance Redressal</h1><p>For unresolved complaints about orders, delivery, returns or website services, contact the grievance officer with your name, contact details, order number (if applicable) and a clear description of the issue.</p><div className="storefront-grievance-card"><strong>Grievance Officer</strong><h2>NK Singh</h2><p>Phone: <a href="tel:+917644841104">+91 76448 41104</a></p><p>Email: <a href="mailto:nibandhansingh1997@gmail.com">nibandhansingh1997@gmail.com</a></p></div><h2>How to raise a grievance</h2><ol><li>Contact the officer using the phone or email above.</li><li>Include relevant order or ticket details and any supporting information.</li><li>Keep the complaint reference and any replies for follow-up.</li></ol><p>Complaints will be reviewed and addressed in accordance with applicable law and the processes applicable to the business.</p></>}
      {infoSlug === "legal" && <><span className="storefront-kicker">APPLICABLE FRAMEWORK</span><h1>Legal Information</h1><p>The legal framework relevant to an Indian e-commerce business may include the following, depending on the actual business model and applicability:</p><ul><li><strong>Consumer Protection Act, 2019</strong> and the <strong>Consumer Protection (E-Commerce) Rules, 2020</strong>.</li><li><strong>Information Technology Act, 2000</strong> and applicable rules.</li><li><strong>Digital Personal Data Protection Act, 2023</strong>, to the extent in force and applicable.</li><li><strong>Foreign Exchange Management Act (FEMA)</strong> and applicable foreign investment rules, if relevant to ownership or investment.</li></ul><p>The Department for Promotion of Industry and Internal Trade (DPIIT), under the Ministry of Commerce and Industry, handles relevant policy matters including FDI policy. The Central Consumer Protection Authority (CCPA) has functions relating to consumer rights and unfair trade practices under consumer protection law.</p><p className="storefront-info-note">This information is general and does not determine which obligations apply to this specific business. Have the final policy and legal disclosures reviewed by a qualified professional before launch.</p></>}
      {infoSlug === "faq" && <><span className="storefront-kicker">QUICK ANSWERS</span><h1>Frequently Asked Questions</h1><h2>How long does delivery take?</h2><p>Standard delivery is estimated at 1–5 days. Eligible express orders may take 30 minutes to 1 day and cost ₹39 per order.</p><h2>How do I contact support?</h2><p>Call or WhatsApp +91 76448 41104 or email kpmcenterprise@gmail.com.</p><h2>How long do refunds take?</h2><p>Approved refunds for genuine and verified returns are processed within 2 working days after verification and approval. Bank processing may take additional time.</p><h2>How can I raise a grievance?</h2><p>Contact grievance officer NK Singh at +91 76448 41104 or nibandhansingh1997@gmail.com.</p><h2>Where can I check whether delivery is available?</h2><p>Use the delivery PIN selector on the storefront. Availability depends on the configured delivery locations and eligible products.</p></>}
      {!["about-us","contact-us","privacy-policy","terms-and-conditions","shipping-delivery","returns-refunds","grievance-redressal","legal","faq"].includes(infoSlug) && <><h1>Page not found</h1><p>This information page does not exist.</p><button className="storefront-primary" type="button" onClick={openShopHome}>Return to shopping</button></>}
    </section>}
    {!isAccountPage && !isCheckoutPage && !isInfoPage && (isCategoryPage || isWishlistPage) && <section className={"storefront-products " + (isCategoryPage ? "storefront-category-page" : "") + (isWishlistPage ? " storefront-wishlist-page" : "")} id="products">
      <div className="storefront-category-breadcrumb"><a href="/" onClick={event => {event.preventDefault(); openShopHome();}}>Home</a><span>/</span><span>{isWishlistPage ? "My Wishlist" : routeCategoryName || "Shop products"}</span></div><div className="storefront-section-heading"><div><span className="storefront-kicker">{isWishlistPage ? "YOUR SAVED FAVOURITES" : isCategoryPage ? "SHOP BY DEPARTMENT" : "TODAY’S PICKS"}</span><h1>{isWishlistPage ? "My Wishlist" : isCategoryPage ? routeCategoryName : categoryId ? (orderedCategories.find(c => String(c.id) === categoryId)?.name || "Products") : "Shop products"}</h1>{isWishlistPage && <p className="storefront-category-description">Your saved products, ready to revisit or add to your basket.</p>}{isCategoryPage && <p className="storefront-category-description">{categoryArt[routeCategoryName]?.detail || "Explore products in this department."}</p>}</div><span className="storefront-heading-note">{displayedVariants.length} {isWishlistPage ? "saved products" : "variants available"}</span></div>
      <label className="storefront-search">Search products or SKU<input value={search} onChange={e => setSearch(e.target.value)} placeholder="Try a product name or SKU" /></label>
      {error && <p className="storefront-alert" role="alert">{error}</p>}
      {loading ? <p className="storefront-empty">Loading live products…</p> : displayedVariants.length ? <div className="storefront-product-grid">{displayedVariants.map(renderProductCard)}</div> : isWishlistPage ? <div className="storefront-wishlist-empty"><span aria-hidden="true">♡</span><h2>Your wishlist is waiting</h2><p>Tap the heart on any product to save it here for later.</p><button type="button" className="storefront-primary" onClick={openShopHome}>Explore products</button></div> : <p className="storefront-empty">{error ? "The live catalogue could not be loaded." : "No active products are available in this category yet."}</p>}
    </section>}
    {!isAccountPage && !isCheckoutPage && !isCategoryPage && !isWishlistPage && !loading && <div className="storefront-discovery">
      {renderDiscoverySection("Best Sellers", "Customer favourites, ranked by recorded sales", bestSellers, "Best Sellers will appear when real sales data is available.", <Flame size={18} />)}
      {renderDiscoverySection("New Arrivals", "Fresh additions to the catalogue", newArrivals, "New products will appear here when available.", <Sparkles size={18} />)}
      {renderDiscoverySection("Recently Viewed", "Pick up where you left off", recentVariants, "Products you open will appear here during this browsing session.", <Clock3 size={18} />)}
    </div>}
    
    {!isCategoryPage && !isWishlistPage && !isAccountPage && !isCheckoutPage && !isInfoPage && <section className="storefront-benefits" id="why-us"><div className="storefront-benefits-heading"><span className="storefront-kicker">THE SUPER BAJAAR DIFFERENCE</span><h2>Why Choose Us</h2><p>Everyday shopping, made simpler for you.</p></div><div className="storefront-benefit-grid"><article><span className="benefit-icon">✦</span><strong>Everyday essentials</strong><small>Explore a wide range of daily needs in one place.</small></article><article><span className="benefit-icon">♡</span><strong>Convenient shopping</strong><small>Browse departments and build your basket with ease.</small></article><article><span className="benefit-icon">✓</span><strong>Clear delivery information</strong><small>See available delivery options and charges before ordering.</small></article><article><span className="benefit-icon">✳</span><strong>Support when you need it</strong><small>Contact our support team or raise a ticket for help.</small></article></div></section>}
    {deliveryOpen && <div className="storefront-delivery-backdrop" role="presentation" onClick={event => { if (event.target === event.currentTarget) setDeliveryOpen(false); }}><section className="storefront-delivery-dialog" role="dialog" aria-modal="true" aria-labelledby="storefront-delivery-title"><button type="button" className="storefront-modal-close" aria-label="Close delivery location" onClick={() => setDeliveryOpen(false)}><X size={19}/></button><span className="storefront-kicker">DELIVERY LOCATION</span><h2 id="storefront-delivery-title">Where should we deliver?</h2><p>Enter your six-digit Indian PIN code to save your preferred delivery location.</p><form onSubmit={saveDeliveryPin}><label>PIN code<input inputMode="numeric" autoComplete="postal-code" pattern="[1-9][0-9]{5}" maxLength="6" value={deliveryDraft} onChange={event => { setDeliveryDraft(event.target.value.replace(/\D/g,"").slice(0,6)); setDeliveryMessage(""); }} required /></label><button className="storefront-primary" type="submit">Save location</button></form>{deliveryMessage && <p className="storefront-delivery-message" role="status">{deliveryMessage}</p>}<small>Saving a PIN does not confirm serviceability; that requires a connected delivery-serviceability check.</small></section></div>}
    {selectedProduct && (() => { const product = productById.get(Number(selectedProduct.product_id)); const saved = wishlist.some(id => Number(id) === Number(selectedProduct.id)); const categoryName = product?.category_name || product?.category || orderedCategories.find(c => String(c.id) === String(product?.category_id))?.name; const tile = categoryArt[categoryName] || art[0]; return <div className="storefront-product-modal-backdrop" role="presentation" onClick={event => { if (event.target === event.currentTarget) setSelectedProduct(null); }}><section className="storefront-product-modal" role="dialog" aria-modal="true" aria-labelledby="storefront-product-modal-title"><button type="button" className="storefront-modal-close" aria-label="Close product details" onClick={() => setSelectedProduct(null)}>×</button><div className="storefront-modal-art" aria-hidden="true">{tile.icon}</div><span className="storefront-kicker">PRODUCT DETAILS</span><h2 id="storefront-product-modal-title">{product?.name || selectedProduct.product_name || selectedProduct.sku}</h2><p className="storefront-modal-brand">{product?.brand || "Super Bajaar"}{categoryName ? " · " + categoryName : ""}</p><p className="storefront-modal-sku">SKU: {selectedProduct.sku || "Not available"}</p>{product?.description && <p className="storefront-modal-description">{product.description}</p>}<strong className="storefront-modal-price">{money(selectedProduct.selling_price)}</strong><div className="storefront-modal-actions"><button type="button" className="storefront-primary" onClick={() => { addToCart(selectedProduct); setSelectedProduct(null); }}>Add to basket</button><button type="button" className="storefront-modal-wishlist" onClick={() => setWishlist(old => old.some(id => Number(id) === Number(selectedProduct.id)) ? old.filter(id => Number(id) !== Number(selectedProduct.id)) : [...old, Number(selectedProduct.id)])}><Heart size={17} fill={saved ? "currentColor" : "none"} />{saved ? "Remove from wishlist" : "Save to wishlist"}</button></div></section></div>; })()}
    <footer className="storefront-footer">
      <div className="storefront-footer-top"><a className="storefront-brand" href="/" onClick={event=>{event.preventDefault();openShopHome();}}><span className="storefront-logo">S</span><span><strong>Super Bajaar</strong><small>Your Everyday Super Store</small></span></a><p>Everyday made a little brighter.</p><div className="storefront-footer-contact"><strong>Customer Support</strong><a href="tel:+917644841104">+91 76448 41104</a><a href="https://wa.me/917644841104" target="_blank" rel="noreferrer">WhatsApp support</a><a href="mailto:kpmcenterprise@gmail.com">kpmcenterprise@gmail.com</a></div></div>
      <div className="storefront-footer-links"><div><strong>Super Bajaar</strong><a href="/pages/about-us" onClick={e=>{e.preventDefault();openInfoPage("about-us");}}>About Us</a><a href="/pages/contact-us" onClick={e=>{e.preventDefault();openInfoPage("contact-us");}}>Contact Us</a><a href="/pages/faq" onClick={e=>{e.preventDefault();openInfoPage("faq");}}>FAQ</a></div><div><strong>Customer Help</strong><a href="/pages/shipping-delivery" onClick={e=>{e.preventDefault();openInfoPage("shipping-delivery");}}>Shipping &amp; Delivery</a><a href="/pages/returns-refunds" onClick={e=>{e.preventDefault();openInfoPage("returns-refunds");}}>Returns &amp; Refunds</a><a href="/account" onClick={e=>{e.preventDefault();openTicketCenter();}}>Raise a Ticket</a><a href="/pages/grievance-redressal" onClick={e=>{e.preventDefault();openInfoPage("grievance-redressal");}}>Grievance Redressal</a></div><div><strong>Legal</strong><a href="/pages/privacy-policy" onClick={e=>{e.preventDefault();openInfoPage("privacy-policy");}}>Privacy Policy</a><a href="/pages/terms-and-conditions" onClick={e=>{e.preventDefault();openInfoPage("terms-and-conditions");}}>Terms &amp; Conditions</a><a href="/pages/legal" onClick={e=>{e.preventDefault();openInfoPage("legal");}}>Legal Information</a></div></div>
      <div className="storefront-footer-bottom"><span>© {new Date().getFullYear()} Super Bajaar · A brand owned by KPMC Enterprises</span>{canOpenAdmin && <a href="/admin">Admin Console ↗</a>}</div>
    </footer>
  </main>;
}
