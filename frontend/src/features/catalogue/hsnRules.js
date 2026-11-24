// HSN/GST rules: category (+ optional product-detail conditions) -> 8-digit HSN and GST rate.

export const GST_RATES = ["0", "0.1", "0.25", "1", "1.5", "3", "5", "6", "7.5", "12", "18", "28", "40"];

export const cleanHsn = value => String(value ?? "").replace(/\D/g, "").slice(0, 8);
export const isValidHsn = value => /^\d{8}$/.test(String(value ?? ""));

const norm = value => String(value ?? "").trim().toLowerCase();

// [self, parent, grandparent, ...] ids for a category, so a rule on a parent also covers its sub-categories.
export function categoryChain(categories = [], categoryId) {
  const byId = new Map(categories.map(item => [String(item.id), item]));
  const chain = [];
  const seen = new Set();
  let current = byId.get(String(categoryId));
  while (current && !seen.has(String(current.id))) {
    chain.push(String(current.id));
    seen.add(String(current.id));
    current = current.parent_id ? byId.get(String(current.parent_id)) : null;
  }
  return chain;
}

export function categoryPath(categories = [], categoryId) {
  const byId = new Map(categories.map(item => [String(item.id), item]));
  return categoryChain(categories, categoryId).reverse().map(id => byId.get(id)?.name).filter(Boolean).join(" > ");
}

// Finds the most specific matching rule.
// ctx = { categoryIds: [..selected product categories..], values: { attributeCode: "value" } }
// More matching conditions beat fewer; a deeper category beats a shallower one; no category is the weakest.
export function matchHsnRule(rules = [], categories = [], ctx = {}) {
  const values = Object.fromEntries(Object.entries(ctx.values || {}).map(([code, value]) => [norm(code), norm(value)]));
  const chains = (ctx.categoryIds || []).map(id => categoryChain(categories, id));
  let best = null;
  let bestScore = null;
  for (const rule of rules) {
    if (rule.is_active === false) continue;
    const conditions = Object.entries(rule.conditions || {});
    if (!conditions.every(([code, wanted]) => values[norm(code)] === norm(wanted))) continue;
    let depth = 0;
    if (rule.category_id != null) {
      const hits = chains.map(chain => chain.indexOf(String(rule.category_id))).filter(i => i !== -1);
      if (!hits.length) continue;
      // Position 0 means the rule is on the product's own category; larger means a more distant ancestor.
      const closest = Math.min(...hits);
      const chainLength = Math.max(...chains.map(chain => chain.length));
      depth = 1 + (chainLength - closest);
    }
    const score = [conditions.length, depth];
    if (!bestScore || score[0] > bestScore[0] || (score[0] === bestScore[0] && score[1] > bestScore[1])) { best = rule; bestScore = score; }
  }
  return best;
}

// Categories (and sub-categories) that have no rule of their own and are not covered by a parent rule.
export function categoriesWithoutRule(categories = [], rules = []) {
  const active = rules.filter(rule => rule.is_active !== false && rule.category_id != null);
  const covered = new Set(active.map(rule => String(rule.category_id)));
  return categories.filter(category => category.is_active !== false && !categoryChain(categories, category.id).some(id => covered.has(id)));
}

// "form=Fresh; packaging=Loose" <-> { form: "Fresh", packaging: "Loose" }
export function parseConditions(text) {
  const result = {};
  for (const part of String(text || "").split(/[;|]/)) {
    const [code, ...rest] = part.split("=");
    const key = String(code || "").trim();
    const value = rest.join("=").trim();
    if (key && value) result[key] = value;
  }
  return result;
}
export const formatConditions = conditions => Object.entries(conditions || {}).map(([code, value]) => code + "=" + value).join("; ");
