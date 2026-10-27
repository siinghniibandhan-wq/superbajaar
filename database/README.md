# Database assets

SQL files in this directory are reference/migration assets only. Nothing in this folder runs automatically.

Before applying a schema change:
1. Confirm the target database and environment.
2. Take a suitable backup.
3. Review the migration for destructive statements.
4. Apply through an explicit migration procedure.
5. Verify schema and application health afterwards.

Do not put credentials in SQL files. This scaffold has not connected to or modified any database.
