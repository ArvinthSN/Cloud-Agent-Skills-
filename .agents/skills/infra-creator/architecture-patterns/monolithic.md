# Monolithic Architecture

Single deployable unit. Shared process and usually shared database.

**Detection:** one main entry point, single language/framework, one Dockerfile, no multi-service compose.

**Infra:** network + container platform + optional managed SQL.

| Cloud | Compute | Database |
|-------|---------|----------|
| AWS | ECS Fargate + ALB + ECR | RDS |
| Azure | Container Apps + ACR | PostgreSQL Flexible Server |
| GCP | Cloud Run + Artifact Registry | Cloud SQL |