# Historical Browser Quality Workflow

**Status:** Retired — GitHub Actions workflow removed by PR [#77](https://github.com/siinghniibandhan-wq/superbajaar/pull/77) on 12 November 2026.

This document is retained as a historical record of the former `browser-quality.yml` workflow. It is not an active workflow specification and no GitHub Actions browser-quality job is currently configured in this repository.

The former workflow contained two independent jobs:

- **Playwright browser smoke tests** built the frontend, installed Chromium, and ran the browser smoke suite.
- **Lighthouse performance and accessibility report** built the frontend, served the production preview locally, and audited performance, accessibility, best practices, and SEO.

The former workflow pinned Lighthouse CLI to `12.8.2` and overrode the problematic `tldts-core` transitive dependency to published version `7.4.16`. It uploaded Lighthouse JSON and HTML reports as the `lighthouse-report` workflow artifact when generated.

These details describe the deleted workflow only. They do not indicate that browser tests, Lighthouse audits or report uploads currently run automatically. Run the relevant tests manually or through a separately approved replacement system when available.
