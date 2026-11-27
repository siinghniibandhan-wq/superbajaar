import { Fragment } from "react";
import { LEGAL_PAGES } from "./legalContent.js";

// Minimal inline renderer: **bold**, [label](href) and line breaks.
function Inline({ text, onInternal }) {
  const out = [];
  const re = /\*\*(.+?)\*\*|\[([^\]]+)\]\(([^)]+)\)/g;
  let last = 0, m, k = 0;
  const lines = String(text);
  while ((m = re.exec(lines))) {
    if (m.index > last) out.push(<Fragment key={k++}>{withBreaks(lines.slice(last, m.index))}</Fragment>);
    if (m[1] !== undefined) out.push(<strong key={k++}>{withBreaks(m[1])}</strong>);
    else {
      const href = m[3];
      const internal = href.startsWith("/pages/");
      out.push(<a key={k++} href={href}
        {...(internal ? { onClick: e => { e.preventDefault(); onInternal(href.slice(7)); } } : { target: "_blank", rel: "noreferrer" })}>{m[2]}</a>);
    }
    last = re.lastIndex;
  }
  if (last < lines.length) out.push(<Fragment key={k++}>{withBreaks(lines.slice(last))}</Fragment>);
  return <>{out}</>;
}
function withBreaks(s) {
  return s.split("\n").map((part, i, a) => <Fragment key={i}>{part}{i < a.length - 1 && <br />}</Fragment>);
}

export default function LegalPage({ slug, openInfoPage }) {
  const page = LEGAL_PAGES[slug];
  if (!page) return null;
  const I = t => <Inline text={t} onInternal={openInfoPage} />;
  return <>
    <span className="storefront-kicker">{page.kicker}</span>
    <h1>{page.title}</h1>
    {page.sections.map((s, i) => <Fragment key={i}>
      {s.h && <h2>{s.h}</h2>}
      {(s.p || []).map((t, j) => <p key={j}>{I(t)}</p>)}
      {s.ul && <ul>{s.ul.map((t, j) => <li key={j}>{I(t)}</li>)}</ul>}
      {s.ol && <ol>{s.ol.map((t, j) => <li key={j}>{I(t)}</li>)}</ol>}
      {s.table && <div style={{ overflowX: "auto" }}><table className="storefront-legal-table"><thead><tr>{s.table.head.map((h, j) => <th key={j}>{h}</th>)}</tr></thead><tbody>{s.table.rows.map((r, j) => <tr key={j}>{r.map((c, n) => <td key={n}>{I(c)}</td>)}</tr>)}</tbody></table></div>}
    </Fragment>)}
  </>;
}
