# Cloud Agent Skills

A modular, safety-first cloud engineering skill set for analyzing application repositories and producing container, CI/CD and infrastructure artifacts.

The project is designed around a small shared harness: consistent skill contracts, compact context handoffs, approval gates and honest validation reports. Specialist skills remain independently invocable.

## Current capabilities

| Skill | Responsibility | Current implementation |
|---|---|---|
| app-containerizer | Inspect apps and generate Docker assets | Python, Node.js and Java heuristics; Dockerfile, Compose and static checks |
| cicd-pipeline-creator | Render and validate CI/CD workflows | Generated output currently wired for GitHub Actions and Azure DevOps |
| infra-creator | Plan and generate Terraform | AWS, Azure and GCP container-focused templates |

Templates for GitLab CI, Jenkins and CircleCI are present as starter assets. They are not yet fully integrated into the automated renderer and must not be presented as production-validated outputs.

## Repository layout

- AGENTS.md — repository-wide safety, workflow and context rules.
- .agents/standards/ — shared skill, output and token-efficiency contracts.
- .agents/schemas/ — machine-readable execution-plan and execution-report schemas.
- .agents/skills/ — specialist skills and their scripts, templates, references and tests.
- .github/workflows/ — repository quality checks.

## Executable orchestration

The Cloud Engineering Orchestrator creates a single bounded project scan and versioned JSON handoffs for the selected specialist skills.

```bash
python .agents/skills/cloud-engineering-orchestrator/scripts/orchestrate.py plan \
  --project ./my-app \
  --goal "Containerize the app and prepare CI plus Terraform" \
  --skills app-containerizer,cicd-pipeline-creator,infra-creator \
  --provider aws \
  --platform github \
  --run-dir ./.cloud-agent/runs/my-app

# Review the plan and each handoff before approving local generation.
python .agents/skills/cloud-engineering-orchestrator/scripts/orchestrate.py execute \
  --run-dir ./.cloud-agent/runs/my-app \
  --approve
```

Use `--project-dir backend` for monorepos, `--compose-services postgresql,redis` only for explicitly selected local dependencies, and `--overwrite` only when replacing existing generated files. The `.cloud-agent/` run directory is ignored by repository scans.

The run contains `project-context.json`, `execution-plan.json`, `handoffs/` and `execution-report.json`. Execution writes local artifacts only; it never applies Terraform, provisions cloud resources, deploys, publishes images or pushes commits.

## Quick start

Each skill has its own SKILL.md with invocation guidance and examples.

For local Python checks, install pytest and run:
- python -m compileall -q .agents/skills
- pytest -q .agents/skills/app-containerizer/tests .agents/skills/infra-creator/tests
- python .agents/skills/cicd-pipeline-creator/scripts/test_examples.py

Run Terraform validation only where the Terraform CLI is installed. Static validation does not prove cloud resources can be provisioned.

## Engineering principles

1. Inspect before generating.
2. Evidence before assumptions.
3. Approval before destructive or external actions.
4. Reuse structured context between skills.
5. Validate generated artifacts with native tools when available.
6. Report PASS, FAIL, WARNING, SKIPPED and NOT_RUN accurately.
7. Never deploy or provision as an implicit side effect.

## Status and limitations

This repository is actively being hardened. A template is not automatically a supported generator. A successful YAML parse is not proof that a pipeline executes. Terraform validation is not a deployment. Cloud-specific behavior still requires provider credentials and an approved environment.
