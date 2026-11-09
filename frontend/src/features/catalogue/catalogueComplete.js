export function buildCompleteProductPayload({ product, productAttributes = {}, customOptions = {}, variants = [], availabilityRules = [] }) {
  return {
    product,
    product_attributes: Object.fromEntries(Object.entries(productAttributes || {}).map(([id, value]) => [String(Number(id)), value])),
    custom_options: Object.fromEntries(Object.entries(customOptions || {}).map(([id, values]) => [String(Number(id)), Array.isArray(values) ? values : []])),
    variants: Array.isArray(variants) ? variants : [],
    availability_rules: Array.isArray(availabilityRules) ? availabilityRules : [],
  };
}
