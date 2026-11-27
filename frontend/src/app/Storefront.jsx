import VariantOptionPicker from "./VariantOptionPicker.jsx";
import ProductGallery from "./ProductGallery.jsx";
import ProductDescription from "./ProductDescription.jsx";
import RelatedProducts from "./RelatedProducts.jsx";
import LoyaltyProgrammePage from "./LoyaltyProgrammePage.jsx";
import LegalPage from "./LegalPage.jsx";
import { LEGAL_SLUGS, BUSINESS } from "./legalContent.js";
import { buildSearchIndex } from "./searchEngine.js";
import { variantAttributeGroups, variantValueLabel } from "./variantOptions.js";
import CategoryHeroSlider from "./CategoryHeroSlider.jsx";
import { useEffect, useMemo, useState } from "react";
import { Heart, ShoppingBag, Search, Sparkles, Flame, Clock3, ChevronLeft, ChevronRight, UserRound, MapPin, X, Coins, CreditCard, CalendarClock, Star, Paperclip, FileText } from "lucide-react";
import { Users, HeartPulse, Package, ShoppingCart, Leaf, Shirt, Droplets, Headphones, Home, PawPrint, Gift, Car, Trophy, Pill, ShieldCheck } from "lucide-react";
import { apiRequest, API_BASE_URL } from "../services/api.js";
import GoogleAnalytics, { getAnalyticsConsent, setAnalyticsConsent, trackAnalyticsEvent } from "./GoogleAnalytics.jsx";
import IdentityClaimsPanel from "./IdentityClaimsPanel.jsx";
import ProductReviews from "./ProductReviews.jsx";
import { clampRedeemCoins } from "../features/loyalty/checkout.js";
import "./storefront.css";
import "./storefront-responsive.css";

const SUPPORT_SUBJECTS = [
  ["item_not_listed", "Item Not Listed"],
  ["account_issue", "Account Issue"],
  ["supercoin", "Supercoin"],
  ["order_delayed", "Order Delayed"],
  ["cancellation_refund", "Cancellation & Refund"],
  ["payment_issue", "Payment Issue"],
  ["referral_earning", "Referral Earning"],
  ["feedback", "Feedback"],
];
const TICKET_FILE_TYPES = ["image/jpeg", "image/png", "image/webp", "application/pdf"];
const TICKET_MAX_FILES = 3;
const TICKET_MAX_BYTES = 5 * 1024 * 1024;
const formatFileSize = bytes => bytes >= 1024 * 1024 ? (bytes / (1024 * 1024)).toFixed(1) + " MB" : Math.max(1, Math.round(bytes / 1024)) + " KB";
// Returns the next file list plus a customer-readable problem, if any file was refused.
function mergeTicketFiles(current, incoming) {
  const next = [...current];
  let problem = "";
  for (const file of incoming) {
    if (next.length >= TICKET_MAX_FILES) { problem = "You can attach up to " + TICKET_MAX_FILES + " files."; break; }
    if (!TICKET_FILE_TYPES.includes(file.type)) { problem = file.name + " is not supported. Attach a JPG, PNG, WebP or PDF."; continue; }
    if (file.size > TICKET_MAX_BYTES) { problem = file.name + " is larger than 5 MB."; continue; }
    if (file.size === 0) { problem = file.name + " is empty."; continue; }
    if (next.some(item => item.name === file.name && item.size === file.size)) continue;
    next.push(file);
  }
  return { files: next, problem };
}

const categoryOrder = [
  "Grocery", "Fresh Daily", "Fashion", "Personal Care", "Electronics",
  "Home Appliances", "Pet Care", "Gifting", "Pooja Essentials",
  "Automobiles", "Toys & Sports", "Pharmacy", "Insurance",
];
const categoryArt = {
  "Grocery": { icon: "ShoppingCart", tone: "lavender", detail: "Everyday groceries" },
  "Fresh Daily": { icon: "Leaf", tone: "green", detail: "Fresh picks, every day" },
  "Fashion": { icon: "Shirt", tone: "peach", detail: "Style for everyone" },
  "Personal Care": { icon: "Droplets", tone: "blue", detail: "Care for every day" },
  "Electronics": { icon: "Headphones", tone: "lavender", detail: "Smart picks, every day" },
  "Home Appliances": { icon: "Home", tone: "yellow", detail: "For a happier home" },
  "Pet Care": { icon: "PawPrint", tone: "green", detail: "Little things for pets" },
  "Gifting": { icon: "Gift", tone: "peach", detail: "Gifts for every moment" },
  "Pooja Essentials": { icon: "Flame", tone: "yellow", detail: "For your traditions" },
  "Automobiles": { icon: "Car", tone: "blue", detail: "Everyday auto essentials" },
  "Toys & Sports": { icon: "Trophy", tone: "lavender", detail: "Play, move, explore" },
  "Pharmacy": { icon: "Pill", tone: "green", detail: "Health and wellness" },
  "Insurance": { icon: "ShieldCheck", tone: "lavender", detail: "Insurance guidance for life, health and motor cover" },
};
const catIcons = { Users, HeartPulse, ShoppingCart, Leaf, Shirt, Droplets, Headphones, Home, PawPrint, Gift, Flame, Car, Trophy, Pill, ShieldCheck };
const art = categoryOrder.map(name => categoryArt[name]);
const money = value => new Intl.NumberFormat("en-IN", { style: "currency", currency: "INR", maximumFractionDigits: 2 }).format(Number(value || 0));

let razorpayScriptPromise;
function loadRazorpayCheckout() {
  if (window.Razorpay) return Promise.resolve();
  if (!razorpayScriptPromise) {
    razorpayScriptPromise = new Promise((resolve, reject) => {
      const script = document.createElement("script");
      script.src = "https://checkout.razorpay.com/v1/checkout.js";
      script.async = true;
      script.onload = () => resolve();
      script.onerror = () => { razorpayScriptPromise = null; reject(new Error("Unable to load secure Razorpay Checkout. Please try again.")); };
      document.head.appendChild(script);
    });
  }
  return razorpayScriptPromise;
}


function checkoutIdempotencyKey(payload) {
  const fingerprint = JSON.stringify(payload);
  const storageKey = "sb-checkout-attempt";
  try {
    const previous = JSON.parse(window.sessionStorage.getItem(storageKey) || "null");
    if (previous?.fingerprint === fingerprint && previous?.key) return previous.key;
    const key = globalThis.crypto?.randomUUID?.()
      || ("sb-" + Date.now().toString(36) + "-" + Math.random().toString(36).slice(2));
    window.sessionStorage.setItem(storageKey, JSON.stringify({ fingerprint, key }));
    return key;
  } catch {
    // The server still validates the order; session storage only preserves retry identity.
    return globalThis.crypto?.randomUUID?.()
      || ("sb-" + Date.now().toString(36) + "-" + Math.random().toString(36).slice(2));
  }
}

function clearCheckoutIdempotencyKey() {
  try { window.sessionStorage.removeItem("sb-checkout-attempt"); } catch { /* Storage may be unavailable. */ }
}

