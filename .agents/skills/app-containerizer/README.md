# App Containerizer

A reusable, repository-aware AI skill that detects Python, Node.js and Java applications and generates Docker artifacts.

This app can create all major Docker asset types for common application stacks, including Dockerfiles, .dockerignore files, Compose configuration, and image build-ready container setups.

## Why a skill instead of a one-off prompt?
A prompt can draft a Dockerfile from a description. This project combines reusable instructions, deterministic repository scanning, structured analysis, generation templates, safety rules and repeatable validation. It can be applied consistently across repositories and reports what it could not verify.

## Components
- `SKILL.md`: agent workflow and operating rules.
- `scripts/`: repository scanner, analyzer, Dockerfile/Compose generators and validator.
- `templates/`: starter Dockerfiles.
- `references/`: security and engineering standards.
- `examples/`: illustrative FastAPI, Node.js and Spring Boot projects.
- `tests/`: pytest coverage.

## Supported stacks
Python (FastAPI, Flask, Django), Node.js (Express, NestJS, React/Vite), and Java (Spring Boot with Maven or Gradle `bootJar`). Python image versions are inferred from `pyproject.toml` version constraints; Java versions and Gradle wrapper versions are read from build metadata when available. Detection is heuristic, and uncertain details must be confirmed.

## Setup
Python 3.10+ recommended. Runtime scripts use only the standard library.
```bash
python -m venv .venv
# Windows: .venv\\Scripts\\activate
# macOS/Linux: source .venv/bin/activate
pip install pytest
```

## Usage
```bash
python scripts/scan_repository.py --path ./my-app --output scan.json
python scripts/analyze_application.py --input scan.json --output plan.json
python scripts/generate_dockerfile.py --path ./my-app --plan plan.json --approve
python scripts/generate_compose.py --path ./my-app --plan plan.json --services postgresql --approve
python scripts/validate_container.py --path ./my-app
```
Existing files are preserved unless `--overwrite` is passed. Review plans and generated files before use.

To request a real Docker build:
```bash
python scripts/validate_container.py --path ./my-app --build
```
If Docker is unavailable, the validator reports that the image was not built.

## Security boundaries
The skill does not deploy, provision infrastructure, push to GitHub, delete source files or automatically overwrite existing Docker configuration. Generated files are a starting point requiring review and image/dependency scanning before production.

## Tests
```bash
pytest -q
```

### Runtime metadata

Inspect `runtime_version`, `runtime_constraint`, and `runtime_version_source` in Python plans. For Gradle, inspect `runtime_version`, `build_tool_version`, and `gradle_wrapper`. The generated Spring Boot Dockerfile packages `bootJar` and runs the executable JAR as a non-root user.
