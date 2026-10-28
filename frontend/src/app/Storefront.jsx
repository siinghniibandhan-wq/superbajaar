import "./storefront.css";

const categories = [
  { name: "Grocery", detail: "Everyday essentials", icon: "🥑", tone: "green" },
  { name: "Fashion", detail: "Style for everyone", icon: "👕", tone: "lavender" },
  { name: "Electronics", detail: "Smart picks, every day", icon: "🎧", tone: "blue" },
  { name: "Personal Care", detail: "Care that feels good", icon: "🧴", tone: "peach" },
  { name: "Fresh Products", detail: "Freshness for your home", icon: "🍊", tone: "yellow" },
  { name: "Pet Care", detail: "Little things for your pets", icon: "🐾", tone: "pink" },
];

export default function Storefront() {
  return (
    <main className="storefront">
      <div className="storefront-promo">Your everyday favourites, all in one place <span>✦</span> Shop smarter with Super Bajaar</div>
      <header className="storefront-header">
        <a className="storefront-brand" href="/" aria-label="Super Bajaar home">
          <span className="storefront-logo">S</span>
          <span><strong>Super Bajaar</strong><small>Your Everyday Super Store</small></span>
        </a>
        <nav className="storefront-nav" aria-label="Main navigation">
          <a href="#categories">Categories</a><a href="#why-us">Why Super Bajaar</a>
        </nav>
        <div className="storefront-actions">
          <a className="storefront-admin-link" href="/admin">Admin login</a>
          <a className="storefront-cart" href="#categories" aria-label="Explore shopping">Explore store <span>↗</span></a>
        </div>
      </header>

      <section className="storefront-hero">
        <div className="storefront-hero-copy">
          <span className="storefront-kicker"><i /> YOUR EVERYDAY SUPER STORE</span>
          <h1>Everyday shopping.<br /><em>Extraordinary</em> easy.</h1>
          <p>From fresh finds to daily essentials, discover more of what you need in one colourful, convenient place.</p>
          <a className="storefront-primary" href="#categories">Explore categories <span>→</span></a>
          <div className="storefront-trust"><span>✦ Thoughtfully picked</span><span>✦ Made for everyday</span></div>
        </div>
        <div className="storefront-hero-art" aria-label="Colourful shopping bags and everyday products" role="img">
          <div className="art-sun" />
          <div className="art-orbit orbit-one" /><div className="art-orbit orbit-two" />
          <div className="art-spark spark-one">✦</div><div className="art-spark spark-two">✳</div>
          <div className="art-bag bag-purple"><span>S</span></div>
          <div className="art-bag bag-orange"><span>♥</span></div>
          <div className="art-box"><span>GOOD</span><strong>THINGS</strong></div>
          <div className="art-leaf leaf-one">✦</div><div className="art-leaf leaf-two">✿</div>
          <div className="art-caption">A little joy in every basket</div>
        </div>
      </section>

      <section className="storefront-categories" id="categories">
        <div className="storefront-section-heading"><div><span className="storefront-kicker">FIND YOUR FAVOURITES</span><h2>Shop by category</h2></div><span className="storefront-heading-note">A little something for every day.</span></div>
        <div className="storefront-category-grid">
          {categories.map((category) => <a className="storefront-category" href="#why-us" key={category.name}>
            <span className={`storefront-category-art tone-${category.tone}`}><span>{category.icon}</span><i>↗</i></span>
            <strong>{category.name}</strong><small>{category.detail}</small>
          </a>)}
        </div>
      </section>

      <section className="storefront-benefits" id="why-us">
        <div><span className="benefit-icon">✦</span><strong>Everyday essentials</strong><small>All your regular picks in one place.</small></div>
        <div><span className="benefit-icon">♡</span><strong>Made for your routine</strong><small>A simpler way to shop for home and family.</small></div>
        <div><span className="benefit-icon">✳</span><strong>Discover something new</strong><small>Explore categories for every kind of day.</small></div>
      </section>

      <footer className="storefront-footer"><a className="storefront-brand" href="/"><span className="storefront-logo">S</span><span><strong>Super Bajaar</strong><small>Your Everyday Super Store</small></span></a><span>Everyday made a little brighter.</span><a href="/admin">Business admin ↗</a></footer>
    </main>
  );
}
