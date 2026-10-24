# API and Module Plan

## Current priorities
1. Stable product catalogue API backed by the existing database.
2. Product and variant management, including images, prices, and availability.
3. Database-backed category listing and creation.
4. Authenticated admin access and server-side validation.
5. Reliable frontend production builds and deployment verification.

## Core rules
- The existing application database is the source of truth for catalogue data.
- Do not fabricate products or categories.
- Do not require CSV imports or an external synchronisation runner for routine catalogue updates.
- Keep credentials and database access on the server.
- Keep changes small and verify the production build before deployment.