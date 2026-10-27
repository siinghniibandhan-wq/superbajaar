# Database design and migration safety

## Non-negotiable rules

- No destructive schema reset in application startup.
- Do not use `DROP DATABASE`, `DROP SCHEMA`, `DROP TABLE`, or `TRUNCATE` as part of routine deployment.
- Schema evolution must be a versioned migration with a clear forward path and documented rollback/backup approach.
- Seed data must be idempotent and must never include real customer, payment or credential data.
- Store monetary amounts as fixed-precision decimals, use explicit currency and tax treatment, and preserve audit timestamps.
- Orders, payment attempts, refunds, stock movements and accounting journals need stable identifiers and idempotency protections.

## Connection safety

Use environment configuration for the database URL. Never print credentials in logs. Before any migration, verify the host/database name and take a backup appropriate to the environment. Local/test databases must be explicitly configured and must not fall back silently to production.

## Current status

This document defines the target rules only. It does not connect to, inspect, migrate, clear or modify any database.
