# Production Readiness v1.0

## Goal

Add repeatable runtime, build, infrastructure-validation and security evidence beyond the repository's static artifact benchmark.

The GitHub Actions workflow `.github/workflows/production-readiness.yml` is a pull-request and main-branch gate. It runs three independent jobs and a final release gate.

## Evidence produced

| Area | Executed check | What it proves | What it does not prove |
|---|---|---|---|
| Container build | Generate a Dockerfile with app-containerizer and run `docker build --pull` | The generated Python fixture Dockerfile builds against a freshly pulled base image | Every detected project builds |
| Runtime | Start the image with no network, read-only root FS, dropped capabilities, no-new-privileges, PID/memory/CPU limits; probe `/health` | The fixture starts, responds and obeys selected runtime hardening controls | Production traffic, scale, availability or application-specific behavior |
| Terraform | `fmt -check`, `init -backend=false`, `validate`, and `plan -refresh=false` against a provider-free fixture | The Terraform CLI lifecycle works without a backend or cloud resources | AWS/Azure/GCP provider compatibility, IAM, quotas or deployability |
| Image security | Trivy vulnerability/secret scan of the locally built image | HIGH/CRITICAL findings in the scanned image are release blockers | Absence of all vulnerabilities; scanner DB freshness and coverage still matter |
| SBOM | CycloneDX SBOM generated from the built image | A machine-readable image component inventory is retained | Provenance or a signed attestation |
| Repository security | Gitleaks plus Trivy filesystem misconfiguration/secret scan | The checked-out repository is scanned for exposed secrets and selected IaC/config issues | Full penetration testing, policy certification or all provider-specific controls |

## Run locally

Requirements: Python 3.12+, Docker Engine, Terraform 1.10.5+, Trivy 0.58.2 and Gitleaks 8.24.2.

~~~bash
python .agents/production-readiness/runtime_smoke.py
python .agents/production-readiness/terraform_smoke.py --output ./artifacts/terraform
~~~

The runtime test creates a temporary stdlib-only HTTP fixture, generates its Dockerfile using the actual app-containerizer generator, builds the image, starts it with restrictive Docker settings, probes its health endpoint from inside the container and checks the effective runtime configuration. The temporary container is always removed. The image is removed unless `--keep-image` is supplied for a subsequent scan.

The Terraform smoke test creates a provider-free fixture in the requested output directory and runs native CLI checks in an isolated temporary copy. It does not configure a backend, provider, resource, cloud identity or credential.

## Release policy

- Every job must pass; skipped or failed jobs block the release gate.
- HIGH and CRITICAL Trivy findings block the workflow.
- Gitleaks findings block the workflow.
- The image SBOM and JSON reports are retained as workflow artifacts for 30 days.
- The workflow has read-only repository permissions and does not access deployment secrets.
- No Terraform apply/destroy, cloud provisioning, external deployment, image push or production release is performed.

## Remaining production evidence

This milestone is a safe CI integration gate, not a claim of complete production readiness. Before a production rollout, add provider-specific integration tests in an isolated cloud account, authenticated deployment rehearsals, workload identity/IAM review, signed image provenance, runtime observability, alert validation, load/resilience tests, backup/restore and rollback exercises. Those actions require an explicitly approved environment and credentials and are intentionally outside this workflow.
