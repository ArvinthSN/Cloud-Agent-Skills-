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

## Immutable images and provider security

Every generated compute module requires `container_image` in immutable OCI digest form, such as `registry.example.com/app@sha256:<64-hex-digest>`. Build and push the image separately before running Terraform. The generator does not build or publish images.

- **AWS:** ECR tags are immutable. Set `certificate_arn` to an ACM certificate in the ALB region. HTTP redirects to HTTPS.
- **Azure:** ACR admin credentials are disabled. Container Apps use a user-assigned managed identity with AcrPull. PostgreSQL uses a delegated subnet, private DNS zone and disabled public networking.
- **GCP:** Cloud Run requires authentication by default. Public unauthenticated access is an explicit opt-in via `allow_unauthenticated = true`.

Generated examples leave image digests and certificate values as commented placeholders. Supply valid values through reviewed tfvars or protected pipeline variables; never commit secrets.

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

## Static security policies

The validator checks for mutable `:latest` image references, mutable ECR tags, Azure registry admin credentials, public Azure PostgreSQL, unconditional GCP `allUsers` access, missing AWS ALB HTTPS redirect/certificate controls and missing immutable image-digest input validation. These policies run without cloud credentials or Terraform CLI.

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
