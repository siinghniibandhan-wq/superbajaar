# Browser Quality Tooling

## Playwright

The frontend browser smoke suite lives in `frontend/tests/e2e` and uses the pinned `@playwright/test` dependency. The configuration tests the built Vite preview on port 4173, not the development server.

Current smoke coverage:
- Storefront route serves the application shell and expected document title.
- Admin route without a session displays the sign-in screen and correctly typed, labelled email/password controls.

Run locally:

```bash
cd frontend
npm install
npx playwright install chromium
npm run build
npm run test:e2e
```

## Lighthouse

The GitHub Actions workflow runs Lighthouse against the built frontend preview and collects Performance, Accessibility, Best Practices and SEO category scores. JSON and HTML reports are retained as workflow artifacts for 14 days.

The first phase is baseline collection only. Scores are not yet merge-blocking because no agreed performance budget or stable production-like test environment has been established. Do not convert Lighthouse scores into required thresholds until a baseline is reviewed and thresholds are approved.

## CI behaviour

Workflow: `.github/workflows/browser-quality.yml`

- Runs on PRs to `main`, pushes to `main`, and manual dispatch.
- Uses no production credentials and does not call the production backend.
- Runs against the static frontend preview; API-dependent workflows are outside this smoke suite.
- Uploads Playwright and Lighthouse reports as artifacts.
- Does not deploy, alter branch protection, or change production data.

The owner may later add the Playwright and Lighthouse job names to the main ruleset after reviewing several stable runs. Existing required CI checks remain unchanged.
