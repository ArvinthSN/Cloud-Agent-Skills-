---
name: app-containerizer
description: Inspect Python, Node.js and Java repositories and safely generate Dockerfiles, .dockerignore and explicit local Compose dependencies.
---

# App Containerizer

## Purpose
Create reproducible container artifacts from verified repository facts.

## Inputs and outputs
- Input: one application directory, optional output path and explicitly selected local services.
- Output: Dockerfile, .dockerignore, optional compose.yaml and compact execution report.
- Detection: Python, Node.js and Java. Detection is heuristic; confirm uncertain startup commands and runtime details.

## Supported generation matrix
| Stack | Current generator support | Stop condition |
|---|---|---|
| Python | pip (requirements/pyproject), Poetry, uv | Missing manifest or unresolved startup command |
| Node.js | npm with package-lock.json | pnpm/yarn or missing lockfile/start command |
| Java | Maven executable JAR | Gradle or unconfirmed non-executable JAR |

Flask uses the detected module path and requires Gunicorn as a project runtime dependency. Django generation stops until the WSGI module is confirmed. The generator must not replace an unsupported package manager with npm or pip.

## Workflow
1. Follow AGENTS.md and .agents/standards/.
2. Scan the repository once with scripts/scan_repository.py. Reuse the scan unless the target or project revision changed.
3. Analyze with scripts/analyze_application.py. Load only references relevant to the detected stack.
4. Present stack, entry point, runtime, package manager, port, startup command, services and unknowns.
5. Obtain approval before writing. Never overwrite Docker assets without explicit approval and --overwrite.
6. Generate Dockerfile and .dockerignore. Generate Compose only for services explicitly selected by the user.
7. Run static validation. Run docker build only when requested and available.
8. Report artifacts and checks using PASS, FAIL, WARNING, SKIPPED or NOT_RUN.

## Safety and correctness
- Never copy .env files, credentials, tokens, private keys or local secrets into an image.
- Prefer explicit maintained base-image versions; avoid latest.
- Respect the detected lockfile and package manager. Unsupported combinations must stop clearly.
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
