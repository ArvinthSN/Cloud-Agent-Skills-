---
name: infra-creator
description: Generate production-ready Terraform IaC for AWS, Azure, or GCP from application repositories. Use when the user asks to create infrastructure, Terraform configs, cloud resources for an app, analyze a repo for infra needs, or run infra-creator. Supports monolithic, microservices, serverless, and event-driven architectures across three clouds.
---

# Infra-Creator Skill (Multi-Cloud)

Generate customized, production-oriented Terraform projects by analyzing application repositories. Supports **AWS**, **Azure**, and **GCP**.

## When to Use

- User provides a repository path and asks for Terraform / cloud infrastructure
- User specifies a target cloud (AWS, Azure, GCP) or asks for multi-cloud options
- User says "generate infra", "create Terraform for this app", "infra-creator", or similar

Do **not** use for pure application code generation or CI/CD pipelines.

## Supported Providers

| Provider | Status | Primary compute | Primary database |
|----------|--------|-----------------|------------------|
| AWS | Full | ECS Fargate | RDS |
| Azure | Full | Container Apps / AKS-ready | Azure Database for PostgreSQL |
| GCP | Full | Cloud Run | Cloud SQL |

## Execution Workflow (Strict Order)

1. Accept repository path and target provider (`aws` | `azure` | `gcp`). Default to `aws` if unspecified.
2. Run `scripts/scan_repository.py` → structured analysis report.
3. Run `scripts/analyze_architecture.py` → architecture classification + confidence + evidence.
4. Load matching file(s) from `architecture-patterns/`.
5. Identify infrastructure requirements (only what the app actually needs).
6. Map requirements → cloud services using `references/*-service-mapping.md`.
7. Select reusable modules from `templates/<provider>/`.
8. **Present a clear infrastructure plan** (provider, resources, why needed).
9. Wait for explicit user approval of the plan.
10. Run `scripts/generate_terraform.py --provider <provider>` → write Terraform into `<repo>/infra/`.
11. Run `scripts/validate_terraform.py` on the generated project.
12. Fix obvious generation issues if validation fails.
13. Generate/update `infra/README.md` with usage instructions.
14. Present final output location and exact Terraform CLI commands.

Never run `terraform apply` or `terraform destroy`. Never push to GitHub. Never hardcode credentials or secrets.

## Key Scripts

| Script | Purpose |
|--------|---------|
| `scripts/scan_repository.py` | Language, framework, Docker, DB, env-var, and structure detection (cloud-agnostic) |
| `scripts/analyze_architecture.py` | Architecture classification with evidence and confidence |
| `scripts/generate_terraform.py` | Requirement → provider modules → HCL generation (`--provider aws|azure|gcp`) |
| `scripts/validate_terraform.py` | `terraform fmt`, `init -backend=false`, `validate` |

## Architecture Detection Rules

- Prefer evidence over folder count. Multiple folders alone ≠ microservices.
- Use `architecture-patterns/*.md` as the knowledge base.
- If confidence is low, report uncertainty and ask the user for clarification.
- Hybrid is valid when evidence supports it.

## Terraform Generation Rules

- Generate only justified resources for the chosen provider.
- Copy and parameterize modules from `templates/<provider>/{networking,compute,database}/`.
- Always produce: `main.tf`, `providers.tf`, `versions.tf`, `variables.tf`, `outputs.tf`, `terraform.tfvars.example`, environment dirs, and `README.md`.
- Follow `references/terraform-standards.md` and `references/security-guidelines.md`.
- Prefer private networking, least-privilege identity, encryption, and remote state recommendations.
- Never emit empty placeholder resources or fake HCL.

## Security Non-Negotiables

- No hardcoded cloud credentials.
- No publicly exposed databases.
- Least-privilege identity (IAM / RBAC / service accounts).
- Encrypt data at rest and in transit where applicable.
- Recommend remote state for team environments.
- Never commit state files, secrets, or sensitive tfvars.

## Manual Invocation Only

This skill is invoked by the user. It does not run continuously and does not auto-deploy.