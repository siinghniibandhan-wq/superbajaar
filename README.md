# Super Bajaar — Storefront

Responsive React + Vite storefront using the original Super Bajaar purple-and-orange brand.

## Run locally

```bash
npm install
npm run dev
```

Create a production bundle with:

```bash
npm run build
npm run preview
```

## Storefront features

- Home page, department browsing, search, sorting, and offer filtering
- Product detail pages with selectable variants and SKU identifiers
- Branded fallback artwork when an external product image cannot load
- Wishlist, shopping bag, quantity controls, and order summary
- `WELCOME10` demo coupon (10% off, capped at ₹300)
- Delivery PIN entry and address form validation
- Local demo order history and responsive mobile layout

## Important implementation status

This repository currently contains a **front-end storefront only**. Product catalogue/prices and ratings are sample data; cart, wishlist, address, and demo orders are stored in the browser when storage is available.

The following are **not connected** and must not be treated as live commerce functions:
- Customer authentication and server-side customer accounts
- Live catalogue, inventory, SKU/variant management, and delivery serviceability
- Verified 30-day product price history
- Server-backed orders, fulfilment, and notifications
- Razorpay or any other online payment processing

Cash-on-delivery checkout creates a local demo record only. Online payment is intentionally blocked until a secure backend is configured. Never place secret payment credentials in frontend code.

## Stack

- React 18
- Vite 6
- lucide-react
