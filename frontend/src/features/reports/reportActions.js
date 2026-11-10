export function buildCsv(rows) {
  const quote = value => '"' + String(value ?? "").replaceAll('"', '""') + '"';
  return rows.map(row => row.map(quote).join(",")).join("\r\n");
}

export function buildMailto(subject, body) {
  return "mailto:?subject=" + encodeURIComponent(subject) + "&body=" + encodeURIComponent(body);
}

export function downloadCsv(filename, rows) {
  const blob = new Blob(["\uFEFF", buildCsv(rows)], { type: "text/csv;charset=utf-8" });
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = filename;
  document.body.appendChild(anchor);
  anchor.click();
  anchor.remove();
  URL.revokeObjectURL(url);
}

export async function shareReport(title, text) {
  if (navigator.share) return navigator.share({ title, text });
  if (navigator.clipboard?.writeText) {
    await navigator.clipboard.writeText(text);
    return "copied";
  }
  throw new Error("Sharing is not supported by this browser");
}
