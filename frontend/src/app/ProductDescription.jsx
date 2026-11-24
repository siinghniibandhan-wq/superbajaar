const KEY_LINE = /^([A-Za-z][A-Za-z0-9 &/()'.-]{0,40}?)\s*:\s*(.*)$/;
const BULLET = /^[-•*·]\s+(.*)$/;

function parseDescription(text) {
  const intro = [];
  const details = [];
  const sections = [];
  let current = null;
  String(text || "").replace(/\r/g, "").split("\n").forEach(raw => {
    const line = raw.trim();
    if (!line) return;
    const bullet = line.match(BULLET);
    const key = !bullet && line.match(KEY_LINE);
    if (key) {
      const label = key[1].trim();
      const value = key[2].trim();
      if (/^(product )?description$/i.test(label) && !value) return;
      if (!value) { current = { title: label, items: [] }; sections.push(current); return; }
      if (/^(product )?description$/i.test(label)) { intro.push(value); return; }
      current = null;
      details.push({ label, value });
      return;
    }
    if (bullet) {
      if (!current) { current = { title: "", items: [] }; sections.push(current); }
      current.items.push(bullet[1]);
      return;
    }
    if (current) current.items.push(line); else intro.push(line);
  });
  return { intro, details, sections: sections.filter(section => section.items.length) };
}

export default function ProductDescription({ text }) {
  const { intro, details, sections } = parseDescription(text);
  if (!intro.length && !details.length && !sections.length) return null;
  return (
    <section className="storefront-desc" aria-label="Product description">
      {intro.length > 0 && (
        <div className="storefront-desc-block">
          <h2>About this product</h2>
          {intro.map((paragraph, i) => <p key={i}>{paragraph}</p>)}
        </div>
      )}
      {sections.map((section, i) => (
        <div className="storefront-desc-block" key={i}>
          {section.title && <h2>{section.title}</h2>}
          <ul>{section.items.map((item, j) => <li key={j}>{item}</li>)}</ul>
        </div>
      ))}
      {details.length > 0 && (
        <div className="storefront-desc-block">
          <h2>Product details</h2>
          <dl className="storefront-desc-details">
            {details.map((row, i) => <div key={i}><dt>{row.label}</dt><dd>{row.value}</dd></div>)}
          </dl>
        </div>
      )}
    </section>
  );
}
