# Super Bajaar

A fresh React/Vite storefront backed by a Python API and the existing application database.

## Catalogue behaviour
- The website reads the current product catalogue from `GET /api/products`.
- No sample products, product backups, CSV imports, or background synchronisation are included.
- Product visibility depends on the records and active statuses in the connected database.
- Database credentials stay on the backend.

## Frontend
Run `npm install`, then `npm run dev`. Run `npm run build` to create the production bundle.

Set `VITE_API_BASE_URL` only when the API is hosted on a different origin. If frontend and API share a domain, leave it unset.

## Backend
Install `backend/requirements.txt`, set `DATABASE_URL` to the existing PostgreSQL database, and run `uvicorn app.main:app --app-dir backend --host 0.0.0.0 --port 8000`.

This app reads the existing database; it does not create a product copy or run continuous synchronisation. Schema changes must be reviewed separately and must not be applied blindly to production.