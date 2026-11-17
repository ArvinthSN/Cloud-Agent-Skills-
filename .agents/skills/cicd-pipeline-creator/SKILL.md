---
name: cicd-pipeline-creator
description: Detect an application stack and render or review CI/CD pipelines with explicit platform selection, guarded deploy stages and static validation.
---

# CI/CD Pipeline Creator

## Purpose
Generate a project-specific pipeline from a reviewed platform template and verified repository facts.

## Current renderer support
| Platform | Template | Status |
|---|---|---|
| GitHub Actions | templates/github/pipeline.yml | Renderer-supported |
| Azure DevOps | templates/azure/azure-pipelines.yml | Renderer-supported |
| GitLab CI | templates/gitlab/.gitlab-ci.yml | Starter asset only |
| Jenkins | templates/jenkins/Jenkinsfile | Starter asset only |
| CircleCI | templates/circleci/config.yml | Starter asset only |

Do not claim renderer support or production validation for starter assets.

## Workflow
1. Follow AGENTS.md and .agents/standards/.
2. Run scripts/detect_stack.py once. It emits compact project and platform facts.
3. Map github-actions to github and azure-devops to azure. If several platforms exist, ask which one to target; never guess.
4. If a monorepo is detected, require --project-dir for the exact project.
5. Confirm the deploy target and required runtime variables before generating a real deploy workflow. Do not infer Azure App Service merely because it is a sample template.
6. Load only the selected platform and stack reference sections. Render only through scripts/render_pipeline.py.
7. Preserve existing output. Use --overwrite only after explicit approval.
8. Run scripts/validate_pipeline.py and native validators when installed. Fix blockers and report remaining warnings.
9. Report output paths, required secret/variable names, unresolved TODOs and whether native validators ran.

## Production guardrails
- No unresolved template markers, fake commands, echo-only deployments or invented cloud resource names.
- Build once; deploy the produced artifact, not the source checkout.
- Secret scans use full Git history. Security/test failures must fail the pipeline.
- No tests detected: fail by default; permit override only through an explicit platform variable.
- Deploy only from the intended protected branch, never pull requests. Production requires a platform-configured approval gate.
- Prefer OIDC/workload identity to long-lived cloud credentials.
- Require timeouts and lockfile-keyed dependency caching.
- Never place secret values in YAML or notes.
- Static validation does not prove a pipeline ran. Only an actual platform run proves execution.

## Validation states
Use PASS, FAIL, WARNING, SKIPPED or NOT_RUN. A missing validator is NOT_RUN, not PASS. YAML parsing alone is not platform validation.

## CLI
~~~bash
python scripts/detect_stack.py ./app
python scripts/render_pipeline.py ./app github --out ./outputs --project-dir backend
python scripts/validate_pipeline.py ./outputs/pipeline.yml --json
~~~

The renderer currently supports Python and Node.js project templates only. Unsupported stacks must stop with a clear message rather than producing a misleading pipeline.
