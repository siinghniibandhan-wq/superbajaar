const MODULE_KEYS = Object.freeze({
  dashboard: "dashboard",
  catalogue: "catalogue",
  pricing: "pricing",
  orders: "orders",
  payments: "payments",
  inventory: "inventory",
  purchase: "purchasing",
  fulfilment: "fulfillment",
  delivery: "delivery",
  pos: "pos",
  customers: "crm",
  loyalty: "loyalty",
  accounting: "accounting",
  hr: "hr_payroll",
  reports: "dashboard",
  settings: "user_management",
});

export function canReadPermission(moduleKey, permissions) {
  return Boolean(moduleKey && permissions?.[moduleKey]?.read === true);
}

export function canReadModule(moduleId, permissions) {
  return canReadPermission(MODULE_KEYS[moduleId], permissions);
}

export function filterNavigationGroups(groups, permissions) {
  return groups
    .map(group => ({ ...group, items: group.items.filter(item => canReadModule(item.id, permissions)) }))
    .filter(group => group.items.length > 0);
}
