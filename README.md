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

## Database schema migrations

Schema updates are applied automatically by the production deploy runner. No manual SQL is needed.

**Rules for schema files**
- Files live in backend/schema and are named NNN_name.sql (three digits, lowercase letters, digits and underscores).
- Write them idempotently (IF NOT EXISTS, guarded ALTER statements). Never DROP or TRUNCATE existing data.
- Never edit a file after it has been applied. A changed checksum fails the deploy. Add a new numbered file instead.

**How it works**
- The runner /home/ec2-user/deploy/deploy.sh (triggered by sb-deploy.timer every 2 minutes) deploys new commits from main only.
- Before the symlink swap and restart, it calls /home/ec2-user/deploy/bin/apply_schema.sh, a server copy of backend/scripts/apply_schema.sh.
- The script takes a verified pg_dump backup (in /home/ec2-user/schema-backups), applies only unrecorded files (one transaction each), records them in the schema_migrations table with a sha256 checksum, grants the app database role access, and smoke-tests /api/products.
- If a migration fails, the commit is marked failed and the previous release keeps running. Restore from the backup manually if ever needed.
- Logs: /home/ec2-user/deploy/schema.log.

**Rebuilding the server**
1. Copy backend/scripts/apply_schema.sh to /home/ec2-user/deploy/bin/apply_schema.sh (owner ec2-user, mode 755).
2. In deploy.sh, add this line just above the line "mv $T $D":
   [ -d $T/backend/schema ] && { /home/ec2-user/deploy/bin/apply_schema.sh $T/backend/schema || fail "schema migration (see /home/ec2-user/deploy/schema.log)"; }
3. Ensure ec2-user can run "sudo -n -u postgres" without a password.
4. Do a dry run first: bash apply_schema.sh <schema_dir> --dry-run

Product data is never migrated by this process.
