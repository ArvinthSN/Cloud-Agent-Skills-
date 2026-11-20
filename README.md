# Cloud Agent Skills

A modular, safety-first cloud engineering skill set for analyzing application repositories and producing container, CI/CD and infrastructure artifacts.

The project is designed around a shared execution harness: bounded project discovery, versioned JSON contracts, compact specialist handoffs, explicit approval gates, dependency-aware orchestration and recoverable local file transactions. Specialist skills remain independently invocable.

## Current capabilities

| Skill | Responsibility | Current implementation |
|---|---|---|
| app-containerizer | Inspect apps and generate Docker assets | Python, Node.js and Java detection; supported package-manager-aware Dockerfiles, Compose and static checks |
| cicd-pipeline-creator | Render and validate CI/CD workflows | Integrated renderers for GitHub Actions, Azure DevOps, GitLab CI, Jenkins and CircleCI |
| infra-creator | Plan and generate Terraform | AWS ECS Fargate, Azure Container Apps and GCP Cloud Run container-focused templates |

The CI renderers produce reviewable local files. Platform-native linting and actual pipeline runs still require each target provider. Terraform generation and validation do not provision cloud infrastructure.

## Repository layout

- AGENTS.md — repository-wide safety, workflow and context rules.
- .agents/standards/ — shared skill, output and token-efficiency contracts.
- .agents/schemas/ — versioned project-context, plan, handoff, report and execution-state schemas.
- .agents/skills/ — specialist skills and their scripts, templates, references and tests.
- .github/workflows/ — cross-platform repository quality checks.

## Executable orchestration

The Cloud Engineering Orchestrator creates one bounded project scan and versioned JSON handoffs for the selected specialist skills.

~~~bash
python .agents/skills/cloud-engineering-orchestrator/scripts/orchestrate.py plan \
  --project ./my-app \
  --goal "Containerize the app and prepare CI plus Terraform" \
  --skills app-containerizer,cicd-pipeline-creator,infra-creator \
  --provider aws \
  --platform github \
  --run-dir ./.cloud-agent/runs/my-app

# Review execution-plan.json, project-context.json and every handoff before approval.
python .agents/skills/cloud-engineering-orchestrator/scripts/orchestrate.py execute \
  --run-dir ./.cloud-agent/runs/my-app \
  --approve
~~~

Use --project-dir backend for monorepos, --compose-services postgresql,redis only for explicitly selected local dependencies, and --overwrite only when replacing existing generated files. Use --no-cache to disable reusable project context or --cache-dir to select another cache directory.

Each execution uses two levels of non-blocking OS locks: one for the run directory and one shared by executions targeting the same project root. The durable state journal records transaction phase and recovery metadata. When a process is interrupted, use resume --run-dir ./.cloud-agent/runs/my-app --approve to restore the pre-run snapshot and restart the complete workflow, or recover --run-dir ./.cloud-agent/runs/my-app --approve to restore without retrying. Resume requires approval again and does not trust partial outputs from the interrupted attempt.

The run contains project-context.json, execution-plan.json, handoffs/ and execution-report.json. The execute/resume CLI prints a compact receipt with artifact and check counts plus the report path; the full execution evidence stays in execution-report.json, avoiding duplicate report text in agent context. Execution follows a validated dependency graph: when containerization is selected, CI/CD and infrastructure generation wait for it to complete. A failed, blocked or partial workflow rolls back the declared generated output paths to their pre-run state. The context cache is reused only for an identical project root, scanner version and full content snapshot; project freshness is still verified. Install jsonschema with python -m pip install jsonschema. Execution writes local artifacts only; it never applies Terraform, provisions cloud resources, deploys, publishes images or pushes commits.

## CI/CD platform generation

The CI/CD renderer supports five explicit platform arguments:

~~~bash
python .agents/skills/cicd-pipeline-creator/scripts/render_pipeline.py ./my-app github --out ./my-app/.github/workflows
python .agents/skills/cicd-pipeline-creator/scripts/render_pipeline.py ./my-app azure --out ./my-app
python .agents/skills/cicd-pipeline-creator/scripts/render_pipeline.py ./my-app gitlab --out ./my-app
python .agents/skills/cicd-pipeline-creator/scripts/render_pipeline.py ./my-app jenkins --out ./my-app
python .agents/skills/cicd-pipeline-creator/scripts/render_pipeline.py ./my-app circleci --out ./my-app
~~~

Current application-build coverage is Python (pip, Poetry, uv) and Node.js (npm with package-lock.json). Other stacks and package managers are rejected rather than guessed. GitHub Actions dependencies in the generated template are pinned to full commit SHAs. Other platform templates use explicit scanner/runtime image tags; pin approved production images to registry digests as part of provider rollout.

