# Infra Creator

Create reviewable, container-focused Terraform plans and modules for AWS, Azure and GCP.

## Current support

| Provider | Compute template | Database template | Notes |
|---|---|---|---|
| AWS | ECS Fargate | RDS | Networking required; database security group comes from compute module |
| Azure | Container Apps | PostgreSQL Flexible Server | Networking module required |
| GCP | Cloud Run | Cloud SQL | Networking module required |

Serverless and VM plans are detected but generation stops because matching compute modules are not implemented. Do not treat a plan as deployable infrastructure until Terraform validation and provider review succeed.

## Quick start

Run from the repository root, adjusting paths and provider as needed:

~~~bash
python .agents/skills/infra-creator/scripts/scan_repository.py ./app --json -o /tmp/scan.json
python .agents/skills/infra-creator/scripts/analyze_architecture.py /tmp/scan.json -o /tmp/arch.json

# Inspect the plan; this does not write infrastructure.
python .agents/skills/infra-creator/scripts/generate_terraform.py --scan /tmp/scan.json --arch /tmp/arch.json --provider aws --output ./app/infra --project-name myapp --plan-only

# After approving the plan:
python .agents/skills/infra-creator/scripts/generate_terraform.py --scan /tmp/scan.json --arch /tmp/arch.json --provider aws --output ./app/infra --project-name myapp --approve

# Validate locally; Terraform CLI is required.
python .agents/skills/infra-creator/scripts/validate_terraform.py ./app/infra --json
~~~

Use --overwrite only after reviewing and explicitly approving replacement of a non-empty output directory. Generation requires --approve.

## Database credentials

The generated db_password variable is required and marked sensitive. Supply it through a secret manager or a protected environment variable such as TF_VAR_db_password. Never write the password into committed tfvars, source code, pipeline YAML or logs.

## Layout

~~~text
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
~~~

## Safety and validation

- No implicit terraform apply or terraform destroy.
- No cloud credentials or secrets in generated files.
- Existing output is preserved unless overwrite is explicitly approved.
- Terraform validation runs against an isolated temporary copy and does not alter generated output.
- If the Terraform CLI is missing, validation fails as NOT_RUN; it is never reported as PASS.
- terraform validate does not prove cloud credentials, quotas, policies or deployment will succeed.

## Tests

~~~bash
pytest -q .agents/skills/infra-creator/tests
~~~
