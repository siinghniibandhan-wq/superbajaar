import { useEffect, useMemo, useState } from "react";
import { apiRequest } from "../../services/api.js";
import ProductImagesPanel from "./ProductImagesPanel.jsx";
import ColourOptionEditor from "./ColourOptionEditor.jsx";
import ImageOptionEditor from "./ImageOptionEditor.jsx";
import ImageValueEditor from "./ImageValueEditor.jsx";
import { combineImageOptions, normalizeImageOption, normalizeImageOptions, resolveImageValue } from "./imageOptions.js";
import { colourOptionLabel, normalizeColourOption } from "./colourOptions.js";
import { buildCompleteProductPayload } from "./catalogueComplete.js";
import { cleanHsn, isValidHsn, matchHsnRule } from "./hsnRules.js";
import { sortValuesLowToHigh, orderByList, moveValue, variantIdsInOrder } from "./variantOrder.js";
import "./ProductCreateForm.css";

const EMPTY = { name: "", slug: "", brand: "", category_id: "", category_ids: [], description: "", tax_code: "", tax_rate: "", selling_price: "", mrp: "", is_pos_available: true, is_website_available: true, delivery_options: ["standard"] };
const OPTION_TYPES = ["text", "colour", "image"];
function ProductImagesEmbedded({ product }) { return <ProductImagesPanel products={[product]} initialProductId={product.id} embedded />; }

function slugifyName(value) { return String(value).toLowerCase().trim().replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, ""); }

function combinationKey(attributes) {
  return JSON.stringify(Object.fromEntries(Object.entries(attributes || {}).sort(([a], [b]) => a.localeCompare(b))));
}

function combinations(items) {
  return items.reduce((acc, item) => acc.flatMap(prefix => item.values.map(value => [...prefix, [item.code, value]])), [[]]).map(entries => Object.fromEntries(entries));
}

// Combinations of the selected values that have no active variant: these were deliberately left out/hidden.
function excludedFrom(values, rows) {
  const codes = Object.keys(values || {}).filter(code => (values[code] || []).length);
  if (!codes.length) return {};
  const all = combinations(codes.map(code => ({ code, values: values[code] })));
  const active = new Set(rows.map(row => combinationKey(row.attributes || {})));
  if (!all.some(attrs => active.has(combinationKey(attrs)))) return {};
  return Object.fromEntries(all.map(attrs => combinationKey(attrs)).filter(key => !active.has(key)).map(key => [key, true]));
}

