import { useEffect, useMemo, useRef, useState } from "react";
import { apiRequest } from "../../services/api.js";
import { buildSearchIndex } from "../../app/searchEngine.js";
import { isImageUrl, imageOptionLabel } from "../catalogue/imageOptions.js";
import "./POSWorkspace.css";

const money = value => new Intl.NumberFormat("en-IN", { style: "currency", currency: "INR", maximumFractionDigits: 2 }).format(Number(value || 0));
const round2 = value => Math.round((Number(value) + Number.EPSILON) * 100) / 100;
const HELD_KEY = "superbajaar.pos_held";
const WALK_IN = { name: "Walk-in Customer", phone: "", pin: "" };

// The tender types the backend already accepts. "cod" is how the system stores cash.
const PAYMENT_METHODS = [
  { id: "cod", label: "Cash", mark: "₹" },
  { id: "upi", label: "UPI", mark: "◎" },
  { id: "card", label: "Card", mark: "▭" },
  { id: "netbanking", label: "Net banking", mark: "⌂" },
  { id: "wallet", label: "Wallet", mark: "◈" },
  { id: "bank_transfer", label: "Bank transfer", mark: "⇄" },
];
const methodLabel = id => PAYMENT_METHODS.find(m => m.id === id)?.label || id;

let posRazorpayScript;
function loadPosRazorpay() {
  if (window.Razorpay) return Promise.resolve();
  if (!posRazorpayScript) posRazorpayScript = new Promise((resolve, reject) => {
    const script = document.createElement("script");
    script.src = "https://checkout.razorpay.com/v1/checkout.js";
    script.async = true;
    script.onload = resolve;
    script.onerror = () => { posRazorpayScript = null; reject(new Error("Unable to load secure Razorpay Checkout.")); };
    document.head.appendChild(script);
  });
  return posRazorpayScript;
}


// Readable variant text. Picture-type values show their name, never a long link.
const cleanValue = value => {
  const text = Array.isArray(value) ? value.join(", ") : String(value ?? "");
  if (isImageUrl(text)) { const label = imageOptionLabel(text); return /^[0-9a-f]{8,}$/i.test(label) ? "" : label; }
  return text;
};
const variantLabel = v => Object.values(v.attributes || {}).map(cleanValue).filter(Boolean).join(" / ");
const productTitle = v => v.product_name || v.name || v.sku || ("Product " + v.product_id);

