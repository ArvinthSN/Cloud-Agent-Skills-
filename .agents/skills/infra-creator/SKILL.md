---
name: infra-creator
description: Generate production-ready Terraform IaC for AWS, Azure, or GCP from application repositories. Use when the user asks to create infrastructure, Terraform configs, cloud resources for an app, analyze a repo for infra needs, or run infra-creator. Supports container-focused monolithic, microservices and hybrid architectures across three clouds. Serverless detection is advisory; serverless generation is not implemented.
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
| AWS | Template-backed, validate per project | ECS Fargate | RDS |
| Azure | Template-backed, validate per project | Container Apps | Azure Database for PostgreSQL |
| GCP | Template-backed, validate per project | Cloud Run | Cloud SQL |

## Shared harness and context discipline

Follow AGENTS.md and the shared contracts in .agents/standards/. Load only the architecture pattern and provider mappings needed for the selected task. Reuse a valid scan and architecture handoff; re-scan only if the target or relevant project revision changed. Keep evidence summaries bounded and link to generated artifacts rather than repeating full files.

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
10. Run `scripts/generate_terraform.py --plan-only` first. After approval, pass `--approve`; pass `--overwrite` only after explicit overwrite approval.
11. Run `scripts/validate_terraform.py` on the generated project.
12. Fix obvious generation issues if validation fails.
13. Generate/update `infra/README.md` with usage instructions.
14. Present final output location and exact Terraform CLI commands.

Generation requires `--approve`. Existing non-empty output directories are preserved unless `--overwrite` is explicitly passed. Never run `terraform apply` or `terraform destroy`. Never push to GitHub. Never hardcode credentials or secrets.

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
- Copy and parameterize only existing templates from `templates/<provider>/{networking,compute,database}/`. Current compute modules are container-focused; serverless plans must stop rather than emit container modules.
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