export default function Storefront() {
  const [categories, setCategories] = useState([]);
  const [products, setProducts] = useState([]);
  const [variants, setVariants] = useState([]);
  const [categoryId, setCategoryId] = useState("");
  const [routePath, setRoutePath] = useState(() => window.location.pathname.replace(/\/+$/, "") || "/");
  const [search, setSearch] = useState(() => window.location.pathname.replace(/\/+$/, "") === "/search" ? (new URLSearchParams(window.location.search).get("q") || "") : "");
  const [suggestOpen, setSuggestOpen] = useState(false);
  const [cart, setCart] = useState(() => { try { return JSON.parse(window.localStorage.getItem("sb-cart") || "[]"); } catch { return []; } });
  const [customerToken, setCustomerToken] = useState(() => { try { return window.localStorage.getItem("sb-customer.access_token") || ""; } catch { return ""; } });
  const [customerAuth, setCustomerAuth] = useState(null);
  const [savedAddresses, setSavedAddresses] = useState([]);
  const [selectedAddressId, setSelectedAddressId] = useState("");
  const [addressEditorOpen, setAddressEditorOpen] = useState(false);
  const [addressBusy, setAddressBusy] = useState(false);
  const [addressDraft, setAddressDraft] = useState({ id: null, label: "Home", recipient_name: "", phone: "", address: "", landmark: "", pin_code: "", is_default: false });
  const [customerAuthMode, setCustomerAuthMode] = useState(() => window.location.pathname === "/customer/register" ? "register" : "login");
  const [customerAuthDraft, setCustomerAuthDraft] = useState(() => ({ full_name: "", email: "", phone: "", password: "", referral_code: new URLSearchParams(window.location.search).get("ref") || "" }));
  const [customerAuthBusy, setCustomerAuthBusy] = useState(false);
  const [oauthProviders, setOauthProviders] = useState([]);
  useEffect(() => {
    let active = true;
    apiRequest("/customer-auth/oauth/providers", { skipAuth: true })
      .then(result => { if (active) setOauthProviders(result?.providers || []); })
      .catch(() => {});
    return () => { active = false; };
  }, []);
  // Returning from Google/GitHub: the API redirects here with the session token (or an error) in the URL fragment.
  useEffect(() => {
    const path = window.location.pathname.replace(/\/+$/, "");
    if (path !== "/customer/oauth-complete" && !(path === "/customer/login" && window.location.hash.includes("error="))) return;
    const params = new URLSearchParams(window.location.hash.replace(/^#/, ""));
    const token = params.get("token");
    const failure = params.get("error");
    if (token) {
      try { window.localStorage.setItem("sb-customer.access_token", token); } catch {}
      setCustomerToken(token);
      window.history.replaceState({}, "", "/account");
      setRoutePath("/account");
    } else {
      window.history.replaceState({}, "", "/customer/login");
      setRoutePath("/customer/login");
      setCustomerAuthMode("login");
      setError(failure || "Could not sign in. Please try again.");
    }
  }, []);
  const [referralData, setReferralData] = useState(null);
  const [referralBusy, setReferralBusy] = useState(false);
  const [wishlist, setWishlist] = useState(() => { try { return JSON.parse(window.localStorage.getItem("sb-wishlist") || "[]").map(Number).filter(Number.isFinite); } catch { return []; } });
  const [recentlyViewed, setRecentlyViewed] = useState([]);
  const [customer, setCustomer] = useState(() => { try { return { name: "", phone: "", pin: "", email: "", address: "", ...JSON.parse(window.localStorage.getItem("sb-customer-profile") || "{}") }; } catch { return { name: "", phone: "", pin: "", email: "", address: "" }; } });
  const [loading, setLoading] = useState(true);
  const [submitting, setSubmitting] = useState(false);
  const [termsAccepted, setTermsAccepted] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [order, setOrder] = useState(null);
  const [selectedProduct, setSelectedProduct] = useState(null);
  const [productPageQuantity, setProductPageQuantity] = useState(1);
  const [deliveryOpen, setDeliveryOpen] = useState(false);
  const [deliveryPin, setDeliveryPin] = useState(() => { try { return window.localStorage.getItem("sb-delivery-pin") || ""; } catch { return ""; } });
  const [deliveryDraft, setDeliveryDraft] = useState(() => { try { return window.localStorage.getItem("sb-delivery-pin") || ""; } catch { return ""; } });
  const [deliveryMessage, setDeliveryMessage] = useState("");
  const [deliveryInfo, setDeliveryInfo] = useState(null);
  const [deliveryType, setDeliveryType] = useState("standard");
  const [checkoutInfo, setCheckoutInfo] = useState(null);
  const [accountOpen, setAccountOpen] = useState(false);
  const [accountSection, setAccountSection] = useState("overview");
  const [analyticsEnabled, setAnalyticsEnabled] = useState(getAnalyticsConsent);
  const [canOpenAdmin, setCanOpenAdmin] = useState(false);
  const [ticketDraft, setTicketDraft] = useState({ category: "", description: "" });
  const [ticketFiles, setTicketFiles] = useState([]);
  const [replyFiles, setReplyFiles] = useState([]);
  const [ticketFileProblem, setTicketFileProblem] = useState("");
  const [ticketUploadIssue, setTicketUploadIssue] = useState("");
  const [ticketCreated, setTicketCreated] = useState(null);
  const [ticketLookup, setTicketLookup] = useState({ caseNumber: "" });
  const [ticketTracked, setTicketTracked] = useState(null);
  const [myTickets, setMyTickets] = useState([]);
  const [ticketReply, setTicketReply] = useState("");
  const [ticketBusy, setTicketBusy] = useState(false);
  const [loyaltyRules, setLoyaltyRules] = useState([]);
  const [attributeDefinitions, setAttributeDefinitions] = useState([]);
  const [categoryHeroImages, setCategoryHeroImages] = useState({});
  const [homeHeroImages, setHomeHeroImages] = useState([]);
  const [reviewSummary, setReviewSummary] = useState({});
  const [reviewsVersion, setReviewsVersion] = useState(0);
  const [loyaltyDefaultRate, setLoyaltyDefaultRate] = useState(1);
  const [loyaltyOrderReference, setLoyaltyOrderReference] = useState("");
  const [loyaltyCustomerData, setLoyaltyCustomerData] = useState(null);
  const [loyaltyBusy, setLoyaltyBusy] = useState(false);
  const [redeemCoins, setRedeemCoins] = useState(0);
  const [redemptionQuote, setRedemptionQuote] = useState(null);
  const [redemptionQuoteBusy, setRedemptionQuoteBusy] = useState(false);
  const [redemptionQuoteError, setRedemptionQuoteError] = useState("");
  const [myOrders, setMyOrders] = useState(null);
  const [myOrderDetail, setMyOrderDetail] = useState(null);
  const [ordersBusy, setOrdersBusy] = useState(false);
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
    if (!customerToken || !customerAuth) { setSavedAddresses([]); setSelectedAddressId(""); return; }
    let active = true;
    customerRequest("/customer-auth/addresses").then(async result => {
      if (!active) return;
      let items = Array.isArray(result?.items) ? result.items : [];
      // Import the address previously stored only in this browser, once, when the account has none.
      if (!items.length) {
        const legacy = (() => { try { return JSON.parse(window.localStorage.getItem("sb-customer-profile") || "{}"); } catch { return {}; } })();
        if (legacy.address && /^[1-9][0-9]{5}$/.test(String(legacy.pin || ""))) {
          try {
            await customerRequest("/customer-auth/addresses", { method: "POST", body: JSON.stringify({
              label: "Home", recipient_name: legacy.name || customerAuth.full_name || customer.name || "", phone: legacy.phone || customer.phone || customerAuth.phone || "",
              address: legacy.address, pin_code: legacy.pin, is_default: true
            })});
            const refreshed = await customerRequest("/customer-auth/addresses");
            items = Array.isArray(refreshed?.items) ? refreshed.items : [];
          } catch { /* Keep the legacy browser address available for manual saving. */ }
        }
      }
      if (!active) return;
      setSavedAddresses(items);
      const preferred = items.find(item => item.is_default) || items[0];
      if (preferred) {
        setSelectedAddressId(String(preferred.id));
        setCustomer(old => ({ ...old, name: preferred.recipient_name || old.name, phone: preferred.phone || old.phone, address: preferred.address || old.address, pin: preferred.pin_code || old.pin }));
      }
    }).catch(() => {
      if (active) setSavedAddresses([]);
    });
    return () => { active = false; };
  }, [customerToken, customerAuth?.id]);

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
    if (!routePath.startsWith("/product/") || !Number.isInteger(Number(routePath.split("/")[2])) || !variants.length) return;
    const productId = Number(routePath.split("/")[2]);
    const variant = variants.find(item => Number(item.product_id) === productId && item.is_active !== false);
    if (!variant) return;
    trackAnalyticsEvent("view_item", {
      currency: "INR",
      value: Number(variant.selling_price || 0),
      items: [{ item_id: String(variant.sku || variant.id), item_name: variant.product_name || "Product", price: Number(variant.selling_price || 0) }],
    });
  }, [routePath, variants]);

  useEffect(() => {
    const syncPath = () => { const path = window.location.pathname.replace(/\/+$/, "") || "/"; setRoutePath(path); setSearch(path === "/search" ? (new URLSearchParams(window.location.search).get("q") || "") : ""); };
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
    apiRequest("/reviews/summary", { skipAuth: true }).then(result => {
      if (!active) return;
      const map = {};
      (Array.isArray(result?.items) ? result.items : []).forEach(item => { map[Number(item.product_id)] = item; });
      setReviewSummary(map);
    }).catch(() => { if (active) setReviewSummary({}); });
    return () => { active = false; };
  }, [reviewsVersion]);

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
    apiRequest("/catalogue/category-hero-images", { skipAuth: true }).then(result => {
      if (!active) return;
      const byCategory = {};
      (Array.isArray(result?.items) ? result.items : []).forEach(item => { const key = Number(item.category_id); byCategory[key] = [...(byCategory[key] || []), item]; });
      setCategoryHeroImages(byCategory);
    }).catch(() => { if (active) setCategoryHeroImages({}); });
    return () => { active = false; };
  }, []);

  useEffect(() => {
    let active = true;
    apiRequest("/catalogue/homepage-hero-images", { skipAuth: true })
      .then(result => { if (active) setHomeHeroImages(Array.isArray(result?.items) ? result.items : []); })
      .catch(() => { if (active) setHomeHeroImages([]); });
    return () => { active = false; };
  }, []);

  useEffect(() => {
    let active = true;
    apiRequest("/catalogue/attributes?limit=5000", { skipAuth: true })
      .then(result => { if (active) setAttributeDefinitions(Array.isArray(result?.items) ? result.items : []); })
      .catch(() => { if (active) setAttributeDefinitions([]); });
    const endpoints = [
      ["categories", () => apiRequest("/catalogue/categories?limit=5000", { skipAuth: true })],
      ["products", () => apiRequest("/catalogue/products?limit=5000", { skipAuth: true })],
      ["variants", () => apiRequest("/catalogue/variants?limit=5000", { skipAuth: true })],
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
  const searchIndex = useMemo(() => buildSearchIndex({ products, variants, categories }), [products, variants, categories]);
  const suggestions = useMemo(() => {
    const term = search.trim();
    if (!term) return [];
    const scoreMap = searchIndex.scores(term);
    const best = new Map();
    variants.forEach(v => {
      if (v.is_active === false) return;
      const pid = Number(v.product_id);
      if (!scoreMap.has(pid)) return;
      const existing = best.get(pid);
      if (!existing || Number(v.selling_price || 0) < Number(existing.selling_price || 0)) best.set(pid, v);
    });
    return [...best.entries()].sort((a, b) => scoreMap.get(b[0]) - scoreMap.get(a[0])).slice(0, 6).map(entry => entry[1]);
  }, [search, searchIndex, variants]);
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
  const isSearchPage = routePath === "/search";
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
    setProductPageQuantity(1);
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
  const submitSearch = () => {
    const term = search.trim();
    if (!term) return;
    window.history.pushState({}, "", "/search?q=" + encodeURIComponent(term));
    setRoutePath("/search"); setCategoryId(""); setSuggestOpen(false);
    window.scrollTo({ top: 0, behavior: "smooth" });
  };
  const onSearchInput = value => {
    setSearch(value); setSuggestOpen(true);
    if (routePath === "/search") window.history.replaceState({}, "", "/search?q=" + encodeURIComponent(value));
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
  useEffect(() => {
    if (!customerToken || !customerAuth || accountSection !== "tickets") return;
    let active = true;
    customerRequest("/customers/support-portal/tickets").then(result => {
      if (active) setMyTickets(result.items || []);
    }).catch(reason => {
      if (active) setError(reason.message || "Unable to load your support tickets.");
    });
    return () => { active = false; };
  }, [customerToken, customerAuth, accountSection]);

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
      setDeliveryInfo(result);
      setDeliveryMessage(result.message || (result.serviceable ? "Delivery is available at " + deliveryDraft + "." : "Sorry, Super Bajaar isn't available in your region yet."));
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

  const selectedAddress = savedAddresses.find(item => String(item.id) === String(selectedAddressId)) || null;
  useEffect(() => {
    if (!/^[1-9][0-9]{5}$/.test(deliveryPin)) { setDeliveryInfo(null); return undefined; }
    let live = true;
    apiRequest("/delivery/serviceability/" + deliveryPin, { skipAuth: true })
      .then(result => { if (live) setDeliveryInfo(result); })
      .catch(() => { if (live) setDeliveryInfo(null); });
    return () => { live = false; };
  }, [deliveryPin]);
  const checkoutPin = String(selectedAddress?.pin_code || "").trim();
  useEffect(() => {
    if (!isCheckoutPage || !/^[1-9][0-9]{5}$/.test(checkoutPin)) { setCheckoutInfo(null); return undefined; }
    let live = true;
    apiRequest("/delivery/serviceability/" + checkoutPin, { skipAuth: true })
      .then(result => { if (live) setCheckoutInfo(result); })
      .catch(() => { if (live) setCheckoutInfo(null); });
    return () => { live = false; };
  }, [isCheckoutPage, checkoutPin]);
  const regionUnserved = deliveryInfo?.serviceable === false;
  const blockedProductIds = new Set((deliveryInfo?.blocked_product_ids || []).map(Number));
  const isProductUnavailable = productId => regionUnserved || blockedProductIds.has(Number(productId));
  const checkoutBlockedIds = new Set((checkoutInfo?.blocked_product_ids || []).map(Number));
  const checkoutUnavailableLines = cart.filter(line => checkoutBlockedIds.has(Number(line.product_id)));
  const checkoutRegionUnserved = checkoutInfo?.serviceable === false;
  const expressEligibleCart = cart.length > 0 && cart.every(line => (productById.get(Number(line.product_id))?.delivery_options || []).includes("express"));
  const expressOffered = Boolean(checkoutInfo?.express_available) && expressEligibleCart;
  const effectiveDeliveryType = expressOffered && deliveryType === "express" ? "express" : "standard";
  const selectSavedAddress = address => {
    setSelectedAddressId(String(address.id));
    setCustomer(old => ({ ...old, name: address.recipient_name, phone: address.phone, address: address.address, pin: address.pin_code }));
  };
  const openAddressEditor = address => {
    setAddressDraft(address ? { ...address, id: address.id } : {
      id: null, label: "Home", recipient_name: customer.name || customerAuth?.full_name || "",
      phone: customer.phone || customerAuth?.phone || "", address: customer.address || "",
      landmark: "", pin_code: customer.pin || "", is_default: savedAddresses.length === 0
    });
    setAddressEditorOpen(true);
    setError("");
  };
  const saveCustomerAddress = async event => {
    event.preventDefault();
    if (!customerToken) { setError("Sign in to save a delivery address."); return; }
    setAddressBusy(true); setError("");
    try {
      const payload = { label: addressDraft.label, recipient_name: addressDraft.recipient_name.trim(),
        phone: addressDraft.phone.trim(), address: addressDraft.address.trim(),
        landmark: addressDraft.landmark.trim() || null, pin_code: addressDraft.pin_code.trim(),
        is_default: Boolean(addressDraft.is_default) };
      const result = await customerRequest(addressDraft.id ? "/customer-auth/addresses/" + addressDraft.id : "/customer-auth/addresses", {
        method: addressDraft.id ? "PATCH" : "POST", body: JSON.stringify(payload)
      });
      const saved = result?.address;
      if (!saved?.id) throw new Error("The saved address response was incomplete.");
      const refreshed = await customerRequest("/customer-auth/addresses");
      const items = Array.isArray(refreshed?.items) ? refreshed.items : [];
      setSavedAddresses(items);
      selectSavedAddress(saved);
      setAddressEditorOpen(false);
      setNotice("Delivery address saved to your Super Bajaar account.");
    } catch (reason) { setError(reason.message || "Could not save delivery address."); }
    finally { setAddressBusy(false); }
  };
  const setDefaultCustomerAddress = async address => {
    setAddressBusy(true); setError("");
    try {
      await customerRequest("/customer-auth/addresses/" + address.id, { method: "PATCH", body: JSON.stringify({ is_default: true }) });
      const refreshed = await customerRequest("/customer-auth/addresses");
      setSavedAddresses(refreshed.items || []);
      setNotice("Default delivery address updated.");
    } catch (reason) { setError(reason.message || "Could not update default address."); }
    finally { setAddressBusy(false); }
  };
  const deleteCustomerAddress = async address => {
    if (!window.confirm("Delete this saved address?")) return;
    setAddressBusy(true); setError("");
    try {
      await customerRequest("/customer-auth/addresses/" + address.id, { method: "DELETE" });
      const refreshed = await customerRequest("/customer-auth/addresses");
      const items = refreshed.items || [];
      setSavedAddresses(items);
      const next = items.find(item => item.is_default) || items[0];
      if (next) selectSavedAddress(next);
      else { setSelectedAddressId(""); setCustomer(old => ({ ...old, address: "", pin: "" })); }
      setNotice("Address deleted.");
    } catch (reason) { setError(reason.message || "Could not delete address."); }
    finally { setAddressBusy(false); }
  };
  const saveCustomerProfile = async event => {
    event.preventDefault();
    if (!customerToken || !customerAuth) {
      setError("Sign in to update your customer profile.");
      return;
    }
    try {
      const result = await customerRequest("/customer-auth/me", {
        method: "PATCH",
        body: JSON.stringify({ full_name: customer.name.trim() }),
      });
      if (!result?.customer) throw new Error("The profile update response was incomplete.");
      setCustomerAuth(result.customer);
      setCustomer(old => ({ ...old, name: result.customer.full_name || old.name }));
      setNotice("Your name has been saved to your Super Bajaar account. Email and mobile changes require separate verification.");
      setError("");
    } catch (reason) {
      setError(reason.message || "Could not save your customer profile.");
    }
  };
  const openWishlist = () => {
    window.history.pushState({}, "", "/wishlist");
    setRoutePath("/wishlist");
    setCategoryId("");
    setSearch("");
    window.scrollTo({ top: 0, behavior: "smooth" });
  };
  const loadMyOrders = async () => {
    setOrdersBusy(true); setError(""); setMyOrderDetail(null);
    try { const result = await customerRequest("/customer-auth/orders"); setMyOrders(result.items || []); }
    catch (reason) { setError(reason.message || "Could not load your orders."); }
    finally { setOrdersBusy(false); }
  };
  const openMyOrder = async orderNumber => {
    setOrdersBusy(true); setError("");
    try { setMyOrderDetail(await customerRequest("/customer-auth/orders/" + encodeURIComponent(orderNumber))); }
    catch (reason) { setError(reason.message || "Could not open this order."); }
    finally { setOrdersBusy(false); }
  };
  const uploadTicketAttachments = (caseNumber, files, messageId) => {
    const body = new FormData();
    files.forEach(file => body.append("files", file));
    return customerRequest("/customers/support-portal/tickets/" + encodeURIComponent(caseNumber) + "/attachments" + (messageId ? "?message_id=" + messageId : ""), { method: "POST", body });
  };
  const pickTicketFiles = (event, current, setFiles) => {
    const { files, problem } = mergeTicketFiles(current, Array.from(event.target.files || []));
    setFiles(files); setTicketFileProblem(problem);
    event.target.value = "";
  };
  const submitSupportTicket = async event => {
    event.preventDefault();
    if (!customerToken || !customerAuth) { openCustomerAuth("login", "/account"); setError("Sign in to raise a support ticket."); return; }
    if (!ticketDraft.category) { setError("Choose a subject for your ticket."); return; }
    setTicketBusy(true); setError(""); setTicketCreated(null); setTicketTracked(null); setTicketUploadIssue(""); setTicketFileProblem("");
    let result;
    try {
      result = await customerRequest("/customers/support-portal/tickets", { method: "POST", body: JSON.stringify({ category: ticketDraft.category, description: ticketDraft.description.trim() }) });
    } catch (reason) { setError(reason.message || "Could not create your support ticket."); setTicketBusy(false); return; }
    setTicketCreated(result.ticket);
    setTicketLookup({ caseNumber: result.ticket.case_number });
    if (ticketFiles.length) {
      try { await uploadTicketAttachments(result.ticket.case_number, ticketFiles, result.message_id); }
      catch (reason) { setTicketUploadIssue((reason.message || "Attachments could not be uploaded.") + " Your ticket was created. Open it and reply to attach the files again."); }
    }
    setTicketDraft({ category: "", description: "" });
    setTicketFiles([]);
    try {
      const list = await customerRequest("/customers/support-portal/tickets");
      setMyTickets(list.items || []);
    } catch { /* The ticket exists; the list refreshes the next time this tab opens. */ }
    setTicketBusy(false);
  };
  const submitInsuranceRequest = async event => {
    event.preventDefault();
    if (!customerToken || !customerAuth) { openCustomerAuth("login", "/account"); setError("Sign in before submitting a consultation request."); return; }
    setTicketBusy(true); setError(""); setTicketCreated(null); setTicketTracked(null);
    const form = event.currentTarget;
    const data = new FormData(form);
    const service = String(data.get("insuranceType") || "Life Insurance");
    const payload = {
      subject: "Insurance consultation request — " + service,
      description: "Customer requested a consultation for " + service + ". Preferred contact time: " + String(data.get("contactTime") || "Any time") + ". Customer message: " + String(data.get("message") || "").trim(),
    };
    try {
      const result = await customerRequest("/customers/support-portal/tickets", { method: "POST", body: JSON.stringify(payload) });
      setTicketCreated(result.ticket);
      setTicketLookup({ caseNumber: result.ticket.case_number });
      form.reset();
      setNotice("Your insurance consultation request has been submitted.");
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
    event.preventDefault();
    if (!customerToken || !customerAuth) { openCustomerAuth("login", "/account"); return; }
    setTicketBusy(true); setError(""); setTicketTracked(null);
    try {
      const result = await customerRequest("/customers/support-portal/tickets/" + encodeURIComponent(ticketLookup.caseNumber.trim()));
      setTicketTracked(result);
    } catch (reason) { setError(reason.message || "Could not find that ticket in your account."); }
    finally { setTicketBusy(false); }
  };
  const openCustomerTicket = async caseNumber => {
    setTicketBusy(true); setError("");
    try {
      const result = await customerRequest("/customers/support-portal/tickets/" + encodeURIComponent(caseNumber));
      setTicketTracked(result);
      setTicketLookup({ caseNumber });
    } catch (reason) { setError(reason.message || "Could not open this ticket."); }
    finally { setTicketBusy(false); }
  };
  const downloadTicketAttachment = async (caseNumber, attachment) => {
    setError("");
    try {
      const result = await customerRequest("/customers/support-portal/tickets/" + encodeURIComponent(caseNumber) + "/attachments/" + attachment.id + "/download");
      const link = document.createElement("a");
      link.href = result.url; link.target = "_blank"; link.rel = "noopener noreferrer";
      document.body.appendChild(link); link.click(); link.remove();
    } catch (reason) { setError(reason.message || "Could not open this attachment."); }
  };
  const replyToCustomerTicket = async event => {
    event.preventDefault();
    const caseNumber = ticketTracked?.ticket?.case_number;
    if (!caseNumber || !ticketReply.trim()) return;
    setTicketBusy(true); setError(""); setTicketFileProblem("");
    try {
      const sent = await customerRequest("/customers/support-portal/tickets/" + encodeURIComponent(caseNumber) + "/messages", {
        method: "POST", body: JSON.stringify({ body: ticketReply.trim() }),
      });
      setTicketReply("");
      if (replyFiles.length) {
        try { await uploadTicketAttachments(caseNumber, replyFiles, sent.message?.id); }
        catch (reason) { setError("Your reply was sent, but the attachments could not be uploaded: " + (reason.message || "please try again.")); }
      }
      setReplyFiles([]);
      const result = await customerRequest("/customers/support-portal/tickets/" + encodeURIComponent(caseNumber));
      setTicketTracked(result);
    } catch (reason) { setError(reason.message || "Could not send your reply."); }
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
  // The department strip is a navigation shortcut for top-level categories only.
  // Keep displayCategories unchanged for category tiles, filtering, and nested category routes.
  const departmentCategories = useMemo(() => displayCategories.filter(category => {
    const parentId = category.parent_id ?? category.parent_category_id ?? category.parentId;
    return parentId == null || String(parentId).trim() === "";
  }), [displayCategories]);

  const visibleVariants = useMemo(() => {
    const term = search.trim().toLowerCase();
    const scoreMap = term ? searchIndex.scores(term) : null;
    const matched = variants.filter(v => {
      if (v.is_active === false) return false;
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
      return !scoreMap || (scoreMap.get(Number(v.product_id)) || 0) > 0;
    });
    return scoreMap ? matched.sort((a, b) => (scoreMap.get(Number(b.product_id)) || 0) - (scoreMap.get(Number(a.product_id)) || 0)) : matched;
  }, [variants, productById, categoryId, routeCategoryName, search, displayCategories, searchIndex]);
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
  const recentVariants = useMemo(() => recentlyViewed.map(item => variants.find(v => Number(v.id) === Number(item.variantId))).filter(Boolean).filter(variant => variant.is_active !== false).filter((variant, index, items) => items.findIndex(item => Number(item.product_id) === Number(variant.product_id)) === index).slice(0,8), [recentlyViewed, variants]);
  const categorySubcategories = useMemo(() => {
    const parent = displayCategories.find(c => String(c.name || "").trim().toLowerCase() === String(routeCategoryName).trim().toLowerCase());
    if (!parent) return [];
    return categories.filter(c => [c.parent_id, c.parent_category_id, c.parentId].some(id => id != null && String(id) === String(parent.id)));
  }, [categories, displayCategories, routeCategoryName]);
  const subcategoryProductRows = useMemo(() => categorySubcategories.map(category => {
    const items = variants.filter(variant => variant.is_active !== false).filter((variant, index, allVariants) => {
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
    const dealScores = term ? searchIndex.scores(term) : null;
    const discounted = variants.filter(v => {
      if (v.is_active === false) return false;
      const p = productById.get(Number(v.product_id)) || {};
      const price = Number(v.selling_price ?? v.price ?? 0);
      const compare = Number(v.compare_at_price ?? v.original_price ?? v.mrp ?? p.compare_at_price ?? p.original_price ?? p.mrp ?? 0);
      const discount = Number(v.discount_percent ?? v.discount_percentage ?? p.discount_percent ?? p.discount_percentage ?? 0);
      const matchesSearch = !dealScores || (dealScores.get(Number(v.product_id)) || 0) > 0;
      return matchesSearch && (((compare > price) && price > 0) || discount > 0);
    });
    return discounted.filter((variant, index, all) => all.findIndex(item => Number(item.product_id) === Number(variant.product_id)) === index).slice(0, 24);
  }, [variants, productById, search, searchIndex]);
  const total = cart.reduce((sum, line) => sum + Number(line.selling_price || 0) * line.quantity, 0);
  const redeemableCoins = clampRedeemCoins(redeemCoins, redemptionQuote?.maximum_redeemable_coins ?? 0);
  const redemptionDiscount = redeemableCoins * Number(redemptionQuote?.coin_value_in_rupees || 1);

  useEffect(() => {
    if (!isCheckoutPage || !customerToken || !customerAuth?.email || total <= 0) {
      setRedemptionQuote(null);
      setRedeemCoins(0);
      setRedemptionQuoteBusy(false);
      setRedemptionQuoteError("");
      return;
    }
    let active = true;
    setRedemptionQuoteBusy(true);
    setRedemptionQuoteError("");
    customerRequest("/loyalty/customer/redemption-quote?amount=" + encodeURIComponent(total.toFixed(2)))
      .then(quote => {
        if (!active) return;
        setRedemptionQuote(quote);
        setRedeemCoins(current => clampRedeemCoins(current, quote?.maximum_redeemable_coins ?? 0));
      })
      .catch(reason => {
        if (!active) return;
        setRedemptionQuote(null);
        setRedeemCoins(0);
        setRedemptionQuoteError(reason.message || "Could not check Super Coin redemption.");
      })
      .finally(() => { if (active) setRedemptionQuoteBusy(false); });
    return () => { active = false; };
  }, [isCheckoutPage, customerToken, customerAuth?.email, total]);

  const addToCart = (variant, requestedQuantity = 1) => {
    if (isProductUnavailable(variant.product_id)) {
      setError(regionUnserved ? "Sorry, Super Bajaar isn't available in your region yet." : "This product isn't available in your area.");
      return;
    }
    const quantity = Math.min(100000, Math.max(1, Math.floor(Number(requestedQuantity) || 1)));
    trackAnalyticsEvent("add_to_cart", {
      currency: "INR",
      value: Number(variant.selling_price || 0) * quantity,
      items: [{ item_id: String(variant.sku || variant.id), item_name: variant.product_name || "Product", price: Number(variant.selling_price || 0), quantity }],
    });
    setCart(old => {
      const found = old.find(line => line.id === variant.id);
      return found ? old.map(line => line.id === variant.id ? { ...line, quantity: Math.min(100000, line.quantity + quantity) } : line)
        : [...old, { ...variant, quantity }];
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
    if (!termsAccepted) { setError("Please accept the Terms & Conditions and acknowledge the Privacy Policy before placing your order."); return; }
    trackAnalyticsEvent("begin_checkout", {
      currency: "INR",
      value: total,
      items: cart.map(line => ({ item_id: String(line.sku || line.id), item_name: line.product_name || "Product", price: Number(line.selling_price || 0), quantity: line.quantity })),
    });
    setSubmitting(true); setError(""); setNotice(""); setOrder(null);
    try {
      const delivery = selectedAddress;
      if (!delivery) throw new Error("Choose or add a saved delivery address before placing your order.");
      const phone = (customer.phone || delivery.phone).trim();
      const address = delivery.address.trim();
      if (phone.length < 7 || phone.length > 20) {
        throw new Error("Enter a valid contact phone number for delivery.");
      }
      if (address.length < 5 || address.length > 1000) {
        throw new Error("Enter your complete delivery address (at least 5 characters).");
      }
      const pin = String(delivery.pin_code || "").trim();
      if (!/^[0-9]{6}$/.test(pin)) {
        throw new Error("Enter a valid six-digit delivery PIN before placing your order.");
      }
      const serviceability = await customerRequest("/delivery/serviceability/" + encodeURIComponent(pin));
      if (!serviceability?.serviceable) {
        throw new Error(serviceability?.message || "Sorry, Super Bajaar isn't available in your region yet.");
      }
      const blockedNow = cart.filter(line => (serviceability.blocked_product_ids || []).map(Number).includes(Number(line.product_id)));
      if (blockedNow.length) {
        throw new Error("Not available in your area: " + blockedNow.map(line => line.product_name || line.sku).join(", ") + ". Remove these items to continue.");
      }
      const wantsExpress = effectiveDeliveryType === "express" && serviceability.express_available;
      const orderPayload = {
        channel: "website",
        customer_name: customer.name.trim() || delivery.recipient_name || customerAuth.full_name,
        customer_phone: phone || null,
        customer_email: customerAuth.email,
        delivery_pin: pin || null,
        delivery_type: wantsExpress ? "express" : "standard",
        notes: ["Website checkout", "Customer accepted Terms & Conditions and acknowledged Privacy Policy (version 2026-11-04)", customer.email.trim() ? "Email: " + customer.email.trim() : "", "Delivery recipient: " + (customer.name.trim() || delivery.recipient_name), "Delivery address (" + delivery.label + "): " + address, delivery.landmark ? "Landmark: " + delivery.landmark : "", "Address contact: " + delivery.phone, "Order contact: " + phone].filter(Boolean).join(" | "),
        lines: cart.map(line => ({ variant_id: line.id, quantity: line.quantity })),
        redeem_coins: redeemableCoins,
      };
      orderPayload.checkout_idempotency_key = checkoutIdempotencyKey(orderPayload);
      const created = await customerRequest("/orders", {
        method: "POST",
        body: JSON.stringify(orderPayload),
      });
      const gatewayOrder = await customerRequest("/razorpay/orders", {
        method: "POST",
        body: JSON.stringify({ order_id: created.id }),
      });
      await loadRazorpayCheckout();
      const paymentResult = await new Promise((resolve, reject) => {
        let settled = false;
        const finish = (callback, value) => {
          if (settled) return;
          settled = true;
          callback(value);
        };
        const checkout = new window.Razorpay({
          key: gatewayOrder.key_id,
          amount: gatewayOrder.amount,
          currency: gatewayOrder.currency,
          name: "Super Bajaar",
          description: "Order " + gatewayOrder.order_number,
          order_id: gatewayOrder.razorpay_order_id,
          prefill: {
            name: customerAuth.full_name || customer.name,
            email: customerAuth.email,
            contact: customer.phone,
          },
          theme: { color: "#6b35b5" },
          handler: response => finish(resolve, response),
          modal: { ondismiss: () => finish(reject, new Error("Payment window closed. Your basket is safe; you can retry checkout.")) },
        });
        checkout.on("payment.failed", response => {
          const reason = response?.error?.description || "Payment failed. Your basket is safe; please try again.";
          finish(reject, new Error(reason));
        });
        checkout.open();
      });
      const verification = await customerRequest("/razorpay/verify", {
        method: "POST",
        body: JSON.stringify(paymentResult),
      });
      clearCheckoutIdempotencyKey();
      setOrder(created);
      setCart([]);
      setTermsAccepted(false);
      setNotice(verification.refund_required ? "Payment was captured, but this order was already cancelled. Please contact support to arrange a refund." : "Payment received securely. Your order is confirmed.");
      try {
        trackAnalyticsEvent("order_placed", {
          currency: "INR",
          value: Number(created?.total ?? 0),
          transaction_id: String(created?.order_number || created?.order_id || created?.id || ""),
          items: cart.map(line => ({ item_id: String(line.sku || line.id), item_name: line.product_name || "Product", price: Number(line.selling_price || 0), quantity: line.quantity })),
        });
      } catch {
        // Analytics must never turn a successfully accepted order into a retryable checkout error.
      }
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
    const priceVariant = productVariants.find(item => Number(item.selling_price || 0) === minPrice) || variant;
    const mrp = Number(priceVariant.mrp ?? priceVariant.compare_at_price ?? 0);
    const offPercent = mrp > minPrice && minPrice > 0 ? Math.round((mrp - minPrice) / mrp * 100) : 0;
    const reviewInfo = reviewSummary[Number(variant.product_id)];
    const ratingCount = Number(reviewInfo?.review_count ?? 0);
    const ratingAverage = Number(reviewInfo?.rating_average ?? 0);
    const openDetails = () => openProductPage(variant);
    const unavailable = isProductUnavailable(variant.product_id);
    return <article className={"storefront-product-card" + (unavailable ? " is-unavailable" : "")} key={variant.product_id} role="link" tabIndex={0} onClick={openDetails} onKeyDown={event => { if (event.target === event.currentTarget && (event.key === "Enter" || event.key === " ")) { event.preventDefault(); openDetails(); } }}>
      <div className="storefront-product-art">{variant.image_url ? <img className="storefront-product-image" src={variant.image_url} alt={product?.name || variant.product_name || "Product"} loading="lazy"/> : <span>{(() => { const I = catIcons[tile.icon]; return I ? <I size={40} strokeWidth={1.6} aria-hidden="true" /> : tile.icon; })()}</span>}<button type="button" className={"storefront-wishlist " + (saved ? "is-saved" : "")} onClick={event => { event.stopPropagation(); setWishlist(old => saved ? old.filter(id => !productVariants.some(item => Number(item.id) === Number(id))) : [...new Set([...old, ...productVariants.map(item => Number(item.id))])]); }} aria-label={(saved ? "Remove from" : "Add to") + " wishlist: " + (product?.name || variant.sku)} aria-pressed={saved}><Heart size={19} strokeWidth={1.9} fill={saved ? "currentColor" : "none"} /></button></div>
      <small>{product?.brand || product?.name || "Super Bajaar"}</small>
      <h3><button type="button" className="storefront-product-title" onClick={event => { event.stopPropagation(); openDetails(); }}>{product?.name || variant.product_name || variant.sku}</button></h3>
      {hasSelectableVariants && <p className="storefront-sku">Choose colour, size or weight</p>}
      <span className={"storefront-product-rating" + (ratingCount > 0 ? "" : " is-empty")}>{ratingCount > 0 ? <><Star size={13} fill="currentColor" aria-hidden="true" /> <b>{ratingAverage.toFixed(1)}</b> ({ratingCount} reviews)</> : "No reviews yet"}</span>
      <strong className="storefront-card-price">{minPrice === maxPrice ? money(minPrice) : money(minPrice) + " – " + money(maxPrice)}{offPercent > 0 && <><s className="storefront-card-mrp" aria-label={"MRP " + money(mrp)}>{money(mrp)}</s><em className="storefront-card-off">{offPercent}% off</em></>}</strong>
      {coinsFor(product, minPrice) > 0 && <span className="storefront-product-coins"><Coins size={14} /> Earn {minPrice === maxPrice ? "" : "from "}{coinsFor(product, minPrice)} Super Coins</span>}
      {unavailable ? <button type="button" className="storefront-add" disabled onClick={event => event.stopPropagation()}>{regionUnserved ? "Not available in your region" : "Not available in your area"}</button> : hasSelectableVariants ? <button type="button" className="storefront-add" onClick={event => { event.stopPropagation(); openDetails(); }}>Choose options</button> : <button type="button" className="storefront-add" onClick={event => { event.stopPropagation(); addToCart(variant); }}><ShoppingBag size={17} strokeWidth={2} /> Add to basket</button>}
    </article>;
  }
  function coinsFor(product, amount) {
    const rule = loyaltyRules.find(r => r.scope_type === "product" && Number(r.scope_id) === Number(product?.id)) || loyaltyRules.find(r => r.scope_type === "category" && Number(r.scope_id) === Number(product?.category_id)) || loyaltyRules.find(r => r.scope_type === "default");
    const rate = Number(rule?.coins_per_100 ?? loyaltyDefaultRate);
    return Math.floor(Number(amount || 0) / 100 * (Number.isFinite(rate) ? rate : 0));
  }
  function renderDiscoverySection(title, subtitle, items, icon) {
    if (!items.length) return null;
    const trackId = "carousel-" + title.toLowerCase().replace(/[^a-z0-9]+/g, "-");
    const moveTrack = direction => {
      const track = document.getElementById(trackId);
      const card = track?.querySelector(".storefront-product-card");
      if (!track || !card) return;
      const styles = window.getComputedStyle(track);
      const gap = Number.parseFloat(styles.columnGap || styles.gap || "0") || 0;
      track.scrollBy({ left: direction * (card.getBoundingClientRect().width + gap), behavior: "smooth" });
    };
    return <section className="storefront-discovery-section storefront-home-section" id={title === "Best Sellers" ? "deals" : undefined}>
      <div className="storefront-section-heading storefront-carousel-heading">
        <div><span className="storefront-kicker">{icon} DISCOVER MORE</span><h2>{title}</h2><p>{subtitle}</p></div>
        <div className="storefront-carousel-controls" aria-label={title + " carousel controls"}>
          <button type="button" aria-label={"Previous " + title} onClick={() => moveTrack(-1)}><ChevronLeft size={20} /></button>
          <button type="button" aria-label={"Next " + title} onClick={() => moveTrack(1)}><ChevronRight size={20} /></button>
        </div>
      </div>
      <div className="storefront-carousel-track" id={trackId} tabIndex={0} aria-label={title + " products"}>{items.map(renderProductCard)}</div>
    </section>;
  }

  return <main className="storefront">
    <GoogleAnalytics pagePath={routePath} />
    <div className="storefront-promo"><span aria-hidden="true">✦</span> Everyday essentials, made easier to shop <span>· Check delivery availability by PIN</span></div>
    <header className="storefront-header">
      <a className="storefront-brand" href="/" onClick={event => { event.preventDefault(); openShopHome(); }} aria-label="Super Bajaar home"><span className="storefront-logo"><img src="/superbajaar.svg" alt="" /></span><span><strong>Super Bajaar <span className="storefront-crown" aria-hidden="true">♛</span></strong><small>Your Everyday Super Store</small></span></a>
      <div className="storefront-header-search storefront-search-box" role="search">
        <label className="sr-only" htmlFor="storefront-search-input">Search products</label>
        <input id="storefront-search-input" type="search" autoComplete="off" enterKeyHint="search" value={search} onChange={e => onSearchInput(e.target.value)} onFocus={() => setSuggestOpen(true)} onBlur={() => setTimeout(() => setSuggestOpen(false), 150)} onKeyDown={e => { if (e.key === "Enter") { e.preventDefault(); submitSearch(); } else if (e.key === "Escape") setSuggestOpen(false); }} placeholder="Search groceries, snacks and more…" />
        <button type="button" className="storefront-search-go" aria-label="Search" onMouseDown={e => e.preventDefault()} onClick={submitSearch}><Search aria-hidden="true" size={19} /></button>
        {suggestOpen && search.trim() && <div className="storefront-suggest" role="listbox" aria-label="Search suggestions">
          {suggestions.length ? <>
            {suggestions.map(item => { const product = productById.get(Number(item.product_id)); const name = product?.name || item.product_name || item.sku; return <button type="button" role="option" key={item.product_id} className="storefront-suggest-item" onMouseDown={e => e.preventDefault()} onClick={() => { setSuggestOpen(false); setSearch(""); openProductPage(item); }}><span className="storefront-suggest-img">{item.image_url ? <img src={item.image_url} alt="" loading="lazy" /> : null}</span><span className="storefront-suggest-text"><strong>{name}</strong><small>{product?.brand || "Super Bajaar"}</small></span><span className="storefront-suggest-price">{money(item.selling_price)}</span></button>; })}
            <button type="button" className="storefront-suggest-all" onMouseDown={e => e.preventDefault()} onClick={submitSearch}>See all results for “{search.trim()}”</button>
          </> : <p className="storefront-suggest-empty">No matches for “{search.trim()}”. Try another spelling or a simpler word.</p>}
        </div>}
      </div>
      <div className="storefront-actions"><button type="button" className="storefront-delivery" onClick={() => { setDeliveryDraft(deliveryPin); setDeliveryMessage(""); setDeliveryOpen(true); }} aria-haspopup="dialog"><small>Deliver to</small><strong><MapPin size={13} /> {deliveryPin || "Set PIN"} ▾</strong><small className="storefront-delivery-note">Check delivery availability</small></button><a className="storefront-icon-action" href="/wishlist" aria-label={`Open wishlist, ${wishlist.length} saved`} onClick={event => { event.preventDefault(); openWishlist(); }}><Heart size={22} strokeWidth={1.8} /><small>{wishlist.length}</small></a><a className="storefront-icon-action" href="#basket" aria-label="Shopping basket" onClick={event => { event.preventDefault(); openCheckout(); }}><ShoppingBag size={22} strokeWidth={1.8} /><small>{cart.reduce((n, line) => n + line.quantity, 0)}</small></a><div className="storefront-account-wrap"><button type="button" className="storefront-account-button" aria-label="Open account menu" aria-expanded={accountOpen} onClick={() => setAccountOpen(value => !value)}><UserRound size={20} /><span>Account</span></button>{accountOpen && <div className="storefront-account-menu storefront-account-menu-desktop"><strong>Your account</strong><p>{customerAuth ? "Manage your profile, orders and Super Coins." : "Sign in to manage orders, referrals and Super Coins."}</p><button type="button" onClick={customerAuth ? openAccount : () => openCustomerAuth("login", "/account")}>{customerAuth ? "My Account" : "Customer Sign in"}</button>{customerAuth && <button type="button" onClick={signOutCustomer}>Sign out</button>}{canOpenAdmin && <a href="/admin">Admin Console</a>}</div>}</div></div>
    </header>
    {accountOpen && <div className="storefront-account-sheet-backdrop" role="presentation" onClick={event => { if (event.target === event.currentTarget) setAccountOpen(false); }}><section className="storefront-account-sheet" role="dialog" aria-modal="true" aria-labelledby="storefront-account-sheet-title"><div className="storefront-account-sheet-handle" aria-hidden="true" /><div className="storefront-account-sheet-heading"><div><span className="storefront-kicker">SUPER BAJAAR</span><h2 id="storefront-account-sheet-title">Your account</h2></div><button type="button" className="storefront-modal-close" aria-label="Close account menu" onClick={() => setAccountOpen(false)}><X size={19} /></button></div><p>Manage your profile and shopping experience.</p><button type="button" className="storefront-account-sheet-action" onClick={customerAuth ? openAccount : () => { setAccountOpen(false); openCustomerAuth("login", "/account"); }}><span className="storefront-account-sheet-action-icon"><UserRound size={20} /></span><span><strong>{customerAuth ? "My Account" : "Customer Sign in"}</strong><small>{customerAuth ? "Contact and delivery details" : "Sign in to manage your account"}</small></span><span aria-hidden="true">›</span></button>{customerAuth && <button type="button" className="storefront-account-sheet-action" onClick={signOutCustomer}><span className="storefront-account-sheet-action-icon">↪</span><span><strong>Sign out</strong><small>Sign out of your customer account</small></span><span aria-hidden="true">›</span></button>}{canOpenAdmin && <a className="storefront-account-sheet-action" href="/admin"><span className="storefront-account-sheet-action-icon">⌘</span><span><strong>Admin Console</strong><small>Store management</small></span><span aria-hidden="true">›</span></a>}</section></div>}
    <nav className="storefront-department-nav" aria-label="Shop departments"><a href="/#categories" onClick={event => { event.preventDefault(); openShopHome(); setTimeout(() => document.getElementById("categories")?.scrollIntoView({ behavior: "smooth" }), 0); }}>☰ All Categories</a><a href="/deals" onClick={event => { event.preventDefault(); openDealsPage(); }}>Deals <Flame size={14} /></a><button type="button" onClick={() => { openShopHome(); setTimeout(() => document.getElementById("products")?.scrollIntoView({ behavior: "smooth" }), 0); }}>Shop All</button>{departmentCategories.map(category => <a key={category.id} href={"/category/" + categorySlug(category.name)} aria-current={routeSlug === categorySlug(category.name) ? "page" : undefined}>{category.name === "Fresh Daily" ? "Fresh" : category.name}</a>)}</nav>
    {homeHeroImages.length > 0 && !isProductPage && !isCustomerAuthPage && !isCategoryPage && !isDealsPage && !isWishlistPage && !isAccountPage && !isCheckoutPage && !isInfoPage && !isSearchPage && <section className="storefront-home-banner" aria-label="Featured offers"><CategoryHeroSlider images={homeHeroImages} title="Super Bajaar" /></section>}
    {!isProductPage && !isCustomerAuthPage && !isCategoryPage && !isDealsPage && !isWishlistPage && !isAccountPage && !isCheckoutPage && !isInfoPage && !isSearchPage && !homeHeroImages.length && <section className="storefront-hero storefront-home-hero">
      <div className="storefront-hero-copy"><span className="storefront-kicker"><i /> YOUR EVERYDAY SUPER STORE</span><h1>Daily essentials<br /><em>at your fingertips.</em></h1><p>Groceries, fresh picks and everyday favourites for your home — all in one easy shopping destination.</p><a className="storefront-primary" href="#products">Start shopping <span>→</span></a><div className="storefront-trust"><span>Easy everyday shopping</span><span>Delivery availability by PIN</span></div></div>
      <div className="storefront-hero-art" aria-hidden="true"><div className="hero-icon-grid">{[ShoppingCart, Leaf, Shirt, Gift, Headphones, Home].map((I, i) => <span key={i}><I size={34} strokeWidth={1.6} /></span>)}</div><div className="art-caption">Everything for your everyday</div></div>
    </section>}
    {!isProductPage && !isCategoryPage && !isDealsPage && !isWishlistPage && !isAccountPage && !isCheckoutPage && !isInfoPage && !isSearchPage && <section className="storefront-categories storefront-home-section" id="categories">
      <div className="storefront-section-heading"><div><span className="storefront-kicker">FIND YOUR FAVOURITES</span><h2>Shop by category</h2></div><span className="storefront-heading-note">Choose a category to filter products.</span></div>
      <div className="storefront-category-grid">

        {displayCategories.map((category, index) => {
          const tile = categoryArt[category.name] || art[index % art.length];
          return <button type="button" className={"storefront-category " + (String(category.id) === categoryId ? "is-selected" : "")} key={category.id} onClick={() => openCategory(category)}>
            <span className={"storefront-category-art tone-" + tile.tone}><span>{(() => { const I = catIcons[tile.icon]; return I ? <I size={40} strokeWidth={1.6} aria-hidden="true" /> : tile.icon; })()}</span><i>↗</i></span><strong>{category.name}</strong><small>{category.description || tile.detail}</small>
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
        {oauthProviders.length > 0 && <div className="storefront-social-login">
          <p className="storefront-social-divider"><span>or continue with</span></p>
          {oauthProviders.includes("google") && <a className="storefront-social-button" href={API_BASE_URL + "/customer-auth/oauth/google/start"}>Continue with Google</a>}
          {oauthProviders.includes("github") && <a className="storefront-social-button" href={API_BASE_URL + "/customer-auth/oauth/github/start"}>Continue with GitHub</a>}
        </div>}
        <p className="storefront-account-note">{customerAuthMode === "register" ? "Already registered? " : "New to Super Bajaar? "}<button type="button" className="storefront-inline-link" onClick={()=>{setCustomerAuthMode(customerAuthMode==="register"?"login":"register");setError("");}}>{customerAuthMode === "register" ? "Sign in" : "Create an account"}</button></p>
      </form>
    </section>}
    {isCheckoutPage && <section className="storefront-checkout-page"><div className="storefront-category-breadcrumb"><button type="button" onClick={openShopHome}>Home</button><span>/</span><span>Checkout</span></div><div className="storefront-checkout-page-heading"><span className="storefront-kicker">YOUR BASKET</span><h1>Checkout</h1><p>Review your items and delivery details before placing your order.</p></div>{error && <p className="storefront-alert" role="alert">{error}</p>}{notice && <p className="storefront-order-success" role="status">{notice}</p>}{order && <p className="storefront-order-success" role="status">Order placed: <strong>{order.order_number}</strong> · {money(order.total)}</p>}<section className="storefront-checkout" id="basket"><div className="storefront-checkout-section checkout-section--summary"><span className="storefront-kicker">ORDER SUMMARY</span><h2>Your basket</h2><p>Prices and order totals are verified by our server. Pay securely with Razorpay at checkout.</p></div><div className="storefront-basket-lines">{cart.length ? cart.map(line => <div className="storefront-basket-line" key={line.id}><div className="basket-line-info"><strong>{line.product_name || line.sku}</strong><small>{money(line.selling_price)} each</small><small className="basket-line-sku">{line.sku}</small></div><div className="basket-line-qty" role="group" aria-label={"Quantity for " + (line.product_name || line.sku)}><button type="button" aria-label="Decrease quantity" onClick={() => setQuantity(line.id, Number(line.quantity) - 1)}>−</button><input type="number" inputMode="numeric" min="0" max="100000" step="1" value={line.quantity} onChange={e => setQuantity(line.id, e.target.value)} aria-label="Quantity" /><button type="button" aria-label="Increase quantity" onClick={() => setQuantity(line.id, Number(line.quantity) + 1)}>+</button></div><strong className="basket-line-total">{money(line.selling_price * line.quantity)}</strong><button type="button" className="basket-line-remove" aria-label={"Remove " + line.sku} onClick={() => setCart(old => old.filter(x => x.id !== line.id))}>×</button></div>) : <div className="storefront-checkout-empty"><h3>Your basket is empty</h3><p>Add products to your basket before placing an order.</p><button type="button" className="storefront-primary" onClick={openShopHome}>Continue shopping</button></div>}<div className="storefront-basket-total"><span>Subtotal</span><strong>{money(total)}</strong></div>{cart.length > 0 && (() => { const earn = cart.reduce((sum, l) => sum + coinsFor(productById.get(Number(l.product_id)), Number(l.selling_price || 0) * Number(l.quantity || 0)), 0); return earn > 0 ? <p className="storefront-product-coins storefront-product-coins-page"><Coins size={15} /> You will earn {earn} Super Coins on this order, credited after delivery</p> : null; })()}{cart.length > 0 && <div className="storefront-super-coin-redemption"><div><span className="storefront-kicker">REWARDS AT CHECKOUT</span><h3><Coins size={18}/> Use Super Coins</h3><p>1 Super Coin = ₹1. Redeem only available, unexpired coins.</p></div>{redemptionQuoteBusy ? <p role="status">Checking your Super Coin balance…</p> : redemptionQuoteError ? <p className="storefront-account-note" role="status">{redemptionQuoteError} You can continue without redemption.</p> : redemptionQuote?.redemption_enabled && Number(redemptionQuote.maximum_redeemable_coins || 0) > 0 ? <><p>Available: <strong>{Number(redemptionQuote.available_coins || 0).toLocaleString("en-IN")}</strong> · Maximum for this order: <strong>{Number(redemptionQuote.maximum_redeemable_coins).toLocaleString("en-IN")}</strong></p><label>Super Coins to redeem<input type="number" min="0" max={redemptionQuote.maximum_redeemable_coins} step="1" value={redeemableCoins} onChange={event => setRedeemCoins(clampRedeemCoins(event.target.value, redemptionQuote.maximum_redeemable_coins))}/></label>{redeemableCoins > 0 && <p className="storefront-super-coin-discount">Super Coin discount: <strong>{money(redemptionDiscount)}</strong> · Estimated amount to pay: <strong>{money(Math.max(0, total - redemptionDiscount))}</strong></p>}</> : <p className="storefront-account-note">{redemptionQuote?.reason || (Number(redemptionQuote?.available_coins || 0) > 0 ? "No Super Coins can be applied to this order amount." : "You do not have any available, unexpired Super Coins to redeem.")}</p>}</div>}{cart.length>0 && <div className="storefront-checkout-content">
          <section className="storefront-checkout-section checkout-section--delivery"><div className="storefront-checkout-section-heading"><div><span className="storefront-kicker">DELIVERY DETAILS</span><h3>Choose delivery address</h3></div><div className="storefront-checkout-address-tools"><button type="button" onClick={()=>document.querySelector(".storefront-checkout-address-list")?.scrollIntoView({behavior:"smooth",block:"center"})}>Change address</button><button type="button" onClick={()=>openAddressEditor(null)}>+ Add address</button></div></div>
            {savedAddresses.length ? <div className="storefront-checkout-address-list">{savedAddresses.map(address=><button type="button" key={address.id} className={"storefront-checkout-address "+(String(address.id)===String(selectedAddressId)?"is-selected":"")} onClick={()=>selectSavedAddress(address)}><span className="storefront-address-radio">{String(address.id)===String(selectedAddressId)?"●":"○"}</span><span><strong>{address.label} {address.is_default?"· Default":""}</strong><b>{address.recipient_name} · {address.phone}</b><small>{address.address}{address.landmark?", "+address.landmark:""} · {address.pin_code}</small></span><span className="storefront-address-edit" onClick={e=>{e.stopPropagation();openAddressEditor(address);}}>Edit</span></button>)}</div> : <div className="storefront-checkout-no-address"><p>No saved delivery address. Add one to continue.</p><button type="button" className="storefront-primary" onClick={()=>openAddressEditor(null)}>Add delivery address</button></div>}
            {addressEditorOpen&&<form className="storefront-address-editor" onSubmit={saveCustomerAddress}><h3>{addressDraft.id?"Edit address":"Add new address"}</h3><label>Address type<select value={addressDraft.label} onChange={e=>setAddressDraft(v=>({...v,label:e.target.value}))}><option>Home</option><option>Work</option><option>Other</option></select></label><label>Recipient name<input required minLength="2" maxLength="200" value={addressDraft.recipient_name} onChange={e=>setAddressDraft(v=>({...v,recipient_name:e.target.value}))}/></label><label>Contact phone<input required minLength="7" maxLength="20" value={addressDraft.phone} onChange={e=>setAddressDraft(v=>({...v,phone:e.target.value}))}/></label><label className="storefront-address-editor-wide">Full address<textarea required minLength="5" maxLength="1000" rows="3" value={addressDraft.address} onChange={e=>setAddressDraft(v=>({...v,address:e.target.value}))}/></label><label>Landmark<input maxLength="200" value={addressDraft.landmark||""} onChange={e=>setAddressDraft(v=>({...v,landmark:e.target.value}))}/></label><label>Delivery PIN<input required inputMode="numeric" pattern="[1-9][0-9]{5}" maxLength="6" value={addressDraft.pin_code} onChange={e=>setAddressDraft(v=>({...v,pin_code:e.target.value.replace(/\\D/g,"").slice(0,6)}))}/></label><label className="storefront-address-default"><input type="checkbox" checked={Boolean(addressDraft.is_default)} onChange={e=>setAddressDraft(v=>({...v,is_default:e.target.checked}))}/> Set as default</label><div className="storefront-address-editor-actions"><button className="storefront-primary" type="submit" disabled={addressBusy}>{addressBusy?"Saving…":"Save address"}</button><button type="button" onClick={()=>setAddressEditorOpen(false)}>Cancel</button></div></form>}
          </section>
          {checkoutRegionUnserved && <p className="storefront-alert" role="alert">Sorry, Super Bajaar isn&apos;t available in your region yet. Choose a different delivery address.</p>}
          {!checkoutRegionUnserved && checkoutUnavailableLines.length > 0 && <p className="storefront-alert" role="alert">Not available in your area: {checkoutUnavailableLines.map(line => line.product_name || line.sku).join(", ")}. Remove these items from your basket to continue.</p>}
          {checkoutInfo?.serviceable && <section className="storefront-checkout-section storefront-delivery-type"><span className="storefront-kicker">DELIVERY TYPE</span><h3>How fast do you want it?</h3><div className="storefront-delivery-type-options"><label className={effectiveDeliveryType === "standard" ? "is-selected" : ""}><input type="radio" name="delivery-type" checked={effectiveDeliveryType === "standard"} onChange={() => setDeliveryType("standard")}/><span><strong>Standard delivery</strong><small>Usually 1–5 days</small></span></label>{expressOffered ? <label className={effectiveDeliveryType === "express" ? "is-selected" : ""}><input type="radio" name="delivery-type" checked={effectiveDeliveryType === "express"} onChange={() => setDeliveryType("express")}/><span><strong>Express delivery</strong><small>Available at {checkoutPin}</small></span></label> : <p className="storefront-account-note">{checkoutInfo.express_available ? "Express delivery isn't offered for every item in your basket." : "Express delivery isn't available in your area yet."}</p>}</div></section>}
          <form className="storefront-checkout-form" onSubmit={checkout}><section className="storefront-checkout-section checkout-section--contact"><span className="storefront-kicker">CONTACT DETAILS</span><h3>Who should we contact?</h3><label>Full name<input required minLength="1" maxLength="200" value={customer.name} onChange={e=>setCustomer(v=>({...v,name:e.target.value}))}/></label><label>Email address<input type="email" autoComplete="email" required maxLength="254" value={customer.email} onChange={e=>setCustomer(v=>({...v,email:e.target.value}))}/></label><label>Phone<input required minLength="7" maxLength="20" autoComplete="tel" value={customer.phone} onChange={e=>setCustomer(v=>({...v,phone:e.target.value}))}/></label></section>
          <section className="storefront-checkout-section checkout-section--payment"><span className="storefront-kicker">PAYMENT & CONFIRMATION</span><h3>Order total</h3><div className="storefront-checkout-total"><span>Subtotal</span><strong>{money(Math.max(0,total-redemptionDiscount))}</strong></div><p>Final amount, stock and discounts are verified securely by Super Bajaar.</p><label className="storefront-checkout-consent"><input type="checkbox" required checked={termsAccepted} onChange={e=>setTermsAccepted(e.target.checked)}/><span>I agree to the <a href="/pages/terms-and-conditions" onClick={e=>{e.preventDefault();openInfoPage("terms-and-conditions");}}>Terms &amp; Conditions</a> and acknowledge the <a href="/pages/privacy-policy" onClick={e=>{e.preventDefault();openInfoPage("privacy-policy");}}>Privacy Policy</a> and <a href="/pages/payment-information" onClick={e=>{e.preventDefault();openInfoPage("payment-information");}}>Payment Information</a>.</span></label><button type="submit" className="storefront-primary" disabled={submitting||redemptionQuoteBusy||!cart.length||!termsAccepted||!selectedAddress||checkoutRegionUnserved||checkoutUnavailableLines.length>0}>{submitting?"Opening secure payment…":"Pay securely with Razorpay"}</button></section></form></div>}</div></section></section>}
    {isAccountPage && <section className="storefront-account-page">
      <div className="storefront-category-breadcrumb"><button type="button" onClick={openShopHome}>Home</button><span>/</span><span>My Account</span></div>
      <div className="storefront-account-welcome"><span className="storefront-kicker">YOUR SUPER BAJAAR</span><h1>{customer.name.trim() ? `Hello, ${customer.name.trim().split(/\s+/)[0]}` : "My Account"}</h1><p>Manage your profile, purchases and support in one place.</p></div>
      <div className="storefront-account-layout">
        <nav className="storefront-account-nav" aria-label="Customer account sections">
          {[["overview","Overview","user-round"],["identity-claims","Identity claims","shield-check"],["loyalty","Loyalty Card & Coins","coins"],["referrals","Refer & Earn","users"],["orders","My Orders","package"],["tickets","My Tickets","ticket"],["wishlist","My Wishlist","heart"],["addresses","Addresses","map-pin"],["security","Security","shield-check"],["privacy","Privacy & Analytics","shield-check"]].map(([key,label])=><button key={key} type="button" className={accountSection===key?"is-active":""} onClick={()=>{if(key==="wishlist"){openWishlist();return;}setAccountSection(key);setNotice("");setError("");if(key==="referrals") loadReferrals();if(key==="loyalty") loadCustomerLoyalty();if(key==="orders") loadMyOrders();}}>{label}<span aria-hidden="true">›</span></button>)}
        </nav>
        <div className="storefront-account-panel">
          {accountSection==="overview" && <div className="storefront-account-section">
            <div className="storefront-account-section-heading"><div><h2>Personal details</h2><p>Your saved contact information.</p></div><span className="storefront-account-avatar">{customer.name.trim()?customer.name.trim().slice(0,1).toUpperCase():"S"}</span></div>
            {(customer.name||customer.email||customer.phone) ? <div className="storefront-account-summary">{customerAuth?.sbid&&<div><small>Super Bajaar ID</small><strong>{customerAuth.sbid}</strong></div>}{customer.name&&<div><small>Full name</small><strong>{customer.name}</strong></div>}{customer.email&&<div><small>Email address</small><strong>{customer.email}</strong></div>}{customer.phone&&<div><small>Mobile number</small><strong>{customer.phone}</strong></div>}</div> : <p className="storefront-account-empty">Your profile is not filled in yet. Add your details below so they are ready at checkout.</p>}
            <form className="storefront-account-form" onSubmit={saveCustomerProfile}><label>Full name<input autoComplete="name" required maxLength="200" value={customer.name} onChange={event=>setCustomer(old=>({...old,name:event.target.value}))}/></label><label>Mobile number<input autoComplete="tel" maxLength="20" value={customer.phone} onChange={event=>setCustomer(old=>({...old,phone:event.target.value}))}/></label><label>Email address<input type="email" autoComplete="email" maxLength="254" value={customer.email} onChange={event=>setCustomer(old=>({...old,email:event.target.value}))}/></label><button className="storefront-primary" type="submit">Save profile</button><p className="storefront-account-note">Your sign-in identity is stored securely by Super Bajaar. Address syncing is a separate feature.</p><button type="button" className="storefront-primary" onClick={signOutCustomer}>Sign out</button></form>
          </div>}
          {accountSection==="identity-claims" && <IdentityClaimsPanel customerToken={customerToken} />}
          {accountSection==="loyalty" && <div className="storefront-account-section storefront-account-section--loyalty">
            <span className="storefront-kicker">REWARDS FOR EVERYDAY SHOPPING</span>
            <h2>Loyalty Card &amp; Super Coins</h2>
            <p>Earn Super Coins on eligible purchases. The standard rate is {loyaltyDefaultRate} coin(s) per ₹100 eligible spend unless a product or category override applies.</p>
            <button className="storefront-primary" type="button" onClick={loadCustomerLoyalty} disabled={loyaltyBusy}>{loyaltyBusy ? "Loading card…" : "Refresh my Super Coin card"}</button>
            {loyaltyCustomerData && <><div className="storefront-loyalty-card">
              <div className="storefront-loyalty-card-top"><img className="storefront-loyalty-mark" src="/superbajaar.svg" alt="" /><span>SUPER BAJAAR<br/><strong>LOYALTY CARD</strong></span><CreditCard size={28}/></div>
              <div className="storefront-loyalty-card-bottom"><span>{customer.name.trim() || loyaltyCustomerData.account?.customer_email || "Super Bajaar Customer"}</span><strong>{loyaltyCustomerData.account?.card_number || "CARD AFTER FIRST DELIVERY"}</strong></div>
            </div>
            <div className="storefront-loyalty-summary">
              <article><Coins size={22}/><small>Available Super Coins</small><strong>{Number(loyaltyCustomerData.available_coins || 0).toLocaleString("en-IN")}</strong><span>Only unexpired coins are available to use.</span></article>
              <article><CalendarClock size={22}/><small>Expiry</small><strong>Never expires</strong><span>Your Super Coins stay in your account. The oldest coins are used first.</span></article>
            </div>
            {!loyaltyCustomerData.account && <p className="storefront-account-note" role="status">{loyaltyCustomerData.message}</p>}
            {loyaltyCustomerData.account && <div className="storefront-account-summary storefront-loyalty-activity"><h3>Recent loyalty activity</h3>{loyaltyCustomerData.items.length ? loyaltyCustomerData.items.map(item=><div key={item.id}><small>{item.transaction_type.toUpperCase()} · {new Date(item.created_at).toLocaleString()}</small><strong>{item.coins} Super Coins{item.expires_at && new Date(item.expires_at).getFullYear() < 2100 ? " · Expires " + new Date(item.expires_at).toLocaleDateString() : ""}</strong><span>{item.description || item.order_reference || "Loyalty activity"}</span></div>) : <p>No loyalty transactions yet.</p>}</div>}
            </>}
            <div className="storefront-loyalty-note"><strong>How it works</strong><p>Coins are credited only after an order is marked delivered. Product-specific earning rules override category rules, which override the default. Coins never expire.</p><p>1 Super Coin = ₹{Number(loyaltyCustomerData?.coin_value_in_rupees ?? 1)}. Redeem your available coins at checkout (at least ₹1 of each order is paid online) when the programme accounting mapping is active. The server rechecks your balance and payable amount before applying a redemption.</p></div>
            {error && <p className="storefront-account-note" role="alert">{error}</p>}
          </div>}
          {accountSection==="referrals" && <div className="storefront-account-section storefront-account-section--referrals">
      <span className="storefront-kicker">SHARE THE SUPER BAJAAR LOVE</span><h2>Refer &amp; Earn</h2>
      <p>Share your unique referral code with friends. Their sign-up will be linked to your account so referrals can be tracked.</p>
      {referralBusy && <p className="storefront-account-note">Loading referral details…</p>}
      {referralData && <>
        <div className="storefront-loyalty-card"><div className="storefront-loyalty-card-top"><img className="storefront-loyalty-mark" src="/superbajaar.svg" alt="" /><span>SUPER BAJAAR<br/><strong>REFERRAL CODE</strong></span><UserRound size={28}/></div><div className="storefront-loyalty-card-bottom"><span>Your unique code</span><strong>{referralData.referral_code}</strong></div></div>
        <label className="storefront-referral-link">Referral link<input readOnly value={window.location.origin + (referralData.referral_link_path || ("/customer/register?ref=" + referralData.referral_code))}/></label>
        <button type="button" className="storefront-primary" onClick={async()=>{const link=window.location.origin+(referralData.referral_link_path||("/customer/register?ref="+referralData.referral_code));try{await navigator.clipboard.writeText(link);setNotice("Referral link copied.");}catch{setNotice("Your referral code is "+referralData.referral_code+". Copy it to share.");}}}>Copy referral link</button>
        <div className="storefront-account-summary storefront-referral-summary"><div><small>Tracked referrals</small><strong>{(referralData.items||[]).length}</strong></div><div><small>Reward status</small><strong>100 coins each after first delivery</strong></div></div>
        <p className="storefront-account-note">{referralData.reward_status || "Both the referrer and new customer receive 100 Super Coins each after the referred customer’s first order is delivered."}</p>
        {(referralData.items||[]).length ? <div className="storefront-account-summary"><h3>Your referrals</h3>{referralData.items.map(item=><div key={item.id}><small>{new Date(item.created_at).toLocaleDateString()} · {String(item.status||"tracked").replaceAll("_"," ")}</small><strong>{item.referred_customer}</strong><span>{item.status === "rewarded" ? "100 Super Coins awarded to each customer" : "100 Super Coins each after first delivery"}</span></div>)}</div> : <p className="storefront-account-empty">No referrals yet. Share your code to start building your referral list.</p>}
      </>}
      {error && <p className="storefront-account-note" role="alert">{error}</p>}
    </div>}
    {accountSection==="orders" && <div className="storefront-account-section"><h2>My Orders</h2><p>Your purchases, payment status and delivery updates.</p>
            {ordersBusy && <p className="storefront-account-note" role="status">Loading…</p>}
            {error && <p className="storefront-account-note" role="alert">{error}</p>}
            {!myOrderDetail && myOrders && (myOrders.length ? <div className="storefront-order-list">{myOrders.map(item => <button type="button" className="storefront-order-card" key={item.order_number} onClick={() => openMyOrder(item.order_number)}><div><small>{new Date(item.created_at).toLocaleDateString("en-IN")}</small><strong>{item.order_number}</strong></div><div><small>Items</small><strong>{item.line_count}</strong></div><div><small>Total</small><strong>{money(item.total)}</strong></div><div><small>Status</small><strong className={"storefront-status-pill status-" + item.status}>{String(item.status).replaceAll("_"," ")}</strong></div></button>)}</div> : <div className="storefront-account-empty-state"><span><Package size={40} strokeWidth={1.5} /></span><h3>No orders yet</h3><p>When you place an order it will appear here.</p><button type="button" className="storefront-primary" onClick={openShopHome}>Start shopping</button></div>)}
            {myOrderDetail && <div className="storefront-order-detail">
              <button type="button" className="storefront-inline-link" onClick={() => setMyOrderDetail(null)}>← All orders</button>
              <h3>{myOrderDetail.order.order_number}</h3>
              <p>Placed {new Date(myOrderDetail.order.created_at).toLocaleString("en-IN")} · Status: <strong>{String(myOrderDetail.order.status).replaceAll("_"," ")}</strong></p>
              <div className="storefront-order-lines">{myOrderDetail.lines.map(line => <div key={line.id}><span>{line.product_name} <small>× {line.quantity}</small></span><strong>{money(line.line_total)}</strong></div>)}<div className="storefront-order-total"><span>Total</span><strong>{money(myOrderDetail.order.total)}</strong></div></div>
              <h4>Payment</h4>{myOrderDetail.payments.length ? myOrderDetail.payments.map((pay, i) => <p key={i}>{money(pay.amount)} · {String(pay.status).replaceAll("_"," ")}</p>) : <p>No payment recorded yet.</p>}
              <h4>Delivery</h4>{myOrderDetail.shipments.length ? myOrderDetail.shipments.map(sh => <p key={sh.shipment_reference}>{sh.shipment_reference} · {String(sh.status).replaceAll("_"," ")}{sh.tracking_reference ? " · Tracking: " + sh.tracking_reference : ""}</p>) : <p>Not dispatched yet. We will update this page when it ships.</p>}
              <p><button type="button" className="storefront-inline-link" onClick={() => { setAccountSection("tickets"); setTicketDraft({ category: "", description: "Order " + myOrderDetail.order.order_number + ": " }); setTicketFiles([]); }}>Need help with this order?</button></p>
            </div>}
          </div>}
          {accountSection==="tickets" && <div className="storefront-account-section">
            <h2>My Support Tickets</h2><p>Your tickets are tied to your signed-in account. No email or phone lookup is used to grant access.</p>
            <form className="storefront-account-form storefront-ticket-form" onSubmit={submitSupportTicket}>
              <h3>Raise a ticket</h3>
              <label>Subject
                <select required value={ticketDraft.category} onChange={event=>setTicketDraft(old=>({...old,category:event.target.value}))}>
                  <option value="" disabled>Select a subject</option>
                  {SUPPORT_SUBJECTS.map(([key,text])=><option key={key} value={key}>{text}</option>)}
                </select>
              </label>
              <label>How can we help?<textarea required rows="4" maxLength="5000" placeholder="Tell us what happened. Include your order number if it relates to an order." value={ticketDraft.description} onChange={event=>setTicketDraft(old=>({...old,description:event.target.value}))}/></label>
              <div className="storefront-ticket-attach">
                <span className="storefront-ticket-attach-title">Attachments (optional)</span>
                <label className={"storefront-ticket-attach-button" + (ticketFiles.length >= TICKET_MAX_FILES ? " is-disabled" : "")}>
                  <Paperclip size={16} aria-hidden="true"/>Add photo or PDF
                  <input className="storefront-file-input" type="file" multiple accept={TICKET_FILE_TYPES.join(",")} disabled={ticketBusy || ticketFiles.length >= TICKET_MAX_FILES} onChange={event=>pickTicketFiles(event, ticketFiles, setTicketFiles)}/>
                </label>
                <small>Up to {TICKET_MAX_FILES} files. JPG, PNG, WebP or PDF, 5 MB each.</small>
                {ticketFileProblem && <small className="storefront-ticket-attach-problem" role="alert">{ticketFileProblem}</small>}
                {ticketFiles.length > 0 && <ul className="storefront-ticket-files">{ticketFiles.map(file=><li key={file.name + file.size}><FileText size={15} aria-hidden="true"/><span>{file.name}</span><small>{formatFileSize(file.size)}</small><button type="button" aria-label={"Remove " + file.name} onClick={()=>setTicketFiles(old=>old.filter(item=>item!==file))}><X size={14} aria-hidden="true"/></button></li>)}</ul>}
              </div>
              <button className="storefront-primary" type="submit" disabled={ticketBusy}>{ticketBusy?"Submitting…":"Create support ticket"}</button>
            </form>
            {ticketCreated && <div className="storefront-account-summary" role="status"><div><small>Ticket created</small><strong>{ticketCreated.case_number}</strong></div><p>{ticketUploadIssue ? "" : "Your ticket is now linked to this signed-in account."}</p>{ticketUploadIssue && <p className="storefront-ticket-attach-problem" role="alert">{ticketUploadIssue}</p>}</div>}
            <div className="storefront-account-form">
              <h3>Your tickets</h3>
              {myTickets.length ? myTickets.map(ticket => <button className="storefront-account-summary" type="button" key={ticket.case_number} onClick={() => openCustomerTicket(ticket.case_number)}><div><small>{ticket.case_number}</small><strong>{ticket.subject}</strong></div><div><small>Status</small><strong>{String(ticket.status).replaceAll("_"," ")}</strong></div><div><small>Priority</small><strong>{ticket.priority}</strong></div></button>) : <p>No support tickets yet.</p>}
            </div>
            <form className="storefront-account-form" onSubmit={trackSupportTicket}>
              <h3>Open a ticket by reference</h3>
              <label>Ticket reference<input required placeholder="SUP-XXXXXXXXXXXX" value={ticketLookup.caseNumber} onChange={event=>setTicketLookup({caseNumber:event.target.value.toUpperCase()})}/></label>
              <button className="storefront-primary" type="submit" disabled={ticketBusy || !ticketLookup.caseNumber.trim()}>{ticketBusy?"Loading…":"Open ticket"}</button>
            </form>
            {ticketTracked?.ticket && <div className="storefront-account-summary" role="region" aria-label="Support ticket details">
              <div><small>Reference</small><strong>{ticketTracked.ticket.case_number}</strong></div>
              <div><small>Subject</small><strong>{ticketTracked.ticket.subject}</strong></div>
              <div><small>Status</small><strong>{String(ticketTracked.ticket.status).replaceAll("_"," ")}</strong></div>
              <div><small>Last updated</small><strong>{ticketTracked.ticket.updated_at ? new Date(ticketTracked.ticket.updated_at).toLocaleString() : "Not available"}</strong></div>
              <div><small>Resolution</small><strong>{ticketTracked.ticket.resolution || "Awaiting support response"}</strong></div>
              <div>{(ticketTracked.messages || []).map(message => <article key={message.id}><small>{message.author_type === "customer" ? "You" : "Super Bajaar support"} · {new Date(message.created_at).toLocaleString()}</small><p>{message.body}</p>{(ticketTracked.attachments || []).filter(item => item.message_id === message.id).map(item => <button type="button" className="storefront-ticket-file-link" key={item.id} onClick={() => downloadTicketAttachment(ticketTracked.ticket.case_number, item)}><Paperclip size={14} aria-hidden="true"/>{item.original_filename} <small>{formatFileSize(item.file_size_bytes)}</small></button>)}</article>)}
                {(ticketTracked.attachments || []).some(item => !item.message_id) && <article><small>Other attachments</small>{(ticketTracked.attachments || []).filter(item => !item.message_id).map(item => <button type="button" className="storefront-ticket-file-link" key={item.id} onClick={() => downloadTicketAttachment(ticketTracked.ticket.case_number, item)}><Paperclip size={14} aria-hidden="true"/>{item.original_filename} <small>{formatFileSize(item.file_size_bytes)}</small></button>)}</article>}</div>
              {![ "resolved", "closed" ].includes(ticketTracked.ticket.status) && <form onSubmit={replyToCustomerTicket}><label>Reply to support<textarea required rows="3" maxLength="10000" value={ticketReply} onChange={event=>setTicketReply(event.target.value)}/></label><div className="storefront-ticket-attach"><label className={"storefront-ticket-attach-button" + (replyFiles.length >= TICKET_MAX_FILES ? " is-disabled" : "")}><Paperclip size={16} aria-hidden="true"/>Add photo or PDF<input className="storefront-file-input" type="file" multiple accept={TICKET_FILE_TYPES.join(",")} disabled={ticketBusy || replyFiles.length >= TICKET_MAX_FILES} onChange={event=>pickTicketFiles(event, replyFiles, setReplyFiles)}/></label>{ticketFileProblem && <small className="storefront-ticket-attach-problem" role="alert">{ticketFileProblem}</small>}{replyFiles.length > 0 && <ul className="storefront-ticket-files">{replyFiles.map(file=><li key={file.name + file.size}><FileText size={15} aria-hidden="true"/><span>{file.name}</span><small>{formatFileSize(file.size)}</small><button type="button" aria-label={"Remove " + file.name} onClick={()=>setReplyFiles(old=>old.filter(item=>item!==file))}><X size={14} aria-hidden="true"/></button></li>)}</ul>}</div><button className="storefront-primary" type="submit" disabled={ticketBusy || !ticketReply.trim()}>{ticketBusy?"Sending…":"Send reply"}</button></form>}
            </div>}
            {error && <p className="storefront-account-note" role="alert">{error}</p>}
          </div>}
          {accountSection==="addresses" && <div className="storefront-account-section"><div className="storefront-account-section-heading"><div><h2>Saved addresses</h2><p>Your delivery locations are synced to your Super Bajaar account.</p></div><button type="button" className="storefront-primary" onClick={()=>openAddressEditor(null)}>Add new address</button></div><div className="storefront-saved-address-grid">{savedAddresses.map(address=><article className={"storefront-saved-address "+(address.is_default?"is-default":"")} key={address.id}><div className="storefront-saved-address-top"><strong>{address.label}</strong>{address.is_default&&<span>Default</span>}</div><b>{address.recipient_name}</b><p>{address.address}{address.landmark?", "+address.landmark:""}<br/>PIN {address.pin_code} · {address.phone}</p><div className="storefront-saved-address-actions"><button type="button" onClick={()=>openAddressEditor(address)}>Edit</button>{!address.is_default&&<button type="button" disabled={addressBusy} onClick={()=>setDefaultCustomerAddress(address)}>Set as default</button>}<button type="button" disabled={addressBusy} onClick={()=>deleteCustomerAddress(address)}>Delete address</button></div></article>)}</div>{!savedAddresses.length&&<p className="storefront-account-empty">No saved addresses yet. Add one to speed up checkout.</p>}{addressEditorOpen&&<form className="storefront-address-editor" onSubmit={saveCustomerAddress}><h3>{addressDraft.id?"Edit address":"Add new address"}</h3><label>Address type<select value={addressDraft.label} onChange={e=>setAddressDraft(v=>({...v,label:e.target.value}))}><option>Home</option><option>Work</option><option>Other</option></select></label><label>Recipient name<input required minLength="2" maxLength="200" autoComplete="name" value={addressDraft.recipient_name} onChange={e=>setAddressDraft(v=>({...v,recipient_name:e.target.value}))}/></label><label>Contact phone<input required minLength="7" maxLength="20" autoComplete="tel" value={addressDraft.phone} onChange={e=>setAddressDraft(v=>({...v,phone:e.target.value}))}/></label><label className="storefront-address-editor-wide">Full address<textarea required minLength="5" maxLength="1000" autoComplete="street-address" rows="3" value={addressDraft.address} onChange={e=>setAddressDraft(v=>({...v,address:e.target.value}))}/></label><label>Landmark (optional)<input maxLength="200" value={addressDraft.landmark||""} onChange={e=>setAddressDraft(v=>({...v,landmark:e.target.value}))}/></label><label>Delivery PIN<input required inputMode="numeric" pattern="[1-9][0-9]{5}" maxLength="6" autoComplete="postal-code" value={addressDraft.pin_code} onChange={e=>setAddressDraft(v=>({...v,pin_code:e.target.value.replace(/\\D/g,"").slice(0,6)}))}/></label><label className="storefront-address-default"><input type="checkbox" checked={Boolean(addressDraft.is_default)} onChange={e=>setAddressDraft(v=>({...v,is_default:e.target.checked}))}/> Set as default address</label><div className="storefront-address-editor-actions"><button className="storefront-primary" type="submit" disabled={addressBusy}>{addressBusy?"Saving…":"Save address"}</button><button type="button" onClick={()=>setAddressEditorOpen(false)}>Cancel</button></div></form>}</div>}
          {accountSection==="privacy" && <div className="storefront-account-section">
            <span className="storefront-kicker">YOUR PRIVACY</span>
            <h2>Analytics preferences</h2>
            <p>Choose whether Super Bajaar may use Google Analytics to understand storefront usage and improve your shopping experience. This setting does not affect essential account, cart or checkout functions.</p>
            <div className="storefront-security-list">
              <div>
                <span><strong>Google Analytics</strong><small>{analyticsEnabled ? "Analytics is enabled on this browser." : "Analytics is disabled on this browser."}</small></span>
                <label className="storefront-analytics-toggle">
                  <input type="checkbox" role="switch" checked={analyticsEnabled} onChange={event => {
                    const enabled = event.target.checked;
                    setAnalyticsEnabled(enabled);
                    setAnalyticsConsent(enabled);
                    setNotice(enabled ? "Analytics enabled. Thank you for helping us improve." : "Analytics disabled. No further analytics events will be sent.");
                  }} />
                  <span>{analyticsEnabled ? "On" : "Off"}</span>
                </label>
              </div>
            </div>
            <p className="storefront-account-note">You can change this choice anytime in My Account → Privacy &amp; Analytics. If you turn analytics off, further GA4 events are blocked and analytics consent is withdrawn for this browser.</p>
          </div>}
          {accountSection==="security" && <div className="storefront-account-section"><h2>Security</h2><p>Protect your account and keep your contact details verified.</p><div className="storefront-security-list"><div><span><strong>Change password</strong><small>Change the password used to sign in.</small></span><button type="button" disabled>Not available yet</button></div><div><span><strong>Update mobile number</strong><small>Requires OTP verification of the new number.</small></span><button type="button" disabled>OTP setup required</button></div><div><span><strong>Update email address</strong><small>Requires verification of the new email address.</small></span><button type="button" disabled>Email verification required</button></div><div><span><strong>Login sessions</strong><small>Review and end active customer sessions.</small></span><button type="button" disabled>Customer sign-in required</button></div></div><p className="storefront-account-note">These actions are not enabled because customer authentication and verification are not implemented yet. We will not simulate security changes in the browser.</p></div>}
          {notice && <p className="storefront-order-success" role="status">{notice}</p>}
        </div>
      </div>
    </section>}
    {isInfoPage && <section className="storefront-info-page"><div className="storefront-category-breadcrumb"><button type="button" onClick={openShopHome}>Home</button><span>/</span><span>Information</span></div>
      {infoSlug === "seller-registration" && <><span className="storefront-kicker">GROW WITH SUPER BAJAAR</span><h1>Partner with Us</h1><p>Bring your products, brand or delivery expertise to Super Bajaar. We welcome enquiries from sellers, brands, suppliers and logistics partners. Every enquiry is reviewed before onboarding; submitting this form does not guarantee acceptance.</p><div className="storefront-partner-cards"><article><strong>Sell on Super Bajaar</strong><p>Introduce eligible products to everyday shoppers.</p></article><article><strong>Brand &amp; supplier partnerships</strong><p>Discuss product range, supply capacity and commercial terms.</p></article><article><strong>Delivery &amp; logistics</strong><p>Explore service coverage and fulfilment partnerships.</p></article></div><form className="storefront-partner-form" onSubmit={submitPartnerEnquiry}><h2>Tell us about your business</h2><label>Your name<input name="name" required maxLength="120" /></label><label>Business / brand name<input name="business" required maxLength="160" /></label><label>Phone number<input name="phone" required minLength="7" maxLength="20" /></label><label>Email address<input name="email" type="email" required maxLength="254" /></label><label>Partnership type<select name="partnerType" required><option value="">Choose a partnership</option><option>Seller</option><option>Brand</option><option>Supplier</option><option>Delivery / logistics</option><option>Other</option></select></label><label>How would you like to partner?<textarea name="message" rows="4" required maxLength="3000" /></label><button className="storefront-primary" type="submit" disabled={partnerBusy}>{partnerBusy ? "Submitting…" : "Send partnership enquiry"}</button>{partnerResult && <p className={partnerResult.error ? "storefront-alert" : "storefront-order-success"} role="status">{partnerResult.error || partnerResult.message}</p>}<p className="storefront-info-note">Your enquiry is submitted to Super Bajaar for review. Onboarding is subject to approval.</p></form></>}
      {infoSlug === "loyalty-programme" && <LoyaltyProgrammePage rate={loyaltyDefaultRate} onShop={openShopHome} onAccount={openAccount} />}
      {infoSlug === "super-coins" && <><span className="storefront-kicker">REWARDS WALLET</span><h1>Super Coins</h1><p>Super Coins are earned on eligible orders after delivery is confirmed. The default rate is 1 coin per ₹100 eligible spend, with optional product and category overrides. Super Coins never expire.</p><p>Use My Account → Loyalty Card &amp; Coins to verify an order and view your available balance and recent activity.</p><p className="storefront-info-note">Checkout redemption is not enabled yet because the rupee value per coin has not been defined.</p></>}
      {infoSlug === "feedback" && <><span className="storefront-kicker">HELP US IMPROVE</span><h1>Feedback</h1><p>We welcome suggestions about your shopping experience, product selection, website usability and customer support.</p><div className="storefront-contact-grid"><a href="mailto:kpmcenterprise@gmail.com?subject=Super%20Bajaar%20Feedback"><strong>Send feedback by email</strong><span>kpmcenterprise@gmail.com</span></a><a href="https://wa.me/917644841104?text=Super%20Bajaar%20feedback" target="_blank" rel="noreferrer"><strong>Share on WhatsApp</strong><span>Message customer support</span></a></div></>}
      {LEGAL_SLUGS.includes(infoSlug) && <LegalPage slug={infoSlug} openInfoPage={openInfoPage} />}
      {infoSlug === "about-us" && <><span className="storefront-kicker">OUR STORY</span><h1>About Super Bajaar</h1><p><strong>Super Bajaar</strong> is a retail brand owned and operated by <strong>KPMC Enterprises</strong>, a proprietorship concern based in Daltonganj, Palamu, Jharkhand. Our aim is to make everyday shopping simpler by bringing daily essentials and multiple product categories together in one convenient place.</p><h2>Our brand</h2><p>Super Bajaar is the customer-facing shopping brand. KPMC Enterprises owns the brand and is responsible for its business operations. Product availability, prices, delivery options and applicable terms are displayed through the storefront and at checkout.</p><h2>Contact</h2><p>For customer assistance, email <a href="mailto:kpmcenterprise@gmail.com">kpmcenterprise@gmail.com</a> or call <a href="tel:+917644841104">+91 76448 41104</a>.</p></>}
      {infoSlug === "contact-us" && <><span className="storefront-kicker">WE ARE HERE TO HELP</span><h1>Customer Support</h1><p>Choose the channel that works best for you. For order-related issues, please include your order number when contacting us.</p><div className="storefront-contact-grid"><a href="tel:+917644841104"><strong>Call us</strong><span>+91 76448 41104</span></a><a href="https://wa.me/917644841104" target="_blank" rel="noreferrer"><strong>WhatsApp</strong><span>Chat with customer support</span></a><a href="mailto:kpmcenterprise@gmail.com"><strong>Email support</strong><span>kpmcenterprise@gmail.com</span></a><button type="button" onClick={openTicketCenter}><strong>Raise a ticket</strong><span>Open customer support in My Account</span></button></div></>}
      {infoSlug === "faq" && <><span className="storefront-kicker">QUICK ANSWERS</span><h1>Frequently Asked Questions</h1><h2>How long does delivery take?</h2><p>Standard delivery is estimated at 1–5 days. Eligible express orders may take 30 minutes to 1 day and cost ₹39 per order.</p><h2>How do I contact support?</h2><p>Call or WhatsApp +91 76448 41104 or email kpmcenterprise@gmail.com.</p><h2>How long do refunds take?</h2><p>Approved refunds for genuine and verified returns are processed within 2 working days after verification and approval. Bank processing may take additional time.</p><h2>How can I raise a grievance?</h2><p>Contact grievance officer NK Singh at +91 76448 41104 or nibandhansingh1997@gmail.com.</p><h2>Where can I check whether delivery is available?</h2><p>Use the delivery PIN selector on the storefront. Availability depends on the configured delivery locations and eligible products.</p></>}
      {!(LEGAL_SLUGS.includes(infoSlug)||["about-us","contact-us","faq","feedback","seller-registration","loyalty-programme","super-coins"].includes(infoSlug)) && <><h1>Page not found</h1><p>This information page does not exist.</p><button className="storefront-primary" type="button" onClick={openShopHome}>Return to shopping</button></>}
    </section>}
    {isProductPage && !selectedProduct && <main className="storefront-product-page"><button type="button" className="storefront-product-back" onClick={openShopHome}>← Continue shopping</button><section className="storefront-product-page-details" role="status"><h1>{loading ? "Loading product…" : "Product unavailable"}</h1><p>{loading ? "Please wait while product details load." : "This product may be unavailable or no longer active."}</p></section></main>}
    {isProductPage && selectedProduct && (() => { const product = productById.get(Number(selectedProduct.product_id)); const productVariants = variants.filter(item => Number(item.product_id) === Number(selectedProduct.product_id) && item.is_active !== false); const saved = productVariants.some(item => wishlist.some(id => Number(id) === Number(item.id))); const categoryName = product?.category_name || product?.category || orderedCategories.find(c => String(c.id) === String(product?.category_id))?.name; const tile = categoryArt[categoryName] || art[0]; const optionGroups = variantAttributeGroups(productVariants, attributeDefinitions); const variantLabel = item => { const values = Object.entries(item.attributes || {}).map(([key, value]) => variantValueLabel(key, value, attributeDefinitions)); return values.length ? values.join(" / ") : "Standard"; }; return <main className="storefront-product-page"><button type="button" className="storefront-product-back" onClick={openShopHome}>← Continue shopping</button><div className="storefront-product-page-layout"><ProductGallery images={selectedProduct.images} fallbackUrl={selectedProduct.image_url} alt={product?.name || selectedProduct.product_name || "Product"} placeholder={<span>{(() => { const I = catIcons[tile.icon]; return I ? <I size={48} strokeWidth={1.5} aria-hidden="true" /> : null; })()}</span>} /><section className="storefront-product-page-details"><span className="storefront-kicker">PRODUCT DETAILS</span><h1>{product?.name || selectedProduct.product_name || "Product"}</h1><p className="storefront-modal-brand">{product?.brand || "Super Bajaar"}{categoryName ? " · " + categoryName : ""}</p>{productVariants.length > 1 && (optionGroups.length ? <VariantOptionPicker groups={optionGroups} variants={productVariants} selected={selectedProduct} productName={product?.name || selectedProduct.product_name || ""} onSelect={chosen => { rememberViewed(chosen); setSelectedProduct(chosen); }} /> : <label className="storefront-variant-select">Choose variant<select aria-label={"Choose variant for " + (product?.name || selectedProduct.product_name)} value={String(selectedProduct.id)} onChange={event => { const chosen = productVariants.find(item => String(item.id) === event.target.value); if (chosen) { rememberViewed(chosen); setSelectedProduct(chosen); } }}>{productVariants.map(item => <option key={item.id} value={item.id}>{variantLabel(item)} · {money(item.selling_price)}</option>)}</select></label>)}<label className="storefront-product-page-quantity">Quantity<input type="number" inputMode="numeric" min="1" max="100000" step="1" value={productPageQuantity} onChange={event => { const value = event.target.value; setProductPageQuantity(value === "" ? "" : Math.min(100000, Math.max(1, Math.floor(Number(value) || 1)))); }} onBlur={() => setProductPageQuantity(Math.min(100000, Math.max(1, Math.floor(Number(productPageQuantity) || 1))))} /></label><p className="storefront-modal-sku">SKU: {selectedProduct.sku || "Not available"}</p><strong className="storefront-modal-price">{money(selectedProduct.selling_price)}</strong>{selectedProduct.lowest_price_30d != null && <small className="storefront-lowest-price">Lowest price in last 30 days: <strong>{money(Math.min(Number(selectedProduct.lowest_price_30d), Number(selectedProduct.selling_price)))}</strong></small>}{coinsFor(product, Number(selectedProduct.selling_price || 0) * Number(productPageQuantity || 1)) > 0 && <p className="storefront-product-coins storefront-product-coins-page"><Coins size={15} /> Earn {coinsFor(product, Number(selectedProduct.selling_price || 0) * Number(productPageQuantity || 1))} Super Coins on this purchase, credited after delivery</p>}<div className="storefront-modal-actions"><button type="button" className="storefront-primary" disabled={isProductUnavailable(selectedProduct.product_id)} onClick={() => { addToCart(selectedProduct, productPageQuantity); setProductPageQuantity(1); }}><ShoppingBag size={17}/> {isProductUnavailable(selectedProduct.product_id) ? (regionUnserved ? "Not available in your region" : "Not available in your area") : "Add to basket"}</button><button type="button" className="storefront-modal-wishlist" onClick={() => setWishlist(old => saved ? old.filter(id => !productVariants.some(item => Number(item.id) === Number(id))) : [...new Set([...old, ...productVariants.map(item => Number(item.id))])])}><Heart size={17} fill={saved ? "currentColor" : "none"} />{saved ? "Remove from wishlist" : "Save to wishlist"}</button></div></section></div><ProductDescription text={product?.description} /><RelatedProducts current={selectedProduct} variants={variants} productById={productById} onOpen={openProductPage} money={money} /><ProductReviews productId={selectedProduct.product_id} customerToken={customerToken} request={customerRequest} onSignIn={() => openCustomerAuth("login", window.location.pathname)} onChanged={() => setReviewsVersion(v => v + 1)} /></main>; })()}
    {isCategoryPage && !isCategoryListingPage && !isWishlistPage && !isAccountPage && !isCheckoutPage && !isInfoPage && !isSearchPage && !isProductPage && <section className="storefront-category-landing">
      <div className="storefront-category-breadcrumb"><a href="/" onClick={event => { event.preventDefault(); openShopHome(); }}>Home</a><span>/</span><span>{routeCategoryName}</span></div>
      {(() => { const heroImages = categoryHeroImages[Number(categories.find(c => c.name === routeCategoryName)?.id)] || []; return heroImages.length ? <CategoryHeroSlider key={routeCategoryName} images={heroImages} title={routeCategoryName} /> : null; })()}
      {routeCategoryName === "Insurance" && <section className="storefront-insurance-section">
        <div className="storefront-section-heading"><div><span className="storefront-kicker">PERSONALISED GUIDANCE</span><h2>Choose an insurance consultation</h2><p>Each consultation costs ₹100. Compare your options with our team.</p></div></div>
        <div className="storefront-insurance-options">
          {[
            {name:"Life Insurance",icon:"Users",description:"Discuss family protection, life cover and policy choices."},
            {name:"Health Insurance",icon:"HeartPulse",description:"Discuss medical cover, hospitalisation benefits and policy choices."},
            {name:"Motor Insurance",icon:"Car",description:"Discuss vehicle cover, third-party and comprehensive options."},
          ].map(service => <article className="storefront-insurance-card" key={service.name}>
            <span className="storefront-insurance-icon" aria-hidden="true">{(() => { const I = catIcons[service.icon]; return I ? <I size={28} strokeWidth={1.6} /> : null; })()}</span><h3>{service.name}</h3><p>{service.description}</p><strong>₹100 <small>/ consultation</small></strong>
            <button type="button" className="storefront-primary" onClick={() => { const select = document.getElementById("insuranceType"); if (select) select.value = service.name; document.getElementById("insurance-request")?.scrollIntoView({behavior:"smooth",block:"start"}); }}>Request consultation</button>
            <button type="button" className="storefront-insurance-pay" disabled title="Online payment is not enabled in the current checkout">Pay ₹100 online · Coming soon</button>
          </article>)}
        </div>
        <form id="insurance-request" className="storefront-insurance-form" onSubmit={submitInsuranceRequest}>
          <div><span className="storefront-kicker">WE’LL GET IN TOUCH</span><h2>Request a consultation</h2><p>Submit your details and our team will contact you. This request does not collect payment.</p></div>
          <label>Consultation type<select id="insuranceType" name="insuranceType" required defaultValue="Life Insurance"><option>Life Insurance</option><option>Health Insurance</option><option>Motor Insurance</option></select></label>
          <div className="storefront-insurance-form-grid"><label>Preferred contact time<select name="contactTime" defaultValue="Any time"><option>Any time</option><option>Morning</option><option>Afternoon</option><option>Evening</option></select></label></div>
          <p className="storefront-account-note">Consultation requests are attached to your signed-in Super Bajaar account. Sign in before submitting.</p>
          <label>What would you like help with? <textarea name="message" rows="3" placeholder="Optional details about your insurance needs" /></label>
          <button className="storefront-primary" type="submit" disabled={ticketBusy}>{ticketBusy ? "Submitting request…" : "Submit consultation request"}</button>
          {ticketCreated && <p className="storefront-insurance-success" role="status">Request received. Reference: {ticketCreated.case_number}</p>}
          {notice && <p className="storefront-insurance-success" role="status">{notice}</p>}
          {error && <p className="storefront-alert" role="alert">{error}</p>}
        </form>
      </section>}
      {routeCategoryName !== "Insurance" && categorySubcategories.length > 0 && <section className="storefront-subcategory-section"><div className="storefront-section-heading"><div><span className="storefront-kicker">SHOP YOUR WAY</span><h2>Explore subcategories</h2></div></div><div className="storefront-subcategory-grid">{categorySubcategories.map((category, index) => { const tile = categoryArt[category.name] || art[index % art.length]; return <button key={category.id} type="button" className="storefront-subcategory-card" onClick={() => openCategory(category)}><span className={"storefront-subcategory-icon tone-" + tile.tone}>{(() => { const I = catIcons[tile.icon]; return I ? <I size={28} strokeWidth={1.6} aria-hidden="true" /> : null; })()}</span><strong>{category.name}</strong><span>Explore collection →</span></button>; })}</div></section>}
      {routeCategoryName !== "Insurance" && subcategoryProductRows.map(({ category, items }) => <section className="storefront-subcategory-products" key={category.id}>
        <div className="storefront-category-featured-heading"><div><span className="storefront-kicker">SHOP BY SUBCATEGORY</span><h2>{category.name}</h2><p>Explore products in {category.name}.</p></div><button type="button" onClick={() => openCategory(category)}>View all <span>→</span></button></div>
        <div className="storefront-subcategory-products-viewport">
          <div className="storefront-carousel-track storefront-subcategory-product-track" tabIndex={0} aria-label={category.name + " products"}>{items.map(renderProductCard)}</div>
        </div>
      </section>)}
      {routeCategoryName !== "Insurance" && <><div className="storefront-category-featured-heading"><div><span className="storefront-kicker">HANDPICKED FOR YOU</span><h2>Featured {routeCategoryName}</h2><p>Customer favourites in this department.</p></div><button type="button" onClick={openCategoryListing}>View all <span>→</span></button></div>
      {loading ? <p className="storefront-empty">Loading live products…</p> : visibleVariants.length ? <div className="storefront-category-featured-track">{displayedVariants.slice(0, 8).map(renderProductCard)}</div> : <p className="storefront-empty">No active products are available in this category yet.</p>}
      {bestSellers.length > 0 && <div className="storefront-category-featured-heading"><div><span className="storefront-kicker">CUSTOMER FAVOURITES</span><h2>Popular in {routeCategoryName}</h2></div><button type="button" onClick={openCategoryListing}>View all <span>→</span></button></div>}
      {bestSellers.length > 0 && <div className="storefront-category-featured-track">{bestSellers.slice(0, 8).map(renderProductCard)}</div>}</>}
    </section>}
    {(isCategoryListingPage || isDealsPage || isWishlistPage || isSearchPage) && !isAccountPage && !isCheckoutPage && !isInfoPage && !isProductPage && <section className={"storefront-products " + (isCategoryPage ? "storefront-category-page" : "") + (isWishlistPage ? " storefront-wishlist-page" : "")} id="products">
      <div className="storefront-category-breadcrumb"><a href="/" onClick={event => {event.preventDefault(); openShopHome();}}>Home</a><span>/</span><span>{isSearchPage ? "Search" : isWishlistPage ? "My Wishlist" : isDealsPage ? "Deals" : routeCategoryName || "Shop products"}</span></div><div className="storefront-section-heading"><div><span className="storefront-kicker">{isSearchPage ? "SEARCH RESULTS" : isWishlistPage ? "YOUR SAVED FAVOURITES" : isDealsPage ? "SPECIAL OFFERS" : "SHOP BY DEPARTMENT"}</span><h1>{isSearchPage ? (search.trim() ? "Results for “" + search.trim() + "”" : "Search products") : isWishlistPage ? "My Wishlist" : isDealsPage ? "Deals & Offers" : routeCategoryName}</h1>{isWishlistPage && <p className="storefront-category-description">Your saved products, ready to revisit or add to your basket.</p>}{isDealsPage && <p className="storefront-category-description">Discover current discounted items and customer favourites.</p>}</div><span className="storefront-heading-note">{(isSearchPage || isWishlistPage ? displayedVariants : isDealsPage ? dealVariants : visibleVariants).length} {isWishlistPage ? "saved products" : isSearchPage ? "products found" : "products and variants"}</span></div>
      {!isSearchPage && <label className="storefront-search">Search products or SKU<input value={search} onChange={e => setSearch(e.target.value)} placeholder="Try a product name or SKU" /></label>}
      {error && <p className="storefront-alert" role="alert">{error}</p>}
      {loading ? <p className="storefront-empty">Loading live products…</p> : (isDealsPage ? dealVariants : displayedVariants).length ? <div className="storefront-product-grid">{(isDealsPage ? dealVariants : displayedVariants).map(renderProductCard)}</div> : isWishlistPage ? <div className="storefront-wishlist-empty"><span aria-hidden="true">♡</span><h2>Your wishlist is waiting</h2><p>Tap the heart on any product to save it here for later.</p><button type="button" className="storefront-primary" onClick={openShopHome}>Explore products</button></div> : <p className="storefront-empty">{error ? "The live catalogue could not be loaded." : isSearchPage ? (search.trim() ? "No products found for “" + search.trim() + "”. Try a different spelling, a simpler word, or browse the categories." : "Type a product name in the search bar to get started.") : isDealsPage ? "No discounted products or featured picks are available yet." : "No active products are available in this category yet."}</p>}
    </section>}
    {!isProductPage && !isAccountPage && !isCheckoutPage && !isInfoPage && !isSearchPage && !isCategoryPage && !isWishlistPage && !isDealsPage && !loading && <div className="storefront-discovery">
      {renderDiscoverySection("Best Sellers", "Customer favourites, ranked by recorded sales", bestSellers, <Flame size={18} />)}
      {renderDiscoverySection("New Arrivals", "Fresh additions to the catalogue", newArrivals, <Sparkles size={18} />)}
      {renderDiscoverySection("Recently Viewed", "Pick up where you left off", recentVariants, <Clock3 size={18} />)}
    </div>}
    {!isProductPage && !isAccountPage && !isCheckoutPage && !isInfoPage && !isSearchPage && !isCategoryPage && !isWishlistPage && !isDealsPage && !loading && !displayedVariants.length && !newArrivals.length && !recentVariants.length && <section className="storefront-home-empty" aria-live="polite">
      <div className="storefront-home-empty-icon"><ShoppingBag size={22} aria-hidden="true" /></div>
      <div className="storefront-home-empty-copy"><span className="storefront-kicker">YOUR SUPER BAJAAR</span><h2>No products are available to shop just yet</h2><p>{error ? "We're having trouble loading the catalogue right now. Please try again shortly." : "Explore our departments while we prepare the latest products for your store."}</p></div>
      <a href="#categories">Explore categories <span aria-hidden="true">→</span></a>
    </section>}
    
    {!isProductPage && !isCategoryPage && !isDealsPage && !isWishlistPage && !isAccountPage && !isCheckoutPage && !isInfoPage && !isSearchPage && <section className="storefront-benefits storefront-home-benefits" id="why-us"><div className="storefront-benefits-heading"><span className="storefront-kicker">THE SUPER BAJAAR DIFFERENCE</span><h2>Why Choose Us</h2><p>Everyday shopping, made simpler for you.</p></div><div className="storefront-benefit-grid"><article><span className="benefit-icon"><ShieldCheck size={20} strokeWidth={1.8} aria-hidden="true" /></span><div><strong>Honest pricing</strong><small>No hidden fees, no surcharge and no manipulated shopping.</small></div></article><article><span className="benefit-icon"><Clock3 size={20} strokeWidth={1.8} aria-hidden="true" /></span><div><strong>Just a click away</strong><small>We are always a click away from you, whenever you need us.</small></div></article><article><span className="benefit-icon"><Coins size={20} strokeWidth={1.8} aria-hidden="true" /></span><div><strong>Supercoins that never expire</strong><small>Rewards that really work, without restrictions.</small></div></article><article><span className="benefit-icon"><Users size={20} strokeWidth={1.8} aria-hidden="true" /></span><div><strong>Earn by referring</strong><small>After their first delivered order, you and your friend each get 100 Supercoins, worth ₹100.</small></div></article></div></section>}
    {deliveryOpen && <div className="storefront-delivery-backdrop" role="presentation" onClick={event => { if (event.target === event.currentTarget) setDeliveryOpen(false); }}><section className="storefront-delivery-dialog" role="dialog" aria-modal="true" aria-labelledby="storefront-delivery-title"><button type="button" className="storefront-modal-close" aria-label="Close delivery location" onClick={() => setDeliveryOpen(false)}><X size={19}/></button><span className="storefront-kicker">DELIVERY LOCATION</span><h2 id="storefront-delivery-title">Where should we deliver?</h2><p>Enter your six-digit Indian PIN code to save your preferred delivery location.</p><form onSubmit={saveDeliveryPin}><label>PIN code<input inputMode="numeric" autoComplete="postal-code" pattern="[1-9][0-9]{5}" maxLength="6" value={deliveryDraft} onChange={event => { setDeliveryDraft(event.target.value.replace(/\D/g,"").slice(0,6)); setDeliveryMessage(""); }} required /></label><button className="storefront-primary" type="submit">Save location</button></form>{deliveryMessage && <p className="storefront-delivery-message" role="status">{deliveryMessage}</p>}</section></div>}

    {!isCustomerAuthPage && !isAccountPage && !isCheckoutPage && !isInfoPage && !isSearchPage && !isProductPage && <nav className="storefront-mobile-nav" aria-label="Mobile shopping navigation"><button type="button" className={routePath === "/" ? "is-active" : ""} onClick={openShopHome}><Home size={19}/><span>Home</span></button><button type="button" onClick={() => { openShopHome(); window.setTimeout(() => document.getElementById("categories")?.scrollIntoView({ behavior: "smooth" }), 0); }}><ShoppingCart size={19}/><span>Categories</span></button><button type="button" onClick={() => { window.scrollTo({ top: 0, behavior: "smooth" }); window.setTimeout(() => document.querySelector(".storefront-header-search input")?.focus(), 80); }}><Search size={19}/><span>Search</span></button><button type="button" onClick={() => { if (!customerAuth) { openCustomerAuth("login", "/account"); return; } setAccountSection("orders"); openAccount(); loadMyOrders(); }}><Package size={19}/><span>Orders</span></button><button type="button" onClick={() => customerAuth ? openAccount() : openCustomerAuth("login", "/account")}><UserRound size={19}/><span>Account</span></button></nav>}
    <footer className="storefront-footer">
      <div className="storefront-footer-top"><a className="storefront-brand" href="/" onClick={event=>{event.preventDefault();openShopHome();}}><span className="storefront-logo"><img src="/superbajaar.svg" alt="" /></span><span><strong>Super Bajaar</strong><small>Your Everyday Super Store</small></span></a><p>Everyday made a little brighter.</p></div>
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
          <a href="/pages/payment-information" onClick={e=>{e.preventDefault();openInfoPage("payment-information");}}>Payment Information</a>
          <a href="/pages/cookie-policy" onClick={e=>{e.preventDefault();openInfoPage("cookie-policy");}}>Cookie Policy</a>
          <a href="/pages/loyalty-terms" onClick={e=>{e.preventDefault();openInfoPage("loyalty-terms");}}>Super Coins &amp; Referral Terms</a>
          <a href="/pages/category-terms" onClick={e=>{e.preventDefault();openInfoPage("category-terms");}}>Category-Specific Terms</a>
          <a href="/pages/legal" onClick={e=>{e.preventDefault();openInfoPage("legal");}}>Legal Information</a>
        </div>
      </div>
      <div className="storefront-footer-bottom"><span>© {new Date().getFullYear()} Super Bajaar · A brand of KPMC Enterprises (Proprietorship) · Udyam {BUSINESS.udyam}</span><div className="storefront-social-links"><a href="https://www.facebook.com/profile.php?id=61594558420175" target="_blank" rel="noreferrer">Facebook</a><a href="https://www.instagram.com/super_bajaar" target="_blank" rel="noreferrer">Instagram</a><a href="https://wa.me/917644841104" target="_blank" rel="noreferrer">WhatsApp</a></div>{canOpenAdmin && <a href="/admin">Admin Console ↗</a>}</div>
    </footer>
  </main>;
}
