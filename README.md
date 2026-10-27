# Super Bajaar — clean architecture branch

This branch establishes the target architecture for a new modular commerce and ERP application. The current production-oriented legacy files are intentionally retained for reference during the transition; they are not the foundation for new modules.

## Target layout

- `frontend/` — new React + Vite application structure.
- `backend/app/` — modular FastAPI application, versioned routes and configuration.
- `database/` — reviewed schema/seed assets; never auto-run.
- `docs/` — architecture, database safety and API contracts.
- `scripts/` — explicit safe operational scripts.

## Ports

- Vite development: `5173`.
- Existing backend deployment has historically used `127.0.0.1:8001`; preserve it until the server service, reverse proxy, health checks and frontend API URL are verified together.
- PostgreSQL was reported by the user's terminal as listening on `127.0.0.1:5432`; preserve it. The actual database name and credentials must be taken from the active service environment, not guessed.

## Database safety

Creating this structure does not modify the database. Do not run reset/drop/truncate commands. The target schema is deliberately a placeholder until entities and versioned migrations are reviewed. Preserve the current database URL and secrets during the transition; never commit real credentials.

## Next implementation steps

1. Confirm deployment/runtime settings and database target without changing them.
2. Implement the frontend app shell, router, providers and API client in `frontend/`.
3. Implement backend domain modules and migrations under `backend/app/`.
4. Add tests against a dedicated test database and verify each end-to-end workflow.
5. Switch deployment entrypoints only after build and smoke tests pass.

See `docs/architecture.md`, `docs/database-design.md` and `docs/api-contracts.md`.
