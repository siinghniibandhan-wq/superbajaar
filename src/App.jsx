import { useMemo, useState } from 'react';
import {
  Menu, MapPin, Search, Heart, ShoppingCart, UserRound, ChevronDown, ChevronRight,
  Truck, ShieldCheck, RotateCcw, CreditCard, Crown, ShoppingBag, Leaf, Shirt,
  Laptop, Sofa, Sparkles, PawPrint, Baby, Dumbbell, CookingPot, BookOpen, Car,
  Apple, Package, Tag, X, Plus, Check, SlidersHorizontal
} from 'lucide-react';

const categories = [
  { name: 'Grocery & Staples', short: 'Grocery', icon: ShoppingBag, tint: 'lavender', count: 'Daily essentials' },
  { name: 'Fresh Produce', short: 'Fresh', icon: Leaf, tint: 'green', count: 'Farm fresh picks' },
  { name: 'Fashion', short: 'Fashion', icon: Shirt, tint: 'lilac', count: 'Everyday style' },
  { name: 'Electronics', short: 'Electronics', icon: Laptop, tint: 'blue', count: 'Smart choices' },
  { name: 'Home & Living', short: 'Home & Living', icon: Sofa, tint: 'sand', count: 'Make it yours' },
  { name: 'Beauty', short: 'Beauty', icon: Sparkles, tint: 'peach', count: 'Your daily ritual' },
  { name: 'Personal Care', short: 'Personal Care', icon: Package, tint: 'lavender', count: 'Care essentials' },
  { name: 'Baby & Kids', short: 'Baby & Kids', icon: Baby, tint: 'peach', count: 'Little comforts' },
  { name: 'Sports & Fitness', short: 'Sports', icon: Dumbbell, tint: 'blue', count: 'Move every day' },
  { name: 'Pet Care', short: 'Pet Care', icon: PawPrint, tint: 'sand', count: 'For your best friend' },
  { name: 'Kitchen & Dining', short: 'Kitchen', icon: CookingPot, tint: 'green', count: 'Cook and gather' },
  { name: 'Books & Stationery', short: 'Books', icon: BookOpen, tint: 'lilac', count: 'Ideas in motion' },
  { name: 'Automotive', short: 'Automotive', icon: Car, tint: 'blue', count: 'On the go' },
  { name: 'Deals & Offers', short: 'Deals', icon: Tag, tint: 'peach', count: 'More for less' },
];
const products = [
  { id: 1, name: 'Wireless Earbuds', category: 'Electronics', price: 1799, mrp: 2999, off: 40, image: 'photo-1606220945770-b5b6c2c55bf1', tag: 'Bestseller' },
  { id: 2, name: 'Fresh Fruits Basket', category: 'Fresh Produce', price: 149, mrp: 199, off: 25, image: 'photo-1610832958506-aa56368176cf', tag: 'Fresh pick' },
  { id: 3, name: 'Cookware Set (5 pcs)', category: 'Kitchen & Dining', price: 2999, mrp: 4999, off: 40, image: 'photo-1584990347449-a4f6c3b0e8e2', tag: 'Top rated' },
  { id: 4, name: 'Everyday Running Shoes', category: 'Fashion', price: 2499, mrp: 3999, off: 37, image: 'photo-1542291026-7eec264c27ff', tag: 'Popular' },
  { id: 5, name: 'Signature Eau de Parfum', category: 'Beauty', price: 999, mrp: 1499, off: 33, image: 'photo-1541643600914-78b084683601', tag: 'Trending' },
  { id: 6, name: 'Everyday Tote Bag', category: 'Fashion', price: 799, mrp: 1199, off: 33, image: 'photo-1548036328-c9fa89d128fa', tag: 'New arrival' },
  { id: 7, name: 'Minimal Table Lamp', category: 'Home & Living', price: 1299, mrp: 1899, off: 32, image: 'photo-1507473885765-e6ed057f782c', tag: 'Editor’s pick' },
  { id: 8, name: 'Gentle Daily Care Set', category: 'Personal Care', price: 499, mrp: 699, off: 29, image: 'photo-1608248543803-ba4f8c70ae0b', tag: 'Everyday value' },
];
const money = n => '₹' + n.toLocaleString('en-IN');
const imageUrl = (id, w=600) => 'https://images.unsplash.com/' + id + '?auto=format&fit=crop&w=' + w + '&q=85';

