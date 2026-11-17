# Enterprise-Grade Upgrade Plan for infra-creator

## Objective
Turn the current repo-aware Terraform generator into a governed infrastructure platform that is suitable for production use, not just a strong starter generator.

## Design goals
- Generate infrastructure only from verified repository evidence
- Enforce security and governance constraints by default
- Separate repo analysis from policy evaluation and IaC rendering
- Produce reviewable, auditable outputs for each environment
- Support staging and production promotion with explicit approval gates
- Keep Terraform valid, policy-safe, and cost-conscious

## Architectural layers

### 1. Repo intelligence layer
Responsible for scanning and classifying the application repository.

Inputs:
- app language and framework
- runtime and dependency manager
- database and message bus usage
- service topology and app boundaries
- Docker / compose / runtime hints
- environment and secret requirements

Outputs:
- normalized app manifest
- architecture confidence and assumptions
- resource requirements list

### 2. Policy engine
Responsible for enforcing enterprise guardrails before generation proceeds.

Rules:
- no hardcoded credentials
- no public DBs by default
- private networking preferred
- encryption required at rest and in transit where supported
- least-privilege identity only
- cost-sensitive defaults for dev and test environments
- environment separation for dev, staging, and prod
- explicit approval required for any public ingress or production exposure

### 3. Cloud decision layer
Responsible for selecting the target cloud and resource model.

Supported providers:
- AWS
- Azure
- GCP

This layer should choose the correct service mapping based on evidence and policy constraints, not repo guesses alone.

### 4. Infrastructure manifest builder
Build a structured manifest before Terraform rendering.

Example fields:
- app_name
- environment
- cloud_provider
- compute_mode
- database_type
- ingress_type
- networking_model
- identity_model
- storage_requirements
- observability_requirements
- deployment_targets
- rollback_strategy

### 5. Terraform renderer
Render environment-aware Terraform based on the manifest and provider templates.

Output should include:
- main.tf
- providers.tf
- versions.tf
- variables.tf
- outputs.tf
- terraform.tfvars.example
- README.md
- backend configuration guidance

### 6. Validation and governance layer
Run validation before accepting output.

Checks:
- terraform fmt
- terraform init -backend=false
- terraform validate
- policy checks for exposed DBs and public resources
- required tagging rules
- naming conventions and environment tags
- cost model and resource size sanity checks

### 7. Environment promotion layer
Support explicit promotion gates.

Rules:
- dev can be auto-generated
- staging requires configuration review
- production requires approval and rollout controls
- rollback plan documented before apply
- state storage guidance provided

### 8. Audit and review layer
Each generated project should include:
- assumptions log
- warnings and TODOs
- security review notes
- resource map
- deployment notes
- rollback plan

## Production hardening checklist
- private networking is default
- public access is explicit and reviewed
- least-privilege IAM and service accounts
- DB encryption, backups, and retention policy
- secret handling externalized from Git and Terraform state
- remote state guidance for team use
- health checks and readiness rules
- environment-specific variable mapping
- cost and sizing review for non-trivial deployments

## Release gates
A generated environment is considered ready only when all of the following pass:
- repo evidence matched to architecture
- policy validation passed
- cloud-specific mapping validated
- Terraform rendered without unresolved placeholders
- security checks passed
- environment approval conditions documented
- rollback path exists

## Roadmap

### Phase 1: stabilize the foundation
- Validate all repo detection outputs
- Reduce false positives in architecture classification
- Make provider selection evidence-based and explainable

### Phase 2: add governance to generation
- Add policy evaluation layer
- Add private-network and encryption defaults
- Add environment-specific templates

### Phase 3: add operational controls
- Add backend/state guidance
- Add cost/tags/audit output
- Add rollback and promotion notes

### Phase 4: enterprise readiness
- Add compliance-ready templates
- Add environment approval flow specification
- Add drift and change review structure

## Success definition
The project is enterprise-grade when it can:
- generate secure Terraform from repo evidence
- explain why a provider and architecture were chosen
- enforce policies before writing infra
- produce auditable outputs for stakeholders
- provide clear promotion and rollback guidance
- remain safe for team adoption without manual security cleanup

## Current status
This project is already a strong infra scaffolding tool. It is not yet a full enterprise platform engine, but it has the right foundation to evolve into one.
