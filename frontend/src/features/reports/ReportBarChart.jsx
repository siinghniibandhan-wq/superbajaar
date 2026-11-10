export default function ReportBarChart({ title, items = [], labelKey, valueKey, format = value => Number(value || 0).toLocaleString("en-IN") }) {
  const values = items.map(item => Math.max(0, Number(item?.[valueKey]) || 0));
  const max = Math.max(1, ...values);
  return <section className="sb-report-chart" aria-label={title}>
    <h2>{title}</h2>
    {items.length ? <div className="sb-report-bars">{items.map((item, index) => <div className="sb-report-bar-row" key={String(item?.[labelKey] ?? index)}>
      <span>{String(item?.[labelKey] ?? "Unknown").replaceAll("_", " ")}</span>
      <div className="sb-report-bar-track"><i style={{ width: (values[index] / max * 100) + "%" }} /></div>
      <strong>{format(values[index])}</strong>
    </div>)}</div> : <div className="sb-report-chart-empty"><span className="sb-report-empty-grid" /><p>No records for this period. The chart will populate when matching records are available.</p></div>}
  </section>;
}
