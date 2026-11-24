const GROUPS = [
  ["onion", "pyaz", "pyaaz", "pyaj", "pyaaj", "piyaz", "kanda", "kaanda"],
  ["tomato", "tamatar", "tamater", "tamatr"],
  ["potato", "aloo", "aalu", "alu", "batata"],
  ["chilli", "chili", "chilly", "mirch", "mirchi"],
  ["ginger", "adrak", "adarak"],
  ["garlic", "lahsun", "lasun", "lehsun", "lasan"],
  ["coriander", "cilantro", "dhaniya", "dhania"],
  ["spinach", "palak"],
  ["cauliflower", "gobi", "gobhi", "phoolgobi"],
  ["cabbage", "bandgobi", "bandhgobi"],
  ["brinjal", "eggplant", "aubergine", "baingan", "baigan", "begun"],
  ["okra", "ladyfinger", "bhindi", "bhendi"],
  ["cucumber", "kheera", "khira", "kakdi", "kakri"],
  ["carrot", "gajar"],
  ["peas", "matar", "mutter", "muttar"],
  ["lemon", "lime", "nimbu", "nimboo"],
  ["banana", "kela"],
  ["apple", "seb"],
  ["mango", "aam"],
  ["milk", "doodh", "dudh"],
  ["curd", "yogurt", "yoghurt", "dahi"],
  ["butter", "makhan", "makkhan"],
  ["rice", "chawal", "chaawal"],
  ["flour", "atta", "aata"],
  ["lentil", "lentils", "dal", "daal", "dhal"],
  ["sugar", "chini", "cheeni", "shakkar"],
  ["salt", "namak"],
  ["oil", "tel"],
  ["tea", "chai", "chay"],
  ["egg", "eggs", "anda", "ande"],
  ["chicken", "murgi", "murga"],
  ["coconut", "nariyal", "narial"],
  ["turmeric", "haldi"],
  ["cumin", "jeera", "zeera", "jira"],
  ["mustard", "sarson", "rai"],
  ["cardamom", "elaichi", "ilaichi"],
  ["clove", "cloves", "laung", "lavang"],
  ["cinnamon", "dalchini"],
  ["gourd", "lauki", "ghiya", "doodhi"],
  ["karela", "bittergourd"],
  ["pumpkin", "kaddu"],
  ["radish", "mooli", "muli"],
  ["beetroot", "beet", "chukandar"],
  ["capsicum", "shimlamirch", "bellpepper"],
  ["fenugreek", "methi"],
  ["mint", "pudina", "pudeena"],
  ["watermelon", "tarbooz", "tarbuj"],
  ["grapes", "grape", "angoor", "angur"],
  ["pomegranate", "anar"],
  ["papaya", "papita"],
  ["guava", "amrood", "amrud"],
  ["orange", "santra", "narangi"],
  ["pineapple", "ananas"],
  ["honey", "shahad", "shehad"],
  ["jaggery", "gud", "gur"],
  ["soap", "sabun"],
  ["paneer", "cottagecheese"],
  ["biscuit", "biscuits", "cookies"],
];

const normalize = value => String(value ?? "")
  .toLowerCase()
  .normalize("NFD").replace(/[\u0300-\u036f]/g, "")
  .replace(/[^a-z0-9]+/g, " ")
  .trim();

const phon = word => word
  .replace(/ph/g, "f").replace(/kh/g, "k").replace(/gh/g, "g").replace(/bh/g, "b")
  .replace(/dh/g, "d").replace(/sh/g, "s")
  .replace(/ee|ii/g, "i").replace(/oo|uu/g, "u")
  .replace(/z/g, "j").replace(/w/g, "v").replace(/q/g, "k").replace(/x/g, "ks")
  .replace(/(.)\1+/g, "$1")
  .replace(/h$/, "");

function lev(a, b, max) {
  if (a === b) return 0;
  if (Math.abs(a.length - b.length) > max) return max + 1;
  let prev = Array.from({ length: b.length + 1 }, (_, i) => i);
  for (let i = 1; i <= a.length; i++) {
    const row = [i];
    let best = i;
    for (let j = 1; j <= b.length; j++) {
      const cost = a[i - 1] === b[j - 1] ? 0 : 1;
      const value = Math.min(prev[j] + 1, row[j - 1] + 1, prev[j - 1] + cost);
      row[j] = value;
      if (value < best) best = value;
    }
    if (best > max) return max + 1;
    prev = row;
  }
  return prev[b.length];
}

