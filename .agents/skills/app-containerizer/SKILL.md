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
| Java | Maven executable JAR; Gradle Spring Boot `bootJar` | Unknown build manager, missing build manifest, or unconfirmed executable JAR |

Flask uses the detected module path and requires Gunicorn as a project runtime dependency. Django generation stops until the WSGI module is confirmed. The generator must not replace an unsupported package manager with npm or pip.

## Workflow
1. Follow AGENTS.md and .agents/standards/.
2. Scan the repository once with scripts/scan_repository.py. Reuse the scan unless the target or project revision changed. If `scan_truncated` is true, stop and narrow the scan scope; never generate from an incomplete scan.
3. Analyze with scripts/analyze_application.py. Load only references relevant to the detected stack.
4. Present stack, entry point, runtime, package manager, port, startup command, services and unknowns.
5. Obtain approval before writing. Never overwrite Docker assets without explicit approval and --overwrite.
6. Generate Dockerfile and .dockerignore. Generate Compose only for services explicitly selected by the user.
7. Run static validation and Hadolint when installed. Run Docker build only with explicit --build approval; the build uses network=none, does not pull images and removes its temporary image.
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

When `scan_repository.py --output <path>` is used, the full scan is saved to that JSON artifact and stdout returns only a compact receipt. Omit `--output` when a downstream tool explicitly needs the full JSON on stdout.

Add --overwrite only after reviewing existing files. Add --build only when an actual Docker build is desired. The Docker build executes Dockerfile instructions inside the build environment; review the Dockerfile first and ensure required base images/dependencies are already cached because network access is disabled.

## Runtime and build-tool detection

- **Python:** Read `project.requires-python` (PEP 621) or Poetry's Python constraint from `pyproject.toml`. For a range such as `>=3.14,<4.0`, select the declared lower bound (`3.14`) for the base image and preserve the original constraint in the plan. If no usable constraint is present, use the documented fallback (`3.12`) and mark the source as default.
- **Java:** Select the root Gradle build when present; if root Maven and Gradle manifests coexist, require a checked-in Gradle wrapper to select Gradle; otherwise stop as ambiguous. If no root Gradle manifest exists, select the root Maven build. Read Java toolchain/source compatibility from the selected build file. For Gradle, read the version from `gradle/wrapper/gradle-wrapper.properties` when available; otherwise use the generator's documented fallback.
- **Gradle Spring Boot:** Build `bootJar` in a Gradle/JDK build stage, exclude the `*-plain.jar` artifact, and copy the executable JAR into a minimal JRE runtime stage. The Dockerfile generator never runs Gradle itself.
- If multiple root build systems or non-standard packaging make the target ambiguous, review the generated plan and stop rather than guessing.
