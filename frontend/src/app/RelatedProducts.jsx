export default function RelatedProducts({ current, variants, productById, onOpen, money, limit = 8 }) {
  if (!current) return null;
  const currentProduct = productById.get(Number(current.product_id));
  const categoryOf = product => String(product?.category_id ?? product?.category_name ?? product?.category ?? "");
  const currentCategory = categoryOf(currentProduct);
  const cheapest = new Map();
  variants.forEach(item => {
    if (item.is_active === false) return;
    const pid = Number(item.product_id);
    if (pid === Number(current.product_id)) return;
    const price = Number(item.selling_price || 0);
    const existing = cheapest.get(pid);
    if (!existing || price < Number(existing.selling_price || 0)) cheapest.set(pid, item);
  });
  const all = [...cheapest.values()];
  const same = all.filter(item => currentCategory && categoryOf(productById.get(Number(item.product_id))) === currentCategory);
  const others = all.filter(item => !same.includes(item));
  const list = [...same, ...others].slice(0, limit);
  if (!list.length) return null;
  return (
    <section className="storefront-related" aria-label="Recommended products">
      <h2>{same.length ? "You may also like" : "Recommended for you"}</h2>
      <div className="storefront-related-row">
        {list.map(item => {
          const product = productById.get(Number(item.product_id));
          const name = product?.name || item.product_name || item.sku;
          const mrp = Number(item.mrp ?? 0);
          const price = Number(item.selling_price || 0);
          const off = mrp > price && price > 0 ? Math.round((mrp - price) / mrp * 100) : 0;
          return (
            <button type="button" key={item.product_id} className="storefront-related-card" onClick={() => { onOpen(item); window.scrollTo({ top: 0, behavior: "smooth" }); }}>
              <span className="storefront-related-img">{item.image_url ? <img src={item.image_url} alt={name} loading="lazy" /> : null}</span>
              <small>{product?.brand || "Super Bajaar"}</small>
              <strong>{name}</strong>
              <span className="storefront-related-price">{money(price)}{off > 0 && <em>{off}% off</em>}</span>
            </button>
          );
        })}
      </div>
    </section>
  );
}
