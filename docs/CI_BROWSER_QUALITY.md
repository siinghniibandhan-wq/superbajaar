# Browser Quality Workflow

The `Browser quality (Playwright + Lighthouse)` workflow validates the storefront in two independent jobs:

- **Playwright browser smoke tests** build the frontend, install Chromium, and run the browser smoke suite.
- **Lighthouse performance and accessibility report** builds the frontend, serves the production preview locally, and audits performance, accessibility, best practices, and SEO.

Lighthouse is installed into an isolated temporary npm project rather than invoked through an unpinned `npx` resolution. The workflow pins Lighthouse CLI to `12.8.2` and overrides the problematic `tldts-core` transitive dependency to published version `7.4.16`. This avoids the observed npm `ETARGET` failure for the unavailable `^7.4.26` range without changing application dependencies.

The Lighthouse JSON and HTML reports are uploaded as the `lighthouse-report` workflow artifact when generated. This workflow does not deploy application code or apply database migrations.
