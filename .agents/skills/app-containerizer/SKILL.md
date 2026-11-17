---
name: app-containerizer
description: Inspect Python, Node.js and Java repositories and safely generate Dockerfiles, .dockerignore and explicit local Compose dependencies.
---

# App Containerizer

## Purpose
Create reproducible container artifacts from verified repository facts.

## Inputs and outputs
- Input: application directory, optional output path and explicitly selected local services.
- Output: Dockerfile, .dockerignore, optional compose.yaml, compact execution report.
- Supported detection: Python, Node.js and Java. Detection is heuristic; generated commands must be confirmed when uncertain.

## Workflow
1. Follow repository instructions in AGENTS.md and shared standards in .agents/standards/.
2. Scan the repository once with scripts/scan_repository.py. Reuse the scan unless the target or project revision changed.
3. Analyze with scripts/analyze_application.py. Review only the applicable reference sections.
4. Present detected stack, entry point, runtime, dependency manager, port, startup command, services and unknowns.
5. Obtain approval before writing. Never overwrite Docker assets without explicit approval and --overwrite.
6. Generate Dockerfile and .dockerignore. Generate Compose only for services explicitly selected by the user.
7. Run static validation. Run docker build only when requested and available.
8. Report artifacts and checks using PASS, FAIL, WARNING, SKIPPED or NOT_RUN.

## Safety and correctness
- Never copy .env files, credentials, tokens, private keys or local secrets into an image.
- Prefer maintained, explicit base-image versions; avoid latest.
- Use lockfile-aware installation. Do not silently replace Poetry, pnpm, yarn or Gradle with pip/npm/Maven.
- Use exec-form startup commands and a non-root runtime user where supported.
- Do not invent ports, startup commands or service dependencies.
- Preserve existing files unless explicit overwrite approval was provided.
- Never push images, deploy, provision infrastructure or run arbitrary application scripts.
- Missing Docker means NOT_RUN, not PASS. Static inspection is not a successful image build.

## CLI
~~~bash
python scripts/scan_repository.py --path ./app --output scan.json
python scripts/analyze_application.py --input scan.json --output plan.json
python scripts/generate_dockerfile.py --path ./app --plan plan.json --approve
python scripts/generate_compose.py --path ./app --plan plan.json --services postgresql --approve
python scripts/validate_container.py --path ./app
~~~

Add --overwrite only after reviewing existing files. Add --build only when an actual Docker build is desired.
