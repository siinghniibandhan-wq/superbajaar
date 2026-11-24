import { useEffect, useState } from "react";

export default function ProductGallery({ images, fallbackUrl, alt, placeholder }) {
  const list = (Array.isArray(images) && images.length ? images : fallbackUrl ? [{ url: fallbackUrl }] : []).filter(item => item && item.url);
  const key = list.map(item => item.url).join("|");
  const [index, setIndex] = useState(0);
  useEffect(() => { setIndex(0); }, [key]);
  if (!list.length) return <div className="storefront-product-page-art">{placeholder}</div>;
  const current = list[Math.min(index, list.length - 1)];
  return (
    <div className="storefront-gallery">
      <div className="storefront-product-page-art"><img src={current.url} alt={current.alt || alt} /></div>
      {list.length > 1 && (
        <div className="storefront-gallery-thumbs" role="tablist" aria-label="Product images">
          {list.map((item, i) => (
            <button key={item.url + i} type="button" role="tab" aria-selected={i === index} aria-label={"Image " + (i + 1)} className={"storefront-gallery-thumb" + (i === index ? " is-active" : "")} onClick={() => setIndex(i)}>
              <img src={item.url} alt="" loading="lazy" />
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
