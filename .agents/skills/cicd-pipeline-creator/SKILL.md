---
name: cicd-pipeline-creator
description: Create, improve or review a CI/CD pipeline (currently generated for GitHub Actions and Azure DevOps) from a repo and its tests. Detects the stack, renders a vetted platform template (build, scan, test, deploy), validates it, and writes terse notes. Use for any request about pipelines, CI/CD, workflows, build or deploy automation.
---

# CI/CD Pipeline Creator

## Support matrix
| platform | template | output path | status |
| --- | --- | --- | --- |
| github | templates/github/pipeline.yml | .github/workflows/pipeline.yml | supported |
| azure | templates/azure/azure-pipelines.yml | azure-pipelines.yml | supported |
| gitlab | templates/gitlab/.gitlab-ci.yml | .gitlab-ci.yml | starter asset; renderer not integrated |
| jenkins | templates/jenkins/Jenkinsfile | Jenkinsfile | starter asset; renderer not integrated |
| circleci | templates/circleci/config.yml | .circleci/config.yml | starter asset; renderer not integrated |

## Workflow
1. `python scripts/detect_stack.py <repo>` (compact JSON, one entry per project `dir`).
2. Platform = the single entry in `ci_platforms`. Map `github-actions` to `github` and `azure-devops` to `azure`. Several or none: ask ONE question. Never guess.
3. Read only the matching headings in `references/stacks.md` and `references/platforms/<platform>.md`. Never read whole folders. Never re-read a file.
4. `python scripts/render_pipeline.py <repo> <platform> --out <dir>`. For monorepos pass `--project-dir <detected-dir>`; the renderer must not silently choose the first project. Use `--overwrite` only after explicit approval. Fill leftover markers only from detect output or documented defaults.
5. `python scripts/validate_pipeline.py <file>`. Fix only what failed. Run once more. Stop after the second run.
6. Write the pipeline to its output path and a terse `PIPELINE_NOTES.md`. Do not commit or push.

## Production-grade guardrails
- Never leave unresolved `@@MARKER@@` values in the rendered YAML.
- Require platform-specific validation before accepting the file as production-ready.
- Enforce artifact-based deploys, branch guards, approval gates, and health checks.
- Allow only verified vendor actions and container images from the platform documentation.
- Reject secret leaks, insecure failure suppression, and echo-only deploy steps.

## Templates (MANDATORY)
- Never write a pipeline from memory. Start from the template and fill `@@MARKERS@@` only.
- Template missing: STOP and report it. Never recreate it.
- Raw templates are not valid YAML or Groovy. Validate rendered output only.
- Render one explicitly selected project `dir` in a monorepo. Never silently select the first project. Drop setup steps for languages not detected.
- Existing pipeline: merge and keep its custom steps. List breaking changes. Ask only before overwriting.
- Never mix syntax across platforms.

## Pipeline rules
- Order: build > scan > test > deploy.
- Build once. Upload only real build output, never a dummy file. Fail if the output is empty.
- Source and secret scans need no artifact and run parallel to build. Image scans consume the built image.
- Tests reinstall dev dependencies from cache. Do not rebuild.
- Scans fail on HIGH/CRITICAL. Banned on scan/test steps: `|| true`, `|| exit 0`, `continue-on-error`, `allow_failure: true`, `catchError`/`warnError`.
- Secret scan uses full git history.
- No tests detected: emit a warning and FAIL unless `ALLOW_NO_TESTS=true`. Publish JUnit and coverage on success or failure.
- Cache by lockfile hash. Set a timeout on every job.
- Install scanners via the publisher's official image, action or release binary. Never `pip install` or `npm -g` a Go binary scanner.

## Deploy rules
- Never on PRs. Staging is automatic on the default branch. Production needs an environment approval. State that approvers are configured on the platform, not in YAML.
- Deploy the downloaded build artifact, never the repo root. Production gets the exact artifact staging got (same artifact or slot swap).
- `DEPLOY_ENABLED != true`: skip with a visible warning (orange, never plain green). Unknown target: fail with a clear message.
- Runtime config (`DEPLOY_ENABLED`, `ALLOW_NO_TESTS`, app name, resource group, URLs) lives in platform variables, NOT in the YAML. Map it through `env:`. No `:-default` fallbacks for targets.
- A "set" check must also reject unresolved markers and unexpanded macros.
- Authenticate before any `az`/`aws`/`gcloud` command. Prefer OIDC or workload identity. Declare only the permissions used.
- Deploy jobs never cancel in flight (`cancel-in-progress: false`, `interruptible: false`).
- Post-deploy health check: `curl --fail --retry 5 --retry-all-errors` against a real URL, for staging and production.

## Anti-hallucination (MUST)
- Every action, task, orb or image must come from the template or `references/platforms/<platform>.md`. Names and versions are never taken from memory.
- Pin to a version or SHA from that file. Not verified: mark `# TODO(verify)` and list it in notes.
- Never leave an echo-only step. Missing info: failing guard plus TODO, or the one allowed question.
- Do not invent commands, paths, service connections, secrets or resource names.
- Never put credentials in YAML, logs or notes. Never ask the user to paste them.
- No unresolved `@@` marker may remain in the delivered file.

## Experimental platforms
Say "experimental" in the reply and notes. Run static checks only. Never write "validated". List native validators as SKIPPED.

## Validation
- Exit codes: 0 pass, 1 errors (blocker), 2 warnings only. Deliver on 0. On 2, list each warning in notes.
- Run native validators if installed (`actionlint`, `yamllint`). Report RAN or SKIPPED per tool.
- Parsing as YAML is not validation. Static checks are not proof the pipeline runs.
- Never claim the pipeline is connected, executed or deployed. Only a platform run proves that.

## PIPELINE_NOTES.md
One line each: Detected, Platform, Secrets/Variables (NAME - purpose), Assumptions, TODO(verify), Validation (tool RAN/SKIPPED, exit code). No prose, no sections beyond these.

## File discipline
- Touch only the pipeline file and `PIPELINE_NOTES.md`. Never edit the skill's own files during a run.
- No scratch, helper or test files. Use the OS temp dir and delete afterwards.
- Run `git status --short` at the end and remove anything unexpected.

## Reply (max 5 lines)
Stack | platform + status | stages generated | required secrets/variables | validation result and open TODO(verify). Do not paste YAML.

## Stop and ask (one question only)
Platform unclear, or deploy target unknown and the user wants a real deploy. For anything else, assume, record the assumption, and proceed.