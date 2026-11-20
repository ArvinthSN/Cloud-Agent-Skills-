#!/usr/bin/env python3
"""Generate Dockerfile and .dockerignore only after explicit approval."""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path


def _safe_dependency_path(value: str | None, allowed_names: set[str]) -> str:
    if not value:
        raise ValueError("Dependency manifest was not detected.")
    path = Path(value)
    if path.is_absolute() or ".." in path.parts or path.name not in allowed_names:
        raise ValueError(f"Unsupported or unsafe dependency manifest path: {value}")
    return path.as_posix()


def _runtime_version(value: str | None, fallback: str) -> str:
    version = str(value or fallback)
    if not re.fullmatch(r"\d+(?:\.\d+)*", version):
        raise ValueError(f"Unsafe or unresolved runtime version: {version}")
    return version


def render(plan: dict) -> str:
    stack = plan.get("stack")
    manager = plan.get("package_manager", "unknown")
    command = plan.get("startup_command") or []
    if not isinstance(command, list) or not command or not all(isinstance(part, str) and part for part in command):
        raise ValueError("Startup command is unknown. Confirm it in the plan before generating a Dockerfile.")
    port = int(plan.get("port") or {"python": 8000, "nodejs": 3000, "java": 8080}.get(stack, 0))
    if not 1 <= port <= 65535:
        raise ValueError(f"Invalid application port: {port}")

    if stack == "python":
        version = _runtime_version(plan.get("runtime_version"), "3.12")
        dep = _safe_dependency_path(
            plan.get("dependency_file"),
            {"requirements.txt", "pyproject.toml", "setup.py", "poetry.lock", "uv.lock"},
        )
        if manager == "uv":
            if Path(dep).name != "uv.lock":
                raise ValueError("uv projects must include uv.lock.")
            return f"""FROM python:{version}-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app
RUN pip install --no-cache-dir uv
COPY ["pyproject.toml", "./"]
COPY ["{dep}", "./"]
COPY . .
RUN uv sync --frozen --no-dev
ENV PATH="/app/.venv/bin:$PATH"
RUN groupadd --system app && useradd --system --gid app --create-home app
USER app
EXPOSE {port}
CMD {json.dumps(command)}
"""
        if manager == "poetry":
            if Path(dep).name not in {"poetry.lock", "pyproject.toml"}:
                raise ValueError("Poetry projects require pyproject.toml and poetry.lock.")
            return f"""FROM python:{version}-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app
RUN pip install --no-cache-dir poetry
COPY ["pyproject.toml", "./"]
COPY ["poetry.lock", "./"]
RUN poetry config virtualenvs.create false && poetry install --only main --no-root --no-interaction
COPY . .
RUN groupadd --system app && useradd --system --gid app --create-home app
USER app
EXPOSE {port}
CMD {json.dumps(command)}
"""
        if manager != "pip":
            raise ValueError(f"Unsupported Python package manager: {manager}")
        if Path(dep).name == "requirements.txt":
            install = f'COPY ["{dep}", "./requirements.txt"]\nRUN pip install --no-cache-dir -r requirements.txt'
        else:
            install = f'COPY ["{dep}", "./{Path(dep).name}"]\nCOPY . .\nRUN pip install --no-cache-dir .'
            return f"""FROM python:{version}-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app
{install}
RUN groupadd --system app && useradd --system --gid app --create-home app
USER app
EXPOSE {port}
CMD {json.dumps(command)}
"""
        return f"""FROM python:{version}-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app
{install}
COPY . .
RUN groupadd --system app && useradd --system --gid app --create-home app
USER app
EXPOSE {port}
CMD {json.dumps(command)}
"""

    if stack == "nodejs":
        version = _runtime_version(plan.get("runtime_version"), "22")
        if manager != "npm":
            raise ValueError(f"Node.js package manager '{manager}' is not yet supported by the Dockerfile template; npm with package-lock.json is required.")
        _safe_dependency_path(plan.get("dependency_file"), {"package.json"})
        if not isinstance(plan.get("lockfile", "package-lock.json"), str):
            raise ValueError("Node.js lockfile path is invalid.")
        return f"""FROM node:{version}-bookworm-slim AS build
WORKDIR /app
COPY package*.json ./
RUN npm ci
COPY . .
RUN npm run build --if-present && npm prune --omit=dev
FROM node:{version}-bookworm-slim AS runtime
ENV NODE_ENV=production
WORKDIR /app
RUN groupadd --system app && useradd --system --gid app --create-home app
COPY --from=build --chown=app:app /app ./
USER app
EXPOSE {port}
CMD {json.dumps(command)}
"""

    if stack == "java":
        version = _runtime_version(plan.get("runtime_version"), "21")
        if manager == "maven":
            _safe_dependency_path(plan.get("dependency_file"), {"pom.xml"})
            return f"""FROM maven:3.9-eclipse-temurin-{version} AS build
WORKDIR /workspace
COPY pom.xml ./
RUN mvn -B -q dependency:go-offline
COPY src ./src
RUN mvn -B -DskipTests package
FROM eclipse-temurin:{version}-jre
WORKDIR /app
RUN groupadd --system app && useradd --system --gid app --create-home app
COPY --from=build /workspace/target/*.jar /app/app.jar
USER app
EXPOSE {port}
ENTRYPOINT {json.dumps(command)}
"""
        if manager == "gradle":
            # Use the Gradle version declared by the checked-in wrapper where possible.
            # The scanner only reads metadata; Gradle is run later by an explicit image build.
            _safe_dependency_path(plan.get("dependency_file"), {"build.gradle", "build.gradle.kts"})
            gradle_version = _runtime_version(plan.get("build_tool_version"), "8.14")
            return f"""FROM gradle:{gradle_version}-jdk{version} AS build
WORKDIR /workspace
COPY . .
RUN gradle --no-daemon bootJar -x test
# Exclude Spring Boot's plain JAR so only the executable bootJar enters the runtime stage.
RUN set -eu; jar="$(find build/libs -maxdepth 1 -type f -name '*.jar' ! -name '*-plain.jar' -print -quit)"; test -n "$jar"; cp "$jar" /workspace/app.jar
FROM eclipse-temurin:{version}-jre
WORKDIR /app
RUN groupadd --system app && useradd --system --gid app --create-home app
COPY --from=build --chown=app:app /workspace/app.jar /app/app.jar
USER app
EXPOSE {port}
ENTRYPOINT {json.dumps(command)}
"""
        raise ValueError(f"Java package manager '{manager}' is not supported; Maven or Gradle is required.")

    raise ValueError(f"Unsupported or unknown stack: {stack}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--path", required=True)
    parser.add_argument("--plan", required=True)
    parser.add_argument("--approve", action="store_true")
    parser.add_argument("--overwrite", action="store_true")
    args = parser.parse_args()

    repo = Path(args.path).resolve()
    if not repo.is_dir():
        parser.error("--path must be an existing directory")
    try:
        plan = json.loads(Path(args.plan).read_text(encoding="utf-8"))
        dockerfile = render(plan)
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        parser.error(f"Cannot generate Dockerfile: {exc}")
    if not args.approve:
        parser.error("No files written; re-run with --approve after reviewing the plan.")

    targets = [repo / "Dockerfile", repo / ".dockerignore"]
    existing = [target.name for target in targets if target.exists()]
    if existing and not args.overwrite:
        parser.error(f"Existing files preserved: {existing}; use --overwrite only after review.")

    ignore = """.git
.gradle
.venv
venv
__pycache__
.pytest_cache
.mypy_cache
.ruff_cache
node_modules
coverage
dist
build
target
.idea
.vscode
*.log
.env
.env.*
!.env.example
!.env.sample
*.pem
*.key
id_rsa
"""
    (repo / "Dockerfile").write_text(dockerfile, encoding="utf-8")
    (repo / ".dockerignore").write_text(ignore, encoding="utf-8")
    print(json.dumps({"generated": [str(target) for target in targets]}, indent=2))


if __name__ == "__main__":
    main()
