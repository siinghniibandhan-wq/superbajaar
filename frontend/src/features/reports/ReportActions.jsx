import { buildMailto, downloadCsv, shareReport } from "./reportActions.js";

export default function ReportActions({ title, filename, rows, summary }) {
  const body = [title, summary || "", "", ...rows.map(row => row.join(" | "))].join("\n");
  const onShare = async () => {
    try {
      const result = await shareReport(title, body);
      if (result === "copied") window.alert("Report summary copied to clipboard.");
    } catch (error) {
      if (error?.name !== "AbortError") window.alert(error?.message || "Unable to share this report.");
    }
  };
  return <div className="sb-report-actions" aria-label="Report actions">
    <button type="button" onClick={() => downloadCsv(filename, rows)}>↓ Download CSV</button>
    <button type="button" onClick={onShare}>↗ Share</button>
    <a href={buildMailto(title, body)}>✉ Email</a>
  </div>;
}