export default function POSWorkspace({ onBack }) {
  const [activeView, setActiveView] = useState("checkout");
  const [mobileCheckoutTab, setMobileCheckoutTab] = useState("catalogue");
  const [variants, setVariants] = useState([]);
  const [posSummary, setPosSummary] = useState(null);
  const [recentSales, setRecentSales] = useState([]);
  const [salesTotal, setSalesTotal] = useState(0);
  const [salesOffset, setSalesOffset] = useState(0);
  const [salesFilters, setSalesFilters] = useState({ search: "", date_from: "", date_to: "", payment_method: "", register_id: "", cashier_user_id: "", status: "" });
  const [salesBusy, setSalesBusy] = useState(false);
  const [selectedSale, setSelectedSale] = useState(null);
  const [refundPayment, setRefundPayment] = useState(null);
  const [refundAmount, setRefundAmount] = useState("");
  const [refundReason, setRefundReason] = useState("");
  const [refundBusy, setRefundBusy] = useState(false);
  const [saleDetailBusy, setSaleDetailBusy] = useState(false);
  const [analyticsError, setAnalyticsError] = useState("");
  const [locations, setLocations] = useState([]);
  const [registers, setRegisters] = useState([]);
  const [selectedRegisterId, setSelectedRegisterId] = useState("");
  const [activeShift, setActiveShift] = useState(null);
  const [shiftCash, setShiftCash] = useState(null);
  const [shiftMovements, setShiftMovements] = useState([]);
  const [shiftHistory, setShiftHistory] = useState([]);
  const [openingFloat, setOpeningFloat] = useState("0.00");
  const [countedCash, setCountedCash] = useState("");
  const [cashMove, setCashMove] = useState({ type: "cash_in", amount: "", reason: "" });
  const [registerDraft, setRegisterDraft] = useState({ code: "", name: "" });
  const [registerBusy, setRegisterBusy] = useState(false);
  const [canManageRegisters, setCanManageRegisters] = useState(false);
  const [cart, setCart] = useState([]);
  const [locationId, setLocationId] = useState("");
  const [registerLocationId, setRegisterLocationId] = useState("");
  const [customer, setCustomer] = useState({ name: "Walk-in Customer", phone: "", pin: "" });
  const [couponCode, setCouponCode] = useState("");
  const [couponApplied, setCouponApplied] = useState(null);
  const [couponBusy, setCouponBusy] = useState(false);
  const [method, setMethod] = useState("cod");
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [receipt, setReceipt] = useState(null);
  const [search, setSearch] = useState("");
  const [selectedVariantByProduct, setSelectedVariantByProduct] = useState({});
  const checkoutAttempt = useRef(null);
  const searchRef = useRef(null);
  const [shown, setShown] = useState(60);
  const [tendered, setTendered] = useState("");
  const [reference, setReference] = useState("");
  const [showCustomer, setShowCustomer] = useState(false);
  const [showReceipt, setShowReceipt] = useState(false);
  const [showHeld, setShowHeld] = useState(false);
  const [pickerId, setPickerId] = useState(null);
  const [held, setHeld] = useState(() => { try { return JSON.parse(window.localStorage.getItem("superbajaar.pos_held") || "[]"); } catch { return []; } });

  async function loadSales(filters = salesFilters, offset = 0) {
    setSalesBusy(true);
    try {
      const query = new URLSearchParams({ limit: "50", offset: String(offset) });
      for (const [key, value] of Object.entries(filters)) if (String(value || "").trim()) query.set(key, String(value).trim());
      const result = await apiRequest("/pos/sales?" + query.toString());
      setRecentSales(result.items || []);
      setSalesTotal(Number(result.total || 0));
      setSalesOffset(offset);
      setAnalyticsError("");
    } catch (e) {
      setAnalyticsError(e.message || "Unable to load POS sales history.");
    } finally {
      setSalesBusy(false);
    }
  }

  function startRefund(payment) {
    const alreadyRefunded = (selectedSale?.refunds || []).filter(r => r.payment_id === payment.id && ["processed","pending"].includes(r.status)).reduce((sum,r)=>sum+Number(r.amount||0),0);
    const remaining = Math.max(0,Number(payment.amount||0)-alreadyRefunded);
    setRefundPayment(payment); setRefundAmount(remaining.toFixed(2)); setRefundReason("");
  }

  async function submitRefund(event) {
    event.preventDefault();
    if (!refundPayment || !selectedSale) return;
    const amount = Number(refundAmount);
    if (!Number.isFinite(amount) || amount <= 0 || !refundReason.trim()) { setAnalyticsError("Enter a positive refund amount and a reason."); return; }
    setRefundBusy(true); setAnalyticsError("");
    try {
      const key = globalThis.crypto?.randomUUID?.() || (Date.now().toString(16)+Math.random().toString(16).slice(2));
      await apiRequest("/payments/"+refundPayment.id+"/manual-refunds", {
        method:"POST", headers:{"Idempotency-Key":key}, body:JSON.stringify({amount,note:refundReason.trim()}),
      });
      setRefundPayment(null); setRefundAmount(""); setRefundReason("");
      await openSaleDetails(selectedSale.id); await refreshAnalytics();
      setNotice("Manual refund recorded. POS cash drawer movement was audited where applicable.");
    } catch(e) { setAnalyticsError(e.message || "Refund could not be recorded."); }
    finally { setRefundBusy(false); }
  }

  async function openSaleDetails(saleId) {
    setSaleDetailBusy(true);
    setSelectedSale(null);
    try {
      setSelectedSale(await apiRequest("/pos/sales/" + saleId));
    } catch (e) {
      setAnalyticsError(e.message || "Unable to load sale details.");
    } finally {
      setSaleDetailBusy(false);
    }
  }

  async function refreshAnalytics() {
    const analytics = await Promise.allSettled([
      apiRequest("/pos/summary"),
      apiRequest("/pos/sales?limit=10"),
    ]);
    if (analytics[0].status === "fulfilled") setPosSummary({ orders: analytics[0].value.orders, payments: analytics[0].value.payments });
    else setPosSummary(null);
    if (analytics[1].status === "fulfilled") setRecentSales(analytics[1].value.items || []);
    else setRecentSales([]);
    const failedAnalytics = analytics.filter(result => result.status === "rejected").length;
    setAnalyticsError(failedAnalytics ? "POS overview is partially unavailable; checkout remains connected to the existing order and payment workflows." : "");
  }

  async function load() {
    setLoading(true); setError("");
    try {
      const [result, locationResult, registerResult, meResult] = await Promise.all([
        apiRequest("/catalogue/variants?limit=5000"),
        apiRequest("/inventory/locations?limit=500"),
        apiRequest("/pos/registers"),
        apiRequest("/auth/me"),
      ]);
      setVariants(result.items || []);
      const activeLocations = (locationResult.items || []).filter(location => location.is_active !== false);
      setLocations(activeLocations);
      if (!registerLocationId && activeLocations.length) setRegisterLocationId(String(activeLocations[0].id));
      const nextRegisters = registerResult.items || [];
      setRegisters(nextRegisters);
      setCanManageRegisters(["manager", "admin", "super_admin"].includes(meResult.user?.role));
      if (!selectedRegisterId && nextRegisters.length) {
        setSelectedRegisterId(String(nextRegisters[0].id));
        setLocationId(String(nextRegisters[0].location_id));
        setRegisterLocationId(String(nextRegisters[0].location_id));
      }
      await refreshAnalytics();
    } catch (e) { setError(e.message || "Unable to load active catalogue variants."); }
    finally { setLoading(false); }
  }
  useEffect(() => { load(); }, []);

  useEffect(() => {
    if (!selectedRegisterId) { setActiveShift(null); setShiftCash(null); setShiftMovements([]); setShiftHistory([]); return; }
    let live = true;
    Promise.all([apiRequest("/pos/registers/" + selectedRegisterId + "/shift"), apiRequest("/pos/registers/" + selectedRegisterId + "/shifts?limit=20")]).then(([result, history]) => {
      if (live) { setActiveShift(result.shift || null); setShiftCash(result.cash || null); setShiftMovements(result.movements || []); setShiftHistory(history.items || []); }
    }).catch(e => { if (live) setError(e.message || "Unable to load register shift."); });
    return () => { live = false; };
  }, [selectedRegisterId]);

  async function refreshShift() {
    if (!selectedRegisterId) return;
    const [result, history] = await Promise.all([apiRequest("/pos/registers/" + selectedRegisterId + "/shift"), apiRequest("/pos/registers/" + selectedRegisterId + "/shifts?limit=20")]);
    setActiveShift(result.shift || null); setShiftCash(result.cash || null); setShiftMovements(result.movements || []); setShiftHistory(history.items || []);
  }

  async function openShift(event) {
    event.preventDefault(); setRegisterBusy(true); setError("");
    try {
      await apiRequest("/pos/registers/" + selectedRegisterId + "/open", { method: "POST", body: JSON.stringify({ opening_float: Number(openingFloat || 0) }) });
      await refreshShift(); await load(); setNotice("Cashier shift opened. Sales are now enabled for this register.");
    } catch (e) { setError(e.message || "Unable to open cashier shift."); }
    finally { setRegisterBusy(false); }
  }

  async function createRegister(event) {
    event.preventDefault(); setRegisterBusy(true); setError("");
    try {
      const created = await apiRequest("/pos/registers", { method: "POST", body: JSON.stringify({ location_id: Number(registerLocationId), register_code: registerDraft.code, name: registerDraft.name }) });
      setRegisterDraft({ code: "", name: "" });
      const next = await apiRequest("/pos/registers"); setRegisters(next.items || []); setSelectedRegisterId(String(created.id)); setLocationId(String(registerLocationId));
      setNotice("Register created. Open a cashier shift to start selling.");
    } catch (e) { setError(e.message || "Unable to create register."); }
    finally { setRegisterBusy(false); }
  }

  async function addCashMovement(event) {
    event.preventDefault(); if (!activeShift) return; setRegisterBusy(true); setError("");
    try {
      await apiRequest("/pos/shifts/" + activeShift.id + "/cash-movements", { method: "POST", body: JSON.stringify({ movement_type: cashMove.type, amount: Number(cashMove.amount), reason: cashMove.reason }) });
      setCashMove({ type: "cash_in", amount: "", reason: "" }); await refreshShift();
      setNotice("Cash drawer movement recorded in the shift audit.");
    } catch (e) { setError(e.message || "Unable to record cash movement."); }
    finally { setRegisterBusy(false); }
  }


  async function confirmCashTender() {
    if (!activeShift || !receipt?.payment?.id) return;
    setRegisterBusy(true); setError("");
    try {
      const payment = await apiRequest("/pos/shifts/" + activeShift.id + "/payments/" + receipt.payment.id + "/confirm-cash", { method: "POST" });
      setReceipt(old => ({ ...old, payment: { ...old.payment, ...payment } }));
      await refreshShift(); void refreshAnalytics();
      setNotice("Cash received and confirmed against this cashier shift.");
    } catch (e) { setError(e.message || "Cash tender could not be confirmed."); }
    finally { setRegisterBusy(false); }
  }

  async function closeShift(event) {
    event.preventDefault(); if (!activeShift) return; setRegisterBusy(true); setError("");
    try {
      const closed = await apiRequest("/pos/shifts/" + activeShift.id + "/close", { method: "POST", body: JSON.stringify({ counted_cash: Number(countedCash), closing_note: "Cashier drawer count" }) });
      setActiveShift(null); setShiftCash(null); setShiftMovements([]); setCountedCash("");
      setNotice("Shift closed. Expected " + money(closed.expected_cash) + ", counted " + money(closed.counted_cash) + ", variance " + money(closed.cash_variance) + ".");
      await load();
    } catch (e) { setError(e.message || "Unable to close cashier shift."); }
    finally { setRegisterBusy(false); }
  }

  const activeVariants = useMemo(() => variants.filter(v => v.is_active !== false), [variants]);
  const searchIndex = useMemo(() => {
    const products = new Map();
    for (const v of activeVariants) if (!products.has(v.product_id)) products.set(v.product_id, { id: v.product_id, name: productTitle(v) });
    return buildSearchIndex({ products: [...products.values()], variants: activeVariants });
  }, [activeVariants]);

  // Search now reacts to every letter typed. It understands spellings like "atta"/"aata",
  // product names, SKUs, barcodes and variant words such as "5 kg".
  const visible = useMemo(() => {
    const term = search.trim().toLowerCase();
    if (!term) return activeVariants;
    const tokens = term.split(/\s+/).filter(Boolean);
    const scores = searchIndex.scores(term);
    const rows = [];
    for (const v of activeVariants) {
      const codes = [v.sku, v.barcode].map(x => String(x || "").toLowerCase());
      const exact = codes.some(x => x === term);
      const codeHit = codes.some(x => x && x.includes(term));
      const nameHit = tokens.every(t => (productTitle(v) + " " + variantLabel(v)).toLowerCase().includes(t));
      const score = scores.get(Number(v.product_id)) || 0;
      if (!exact && !codeHit && !nameHit && !score) continue;
      const label = variantLabel(v).toLowerCase();
      const labelBoost = tokens.filter(t => label.includes(t)).length;
      rows.push({ v, rank: (exact ? 1e6 : 0) + (codeHit ? 1e4 : 0) + (nameHit ? 500 : 0) + score * 10 + labelBoost });
    }
    rows.sort((a, b) => b.rank - a.rank);
    return rows.map(r => r.v);
  }, [activeVariants, searchIndex, search]);
  useEffect(() => { setShown(60); }, [search]);

  // One tile per product; its variants are chosen after tapping the tile.
  const groups = useMemo(() => {
    const map = new Map();
    for (const v of visible) {
      const key = String(v.product_id);
      if (!map.has(key)) map.set(key, { productId: v.product_id, title: productTitle(v), image: v.image_url || "", variants: [] });
      const g = map.get(key);
      if (!g.image && v.image_url) g.image = v.image_url;
      g.variants.push(v);
    }
    return [...map.values()];
  }, [visible]);
  const pickerVariants = useMemo(() => pickerId == null ? [] : activeVariants.filter(v => String(v.product_id) === String(pickerId)), [activeVariants, pickerId]);
  const pickerTitle = pickerVariants.length ? productTitle(pickerVariants[0]) : "";
  function openProduct(group) {
    if (group.variants.length === 1) add(group.variants[0]);
    else setPickerId(String(group.productId));
  }

  const cartCount = cart.reduce((sum, line) => sum + line.quantity, 0);
  const subtotal = round2(cart.reduce((sum, line) => sum + Number(line.selling_price || 0) * line.quantity, 0));
  const validCouponQuote = couponApplied && couponApplied.subtotal === subtotal && couponApplied.code === couponCode.trim().toUpperCase();
  const couponDiscount = validCouponQuote ? Number(couponApplied.discount_amount || 0) : 0;
  const total = round2(subtotal - couponDiscount);
  const qtyById = useMemo(() => new Map(cart.map(line => [line.id, line.quantity])), [cart]);
  const selectedRegister = registers.find(r => String(r.id) === String(selectedRegisterId));
  const locationName = locations.find(l => String(l.id) === String(locationId))?.name || selectedRegister?.location_name || "";

  const tenderedNumber = method === "cod" && tendered !== "" ? Number(tendered) : null;
  const changeDue = tenderedNumber != null && tenderedNumber >= total ? round2(tenderedNumber - total) : null;
  const shortBy = tenderedNumber != null && tenderedNumber < total ? round2(total - tenderedNumber) : null;
  const quickCash = useMemo(() => {
    if (method !== "cod" || total <= 0) return [];
    const up = step => Math.ceil(total / step) * step;
    return [...new Set([up(10), up(50), up(100), up(500), 500, 1000, 2000].filter(x => x > total))].sort((a, b) => a - b).slice(0, 4);
  }, [method, total]);

  const blocker = !cart.length ? "Tap an item on the left to start a sale."
    : couponCode.trim() && !validCouponQuote ? "Apply or reapply the coupon against the current cart subtotal."
    : !selectedRegisterId ? "Choose a counter to sell from."
    : !activeShift ? "Open the cashier shift above to take payment."
    : !locationId ? "Choose a stock location."
    : shortBy != null ? "Cash received is " + money(shortBy) + " short."
    : "";
  const chargeLabel = saving ? "Processing…" : method === "cod" ? "Receive cash · " + money(total) : "Charge " + money(total) + " · " + methodLabel(method);

  useEffect(() => { try { window.localStorage.setItem(HELD_KEY, JSON.stringify(held)); } catch {} }, [held]);
  useEffect(() => {
    const onKey = event => {
      if (event.key === "F2" && activeView === "checkout") { event.preventDefault(); searchRef.current?.focus(); }
      if (event.key === "Escape") { setShowReceipt(false); setPickerId(null); }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [activeView]);

  function selectRegister(value) {
    const r = registers.find(x => String(x.id) === value);
    setSelectedRegisterId(value);
    if (r) { setLocationId(String(r.location_id)); setRegisterLocationId(String(r.location_id)); }
  }

  function add(variant) {
    setCart(old => {
      const existing = old.find(line => line.id === variant.id);
      if (existing) return old.map(line => line.id === variant.id ? { ...line, quantity: Math.min(100000, line.quantity + 1) } : line);
      return [...old, { ...variant, quantity: 1 }];
    });
    setNotice(""); setError("");
  }
  function setQuantity(id, value) {
    const quantity = Number(value);
    setCart(old => !Number.isFinite(quantity) || quantity <= 0 ? old.filter(line => line.id !== id) : old.map(line => line.id === id ? { ...line, quantity: Math.min(100000, Math.floor(quantity)) } : line));
  }
  const bump = (id, delta) => setCart(old => old.map(line => line.id === id ? { ...line, quantity: Math.max(0, Math.min(100000, line.quantity + delta)) } : line).filter(line => line.quantity > 0));
  const removeLine = id => setCart(old => old.filter(line => line.id !== id));

  function resetSale() {
    setCart([]); setCustomer({ ...WALK_IN }); setTendered(""); setReference(""); setShowCustomer(false);
    setCouponCode(""); setCouponApplied(null);
    checkoutAttempt.current = null;
  }
  function holdSale() {
    if (!cart.length) return;
    setHeld(old => [...old, { id: Date.now(), at: new Date().toISOString(), cart, customer, subtotal, total, couponCode, couponApplied }]);
    resetSale(); setNotice("Sale put on hold. Recall it from “Held” whenever you're ready.");
  }
  function recallSale(entry) {
    if (cart.length) { setError("Hold or clear the current sale before recalling a held one."); return; }
    setCart(entry.cart); setCustomer(entry.customer || { ...WALK_IN }); setCouponCode(entry.couponCode || ""); setCouponApplied(entry.couponApplied || null);
    setHeld(old => old.filter(x => x.id !== entry.id)); setShowHeld(false); setError("");
  }
  function onSearchKey(event) {
    if (event.key !== "Enter") return;
    event.preventDefault();
    const term = search.trim().toLowerCase();
    if (!term) return;
    // Barcode scanners "type" the code and press Enter: an exact code (or a single result) goes straight to the sale.
    const exact = visible.find(v => [v.sku, v.barcode].some(x => String(x || "").toLowerCase() === term));
    if (exact) { add(exact); setSearch(""); return; }
    if (groups.length === 1) { openProduct(groups[0]); if (groups[0].variants.length === 1) setSearch(""); }
  }
  function closeReceipt() { setShowReceipt(false); window.setTimeout(() => searchRef.current?.focus(), 50); }

  async function applyCoupon() {
    const code = couponCode.trim().toUpperCase();
    if (!code) { setCouponApplied(null); setError("Enter a coupon code first."); return; }
    if (!cart.length) { setError("Add items before applying a coupon."); return; }
    setCouponBusy(true); setError("");
    try {
      const quote = await apiRequest("/orders/promotions/quote?code=" + encodeURIComponent(code) + "&subtotal=" + encodeURIComponent(subtotal.toFixed(2)));
      setCouponCode(code); setCouponApplied({ code, subtotal, discount_amount: Number(quote.discount_amount) });
      setNotice(code + " applied. You save " + money(quote.discount_amount) + ".");
    } catch (e) { setCouponApplied(null); setError(e.message || "Coupon could not be applied."); }
    finally { setCouponBusy(false); }
  }

  async function checkout(event) {
    event?.preventDefault?.();
    if (!cart.length) { setError("Add at least one item before checkout."); return; }
    const customerName = customer.name.trim() || WALK_IN.name;
    const pin = customer.pin.trim();
    if (pin && !/^[0-9]{6}$/.test(pin)) { setError("Delivery PIN must be exactly 6 digits."); setShowCustomer(true); return; }
    if (shortBy != null) { setError("Cash received is less than the total."); return; }
    setSaving(true); setError(""); setNotice(""); setReceipt(null);
    const note = "Created at POS" + (reference.trim() ? " · Ref: " + reference.trim().slice(0, 100) : "");
    const checkoutPayload = {
      channel: "pos", customer_name: customerName, customer_phone: customer.phone.trim() || null,
      delivery_pin: pin || null, location_id: Number(locationId), pos_register_id: Number(selectedRegisterId), pos_payment_method: method,
      coupon_code: couponCode.trim() || null,
      notes: note, lines: cart.map(line => ({ variant_id: line.id, quantity: line.quantity })),
    };
    const signature = JSON.stringify(checkoutPayload);
    if (!checkoutAttempt.current || checkoutAttempt.current.signature !== signature) {
      checkoutAttempt.current = { signature, key: globalThis.crypto?.randomUUID?.() || (Date.now().toString(16) + Math.random().toString(16).slice(2)) };
    }
    try {
      const order = await apiRequest("/orders", {
        method: "POST",
        body: JSON.stringify({ ...checkoutPayload, checkout_idempotency_key: checkoutAttempt.current.key }),
      });
      let payment = order.payment || null;
      if (!payment) {
        setError("Order " + order.order_number + " was returned without its tender record. Do not create another order; reconcile this sale before retrying.");
        return;
      }
      if (method !== "cod") {
        const gatewayOrder = await apiRequest("/razorpay/orders", {
          method: "POST", body: JSON.stringify({ order_id: order.id }),
        });
        await loadPosRazorpay();
        const result = await new Promise((resolve, reject) => {
          let settled = false;
          const finish = (fn, value) => { if (settled) return; settled = true; fn(value); };
          const checkout = new window.Razorpay({
            key: gatewayOrder.key_id, amount: gatewayOrder.amount, currency: gatewayOrder.currency,
            name: "Super Bajaar", description: "POS sale " + order.order_number,
            order_id: gatewayOrder.razorpay_order_id,
            prefill: { name: customerName, contact: customer.phone.trim() },
            handler: response => finish(resolve, response),
            modal: { ondismiss: () => finish(reject, new Error("Payment window closed. The sale is pending; retry using the same checkout.")) },
          });
          checkout.on("payment.failed", response => finish(reject, new Error(response?.error?.description || "Payment failed. Retry this sale.")));
          checkout.open();
        });
        const verified = await apiRequest("/razorpay/verify", {
          method: "POST", body: JSON.stringify(result),
        });
        payment = { ...payment, status: verified.status || "captured", provider_reference: result.razorpay_payment_id };
      }
      const sale = {
        order, payment, method, at: new Date().toISOString(), counter: activeShift?.register_code || "",
        customer: { name: customerName, phone: customer.phone.trim() },
        tendered: tenderedNumber,
        lines: cart.map((line, index) => ({ id: line.id, name: productTitle(line), label: variantLabel(line), sku: line.sku, quantity: line.quantity, price: Number(line.selling_price || 0), tax: order.tax_lines?.[index] || null })),
      };
      setReceipt(sale);
      resetSale(); setShowReceipt(true);
      void refreshAnalytics();
    } catch (e) {
      setError(e.message || "POS checkout could not be completed. Retry the same sale to safely reuse its checkout key.");
    } finally { setSaving(false); }
  }

  const receiptTotal = receipt ? Number(receipt.order?.total ?? 0) : 0;
  const receiptChange = receipt?.tendered != null && receipt.tendered >= receiptTotal ? round2(receipt.tendered - receiptTotal) : null;
  const cashPending = receipt?.payment?.method === "cod" && receipt.payment.status === "pending";

  return <section className="sb-workspace sb-pos">
    <button className="sb-back" type="button" onClick={onBack}>← All workspaces</button>
    <div className="sb-pos-head">
      <div><p className="sb-eyebrow">OPERATIONS · STORES</p><h1>POS & Stores</h1></div>
      <nav className="sb-pos-nav" aria-label="POS modules"><button type="button" className={activeView === "checkout" ? "is-active" : ""} onClick={() => setActiveView("checkout")}>Checkout</button><button type="button" className={activeView === "sales" ? "is-active" : ""} onClick={() => { setActiveView("sales"); loadSales(salesFilters, 0); }}>Sales history</button><button type="button" className={activeView === "registers" ? "is-active" : ""} onClick={() => setActiveView("registers")}>Registers & cash</button><span>{activeShift ? "Counter active" : "No active shift"}</span></nav>
    </div>
    {activeView !== "checkout" && <p className="sb-pos-sub">Retail checkout, independent counters, cashier shifts and auditable cash-drawer controls.</p>}
    {error && <p className="sb-alert" role="alert">{error}</p>}
    {analyticsError && <p className="sb-alert" role="status">{analyticsError}</p>}
    {notice && <p className="sb-success" role="status">{notice}</p>}
    <div className="sb-data-card sb-pos-register-panel" style={{ display: activeView === "registers" ? "block" : "none" }}>
      <div className="sb-data-heading"><h2>Counter & cashier shift</h2><span className={activeShift ? "sb-pos-status is-open" : "sb-pos-status"}>{activeShift ? "SHIFT OPEN" : "REGISTER CLOSED"}</span></div>
      <div className="sb-pos-register-grid">
        <label>Store counter<select value={selectedRegisterId} onChange={e => { const r = registers.find(x => String(x.id) === e.target.value); setSelectedRegisterId(e.target.value); if (r) { setLocationId(String(r.location_id)); setRegisterLocationId(String(r.location_id)); } }}><option value="">Select register</option>{registers.map(r => <option key={r.id} value={r.id}>{r.location_name} · {r.register_code} — {r.name}</option>)}</select></label>
        {activeShift ? <div className="sb-pos-shift-meta"><strong>{activeShift.register_code} · {activeShift.register_name}</strong><span>Cashier ID: {activeShift.cashier_user_id} · Opened {new Date(activeShift.opened_at).toLocaleString("en-IN")}</span><span>Opening float: {money(activeShift.opening_float)}</span></div> : <form className="sb-pos-inline-form" onSubmit={openShift}><label>Opening cash float (₹)<input type="number" min="0" step="0.01" required value={openingFloat} onChange={e => setOpeningFloat(e.target.value)} /></label><button className="sb-primary" type="submit" disabled={!selectedRegisterId || registerBusy}>{registerBusy ? "Please wait…" : "Open cashier shift"}</button></form>}
      </div>
      {!registers.length && canManageRegisters && <form className="sb-pos-register-create" onSubmit={createRegister}><strong>Create first counter register</strong><label>Store location<select required value={registerLocationId} onChange={e => setRegisterLocationId(e.target.value)}><option value="">Choose store</option>{locations.map(l => <option key={l.id} value={l.id}>{l.name}</option>)}</select></label><label>Register code<input required minLength="2" maxLength="40" value={registerDraft.code} onChange={e => setRegisterDraft(v => ({ ...v, code: e.target.value }))} placeholder="COUNTER-01" /></label><label>Counter name<input required minLength="2" maxLength="120" value={registerDraft.name} onChange={e => setRegisterDraft(v => ({ ...v, name: e.target.value }))} /></label><button className="sb-primary" type="submit" disabled={!registerLocationId || registerBusy}>Create register</button></form>}
      {activeShift && <div className="sb-pos-cash-controls"><div className="sb-pos-cash-metrics"><span>Cash sales<strong>{money(shiftCash?.cash_sales)}</strong></span><span>Cash refunds<strong>{money(shiftCash?.cash_refunds)}</strong></span><span>Cash in<strong>{money(shiftCash?.cash_in)}</strong></span><span>Cash out<strong>{money(shiftCash?.cash_out)}</strong></span></div><form className="sb-pos-inline-form" onSubmit={addCashMovement}><label>Drawer action<select value={cashMove.type} onChange={e => setCashMove(v => ({ ...v, type: e.target.value }))}><option value="cash_in">Cash in</option><option value="cash_out">Cash out</option></select></label><label>Amount (₹)<input type="number" min="0.01" step="0.01" required value={cashMove.amount} onChange={e => setCashMove(v => ({ ...v, amount: e.target.value }))} /></label><label>Reason<input required minLength="3" value={cashMove.reason} onChange={e => setCashMove(v => ({ ...v, reason: e.target.value }))} placeholder="Petty cash / float top-up" /></label><button type="submit" disabled={registerBusy}>Record movement</button></form>{shiftMovements.length > 0 && <div className="sb-pos-movements"><strong>Drawer movement history</strong>{shiftMovements.map(item => <div key={item.id}><span>{item.movement_type.replace("_", " ").toUpperCase()} · {item.reason}</span><b>{money(item.amount)}</b></div>)}</div>}<form className="sb-pos-inline-form sb-pos-close-form" onSubmit={closeShift}><label>Counted drawer cash (₹)<input type="number" min="0" step="0.01" required value={countedCash} onChange={e => setCountedCash(e.target.value)} placeholder="Enter physical cash count" /></label><button type="submit" disabled={registerBusy || countedCash === ""}>Close shift & reconcile</button></form></div>}
      {shiftHistory.length > 0 && <div className="sb-pos-shift-history"><strong>Recent shift history</strong><div className="sb-table-wrap"><table><thead><tr><th>Shift</th><th>Cashier</th><th>Status</th><th>Expected</th><th>Counted</th><th>Variance</th></tr></thead><tbody>{shiftHistory.map(s => <tr key={s.id}><td>#{s.id}<br/><small>{new Date(s.opened_at).toLocaleString("en-IN")}</small></td><td>{s.cashier_user_id}</td><td>{s.status}</td><td>{money(s.expected_cash)}</td><td>{money(s.counted_cash)}</td><td>{s.cash_variance == null ? "—" : money(s.cash_variance)}</td></tr>)}</tbody></table></div></div>}
      {!registers.length && !canManageRegisters && <p className="sb-muted">No counter is configured for this store yet. Ask a manager to create the first POS register.</p>}
      {registers.length > 0 && canManageRegisters && <details className="sb-pos-register-create"><summary>Manager: add another counter</summary><form onSubmit={createRegister}><label>Store location<select required value={locationId} onChange={e => setLocationId(e.target.value)}><option value="">Choose store</option>{locations.map(l => <option key={l.id} value={l.id}>{l.name}</option>)}</select></label><label>Register code<input required value={registerDraft.code} onChange={e => setRegisterDraft(v => ({ ...v, code: e.target.value }))} /></label><label>Counter name<input required value={registerDraft.name} onChange={e => setRegisterDraft(v => ({ ...v, name: e.target.value }))} /></label><button type="submit" disabled={!locationId || registerBusy}>Create register</button></form></details>}
    </div>
    {posSummary && <div className="sb-report-grid" aria-label="POS overview" style={{ display: activeView === "sales" ? "grid" : "none" }}>
      <article className="sb-report-card"><small>POS orders</small><strong>{Number(posSummary.orders?.order_count || 0).toLocaleString("en-IN")}</strong><span>All recorded POS orders</span></article>
      <article className="sb-report-card"><small>Today's sales value</small><strong>{money(posSummary.orders?.today_order_value)}</strong><span>{Number(posSummary.orders?.today_order_count || 0)} orders today</span></article>
      <article className="sb-report-card"><small>Captured payments</small><strong>{money(posSummary.payments?.captured_amount)}</strong><span>{Number(posSummary.payments?.captured_count || 0)} confirmed records</span></article>
      <article className="sb-report-card"><small>Pending payments</small><strong>{money(posSummary.payments?.pending_amount)}</strong><span>{Number(posSummary.payments?.pending_count || 0)} awaiting confirmation</span></article>
    </div>}
    {receipt && <div className="sb-data-card" style={{ display: activeView === "sales" ? "block" : "none" }}><h2>Latest order</h2><p><strong>{receipt.order.order_number}</strong> · {money(receipt.order.total)} · {receipt.order.status}</p><p>Payment record: {receipt.payment ? receipt.payment.payment_reference + " · " + receipt.payment.status : "Not returned — reconcile before retrying."}</p>{receipt.payment?.method === "cod" && receipt.payment.status === "pending" && activeShift && <button type="button" className="sb-primary" onClick={confirmCashTender} disabled={registerBusy}>Confirm cash received</button>}</div>}
    <div className="sb-data-card" style={{ display: activeView === "sales" ? "block" : "none" }}>
      <div className="sb-data-heading"><h2>POS sales history</h2><span>{salesTotal.toLocaleString("en-IN")} matching sales</span></div>
      <form className="sb-pos-inline-form" onSubmit={event => { event.preventDefault(); loadSales(salesFilters, 0); }}>
        <label>Search order / customer / phone<input type="search" maxLength="200" value={salesFilters.search} onChange={event => setSalesFilters(old => ({ ...old, search: event.target.value }))} placeholder="Order number, name or phone" /></label>
        <label>From date<input type="date" value={salesFilters.date_from} onChange={event => setSalesFilters(old => ({ ...old, date_from: event.target.value }))} /></label>
        <label>To date<input type="date" value={salesFilters.date_to} onChange={event => setSalesFilters(old => ({ ...old, date_to: event.target.value }))} /></label>
        <label>Register<select value={salesFilters.register_id} onChange={event => setSalesFilters(old => ({ ...old, register_id: event.target.value }))}><option value="">All registers</option>{registers.map(register => <option key={register.id} value={register.id}>{register.register_code} — {register.name}</option>)}</select></label>
        <label>Order status<select value={salesFilters.status} onChange={event => setSalesFilters(old => ({ ...old, status: event.target.value }))}><option value="">All statuses</option><option value="placed">Placed</option><option value="confirmed">Confirmed</option><option value="processing">Processing</option><option value="ready_for_dispatch">Ready for dispatch</option><option value="dispatched">Dispatched</option><option value="delivered">Delivered</option><option value="cancelled">Cancelled</option></select></label>
        <label>Cashier user ID<input type="number" min="1" step="1" value={salesFilters.cashier_user_id} onChange={event => setSalesFilters(old => ({ ...old, cashier_user_id: event.target.value }))} placeholder="All cashiers" /></label>
        <label>Payment method<select value={salesFilters.payment_method} onChange={event => setSalesFilters(old => ({ ...old, payment_method: event.target.value }))}><option value="">All methods</option><option value="cod">Cash / COD</option><option value="upi">UPI</option><option value="card">Card</option><option value="wallet">Wallet</option><option value="netbanking">Net banking</option><option value="bank_transfer">Bank transfer</option><option value="other">Other</option></select></label>
        <button type="submit" disabled={salesBusy}>{salesBusy ? "Searching…" : "Apply filters"}</button>
        <button type="button" onClick={() => { const cleared = { search: "", date_from: "", date_to: "", payment_method: "", register_id: "", cashier_user_id: "", status: "" }; setSalesFilters(cleared); loadSales(cleared, 0); }} disabled={salesBusy}>Clear</button>
      </form>
      <div className="sb-data-heading"><span>Showing {recentSales.length} of {salesTotal}</span><button type="button" onClick={() => loadSales()} disabled={salesBusy}>Refresh sales</button></div>
      {recentSales.length ? <div className="sb-table-wrap"><table><thead><tr><th>Order</th><th>Customer</th><th>Register / cashier</th><th>Status</th><th>Total</th><th>Captured</th><th>Refunded</th><th>Payment state</th><th>Details</th></tr></thead><tbody>{recentSales.map(sale => <tr key={sale.id}><td>{sale.order_number}</td><td>{sale.customer_name}<br/><small>{sale.customer_phone || "—"}</small></td><td>{sale.register_id ? "#" + sale.register_id : "—"} / {sale.cashier_user_id || "—"}</td><td>{sale.status}</td><td>{money(sale.total)}</td><td>{money(sale.captured_amount)}</td><td>{money(sale.refunded_amount)}</td><td>{sale.payment_statuses || "No payment record"}</td><td><button type="button" onClick={() => openSaleDetails(sale.id)} disabled={saleDetailBusy}>View</button></td></tr>)}</tbody></table></div> : <p className="sb-empty">{salesBusy ? "Loading sales…" : "No POS sales match these filters."}</p>}
      {saleDetailBusy && <p role="status">Loading sale details…</p>}
      <div className="sb-data-heading" aria-label="Sales history pagination"><span>Page {Math.floor(salesOffset / 50) + 1} of {Math.max(1, Math.ceil(salesTotal / 50))}</span><div><button type="button" onClick={() => loadSales(salesFilters, Math.max(0, salesOffset - 50))} disabled={salesBusy || salesOffset === 0}>Previous</button><button type="button" onClick={() => loadSales(salesFilters, salesOffset + 50)} disabled={salesBusy || salesOffset + 50 >= salesTotal}>Next</button></div></div>
      {selectedSale && <section className="sb-pos-sale-detail" aria-label={"Sale details " + selectedSale.order_number}>
        <div className="sb-data-heading"><h3>{selectedSale.order_number} · {money(selectedSale.total)}</h3><button type="button" onClick={() => setSelectedSale(null)}>Close details</button></div>
        <p>{selectedSale.customer_name} · {selectedSale.customer_phone || "No phone"} · {selectedSale.status}</p><p>Subtotal {money(selectedSale.subtotal)} · Discount {money(selectedSale.discount_total)}{selectedSale.promotion_code ? " (" + selectedSale.promotion_code + ")" : ""} · GST {money(selectedSale.tax_total)} · Total {money(selectedSale.total)}</p>
        <div className="sb-table-wrap"><table><thead><tr><th>Item</th><th>SKU</th><th>Qty</th><th>Unit price</th><th>Line total</th><th>GST</th></tr></thead><tbody>{(selectedSale.lines || []).map(line => <tr key={line.id}><td>{line.product_name}</td><td>{line.sku}</td><td>{line.quantity}</td><td>{money(line.unit_price)}</td><td>{money(line.line_total)}</td><td>{money(line.tax_total)}{line.hsn_code ? <small>HSN {line.hsn_code} · {line.gst_rate}%</small> : null}</td></tr>)}</tbody></table></div>
        <div className="sb-table-wrap"><table><thead><tr><th>Payment ref</th><th>Method</th><th>Amount</th><th>Status</th><th>Provider ref</th><th>Action</th></tr></thead><tbody>{(selectedSale.payments || []).map(payment => <tr key={payment.id}><td>{payment.payment_reference}</td><td>{payment.method}</td><td>{money(payment.amount)}</td><td>{payment.status}</td><td>{payment.provider_reference || "—"}</td><td>{canManageRegisters && !payment.provider_reference && ["captured","refunded"].includes(payment.status) && Number(payment.amount) > (selectedSale.refunds || []).filter(r=>r.payment_id===payment.id && ["processed","pending"].includes(r.status)).reduce((sum,r)=>sum+Number(r.amount||0),0) ? <button type="button" onClick={()=>startRefund(payment)}>Refund</button> : "—"}</td></tr>)}</tbody></table></div>{refundPayment && <form className="sb-pos-refund-form" onSubmit={submitRefund}><h4>Refund payment {refundPayment.payment_reference}</h4><label>Refund amount ₹<input type="number" min="0.01" max={Number(refundPayment.amount)} step="0.01" value={refundAmount} onChange={e=>setRefundAmount(e.target.value)} required/></label><label>Reason<input maxLength={500} value={refundReason} onChange={e=>setRefundReason(e.target.value)} placeholder="Customer return / price adjustment" required/></label><button type="submit" disabled={refundBusy}>{refundBusy?"Recording…":"Record refund"}</button><button type="button" disabled={refundBusy} onClick={()=>setRefundPayment(null)}>Cancel</button><small>Gateway refunds are sent to the provider; manual refunds are manager-approved ledger entries with cash-drawer audit when applicable.</small></form>}{(selectedSale.refunds || []).length > 0 && <div className="sb-table-wrap"><h4>Refund ledger</h4><table><thead><tr><th>Refund ID</th><th>Amount</th><th>Method</th><th>Status</th><th>Cash shift</th><th>Reference</th></tr></thead><tbody>{selectedSale.refunds.map(refund=><tr key={refund.id}><td>{refund.id}</td><td>{money(refund.amount)}</td><td>{refund.provider}</td><td>{refund.status}</td><td>{refund.pos_shift_id || "—"}</td><td>{refund.provider_refund_id || refund.note || "—"}</td></tr>)}</tbody></table></div>}
      </section>}
    </div>
    <div className="sb-pos-terminal" style={{ display: activeView === "checkout" ? "block" : "none" }}>
      <div className={"sb-pos-statusbar" + (activeShift ? " is-open" : "")}>
        <label className="sb-pos-counter">Counter
          <select value={selectedRegisterId} onChange={e => selectRegister(e.target.value)} aria-label="Counter">
            <option value="">{registers.length ? "Select counter" : "No counter yet"}</option>
            {registers.map(r => <option key={r.id} value={r.id}>{r.register_code} — {r.name}</option>)}
          </select>
        </label>
        {activeShift ? <>
          <span className="sb-pos-live"><i />Shift open</span>
          <span className="sb-pos-meta">{locationName && <>Stock: <b>{locationName}</b> · </>}Since {new Date(activeShift.opened_at).toLocaleTimeString("en-IN", { hour: "2-digit", minute: "2-digit" })} · Float {money(activeShift.opening_float)}</span>
          <button type="button" className="sb-pos-link" onClick={() => setActiveView("registers")}>Cash drawer & close shift</button>
        </> : selectedRegisterId ? <form className="sb-pos-openshift" onSubmit={openShift}>
          <span className="sb-pos-live is-off"><i />Shift closed</span>
          <label>Opening cash (₹)<input type="number" min="0" step="0.01" required value={openingFloat} onChange={e => setOpeningFloat(e.target.value)} /></label>
          <button type="submit" disabled={registerBusy}>{registerBusy ? "Please wait…" : "Open shift & start selling"}</button>
        </form> : <span className="sb-pos-meta">{registers.length ? "Choose a counter to begin." : "No counter is set up for this store yet."} {!registers.length && <button type="button" className="sb-pos-link" onClick={() => setActiveView("registers")}>Set up a counter</button>}</span>}
        <div className="sb-pos-held">
          <button type="button" onClick={() => setShowHeld(v => !v)} aria-expanded={showHeld}>Held ({held.length})</button>
          {showHeld && <div className="sb-pos-held-list">
            {!held.length ? <p>No sales on hold.</p> : held.map(entry => <div key={entry.id}><span><b>{entry.customer?.name || WALK_IN.name}</b><small>{entry.cart.reduce((s, l) => s + l.quantity, 0)} items · {money(entry.total)} · {new Date(entry.at).toLocaleTimeString("en-IN", { hour: "2-digit", minute: "2-digit" })}</small></span><button type="button" onClick={() => recallSale(entry)}>Recall</button><button type="button" className="is-danger" onClick={() => setHeld(old => old.filter(x => x.id !== entry.id))} aria-label="Delete held sale">✕</button></div>)}
          </div>}
        </div>
      </div>
      <nav className="sb-pos-mobile-step" aria-label="POS checkout steps">
        <button type="button" className={mobileCheckoutTab === "catalogue" ? "is-active" : ""} aria-current={mobileCheckoutTab === "catalogue" ? "step" : undefined} onClick={() => setMobileCheckoutTab("catalogue")}>Items</button>
        <button type="button" className={mobileCheckoutTab === "cart" ? "is-active" : ""} aria-current={mobileCheckoutTab === "cart" ? "step" : undefined} onClick={() => setMobileCheckoutTab("cart")}>Cart ({cartCount})</button>
        <button type="button" className={mobileCheckoutTab === "pay" ? "is-active" : ""} aria-current={mobileCheckoutTab === "pay" ? "step" : undefined} onClick={() => setMobileCheckoutTab("pay")}>Pay</button>
      </nav>
      <div className="sb-pos-layout">
        <div className={"sb-data-card sb-pos-catalogue-panel " + (mobileCheckoutTab === "catalogue" ? "is-mobile-active" : "")}>
          <div className="sb-pos-searchbar">
            <span aria-hidden="true">⌕</span>
            <input ref={searchRef} type="search" value={search} onChange={e => setSearch(e.target.value)} onKeyDown={onSearchKey} placeholder="Search item, SKU or scan barcode…  (F2)" aria-label="Search product or SKU" autoComplete="off" enterKeyHint="search" />
            {search && <button type="button" onClick={() => { setSearch(""); searchRef.current?.focus(); }} aria-label="Clear search">✕</button>}
            <button type="button" className="sb-pos-refresh" onClick={load} disabled={loading}>{loading ? "Loading…" : "Refresh"}</button>
          </div>
          {!loading && <p className="sb-pos-count">{search.trim() ? groups.length + (groups.length === 1 ? " product" : " products") + " found for “" + search.trim() + "”" : groups.length + " products available"}</p>}
          {loading ? <p className="sb-empty">Loading items…</p> : <div className="sb-pos-products">
            {groups.slice(0, shown).map(g => {
              const multi = g.variants.length > 1;
              const inCart = g.variants.reduce((sum, v) => sum + (qtyById.get(v.id) || 0), 0);
              const prices = g.variants.map(v => Number(v.selling_price || 0));
              const low = Math.min(...prices); const high = Math.max(...prices);
              const single = g.variants[0]; const label = multi ? "" : variantLabel(single);
              return <button type="button" className={"sb-pos-tile" + (inCart ? " is-in-cart" : "")} key={g.productId} onClick={() => openProduct(g)} aria-label={(multi ? "Choose variant: " : "Add to sale: ") + g.title}>
                <span className="sb-pos-tile-art">{g.image ? <img src={g.image} alt="" loading="lazy" onError={e => { e.currentTarget.style.display = "none"; }} /> : null}<i>{g.title.trim().charAt(0).toUpperCase()}</i>{inCart > 0 && <b className="sb-pos-tile-badge">{inCart}</b>}</span>
                <strong>{g.title}</strong>
                {multi ? <small className="sb-pos-tile-variants">{g.variants.length} variants ›</small> : label ? <small>{label}</small> : null}
                <span className="sb-pos-tile-price">{multi && low !== high ? "From " : ""}{money(low)}</span>
              </button>;
            })}
          </div>}
          {!loading && groups.length > shown && <button type="button" className="sb-pos-more" onClick={() => setShown(n => n + 60)}>Show more products ({groups.length - shown} left)</button>}
          {!loading && !groups.length && <p className="sb-empty">{search.trim() ? "Nothing matches “" + search.trim() + "”. Try fewer letters, another spelling, or the SKU." : "No active saleable variants are available. Add or activate a product and its variant in Catalogue."}</p>}
        </div>
        <div className={"sb-data-card sb-pos-sale-panel " + (mobileCheckoutTab !== "catalogue" ? "is-mobile-active" : "")}>
          <div className={"sb-pos-cart-panel " + (mobileCheckoutTab === "cart" ? "is-mobile-active" : "")}>
            <div className="sb-pos-cart-head"><h2>Current sale <small>{cartCount} {cartCount === 1 ? "item" : "items"}</small></h2>
              <span><button type="button" onClick={holdSale} disabled={!cart.length}>Hold</button><button type="button" className="is-danger" onClick={resetSale} disabled={!cart.length}>Clear</button></span></div>
            {!cart.length ? <p className="sb-empty sb-pos-empty">Cart is empty.<br />Tap an item to add it, or scan a barcode.</p> : <div className="sb-pos-cart">{cart.map(line => <div className="sb-pos-cart-line" key={line.id}>
              <div className="sb-pos-line-info"><strong>{productTitle(line)}</strong><small>{[variantLabel(line), money(line.selling_price) + " each"].filter(Boolean).join(" · ")}</small></div>
              <div className="sb-pos-stepper"><button type="button" onClick={() => bump(line.id, -1)} aria-label={"Decrease " + productTitle(line)}>−</button><input type="number" min="0" max="100000" step="1" inputMode="numeric" value={line.quantity} onChange={e => setQuantity(line.id, e.target.value)} aria-label={"Quantity for " + productTitle(line)} /><button type="button" onClick={() => bump(line.id, 1)} aria-label={"Increase " + productTitle(line)}>+</button></div>
              <strong className="sb-pos-line-total">{money(Number(line.selling_price || 0) * line.quantity)}</strong>
              <button type="button" className="sb-pos-remove" onClick={() => removeLine(line.id)} aria-label={"Remove " + productTitle(line)}>✕</button>
            </div>)}</div>}
            <div className="sb-pos-total"><span>Subtotal</span><strong>{money(subtotal)}</strong></div>
            <div className="sb-pos-coupon" aria-label="Coupon discount">
              <label>Coupon code<input value={couponCode} maxLength={40} onChange={e => { setCouponCode(e.target.value.toUpperCase()); setCouponApplied(null); }} placeholder="Enter coupon" /></label>
              <button type="button" onClick={applyCoupon} disabled={couponBusy || !couponCode.trim() || !cart.length}>{couponBusy ? "Checking…" : "Apply"}</button>
              {validCouponQuote && <button type="button" onClick={() => { setCouponCode(""); setCouponApplied(null); setNotice("Coupon removed."); }} aria-label="Remove coupon">Remove</button>}
            </div>
            {couponCode.trim() && !validCouponQuote && <small className="sb-muted">Reapply the coupon if cart items or quantities change.</small>}
            {validCouponQuote && <div className="sb-pos-total sb-pos-discount"><span>Coupon · {couponCode}</span><strong>−{money(couponDiscount)}</strong></div>}
            <div className="sb-pos-total"><span>Total due</span><strong>{money(total)}</strong></div>
            <button className="sb-pos-mobile-next" type="button" onClick={() => setMobileCheckoutTab("pay")}>Continue to payment</button>
          </div>
          <form className={"sb-pos-payment-panel " + (mobileCheckoutTab === "pay" ? "is-mobile-active" : "")} onSubmit={checkout} noValidate>
            <button className="sb-pos-mobile-back" type="button" onClick={() => setMobileCheckoutTab("cart")}>← Back to cart</button>
            <div className="sb-pos-customer">
              <button type="button" className="sb-pos-customer-row" onClick={() => setShowCustomer(v => !v)} aria-expanded={showCustomer}><span>Customer</span><b>{customer.name.trim() || WALK_IN.name}{customer.phone ? " · " + customer.phone : ""}</b><em>{showCustomer ? "Done" : "Edit"}</em></button>
              {showCustomer && <div className="sb-pos-customer-edit">
                <label>Customer name<input maxLength="200" value={customer.name} onChange={e => setCustomer(v => ({ ...v, name: e.target.value }))} /></label>
                <label>Phone (optional)<input type="tel" maxLength="20" value={customer.phone} onChange={e => setCustomer(v => ({ ...v, phone: e.target.value }))} /></label>
                <label>Delivery PIN (optional)<input inputMode="numeric" maxLength="6" value={customer.pin} onChange={e => setCustomer(v => ({ ...v, pin: e.target.value.replace(/\D/g, "") }))} /></label>
                {!selectedRegisterId && <label>Stock location<select value={locationId} onChange={e => setLocationId(e.target.value)}><option value="">Choose stock location</option>{locations.map(location => <option key={location.id} value={location.id}>{location.name} · {location.location_type || "location"}</option>)}</select></label>}
              </div>}
            </div>
            <div className="sb-pos-methods" role="radiogroup" aria-label="Payment method">
              {PAYMENT_METHODS.map(m => <button type="button" role="radio" aria-checked={method === m.id} key={m.id} className={method === m.id ? "is-selected" : ""} onClick={() => { setMethod(m.id); setTendered(""); }}><i aria-hidden="true">{m.mark}</i>{m.label}</button>)}
            </div>
            <div className="sb-pos-tender">
              {method === "cod" ? <>
                <label>Cash received (₹)<input type="number" min="0" step="0.01" inputMode="decimal" value={tendered} onChange={e => setTendered(e.target.value)} placeholder={total ? "Leave empty if exact" : "0.00"} /></label>
                {quickCash.length > 0 || total > 0 ? <div className="sb-pos-quick"><button type="button" onClick={() => setTendered(total.toFixed(2))} disabled={!total}>Exact</button>{quickCash.map(x => <button type="button" key={x} onClick={() => setTendered(String(x))}>{money(x)}</button>)}</div> : null}
                <div className={"sb-pos-change" + (shortBy != null ? " is-short" : "")}><span>{shortBy != null ? "Still to collect" : "Change to return"}</span><strong>{money(shortBy != null ? shortBy : (changeDue ?? 0))}</strong></div>
                <p className="sb-muted">Cash is saved as pending and counted into this shift once you tap “Confirm cash received” on the receipt.</p>
              </> : <>
                <div className="sb-pos-due"><span>Amount to collect via {methodLabel(method)}</span><strong>{money(total)}</strong></div>
                <label>{method === "card" ? "Card terminal / approval reference (optional)" : "Payment reference (optional)"}<input maxLength="100" value={reference} onChange={e => setReference(e.target.value)} placeholder={method === "card" ? "Last 4 digits or approval code" : method === "upi" ? "UPI transaction ID" : "Reference number"} /></label>
                <p className="sb-muted">{method === "card" ? "Customer taps, inserts or swipes their card on the machine." : method === "upi" ? "Customer scans the store UPI QR and pays." : "Collect the payment as per the method chosen."} The sale stays pending until the payment is verified.</p>
              </>}
            </div>
            <button className="sb-pos-charge" type="submit" disabled={saving || Boolean(blocker)}>{chargeLabel}</button>
            {blocker && <p className="sb-pos-blocker" role="status">{blocker}</p>}
            {!locations.length && !loading && <small className="sb-muted">No active stock locations are available. Create or activate a store or warehouse in Inventory before checkout.</small>}
          </form>
        </div>
      </div>
      {mobileCheckoutTab === "catalogue" && cartCount > 0 && <button type="button" className="sb-pos-cartbar" onClick={() => setMobileCheckoutTab("cart")}><span>{cartCount} {cartCount === 1 ? "item" : "items"}</span><strong>View cart · {money(total)} →</strong></button>}
    </div>
    {pickerId != null && pickerVariants.length > 0 && <div className="sb-pos-modal" role="dialog" aria-modal="true" aria-label={"Choose variant of " + pickerTitle} onClick={e => { if (e.target === e.currentTarget) setPickerId(null); }}>
      <div className="sb-pos-picker">
        <div className="sb-pos-picker-head"><div><h2>{pickerTitle}</h2><p>Tap a variant to add it to the sale</p></div><button type="button" onClick={() => setPickerId(null)} aria-label="Close">✕</button></div>
        <div className="sb-pos-picker-list">{pickerVariants.map(v => {
          const qty = qtyById.get(v.id) || 0; const label = variantLabel(v);
          return <button type="button" key={v.id} className={"sb-pos-picker-row" + (qty ? " is-in-cart" : "")} onClick={() => add(v)}>
            <span className="sb-pos-picker-info"><b>{label || "Default variant"}</b><small>{v.sku}</small></span>
            <span className="sb-pos-picker-price">{money(v.selling_price)}</span>
            <span className="sb-pos-picker-qty">{qty ? "× " + qty : "+ Add"}</span>
          </button>;
        })}</div>
        <button type="button" className="sb-pos-picker-done" onClick={() => setPickerId(null)}>{cartCount ? "Done · " + cartCount + (cartCount === 1 ? " item" : " items") + " in cart" : "Close"}</button>
      </div>
    </div>}
    {showReceipt && receipt?.payment && <div className="sb-pos-modal" role="dialog" aria-modal="true" aria-label="Sale receipt" onClick={e => { if (e.target === e.currentTarget) closeReceipt(); }}>
      <div className="sb-pos-receipt">
        <div className="sb-pos-receipt-sheet">
          <div className="sb-pos-receipt-top"><span className="sb-pos-tick" aria-hidden="true">✓</span><h2>Sale recorded</h2><p>{receipt.order.order_number}</p></div>
          <p className="sb-pos-receipt-meta">Super Bajaar{receipt.counter ? " · " + receipt.counter : ""}<br />{new Date(receipt.at).toLocaleString("en-IN")}<br />Customer: {receipt.customer.name}{receipt.customer.phone ? " · " + receipt.customer.phone : ""}</p>
          <table><tbody>{receipt.lines.map(l => <tr key={l.id}><td>{l.name}{l.label ? <small>{l.label}</small> : null}<small>{l.quantity} × {money(l.price)}</small>{l.tax?.hsn_code ? <small>HSN {l.tax.hsn_code} · GST {l.tax.gst_rate}%</small> : null}</td><td>{money(l.price * l.quantity)}</td></tr>)}</tbody></table>
          {Number(receipt.order.tax_total || 0) > 0 && <div className="sb-pos-receipt-tax"><span>GST included in total</span><strong>{money(receipt.order.tax_total)}</strong></div>}
          {Number(receipt.order.discount_total || 0) > 0 && <div className="sb-pos-receipt-tax"><span>Discount{receipt.order.promotion_code ? " · " + receipt.order.promotion_code : ""}</span><strong>−{money(receipt.order.discount_total)}</strong></div>}
          <div className="sb-pos-receipt-total"><span>Total</span><strong>{money(receiptTotal)}</strong></div>
          <p className="sb-pos-receipt-pay">{methodLabel(receipt.method)} · {cashPending ? "cash awaiting confirmation" : receipt.payment.status}{receipt.payment.payment_reference ? " · " + receipt.payment.payment_reference : ""}</p>
          {receipt.tendered != null && <p className="sb-pos-receipt-pay">Cash received {money(receipt.tendered)}{receiptChange != null ? " · Change " + money(receiptChange) : ""}</p>}
          <p className="sb-pos-receipt-thanks">Thank you for shopping at Super Bajaar!</p>
        </div>
        <div className="sb-pos-receipt-actions">
          {cashPending && activeShift && <button type="button" className="sb-pos-charge" onClick={confirmCashTender} disabled={registerBusy}>{registerBusy ? "Please wait…" : "Confirm cash received"}</button>}
          <button type="button" onClick={() => window.print()}>Print receipt</button>
          <button type="button" className="is-primary" onClick={closeReceipt}>New sale</button>
        </div>
      </div>
    </div>}
  </section>;
}
