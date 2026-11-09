# Super Bajaar launch checklist

Use this checklist as a release gate, not as evidence that any item has already passed. Record the commit, environment, evidence and owner for every completed check.

## Application
- [ ] Confirm the storefront and admin application entry points and their intended hosting roots.
- [ ] Run clean dependency installation and production builds for each frontend workspace.
- [ ] Run backend unit, API and integration tests against an isolated test database.
- [ ] Verify authentication, role-based authorization and session revocation.
- [ ] Verify checkout, payment status, order creation, cancellation and refund paths end to end.
- [ ] Verify stock reservation, receipt, issue, return and reconciliation workflows.

## Security and privacy
- [ ] Confirm no secrets, production environment files, private keys or tokens are in Git or frontend bundles.
- [ ] Verify CORS allowlist, security headers, rate limits and request-size limits.
- [ ] Verify server-side authorization for every privileged API route.
- [ ] Review dependency vulnerabilities and run configured secret/code scanners.
- [ ] Verify logging does not expose credentials, payment data or unnecessary personal data.

## Database and recovery
- [ ] Review migration ordering, checksums and required-schema manifest.
- [ ] Confirm a fresh, restorable database backup before any production migration.
- [ ] Test migrations and rollback/recovery procedures on a production-like disposable database.
- [ ] Reconcile critical inventory, order, payment and accounting records after deployment.

## Operations
- [ ] Confirm approved domains, DNS, TLS, environment variables and service health checks.
- [ ] Confirm monitoring, alerting, log access and incident contacts.
- [ ] Verify backup retention and restore procedure.
- [ ] Obtain explicit owner approval for production deployment.
- [ ] Perform post-deployment smoke checks and document results.

## Release record
- Release commit SHA:
- Environment:
- Test evidence:
- Backup reference:
- Approver:
- Deployment timestamp:
- Post-deployment verification:
