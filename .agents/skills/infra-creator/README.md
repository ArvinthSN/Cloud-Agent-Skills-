# infra-creator (Multi-Cloud)

Generate production-oriented Terraform IaC for **AWS**, **Azure**, and **GCP** from application repositories.

## Providers

| Provider | Compute | Database | Registry |
|----------|---------|----------|----------|
| AWS | ECS Fargate + ALB | RDS | ECR |
| Azure | Container Apps | PostgreSQL Flexible Server | ACR |
| GCP | Cloud Run | Cloud SQL | Artifact Registry |

## Quick Start

```bash
# Scan
python scripts/scan_repository.py /path/to/app --json -o /tmp/scan.json

# Analyze architecture
python scripts/analyze_architecture.py /tmp/scan.json -o /tmp/arch.json

# Plan (no files written) — choose provider
python scripts/generate_terraform.py \
  --scan /tmp/scan.json --arch /tmp/arch.json \
  --provider aws \          # or azure | gcp
  --output /path/to/app/infra \
  --project-name myapp \
  --plan-only

# Generate after approval
python scripts/generate_terraform.py \
  --scan /tmp/scan.json --arch /tmp/arch.json \
  --provider aws \
  --output /path/to/app/infra \
  --project-name myapp

# Validate
python scripts/validate_terraform.py /path/to/app/infra
```

## Layout

```
infra-creator/
├── SKILL.md
├── scripts/           # scan, analyze, generate, validate
├── architecture-patterns/
├── references/        # per-cloud service mappings + standards
├── templates/
│   ├── aws/
│   ├── azure/
│   └── gcp/
├── examples/
└── tests/
```

## Principles

- Evidence-based architecture detection
- Only justified resources
- Human approval before generation
- No auto-apply, no credential hardcoding
- Private networking and encrypted databases by default

## Testing

```bash
pytest tests/ -v
```

## Limitations (v1)

- Container-focused compute modules (ECS / Container Apps / Cloud Run)
- Serverless detection exists; dedicated Lambda/Functions modules can be extended later
- Terraform CLI required for validation (not for generation)
- Does not run `terraform apply` or push to GitHub
```