export default function ProductCreateForm({ categories = [], product = null, duplicateFrom = null, onSaved, onBusyChange }) {
  const [form, setForm] = useState(duplicateFrom && !product ? {
    ...EMPTY,
    name: (duplicateFrom.name || "") + " (Copy)",
    slug: slugifyName((duplicateFrom.name || "") + " (Copy)"),
    brand: duplicateFrom.brand || "",
    description: duplicateFrom.description || "",
    tax_code: duplicateFrom.tax_code || "",
    tax_rate: duplicateFrom.tax_rate == null ? "" : String(Number(duplicateFrom.tax_rate)),
    selling_price: duplicateFrom.min_selling_price ?? "",
    mrp: duplicateFrom.min_mrp ?? duplicateFrom.min_selling_price ?? "",
    category_ids: Array.isArray(duplicateFrom.category_ids) && duplicateFrom.category_ids.length ? duplicateFrom.category_ids.map(String) : (duplicateFrom.category_id ? [String(duplicateFrom.category_id)] : []),
    is_pos_available: duplicateFrom.is_pos_available !== false,
    is_website_available: duplicateFrom.is_website_available !== false,
    delivery_options: duplicateFrom.delivery_options?.length ? duplicateFrom.delivery_options : ["standard"],
  } : product ? {
    ...EMPTY,
    ...product,
    selling_price: product.selling_price ?? product.min_selling_price ?? "",
    mrp: product.mrp ?? product.min_mrp ?? "",
    category_id: product.category_id ? String(product.category_id) : "",
    category_ids: Array.isArray(product.category_ids) && product.category_ids.length ? product.category_ids.map(String) : (product.category_id ? [String(product.category_id)] : []),
  } : EMPTY);
  const [definitions, setDefinitions] = useState([]);
  const [selected, setSelected] = useState({});
  // Storefront display order of the selected values, per attribute code, e.g. { weight: ["0.1 Kg", "0.5 Kg", "1 Kg"] }.
  const [valueOrder, setValueOrder] = useState({});
  const [hsnRules, setHsnRules] = useState([]);
  // Once someone types an HSN/GST by hand (or the product already has one), rules only suggest instead of overwriting.
  const [taxManual, setTaxManual] = useState(Boolean(product?.tax_code || duplicateFrom?.tax_code));
  const [productAttributeValues, setProductAttributeValues] = useState({});
  const [customAttributeOptions, setCustomAttributeOptions] = useState({});
  const [pendingCustomOptions, setPendingCustomOptions] = useState({});
  const [variantPricing, setVariantPricing] = useState({});
  const [excludedCombos, setExcludedCombos] = useState({});
  const [newOptions, setNewOptions] = useState({});
  const [editingImage, setEditingImage] = useState(null);
  const [activeTab, setActiveTab] = useState("general");
  const [availabilityRules, setAvailabilityRules] = useState([]);
  const [stockLocations, setStockLocations] = useState([]);
  const [ruleDraft, setRuleDraft] = useState({ channel: "website", region_code: "", pincode: "", location_id: "", is_allowed: true });
  const [existingVariants, setExistingVariants] = useState([]);
  const [variantPriceEdits, setVariantPriceEdits] = useState({});
  const [bulkPrice, setBulkPrice] = useState({ selling_price: "", mrp: "" });
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [success, setSuccess] = useState("");
  const slugify = value => value.toLowerCase().trim().replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "");
  const change = (key, value) => setForm(old => ({ ...old, [key]: value }));

  async function loadDefinitions() {
    const result = await apiRequest("/catalogue/attributes");
    setDefinitions(result.items || []);
  }
  useEffect(() => { loadDefinitions().catch(e => setError(e.message || "Unable to load attributes.")); }, []);
  useEffect(() => {
    apiRequest("/catalogue/hsn-rules").then(result => setHsnRules(result.items || [])).catch(() => setHsnRules([]));
  }, []);
  useEffect(() => {
    apiRequest("/catalogue/stock-locations").then(result => setStockLocations(result.items || [])).catch(() => setStockLocations([]));
  }, []);
  useEffect(() => {
    if (!product?.id || !definitions.length) return;
    apiRequest("/catalogue/products/" + product.id + "/attributes")
      .then(result => {
        const values = {};
        for (const item of result.items || []) {
          if (!item.is_variant_attribute && item.value !== null && item.value !== undefined) values[item.id] = item.value;
        }
        setProductAttributeValues(values);
      })
      .catch(e => setError(e.message || "Unable to load product attributes."));
    Promise.all(definitions.filter(def => def.is_variant_attribute && OPTION_TYPES.includes(def.value_type)).map(async def => {
      const result = await apiRequest("/catalogue/products/" + product.id + "/attributes/" + def.id + "/options");
      return [def.id, (result.items || []).map(item => item.value)];
    })).then(entries => setCustomAttributeOptions(Object.fromEntries(entries)))
      .catch(e => setError(e.message || "Unable to load product-specific attribute options."));
    apiRequest("/catalogue/products/" + product.id + "/variants?limit=500")
      .then(result => {
        const values = {};
        // Only active variants count: un-ticked (retired) values must not come back ticked.
        for (const row of (result.items || []).filter(item => item.is_active !== false)) {
          for (const [code, raw] of Object.entries(row.attributes || {})) {
            const list = Array.isArray(raw) ? raw : [raw];
            values[code] = [...new Set([...(values[code] || []), ...list])];
          }
        }
        setSelected(old => ({ ...values, ...old }));
        setValueOrder(old => ({ ...values, ...old }));
        setExcludedCombos(excludedFrom(values, (result.items || []).filter(item => item.is_active !== false)));
      })
      .catch(e => setError(e.message || "Unable to load existing product variants."));
  }, [product?.id, definitions]);
  useEffect(() => {
    if (!product?.id) return;
    apiRequest("/catalogue/products/" + product.id + "/variants?limit=500")
      .then(result => {
        const active = (result.items || []).filter(item => item.is_active !== false);
        setExistingVariants(active);
        setVariantPriceEdits(Object.fromEntries(active.map(item => [item.id, {
          selling_price: item.selling_price == null ? "" : String(item.selling_price),
          mrp: item.mrp == null ? "" : String(item.mrp),
          cost_price: item.cost_price == null ? "" : String(item.cost_price),
        }])));
      })
      .catch(() => setExistingVariants([]));
  }, [product?.id]);
  useEffect(() => {
    if (!product?.id) return;
    apiRequest("/catalogue/products/" + product.id + "/availability-rules")
      .then(result => setAvailabilityRules(result.items || []))
      .catch(e => setError(e.message || "Unable to load availability restrictions."));
  }, [product?.id]);

  useEffect(() => {
    if (product?.id || !duplicateFrom?.id || !definitions.length) return;
    const sourceId = duplicateFrom.id;
    apiRequest("/catalogue/products/" + sourceId + "/attributes")
      .then(result => {
        const values = {};
        for (const item of result.items || []) {
          if (!item.is_variant_attribute && item.value !== null && item.value !== undefined) values[item.id] = item.value;
        }
        setProductAttributeValues(values);
      })
      .catch(e => setError(e.message || "Unable to copy product attributes."));
    Promise.all(definitions.filter(def => def.is_variant_attribute && OPTION_TYPES.includes(def.value_type)).map(async def => {
      const result = await apiRequest("/catalogue/products/" + sourceId + "/attributes/" + def.id + "/options");
      return [def.id, (result.items || []).map(item => item.value)];
    })).then(entries => {
      const options = Object.fromEntries(entries.filter(([, list]) => list.length));
      setCustomAttributeOptions(options);
      setPendingCustomOptions(options);
    }).catch(e => setError(e.message || "Unable to copy product-specific attribute options."));
    apiRequest("/catalogue/products/" + sourceId + "/variants?limit=500")
      .then(result => {
        const values = {}; const pricing = {};
        for (const row of (result.items || []).filter(item => item.is_active !== false)) {
          for (const [code, raw] of Object.entries(row.attributes || {})) {
            const list = Array.isArray(raw) ? raw : [raw];
            values[code] = [...new Set([...(values[code] || []), ...list])];
          }
          pricing[combinationKey(row.attributes || {})] = {
            selling_price: row.selling_price == null ? "" : String(row.selling_price),
            mrp: row.mrp == null ? "" : String(row.mrp),
            cost_price: row.cost_price == null ? "" : String(row.cost_price),
          };
        }
        setSelected(values);
        setValueOrder(values);
        setVariantPricing(pricing);
        setExcludedCombos(excludedFrom(values, (result.items || []).filter(item => item.is_active !== false)));
      })
      .catch(e => setError(e.message || "Unable to copy product variants."));
    apiRequest("/catalogue/products/" + sourceId + "/availability-rules")
      .then(result => setAvailabilityRules((result.items || []).map(({ id, ...rule }) => rule)))
      .catch(e => setError(e.message || "Unable to copy availability restrictions."));
  }, [duplicateFrom?.id, definitions]);

  // On edit: a product with exactly one active variant can have its price edited here; with several variants, prices stay per-variant.
  const soleVariant = product?.id && existingVariants.length === 1 ? existingVariants[0] : null;
  // Editing a product with several variants: prices are edited per variant in the form (no more locked fields).
  const multiVariantEdit = Boolean(product?.id) && existingVariants.length > 1;
  const variantLabel = row => {
    // Image values may be saved as an image link; show the same readable name the Images tab shows.
    const parts = Object.entries(row.attributes || {}).flatMap(([code, raw]) => {
      const definition = definitions.find(item => item.code === code);
      return (Array.isArray(raw) ? raw : [raw]).map(value => {
        if (value && typeof value === "object") return value.name || value.label || value.value || "";
        if (definition?.value_type === "image") return resolveImageValue(value, combineImageOptions(definition.options || [], (customAttributeOptions || {})[definition.id] || [])).name;
        return String(value);
      });
    }).filter(Boolean);
    return (parts.join(" / ") || "Default") + (row.sku ? " · " + row.sku : "");
  };
  const setVariantPrice = (id, key, value) => setVariantPriceEdits(old => ({ ...old, [id]: { ...(old[id] || {}), [key]: value } }));
  const applyBulkPrice = () => {
    if (bulkPrice.selling_price === "" && bulkPrice.mrp === "") { setError("Type a selling price or an MRP to apply to all variants."); return; }
    setError("");
    setVariantPriceEdits(old => Object.fromEntries(existingVariants.map(row => [row.id, {
      ...(old[row.id] || {}),
      ...(bulkPrice.selling_price !== "" ? { selling_price: bulkPrice.selling_price } : {}),
      ...(bulkPrice.mrp !== "" ? { mrp: bulkPrice.mrp } : {}),
    }])));
  };
  const changedVariantPrices = () => existingVariants.map(row => {
    const edit = variantPriceEdits[row.id] || {};
    const selling = edit.selling_price === "" || edit.selling_price === undefined ? NaN : Number(edit.selling_price);
    const mrpValue = edit.mrp === "" || edit.mrp === undefined ? selling : Number(edit.mrp);
    const cost = edit.cost_price === "" || edit.cost_price === undefined ? null : Number(edit.cost_price);
    return { row, selling, mrp: mrpValue, cost };
  });
  // Product details (Form, Formulation, Packaging...) by attribute code, used to pick the most specific HSN rule.
  const hsnSuggestion = useMemo(() => {
    const values = {};
    for (const def of definitions) {
      if (def.is_variant_attribute) continue;
      const raw = productAttributeValues[def.id];
      if (typeof raw === "string" && raw.trim()) values[def.code] = raw;
    }
    return matchHsnRule(hsnRules, categories, { categoryIds: form.category_ids || [], values });
  }, [hsnRules, categories, definitions, productAttributeValues, form.category_ids]);
  useEffect(() => {
    if (!hsnSuggestion || taxManual) return;
    setForm(old => (old.tax_code === hsnSuggestion.hsn_code && String(old.tax_rate) === String(Number(hsnSuggestion.gst_rate))) ? old : { ...old, tax_code: hsnSuggestion.hsn_code, tax_rate: String(Number(hsnSuggestion.gst_rate)) });
  }, [hsnSuggestion, taxManual]);
  const hsnMatchesForm = hsnSuggestion && form.tax_code === hsnSuggestion.hsn_code && String(form.tax_rate) === String(Number(hsnSuggestion.gst_rate));
  const chosenAttributes = useMemo(() => definitions.filter(def => def.is_variant_attribute && OPTION_TYPES.includes(def.value_type) && (selected[def.code] || []).length), [definitions, selected]);
  const variantCombinations = useMemo(() => {
    if (!chosenAttributes.length) return [{}];
    return combinations(chosenAttributes.map(def => ({ code: def.code, values: def.value_type === "multi_select" ? [[...(selected[def.code] || [])]] : orderByList(selected[def.code] || [], valueOrder[def.code] || []) })));
  }, [chosenAttributes, selected, valueOrder]);

  const includedCombinations = useMemo(() => chosenAttributes.length ? variantCombinations.filter(attrs => !excludedCombos[combinationKey(attrs)]) : variantCombinations, [chosenAttributes, variantCombinations, excludedCombos]);
  const setComboIncluded = (attrs, included) => setExcludedCombos(old => { const next = { ...old }; if (included) delete next[combinationKey(attrs)]; else next[combinationKey(attrs)] = true; return next; });
  const setAllCombosIncluded = included => setExcludedCombos(included ? {} : Object.fromEntries(variantCombinations.map(attrs => [combinationKey(attrs), true])));

  // One source of truth for variant prices, shared by the General and Attributes tabs.
  const existingByKey = attrs => existingVariants.find(row => combinationKey(row.attributes || {}) === combinationKey(attrs));
  const singleNewCombo = !product?.id && chosenAttributes.length > 0 && includedCombinations.length === 1;
  const priceField = (attrs, field) => {
    const key = combinationKey(attrs);
    const existing = existingByKey(attrs);
    if (existing && multiVariantEdit) return variantPriceEdits[existing.id]?.[field] ?? "";
    if (existing && soleVariant) return field === "cost_price" ? (variantPriceEdits[existing.id]?.cost_price ?? "") : (form[field] ?? "");
    if (singleNewCombo && field !== "cost_price") return form[field] ?? "";
    const override = variantPricing[key]?.[field];
    return override !== undefined ? override : (field === "cost_price" ? "" : (form[field] ?? ""));
  };
  const setPriceField = (attrs, field, value) => {
    const key = combinationKey(attrs);
    const existing = existingByKey(attrs);
    if (existing && multiVariantEdit) return setVariantPrice(existing.id, field, value);
    if (existing && soleVariant) return field === "cost_price" ? setVariantPrice(existing.id, field, value) : change(field, value);
    if (singleNewCombo && field !== "cost_price") return change(field, value);
    setVariantPricing(old => ({ ...old, [key]: { ...(old[key] || {}), [field]: value } }));
  };
  const rowFor = attrs => ({ selling_price: priceField(attrs, "selling_price"), mrp: priceField(attrs, "mrp"), cost_price: priceField(attrs, "cost_price") });

  const reorderValue = (def, value, direction) => setValueOrder(old => ({ ...old, [def.code]: moveValue(orderByList(selected[def.code] || [], old[def.code] || []), value, direction) }));
  const autoSortValues = def => setValueOrder(old => ({ ...old, [def.code]: sortValuesLowToHigh(selected[def.code] || []) }));

  function toggleValue(def, value) {
    setSelected(old => {
      const values = old[def.code] || [];
      return { ...old, [def.code]: values.includes(value) ? values.filter(item => item !== value) : [...values, value] };
    });
  }

  async function addOption(def, colourOption = null, imageOption = null) {
    const raw = def.value_type === "colour" ? colourOption : (imageOption != null ? { name: String(imageOption.name || "").trim(), image: String(imageOption.image || "").trim() } : (newOptions[def.code] || "").trim());
    if (!raw || (def.value_type === "image" && (!raw.name || !raw.image))) return;
    const existing = customAttributeOptions[def.id] || [];
    const label = def.value_type === "colour" ? colourOptionLabel(raw) : def.value_type === "image" ? raw.name : String(raw).trim();
    const duplicate = [...(def.options || []), ...existing].some(option => {
      if (def.value_type === "image") {
        const current = normalizeImageOption(option);
        // Names may repeat (several "Black" designs); only the same image counts as a duplicate.
        return Boolean(current.image && current.image === raw.image);
      }
      if (def.value_type === "colour") {
        const current = normalizeColourOption(option);
        const candidate = normalizeColourOption(raw);
        return current.name.toLowerCase() === candidate.name.toLowerCase() || (current.hex && current.hex.toUpperCase() === candidate.hex.toUpperCase());
      }
      return String(option).trim().toLowerCase() === label.toLowerCase();
    });
    if (duplicate) throw new Error(def.value_type === "image" ? "This image already exists for this attribute. Choose a different image." : "This value already exists for the selected attribute. Choose a different value.");
    setCustomAttributeOptions(old => ({ ...old, [def.id]: [...(old[def.id] || []), raw] }));
    setPendingCustomOptions(old => ({ ...old, [def.id]: [...(old[def.id] || []), raw] }));
    // A value that shares a name with an earlier one is stored by its image link, so tick that, not the bare name.
    const selectValue = def.value_type === "image"
      ? (normalizeImageOptions(combineImageOptions(def.options, existing, [raw])).find(item => item.image === raw.image)?.value || label)
      : label;
    setSelected(old => {
      const current = old[def.code] || [];
      return current.some(value => String(value).toLowerCase() === String(selectValue).toLowerCase())
        ? old
        : { ...old, [def.code]: [...current, selectValue] };
    });
    setNewOptions(old => ({ ...old, [def.code]: "" }));
  }

  // Shared + product-specific values for one attribute. Image values are listed once per picture.
  const optionsFor = def => def.value_type === "image"
    ? combineImageOptions(def.options, customAttributeOptions[def.id])
    : [...(def.options || []), ...(customAttributeOptions[def.id] || [])];

  // Edit one Image value (fix its name or replace its picture). A saved value is changed on the shared attribute
  // and keeps every product and variant that uses it; a value added but not yet saved is only changed here.
  async function saveImageValue(def, target, edits) {
    const sameImage = option => normalizeImageOption(option).image === target.image;
    const all = optionsFor(def);
    if (edits.image !== target.image && all.some(option => normalizeImageOption(option).image === edits.image)) {
      throw new Error("This picture is already used by another value in this attribute.");
    }
    const before = normalizeImageOptions(all);
    const savedShared = (def.options || []).some(sameImage);
    if (savedShared) {
      await apiRequest("/catalogue/attributes/" + def.id + "/image-values", {
        method: "PATCH",
        body: JSON.stringify({ image: target.image, name: edits.name, new_image: edits.image !== target.image ? edits.image : undefined }),
      });
    }
    const replace = list => (list || []).map(option => sameImage(option) ? { name: edits.name, image: edits.image } : option);
    const nextCustom = replace(customAttributeOptions[def.id]);
    const after = normalizeImageOptions(combineImageOptions(replace(def.options), nextCustom));
    // Work out which saved values changed form, so ticked boxes and the display order follow the edit.
    const moved = {};
    before.forEach((item, i) => {
      if (after[i] && after[i].value !== item.value) {
        moved[item.value] = after[i].value;
        if (item.image && item.image !== item.value) moved[item.image] = after[i].value;
      }
    });
    const remap = state => state[def.code] ? { ...state, [def.code]: [...new Set(state[def.code].map(value => moved[value] ?? value))] } : state;
    setSelected(remap);
    setValueOrder(remap);
    setCustomAttributeOptions(old => ({ ...old, [def.id]: nextCustom }));
    setPendingCustomOptions(old => old[def.id] ? { ...old, [def.id]: replace(old[def.id]) } : old);
    setEditingImage(null);
    if (savedShared) await loadDefinitions();
  }

  async function submit(event) {
    event.preventDefault();
    setBusy(true); setError(""); setSuccess("");
    onBusyChange?.(true);
    let savedProduct = null;
    try {
      if (!form.name.trim()) throw new Error("Product name is required.");
      if (!form.slug.trim()) throw new Error("Product slug could not be generated. Enter a valid product name.");
      const price = Number(form.selling_price);
      const mrp = Number(form.mrp);
      if ((!product?.id || chosenAttributes.length) && !multiVariantEdit && (!Number.isFinite(price) || !Number.isFinite(mrp) || form.selling_price === "" || form.mrp === "" || price < 0 || mrp < price)) {
        setActiveTab("general");
        throw new Error("Enter a valid selling price and an MRP equal to or higher than the selling price before creating variants.");
      }
      if (chosenAttributes.length && !includedCombinations.length) {
        setActiveTab("attributes");
        throw new Error("Keep at least one variant visible. Tick at least one combination.");
      }
      for (const attrs of includedCombinations) {
        if (existingByKey(attrs)) continue; // existing variants are validated with their own price rows
        const row = rowFor(attrs);
        const variantPrice = row.selling_price === undefined || row.selling_price === "" ? price : Number(row.selling_price);
        const variantMrp = row.mrp === undefined || row.mrp === "" ? mrp : Number(row.mrp);
        const variantCost = row.cost_price === undefined || row.cost_price === "" ? null : Number(row.cost_price);
        if ((!product?.id || chosenAttributes.length) && (!Number.isFinite(variantPrice) || !Number.isFinite(variantMrp) || variantPrice < 0 || variantMrp < variantPrice || (variantCost !== null && (!Number.isFinite(variantCost) || variantCost < 0)))) {
          setActiveTab("attributes");
          throw new Error("Check each variant's selling price, MRP and cost price. MRP must be at least the selling price.");
        }
      }
      if (multiVariantEdit) {
        for (const item of changedVariantPrices()) {
          if (!Number.isFinite(item.selling) || item.selling < 0 || !Number.isFinite(item.mrp) || item.mrp < item.selling || (item.cost !== null && (!Number.isFinite(item.cost) || item.cost < 0))) {
            setActiveTab("general");
            throw new Error("Check the price of " + variantLabel(item.row) + ". Selling price is required and MRP must be at least the selling price.");
          }
        }
      }
      if (soleVariant && (form.selling_price === "" || form.mrp === "" || !Number.isFinite(price) || !Number.isFinite(mrp) || price < 0 || mrp < price)) {
        setActiveTab("general");
        throw new Error("Enter a valid selling price and an MRP equal to or higher than the selling price.");
      }
      if (form.tax_code && !isValidHsn(form.tax_code)) {
        setActiveTab("general");
        throw new Error("HSN code must be exactly 8 digits (numbers only).");
      }
      const categoryIds = [...new Set((form.category_ids || []).map(Number).filter(id => Number.isInteger(id) && id > 0))];
      if (!categoryIds.length) {
        setActiveTab("general");
        throw new Error("Select at least one category for this product.");
      }
      const payload = { name: form.name.trim(), slug: form.slug, brand: form.brand || null, category_id: categoryIds[0] || null, category_ids: categoryIds, description: form.description || null, tax_code: form.tax_code || null, tax_rate: form.tax_rate === "" ? null : Number(form.tax_rate), is_pos_available: Boolean(form.is_pos_available), is_website_available: Boolean(form.is_website_available), delivery_options: form.delivery_options?.length ? form.delivery_options : ["standard"], status: product?.status || "active" };
      const variantPayloads = product?.id && !chosenAttributes.length ? [] : includedCombinations.map(attrs => {
        const existing = existingByKey(attrs);
        if (existing) return { attributes: attrs, selling_price: Number(existing.selling_price), mrp: Number(existing.mrp ?? existing.selling_price), cost_price: existing.cost_price == null ? null : Number(existing.cost_price) };
        const row = rowFor(attrs);
        const variantPrice = row.selling_price === undefined || row.selling_price === "" ? price : Number(row.selling_price);
        const variantMrp = row.mrp === undefined || row.mrp === "" ? mrp : Number(row.mrp);
        const variantCost = row.cost_price === undefined || row.cost_price === "" ? null : Number(row.cost_price);
        return { attributes: attrs, selling_price: variantPrice, mrp: variantMrp, cost_price: variantCost };
      });
      const completePayload = buildCompleteProductPayload({
        product: payload,
        productAttributes: productAttributeValues,
        customOptions: pendingCustomOptions,
        variants: variantPayloads,
        availabilityRules: (product?.id || duplicateFrom) ? availabilityRules.map(rule => ({
          channel: rule.channel, region_code: rule.region_code || null, pincode: rule.pincode || null,
          location_id: rule.location_id ? Number(rule.location_id) : null, is_allowed: rule.is_allowed !== false,
        })) : [],
      });
      savedProduct = await apiRequest(
        product?.id ? "/catalogue/products/" + product.id + "/complete" : "/catalogue/products/complete",
        { method: product?.id ? "PUT" : "POST", body: JSON.stringify(completePayload) },
      );
      try {
        const orderCodes = definitions.filter(def => def.is_variant_attribute && (selected[def.code] || []).length > 1).map(def => def.code);
        if (orderCodes.length) {
          const saved = await apiRequest("/catalogue/products/" + savedProduct.id + "/variants?limit=500");
          const active = (saved.items || []).filter(item => item.is_active !== false);
          if (active.length > 1) {
            await apiRequest("/catalogue/products/" + savedProduct.id + "/variants/order", { method: "PUT", body: JSON.stringify({ variant_ids: variantIdsInOrder(active, orderCodes, valueOrder) }) });
          }
        }
      } catch (orderError) {
        setError("Product saved, but the option order could not be saved: " + (orderError.message || "unknown error") + " Open the product and save again to retry.");
      }
      const soleCostRaw = soleVariant ? variantPriceEdits[soleVariant.id]?.cost_price : undefined;
      const soleCost = soleCostRaw === undefined ? (soleVariant?.cost_price == null ? null : Number(soleVariant.cost_price)) : (soleCostRaw === "" ? null : Number(soleCostRaw));
      const soleCostBefore = soleVariant?.cost_price == null ? null : Number(soleVariant.cost_price);
      if (soleVariant && (Number(soleVariant.selling_price) !== price || Number(soleVariant.mrp) !== mrp || soleCost !== soleCostBefore)) {
        if (soleCost !== null && (!Number.isFinite(soleCost) || soleCost < 0)) throw new Error("Cost price must be a valid number.");
        await apiRequest("/catalogue/variants/" + soleVariant.id + "/price", {
          method: "PUT",
          body: JSON.stringify({ selling_price: price, mrp, cost_price: soleCost }),
        });
      }
      if (multiVariantEdit) {
        for (const item of changedVariantPrices()) {
          const before = item.row;
          const unchanged = Number(before.selling_price) === item.selling && Number(before.mrp ?? before.selling_price) === item.mrp && (before.cost_price == null ? null : Number(before.cost_price)) === item.cost;
          if (unchanged) continue;
          await apiRequest("/catalogue/variants/" + before.id + "/price", {
            method: "PUT",
            body: JSON.stringify({ selling_price: item.selling, mrp: item.mrp, cost_price: item.cost }),
          });
        }
      }
      setSuccess(product?.id
        ? (savedProduct.created_variant_count ? "Product updated and " + savedProduct.created_variant_count + " new variant(s) added. Existing variants were preserved." : "Product details saved atomically. Existing variants were preserved; no duplicate variants were created.")
        : "Product saved atomically with " + (savedProduct.created_variant_count ?? variantPayloads.length) + " variant(s) and default prices.");
      loadDefinitions().catch(() => {});
      await onSaved?.(savedProduct);
    } catch (e) {
      setError((e.message || "Unable to save product.") + (savedProduct
        ? " The product transaction committed, but the follow-up catalogue refresh failed. Refresh the product list before retrying."
        : " Product, supported attributes, custom options, variants and availability are saved in one transaction; a failed save request rolls back the complete change."));
    } finally { setBusy(false); onBusyChange?.(false); }
  }

    return <form id="catalogue-product-form" className="sb-form sb-modal-form" noValidate onSubmit={submit}>
    {error && <p role="alert" className="sb-alert">{error}</p>}
    {success && <p role="status" className="sb-success">{success}</p>}
    <nav className="sb-catalogue-tabs sb-form-tabs" aria-label="Product form sections" role="tablist">
      {[["general","Product"],["attributes","Variants"],["availability","Availability"],["delivery","Delivery"],["images","Images"],["review","Review"]].map(([key,label]) => <button key={key} type="button" role="tab" aria-selected={activeTab === key} className={activeTab === key ? "is-active" : ""} onClick={() => setActiveTab(key)}>{label}</button>)}
    </nav>
    <section hidden={activeTab !== "general"} aria-label="Product information">
      {duplicateFrom && !product?.id && <p className="sb-success" role="status">Duplicating <b>{duplicateFrom.name}</b>. Details, categories, prices, variants and availability are copied. Change the name, brand or anything else, then save. Images, SKUs, barcodes and stock are not copied.</p>}
      <div className="sb-form-grid">
        <label>Product name *<input required maxLength="240" value={form.name} onChange={e => { const name=e.target.value; setForm(old => ({...old,name,slug:slugify(name)})); }} /></label>
        <label>Slug (automatic)<input required pattern="[a-z0-9]+(-[a-z0-9]+)*" value={form.slug} readOnly aria-readonly="true" /></label>
        <label>Brand<input maxLength="160" value={form.brand || ""} onChange={e => change("brand", e.target.value)} /></label>
        <fieldset className="sb-span-all sb-category-multiselect"><legend>Categories * <small>Select every category where this product should appear.</small></legend><div className="sb-category-checkbox-grid">{categories.map(item => <label className="sb-check" key={item.id}><input type="checkbox" checked={(form.category_ids || []).includes(String(item.id))} onChange={e => { const id=String(item.id); const ids=form.category_ids || []; const next=e.target.checked ? [...new Set([...ids,id])] : ids.filter(value => value !== id); setForm(old => ({...old,category_ids:next,category_id:next[0] || ""})); }} />{item.parent_id ? "↳ " : ""}{item.name}</label>)}</div></fieldset>
        <div className="sb-span-all"><h3>Price &amp; Tax</h3></div>
        {!multiVariantEdit && <>
          <label>Selling price (₹) *<input required={!product?.id || Boolean(soleVariant)} type="number" min="0" step="0.01" value={form.selling_price} onChange={e => change("selling_price", e.target.value)} /></label>
          <label>MRP (₹) *<input required={!product?.id || Boolean(soleVariant)} type="number" min="0" step="0.01" value={form.mrp} onChange={e => change("mrp", e.target.value)} /></label>
        </>}
        {!multiVariantEdit && !product?.id && includedCombinations.length > 1 && <p className="sb-span-all sb-muted">These prices are the default for all {includedCombinations.length} variants. You can set a different price for any variant in the Attributes &amp; variants tab; changes made there also appear in that tab&apos;s list.</p>}
        {multiVariantEdit && <div className="sb-span-all sb-variant-price-edit">
          <p className="sb-muted">This product has {existingVariants.length} variants. Change the price of any variant below, then save the product. Leave MRP empty to use the selling price.</p>
          <div className="sb-bulk-price">
            <label>Selling price for all (₹)<input type="number" min="0" step="0.01" inputMode="decimal" value={bulkPrice.selling_price} onChange={e => setBulkPrice(old => ({ ...old, selling_price: e.target.value }))} /></label>
            <label>MRP for all (₹)<input type="number" min="0" step="0.01" inputMode="decimal" value={bulkPrice.mrp} onChange={e => setBulkPrice(old => ({ ...old, mrp: e.target.value }))} /></label>
            <button type="button" className="sb-secondary" onClick={applyBulkPrice}>Apply to all variants</button>
          </div>
          {existingVariants.map(row => {
            const edit = variantPriceEdits[row.id] || {};
            return <div className="sb-variant-price-row" key={row.id}>
              <strong>{variantLabel(row)}</strong>
              <label>Selling (₹)<input type="number" min="0" step="0.01" inputMode="decimal" value={edit.selling_price ?? ""} onChange={e => setVariantPrice(row.id, "selling_price", e.target.value)} /></label>
              <label>MRP (₹)<input type="number" min="0" step="0.01" inputMode="decimal" value={edit.mrp ?? ""} placeholder="Same as selling" onChange={e => setVariantPrice(row.id, "mrp", e.target.value)} /></label>
              <label>Cost (₹)<input type="number" min="0" step="0.01" inputMode="decimal" value={edit.cost_price ?? ""} onChange={e => setVariantPrice(row.id, "cost_price", e.target.value)} /></label>
            </div>;
          })}
        </div>}
        <label>HSN code (8 digits)<input maxLength="8" inputMode="numeric" pattern="[0-9]{8}" value={form.tax_code || ""} onChange={e => { setTaxManual(true); change("tax_code", cleanHsn(e.target.value)); }} placeholder="Auto-filled from HSN rules, or enter 8 digits" /></label>
        <label>GST rate<select value={form.tax_rate ?? ""} onChange={e => { setTaxManual(true); change("tax_rate", e.target.value); }}><option value="">Select GST rate</option>{["0","0.1","0.25","1","1.5","3","5","6","7.5","12","18","28","40"].map(rate => <option key={rate} value={rate}>{rate}%</option>)}</select></label>
        <div className="sb-span-all">
          {hsnSuggestion && hsnMatchesForm && <small className="sb-muted">Auto-filled from an HSN rule{hsnSuggestion.note ? " (" + hsnSuggestion.note + ")" : ""}. You can still change it.</small>}
          {hsnSuggestion && !hsnMatchesForm && <small className="sb-muted">An HSN rule suggests {hsnSuggestion.hsn_code} at {Number(hsnSuggestion.gst_rate)}% GST. <button type="button" className="sb-secondary" onClick={() => { setTaxManual(false); setForm(old => ({ ...old, tax_code: hsnSuggestion.hsn_code, tax_rate: String(Number(hsnSuggestion.gst_rate)) })); }}>Use suggestion</button></small>}
          {!hsnSuggestion && !form.tax_code && (form.category_ids || []).length > 0 && <small className="sb-muted">No HSN rule matches yet. Enter the 8-digit HSN, or add a rule in Catalogue → HSN rules.</small>}
        </div>
        <label className="sb-span-all">Product description<textarea rows="4" value={form.description || ""} onChange={e => change("description", e.target.value)} placeholder="Features, material, fit, usage and care instructions" /></label>
      </div>
      <button type="button" className="sb-secondary sb-step-next" onClick={() => { if (!form.name.trim() || !form.slug.trim() || (!product?.id && (form.selling_price === "" || form.mrp === "" || Number(form.selling_price) < 0 || Number(form.mrp) < Number(form.selling_price)))) { setError("Complete product name, selling price and valid MRP before continuing."); return; } setError(""); setActiveTab("attributes"); }}>Continue to Attributes &amp; Variants</button>
    </section>
    <section hidden={activeTab !== "availability"} aria-label="Availability">
      <h3>Sales channels</h3>
      <label className="sb-check"><input type="checkbox" checked={Boolean(form.is_pos_available)} onChange={e=>change("is_pos_available",e.target.checked)}/> Available in POS</label>
      <label className="sb-check"><input type="checkbox" checked={Boolean(form.is_website_available)} onChange={e=>change("is_website_available",e.target.checked)}/> Available on Website</label>
      <h3>Region, pincode and warehouse restrictions</h3>
      {product?.id ? <>
        <p className="sb-muted">Restrictions are saved for this product. Each rule can target POS or Website and must specify a state/district/region, six-digit pincode, or warehouse. With no rules the product sells everywhere. If you add Allow rules, the product sells ONLY in those areas; Block rules always hide it in their area. Website customers outside the allowed area see it as unavailable and cannot order it.</p>
        <div className="sb-form-grid">
          <label>Channel<select value={ruleDraft.channel} onChange={e=>setRuleDraft(v=>({...v,channel:e.target.value}))}><option value="website">Website</option><option value="pos">POS</option></select></label>
          <label>State, district or region code (optional)<input value={ruleDraft.region_code} onChange={e=>setRuleDraft(v=>({...v,region_code:e.target.value}))} placeholder="e.g. Jharkhand, Palamu or IN-JH"/></label>
          <label>Pincode (optional)<input inputMode="numeric" maxLength="6" pattern="[0-9]{6}" value={ruleDraft.pincode} onChange={e=>setRuleDraft(v=>({...v,pincode:e.target.value.replace(/\D/g,"")}))} placeholder="6-digit pincode"/></label>
          <label>Warehouse / store (optional)<select value={ruleDraft.location_id} onChange={e=>setRuleDraft(v=>({...v,location_id:e.target.value}))}><option value="">No location restriction</option>{stockLocations.map(location=><option key={location.id} value={location.id}>{location.name} · {location.location_type}{location.pin_code ? " · "+location.pin_code : ""} · #{location.id}</option>)}</select></label>
          <label>Restriction effect<select value={ruleDraft.is_allowed ? "allow" : "block"} onChange={e=>setRuleDraft(v=>({...v,is_allowed:e.target.value==="allow"}))}><option value="allow">Allow availability</option><option value="block">Block availability</option></select></label>
        </div>
        <button type="button" className="sb-secondary" onClick={()=>{if(!ruleDraft.region_code.trim()&&!ruleDraft.pincode&&!ruleDraft.location_id){setError("Enter a region, pincode or stock location ID.");return;} if(ruleDraft.pincode&& !/^\d{6}$/.test(ruleDraft.pincode)){setError("Pincode must contain exactly six digits.");return;} setAvailabilityRules(old=>[...old,{...ruleDraft,region_code:ruleDraft.region_code.trim(),pincode:ruleDraft.pincode||"",location_id:ruleDraft.location_id||"",id:"new-"+Date.now()}]);setRuleDraft(v=>({...v,region_code:"",pincode:"",location_id:""}));setError("");}}>Add restriction</button>
        {availabilityRules.length ? <div className="sb-strip-list">{availabilityRules.map((rule,index)=><article className="sb-strip-row" key={rule.id || index}><div className="sb-strip-main"><strong>{rule.channel.toUpperCase()} · {rule.is_allowed===false?"Blocked":"Allowed"}</strong><small>{[rule.region_code,rule.pincode,rule.location_id?"Location #"+rule.location_id:""].filter(Boolean).join(" · ")}</small></div><button type="button" className="sb-row-action" onClick={()=>setAvailabilityRules(old=>old.filter((_,i)=>i!==index))}>Remove</button></article>)}</div>:<p className="sb-empty">No region, pincode or warehouse restrictions configured.</p>}
      </> : <p className="sb-muted">Save the product first to attach region, pincode and warehouse restrictions. Channel availability can be selected now and will be saved with the product.</p>}
      <button type="button" className="sb-secondary sb-step-next" onClick={()=>setActiveTab("delivery")}>Continue to Delivery</button>
    </section>
    <section hidden={activeTab !== "delivery"} aria-label="Delivery options">
      <h3>Delivery options</h3>
      <p className="sb-muted">Select the delivery methods customers can choose for this product.</p>
      {["standard","express"].map(option=><label className="sb-check" key={option}><input type="checkbox" checked={(form.delivery_options||["standard"]).includes(option)} onChange={e=>change("delivery_options",e.target.checked?[...(form.delivery_options||[]).filter(x=>x!==option),option]:(form.delivery_options||[]).filter(x=>x!==option))}/>{option==="standard"?"Standard delivery":"Express delivery"}</label>)}
      {!(form.delivery_options||[]).length && <p role="alert" className="sb-alert">Choose at least one delivery option.</p>}
      <button type="button" className="sb-secondary sb-step-next" onClick={()=>setActiveTab("images")}>Continue to Images</button>
    </section>
    <section hidden={activeTab !== "images"} aria-label="Product images">
      {product?.id ? <ProductImagesEmbedded product={product} /> : <p className="sb-muted">Save the product and its variants first. Then reopen Edit Product to add product-level and variant-specific image references.</p>}
      <button type="button" className="sb-secondary sb-step-next" onClick={()=>setActiveTab("review")}>Continue to Review &amp; Save</button>
    </section>
    <section hidden={activeTab !== "review"} aria-label="Review and save">
      <h3>Review product</h3>
      <p className="sb-muted">Check the details, then tap the Save button at the bottom.</p>
      <div className="sb-form-grid">
        <p><strong>Product:</strong> {form.name || "Not entered"}</p>
        <p><strong>Slug:</strong> {form.slug || "Not generated"}</p>
        <p><strong>Selling price:</strong> ₹{form.selling_price || "—"}</p>
        <p><strong>MRP:</strong> ₹{form.mrp || "—"}</p>
        <p><strong>POS:</strong> {form.is_pos_available ? "Available" : "Unavailable"}</p>
        <p><strong>Website:</strong> {form.is_website_available ? "Available" : "Unavailable"}</p>
        <p><strong>Delivery:</strong> {(form.delivery_options||[]).join(", ") || "Choose at least one option"}</p>
        <p><strong>Variants to create:</strong> {product?.id ? "Existing variants preserved" : includedCombinations.length}</p>
      </div>
      <div className="sb-product-actions"><button className="sb-secondary" type="button" disabled={busy} onClick={() => setActiveTab("general")}>Back to Product Information</button></div>
    </section>
    <section hidden={activeTab !== "attributes"} aria-label="Attributes and variants">
      {product?.id && <p className="sb-muted">Existing variants are preserved. Select additional values below to add only missing combinations; existing variants will not be duplicated.</p>}
      <>
        <p className="sb-muted">Choose reusable attribute values. Each generated variant gets its own selling price, MRP and cost; the product-level prices are defaults that prefill each row.</p>
        <section className="sb-product-attributes">
          <h3>Attributes and variants</h3>
          {definitions.filter(def => def.is_variant_attribute).map(def => <div className="sb-attribute-picker" key={def.id}>
            <strong>{def.name}</strong><small className="sb-muted">{def.value_type}{def.is_variant_attribute ? " · Variant attribute" : ""}{def.is_required ? " · Required" : ""}</small>
            {def.value_type === "text" && !(def.options || []).length ?
              <input value={(selected[def.code] || [])[0] || ""} placeholder={"Enter " + def.name.toLowerCase()} onChange={e => setSelected(old => ({ ...old, [def.code]: e.target.value ? [e.target.value] : [] }))} /> :
              OPTION_TYPES.includes(def.value_type) ? <><div className="sb-option-chips">{(def.value_type === "text" ? [...new Set([...(def.options || []), ...(customAttributeOptions[def.id] || []), ...(selected[def.code] || [])])] : optionsFor(def)).map((value, optionIndex, allOptions) => { const imageItem = def.value_type === "image" ? normalizeImageOptions(allOptions)[optionIndex] : null; const optionValue = def.value_type === "colour" ? colourOptionLabel(value) : imageItem ? imageItem.value : value; return <label className="sb-option-chip" key={String(optionValue)}>{def.value_type === "colour" && <i className="sb-colour-swatch" style={{backgroundColor:normalizeColourOption(value).hex || "#999"}} />}<input type="checkbox" checked={(selected[def.code] || []).includes(optionValue)} onChange={() => toggleValue(def, optionValue)} />{imageItem && imageItem.image && <img className="sb-image-thumb" src={imageItem.image} alt="" />}{imageItem ? imageItem.name : String(optionValue)}{imageItem && <button type="button" className="sb-row-action" disabled={busy} aria-label={"Edit " + imageItem.name} title="Edit name or picture" onClick={e => { e.preventDefault(); e.stopPropagation(); setEditingImage({ defId: def.id, image: imageItem.image, name: imageItem.name }); }}>✎</button>}</label>; })}</div>{editingImage && editingImage.defId === def.id && <ImageValueEditor key={editingImage.image} option={{ name: editingImage.name, image: editingImage.image }} disabled={busy} note={(def.options || []).some(option => normalizeImageOption(option).image === editingImage.image) ? "Changes apply everywhere this value is used (all products and the storefront)." : ""} onCancel={() => setEditingImage(null)} onSave={edits => saveImageValue(def, editingImage, edits)} />}</> :
              <input value={(selected[def.code] || [])[0] || ""} placeholder={"Enter " + def.name.toLowerCase()} onChange={e => setSelected(old => ({ ...old, [def.code]: e.target.value ? [e.target.value] : [] }))} />}
            {def.value_type === "colour" ? <ColourOptionEditor existingOptions={[...(def.options || []), ...(customAttributeOptions[def.id] || [])]} disabled={busy} compact onAdd={option => addOption(def, option)} /> :
              def.value_type === "image" ? <ImageOptionEditor disabled={busy} onAdd={option => addOption(def, null, option)} /> : OPTION_TYPES.includes(def.value_type) && <div className="sb-add-option"><input aria-label={"New " + def.name + " option"} value={newOptions[def.code] || ""} placeholder={"Add new " + def.name.toLowerCase() + " option"} onChange={e => setNewOptions(old => ({ ...old, [def.code]: e.target.value }))} /><button type="button" className="sb-secondary" disabled={busy || !(newOptions[def.code] || "").trim()} onClick={() => addOption(def).catch(e => setError(e.message || "Unable to add option."))}>Add value</button></div>}
            {OPTION_TYPES.includes(def.value_type) && (selected[def.code] || []).length > 1 && <div className="sb-value-order" aria-label={def.name + " display order"}>
              <div className="sb-value-order-head"><small className="sb-muted">Storefront order for {def.name}</small><button type="button" className="sb-secondary" disabled={busy} onClick={() => autoSortValues(def)}>Sort low to high</button></div>
              <ol>{orderByList(selected[def.code] || [], valueOrder[def.code] || []).map((value, i, list) => <li key={String(value)}>
                <span>{def.value_type === "colour" ? colourOptionLabel(value) : def.value_type === "image" ? resolveImageValue(value, optionsFor(def)).name : String(value)}</span>
                <span className="sb-value-order-actions">
                  <button type="button" className="sb-secondary" aria-label={"Move " + String(value) + " up"} disabled={busy || i === 0} onClick={() => reorderValue(def, value, -1)}>▲</button>
                  <button type="button" className="sb-secondary" aria-label={"Move " + String(value) + " down"} disabled={busy || i === list.length - 1} onClick={() => reorderValue(def, value, 1)}>▼</button>
                </span>
              </li>)}</ol>
            </div>}
          </div>)}
          {definitions.filter(def => def.is_variant_attribute && !OPTION_TYPES.includes(def.value_type) && selected[def.code]?.length).map(def => <p className="sb-muted" key={def.id}>{def.name} · Legacy attribute (read-only): {(selected[def.code] || []).join(", ")}. Existing variant values will be preserved.</p>)}
          {definitions.some(def => !def.is_variant_attribute && OPTION_TYPES.includes(def.value_type)) && <div className="sb-product-attributes"><h3>Product-level attributes</h3>{definitions.filter(def => !def.is_variant_attribute && OPTION_TYPES.includes(def.value_type)).map(def => { const options = optionsFor(def); const current = productAttributeValues[def.id] ?? ""; const displayValue = typeof current === "string" ? current : current == null ? "" : JSON.stringify(current); return <label className="sb-attribute-picker" key={def.id}><strong>{def.name}</strong><small className="sb-muted">{def.value_type} · Product attribute{def.is_required ? " · Required" : ""}</small>{def.value_type === "text" ? <input value={displayValue} placeholder={"Enter " + def.name.toLowerCase()} onChange={e => setProductAttributeValues(old => ({ ...old, [def.id]: e.target.value }))} /> : <select value={displayValue} onChange={e => setProductAttributeValues(old => ({ ...old, [def.id]: e.target.value }))}><option value="">Select {def.name.toLowerCase()}</option>{options.map((option, optionIndex) => { const image = def.value_type === "image" ? normalizeImageOptions(options)[optionIndex] : null; const value = def.value_type === "colour" ? colourOptionLabel(option) : image ? image.value : String(option); return <option key={value} value={value}>{image ? image.name : value}</option>; })}</select>}</label>; })}</div>}
          {!definitions.length && <p className="sb-empty">Create an attribute in the Attributes tab first, or continue with a product that has no variants.</p>}
          <p className="sb-muted">This product will have {includedCombinations.length} of {variantCombinations.length} possible variant(s). Untick a combination that does not exist (for example 1 kg in a can) to hide it. Hidden combinations are not sold or shown in the shop. Prices below are stored on each variant, not on the reusable attribute definition.</p>
          {chosenAttributes.length > 0 && variantCombinations.length > 1 && <div className="sb-combo-tools">
            <button type="button" className="sb-row-action" disabled={busy} onClick={() => setAllCombosIncluded(true)}>Show all</button>
            <button type="button" className="sb-row-action" disabled={busy} onClick={() => setAllCombosIncluded(false)}>Hide all</button>
          </div>}
          {chosenAttributes.length === 2 && <div className="sb-combo-matrix-wrap"><table className="sb-combo-matrix" aria-label="Choose which combinations are available">
            <thead><tr><th>{chosenAttributes[0].name} \ {chosenAttributes[1].name}</th>{orderByList(selected[chosenAttributes[1].code] || [], valueOrder[chosenAttributes[1].code] || []).map(b => <th key={String(b)}>{String(b)}</th>)}</tr></thead>
            <tbody>{orderByList(selected[chosenAttributes[0].code] || [], valueOrder[chosenAttributes[0].code] || []).map(a => <tr key={String(a)}><th scope="row">{String(a)}</th>{orderByList(selected[chosenAttributes[1].code] || [], valueOrder[chosenAttributes[1].code] || []).map(b => {
              const attrs = { [chosenAttributes[0].code]: a, [chosenAttributes[1].code]: b };
              const on = !excludedCombos[combinationKey(attrs)];
              return <td key={String(b)}><input type="checkbox" checked={on} disabled={busy} aria-label={String(a) + " / " + String(b) + (on ? " visible" : " hidden")} onChange={e => setComboIncluded(attrs, e.target.checked)} /></td>;
            })}</tr>)}</tbody>
          </table></div>}
          <div className="sb-variant-pricing-list" aria-label="Variant-specific pricing">
            {variantCombinations.map((attrs, index) => {
              const key = combinationKey(attrs);
              const hidden = chosenAttributes.length > 0 && Boolean(excludedCombos[key]);
              const visibleNumber = includedCombinations.indexOf(attrs) + 1;
              const label = Object.entries(attrs).map(([code, value]) => {
                const definition = definitions.find(item => item.code === code);
                return (definition?.name || code) + ": " + (Array.isArray(value) ? value.join(", ") : String(value));
              }).join(" · ") || "Simple product (no selectable options)";
              const row = rowFor(attrs);
              return <article className={"sb-strip-row" + (hidden ? " sb-variant-hidden" : "")} key={key || index}>
                {chosenAttributes.length > 0 && <label className="sb-combo-toggle"><input type="checkbox" checked={!hidden} disabled={busy} onChange={e => setComboIncluded(attrs, e.target.checked)} /> Visible</label>}
                <div className="sb-strip-main"><strong>{label}</strong><small>{hidden ? "Hidden — not sold or shown" : "Variant " + visibleNumber}</small></div>
                <label>Selling price (₹)<input type="number" disabled={hidden} min="0" step="0.01" value={row.selling_price} onChange={e => setPriceField(attrs, "selling_price", e.target.value)}/></label>
                <label>MRP (₹)<input type="number" disabled={hidden} min="0" step="0.01" value={row.mrp} onChange={e => setPriceField(attrs, "mrp", e.target.value)}/></label>
                <label>Cost price (₹)<input type="number" disabled={hidden} min="0" step="0.01" value={row.cost_price} onChange={e => setPriceField(attrs, "cost_price", e.target.value)} placeholder="Optional"/></label>
              </article>;
            })}
          </div>
        </section>
      </>
      <div className="sb-product-actions"><button className="sb-secondary" type="button" disabled={busy} onClick={() => setActiveTab("general")}>Back to Product Information</button><button className="sb-secondary sb-step-next" type="button" disabled={busy} onClick={() => setActiveTab("availability")}>Next: Availability</button></div>
    </section>
  </form>;
}
