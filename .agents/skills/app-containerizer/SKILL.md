---
name: app-containerizer
description: Inspect application repositories and generate secure Docker artifacts, including Dockerfiles, Compose files, .dockerignore files, and image-ready container setup with validation.
---
# App Containerizer

## Purpose
Convert an existing application repository into a reproducible container setup and generate the Docker assets needed to build, run, and validate the app in containers.

## Workflow
1. Inspect the repository using `scripts/scan_repository.py`.
2. Analyze the scan using `scripts/analyze_application.py`.
3. Review `references/` and present the proposed stack, runtime, port, startup command, dependencies and assumptions.
4. Obtain approval before writing or replacing files.
5. Generate Dockerfile and `.dockerignore`; generate Compose only when justified.
6. Run static validation. Run a Docker build only when Docker is installed and the user explicitly requests it.
7. Report generated files, PASS/FAIL/WARNING/SKIPPED/NOT_AVAILABLE statuses and remaining unknowns.

## Supported stacks
- Python: FastAPI, Flask, Django; pip and Poetry indicators.
- Node.js: Express, NestJS, React/Vite; npm, pnpm and yarn.
- Java: Spring Boot; Maven and Gradle.

Detection is heuristic. Do not guess when evidence is insufficient. Ask the user to confirm unknown startup commands, ports or service dependencies.

## Safety and engineering rules
- Prefer explicit maintained base-image versions; avoid `latest`.
- Respect dependency lockfiles.
- Use multi-stage builds when useful.
- Run as non-root where practical.
- Never copy `.env`, credentials, tokens, private keys or secret files into images.
- Never embed secrets in Dockerfile or Compose configuration.
- Use exec-form CMD/ENTRYPOINT.
- Do not add databases or caches without evidence or explicit selection.
- Never overwrite existing Docker files without explicit approval.
- Never push to Git, deploy, provision infrastructure, delete source files or run arbitrary app scripts.
- Never claim a build or runtime test passed unless it actually ran and succeeded.

## CLI
```bash
python scripts/scan_repository.py --path ./app --output scan.json
python scripts/analyze_application.py --input scan.json --output plan.json
python scripts/generate_dockerfile.py --path ./app --plan plan.json --approve
python scripts/generate_compose.py --path ./app --plan plan.json --services postgresql --approve
python scripts/validate_container.py --path ./app
```
Add `--overwrite` only after reviewing existing files. Add `--build` to validation only when an actual Docker build is desired.