const SYNONYMS = new Map();
GROUPS.forEach((group, index) => group.forEach(term => { const key = phon(normalize(term)); if (!SYNONYMS.has(key)) SYNONYMS.set(key, index); }));
const SYNONYM_KEYS = [...SYNONYMS.keys()];

function synonymsFor(token) {
  const key = phon(token);
  let index = SYNONYMS.get(key);
  if (index === undefined && token.length >= 4) {
    const close = SYNONYM_KEYS.find(candidate => candidate[0] === key[0] && Math.abs(candidate.length - key.length) <= 1 && lev(candidate, key, 1) <= 1);
    if (close !== undefined) index = SYNONYMS.get(close);
  }
  return index === undefined ? [] : GROUPS[index].map(normalize).filter(term => term && term !== token);
}

function alternatives(token) {
  const literal = new Set([token]);
  if (token.length > 3 && token.endsWith("es")) literal.add(token.slice(0, -2));
  if (token.length > 3 && token.endsWith("s")) literal.add(token.slice(0, -1));
  const out = [...literal].map(text => ({ text, phon: phon(text), weight: 1 }));
  literal.forEach(text => synonymsFor(text).forEach(term => out.push({ text: term, phon: phon(term), weight: 0.9 })));
  return out;
}

function toField(value, weight) {
  const text = normalize(Array.isArray(value) ? value.join(" ") : value);
  if (!text) return null;
  const words = text.split(" ");
  const phons = words.map(phon);
  return { weight, text, words, phons, phonText: phons.join(" ") };
}

function quality(alt, field) {
  if (alt.text.includes(" ")) {
    if (field.text.includes(alt.text)) return 0.9;
    return field.phonText.includes(alt.phon) ? 0.8 : 0;
  }
  const maxEdits = alt.phon.length >= 8 ? 2 : alt.phon.length >= 4 ? 1 : 0;
  let best = 0;
  for (let i = 0; i < field.words.length; i++) {
    const word = field.words[i];
    const sound = field.phons[i];
    let value = 0;
    if (word === alt.text) value = 1;
    else if (sound === alt.phon) value = 0.92;
    else if (alt.text.length >= 2 && word.startsWith(alt.text)) value = 0.8;
    else if (alt.phon.length >= 3 && sound.startsWith(alt.phon)) value = 0.72;
    else if (alt.text.length >= 3 && word.includes(alt.text)) value = 0.5;
    else if (maxEdits && lev(sound, alt.phon, maxEdits) <= maxEdits) value = 0.45;
    if (value > best) best = value;
    if (best === 1) break;
  }
  return best;
}

export function buildSearchIndex({ products = [], variants = [], categories = [] }) {
  const categoryName = id => categories.find(category => String(category.id) === String(id))?.name || "";
  const variantsByProduct = new Map();
  variants.forEach(variant => {
    if (variant.is_active === false) return;
    const key = Number(variant.product_id);
    if (!variantsByProduct.has(key)) variantsByProduct.set(key, []);
    variantsByProduct.get(key).push(variant);
  });
  const docs = products.map(product => {
    const own = variantsByProduct.get(Number(product.id)) || [];
    const ids = Array.isArray(product.category_ids) ? product.category_ids : [product.category_id];
    const extra = product.tags ?? product.keywords ?? product.search_keywords ?? "";
    const fields = [
      toField([product.name, ...own.map(item => item.product_name)], 10),
      toField(extra, 6),
      toField(product.brand, 4),
      toField([product.category_name, product.category, ...ids.map(categoryName)], 4),
      toField(own.map(item => item.sku), 3),
      toField(product.description, 3),
      toField(own.flatMap(item => Object.values(item.attributes || {}).map(value => Array.isArray(value) ? value.join(" ") : String(value))), 2),
    ].filter(Boolean);
    return { id: Number(product.id), fields };
  });

  function scores(term) {
    const tokens = normalize(term).split(" ").filter(Boolean).slice(0, 6);
    const result = new Map();
    if (!tokens.length) return result;
    const expanded = tokens.map(alternatives);
    const run = requireAll => {
      docs.forEach(doc => {
        let total = 0;
        for (const alts of expanded) {
          let best = 0;
          for (const field of doc.fields) {
            for (const alt of alts) {
              const value = field.weight * alt.weight * quality(alt, field);
              if (value > best) best = value;
            }
          }
          if (best <= 0 && requireAll) { total = 0; break; }
          total += best;
        }
        if (total > 0) result.set(doc.id, requireAll ? total : total * 0.5);
      });
    };
    run(true);
    if (!result.size && tokens.length > 1) run(false);
    return result;
  }

  return { scores };
}
