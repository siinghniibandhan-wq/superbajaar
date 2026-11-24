import { useEffect, useRef, useState } from "react";

// Hero image slider for a category page. Images come from Admin > Catalogue > Category banners.
// One image shows as a plain banner; two or more get auto-play, swipe, arrows and dots.
export default function CategoryHeroSlider({ images = [], title = "", interval = 5000 }) {
  const count = images.length;
  const [index, setIndex] = useState(0);
  const [paused, setPaused] = useState(false);
  const touchStart = useRef(null);

  useEffect(() => { setIndex(0); }, [count, title]);
  useEffect(() => {
    if (count < 2 || paused) return undefined;
    if (typeof window !== "undefined" && window.matchMedia?.("(prefers-reduced-motion: reduce)").matches) return undefined;
    const timer = setInterval(() => setIndex(i => (i + 1) % count), interval);
    return () => clearInterval(timer);
  }, [count, paused, interval]);

  if (!count) return null;
  const go = next => setIndex(((next % count) + count) % count);
  const onTouchStart = event => { setPaused(true); touchStart.current = event.touches[0].clientX; };
  const onTouchEnd = event => {
    const start = touchStart.current; touchStart.current = null; setPaused(false);
    if (start == null) return;
    const delta = event.changedTouches[0].clientX - start;
    if (Math.abs(delta) > 40) go(index + (delta < 0 ? 1 : -1));
  };

  return <div className="storefront-hero-slider" role="region" aria-roledescription="carousel" aria-label={title + " banners"}
    onMouseEnter={() => setPaused(true)} onMouseLeave={() => setPaused(false)} onFocus={() => setPaused(true)} onBlur={() => setPaused(false)}
    onTouchStart={onTouchStart} onTouchEnd={onTouchEnd}>
    <div className="storefront-hero-slider-track" style={{ transform: "translateX(-" + index * 100 + "%)" }}>
      {images.map((image, i) => <div className="storefront-hero-slide" key={image.id ?? image.image_url} role="group" aria-roledescription="slide" aria-label={(i + 1) + " of " + count} aria-hidden={i !== index}>
        <img src={image.image_url} alt={image.alt_text || title} loading={i === 0 ? "eager" : "lazy"} decoding="async" draggable="false" />
      </div>)}
    </div>
    {count > 1 && <>
      <button type="button" className="storefront-hero-arrow is-prev" aria-label="Previous banner" onClick={() => go(index - 1)}>‹</button>
      <button type="button" className="storefront-hero-arrow is-next" aria-label="Next banner" onClick={() => go(index + 1)}>›</button>
      <div className="storefront-hero-dots">
        {images.map((image, i) => <button type="button" key={image.id ?? image.image_url} className={i === index ? "is-active" : ""} aria-label={"Show banner " + (i + 1)} aria-current={i === index} onClick={() => go(i)} />)}
      </div>
    </>}
  </div>;
}
