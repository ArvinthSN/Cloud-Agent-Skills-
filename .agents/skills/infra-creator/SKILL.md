---
name: infra-creator
description: Analyze an application and produce guarded, container-focused Terraform plans and modules for AWS, Azure or GCP.
---

# Infra Creator

## Purpose
Generate reviewable Terraform from evidence in an application repository.

## Inputs and outputs
- Input: application path, cloud provider (AWS, Azure or GCP), project name and optional region.
- Output: plan report, Terraform files and usage README.
- Current compute templates are container-focused. Serverless and VM generation are not implemented.

## Secure defaults and required inputs

- Every generated compute module requires `container_image` to be an immutable OCI digest reference (`repository@sha256:<64 hex characters>`). Build and push the image separately before provisioning.
- AWS ECR enforces immutable tags. The public ALB redirects HTTP to HTTPS and requires an ACM certificate ARN in the selected AWS region.
- Azure Container Registry admin access is disabled. The Container App pulls through a user-assigned managed identity with AcrPull. Azure PostgreSQL uses a delegated subnet, private DNS and disabled public network access.
- GCP Cloud Run is authenticated by default. Unauthenticated invocation is created only when `allow_unauthenticated=true` is explicitly approved.
- Database passwords remain sensitive inputs and must be supplied through a protected environment or secret manager, not committed tfvars.
- Shared/team use requires a reviewed remote-state backend with state locking; the generated backend snippets are examples and are not enabled automatically.

## Workflow
1. Follow AGENTS.md and .agents/standards/.
2. Scan once with scripts/scan_repository.py and classify with scripts/analyze_architecture.py. Reuse valid reports for the same project revision.
3. Load only the selected architecture pattern, provider mapping and security references.
4. Build the Terraform plan with scripts/generate_terraform.py --plan-only.
5. Explain each resource, module dependency, cost-relevant choice, assumption and unknown.
6. Obtain explicit approval before writing. Generation requires --approve; existing non-empty output requires separate --overwrite approval.
7. Generate only capabilities supported by the selected provider templates. Stop clearly for serverless/VM plans and unsupported dependency combinations.
8. Run scripts/validate_terraform.py. It applies provider-aware static security policies, then validates an isolated copy with Terraform when installed; it never applies infrastructure. Missing Terraform is NOT_RUN. The orchestrator can additionally run an isolated Terraform plan only with explicit --terraform-plan approval. Terraform templates must use valid multiline HCL blocks; semicolons are not attribute separators. Require terraform fmt, init -backend=false and validate to pass before accepting generated modules.
9. Report artifacts and check statuses, including Terraform NOT_RUN when the CLI is unavailable.

## Safety
- Never run terraform apply or destroy. Terraform plan is read-only with backend and refresh disabled, but provider plugins and external data sources can execute code; review the configuration before explicitly requesting it.
- Never provision cloud resources, change cloud accounts or push to GitHub.
- Never hardcode credentials or secret values. Use secret managers or environment variables.
- Do not expose databases publicly by default.
- Preserve existing output unless explicit overwrite approval is given.
- A successful terraform validate is not proof that a cloud deployment will succeed.
- State provider-specific limitations and manual prerequisites.

## CLI
~~~bash
python scripts/scan_repository.py ./app --json -o /tmp/scan.json
python scripts/analyze_architecture.py /tmp/scan.json -o /tmp/arch.json
python scripts/generate_terraform.py --scan /tmp/scan.json --arch /tmp/arch.json --provider aws --output ./app/infra --plan-only
python scripts/generate_terraform.py --scan /tmp/scan.json --arch /tmp/arch.json --provider aws --output ./app/infra --approve
python scripts/validate_terraform.py ./app/infra --json
~~~
