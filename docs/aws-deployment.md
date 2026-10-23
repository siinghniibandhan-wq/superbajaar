# Super Bajaar — AWS deployment plan

## Target layout
- **Frontend:** AWS Amplify Hosting connected to the private GitHub repository.
- **API:** Containerized FastAPI service. For a new AWS deployment, evaluate Amazon ECS Express Mode/Fargate rather than selecting App Runner for a new account; AWS has announced App Runner will stop accepting new customers after 30 April 2026.
- **Database:** Amazon RDS for PostgreSQL, private subnets, no public database access.
- **Product images:** Amazon S3 with private-by-default access and controlled delivery.
- **Secrets:** AWS Secrets Manager or Systems Manager Parameter Store SecureString; never commit secrets.
- **Monitoring:** CloudWatch logs/alarms and an AWS Budget alert.

## Deployment gates
1. Confirm AWS account, region, billing alerts and existing resources before provisioning anything billable.
2. Create a non-production environment first.
3. Provision a private PostgreSQL database and security groups that permit access only from the API service.
4. Apply schema files in order: `001_product_inventory_foundation.sql`, `002_suppliers_purchasing.sql`, `003_serviceability.sql`. Review against the actual database before production use.
5. Set `DATABASE_URL` and `CORS_ALLOWED_ORIGINS` in the service's secret/configuration manager. Use the Amplify domain as the allowed origin; do not use wildcard origins with credentials.
6. Configure Amplify's `VITE_API_BASE_URL` to the HTTPS API base URL ending before `/api` (for example, the base URL of the API service).
7. Run health, readiness, catalogue, PIN-code, CORS, and security tests before opening traffic.

## Important current state
The API is a foundation, not production-ready commerce software. Product/order writes, authentication, admin roles, audit logs, rate limiting, migrations tooling, image upload, and payment integration are not implemented. Do not expose admin or write endpoints until authentication and authorization are implemented. The catalogue intentionally returns no invented products. PIN-code checks return a configuration error until verified warehouse coverage data is loaded.

## Cost and account safety
No AWS infrastructure is provisioned by these repository changes. Review the current AWS pricing and your existing account resources before creating RDS, ECS, NAT gateways, load balancers, or storage. Do not paste AWS access keys or database passwords into GitHub or chat.