CircleCI command steps have explicit no-output timeouts; total execution limits remain governed by the CircleCI plan. GitHub Actions job permissions and timeouts are checked by the static validator.\n\nGenerated deployment stages remain disabled or fail closed until target-specific deployment commands, credentials/workload identity and protected environments are configured. The renderer does not create provider-side secrets or environments.

## Quick start and tests

Install the shared test dependencies:

~~~bash
python -m pip install pytest pyyaml jsonschema
python -m compileall -q .agents/skills
pytest -q tests/harness
pytest -q .agents/skills/app-containerizer/tests
pytest -q .agents/skills/infra-creator/tests
pytest -q .agents/skills/cicd-pipeline-creator/tests
python .agents/skills/cicd-pipeline-creator/scripts/test_examples.py
~~~

The CI workflow runs the suite on Python 3.11 and 3.12 across Ubuntu, Windows and macOS. Terraform CLI validation runs only where the CLI is installed. Provider-native validation and controlled integration tests are separate release gates.

## Engineering principles

1. Inspect before generating.
2. Evidence before assumptions.
3. Approval before destructive or external actions.
4. Reuse validated structured context between skills.
5. Validate generated artifacts with native tools when available.
6. Report PASS, FAIL, WARNING, SKIPPED and NOT_RUN accurately.
7. Never deploy or provision as an implicit side effect.
8. Keep generated artifacts reviewable, deterministic and recoverable.

## Known boundaries

- Project detection is heuristic; review detected facts and generated commands before approval.
- Locking is local-filesystem and project-root scoped. It is not a distributed lock for remote workers or a shared filesystem with unsupported locking semantics.
- Resume restores the original snapshot and reruns the complete workflow; it is not checkpoint-level continuation.
- The app containerizer's static validation is not an image build unless Docker build is explicitly requested.
- GitLab CI Lint, CircleCI CLI, Jenkins controller validation and Azure DevOps runs require provider-specific environments.
- Terraform fmt/init/validate is not a security audit, deployment or proof that cloud quotas, IAM, policies and networking are correct.
- Actual production readiness requires provider-native integration tests, review of image digests/action pins, security policy checks, observability and a controlled cloud deployment rehearsal.

## Application intelligence and automatic skill selection

The orchestrator includes a deterministic Phase 1 intelligence layer. It creates an evidence-backed architecture profile, resolves prerequisites and can select skills from the requested goal.

Use `--skills auto` to enable goal-driven selection. Supply `--platform` when requesting CI/CD generation and `--provider` when requesting infrastructure generation; the planner records missing requirements instead of guessing. Existing comma-separated explicit skill selection remains supported.

Each plan includes `architecture-profile.json` and `skill-selection.json` alongside the execution plan and versioned specialist handoffs. Architecture confidence is an evidence-based heuristic and must be reviewed before approving generation.


## Phase 2: output verification

The orchestrator now verifies generated artifacts before committing its output transaction. It checks artifact presence, runs the existing container/CI/Terraform validators, invokes available native validators and automatically uses installed Gitleaks, Trivy and Checkov scanners. Trivy also scans a locally built image when an approved Docker build is requested. Missing optional tools are recorded as `NOT_RUN`, never as a pass. Mandatory verification failures trigger the existing rollback mechanism.

Docker image builds and Terraform plans require explicit opt-in:

~~~bash
python .agents/skills/cloud-engineering-orchestrator/scripts/orchestrate.py execute \\
  --run-dir ./.cloud-agent/runs/my-app --approve \\
  --docker-build --terraform-plan
~~~

Docker builds run with networking disabled, no base-image pull and temporary-image cleanup. Terraform plans run in a temporary source copy with backend and refresh disabled and cloud credential environment variables removed. Terraform provider plugins and external data sources can still execute code, so review Terraform before requesting a plan. Neither check applies infrastructure or deploys anything.

Re-run checks after a committed execution with `orchestrate.py verify --run-dir <run-dir>`. Full evidence is stored in `verification-report.json`; missing tools and warnings remain visible in the report and may make verification partial.



## Phase 3: benchmark harness

A 24-case benchmark dataset covers Python/Node/Java/Go/Rust containerization, CI/CD generation, AWS/Azure/GCP Terraform generation and end-to-end scenarios. Run `python benchmarks/scripts/benchmark.py --validate-only` to validate the dataset. To score generated artifacts, prepare one workspace directory per case ID and run `python benchmarks/scripts/benchmark.py --workspace ./benchmark-workspace --output ./benchmark-report.json`. The report scores correctness, completeness, security, reproducibility and efficiency. Reproducibility and efficiency are marked unmeasured unless explicit run metadata is supplied; the checked-in scenarios are not claimed as real-world benchmark results. See `benchmarks/README.md` for the corpus contract and scoring details.
