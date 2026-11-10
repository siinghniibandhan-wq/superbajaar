export function canWriteAccounting(role) {
  const normalizedRole = String(role || "").trim().toLowerCase();
  return normalizedRole === "super_admin" || normalizedRole === "admin";
}

export function isAccountingSchemaUnavailableError(error) {
  const message = String(error || "").toLowerCase();
  return (
    message.includes("migration 015") ||
    message.includes("accounting storage is not ready") ||
    message.includes("accounting tables are not available") ||
    (message.includes("relation") && message.includes("does not exist")) ||
    message.includes("undefined table") ||
    message.includes("undefined column")
  );
}
