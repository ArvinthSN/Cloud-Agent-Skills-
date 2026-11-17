---
name: cloud-engineering-orchestrator
description: Execute coordinated containerization, CI/CD and Terraform workflows using one bounded repository scan and versioned JSON handoffs.
---

# Cloud Engineering Orchestrator

## Purpose
Create a reusable execution plan and coordinate specialist generators from a single versioned project context.

## CLI

Run from the repository root:

~~~bash
python .agents/skills/cloud-engineering-orchestrator/scripts/orchestrate.py plan \
  --project ./my-app \
  --goal "Containerize the application and prepare CI plus Terraform" \
  --skills app-containerizer,cicd-pipeline-creator,infra-creator \
  --provider aws \
  --platform github \
  --run-dir ./.cloud-agent/runs/my-app

# Review execution-plan.json, project-context.json and handoffs/ first.
python .agents/skills/cloud-engineering-orchestrator/scripts/orchestrate.py execute \
  --run-dir ./.cloud-agent/runs/my-app \
  --approve
~~~

Add --project-dir backend when a monorepo has multiple applications. Add --compose-services postgresql,redis only when those local dependencies are intentionally requested. Add --overwrite as a separate approval when an existing Dockerfile, pipeline or Terraform output must be replaced.

## Commands

### plan
1. Validate requested skills and required provider/platform inputs.
2. Perform one bounded read-only scan, skipping VCS, dependency, cache, generated and local state directories.
3. Record a content fingerprint and Git revision where available.
4. Write project-context.json, execution-plan.json and one handoff.json per selected skill.
5. Reuse one project selection across containerizer and CI; fail closed on ambiguous monorepos or unsupported CI stacks.

Planning creates run metadata only. It does not generate application artifacts.

### execute
1. Require --approve.
2. Verify that the project fingerprint still matches the plan. A changed project requires a fresh plan.
3. Validate run IDs and skill identity in every handoff.
4. Execute only selected local generators in dependency order.
5. Pass precomputed handoff data into the specialist scripts. CI renderer accepts --context and skips its own discovery scan.
6. Run available static validators and write execution-report.json with per-skill results.
7. Continue independent skills after an individual skill failure and return partial status when appropriate.

Exit codes: 0 completed, 1 failed/blocked, 2 partial.

## Handoff contract
Every handoff follows .agents/schemas/skill-handoff.schema.json and includes:
- schema version, run ID, skill ID and project root;
- Git revision and a SHA-256 project snapshot fingerprint;
- goal and approval requirement;
- compact skill-specific inputs and output paths.

The canonical context stores file paths, sizes, hashes and detected metadata only. It does not copy application source code or environment variable values. Secret-like environment variable names may be included as metadata; secret values must never be read into handoffs.

## Safety and scope
- --approve authorizes only local file generation described by the reviewed plan.
- --overwrite separately authorizes replacing existing generated files.
- Never execute terraform apply/destroy, cloud provisioning, deployment, image publishing, secret retrieval or Git push.
- Terraform validation runs only if the CLI is installed. Missing Terraform is NOT_RUN.
- Pipeline rendering is not pipeline execution. Container static validation is not a Docker build.
- No secret values, tokens or local .env contents are written to context files.
- Run directories must be outside the project or under the ignored .cloud-agent/ folder.
- A stale plan is rejected; re-run plan after source changes.
- Project discovery is heuristic. Review stack, framework, runtime, service and architecture findings before approval.

## Outputs
The run directory contains:
- project-context.json — canonical bounded scan and project fingerprint;
- execution-plan.json — selected skills, assumptions, provider/platform and outputs;
- handoffs/<skill>/handoff.json — compact versioned input for each specialist;
- handoffs/<skill>/* — derived intermediate files for executed skills;
- execution-report.json — statuses, artifacts, checks, risks and manual actions.

The report status is completed, partial, blocked or failed. Each check is PASS, FAIL, WARNING, SKIPPED or NOT_RUN. Missing tools never count as successful validation.
