---
name: cicd-pipeline-creator
description: Detect a supported application stack and render or review pipelines for GitHub Actions, Azure DevOps, GitLab CI, Jenkins or CircleCI with guarded deployment stages.
---

# CI/CD Pipeline Creator

## Purpose
Generate a project-specific CI pipeline from a reviewed platform template and verified repository facts.

## Current renderer support
| Platform argument | Generated file | Static/native validation |
|---|---|---|
| github | .github/workflows/pipeline.yml | YAML, supply-chain checks, actionlint when installed |
| azure | azure-pipeline.yml | YAML and repository policy checks; validate in Azure DevOps before use |
| gitlab | .gitlab-ci.yml | YAML and repository policy checks; GitLab CI Lint requires the target instance |
| jenkins | Jenkinsfile | Structural checks; Groovy compiler when installed; validate with the configured Jenkins controller |
| circleci | .circleci/config.yml | YAML and repository policy checks; CircleCI CLI when installed |

All five renderers are integrated. Static validation is not equivalent to a provider-native lint, pipeline execution or deployment.

## Supported application stacks
- Python with pip, Poetry or uv when the detector finds a real artifact-producing package build.
- Node.js with npm and package-lock.json. pnpm, Yarn and unlocked npm projects are not supported by this renderer yet.
- Other stacks are detected but fail closed until a tested build template is implemented.

## Workflow
1. Follow AGENTS.md and .agents/standards/.
2. Run scripts/detect_stack.py once. It emits compact project and platform facts.
3. Select exactly one target platform. Never infer a target from a repository's existing config when multiple platforms are present.
4. If a monorepo is detected, require --project-dir for the exact application.
5. Review detected package manager, runtime version, install/build/test commands, lockfile and artifact directory. Treat repository-derived commands as untrusted input.
6. Confirm the deploy target and required runtime variables before enabling a real deploy workflow. Generated templates intentionally keep deployment disabled or fail closed until target-specific commands and protected environments are configured.
7. Load only the selected platform and stack reference sections. Render only through scripts/render_pipeline.py.
8. Preserve existing output. Use --overwrite only after explicit approval.
9. Run scripts/validate_pipeline.py and native validators when installed. Fix blockers and report remaining warnings and skipped checks.
10. Report output paths, required secret/variable names, assumptions, unresolved risks and whether native validators ran.

## Production guardrails
- No unresolved template markers, fabricated build commands, placeholder deployments or invented cloud resource names.
- Build once; deploy the exact produced artifact, not a fresh source checkout.
- GitHub Actions references must use full immutable commit SHAs. Review and refresh SHA pins deliberately.
- Container image versions are explicit but tag-based starter defaults; high-assurance use must pin approved images to registry digests and review provenance.
- Secret scans use full Git history where platform support permits. Security and test failures must fail the pipeline.
- No tests detected: fail by default; permit an override only through an explicit platform variable.
- Deploy only from the intended protected branch, never pull requests. Production requires provider-native approval/protection configuration.
- Prefer OIDC/workload identity to long-lived cloud credentials. Never place secret values in YAML or notes.
- Commands read from package manifests are executable shell input. Review them before approving the generated pipeline. The renderer rejects multiline/oversized commands and unsafe working-directory paths; this does not make a malicious project safe.
- Require timeouts and lockfile-keyed dependency caching.
- Static validation does not prove a pipeline ran. Only an actual platform run proves execution.

## Validation states
Use PASS, FAIL, WARNING, SKIPPED or NOT_RUN. A missing validator is NOT_RUN, not PASS. YAML parsing or structural checks alone are not provider-native validation.

## CLI
~~~bash
python scripts/detect_stack.py ./app

python scripts/render_pipeline.py ./app github --out ./outputs
python scripts/render_pipeline.py ./app azure --out ./outputs
python scripts/render_pipeline.py ./app gitlab --out ./outputs
python scripts/render_pipeline.py ./app jenkins --out ./outputs
python scripts/render_pipeline.py ./app circleci --out ./outputs

python scripts/validate_pipeline.py ./outputs/pipeline.yml --json
~~~

For a monorepo, add --project-dir backend (or the exact detected project directory). The renderer writes only local configuration files; it does not connect to a CI platform, create secrets, approve protected environments, deploy or release.
