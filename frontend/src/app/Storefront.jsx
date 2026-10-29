import { useEffect, useMemo, useState } from "react";
import { Heart, ShoppingBag, Search, Sparkles, Flame, Clock3, ChevronLeft, ChevronRight, UserRound, MapPin, X, Coins, CreditCard, CalendarClock } from "lucide-react";
import { apiRequest } from "../services/api.js";
import "./storefront.css";

const categoryOrder = [
  "Grocery", "Fresh Daily", "Fashion", "Personal Care", "Electronics",
  "Home Appliances", "Pet Care", "Gifting", "Pooja Essentials",
  "Automobiles", "Toys & Sports", "Pharmacy", "Insurance",
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
  "Insurance": { icon: "🛡️", tone: "lavender", detail: "Insurance guidance for life, health and motor cover" },
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
  const [cart, setCart] = useState(() => { try { return JSON.parse(window.localStorage.getItem("sb-cart") || "[]"); } catch { return []; } });
  const [customerToken, setCustomerToken] = useState(() => { try { return window.localStorage.getItem("sb-customer.access_token") || ""; } catch { return ""; } });
  const [customerAuth, setCustomerAuth] = useState(null);
  const [customerAuthMode, setCustomerAuthMode] = useState(() => window.location.pathname === "/customer/register" ? "register" : "login");
  const [customerAuthDraft, setCustomerAuthDraft] = useState(() => ({ full_name: "", email: "", phone: "", password: "", referral_code: new URLSearchParams(window.location.search).get("ref") || "" }));
  const [customerAuthBusy, setCustomerAuthBusy] = useState(false);
  const [referralData, setReferralData] = useState(null);
  const [referralBusy, setReferralBusy] = useState(false);
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
  const [ticketDraft, setTicketDraft] = useState({ name: "", phone: "", email: "", subject: "", description: "" });
  const [ticketCreated, setTicketCreated] = useState(null);
  const [ticketLookup, setTicketLookup] = useState({ caseNumber: "", email: "", phone: "" });
  const [ticketTracked, setTicketTracked] = useState(null);
  const [ticketBusy, setTicketBusy] = useState(false);
  const [loyaltyRules, setLoyaltyRules] = useState([]);
  const [loyaltyDefaultRate, setLoyaltyDefaultRate] = useState(1);
  const [loyaltyOrderReference, setLoyaltyOrderReference] = useState("");
  const [loyaltyCustomerData, setLoyaltyCustomerData] = useState(null);
  const [loyaltyBusy, setLoyaltyBusy] = useState(false);
  const [partnerBusy, setPartnerBusy] = useState(false);
  const [partnerResult, setPartnerResult] = useState(null);

  useEffect(() => {
    try { setRecentlyViewed(JSON.parse(sessionStorage.getItem("sb-recently-viewed") || "[]")); } catch { setRecentlyViewed([]); }
  }, []);

  useEffect(() => {
    try { window.localStorage.setItem("sb-wishlist", JSON.stringify(wishlist)); } catch { /* Wishlist remains usable for this session if storage is unavailable. */ }
  }, [wishlist]);

  useEffect(() => {
    try { window.localStorage.setItem("sb-cart", JSON.stringify(cart)); } catch { /* Keep cart in memory if storage is unavailable. */ }
  }, [cart]);

  useEffect(() => {
    if (!customerToken) { setCustomerAuth(null); return; }
    let active = true;
    customerRequest("/customer-auth/me").then(result => {
      if (!active) return;
      const profile = result?.customer || null;
      setCustomerAuth(profile);
      if (profile) setCustomer(old => ({ ...old, name: profile.full_name || old.name, email: profile.email || old.email, phone: profile.phone || old.phone }));
    }).catch(() => {
      if (!active) return;
      setCustomerAuth(null); setCustomerToken("");
      try { window.localStorage.removeItem("sb-customer.access_token"); } catch {}
    });
    return () => { active = false; };
  }, [customerToken]);

  useEffect(() => {
    if (!/^\/product\/\d+$/.test(routePath) || !variants.length) return;
    const productId = Number(routePath.split("/")[2]);
    const current = variants.find(item => Number(item.product_id) === productId && item.is_active !== false);
    if (Number(selectedProduct?.product_id) !== productId || !current) {
      setSelectedProduct(current || null);
    }
  }, [routePath, variants, selectedProduct]);

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
    apiRequest("/loyalty/rules", { skipAuth: true }).then(result => {
      if (active) {
        setLoyaltyRules(Array.isArray(result?.items) ? result.items : []);
        setLoyaltyDefaultRate(Number(result?.default_coins_per_100 ?? 0));
      }
    }).catch(() => { if (active) { setLoyaltyRules([]); setLoyaltyDefaultRate(0); } });
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
  const categorySlug = name => {
    const normalized = String(name || "").trim().toLowerCase();
    if (normalized === "fresh daily") return "fresh";
    return normalized.replace(/&/g, "and").replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "");
  };
  const routeSlug = routePath.startsWith("/category/") ? routePath.slice("/category/".length).split("/")[0] : "";
  const routeCategoryName = (routeSlug === "fresh" || routeSlug === "fresh-daily")
    ? (categories.find(category => String(category.name || "").trim().toLowerCase() === "fresh daily")?.name || "Fresh Daily")
    : categoryOrder.find(name => categorySlug(name) === routeSlug)
      || categories.find(category => categorySlug(category.name) === routeSlug)?.name || "";
  const isProductPage = /^\/product\/\d+$/.test(routePath);
  const routeProductId = isProductPage ? Number(routePath.split("/")[2]) : null;
  const isCategoryPage = Boolean(routeSlug);
  const isCategoryListingPage = isCategoryPage && routePath.split("/").filter(Boolean)[2] === "all";
  const isDealsPage = routePath === "/deals";
  const isWishlistPage = routePath === "/wishlist";
  const isAccountPage = routePath === "/account";
  const isCheckoutPage = routePath === "/checkout";
  const isCustomerAuthPage = routePath === "/customer/login" || routePath === "/customer/register";
  const infoSlug = routePath.startsWith("/pages/") ? routePath.slice("/pages/".length) : "";
  const isInfoPage = Boolean(infoSlug);
  const openProductPage = variant => {
    if (!variant) return;
    rememberViewed(variant);
    setSelectedProduct(variant);
    const target = "/product/" + Number(variant.product_id);
    window.history.pushState({}, "", target);
    setRoutePath(target);
    setCategoryId("");
    setSearch("");
    window.scrollTo({ top: 0, behavior: "smooth" });
  };
  const openCategory = category => {
    const slug = categorySlug(category.name);
    window.history.pushState({}, "", "/category/" + slug);
    setRoutePath("/category/" + slug);
    setCategoryId(String(category.id));
    setSearch("");
    window.scrollTo({ top: 0, behavior: "smooth" });
  };
  const openCategoryListing = () => {
    const target = "/category/" + routeSlug + "/all";
    window.history.pushState({}, "", target); setRoutePath(target); setSearch("");
    window.scrollTo({ top: 0, behavior: "smooth" });
  };
  const openDealsPage = () => {
    window.history.pushState({}, "", "/deals"); setRoutePath("/deals"); setCategoryId(""); setSearch("");
    window.scrollTo({ top: 0, behavior: "smooth" });
  };
  const openCustomerAuth = (mode = "login", returnTo = "/checkout") => {
    const target = mode === "register" ? "/customer/register" : "/customer/login";
    const query = new URLSearchParams({ return: returnTo });
    window.history.pushState({}, "", target + "?" + query.toString());
    setRoutePath(target); setCustomerAuthMode(mode);
    setCustomerAuthDraft(old => ({ ...old, referral_code: new URLSearchParams(window.location.search).get("ref") || old.referral_code || "" }));
    setCategoryId(""); setSearch(""); setAccountOpen(false); setError(""); setNotice("");
    window.scrollTo({ top: 0, behavior: "smooth" });
  };
  const customerRequest = (path, options = {}) => apiRequest(path, {
    ...options, skipAuth: true,
    headers: { ...(customerToken ? { Authorization: "Bearer " + customerToken } : {}), ...(options.headers || {}) },
  });
  const openCheckout = () => {
    if (!customerToken || !customerAuth) { openCustomerAuth("login", "/checkout"); return; }
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
    setSelectedProduct(null);
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
    if (!customerToken || !customerAuth) { openCustomerAuth("login", "/account"); return; }
    window.history.pushState({}, "", "/account");
    setRoutePath("/account");
    setCategoryId(""); setSearch(""); setAccountOpen(false);
    window.scrollTo({ top: 0, behavior: "smooth" });
  };
  const submitCustomerAuth = async event => {
    event.preventDefault(); setCustomerAuthBusy(true); setError(""); setNotice("");
    const isRegister = customerAuthMode === "register";
    const returnTo = new URLSearchParams(window.location.search).get("return") === "/checkout" ? "/checkout" : "/account";
    const payload = isRegister
      ? { full_name: customerAuthDraft.full_name.trim(), email: customerAuthDraft.email.trim(), phone: customerAuthDraft.phone.trim(), password: customerAuthDraft.password, referral_code: customerAuthDraft.referral_code.trim() || null }
      : { email: customerAuthDraft.email.trim(), password: customerAuthDraft.password };
    try {
      const result = await apiRequest(isRegister ? "/customer-auth/register" : "/customer-auth/login", { method: "POST", skipAuth: true, body: JSON.stringify(payload) });
      if (!result?.access_token || !result?.customer) throw new Error("Customer authentication response was incomplete.");
      try { window.localStorage.setItem("sb-customer.access_token", result.access_token); } catch {}
      setCustomerToken(result.access_token); setCustomerAuth(result.customer);
      setCustomer(old => ({ ...old, name: result.customer.full_name || old.name, email: result.customer.email || old.email, phone: result.customer.phone || old.phone }));
      window.history.pushState({}, "", returnTo); setRoutePath(returnTo); setCategoryId(""); setSearch("");
      setNotice(isRegister ? "Your customer account has been created." : "You are signed in.");
    } catch (reason) { setError(reason.message || "Could not sign in. Please try again."); }
    finally { setCustomerAuthBusy(false); }
  };

  const signOutCustomer = async () => {
    try { if (customerToken) await customerRequest("/customer-auth/logout", { method: "POST" }); } catch {}
    try { window.localStorage.removeItem("sb-customer.access_token"); } catch {}
    setCustomerToken(""); setCustomerAuth(null); setReferralData(null);
    setAccountOpen(false); setNotice("You have signed out.");
    if (["/account", "/checkout"].includes(window.location.pathname.replace(/\/+$/, "") || "/")) {
      window.history.pushState({}, "", "/");
      setRoutePath("/");
      setCategoryId(""); setSearch("");
      window.scrollTo({ top: 0, behavior: "smooth" });
    }
  };

  const loadReferrals = async () => {
    setReferralBusy(true); setError("");
    try { setReferralData(await customerRequest("/customer-auth/referrals")); }
    catch (reason) { setError(reason.message || "Could not load your referral information."); }
    finally { setReferralBusy(false); }
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
  const submitSupportTicket = async event => {
    event.preventDefault();
    setTicketBusy(true); setError(""); setTicketCreated(null); setTicketTracked(null);
    try {
      const result = await apiRequest("/customers/support-portal/tickets", { method: "POST", skipAuth: true, body: JSON.stringify(ticketDraft) });
      setTicketCreated(result.ticket);
      setTicketLookup(old => ({ ...old, caseNumber: result.ticket.case_number, email: ticketDraft.email, phone: ticketDraft.phone }));
      setTicketDraft(old => ({ ...old, subject: "", description: "" }));
    } catch (reason) { setError(reason.message || "Could not create your support ticket."); }
    finally { setTicketBusy(false); }
  };
  const submitInsuranceRequest = async event => {
    event.preventDefault();
    setTicketBusy(true); setError(""); setTicketCreated(null); setTicketTracked(null);
    const form = event.currentTarget;
    const data = new FormData(form);
    const service = String(data.get("insuranceType") || "Life Insurance");
    const payload = {
      name: String(data.get("name") || "").trim(),
      phone: String(data.get("phone") || "").trim(),
      email: String(data.get("email") || "").trim(),
      subject: "Insurance consultation request — " + service,
      description: "Customer requested a consultation for " + service + ". Consultation fee: ₹100. Preferred contact time: " + String(data.get("contactTime") || "Any time") + ". Customer message: " + String(data.get("message") || "").trim(),
    };
    try {
      const result = await apiRequest("/customers/support-portal/tickets", { method: "POST", skipAuth: true, body: JSON.stringify(payload) });
      setTicketCreated(result.ticket);
      setTicketLookup(old => ({ ...old, caseNumber: result.ticket.case_number, email: payload.email, phone: payload.phone }));
      form.reset();
      setNotice("Your insurance consultation request has been submitted. Our team will contact you.");
    } catch (reason) {
      setError(reason.message || "Could not submit your consultation request. Please try again.");
    } finally { setTicketBusy(false); }
  };
  const submitPartnerEnquiry = async event => {
    event.preventDefault();
    setPartnerBusy(true); setPartnerResult(null); setError("");
    const form = event.currentTarget;
    const data = new FormData(form);
    const payload = { name: String(data.get("name") || "").trim(), business_name: String(data.get("business") || "").trim(), phone: String(data.get("phone") || "").trim(), email: String(data.get("email") || "").trim(), partnership_type: String(data.get("partnerType") || ""), message: String(data.get("message") || "").trim() };
    try {
      const result = await apiRequest("/loyalty/partner-enquiries", { method: "POST", skipAuth: true, body: JSON.stringify(payload) });
      setPartnerResult(result); form.reset();
    } catch (reason) { setPartnerResult({ error: reason.message || "Could not submit your enquiry. Please try again." }); }
    finally { setPartnerBusy(false); }
  };
  const trackSupportTicket = async event => {
    event.preventDefault(); setTicketBusy(true); setError(""); setTicketTracked(null);
    try {
      const params = new URLSearchParams();
      if (ticketLookup.email.trim()) params.set("email", ticketLookup.email.trim());
      if (ticketLookup.phone.trim()) params.set("phone", ticketLookup.phone.trim());
      const result = await apiRequest("/customers/support-portal/tickets/" + encodeURIComponent(ticketLookup.caseNumber.trim()) + "?" + params.toString(), { skipAuth: true });
      setTicketTracked(result.ticket);
    } catch (reason) { setError(reason.message || "Could not find that ticket."); }
    finally { setTicketBusy(false); }
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
        const productCategoryIds = Array.isArray(product.category_ids) ? product.category_ids.map(String) : [String(product.category_id || "")];
        const matches = (selected && (productCategoryIds.includes(String(selected.id)) || String(product.category_id || "") === String(selected.id)) )
          || (targetName && (String(productCategoryName).trim().toLowerCase() === String(targetName).trim().toLowerCase() || productCategoryIds.some(id => String(categories.find(c => String(c.id) === id)?.name || "").trim().toLowerCase() === String(targetName).trim().toLowerCase())));
        if (!matches) return false;
      }
      return !term || [v.product_name, product.name, v.sku, product.brand].some(x => String(x || "").toLowerCase().includes(term));
    });
  }, [variants, productById, categoryId, routeCategoryName, search, displayCategories]);
  const displayedVariants = (isWishlistPage ? visibleVariants.filter(v => wishlist.some(id => Number(id) === Number(v.id))) : visibleVariants).filter((variant, index, items) => items.findIndex(item => Number(item.product_id) === Number(variant.product_id)) === index);
  const rememberViewed = variant => {
    const entry = { variantId: variant.id, productId: variant.product_id, viewedAt: Date.now() };
    setRecentlyViewed(old => {
      const next = [entry, ...old.filter(item => Number(item.variantId) !== Number(variant.id))].slice(0, 12);
      try { sessionStorage.setItem("sb-recently-viewed", JSON.stringify(next)); } catch {}
      return next;
    });
  };
  // Discovery placements are explicit product-category assignments, never inferred from
  // creation dates or sales. Each section contains one card per parent product.
  const assignedSectionProducts = useMemo(() => sectionName => {
    const section = categories.find(category => String(category.name || "").trim().toLowerCase() === sectionName.toLowerCase());
    if (!section) return [];
    const seen = new Set();
    return variants.filter(variant => {
      if (variant.is_active === false) return false;
      const productId = Number(variant.product_id);
      if (!productId || seen.has(productId)) return false;
      const product = productById.get(productId);
      if (!product) return false;
      const assignedIds = Array.isArray(product.category_ids) ? product.category_ids.map(String) : [String(product.category_id || "")];
      const explicitlyAssigned = assignedIds.includes(String(section.id)) || String(product.category_id || "") === String(section.id);
      if (explicitlyAssigned) seen.add(productId);
      return explicitlyAssigned;
    }).slice(0, 8);
  }, [categories, variants, productById]);
  const newArrivals = useMemo(() => assignedSectionProducts("New Arrivals"), [assignedSectionProducts]);
  const bestSellers = useMemo(() => assignedSectionProducts("Best Sellers"), [assignedSectionProducts]);
  const recentVariants = useMemo(() => recentlyViewed.map(item => variants.find(v => Number(v.id) === Number(item.variantId))).filter(Boolean).filter((variant, index, items) => items.findIndex(item => Number(item.product_id) === Number(variant.product_id)) === index).slice(0,8), [recentlyViewed, variants]);
  const categorySubcategories = useMemo(() => {
    const parent = displayCategories.find(c => String(c.name || "").trim().toLowerCase() === String(routeCategoryName).trim().toLowerCase());
    if (!parent) return [];
    return categories.filter(c => [c.parent_id, c.parent_category_id, c.parentId].some(id => id != null && String(id) === String(parent.id)));
  }, [categories, displayCategories, routeCategoryName]);
  const subcategoryProductRows = useMemo(() => categorySubcategories.map(category => {
    const items = variants.filter((variant, index, allVariants) => {
      const productId = Number(variant.product_id);
      if (allVariants.findIndex(item => Number(item.product_id) === productId) !== index) return false;
      const product = productById.get(productId);
      if (!product) return false;
      const productCategoryId = product.category_id ?? product.categoryId;
      const productCategoryName = product.category_name || product.category || "";
      const assignedIds = Array.isArray(product.category_ids) ? product.category_ids.map(String) : [String(productCategoryId || "")];
      return assignedIds.includes(String(category.id))
        || (productCategoryId != null && String(productCategoryId) === String(category.id))
        || String(productCategoryName).trim().toLowerCase() === String(category.name || "").trim().toLowerCase();
    }).slice(0, 24);
    return { category, items };
  }).filter(row => row.items.length > 0), [categorySubcategories, variants, productById]);
  const dealVariants = useMemo(() => {
    const term = search.trim().toLowerCase();
    const discounted = variants.filter(v => {
      const p = productById.get(Number(v.product_id)) || {};
      const price = Number(v.selling_price ?? v.price ?? 0);
      const compare = Number(v.compare_at_price ?? v.original_price ?? v.mrp ?? p.compare_at_price ?? p.original_price ?? p.mrp ?? 0);
      const discount = Number(v.discount_percent ?? v.discount_percentage ?? p.discount_percent ?? p.discount_percentage ?? 0);
      const matchesSearch = !term || [v.product_name, p.name, v.sku, p.brand].some(value => String(value || "").toLowerCase().includes(term));
      return matchesSearch && (((compare > price) && price > 0) || discount > 0);
    });
    return discounted.filter((variant, index, all) => all.findIndex(item => Number(item.product_id) === Number(variant.product_id)) === index).slice(0, 24);
  }, [variants, productById, search]);
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
    if (!customerToken || !customerAuth) { openCustomerAuth("login", "/checkout"); return; }
    if (!cart.length) { setError("Add at least one item to your basket."); return; }
    setSubmitting(true); setError(""); setNotice(""); setOrder(null);
    try {
      const created = await customerRequest("/orders", {
        method: "POST",
        body: JSON.stringify({
          channel: "website",
          customer_name: customerAuth.full_name,
          customer_phone: customer.phone.trim() || null,
          customer_email: customerAuth.email,
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

  async function loadCustomerLoyalty() {
    if (!customerToken || !customerAuth) { openCustomerAuth("login", "/account"); return; }
    setLoyaltyBusy(true); setError(""); setLoyaltyCustomerData(null);
    try {
      const result = await customerRequest("/loyalty/customer/me");
      setLoyaltyCustomerData(result);
    } catch (reason) {
      setError(reason.message || "Could not load your Super Coin card.");
    } finally { setLoyaltyBusy(false); }
  }

  function renderProductCard(variant) {
    const product = productById.get(Number(variant.product_id));
    const categoryName = product?.category_name || product?.category || orderedCategories.find(c => String(c.id) === String(product?.category_id))?.name;
    const tile = categoryArt[categoryName] || art[0];
    const productVariants = variants.filter(item => Number(item.product_id) === Number(variant.product_id) && item.is_active !== false);
    const hasSelectableVariants = productVariants.some(item => Object.keys(item.attributes || {}).length > 0);
    const prices = productVariants.map(item => Number(item.selling_price || 0));
    const minPrice = prices.length ? Math.min(...prices) : Number(variant.selling_price || 0);
    const maxPrice = prices.length ? Math.max(...prices) : minPrice;
    const saved = productVariants.some(item => wishlist.some(id => Number(id) === Number(item.id)));
    const openDetails = () => openProductPage(variant);
    return <article className="storefront-product-card" key={variant.product_id} role="link" tabIndex={0} onClick={openDetails} onKeyDown={event => { if (event.target === event.currentTarget && (event.key === "Enter" || event.key === " ")) { event.preventDefault(); openDetails(); } }}>
      <div className="storefront-product-art">{variant.image_url ? <img className="storefront-product-image" src={variant.image_url} alt={product?.name || variant.product_name || "Product"} loading="lazy"/> : <span>{tile.icon}</span>}<button type="button" className={"storefront-wishlist " + (saved ? "is-saved" : "")} onClick={event => event.stopPropagation()} aria-label={(saved ? "Remove from" : "Add to") + " wishlist: " + (product?.name || variant.sku)} aria-pressed={saved} onClick={() => setWishlist(old => saved ? old.filter(id => !productVariants.some(item => Number(item.id) === Number(id))) : [...new Set([...old, ...productVariants.map(item => Number(item.id))])])}><Heart size={19} strokeWidth={1.9} fill={saved ? "currentColor" : "none"} /></button></div>
      <small>{product?.brand || product?.name || "Super Bajaar"}</small>
      <h3><button type="button" className="storefront-product-title" onClick={event => { event.stopPropagation(); openDetails(); }}>{product?.name || variant.product_name || variant.sku}</button></h3>
      {hasSelectableVariants && <p className="storefront-sku">Choose colour, size or weight</p>}
      <strong>{minPrice === maxPrice ? money(minPrice) : money(minPrice) + " – " + money(maxPrice)}</strong>
      <span className="storefront-product-coins"><Coins size={14} /> Earn up to {Math.floor(Number(minPrice || 0) / 100 * Number((loyaltyRules.find(rule => rule.scope_type === "product" && Number(rule.scope_id) === Number(product?.id)) || loyaltyRules.find(rule => rule.scope_type === "category" && Number(rule.scope_id) === Number(product?.category_id)) || loyaltyRules.find(rule => rule.scope_type === "default"))?.coins_per_100 ?? loyaltyDefaultRate))} Super Coins</span>
      {hasSelectableVariants ? <button type="button" className="storefront-add" onClick={event => { event.stopPropagation(); openDetails(); }}>Choose options</button> : <button type="button" className="storefront-add" onClick={event => { event.stopPropagation(); addToCart(variant); }}><ShoppingBag size={17} strokeWidth={2} /> Add to basket</button>}
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
      <div className="storefront-actions"><button type="button" className="storefront-delivery" onClick={() => { setDeliveryDraft(deliveryPin); setDeliveryMessage(""); setDeliveryOpen(true); }} aria-haspopup="dialog"><small>Deliver to</small><strong><MapPin size={13} /> {deliveryPin || "Set PIN"} ▾</strong></button><a className="storefront-icon-action" href="/wishlist" aria-label={`Open wishlist, ${wishlist.length} saved`} onClick={event => { event.preventDefault(); openWishlist(); }}><Heart size={22} strokeWidth={1.8} /><small>{wishlist.length}</small></a><a className="storefront-icon-action" href="#basket" aria-label="Shopping basket" onClick={event => { event.preventDefault(); openCheckout(); }}><ShoppingBag size={22} strokeWidth={1.8} /><small>{cart.reduce((n, line) => n + line.quantity, 0)}</small></a><div className="storefront-account-wrap"><button type="button" className="storefront-account-button" aria-label="Open account menu" aria-expanded={accountOpen} onClick={() => setAccountOpen(value => !value)}><UserRound size={20} /><span>Account</span></button>{accountOpen && <div className="storefront-account-menu storefront-account-menu-desktop"><strong>Your account</strong><p>{customerAuth ? "Manage your profile, orders and Super Coins." : "Sign in to manage orders, referrals and Super Coins."}</p><button type="button" onClick={customerAuth ? openAccount : () => openCustomerAuth("login", "/account")}>{customerAuth ? "My Account" : "Customer Sign in"}</button>{customerAuth && <button type="button" onClick={signOutCustomer}>Sign out</button>}{canOpenAdmin && <a href="/admin">Admin Console</a>}</div>}</div></div>
    </header>
    {accountOpen && <div className="storefront-account-sheet-backdrop" role="presentation" onClick={event => { if (event.target === event.currentTarget) setAccountOpen(false); }}><section className="storefront-account-sheet" role="dialog" aria-modal="true" aria-labelledby="storefront-account-sheet-title"><div className="storefront-account-sheet-handle" aria-hidden="true" /><div className="storefront-account-sheet-heading"><div><span className="storefront-kicker">SUPER BAJAAR</span><h2 id="storefront-account-sheet-title">Your account</h2></div><button type="button" className="storefront-modal-close" aria-label="Close account menu" onClick={() => setAccountOpen(false)}><X size={19} /></button></div><p>Manage your profile and shopping experience.</p><button type="button" className="storefront-account-sheet-action" onClick={customerAuth ? openAccount : () => { setAccountOpen(false); openCustomerAuth("login", "/account"); }}><span className="storefront-account-sheet-action-icon"><UserRound size={20} /></span><span><strong>{customerAuth ? "My Account" : "Customer Sign in"}</strong><small>{customerAuth ? "Contact and delivery details" : "Sign in to manage your account"}</small></span><span aria-hidden="true">›</span></button>{customerAuth && <button type="button" className="storefront-account-sheet-action" onClick={signOutCustomer}><span className="storefront-account-sheet-action-icon">↪</span><span><strong>Sign out</strong><small>Sign out of your customer account</small></span><span aria-hidden="true">›</span></button>}{canOpenAdmin && <a className="storefront-account-sheet-action" href="/admin"><span className="storefront-account-sheet-action-icon">⌘</span><span><strong>Admin Console</strong><small>Store management</small></span><span aria-hidden="true">›</span></a>}</section></div>}
    <nav className="storefront-department-nav" aria-label="Shop departments"><a href="/#categories" onClick={event => { event.preventDefault(); openShopHome(); setTimeout(() => document.getElementById("categories")?.scrollIntoView({ behavior: "smooth" }), 0); }}>☰ All Categories</a><a href="/deals" onClick={event => { event.preventDefault(); openDealsPage(); }}>Deals <Flame size={14} /></a><button type="button" onClick={() => { openShopHome(); setTimeout(() => document.getElementById("products")?.scrollIntoView({ behavior: "smooth" }), 0); }}>Shop All</button>{displayCategories.map(category => <a key={category.id} href={"/category/" + categorySlug(category.name)} aria-current={routeSlug === categorySlug(category.name) ? "page" : undefined}>{category.name === "Fresh Daily" ? "Fresh" : category.name}</a>)}</nav>
    {!isProductPage && !isCustomerAuthPage && !isCategoryPage && !isDealsPage && !isWishlistPage && !isAccountPage && !isCheckoutPage && !isInfoPage && <section className="storefront-hero">
      <div className="storefront-hero-copy"><span className="storefront-kicker"><i /> YOUR EVERYDAY SUPER STORE</span><h1>Welcome to<br /><em>Super Bajaar</em></h1><p>Everything you need, all in one place. Explore everyday essentials and discover something new for your home and family.</p><a className="storefront-primary" href="#products">Shop Now <span>→</span></a><div className="storefront-trust"><span>✦ Thoughtfully picked</span><span>✦ Made for everyday</span></div></div>
      <div className="storefront-hero-art" aria-label="Colourful shopping bags and everyday products" role="img"><div className="art-sun" /><div className="art-orbit orbit-one" /><div className="art-orbit orbit-two" /><div className="art-spark spark-one">✦</div><div className="art-spark spark-two">✳</div><div className="art-bag bag-purple"><span>S</span></div><div className="art-bag bag-orange"><span>♥</span></div><div className="art-box"><span>GOOD</span><strong>THINGS</strong></div><div className="art-leaf leaf-one">✦</div><div className="art-leaf leaf-two">✿</div><div className="art-caption">A little joy in every basket</div></div>
    </section>}
    {!isProductPage && !isCategoryPage && !isDealsPage && !isWishlistPage && !isAccountPage && !isCheckoutPage && !isInfoPage && <section className="storefront-categories" id="categories">
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
    {isCustomerAuthPage && <section className="storefront-checkout-page">
      <div className="storefront-category-breadcrumb"><button type="button" onClick={openShopHome}>Home</button><span>/</span><span>{customerAuthMode === "register" ? "Create account" : "Customer sign in"}</span></div>
      <div className="storefront-checkout-page-heading"><span className="storefront-kicker">YOUR SUPER BAJAAR</span><h1>{customerAuthMode === "register" ? "Create your customer account" : "Welcome back"}</h1><p>Customer sign-in is separate from the Admin Console. Your basket will be kept while you sign in.</p></div>
      {error && <p className="storefront-alert" role="alert">{error}</p>}{notice && <p className="storefront-order-success" role="status">{notice}</p>}
      <form className="storefront-checkout-form" onSubmit={submitCustomerAuth}>
        {customerAuthMode === "register" && <label>Full name<input required minLength="2" maxLength="200" autoComplete="name" value={customerAuthDraft.full_name} onChange={e=>setCustomerAuthDraft(old=>({...old,full_name:e.target.value}))}/></label>}
        <label>Email address<input required type="email" maxLength="254" autoComplete="email" value={customerAuthDraft.email} onChange={e=>setCustomerAuthDraft(old=>({...old,email:e.target.value}))}/></label>
        {customerAuthMode === "register" && <label>Mobile number <span aria-hidden="true">*</span><input required type="tel" minLength="7" maxLength="20" autoComplete="tel" value={customerAuthDraft.phone} onChange={e=>setCustomerAuthDraft(old=>({...old,phone:e.target.value}))}/></label>}
        <label>Password<input required type="password" minLength={customerAuthMode === "register" ? 10 : 1} maxLength="1024" autoComplete={customerAuthMode === "register" ? "new-password" : "current-password"} value={customerAuthDraft.password} onChange={e=>setCustomerAuthDraft(old=>({...old,password:e.target.value}))}/>{customerAuthMode === "register" && <small>Use at least 10 characters.</small>}</label>
        {customerAuthMode === "register" && <label>Referral code (optional)<input maxLength="24" autoComplete="off" value={customerAuthDraft.referral_code} onChange={e=>setCustomerAuthDraft(old=>({...old,referral_code:e.target.value.toUpperCase()}))} placeholder="Enter a friend's code"/></label>}
        <button type="submit" className="storefront-primary" disabled={customerAuthBusy}>{customerAuthBusy ? "Please wait…" : customerAuthMode === "register" ? "Create account" : "Sign in and continue"}</button>
        <p className="storefront-account-note">{customerAuthMode === "register" ? "Already registered? " : "New to Super Bajaar? "}<button type="button" className="storefront-inline-link" onClick={()=>{setCustomerAuthMode(customerAuthMode==="register"?"login":"register");setError("");}}>{customerAuthMode === "register" ? "Sign in" : "Create an account"}</button></p>
      </form>
    </section>}
    {isCheckoutPage && <section className="storefront-checkout-page"><div className="storefront-category-breadcrumb"><button type="button" onClick={openShopHome}>Home</button><span>/</span><span>Checkout</span></div><div className="storefront-checkout-page-heading"><span className="storefront-kicker">YOUR BASKET</span><h1>Checkout</h1><p>Review your items and delivery details before placing your order.</p></div>{error && <p className="storefront-alert" role="alert">{error}</p>}{notice && <p className="storefront-order-success" role="status">{notice}</p>}{order && <p className="storefront-order-success" role="status">Order placed: <strong>{order.order_number}</strong> · {money(order.total)}</p>}<section className="storefront-checkout" id="basket"><div><span className="storefront-kicker">ORDER SUMMARY</span><h2>Your basket</h2><p>Prices and order totals are calculated by the server. Online payment collection is not enabled yet.</p></div><div className="storefront-basket-lines">{cart.length ? cart.map(line => <div className="storefront-basket-line" key={line.id}><div><strong>{line.product_name || line.sku}</strong><small>{line.sku} · {money(line.selling_price)}</small></div><label>Qty<input type="number" min="0" max="100000" step="1" value={line.quantity} onChange={e => setQuantity(line.id, e.target.value)} /></label><strong>{money(line.selling_price * line.quantity)}</strong><button type="button" aria-label={"Remove " + line.sku} onClick={() => setCart(old => old.filter(x => x.id !== line.id))}>×</button></div>) : <div className="storefront-checkout-empty"><h3>Your basket is empty</h3><p>Add products to your basket before placing an order.</p><button type="button" className="storefront-primary" onClick={openShopHome}>Continue shopping</button></div>}<div className="storefront-basket-total"><span>Subtotal</span><strong>{money(total)}</strong></div>{cart.length>0 && <form className="storefront-checkout-form" onSubmit={checkout}><label>Full name<input required minLength="1" maxLength="200" value={customer.name} onChange={e => setCustomer(v => ({ ...v, name: e.target.value }))} /></label><label>Email address<input type="email" autoComplete="email" required maxLength="254" value={customer.email} onChange={e => setCustomer(v => ({ ...v, email: e.target.value }))} /></label><label>Phone (optional)<input maxLength="20" value={customer.phone} onChange={e => setCustomer(v => ({ ...v, phone: e.target.value }))} /></label><label>Delivery PIN (optional)<input inputMode="numeric" pattern="[0-9]{6}" maxLength="6" value={customer.pin} onChange={e => setCustomer(v => ({ ...v, pin: e.target.value }))} /></label><button type="submit" className="storefront-primary" disabled={submitting || !cart.length}>{submitting ? "Placing order…" : "Place order"}</button></form>}</div></section></section>}
    {isAccountPage && <section className="storefront-account-page">
      <div className="storefront-category-breadcrumb"><button type="button" onClick={openShopHome}>Home</button><span>/</span><span>My Account</span></div>
      <div className="storefront-account-welcome"><span className="storefront-kicker">YOUR SUPER BAJAAR</span><h1>{customer.name.trim() ? `Hello, ${customer.name.trim().split(/\s+/)[0]}` : "My Account"}</h1><p>Manage your profile, purchases and support in one place.</p></div>
      <div className="storefront-account-layout">
        <nav className="storefront-account-nav" aria-label="Customer account sections">
          {[["overview","Overview","user-round"],["loyalty","Loyalty Card & Coins","coins"],["referrals","Refer & Earn","users"],["orders","My Orders","package"],["tickets","My Tickets","ticket"],["wishlist","My Wishlist","heart"],["addresses","Addresses","map-pin"],["security","Security","shield-check"]].map(([key,label])=><button key={key} type="button" className={accountSection===key?"is-active":""} onClick={()=>{if(key==="wishlist"){openWishlist();return;}setAccountSection(key);setNotice("");setError("");if(key==="referrals") loadReferrals();if(key==="loyalty") loadCustomerLoyalty();}}>{label}<span aria-hidden="true">›</span></button>)}
        </nav>
        <div className="storefront-account-panel">
          {accountSection==="overview" && <div className="storefront-account-section">
            <div className="storefront-account-section-heading"><div><h2>Personal details</h2><p>Your saved contact information.</p></div><span className="storefront-account-avatar">{customer.name.trim()?customer.name.trim().slice(0,1).toUpperCase():"S"}</span></div>
            {(customer.name||customer.email||customer.phone) ? <div className="storefront-account-summary">{customer.name&&<div><small>Full name</small><strong>{customer.name}</strong></div>}{customer.email&&<div><small>Email address</small><strong>{customer.email}</strong></div>}{customer.phone&&<div><small>Mobile number</small><strong>{customer.phone}</strong></div>}</div> : <p className="storefront-account-empty">Your profile is not filled in yet. Add your details below so they are ready at checkout.</p>}
            <form className="storefront-account-form" onSubmit={saveCustomerProfile}><label>Full name<input autoComplete="name" required maxLength="200" value={customer.name} onChange={event=>setCustomer(old=>({...old,name:event.target.value}))}/></label><label>Mobile number<input autoComplete="tel" maxLength="20" value={customer.phone} onChange={event=>setCustomer(old=>({...old,phone:event.target.value}))}/></label><label>Email address<input type="email" autoComplete="email" maxLength="254" value={customer.email} onChange={event=>setCustomer(old=>({...old,email:event.target.value}))}/></label><button className="storefront-primary" type="submit">Save profile</button><p className="storefront-account-note">Your sign-in identity is stored securely by Super Bajaar. Address syncing is a separate feature.</p><button type="button" className="storefront-primary" onClick={signOutCustomer}>Sign out</button></form>
          </div>}
          {accountSection==="loyalty" && <div className="storefront-account-section">
            <span className="storefront-kicker">REWARDS FOR EVERYDAY SHOPPING</span>
            <h2>Loyalty Card &amp; Super Coins</h2>
            <p>Earn Super Coins on eligible purchases. The standard rate is {loyaltyDefaultRate} coin(s) per ₹100 eligible spend unless a product or category override applies.</p>
            <button className="storefront-primary" type="button" onClick={loadCustomerLoyalty} disabled={loyaltyBusy}>{loyaltyBusy ? "Loading card…" : "Refresh my Super Coin card"}</button>
            {loyaltyCustomerData && <><div className="storefront-loyalty-card">
              <div className="storefront-loyalty-card-top"><span className="storefront-loyalty-mark">S</span><span>SUPER BAJAAR<br/><strong>LOYALTY CARD</strong></span><CreditCard size={28}/></div>
              <div className="storefront-loyalty-card-bottom"><span>{customer.name.trim() || loyaltyCustomerData.account?.customer_email || "Super Bajaar Customer"}</span><strong>{loyaltyCustomerData.account?.card_number || "CARD AFTER FIRST DELIVERY"}</strong></div>
            </div>
            <div className="storefront-loyalty-summary">
              <article><Coins size={22}/><small>Available Super Coins</small><strong>{Number(loyaltyCustomerData.available_coins || 0).toLocaleString("en-IN")}</strong><span>Only unexpired coins are available to use.</span></article>
              <article><CalendarClock size={22}/><small>Expiry policy</small><strong>365 days</strong><span>Each earned lot expires 365 days after credit. Oldest unexpired coins are allocated first (FIFO).</span></article>
            </div>
            {!loyaltyCustomerData.account && <p className="storefront-account-note" role="status">{loyaltyCustomerData.message}</p>}
            {loyaltyCustomerData.account && <div className="storefront-account-summary"><h3>Recent loyalty activity</h3>{loyaltyCustomerData.items.length ? loyaltyCustomerData.items.map(item=><div key={item.id}><small>{item.transaction_type.toUpperCase()} · {new Date(item.created_at).toLocaleString()}</small><strong>{item.coins} Super Coins{item.expires_at ? " · Expires " + new Date(item.expires_at).toLocaleDateString() : ""}</strong><span>{item.description || item.order_reference || "Loyalty activity"}</span></div>) : <p>No loyalty transactions yet.</p>}</div>}
            </>}
            <div className="storefront-loyalty-note"><strong>How it works</strong><p>Coins are credited only after an order is marked delivered. Product-specific earning rules override category rules, which override the default. Coins expire after 365 days.</p><p>Customer redemption at checkout is not enabled yet; the rupee value of one Super Coin has not been defined in the current programme rules.</p></div>
            {error && <p className="storefront-account-note" role="alert">{error}</p>}
          </div>}
          {accountSection==="referrals" && <div className="storefront-account-section">
      <span className="storefront-kicker">SHARE THE SUPER BAJAAR LOVE</span><h2>Refer &amp; Earn</h2>
      <p>Share your unique referral code with friends. Their sign-up will be linked to your account so referrals can be tracked.</p>
      {referralBusy && <p className="storefront-account-note">Loading referral details…</p>}
      {referralData && <>
        <div className="storefront-loyalty-card"><div className="storefront-loyalty-card-top"><span className="storefront-loyalty-mark">S</span><span>SUPER BAJAAR<br/><strong>REFERRAL CODE</strong></span><UserRound size={28}/></div><div className="storefront-loyalty-card-bottom"><span>Your unique code</span><strong>{referralData.referral_code}</strong></div></div>
        <label className="storefront-account-form">Referral link<input readOnly value={window.location.origin + (referralData.referral_link_path || ("/customer/register?ref=" + referralData.referral_code))}/></label>
        <button type="button" className="storefront-primary" onClick={async()=>{const link=window.location.origin+(referralData.referral_link_path||("/customer/register?ref="+referralData.referral_code));try{await navigator.clipboard.writeText(link);setNotice("Referral link copied.");}catch{setNotice("Your referral code is "+referralData.referral_code+". Copy it to share.");}}}>Copy referral link</button>
        <div className="storefront-account-summary"><div><small>Tracked referrals</small><strong>{(referralData.items||[]).length}</strong></div><div><small>Reward status</small><strong>100 coins each after first delivery</strong></div></div>
        <p className="storefront-account-note">{referralData.reward_status || "Both the referrer and new customer receive 100 Super Coins each after the referred customer’s first order is delivered."}</p>
        {(referralData.items||[]).length ? <div className="storefront-account-summary"><h3>Your referrals</h3>{referralData.items.map(item=><div key={item.id}><small>{new Date(item.created_at).toLocaleDateString()} · {String(item.status||"tracked").replaceAll("_"," ")}</small><strong>{item.referred_customer}</strong><span>{item.status === "rewarded" ? "100 Super Coins awarded to each customer" : "100 Super Coins each after first delivery"}</span></div>)}</div> : <p className="storefront-account-empty">No referrals yet. Share your code to start building your referral list.</p>}
      </>}
      {error && <p className="storefront-account-note" role="alert">{error}</p>}
    </div>}
    {accountSection==="orders" && <div className="storefront-account-section"><h2>My Orders</h2><p>View purchases, order details and delivery updates.</p><div className="storefront-account-empty-state"><span>📦</span><h3>Order history needs customer sign-in</h3><p>Orders are recorded by the store, but this portal does not yet have a secure customer identity to retrieve only your orders. We will not show unverified order records here.</p></div></div>}
          {accountSection==="tickets" && <div className="storefront-account-section">
            <h2>My Tickets</h2><p>Create a support request or track an existing ticket using the contact details registered with it.</p>
            <form className="storefront-account-form" onSubmit={submitSupportTicket}>
              <h3>Raise a ticket</h3>
              <label>Full name<input autoComplete="name" required maxLength="200" value={ticketDraft.name} onChange={event=>setTicketDraft(old=>({...old,name:event.target.value}))}/></label>
              <label>Mobile number<input autoComplete="tel" required minLength="7" maxLength="20" value={ticketDraft.phone} onChange={event=>setTicketDraft(old=>({...old,phone:event.target.value}))}/></label>
              <label>Email address<input type="email" autoComplete="email" required maxLength="254" value={ticketDraft.email} onChange={event=>setTicketDraft(old=>({...old,email:event.target.value}))}/></label>
              <label>Subject<input required minLength="3" maxLength="200" value={ticketDraft.subject} onChange={event=>setTicketDraft(old=>({...old,subject:event.target.value}))}/></label>
              <label>How can we help?<textarea required rows="4" maxLength="5000" value={ticketDraft.description} onChange={event=>setTicketDraft(old=>({...old,description:event.target.value}))}/></label>
              <button className="storefront-primary" type="submit" disabled={ticketBusy}>{ticketBusy?"Submitting…":"Create support ticket"}</button>
            </form>
            {ticketCreated && <div className="storefront-account-summary" role="status"><div><small>Ticket created</small><strong>{ticketCreated.case_number}</strong></div><p>Save this reference. Use both the same email and phone below to track updates.</p></div>}
            <form className="storefront-account-form" onSubmit={trackSupportTicket}>
              <h3>Track a ticket</h3>
              <label>Ticket reference<input required placeholder="SUP-XXXXXXXXXX" value={ticketLookup.caseNumber} onChange={event=>setTicketLookup(old=>({...old,caseNumber:event.target.value.toUpperCase()}))}/></label>
              <label>Email used for the ticket<input type="email" required maxLength="254" value={ticketLookup.email} onChange={event=>setTicketLookup(old=>({...old,email:event.target.value}))}/></label>
              <label>Phone used for the ticket<input required maxLength="20" value={ticketLookup.phone} onChange={event=>setTicketLookup(old=>({...old,phone:event.target.value}))}/></label>
              <button className="storefront-primary" type="submit" disabled={ticketBusy || (!ticketLookup.email.trim() || !ticketLookup.phone.trim())}>{ticketBusy?"Checking…":"Track ticket"}</button>
            </form>
            {ticketTracked && <div className="storefront-account-summary" role="status"><div><small>Reference</small><strong>{ticketTracked.case_number}</strong></div><div><small>Subject</small><strong>{ticketTracked.subject}</strong></div><div><small>Status</small><strong>{String(ticketTracked.status).replaceAll("_"," ")}</strong></div><div><small>Last updated</small><strong>{ticketTracked.updated_at ? new Date(ticketTracked.updated_at).toLocaleString() : "Not available"}</strong></div>{ticketTracked.resolution && <div><small>Support response</small><strong>{ticketTracked.resolution}</strong></div>}</div>}
            {error && <p className="storefront-account-note" role="alert">{error}</p>}
          </div>}
          {accountSection==="addresses" && <div className="storefront-account-section"><h2>Addresses</h2><p>Manage your preferred delivery address and PIN code.</p><form className="storefront-account-form" onSubmit={saveCustomerProfile}><label>Delivery PIN<input inputMode="numeric" autoComplete="postal-code" pattern="[1-9][0-9]{5}" maxLength="6" value={customer.pin} onChange={event=>setCustomer(old=>({...old,pin:event.target.value.replace(/\\D/g,"").slice(0,6)}))}/></label><label className="storefront-account-address">Delivery address<textarea autoComplete="street-address" rows="3" maxLength="1000" value={customer.address} onChange={event=>setCustomer(old=>({...old,address:event.target.value}))}/></label><button className="storefront-primary" type="submit">Save address</button><p className="storefront-account-note">Address is currently saved on this device, not synced to a signed-in customer account.</p></form></div>}
          {accountSection==="security" && <div className="storefront-account-section"><h2>Security</h2><p>Protect your account and keep your contact details verified.</p><div className="storefront-security-list"><div><span><strong>Change password</strong><small>Change the password used to sign in.</small></span><button type="button" disabled>Not available yet</button></div><div><span><strong>Update mobile number</strong><small>Requires OTP verification of the new number.</small></span><button type="button" disabled>OTP setup required</button></div><div><span><strong>Update email address</strong><small>Requires verification of the new email address.</small></span><button type="button" disabled>Email verification required</button></div><div><span><strong>Login sessions</strong><small>Review and end active customer sessions.</small></span><button type="button" disabled>Customer sign-in required</button></div></div><p className="storefront-account-note">These actions are not enabled because customer authentication and verification are not implemented yet. We will not simulate security changes in the browser.</p></div>}
          {notice && <p className="storefront-order-success" role="status">{notice}</p>}
        </div>
      </div>
    </section>}
    {isInfoPage && <section className="storefront-info-page"><div className="storefront-category-breadcrumb"><button type="button" onClick={openShopHome}>Home</button><span>/</span><span>Information</span></div>
      {infoSlug === "seller-registration" && <><span className="storefront-kicker">GROW WITH SUPER BAJAAR</span><h1>Partner with Us</h1><p>Bring your products, brand or delivery expertise to Super Bajaar. We welcome enquiries from sellers, brands, suppliers and logistics partners. Every enquiry is reviewed before onboarding; submitting this form does not guarantee acceptance.</p><div className="storefront-partner-cards"><article><strong>Sell on Super Bajaar</strong><p>Introduce eligible products to everyday shoppers.</p></article><article><strong>Brand &amp; supplier partnerships</strong><p>Discuss product range, supply capacity and commercial terms.</p></article><article><strong>Delivery &amp; logistics</strong><p>Explore service coverage and fulfilment partnerships.</p></article></div><form className="storefront-partner-form" onSubmit={submitPartnerEnquiry}><h2>Tell us about your business</h2><label>Your name<input name="name" required maxLength="120" /></label><label>Business / brand name<input name="business" required maxLength="160" /></label><label>Phone number<input name="phone" required minLength="7" maxLength="20" /></label><label>Email address<input name="email" type="email" required maxLength="254" /></label><label>Partnership type<select name="partnerType" required><option value="">Choose a partnership</option><option>Seller</option><option>Brand</option><option>Supplier</option><option>Delivery / logistics</option><option>Other</option></select></label><label>How would you like to partner?<textarea name="message" rows="4" required maxLength="3000" /></label><button className="storefront-primary" type="submit" disabled={partnerBusy}>{partnerBusy ? "Submitting…" : "Send partnership enquiry"}</button>{partnerResult && <p className={partnerResult.error ? "storefront-alert" : "storefront-order-success"} role="status">{partnerResult.error || partnerResult.message}</p>}<p className="storefront-info-note">Your enquiry is submitted to Super Bajaar for review. Onboarding is subject to approval.</p></form></>}
      {infoSlug === "loyalty-programme" && <><span className="storefront-kicker">CUSTOMER REWARDS</span><h1>Loyalty Programme</h1><p>Super Bajaar customers earn Super Coins on eligible purchases after delivery is confirmed. The default earning rate is 1 coin per ₹100 eligible spend, unless a product or category override is configured by the store.</p><p>Coins expire 365 days after credit. The account area lets you verify an order using the email and order reference to view your loyalty card, available balance and transaction history.</p><p className="storefront-info-note">One Super Coin is intended to equal ₹1 and be redeemable at checkout. Checkout redemption is not enabled until backend balance and accounting controls are implemented.</p></>}
      {infoSlug === "super-coins" && <><span className="storefront-kicker">REWARDS WALLET</span><h1>Super Coins</h1><p>Super Coins are earned on eligible orders after delivery is confirmed. The default rate is 1 coin per ₹100 eligible spend, with optional product and category overrides. Each credit expires 365 days after it is earned.</p><p>Use My Account → Loyalty Card &amp; Coins to verify an order and view your available balance and recent activity.</p><p className="storefront-info-note">Checkout redemption is not enabled yet because the rupee value per coin has not been defined.</p></>}
      {infoSlug === "feedback" && <><span className="storefront-kicker">HELP US IMPROVE</span><h1>Feedback</h1><p>We welcome suggestions about your shopping experience, product selection, website usability and customer support.</p><div className="storefront-contact-grid"><a href="mailto:kpmcenterprise@gmail.com?subject=Super%20Bajaar%20Feedback"><strong>Send feedback by email</strong><span>kpmcenterprise@gmail.com</span></a><a href="https://wa.me/917644841104?text=Super%20Bajaar%20feedback" target="_blank" rel="noreferrer"><strong>Share on WhatsApp</strong><span>Message customer support</span></a></div></>}
      {infoSlug === "cancellation-policy" && <><span className="storefront-kicker">ORDERS &amp; CANCELLATIONS</span><h1>Cancellation Policy</h1><p>If you need to cancel an order, contact customer support as soon as possible and provide your order number. Cancellation depends on the order’s processing and dispatch status; an order that has already been dispatched may need to follow the applicable return process.</p><p>Where a cancellation is accepted and a payment has been collected, eligible refunds are processed after verification. Bank or payment-provider settlement times may vary.</p><p>Contact <a href="mailto:kpmcenterprise@gmail.com">kpmcenterprise@gmail.com</a>, call <a href="tel:+917644841104">+91 76448 41104</a> or message <a href="https://wa.me/917644841104">WhatsApp support</a>.</p></>}
      {infoSlug === "about-us" && <><span className="storefront-kicker">OUR STORY</span><h1>About Super Bajaar</h1><p><strong>Super Bajaar</strong> is a retail brand owned and operated by <strong>KPMC Enterprises</strong>. Our aim is to make everyday shopping simpler by bringing daily essentials and multiple product categories together in one convenient place.</p><h2>Our brand</h2><p>Super Bajaar is the customer-facing shopping brand. KPMC Enterprises owns the brand and is responsible for its business operations. Product availability, prices, delivery options and applicable terms are displayed through the storefront and at checkout.</p><h2>Contact</h2><p>For customer assistance, email <a href="mailto:kpmcenterprise@gmail.com">kpmcenterprise@gmail.com</a> or call <a href="tel:+917644841104">+91 76448 41104</a>.</p></>}
      {infoSlug === "contact-us" && <><span className="storefront-kicker">WE ARE HERE TO HELP</span><h1>Customer Support</h1><p>Choose the channel that works best for you. For order-related issues, please include your order number when contacting us.</p><div className="storefront-contact-grid"><a href="tel:+917644841104"><strong>Call us</strong><span>+91 76448 41104</span></a><a href="https://wa.me/917644841104" target="_blank" rel="noreferrer"><strong>WhatsApp</strong><span>Chat with customer support</span></a><a href="mailto:kpmcenterprise@gmail.com"><strong>Email support</strong><span>kpmcenterprise@gmail.com</span></a><button type="button" onClick={openTicketCenter}><strong>Raise a ticket</strong><span>Open customer support in My Account</span></button></div><p className="storefront-info-note">Ticket creation and ticket-status tracking must be connected to the customer support backend before they can be submitted or tracked online.</p></>}
      {infoSlug === "privacy-policy" && <><span className="storefront-kicker">YOUR INFORMATION &amp; PRIVACY</span><h1>Privacy Policy</h1><p><strong>Effective date:</strong> 28 October 2026</p><p>Super Bajaar is a retail brand owned by KPMC Enterprises. This policy explains how information may be handled when you browse the Super Bajaar website, place an order or contact customer support. It should be read alongside the Terms &amp; Conditions.</p><h2>1. Information we may collect</h2><ul><li>Contact and delivery details you provide, such as name, phone number, email address, delivery address and PIN code.</li><li>Order details, products purchased, delivery preferences, return requests and communications with customer support or the grievance officer.</li><li>Technical and usage information that the website or its hosting/security services may process, such as device/browser information, diagnostic logs and basic interaction data.</li><li>Information needed to investigate fraud, protect the service or meet legal obligations.</li></ul><h2>2. How information is used</h2><p>Information may be used to process and fulfil orders, check delivery availability, provide customer support, handle returns and grievances, maintain website functionality, prevent misuse, maintain business records and comply with applicable law.</p><h2>3. Browser storage</h2><p>Some preferences, including the current customer profile and delivery PIN, may be stored locally in your browser on your device. Browser-stored profile information is not the same as a verified customer account and may not synchronise across devices. You can clear site data through your browser settings; doing so may remove locally saved preferences.</p><h2>4. Sharing and service providers</h2><p>Information may be shared only as reasonably needed with service providers that support hosting, website operation, order processing, delivery, communications, security or customer support, and with authorities where disclosure is required by law. The exact providers and data flows must be confirmed against the live production setup. We do not state that any specific payment, delivery or ticketing integration is active unless it is actually configured.</p><h2>5. Retention and security</h2><p>Information should be retained only for as long as reasonably needed for the purposes described above, including order records, customer requests, dispute handling and legal requirements. Appropriate technical and organisational safeguards should be maintained. No internet service can be represented as completely risk-free.</p><h2>6. Your requests</h2><p>You may contact us to ask about your information, request correction of inaccurate details or raise a privacy concern. We may need to verify your identity before acting on a request. Requests will be handled in accordance with applicable law, including data-protection requirements as and when they apply.</p><h2>7. Children</h2><p>The store is intended for people who can lawfully make purchases. A parent or lawful guardian should contact us if they believe a child’s personal information has been provided improperly.</p><h2>8. Policy updates</h2><p>This policy may be updated when the website, business operations or applicable legal requirements change. The effective date above should be updated whenever a material revision is published.</p><h2>9. Contact for privacy matters</h2><p>Email: <a href="mailto:kpmcenterprise@gmail.com">kpmcenterprise@gmail.com</a><br/>Phone: <a href="tel:+917644841104">+91 76448 41104</a></p><p className="storefront-info-note">Publication check required: KPMC Enterprises should confirm the live data inventory, actual third-party processors, retention periods, security practices and applicable DPDP Act/Rules commencement before treating this as the final legal policy.</p></>}
      {infoSlug === "terms-and-conditions" && <><span className="storefront-kicker">TERMS OF WEBSITE USE &amp; PURCHASE</span><h1>Terms &amp; Conditions</h1><p><strong>Effective date:</strong> 28 October 2026</p><p>Super Bajaar is a retail brand owned by KPMC Enterprises. These terms describe the general conditions for using the website and placing orders. By using the website, you agree to use it lawfully and provide accurate information. Mandatory rights available under consumer-protection law are not excluded by these terms.</p><h2>1. Business and contact details</h2><p>Brand: Super Bajaar. Brand owner: KPMC Enterprises. Customer support: <a href="mailto:kpmcenterprise@gmail.com">kpmcenterprise@gmail.com</a> · <a href="tel:+917644841104">+91 76448 41104</a>. The principal business address and the exact legal constitution/name of the operating entity must be published once confirmed.</p><h2>2. Products, listings and availability</h2><p>Product descriptions, images, prices, taxes, stock and availability are provided to help you make an informed choice. Actual product packaging or appearance may vary where the difference is not material. Products are subject to stock and delivery eligibility. If an item cannot be supplied, customer support will communicate the available next steps.</p><h2>3. Prices and charges</h2><p>The payable total and applicable charges should be shown before you place an order. Standard delivery is estimated at 1–5 days. Eligible express delivery is estimated at 30 minutes to 1 day and costs ₹39 per order. Express service depends on the destination, item and operational availability; it is not available for every order. Any applicable tax and compulsory charge should be disclosed at checkout.</p><h2>4. Order placement and acceptance</h2><p>Please check your basket, quantities, contact details and delivery information before submitting an order. An order request may be subject to stock, serviceability and order validation. A confirmation number should be retained for support. Do not treat an order as paid unless the relevant payment provider or store confirms payment. The current website may not support online payment collection; available payment methods are those explicitly shown at checkout.</p><h2>5. Delivery</h2><p>Delivery windows are estimates and may vary by PIN code, stock, weather, operational conditions and other circumstances. The applicable delivery option and charge should be shown before order submission. If there is a delay or delivery issue, contact customer support with your order reference.</p><h2>6. Cancellation, returns and refunds</h2><p>Cancellation, return and refund requests are handled under the published Returns &amp; Refunds policy and applicable law. Genuine and verified returns approved for refund are processed within 2 working days after verification and approval. The time for the refund to appear may depend on the bank or payment provider. Nothing in these terms removes a consumer right that cannot lawfully be excluded.</p><h2>7. Customer responsibilities</h2><p>Provide accurate contact and delivery details, use the website lawfully, keep any account credentials secure, and do not submit fraudulent orders, interfere with the service or attempt to access another person’s information.</p><h2>8. Complaints and grievance redressal</h2><p>For assistance, contact <a href="mailto:kpmcenterprise@gmail.com">kpmcenterprise@gmail.com</a> or <a href="tel:+917644841104">+91 76448 41104</a>. You may also contact the grievance officer listed on the Grievance Redressal page. Complaints will be acknowledged and handled in accordance with applicable law.</p><h2>9. Website availability and updates</h2><p>We may maintain or update website features to improve security and operation. We will not use these terms to disclaim responsibility for obligations imposed by applicable law.</p><h2>10. Applicable law</h2><p>These terms are subject to applicable laws of India, including consumer-protection and e-commerce laws. Any dispute will be handled by the competent forum under applicable law.</p><h2>11. Contact</h2><p>Email: <a href="mailto:kpmcenterprise@gmail.com">kpmcenterprise@gmail.com</a><br/>Phone/WhatsApp: <a href="https://wa.me/917644841104" target="_blank" rel="noreferrer">+91 76448 41104</a></p><p className="storefront-info-note">Before publication, confirm the legal entity name/constitution, principal business address, checkout/payment process, cancellation rules and all live product/delivery disclosures. These details cannot be inferred from the brand name alone.</p></>}
      {infoSlug === "shipping-delivery" && <><span className="storefront-kicker">DELIVERY INFORMATION</span><h1>Shipping &amp; Delivery</h1><div className="storefront-policy-cards"><article><strong>Standard Delivery</strong><b>1–5 days</b><p>Estimated delivery window, subject to product availability, destination and service conditions.</p></article><article><strong>Express Delivery</strong><b>30 minutes to 1 day</b><p>Express delivery is available only for eligible products and serviceable locations.</p><small>Charge: ₹39 per order</small></article></div><h2>Important information</h2><p>Delivery estimates begin after the order is accepted and may vary due to location, stock, weather, operational constraints or other circumstances. Express delivery is not guaranteed for every PIN code or product. Any applicable delivery charge should be shown before the order is placed.</p><p>For delivery help, call <a href="tel:+917644841104">+91 76448 41104</a> or email <a href="mailto:kpmcenterprise@gmail.com">kpmcenterprise@gmail.com</a>.</p></>}
      {infoSlug === "returns-refunds" && <><span className="storefront-kicker">RETURNS &amp; REFUNDS</span><h1>Returns &amp; Refunds</h1><p>Returns are subject to verification of the order, item condition and the applicable return rules. Please contact support with your order number and the reason for the return before sending an item back.</p><h2>Verification</h2><p>Returned items will be checked to confirm that the return is genuine and meets the applicable return conditions. Some products may be non-returnable where permitted by applicable law and where clearly disclosed before purchase.</p><h2>Refund timing</h2><p>For genuine and verified returns approved for refund, the refund will be processed within <strong>2 working days</strong> after verification and approval. The time for the amount to appear in the original payment method may depend on the bank or payment provider.</p><h2>Request help</h2><p>Call <a href="tel:+917644841104">+91 76448 41104</a>, WhatsApp <a href="https://wa.me/917644841104" target="_blank" rel="noreferrer">+91 76448 41104</a>, or email <a href="mailto:kpmcenterprise@gmail.com">kpmcenterprise@gmail.com</a>.</p></>}
      {infoSlug === "grievance-redressal" && <><span className="storefront-kicker">CUSTOMER RIGHTS &amp; ESCALATION</span><h1>Grievance Redressal</h1><p>We welcome the opportunity to resolve concerns about orders, products, delivery, returns, refunds or website services. Please provide your name, preferred contact details, order reference (if any), a description of the issue and relevant supporting information. Avoid sending passwords or payment credentials.</p><div className="storefront-grievance-card"><strong>Grievance Officer</strong><h2>NK Singh</h2><p>Phone: <a href="tel:+917644841104">+91 76448 41104</a></p><p>Email: <a href="mailto:nibandhansingh1997@gmail.com">nibandhansingh1997@gmail.com</a></p><p>Customer support: <a href="mailto:kpmcenterprise@gmail.com">kpmcenterprise@gmail.com</a></p></div><h2>How to submit a grievance</h2><ol><li>Email the grievance officer or call the number above. You may also contact customer support first.</li><li>Include your order number or previous ticket/reference, if available, and explain the outcome you are seeking.</li><li>Keep a copy of your email and any response for follow-up. When a complaint is formally recorded, ask for the complaint/reference number so you can track it.</li></ol><h2>Acknowledgement and resolution</h2><p>Consumer complaints will be acknowledged within <strong>48 hours</strong> and redressed within <strong>one month</strong> of receipt, in line with the applicable Consumer Protection (E-Commerce) Rules. Where applicable requirements change, this process will be updated accordingly.</p><h2>Further assistance</h2><p>You may also seek assistance through the Government of India’s National Consumer Helpline at <a href="https://consumerhelpline.gov.in/" target="_blank" rel="noreferrer">consumerhelpline.gov.in</a> or by calling 1915, subject to the current availability of that service.</p><p className="storefront-info-note">The online customer ticket form and automatic complaint-number tracking are not yet connected to a verified customer-support backend. Until implemented, use the phone/email channels above and retain your sent message/reference.</p></>}
      {infoSlug === "legal" && <><span className="storefront-kicker">INDIAN E-COMMERCE FRAMEWORK</span><h1>Legal Information</h1><p>Super Bajaar is a brand owned by KPMC Enterprises. This page provides general information about Indian legal frameworks that may be relevant to e-commerce operations. It is not a legal opinion and does not by itself establish that every obligation has been met.</p><h2>Consumer protection and e-commerce</h2><p>The Consumer Protection Act, 2019 and the Consumer Protection (E-Commerce) Rules, 2020 set out consumer-protection duties relevant to covered e-commerce entities and sellers. Depending on the business model, relevant disclosures may include the operating entity’s legal name and address, customer-care details, grievance-officer details, order/pricing information, returns and refunds, and other required information.</p><p>The Central Consumer Protection Authority (CCPA) performs statutory functions relating to consumer rights and unfair trade practices. Official information is available from the <a href="https://consumeraffairs.gov.in/" target="_blank" rel="noreferrer">Department of Consumer Affairs</a>.</p><h2>DPIIT and foreign investment policy</h2><p>The Department for Promotion of Industry and Internal Trade (DPIIT), under the Ministry of Commerce and Industry, is relevant to policy matters including foreign direct investment (FDI) policy. DPIIT guidance is not a substitute for determining which FDI rules apply to the actual ownership and business model. FEMA and applicable FDI rules should be reviewed if foreign investment is relevant.</p><h2>Information technology and personal data</h2><p>The Information Technology Act, 2000 and applicable rules may be relevant to online operations and cybersecurity. The Digital Personal Data Protection Act, 2023 and the Digital Personal Data Protection Rules, 2025 have commencement provisions/timelines; the specific provisions in force at a given date must be checked before making a compliance claim. See the official <a href="https://www.meity.gov.in/documents/act-and-policies" target="_blank" rel="noreferrer">MeitY Acts and Policies</a> page.</p><h2>Upcoming e-commerce amendments</h2><p>The Government has announced that the Consumer Protection (E-Commerce) (Amendment) Rules, 2026 will come into force on <strong>1 January 2027</strong>. The announced changes include additional complaint-record requirements, clearer identification of sponsored listings, prior-price disclosures for announced discounts, dark-pattern compliance/self-audit requirements and additional product/seller disclosures, as applicable to the business model. Super Bajaar should review and implement applicable changes before their effective date.</p><p>Official announcement: <a href="https://www.pib.gov.in/PressReleasePage.aspx?PRID=2308759&amp;lang=2&amp;reg=48" target="_blank" rel="noreferrer">Press Information Bureau — E-Commerce Rules Amendment 2026</a>.</p><h2>Other applicable requirements</h2><p>Depending on products sold and business operations, additional requirements may apply, including GST and tax disclosures, Legal Metrology/packaged-commodity declarations, product-specific licensing, product safety, advertising, intellectual property, payment and consumer complaint requirements. The relevant obligations depend on actual products, transactions and business structure.</p><h2>Official references</h2><ul><li><a href="https://consumeraffairs.gov.in/pages/consumer-protection-acts" target="_blank" rel="noreferrer">Department of Consumer Affairs — Consumer Protection Acts and Rules</a></li><li><a href="https://www.meity.gov.in/documents/act-and-policies" target="_blank" rel="noreferrer">MeitY — Acts and Policies, including DPDP materials</a></li><li><a href="https://www.dpiit.gov.in/" target="_blank" rel="noreferrer">DPIIT — Department for Promotion of Industry and Internal Trade</a></li></ul><p className="storefront-info-note">Regulatory updates published in 2026 may have future commencement dates. Confirm the current Gazette text and effective dates before launch, and obtain professional review of the final policies and actual operating model.</p></>}
      {infoSlug === "faq" && <><span className="storefront-kicker">QUICK ANSWERS</span><h1>Frequently Asked Questions</h1><h2>How long does delivery take?</h2><p>Standard delivery is estimated at 1–5 days. Eligible express orders may take 30 minutes to 1 day and cost ₹39 per order.</p><h2>How do I contact support?</h2><p>Call or WhatsApp +91 76448 41104 or email kpmcenterprise@gmail.com.</p><h2>How long do refunds take?</h2><p>Approved refunds for genuine and verified returns are processed within 2 working days after verification and approval. Bank processing may take additional time.</p><h2>How can I raise a grievance?</h2><p>Contact grievance officer NK Singh at +91 76448 41104 or nibandhansingh1997@gmail.com.</p><h2>Where can I check whether delivery is available?</h2><p>Use the delivery PIN selector on the storefront. Availability depends on the configured delivery locations and eligible products.</p></>}
      {!["about-us","contact-us","privacy-policy","terms-and-conditions","shipping-delivery","returns-refunds","grievance-redressal","legal","faq"].includes(infoSlug) && <><h1>Page not found</h1><p>This information page does not exist.</p><button className="storefront-primary" type="button" onClick={openShopHome}>Return to shopping</button></>}
    </section>}
    {isProductPage && !selectedProduct && <main className="storefront-product-page"><button type="button" className="storefront-product-back" onClick={openShopHome}>← Continue shopping</button><section className="storefront-product-page-details" role="status"><h1>{loading ? "Loading product…" : "Product unavailable"}</h1><p>{loading ? "Please wait while product details load." : "This product may be unavailable or no longer active."}</p></section></main>}
    {isProductPage && selectedProduct && (() => { const product = productById.get(Number(selectedProduct.product_id)); const productVariants = variants.filter(item => Number(item.product_id) === Number(selectedProduct.product_id) && item.is_active !== false); const saved = productVariants.some(item => wishlist.some(id => Number(id) === Number(item.id))); const categoryName = product?.category_name || product?.category || orderedCategories.find(c => String(c.id) === String(product?.category_id))?.name; const tile = categoryArt[categoryName] || art[0]; const variantLabel = item => { const values = Object.entries(item.attributes || {}).map(([key, value]) => (Array.isArray(value) ? value.join(", ") : String(value))); return values.length ? values.join(" / ") : "Standard"; }; return <main className="storefront-product-page"><button type="button" className="storefront-product-back" onClick={openShopHome}>← Continue shopping</button><div className="storefront-product-page-layout"><div className="storefront-product-page-art">{selectedProduct.image_url ? <img src={selectedProduct.image_url} alt={product?.name || selectedProduct.product_name || "Product"} /> : <span>{tile.icon}</span>}</div><section className="storefront-product-page-details"><span className="storefront-kicker">PRODUCT DETAILS</span><h1>{product?.name || selectedProduct.product_name || "Product"}</h1><p className="storefront-modal-brand">{product?.brand || "Super Bajaar"}{categoryName ? " · " + categoryName : ""}</p>{product?.description && <p className="storefront-modal-description">{product.description}</p>}{productVariants.length > 1 && <label className="storefront-variant-select">Choose variant<select aria-label={"Choose variant for " + (product?.name || selectedProduct.product_name)} value={String(selectedProduct.id)} onChange={event => { const chosen = productVariants.find(item => String(item.id) === event.target.value); if (chosen) { rememberViewed(chosen); setSelectedProduct(chosen); } }}>{productVariants.map(item => <option key={item.id} value={item.id}>{variantLabel(item)} · {money(item.selling_price)}</option>)}</select></label>}<p className="storefront-modal-sku">SKU: {selectedProduct.sku || "Not available"}</p><strong className="storefront-modal-price">{money(selectedProduct.selling_price)}</strong><div className="storefront-modal-actions"><button type="button" className="storefront-primary" onClick={() => addToCart(selectedProduct)}><ShoppingBag size={17}/> Add to basket</button><button type="button" className="storefront-modal-wishlist" onClick={() => setWishlist(old => saved ? old.filter(id => !productVariants.some(item => Number(item.id) === Number(id))) : [...new Set([...old, ...productVariants.map(item => Number(item.id))])])}><Heart size={17} fill={saved ? "currentColor" : "none"} />{saved ? "Remove from wishlist" : "Save to wishlist"}</button></div></section></div></main>; })()}
    {isCategoryPage && !isCategoryListingPage && !isWishlistPage && !isAccountPage && !isCheckoutPage && !isInfoPage && !isProductPage && <section className="storefront-category-landing">
      <div className="storefront-category-breadcrumb"><a href="/" onClick={event => { event.preventDefault(); openShopHome(); }}>Home</a><span>/</span><span>{routeCategoryName}</span></div>
      <div className={"storefront-category-hero tone-" + (categoryArt[routeCategoryName]?.tone || "lavender")}>
        <div className="storefront-category-hero-copy"><span className="storefront-kicker">EXPLORE THE COLLECTION</span><h1>{routeCategoryName}</h1><p>{categoryArt[routeCategoryName]?.detail || categories.find(c => c.name === routeCategoryName)?.description || "Discover everyday favourites selected for you."}</p><div className="storefront-category-hero-actions"><button className="storefront-primary" type="button" onClick={openCategoryListing}>View all {routeCategoryName} <span>→</span></button><span>{visibleVariants.length} products and variants</span></div></div>
        <div className="storefront-category-hero-art" aria-hidden="true"><span>{categoryArt[routeCategoryName]?.icon || "🛍️"}</span><i>✦</i><b>SUPER<br/>PICKS</b></div>
      </div>
      {routeCategoryName === "Insurance" && <section className="storefront-insurance-section">
        <div className="storefront-section-heading"><div><span className="storefront-kicker">PERSONALISED GUIDANCE</span><h2>Choose an insurance consultation</h2><p>Each consultation costs ₹100. Compare your options with our team.</p></div></div>
        <div className="storefront-insurance-options">
          {[
            {name:"Life Insurance",icon:"👨‍👩‍👧",description:"Discuss family protection, life cover and policy choices."},
            {name:"Health Insurance",icon:"🏥",description:"Discuss medical cover, hospitalisation benefits and policy choices."},
            {name:"Motor Insurance",icon:"🚗",description:"Discuss vehicle cover, third-party and comprehensive options."},
          ].map(service => <article className="storefront-insurance-card" key={service.name}>
            <span className="storefront-insurance-icon" aria-hidden="true">{service.icon}</span><h3>{service.name}</h3><p>{service.description}</p><strong>₹100 <small>/ consultation</small></strong>
            <button type="button" className="storefront-primary" onClick={() => { const select = document.getElementById("insuranceType"); if (select) select.value = service.name; document.getElementById("insurance-request")?.scrollIntoView({behavior:"smooth",block:"start"}); }}>Request consultation</button>
            <button type="button" className="storefront-insurance-pay" disabled title="Online payment is not enabled in the current checkout">Pay ₹100 online · Coming soon</button>
          </article>)}
        </div>
        <form id="insurance-request" className="storefront-insurance-form" onSubmit={submitInsuranceRequest}>
          <div><span className="storefront-kicker">WE’LL GET IN TOUCH</span><h2>Request a consultation</h2><p>Submit your details and our team will contact you. This request does not collect payment.</p></div>
          <label>Consultation type<select id="insuranceType" name="insuranceType" required defaultValue="Life Insurance"><option>Life Insurance</option><option>Health Insurance</option><option>Motor Insurance</option></select></label>
          <div className="storefront-insurance-form-grid"><label>Full name<input name="name" required autoComplete="name" /></label><label>Mobile number<input name="phone" required inputMode="tel" autoComplete="tel" /></label><label>Email address<input name="email" type="email" required autoComplete="email" /></label><label>Preferred contact time<select name="contactTime" defaultValue="Any time"><option>Any time</option><option>Morning</option><option>Afternoon</option><option>Evening</option></select></label></div>
          <label>What would you like help with? <textarea name="message" rows="3" placeholder="Optional details about your insurance needs" /></label>
          <button className="storefront-primary" type="submit" disabled={ticketBusy}>{ticketBusy ? "Submitting request…" : "Submit consultation request"}</button>
          {ticketCreated && <p className="storefront-insurance-success" role="status">Request received. Reference: {ticketCreated.case_number}</p>}
          {notice && <p className="storefront-insurance-success" role="status">{notice}</p>}
          {error && <p className="storefront-alert" role="alert">{error}</p>}
        </form>
      </section>}
      {routeCategoryName !== "Insurance" && categorySubcategories.length > 0 && <section className="storefront-subcategory-section"><div className="storefront-section-heading"><div><span className="storefront-kicker">SHOP YOUR WAY</span><h2>Explore subcategories</h2></div></div><div className="storefront-subcategory-grid">{categorySubcategories.map((category, index) => { const tile = categoryArt[category.name] || art[index % art.length]; return <button key={category.id} type="button" className="storefront-subcategory-card" onClick={() => openCategory(category)}><span className={"storefront-subcategory-icon tone-" + tile.tone}>{tile.icon}</span><strong>{category.name}</strong><span>Explore collection →</span></button>; })}</div></section>}
      {routeCategoryName !== "Insurance" && subcategoryProductRows.map(({ category, items }) => <section className="storefront-subcategory-products" key={category.id}>
        <div className="storefront-category-featured-heading"><div><span className="storefront-kicker">SHOP BY SUBCATEGORY</span><h2>{category.name}</h2><p>Explore products in {category.name}.</p></div><button type="button" onClick={() => openCategory(category)}>View all <span>→</span></button></div>
        <div className="storefront-subcategory-products-viewport">
          <div className="storefront-carousel-track storefront-subcategory-product-track" tabIndex={0} aria-label={category.name + " products"}>{items.map(renderProductCard)}</div>
        </div>
      </section>)}
      {routeCategoryName !== "Insurance" && <><div className="storefront-category-featured-heading"><div><span className="storefront-kicker">HANDPICKED FOR YOU</span><h2>Featured {routeCategoryName}</h2><p>Popular picks from this department.</p></div><button type="button" onClick={openCategoryListing}>View all <span>→</span></button></div>
      {loading ? <p className="storefront-empty">Loading live products…</p> : visibleVariants.length ? <div className="storefront-category-featured-track">{displayedVariants.slice(0, 8).map(renderProductCard)}</div> : <p className="storefront-empty">No active products are available in this category yet.</p>}
      {bestSellers.length > 0 && <div className="storefront-category-featured-heading"><div><span className="storefront-kicker">CUSTOMER FAVOURITES</span><h2>Popular in {routeCategoryName}</h2></div><button type="button" onClick={openCategoryListing}>View all <span>→</span></button></div>}
      {bestSellers.length > 0 && <div className="storefront-category-featured-track">{bestSellers.slice(0, 8).map(renderProductCard)}</div>}</>}
    </section>}
    {(isCategoryListingPage || isDealsPage || isWishlistPage) && !isAccountPage && !isCheckoutPage && !isInfoPage && !isProductPage && <section className={"storefront-products " + (isCategoryPage ? "storefront-category-page" : "") + (isWishlistPage ? " storefront-wishlist-page" : "")} id="products">
      <div className="storefront-category-breadcrumb"><a href="/" onClick={event => {event.preventDefault(); openShopHome();}}>Home</a><span>/</span><span>{isWishlistPage ? "My Wishlist" : isDealsPage ? "Deals" : routeCategoryName || "Shop products"}</span></div><div className="storefront-section-heading"><div><span className="storefront-kicker">{isWishlistPage ? "YOUR SAVED FAVOURITES" : isDealsPage ? "SPECIAL OFFERS" : "SHOP BY DEPARTMENT"}</span><h1>{isWishlistPage ? "My Wishlist" : isDealsPage ? "Deals & Offers" : routeCategoryName}</h1>{isWishlistPage && <p className="storefront-category-description">Your saved products, ready to revisit or add to your basket.</p>}{isDealsPage && <p className="storefront-category-description">Discover current discounted items and customer favourites.</p>}</div><span className="storefront-heading-note">{(isWishlistPage ? displayedVariants : isDealsPage ? dealVariants : visibleVariants).length} {isWishlistPage ? "saved products" : "products and variants"}</span></div>
      <label className="storefront-search">Search products or SKU<input value={search} onChange={e => setSearch(e.target.value)} placeholder="Try a product name or SKU" /></label>
      {error && <p className="storefront-alert" role="alert">{error}</p>}
      {loading ? <p className="storefront-empty">Loading live products…</p> : (isDealsPage ? dealVariants : displayedVariants).length ? <div className="storefront-product-grid">{(isDealsPage ? dealVariants : displayedVariants).map(renderProductCard)}</div> : isWishlistPage ? <div className="storefront-wishlist-empty"><span aria-hidden="true">♡</span><h2>Your wishlist is waiting</h2><p>Tap the heart on any product to save it here for later.</p><button type="button" className="storefront-primary" onClick={openShopHome}>Explore products</button></div> : <p className="storefront-empty">{error ? "The live catalogue could not be loaded." : isDealsPage ? "No discounted products or featured picks are available yet." : "No active products are available in this category yet."}</p>}
    </section>}
    {!isProductPage && !isAccountPage && !isCheckoutPage && !isInfoPage && !isCategoryPage && !isWishlistPage && !isDealsPage && !loading && <div className="storefront-discovery">
      {renderDiscoverySection("Best Sellers", "Customer favourites, ranked by recorded sales", bestSellers, "Best Sellers will appear when real sales data is available.", <Flame size={18} />)}
      {renderDiscoverySection("New Arrivals", "Fresh additions to the catalogue", newArrivals, "New products will appear here when available.", <Sparkles size={18} />)}
      {renderDiscoverySection("Recently Viewed", "Pick up where you left off", recentVariants, "Products you open will appear here during this browsing session.", <Clock3 size={18} />)}
    </div>}
    
    {!isProductPage && !isCategoryPage && !isDealsPage && !isWishlistPage && !isAccountPage && !isCheckoutPage && !isInfoPage && <section className="storefront-benefits" id="why-us"><div className="storefront-benefits-heading"><span className="storefront-kicker">THE SUPER BAJAAR DIFFERENCE</span><h2>Why Choose Us</h2><p>Everyday shopping, made simpler for you.</p></div><div className="storefront-benefit-grid"><article><span className="benefit-icon">✦</span><div><strong>Everyday essentials</strong><small>Explore a wide range of daily needs in one place.</small></div></article><article><span className="benefit-icon">♡</span><div><strong>Convenient shopping</strong><small>Browse departments and build your basket with ease.</small></div></article><article><span className="benefit-icon">✓</span><div><strong>Clear delivery information</strong><small>See available delivery options and charges before ordering.</small></div></article><article><span className="benefit-icon">✳</span><div><strong>Support when you need it</strong><small>Contact our support team or raise a ticket for help.</small></div></article></div></section>}
    {deliveryOpen && <div className="storefront-delivery-backdrop" role="presentation" onClick={event => { if (event.target === event.currentTarget) setDeliveryOpen(false); }}><section className="storefront-delivery-dialog" role="dialog" aria-modal="true" aria-labelledby="storefront-delivery-title"><button type="button" className="storefront-modal-close" aria-label="Close delivery location" onClick={() => setDeliveryOpen(false)}><X size={19}/></button><span className="storefront-kicker">DELIVERY LOCATION</span><h2 id="storefront-delivery-title">Where should we deliver?</h2><p>Enter your six-digit Indian PIN code to save your preferred delivery location.</p><form onSubmit={saveDeliveryPin}><label>PIN code<input inputMode="numeric" autoComplete="postal-code" pattern="[1-9][0-9]{5}" maxLength="6" value={deliveryDraft} onChange={event => { setDeliveryDraft(event.target.value.replace(/\D/g,"").slice(0,6)); setDeliveryMessage(""); }} required /></label><button className="storefront-primary" type="submit">Save location</button></form>{deliveryMessage && <p className="storefront-delivery-message" role="status">{deliveryMessage}</p>}<small>Saving a PIN does not confirm serviceability; that requires a connected delivery-serviceability check.</small></section></div>}

    <footer className="storefront-footer">
      <div className="storefront-footer-top"><a className="storefront-brand" href="/" onClick={event=>{event.preventDefault();openShopHome();}}><span className="storefront-logo">S</span><span><strong>Super Bajaar</strong><small>Your Everyday Super Store</small></span></a><p>Everyday made a little brighter.</p></div>
      <div className="storefront-footer-links">
        <div className="storefront-footer-column"><strong>Important Links</strong>
          <a href="/#categories" onClick={e=>{e.preventDefault();openShopHome();setTimeout(()=>document.getElementById("categories")?.scrollIntoView({behavior:"smooth",block:"start"}),0);}}>Explore Categories</a>
          <a href="/pages/about-us" onClick={e=>{e.preventDefault();openInfoPage("about-us");}}>About Us</a>
          <a href="/pages/seller-registration" onClick={e=>{e.preventDefault();openInfoPage("seller-registration");}}>Partner with Us</a>
          <a href="/pages/loyalty-programme" onClick={e=>{e.preventDefault();openInfoPage("loyalty-programme");}}>Loyalty Programme</a>
          <a href="/pages/super-coins" onClick={e=>{e.preventDefault();openInfoPage("super-coins");}}>Super Coins</a>
          <a href="/pages/grievance-redressal" onClick={e=>{e.preventDefault();openInfoPage("grievance-redressal");}}>Grievance Redressal</a>
          <a href="/pages/feedback" onClick={e=>{e.preventDefault();openInfoPage("feedback");}}>Feedback</a>
          <a href="/pages/faq" onClick={e=>{e.preventDefault();openInfoPage("faq");}}>FAQ</a>
          <a href="/pages/shipping-delivery" onClick={e=>{e.preventDefault();openInfoPage("shipping-delivery");}}>Shipping &amp; Delivery</a>
          <a href="/pages/returns-refunds" onClick={e=>{e.preventDefault();openInfoPage("returns-refunds");}}>Return &amp; Refund</a>
          <a href="/pages/cancellation-policy" onClick={e=>{e.preventDefault();openInfoPage("cancellation-policy");}}>Cancellation Policy</a>
        </div>
        <div className="storefront-footer-column"><strong>Customer Support</strong>
          <a href="/account" onClick={e=>{e.preventDefault();openTicketCenter();}}>Raise Ticket</a>
          <a href="tel:+917644841104">Phone: +91 76448 41104</a>
          <a href="mailto:kpmcenterprise@gmail.com">Email: kpmcenterprise@gmail.com</a>
          <a href="https://wa.me/917644841104" target="_blank" rel="noreferrer">WhatsApp</a>
        </div>
        <div className="storefront-footer-column"><strong>Legal</strong>
          <a href="/pages/privacy-policy" onClick={e=>{e.preventDefault();openInfoPage("privacy-policy");}}>Privacy Policy</a>
          <a href="/pages/terms-and-conditions" onClick={e=>{e.preventDefault();openInfoPage("terms-and-conditions");}}>Terms &amp; Conditions</a>
          <a href="/pages/legal" onClick={e=>{e.preventDefault();openInfoPage("legal");}}>Documentations</a>
        </div>
      </div>
      <div className="storefront-footer-bottom"><span>© {new Date().getFullYear()} Super Bajaar · A brand owned by KPMC Enterprises</span><div className="storefront-social-links"><a href="https://www.facebook.com/profile.php?id=61594558420175" target="_blank" rel="noreferrer">Facebook</a><a href="https://www.instagram.com/super_bajaar" target="_blank" rel="noreferrer">Instagram</a><a href="https://wa.me/917644841104" target="_blank" rel="noreferrer">WhatsApp</a></div>{canOpenAdmin && <a href="/admin">Admin Console ↗</a>}</div>
    </footer>
  </main>;
}