function App() {
  const [query, setQuery] = useState('');
  const [activeCategory, setActiveCategory] = useState('All');
  const [cart, setCart] = useState([]);
  const [wishlist, setWishlist] = useState([]);
  const [menuOpen, setMenuOpen] = useState(false);
  const [showAllCategories, setShowAllCategories] = useState(false);
  const [notice, setNotice] = useState('');
  const visibleProducts = useMemo(() => products.filter(p =>
    (activeCategory === 'All' || p.category === activeCategory || (activeCategory === 'Grocery & Staples' && p.category === 'Fresh Produce')) &&
    (p.name.toLowerCase().includes(query.toLowerCase()) || p.category.toLowerCase().includes(query.toLowerCase()))
  ), [query, activeCategory]);
  const addToCart = product => { setCart(prev => [...prev, product]); setNotice(product.name + ' added to your bag'); setTimeout(() => setNotice(''), 2200); };
  const chooseCategory = name => { setActiveCategory(name === 'Deals & Offers' ? 'All' : name); setShowAllCategories(false); document.getElementById('trending')?.scrollIntoView({ behavior: 'smooth', block: 'start' }); };
  const navCategories = ['Grocery & Staples','Fresh Produce','Fashion','Electronics','Home & Living','Beauty','Personal Care','Deals & Offers'];
  return <div className="site-shell">
    <div className="announcement"><span>Thoughtful picks for everyday living</span><span className="announcement-right">Free delivery on orders above ₹799 <span className="announce-dot">•</span> Easy returns within 7 days</span></div>
    <header className="top-header">
      <button className="icon-button menu-trigger" aria-label="Open category menu" onClick={() => setMenuOpen(!menuOpen)}><Menu size={23}/></button>
      <a className="brand" href="#" aria-label="Super Bajaar home" onClick={e => {e.preventDefault(); setActiveCategory('All'); setQuery('');}}>
        <span className="brand-mark"><ShoppingBag size={31} strokeWidth={2.3}/><span className="brand-spark">✦</span></span>
        <span className="brand-copy"><strong>Super Bajaar<span className="registered">®</span></strong><small>Your Everyday Super Store.</small></span>
      </a>
      <button className="delivery" onClick={() => setNotice('Enter your delivery PIN code at checkout to check serviceability')}><MapPin size={20}/><span><small>Deliver to</small><strong>Bengaluru</strong></span><ChevronDown size={15}/></button>
      <label className="search-box"><Search size={19}/><input value={query} onChange={e => {setQuery(e.target.value); if(e.target.value) document.getElementById('trending')?.scrollIntoView({behavior:'smooth'});}} placeholder="Search groceries, fashion, electronics..." aria-label="Search products"/><kbd>⌘ K</kbd></label>
      <div className="header-actions">
        <button className="header-action" onClick={() => setNotice(wishlist.length ? wishlist.length + ' item(s) saved to your wishlist' : 'Your wishlist is ready for your favourites')}><Heart size={22}/><span>Wishlist</span>{wishlist.length > 0 && <i>{wishlist.length}</i>}</button>
        <button className="header-action" onClick={() => setNotice(cart.length ? cart.length + ' item(s) in your shopping bag · ' + money(cart.reduce((s,p)=>s+p.price,0)) : 'Your shopping bag is empty')}><ShoppingBag size={22}/><span>Bag</span>{cart.length > 0 && <i>{cart.length}</i>}</button>
        <button className="header-action account-action" onClick={() => setNotice('Customer account sign-in will be available when authentication is connected')}><UserRound size={22}/><span>Account</span></button>
      </div>
    </header>
    <nav className="nav-bar" aria-label="Main categories">
      <button className="all-categories" onClick={() => setMenuOpen(!menuOpen)}><Menu size={17}/> All Categories <ChevronDown size={15}/></button>
      {navCategories.map(n => <button key={n} className={'nav-link '+(activeCategory===n?'selected':'')} onClick={() => chooseCategory(n)}>{n === 'Grocery & Staples' ? 'Grocery' : n === 'Fresh Produce' ? 'Fresh' : n === 'Deals & Offers' ? <><Tag size={14}/> Deals</> : n}</button>)}
      <button className="plus-pill" onClick={() => setNotice('Super Bajaar Plus rewards and membership details coming soon')}><Crown size={15}/> SB Plus</button>
    </nav>
    {menuOpen && <div className="mega-menu"><div className="mega-head"><div><strong>Shop all departments</strong><small>Find something for every part of your day.</small></div><button className="icon-button" onClick={() => setMenuOpen(false)} aria-label="Close menu"><X size={20}/></button></div><div className="mega-grid">{categories.map(c => <button key={c.name} className="mega-item" onClick={() => {setActiveCategory(c.name==='Deals & Offers'?'All':c.name);setMenuOpen(false);}}><c.icon size={19}/><span>{c.name}</span><ChevronRight size={15}/></button>)}</div></div>}
    <main>
      <section className="hero-wrap">
        <div className="hero-copy">
          <div className="eyebrow"><span className="eyebrow-line"></span> THE EVERYDAY EDITION</div>
          <h1>Everyday essentials.<br/><em>Exceptionally simple.</em></h1>
          <p>Good finds, fair prices and the little things that make every day better.</p>
          <div className="hero-perks"><span><Truck size={17}/> Thoughtful delivery</span><span><ShieldCheck size={17}/> Quality you can trust</span></div>
          <button className="primary-cta" onClick={() => document.getElementById('categories')?.scrollIntoView({behavior:'smooth'})}>Explore the store <ChevronRight size={19}/></button>
        </div>
        <div className="hero-art">
          <div className="hero-orbit orbit-one"></div><div className="hero-orbit orbit-two"></div>
          <div className="hero-note"><span className="note-kicker">A little better, every day</span><strong>Made for<br/>your everyday.</strong><span className="note-dotline"><i></i><i></i><i></i></span></div>
          <div className="hero-photo"><img src={imageUrl('photo-1543168256-418811576931',900)} alt="A curated everyday shopping selection" /></div>
          <div className="floating-label"><Sparkles size={15}/><span>Good things, gathered.</span></div>
        </div>
        <div className="hero-index"><span>01</span><i></i><span>03</span></div>
      </section>
      <section className="trust-strip" aria-label="Shopping benefits">
        <div><Truck/><span><strong>Free delivery</strong><small>On orders above ₹799</small></span></div>
        <div><ShieldCheck/><span><strong>Genuine products</strong><small>Quality assured</small></span></div>
        <div><RotateCcw/><span><strong>Easy returns</strong><small>Within 7 days</small></span></div>
        <div><CreditCard/><span><strong>Secure payments</strong><small>Multiple options</small></span></div>
      </section>
      <section className="category-section" id="categories">
        <div className="section-heading"><div><span className="section-kicker">FIND YOUR EVERYDAY</span><h2>Shop by category</h2><p>Good things for every corner of life.</p></div><button className="text-link" onClick={() => setShowAllCategories(!showAllCategories)}>{showAllCategories?'Show featured':'View all departments'} <ChevronRight size={17}/></button></div>
        <div className={'category-grid '+(showAllCategories?'expanded':'')}>
          {(showAllCategories ? categories : categories.slice(0,8)).map((c,idx) => <button key={c.name} className={'category-card tint-'+c.tint} onClick={() => chooseCategory(c.name)}><span className="category-icon"><c.icon size={24} strokeWidth={1.8}/></span><span className="category-name">{c.short}</span><span className="category-count">{c.count}</span><span className="category-arrow"><ChevronRight size={15}/></span></button>)}
        </div>
      </section>
      <section className="products-section" id="trending">
        <div className="section-heading product-heading"><div><span className="section-kicker">{activeCategory==='All'?'THE GOOD-FIND EDIT':'BROWSE OUR SELECTION'}</span><h2>{activeCategory==='All'?'Trending right now':activeCategory}</h2><p>{query ? 'Search results for “'+query+'”' : 'Customer favourites worth a closer look.'}</p></div><div className="product-heading-actions"><button className="filter-button" onClick={() => {setActiveCategory('All');setQuery('');}}><SlidersHorizontal size={16}/> Clear filters</button><button className="text-link" onClick={() => {setActiveCategory('All');setQuery('');}}>View all <ChevronRight size={17}/></button></div></div>
        {visibleProducts.length ? <div className="product-grid">{visibleProducts.map(p => <article className="product-card" key={p.id}><div className="product-image-wrap"><img src={imageUrl(p.image,600)} alt={p.name} loading="lazy"/><span className="discount-badge">{p.off}% off</span><button className={'wishlist-button '+(wishlist.includes(p.id)?'wishlisted':'')} aria-label={'Save '+p.name+' to wishlist'} onClick={() => setWishlist(prev=>prev.includes(p.id)?prev.filter(id=>id!==p.id):[...prev,p.id])}><Heart size={17} fill={wishlist.includes(p.id)?'currentColor':'none'}/></button><span className="product-tag">{p.tag}</span></div><div className="product-info"><span className="product-category">{p.category}</span><h3>{p.name}</h3><div className="price-row"><strong>{money(p.price)}</strong><del>{money(p.mrp)}</del><span className="saving">Save {p.off}%</span></div><button className="add-bag" onClick={() => addToCart(p)} aria-label={'Add '+p.name+' to shopping bag'}><ShoppingBag size={17}/><span>Add to bag</span></button></div></article>)}</div> : <div className="empty-state"><Search size={28}/><strong>No products found</strong><p>Try a different search or browse all departments.</p><button className="primary-cta" onClick={()=>{setQuery('');setActiveCategory('All');}}>Show all products</button></div>}
      </section>
      <section className="membership-band"><div className="membership-icon"><Crown size={25}/></div><div><span className="section-kicker">A LITTLE EXTRA, JUST FOR YOU</span><h2>Everyday shopping. More rewarding.</h2><p>Discover member perks, special offers and thoughtful surprises with SB Plus.</p></div><button className="membership-button" onClick={() => setNotice('SB Plus membership details coming soon')}>Discover SB Plus <ChevronRight size={17}/></button></section>
    </main>
    <footer className="footer"><a className="brand footer-brand" href="#"><span className="brand-mark"><ShoppingBag size={25}/></span><span className="brand-copy"><strong>Super Bajaar</strong><small>Your Everyday Super Store.</small></span></a><span>Good finds for everyday life.</span><span>© 2026 Super Bajaar</span></footer>
    {notice && <div className="toast" role="status"><Check size={17}/><span>{notice}</span><button onClick={()=>setNotice('')} aria-label="Dismiss"><X size={16}/></button></div>}
    <div className="mobile-bottom"><button onClick={()=>setMenuOpen(!menuOpen)}><Menu/><span>Browse</span></button><button onClick={()=>document.querySelector('.search-box input')?.focus()}><Search/><span>Search</span></button><button onClick={()=>setNotice(cart.length ? cart.length+' item(s) in your bag' : 'Your bag is empty')}><ShoppingBag/><span>Bag {cart.length>0?'('+cart.length+')':''}</span></button><button onClick={()=>setNotice('Customer account sign-in will be available when authentication is connected')}><UserRound/><span>Account</span></button></div>
  </div>;
}
export default App;
