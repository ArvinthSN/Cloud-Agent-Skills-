# infra-creator (Multi-Cloud)

Generate production-oriented Terraform IaC for AWS, Azure and GCP from application repositories.

## Providers

| Provider | Compute | Database | Registry |
|---|---|---|---|
| AWS | ECS Fargate + ALB | RDS | ECR |
| Azure | Container Apps | PostgreSQL Flexible Server | ACR |
| GCP | Cloud Run | Cloud SQL | Artifact Registry |

## Quick start

Plan only; choose aws, azure or gcp:

    python scripts/generate_terraform.py --scan /tmp/scan.json --arch /tmp/arch.json --provider aws --output /path/to/app/infra --project-name myapp --plan-only

Generate only after reviewing and approving the plan:

    python scripts/generate_terraform.py --scan /tmp/scan.json --arch /tmp/arch.json --provider aws --output /path/to/app/infra --project-name myapp --approve

Validate (requires Terraform CLI):

    python scripts/validate_terraform.py /path/to/app/infra

Add --overwrite only after reviewing an existing non-empty output directory.

## Layout

    infra-creator/
    ├── SKILL.md
    ├── scripts/
    ├── architecture-patterns/
    ├── references/
    ├── templates/
    │   ├── aws/
    │   ├── azure/
    │   └── gcp/
    ├── examples/
    └── tests/

## Principles

- Evidence-based architecture detection.
- Generate only justified resources.
- Require human approval before writing.
- Never auto-apply or hardcode credentials.
- Prefer private networking and encrypted databases.

## Testing

    pytest tests/ -v

## Limitations

- Current compute modules are container-focused (ECS, Container Apps and Cloud Run).
- Serverless is detected but generation is blocked until dedicated function modules exist.
- Terraform CLI is required for validation, but not for planning.
- Generation requires --approve; non-empty output directories require --overwrite.
- The generator never runs terraform apply or pushes to GitHub.
