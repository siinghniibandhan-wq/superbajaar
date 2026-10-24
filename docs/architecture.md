# Architecture

- React/Vite frontend for the storefront and admin interface.
- Python API backend for catalogue reads and authenticated product/category management.
- Existing application database as the source of truth for products, variants, categories, prices, images, and stock availability.

The browser must never hold database credentials, privileged admin credentials, or payment secrets. Validate permissions and business rules on the server. Do not add sample catalogue data or make routine product visibility depend on a separate import/synchronisation process.