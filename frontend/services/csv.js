// Client-side CSV download. Cells starting with = + - @ are prefixed so spreadsheets never run them as formulas.
export function downloadCsv(filename, columns, rows) {
  const clean = value => {
    let text = value == null ? "" : String(value);
    if (/^[=+\-@\t\r]/.test(text)) text = "'" + text;
    return /[",\n\r]/.test(text) ? '"' + text.replaceAll('"', '""') + '"' : text;
  };
  const lines = [columns.map(c => clean(c.label)).join(",")];
  rows.forEach(row => lines.push(columns.map(c => clean(typeof c.value === "function" ? c.value(row) : row[c.value])).join(",")));
  const blob = new Blob(["﻿" + lines.join("\r\n")], { type: "text/csv;charset=utf-8" });
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url; link.download = filename;
  document.body.appendChild(link); link.click(); link.remove();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}
