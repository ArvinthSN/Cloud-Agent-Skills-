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

# When an execution process is interrupted, recover and restart from the
# pre-run output snapshot using the same reviewed plan.
python .agents/skills/cloud-engineering-orchestrator/scripts/orchestrate.py resume \
  --run-dir ./.cloud-agent/runs/my-app \
  --approve

# Recovery can also be run separately before inspecting/retrying.
python .agents/skills/cloud-engineering-orchestrator/scripts/orchestrate.py recover \
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
4. Validate the declared dependency graph and execute selected generators in topological dependency order. When containerization is selected, CI/CD and infrastructure generation wait for it to complete.
5. Pass precomputed handoff data into the specialist scripts. CI renderer accepts --context and skips its own discovery scan.
6. Run available static validators and write execution-report.json with per-skill results.
7. Block dependent skills when a prerequisite is not completed. If any selected skill fails, is blocked or is partial, roll back every generated project artifact to its pre-run state.
8. Hold a non-blocking OS-level lock for each run directory. Concurrent execute/resume/recover commands are rejected.
9. Persist execution state atomically before and after each specialist. The journal records attempt, current skill, completed skills and transaction phase.
10. On process interruption, use recover to restore the pre-run snapshot or resume to recover and restart the workflow from a clean output baseline. Resume reruns the full selected workflow rather than trusting partial outputs.

Exit codes: 0 completed, 1 failed/blocked, 2 partial. A rolled-back run never reports generated artifacts as committed.

### resume and recover
- Every run uses .execution.lock, .execution-state.json and a persistent .transaction/ backup directory.
- The OS releases the lock automatically when a process exits or crashes. The lock file remains in place and is safely reused by subsequent invocations.
- The journal is atomically replaced and flushed after every state transition. A running/rolling_back transaction is restored from its persistent snapshot before it can be retried.
- resume requires the original local-generation approval again and restarts all selected skills from the pre-run baseline; it does not trust files created by an interrupted attempt.
- recover requires explicit approval and restores the original output snapshot without starting generators. Run resume afterward to retry.
- A committed journal is final: resume refuses it, and a new plan is required for a fresh execution.

## Handoff contract
Every handoff is validated against .agents/schemas/skill-handoff.schema.json and includes:
- schema version, run ID, skill ID, project root and declared prerequisite skill IDs;
- Git revision and a SHA-256 project snapshot fingerprint;
- goal and approval requirement;
- compact skill-specific inputs and output paths.

The canonical context stores file paths, sizes, hashes and detected metadata only. It does not copy application source code or environment variable values. Secret-like environment variable names may be included as metadata; secret values must never be read into handoffs.

## Context cache and validation
- Reuse context cache entries keyed by the canonical project root, scanner version and full content snapshot hash. The repository is still fingerprinted on every plan/execute freshness check; a changed snapshot cannot hit the cache.
- Default cache location: <project>/.cloud-agent/context-cache. Use --no-cache to disable it or --cache-dir to move it outside the project.
- Validate project context, plan, handoffs and execution report against Draft 2020-12 JSON Schemas. Install jsonschema with python -m pip install jsonschema; execution fails closed if the validator is missing or a contract is invalid.

## Safety and scope
- --approve authorizes only local file generation described by the reviewed plan.
- --overwrite separately authorizes replacing existing generated files. The orchestrator snapshots generated targets before execution and restores them on any failed/blocked/partial workflow. Failed workflows are rolled back as a unit; generated outputs are not left in a partially applied state.
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
- execution-report.json — statuses, artifacts, checks, risks and manual actions;
- .execution-state.json — durable attempt journal and transaction recovery metadata;
- .transaction/ — persistent backups retained until commit or successful rollback.

The report status is completed, partial, blocked or failed. Each check is PASS, FAIL, WARNING, SKIPPED or NOT_RUN. Missing tools never count as successful validation.
