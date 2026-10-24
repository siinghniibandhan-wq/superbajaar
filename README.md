# Super Bajaar

Super Bajaar is a React/Vite storefront with a Python API backend.

## Current design
- The existing application database is the source of truth for products, variants, categories, prices, images, and availability.
- The storefront reads active catalogue items from the backend API.
- Administrators can manage products and categories through authenticated API endpoints.
- New database records become visible through the catalogue API without CSV imports or a separate sync runner.
- Database credentials and admin secrets must remain server-side.

## Development

Frontend commands are defined in `package.json`:
- `npm run dev` — local development server
- `npm run build` — production build
- `npm run preview` — preview the production build

Backend dependencies are listed in `backend/requirements.txt`. Configure the backend environment using `backend/.env.example`.

## Database

The application expects the existing database and its required tables to be configured for the backend. SQL files under `backend/schema/` document the application tables and features; do not run schema changes against production without reviewing them first.

No sample products are fabricated by the storefront.