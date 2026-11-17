#!/usr/bin/env python3
"""Plan and execute Cloud Agent Skills with a single bounded project scan and versioned handoffs."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[4]
SKILLS_ROOT = REPO_ROOT / ".agents" / "skills"
SCHEMA_VERSION = "1.0"
SCANNER_VERSION = "1.0"
MAX_FILES = 5000
MAX_FILE_BYTES = 50 * 1024 * 1024
MAX_TEXT_BYTES = 64 * 1024
MAX_TOTAL_TEXT_BYTES = 3 * 1024 * 1024
SKIP_DIRS = {
    ".git", ".venv", "venv", "node_modules", "__pycache__", ".pytest_cache",
    ".mypy_cache", ".ruff_cache", ".terraform", "vendor", "dist", "build",
    "target", "coverage", "htmlcov", ".next", ".nuxt", ".cache", ".idea",
    ".vscode", ".cloud-agent", "bin", "obj",
}
MANIFEST_NAMES = {
    "package.json", "pyproject.toml", "requirements.txt", "setup.py",
    "poetry.lock", "uv.lock", "pom.xml", "build.gradle", "build.gradle.kts",
    "go.mod", "Cargo.toml", "Gemfile", "composer.json", "package-lock.json",
    "pnpm-lock.yaml", "yarn.lock", "go.sum", "Cargo.lock",
}
SKILL_NAMES = {
    "app-containerizer",
    "cicd-pipeline-creator",
    "infra-creator",
}
CI_PLATFORMS = {"github", "azure"}
PROVIDERS = {"aws", "azure", "gcp"}
COMPOSE_SERVICES = {"postgresql", "mysql", "redis"}
ENV_PATTERN = re.compile(
    r"""(?:os\.environ(?:\.get)?|os\.getenv|process\.env|ENV\[|getenv\()[\(\["'\s]*([A-Z][A-Z0-9_]{2,})""",
    re.IGNORECASE,
)
SENSITIVE_ENV_PATTERN = re.compile(r"(PASSWORD|SECRET|TOKEN|API_KEY|PRIVATE|CREDENTIAL|ACCESS_KEY)", re.I)
FRAMEWORK_MARKERS = {
    "fastapi": ("fastapi", "from fastapi"),
    "flask": ("flask", "from flask"),
    "django": ("django", "DJANGO_SETTINGS_MODULE"),
    "express": ("express",),
    "nestjs": ("@nestjs", "nestjs"),
    "nextjs": ("next", "next.config"),
    "react": ("react", "react-dom"),
    "vue": ("vue", "createApp"),
    "spring": ("springframework", "spring-boot"),
    "gin": ("github.com/gin-gonic/gin",),
}
DATABASE_MARKERS = {
    "postgresql": ("postgres", "postgresql", "psycopg2", "asyncpg"),
    "mysql": ("mysql", "pymysql", "mysqlclient"),
    "mongodb": ("mongodb", "pymongo", "mongoose"),
    "redis": ("redis", "ioredis", "go-redis"),
    "sqlite": ("sqlite", "sqlite3"),
    "dynamodb": ("dynamodb",),
    "cosmosdb": ("cosmosdb", "azure.cosmos"),
    "firestore": ("firestore", "google.cloud.firestore"),
}


class OrchestratorError(Exception):
    """Expected user-facing validation or workflow error."""


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def canonical_json(value: Any) -> str:
    return json.dumps(value, indent=2, sort_keys=True) + "\n"


def payload_hash(value: Any) -> str:
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + ".tmp")
    temp.write_text(canonical_json(value), encoding="utf-8")
    temp.replace(path)


def read_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise OrchestratorError(f"Cannot read JSON file {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise OrchestratorError(f"Expected a JSON object in {path}")
    return value


def git_value(root: Path, *args: str) -> str | None:
    try:
        result = subprocess.run(
            ["git", "-C", str(root), *args],
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    if result.returncode:
        return None
    return result.stdout.strip()


def _hash_file(path: Path, size: int) -> str:
    if size > MAX_FILE_BYTES:
        stat = path.stat()
        return f"large:{size}:{stat.st_mtime_ns}"
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _read_text(path: Path, budget: list[int]) -> str:
    try:
        size = path.stat().st_size
        if size > MAX_TEXT_BYTES or budget[0] <= 0:
            return ""
        text = path.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return ""
    allowance = min(len(text), budget[0])
    budget[0] -= allowance
    return text[:allowance]


def _walk(root: Path) -> tuple[list[dict[str, Any]], bool, int]:
    records: list[dict[str, Any]] = []
    truncated = False
    total_size = 0
    for current, dirs, names in os.walk(root, followlinks=False):
        base = Path(current)
        dirs[:] = sorted(
            name for name in dirs
            if name not in SKIP_DIRS and not (base / name).is_symlink()
        )
        for name in sorted(names):
            item = base / name
            if item.is_symlink() or not item.is_file():
                continue
            try:
                size = item.stat().st_size
                digest = _hash_file(item, size)
            except OSError:
                continue
            rel = item.relative_to(root).as_posix()
            records.append({"path": rel, "name": name, "parent": item.parent.relative_to(root).as_posix(), "size": size, "sha256": digest})
            total_size += size
            if len(records) >= MAX_FILES:
                truncated = True
                return records, truncated, total_size
    return records, truncated, total_size


def _numeric_version(value: Any, fallback: str) -> str:
    match = re.search(r"\d+(?:\.\d+)?", str(value or ""))
    return match.group(0) if match else fallback


def _manifest_projects(records: list[dict[str, Any]], root: Path) -> list[dict[str, Any]]:
    by_dir: dict[str, set[str]] = {}
    for record in records:
        if record["name"] in MANIFEST_NAMES or record["name"].endswith(".csproj"):
            by_dir.setdefault(record["parent"], set()).add(record["name"])

    projects: list[dict[str, Any]] = []
    for directory, names in sorted(by_dir.items()):
        python_manifests = names & {"pyproject.toml", "requirements.txt", "setup.py", "poetry.lock", "uv.lock"}
        other_project_manifests = names & {"pom.xml", "build.gradle", "build.gradle.kts", "go.mod", "Cargo.toml"}
        runtime_groups = sum(bool(group) for group in ({"package.json"} & names, python_manifests, other_project_manifests))
        if runtime_groups > 1:
            raise OrchestratorError(
                f"Multiple language manifest groups share project directory '{directory}'. "
                "Split them into separate project directories before orchestration."
            )
        project_root = root / ("" if directory == "." else directory)
        text_budget = [MAX_TOTAL_TEXT_BYTES]
        manifest_text = ""
        manifest_path: Path | None = None
        for candidate in (
            "package.json", "pyproject.toml", "requirements.txt", "setup.py",
            "poetry.lock", "uv.lock", "pom.xml", "build.gradle", "build.gradle.kts",
            "go.mod", "Cargo.toml", "Gemfile", "composer.json",
        ):
            if candidate in names:
                manifest_path = project_root / candidate
                manifest_text += "\n" + _read_text(manifest_path, text_budget)
        lowered = manifest_text.lower()
        paths = [r["path"] for r in records if directory == "." or r["path"].startswith(directory.rstrip("/") + "/")]
        relative_paths = [
            Path(path).relative_to(directory).as_posix() if directory != "." else path
            for path in paths
        ]
        source_samples: list[str] = []
        used = len(manifest_text)
        for rel in paths:
            file_path = root / rel
            if file_path.name in {".env", ".env.local", ".env.production", ".env.development"}:
                continue
            if file_path.suffix.lower() not in {".py", ".js", ".jsx", ".ts", ".tsx", ".go", ".java"}:
                continue
            if used >= MAX_TOTAL_TEXT_BYTES:
                break
            sample = _read_text(file_path, [MAX_TOTAL_TEXT_BYTES - used])
            if sample:
                source_samples.append(sample)
                used += len(sample)
        combined = (lowered + "\n" + "\n".join(source_samples)).lower()

        if "package.json" in names:
            language = "node"
            pm = "pnpm" if "pnpm-lock.yaml" in names else "yarn" if "yarn.lock" in names else "npm" if "package-lock.json" in names else "unknown"
            manifest = "package.json"
            package_data: dict[str, Any] = {}
            try:
                package_data = json.loads(_read_text(project_root / manifest, [MAX_TEXT_BYTES]))
            except (json.JSONDecodeError, OSError):
                package_data = {}
            scripts = package_data.get("scripts", {}) if isinstance(package_data, dict) else {}
            engines = package_data.get("engines", {}) if isinstance(package_data, dict) else {}
            version = _numeric_version(engines.get("node") if isinstance(engines, dict) else None, "22")
            build_cmd = "npm run build" if isinstance(scripts, dict) and scripts.get("build") else None
            test_cmd = "npm test" if isinstance(scripts, dict) and scripts.get("test") else None
            install_cmd = {
                "npm": "npm ci",
                "pnpm": "pnpm install --frozen-lockfile",
                "yarn": "yarn install --frozen-lockfile",
            }.get(pm, None)
            start_cmd = ["npm", "start"] if pm == "npm" and isinstance(scripts, dict) and scripts.get("start") else []
            if not start_cmd:
                entry = next((rel for rel in relative_paths if Path(rel).name in {"server.js", "index.js", "main.js"}), None)
                if entry and pm == "npm":
                    start_cmd = ["node", entry]
            framework = next((name for name, markers in FRAMEWORK_MARKERS.items() if any(marker in combined for marker in markers)), "unknown")
            ci_lang = "node"
            lockfile = {"npm": "package-lock.json", "pnpm": "pnpm-lock.yaml", "yarn": "yarn.lock"}.get(pm)
        elif names & {"pyproject.toml", "requirements.txt", "setup.py", "poetry.lock", "uv.lock"}:
            language = "python"
            pm = "uv" if "uv.lock" in names else "poetry" if "poetry.lock" in names else "pip"
            manifest = next((name for name in ("pyproject.toml", "requirements.txt", "setup.py", "poetry.lock", "uv.lock") if name in names), "unknown")
            pyproject = _read_text(project_root / "pyproject.toml", [MAX_TEXT_BYTES]) if "pyproject.toml" in names else ""
            version_match = re.search(r'requires-python\s*=\s*["\']([^"\']+)', pyproject)
            version = _numeric_version(version_match.group(1), "3.12") if version_match else "3.12"
            packaged = "setup.py" in names or "[build-system]" in pyproject or "[project]" in pyproject
            build_cmd = "python -m build --outdir dist" if packaged else None
            if pm == "uv":
                install_cmd = "python -m pip install uv && uv sync --frozen"
                lockfile = "uv.lock"
            elif pm == "poetry":
                install_cmd = "python -m pip install poetry && poetry install --no-interaction"
                lockfile = "poetry.lock"
            elif "requirements.txt" in names:
                install_cmd = "python -m pip install -r requirements.txt"
                lockfile = "requirements.txt"
            elif "pyproject.toml" in names:
                install_cmd = "python -m pip install ."
                lockfile = "pyproject.toml"
            else:
                install_cmd = "python -m pip install ."
                lockfile = "setup.py"
            if build_cmd:
                install_cmd = "python -m pip install --upgrade build && " + install_cmd
                if pm == "pip":
                    install_cmd += " && python -m pip install ."
            test_cmd = "pytest -q" if any(re.search(r"(^|/)(tests?|test_.*|.*_test\.py)(/|$)", rel) for rel in paths) else None
            entry = next((rel for rel in relative_paths if Path(rel).name in {"main.py", "app.py", "manage.py"}), "unknown")
            start_cmd = []
            framework = next((name for name, markers in FRAMEWORK_MARKERS.items() if any(marker in combined for marker in markers)), "unknown")
            ci_lang = "python"
        elif "pom.xml" in names or "build.gradle" in names or "build.gradle.kts" in names:
            language = "java"
            pm = "maven" if "pom.xml" in names else "gradle"
            manifest = "pom.xml" if "pom.xml" in names else "build.gradle" if "build.gradle" in names else "build.gradle.kts"
            version = "21"
            build_cmd = "mvn -B -DskipTests package" if pm == "maven" else None
            install_cmd = build_cmd
            test_cmd = "mvn -B verify" if pm == "maven" else None
            lockfile = None
            entry = next((rel for rel in relative_paths if Path(rel).name in {"Application.java", "Main.java"}), "unknown")
            start_cmd = ["java", "-jar", "/app/app.jar"] if pm == "maven" else []
            framework = "spring" if "spring-boot" in combined else "java"
            ci_lang = "java"
        elif "go.mod" in names:
            language, pm, manifest, version = "go", "gomod", "go.mod", "1.23"
            build_cmd, install_cmd, test_cmd, lockfile = "go build ./...", "go mod download", "go test ./...", "go.sum" if "go.sum" in names else None
            entry, start_cmd, framework, ci_lang = "unknown", [], "unknown", "go"
        elif "Cargo.toml" in names:
            language, pm, manifest, version = "rust", "cargo", "Cargo.toml", "stable"
            build_cmd, install_cmd, test_cmd, lockfile = "cargo build --release --locked", "cargo fetch --locked", "cargo test --locked", "Cargo.lock" if "Cargo.lock" in names else None
            entry, start_cmd, framework, ci_lang = "unknown", [], "unknown", "rust"
        else:
            continue

        project_databases = sorted(
            name for name, markers in DATABASE_MARKERS.items()
            if any(marker in combined for marker in markers)
        )
        projects.append({
            "id": f"{directory}:{language}",
            "dir": directory,
            "language": language,
            "ci_lang": ci_lang,
            "framework": framework,
            "databases": project_databases,
            "package_manager": pm,
            "manifest": manifest,
            "version": version,
            "entry_point": entry,
            "start_command": start_cmd,
            "install_command": install_cmd,
            "build_command": build_cmd,
            "test_command": test_cmd,
            "lockfile": lockfile,
        })
    return projects


def scan_project(root: Path) -> dict[str, Any]:
    root = root.resolve()
    if not root.is_dir():
        raise OrchestratorError(f"Project directory does not exist: {root}")
    records, truncated, total_size = _walk(root)
    if truncated:
        raise OrchestratorError(f"Repository scan reached the {MAX_FILES}-file safety limit; reduce the scan scope before planning.")
    budget = [MAX_TOTAL_TEXT_BYTES]
    content_parts: list[str] = []
    for record in records:
        file_path = root / record["path"]
        if file_path.name in {".env", ".env.local", ".env.production", ".env.development"}:
            continue
        if file_path.suffix.lower() in {".py", ".js", ".jsx", ".ts", ".tsx", ".go", ".java", ".yml", ".yaml", ".toml", ".json", ".txt"}:
            sample = _read_text(file_path, budget)
            if sample:
                content_parts.append(sample)
    text = "\n".join(content_parts)
    lower = text.lower()
    languages = set()
    for record in records:
        name, suffix = record["name"].lower(), Path(record["name"]).suffix.lower()
        if suffix == ".py" or name in {"pyproject.toml", "requirements.txt"}: languages.add("python")
        if suffix in {".js", ".jsx", ".ts", ".tsx"} or name == "package.json": languages.add("javascript")
        if suffix == ".java" or name in {"pom.xml", "build.gradle", "build.gradle.kts"}: languages.add("java")
        if suffix == ".go" or name == "go.mod": languages.add("go")
        if suffix == ".rs" or name == "cargo.toml": languages.add("rust")
    frameworks = sorted(name for name, markers in FRAMEWORK_MARKERS.items() if any(marker in lower for marker in markers))
    databases = sorted(name for name, markers in DATABASE_MARKERS.items() if any(marker in lower for marker in markers))
    env_vars = sorted({m.group(1).upper() for m in ENV_PATTERN.finditer(text)})
    for record in records:
        if record["name"].startswith(".env") and record["name"] not in {".env.example", ".env.sample", ".env.template"}:
            continue
        if record["name"] in {".env.example", ".env.sample", ".env.template"}:
            sample = _read_text(root / record["path"], [MAX_TEXT_BYTES])
            for line in sample.splitlines():
                stripped = line.strip()
                if stripped and not stripped.startswith("#") and "=" in stripped:
                    env_vars.append(stripped.split("=", 1)[0].strip().upper())
    env_vars = sorted(set(env_vars))
    sensitive_vars = sorted(name for name in env_vars if SENSITIVE_ENV_PATTERN.search(name))
    paths = [record["path"] for record in records]
    docker_files = [path for path in paths if Path(path).name.lower() == "dockerfile" or Path(path).name.lower() in {"compose.yaml", "compose.yml", "docker-compose.yml", "docker-compose.yaml"}]
    infra_files = [path for path in paths if path.endswith(".tf") or Path(path).name in {"serverless.yml", "serverless.yaml", "template.yaml", "sam.yaml", "cdk.json", "Pulumi.yaml", "Chart.yaml"}]
    top_dirs = sorted({Path(path).parts[0] for path in paths if len(Path(path).parts) > 1 and not Path(path).parts[0].startswith(".")})
    service_dirs = []
    for directory in top_dirs:
        if directory in {"services", "apps", "microservices"}:
            service_dirs.extend(
                f"{directory}/{Path(path).parts[1]}"
                for path in paths if len(Path(path).parts) > 2 and Path(path).parts[0] == directory
            )
        elif any(path.startswith(directory + "/") and Path(path).name in {"Dockerfile", "package.json", "requirements.txt", "go.mod"} for path in paths):
            service_dirs.append(directory)
    ci_platforms = []
    if any(path.startswith(".github/workflows/") for path in paths): ci_platforms.append("github-actions")
    if any(Path(path).name in {"azure-pipelines.yml", "azure-pipeline.yml"} for path in paths): ci_platforms.append("azure-devops")
    if ".gitlab-ci.yml" in paths: ci_platforms.append("gitlab-ci")
    if any(Path(path).name == "Jenkinsfile" for path in paths): ci_platforms.append("jenkins")
    if any(path.startswith(".circleci/") for path in paths): ci_platforms.append("circleci")
    snapshot = hashlib.sha256()
    for record in records:
        snapshot.update(record["path"].encode("utf-8"))
        snapshot.update(str(record["size"]).encode("ascii"))
        snapshot.update(record["sha256"].encode("ascii"))
    projects = _manifest_projects(records, root)
    git_revision = git_value(root, "rev-parse", "HEAD")
    dirty = git_value(root, "status", "--porcelain") or ""
    return {
        "schema_version": SCHEMA_VERSION,
        "scanner_version": SCANNER_VERSION,
        "generated_at": utc_now(),
        "root": str(root),
        "revision": git_revision,
        "working_tree_dirty": bool(dirty),
        "snapshot_hash": snapshot.hexdigest(),
        "file_count": len(records),
        "total_size_bytes": total_size,
        "scan_truncated": False,
        "files": paths[:500],
        "files_omitted": max(0, len(paths) - 500),
        "dependency_files": sorted(path for path in paths if Path(path).name in MANIFEST_NAMES),
        "languages": sorted(languages),
        "frameworks": frameworks,
        "databases": databases,
        "env_var_names": env_vars,
        "sensitive_env_var_names": sensitive_vars,
        "docker_files": docker_files,
        "has_dockerfile": any(Path(path).name.lower() == "dockerfile" for path in paths),
        "has_docker_compose": any(Path(path).name.lower() in {"compose.yaml", "compose.yml", "docker-compose.yml", "docker-compose.yaml"} for path in paths),
        "infra_files": infra_files,
        "top_level_dirs": top_dirs,
        "entry_points": sorted(path for path in paths if Path(path).name in {"main.py", "app.py", "server.py", "index.js", "main.go", "manage.py"}),
        "service_dirs": sorted(set(service_dirs)),
        "ci_platforms": sorted(ci_platforms),
        "projects": projects,
    }


def resolve_output_path(value: str | None, base: Path, default: Path) -> Path:
    if not value:
        return default.resolve()
    candidate = Path(value)
    return (candidate if candidate.is_absolute() else base / candidate).resolve()


def select_project(projects: list[dict[str, Any]], project_dir: str | None, required: bool) -> dict[str, Any] | None:
    if project_dir is not None:
        selected_path = Path(project_dir)
        if selected_path.is_absolute() or ".." in selected_path.parts:
            raise OrchestratorError("--project-dir must be a repository-relative path without '..'.")
        normalized = selected_path.as_posix()
        if normalized in {"", "."}:
            normalized = "."
        elif normalized.startswith("./"):
            normalized = normalized[2:]
        matches = [item for item in projects if item["dir"] == normalized]
        if len(matches) != 1:
            raise OrchestratorError(f"--project-dir '{project_dir}' matched {len(matches)} projects; detected: {[p['id'] for p in projects]}")
        return matches[0]
    if len(projects) == 1:
        return projects[0]
    if len(projects) > 1 and required:
        raise OrchestratorError(f"Multiple application projects detected. Select one with --project-dir. Detected: {[p['id'] for p in projects]}")
    if required and not projects:
        raise OrchestratorError("No supported application manifest was detected; this skill requires one.")
    return None


def _containerizer_scan(project: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
    stack = project["language"]
    return {
        "repository": str(Path(context["root"]) / ("" if project["dir"] == "." else project["dir"])),
        "project_type": {"node": "nodejs"}.get(stack, stack),
        "framework": project["framework"],
        "package_manager": project["package_manager"],
        "dependency_file": project["manifest"],
        "entry_point": project["entry_point"],
        "start_command": project["start_command"],
        "runtime_version": project["version"],
        "detected_services": project.get("databases", []),
        "compose_required": bool(context["databases"]),
        "confidence": "high" if project["framework"] != "unknown" else "low",
        "scan_truncated": context["scan_truncated"],
        "file_count": context["file_count"],
    }


def _infra_scan(context: dict[str, Any]) -> dict[str, Any]:
    return {
        "root": context["root"],
        "languages": context["languages"],
        "frameworks": context["frameworks"],
        "has_dockerfile": context["has_dockerfile"],
        "has_docker_compose": context["has_docker_compose"],
        "docker_files": context["docker_files"],
        "databases": context["databases"],
        "dependency_files": context.get("dependency_files", []),
        "env_var_names": context["env_var_names"],
        "sensitive_env_var_names": context["sensitive_env_var_names"],
        "infra_files": context["infra_files"],
        "top_level_dirs": context["top_level_dirs"],
        "entry_points": context["entry_points"],
        "service_dirs": context["service_dirs"],
        "file_count": context["file_count"],
        "total_size_bytes": context["total_size_bytes"],
        "notes": ["Generated from the orchestrator's single bounded scan; source files were not copied into the handoff."],
    }


def _ci_project(project: dict[str, Any]) -> dict[str, Any]:
    return {
        "dir": ".",
        "lang": project["ci_lang"],
        "pm": project["package_manager"],
        "install": project["install_command"],
        "build": project["build_command"],
        "test": project["test_command"],
        "version": project["version"],
        "lockfile": project["lockfile"],
        "has_tests": bool(project["test_command"]),
    }


def create_plan(args: argparse.Namespace) -> dict[str, Any]:
    root = Path(args.project).resolve()
    context = scan_project(root)
    skills = [name.strip() for name in args.skills.split(",") if name.strip()]
    if not skills or len(set(skills)) != len(skills) or set(skills) - SKILL_NAMES:
        raise OrchestratorError(f"--skills must be a comma-separated unique subset of {sorted(SKILL_NAMES)}")
    if "infra-creator" in skills and not args.provider:
        raise OrchestratorError("--provider is required when infra-creator is selected.")
    if "infra-creator" in skills and args.provider not in PROVIDERS:
        raise OrchestratorError(f"Unsupported provider: {args.provider}")
    if "cicd-pipeline-creator" in skills and args.platform not in CI_PLATFORMS:
        raise OrchestratorError(f"--platform must be one of {sorted(CI_PLATFORMS)} when cicd-pipeline-creator is selected.")
    services = [item.strip() for item in args.compose_services.split(",") if item.strip()]
    if set(services) - COMPOSE_SERVICES or len(services) != len(set(services)):
        raise OrchestratorError(f"--compose-services accepts unique values from {sorted(COMPOSE_SERVICES)}")
    if services and "app-containerizer" not in skills:
        raise OrchestratorError("--compose-services requires app-containerizer.")
    project_required = any(name in skills for name in ("app-containerizer", "cicd-pipeline-creator"))
    selected = select_project(context["projects"], args.project_dir, project_required)
    if selected is not None:
        context["selected_project"] = selected
    if "app-containerizer" in skills and selected["language"] not in {"python", "node", "java"}:
        raise OrchestratorError(f"app-containerizer does not currently support {selected['language']}.")
    if "app-containerizer" in skills:
        if selected["language"] == "node" and selected["package_manager"] != "npm":
            raise OrchestratorError("The current Dockerfile generator requires Node.js with npm and package-lock.json.")
        if selected["language"] == "java" and selected["package_manager"] != "maven":
            raise OrchestratorError("The current Java Dockerfile generator supports Maven projects only.")
        if selected["language"] == "python" and selected["package_manager"] not in {"pip", "poetry", "uv"}:
            raise OrchestratorError(f"Unsupported Python package manager: {selected['package_manager']}.")
    if "cicd-pipeline-creator" in skills:
        if selected["ci_lang"] not in {"python", "node"}:
            raise OrchestratorError(f"CI/CD renderer does not currently support {selected['ci_lang']}; supported stacks are Python and Node.js.")
        if not selected["install_command"] or not selected["build_command"]:
            raise OrchestratorError("The selected application has no supported install and artifact-producing build command. Configure the project before selecting cicd-pipeline-creator.")
        if selected["ci_lang"] == "node" and (selected["package_manager"] != "npm" or selected["lockfile"] != "package-lock.json"):
            raise OrchestratorError("The current CI/CD renderer requires npm with package-lock.json. pnpm, yarn and unlocked projects are not supported yet.")
    run_id = str(uuid.uuid4())
    run_dir = Path(args.run_dir).resolve()
    if root == run_dir or root in run_dir.parents:
        relative_run_dir = run_dir.relative_to(root)
        if ".cloud-agent" not in relative_run_dir.parts:
            raise OrchestratorError("Use a run directory outside the project, or place it under the ignored .cloud-agent/ directory.")
    if run_dir.exists() and any(run_dir.iterdir()):
        raise OrchestratorError(f"Run directory is not empty: {run_dir}")
    run_dir.mkdir(parents=True, exist_ok=True)

    output_root = resolve_output_path(args.output_root, root, root)
    project_root = root / ("" if selected is None or selected["dir"] == "." else selected["dir"])
    default_ci_out = project_root / ".github" / "workflows" if args.platform == "github" else project_root
    ci_out = resolve_output_path(args.ci_output, project_root, default_ci_out)
    infra_out = resolve_output_path(args.infra_output, output_root, output_root / "infra")
    plan = {
        "schema_version": SCHEMA_VERSION,
        "run_id": run_id,
        "request": {"goal": args.goal.strip(), "constraints": args.constraint or []},
        "project": {
            "root": str(root),
            "revision": context["revision"],
            "detected_stack": context["languages"],
            "architecture": None,
            "confidence": None,
            "snapshot_hash": context["snapshot_hash"],
            "context_hash": payload_hash(context),
            "context_file": str(run_dir / "project-context.json"),
            "scanner_version": SCANNER_VERSION,
        },
        "selected_skills": skills,
        "workflow": {
            "project_dir": str(project_root),
            "project_id": selected["id"] if selected else None,
            "provider": args.provider,
            "platform": args.platform,
            "compose_services": services,
            "output_root": str(output_root),
            "ci_output": str(ci_out),
            "infra_output": str(infra_out),
            "overwrite_approved": False,
        },
        "approval_required": True,
        "assumptions": [
            "One bounded repository scan is shared by all selected skills.",
            "Project detection is heuristic and must be reviewed before generation.",
            "The execute command writes local artifacts only; it never deploys, provisions or publishes.",
            "Existing project files are preserved unless execute is explicitly run with --overwrite.",
        ],
        "blocked_on": [],
        "created_at": utc_now(),
    }
    write_json(run_dir / "project-context.json", context)
    write_json(run_dir / "execution-plan.json", plan)

    handoff_paths: dict[str, str] = {}
    handoff_hashes: dict[str, str] = {}
    for skill in skills:
        handoff_dir = run_dir / "handoffs" / skill
        handoff_path = handoff_dir / "handoff.json"
        handoff: dict[str, Any] = {
            "schema_version": SCHEMA_VERSION,
            "run_id": run_id,
            "skill": skill,
            "project_root": str(root),
            "project_revision": context["revision"],
            "snapshot_hash": context["snapshot_hash"],
            "goal": args.goal.strip(),
            "approval_required": True,
        }
        if skill == "app-containerizer":
            handoff["project_root"] = str(project_root)
            handoff["input"] = _containerizer_scan(selected, context)
            handoff["compose_services"] = services
            handoff["outputs"] = ["Dockerfile", ".dockerignore"] + (["compose.yaml"] if services else [])
        elif skill == "cicd-pipeline-creator":
            handoff["project_root"] = str(project_root)
            handoff["ci_project"] = _ci_project(selected)
            handoff["platform"] = args.platform
            handoff["output_dir"] = str(ci_out)
            handoff["outputs"] = ["pipeline.yml" if args.platform == "github" else "azure-pipeline.yml", "PIPELINE_NOTES.md"]
        else:
            handoff["input"] = _infra_scan(context)
            handoff["provider"] = args.provider
            handoff["output_dir"] = str(infra_out)
            handoff["outputs"] = ["main.tf", "variables.tf", "providers.tf", "versions.tf", "outputs.tf", "modules/"]
        write_json(handoff_path, handoff)
        handoff_paths[skill] = str(handoff_path)
        handoff_hashes[skill] = payload_hash(handoff)

    plan["handoffs"] = handoff_paths
    plan["handoff_hashes"] = handoff_hashes
    write_json(run_dir / "execution-plan.json", plan)
    return plan


def _verify_run_fresh(plan: dict[str, Any], context: dict[str, Any], run_dir: Path) -> None:
    if plan.get("schema_version") != SCHEMA_VERSION or context.get("schema_version") != SCHEMA_VERSION:
        raise OrchestratorError("Unsupported plan or project-context schema version.")
    if Path(plan["project"]["root"]).resolve() != Path(context.get("root", "")).resolve():
        raise OrchestratorError("Project root mismatch between execution plan and context.")
    if payload_hash(context) != plan["project"].get("context_hash"):
        raise OrchestratorError("Project context changed after planning. Create a fresh plan.")
    root = Path(plan["project"]["root"]).resolve()
    current = scan_project(root)
    if current["snapshot_hash"] != plan["project"]["snapshot_hash"]:
        raise OrchestratorError("Project files changed after planning. Create a fresh plan before executing.")
    if current["scanner_version"] != plan["project"]["scanner_version"]:
        raise OrchestratorError("Scanner version changed after planning. Create a fresh plan before executing.")
    if context.get("selected_project", {}).get("id") != plan.get("workflow", {}).get("project_id") and plan.get("workflow", {}).get("project_id") is not None:
        raise OrchestratorError("Selected project does not match the execution plan.")
    selected_skills = plan.get("selected_skills", [])
    if not isinstance(selected_skills, list) or not selected_skills or len(selected_skills) != len(set(selected_skills)):
        raise OrchestratorError("Execution plan has an empty or invalid selected_skills list.")
    if plan.get("approval_required") is not True:
        raise OrchestratorError("Execution plan does not declare its approval gate.")
    for skill in selected_skills:
        if skill not in SKILL_NAMES:
            raise OrchestratorError(f"Unsupported skill in execution plan: {skill}")
        handoff_path = run_dir / "handoffs" / skill / "handoff.json"
        recorded_path = plan.get("handoffs", {}).get(skill)
        if not recorded_path or Path(recorded_path).resolve() != handoff_path.resolve():
            raise OrchestratorError(f"Handoff path mismatch for {skill}.")
        handoff = read_json(handoff_path)
        if payload_hash(handoff) != plan.get("handoff_hashes", {}).get(skill):
            raise OrchestratorError(f"Skill handoff changed after planning: {skill}")
        if handoff.get("schema_version") != SCHEMA_VERSION:
            raise OrchestratorError(f"Unsupported handoff schema version for {skill}.")
        if handoff.get("run_id") != plan.get("run_id") or handoff.get("skill") != skill:
            raise OrchestratorError(f"Invalid or mismatched handoff for {skill}.")
        if handoff.get("snapshot_hash") != plan["project"]["snapshot_hash"]:
            raise OrchestratorError(f"Project snapshot mismatch in handoff for {skill}.")
        if handoff.get("approval_required") is not True:
            raise OrchestratorError(f"Approval gate missing in handoff for {skill}.")
        if skill == "app-containerizer" and not isinstance(handoff.get("input"), dict):
            raise OrchestratorError("Containerizer handoff is missing its input object.")
        if skill == "cicd-pipeline-creator":
            if not isinstance(handoff.get("ci_project"), dict) or handoff.get("platform") not in CI_PLATFORMS:
                raise OrchestratorError("CI/CD handoff is missing a supported platform or project object.")
        if skill == "infra-creator":
            if not isinstance(handoff.get("input"), dict) or handoff.get("provider") not in PROVIDERS:
                raise OrchestratorError("Infrastructure handoff is missing a supported provider or scan input.")
        project_root = Path(handoff.get("project_root", "")).resolve()
        if project_root != root and root not in project_root.parents:
            raise OrchestratorError(f"Skill handoff project path escapes the scanned repository: {skill}.")


def run_command(command: list[str], cwd: Path, timeout: int = 600) -> subprocess.CompletedProcess[str]:
    try:
        result = subprocess.run(command, cwd=str(cwd), capture_output=True, text=True, timeout=timeout, check=False)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise OrchestratorError(f"Command could not complete: {command[0]}: {exc}") from exc
    return result


def _check(name: str, status: str, detail: str = "") -> dict[str, str]:
    return {"name": name, "status": status, "detail": detail[:2000]}


def _artifact(path: Path, action: str, kind: str, purpose: str) -> dict[str, str]:
    return {"path": str(path), "type": kind, "action": action, "purpose": purpose}


def execute_skill(skill: str, handoff: dict[str, Any], run_dir: Path, overwrite: bool) -> dict[str, Any]:
    artifacts: list[dict[str, str]] = []
    checks: list[dict[str, str]] = []
    assumptions: list[str] = []
    risks: list[str] = []
    manual: list[str] = []
    handoff_dir = run_dir / "handoffs" / skill
    handoff["executed_at"] = utc_now()

    if skill == "app-containerizer":
        project_root = Path(handoff["project_root"])
        scan_path = handoff_dir / "scan.json"
        plan_path = handoff_dir / "container-plan.json"
        write_json(scan_path, handoff["input"])
        analyzer = SKILLS_ROOT / skill / "scripts" / "analyze_application.py"
        generator = SKILLS_ROOT / skill / "scripts" / "generate_dockerfile.py"
        validator = SKILLS_ROOT / skill / "scripts" / "validate_container.py"
        result = run_command([sys.executable, str(analyzer), "--input", str(scan_path), "--output", str(plan_path)], project_root)
        checks.append(_check("container-analyze", "PASS" if result.returncode == 0 else "FAIL", result.stderr or result.stdout))
        if result.returncode:
            return {"status": "failed", "artifacts": artifacts, "checks": checks, "assumptions": assumptions, "risks": risks, "manual_actions": manual}
        container_plan = read_json(plan_path)
        if not container_plan.get("startup_command"):
            checks.append(_check("container-startup-command", "FAIL", "No verified startup command; no Dockerfile was generated."))
            manual.extend(container_plan.get("unknowns", []))
            return {"status": "blocked", "artifacts": artifacts, "checks": checks, "assumptions": assumptions, "risks": risks, "manual_actions": manual}
        targets = [project_root / "Dockerfile", project_root / ".dockerignore"]
        existed = {path: path.exists() for path in targets}
        command = [sys.executable, str(generator), "--path", str(project_root), "--plan", str(plan_path), "--approve"]
        if overwrite:
            command.append("--overwrite")
        result = run_command(command, project_root)
        checks.append(_check("container-generate", "PASS" if result.returncode == 0 else "FAIL", result.stderr or result.stdout))
        if result.returncode:
            return {"status": "failed", "artifacts": artifacts, "checks": checks, "assumptions": assumptions, "risks": risks, "manual_actions": manual}
        artifacts.extend([
            _artifact(targets[0], "updated" if existed[targets[0]] else "created", "Dockerfile", "Container image definition"),
            _artifact(targets[1], "updated" if existed[targets[1]] else "created", ".dockerignore", "Exclude local and secret files from image build context"),
        ])
        services = handoff.get("compose_services", [])
        if services:
            compose_script = SKILLS_ROOT / skill / "scripts" / "generate_compose.py"
            compose_target = project_root / "compose.yaml"
            compose_existed = compose_target.exists()
            compose_cmd = [sys.executable, str(compose_script), "--path", str(project_root), "--plan", str(plan_path), "--services", ",".join(services), "--approve"]
            if overwrite:
                compose_cmd.append("--overwrite")
            result = run_command(compose_cmd, project_root)
            checks.append(_check("compose-generate", "PASS" if result.returncode == 0 else "FAIL", result.stderr or result.stdout))
            if result.returncode:
                return {"status": "partial", "artifacts": artifacts, "checks": checks, "assumptions": assumptions, "risks": risks, "manual_actions": manual}
            artifacts.append(_artifact(compose_target, "updated" if compose_existed else "created", "Compose", "Explicitly selected local dependencies"))
        validation = run_command([sys.executable, str(validator), "--path", str(project_root)], project_root)
        checks.append(_check("container-static-validation", "PASS" if validation.returncode == 0 else "FAIL", validation.stdout or validation.stderr))
        return {"status": "completed" if validation.returncode == 0 else "partial", "artifacts": artifacts, "checks": checks, "assumptions": assumptions, "risks": risks, "manual_actions": manual}

    if skill == "cicd-pipeline-creator":
        project_root = Path(handoff["project_root"])
        output_dir = Path(handoff["output_dir"])
        context_path = handoff_dir / "ci-context.json"
        write_json(context_path, {"ci_project": handoff["ci_project"]})
        renderer = SKILLS_ROOT / skill / "scripts" / "render_pipeline.py"
        platform = handoff["platform"]
        pipeline_name = "pipeline.yml" if platform == "github" else "azure-pipeline.yml"
        pipeline_path = output_dir / pipeline_name
        notes_path = output_dir / "PIPELINE_NOTES.md"
        existed = {pipeline_path: pipeline_path.exists(), notes_path: notes_path.exists()}
        command = [sys.executable, str(renderer), str(project_root), platform, "--out", str(output_dir), "--context", str(context_path)]
        if overwrite:
            command.append("--overwrite")
        result = run_command(command, project_root)
        checks.append(_check("pipeline-render", "PASS" if result.returncode == 0 else "FAIL", result.stderr or result.stdout))
        if result.returncode:
            return {"status": "failed", "artifacts": artifacts, "checks": checks, "assumptions": assumptions, "risks": risks, "manual_actions": manual}
        artifacts.extend([
            _artifact(pipeline_path, "updated" if existed[pipeline_path] else "created", "CI/CD pipeline", f"{platform} pipeline"),
            _artifact(notes_path, "updated" if existed[notes_path] else "created", "Pipeline notes", "Required variables and review instructions"),
        ])
        validator = SKILLS_ROOT / skill / "scripts" / "validate_pipeline.py"
        validation = run_command([sys.executable, str(validator), str(pipeline_path), "--json"], project_root)
        try:
            payload = json.loads(validation.stdout)
        except json.JSONDecodeError:
            payload = {}
        vstatus = payload.get("status", "fail")
        checks.append(_check("pipeline-static-validation", "PASS" if vstatus == "pass" else "WARNING" if vstatus == "warning" else "FAIL", validation.stdout or validation.stderr))
        if vstatus != "pass":
            risks.extend(payload.get("errors", []))
            risks.extend(payload.get("warnings", []))
        if platform == "github":
            manual.append("Review action versions and configure repository variables. Deployment stays disabled until a target-specific job is implemented.")
        else:
            manual.append("Review Azure task versions and configure protected pipeline variables/service connections. Target-specific deployment needs a separate review.")
        return {"status": "completed" if vstatus == "pass" else "partial" if vstatus == "warning" else "failed", "artifacts": artifacts, "checks": checks, "assumptions": assumptions, "risks": risks, "manual_actions": manual}

    # infra-creator
    provider = handoff["provider"]
    infra_script_root = SKILLS_ROOT / skill / "scripts"
    scan_path = handoff_dir / "infra-scan.json"
    arch_path = handoff_dir / "architecture.json"
    write_json(scan_path, handoff["input"])
    analyzer = infra_script_root / "analyze_architecture.py"
    result = run_command([sys.executable, str(analyzer), str(scan_path), "--json", "-o", str(arch_path)], Path(handoff["project_root"]))
    checks.append(_check("infra-architecture-analysis", "PASS" if result.returncode == 0 else "FAIL", result.stderr or result.stdout))
    if result.returncode:
        return {"status": "failed", "artifacts": artifacts, "checks": checks, "assumptions": assumptions, "risks": risks, "manual_actions": manual}
    architecture = read_json(arch_path)
    assumptions.extend(architecture.get("evidence", []))
    if architecture.get("confidence", 0) < 0.45:
        risks.append("Architecture confidence is low; review the architecture analysis before using the generated Terraform.")
    generator = infra_script_root / "generate_terraform.py"
    output_dir = Path(handoff["output_dir"])
    existed = output_dir.exists() and any(output_dir.iterdir())
    command = [
        sys.executable, str(generator), "--scan", str(scan_path), "--arch", str(arch_path),
        "--provider", provider, "--output", str(output_dir), "--approve",
    ]
    if overwrite:
        command.append("--overwrite")
    result = run_command(command, Path(handoff["project_root"]))
    checks.append(_check("terraform-generate", "PASS" if result.returncode == 0 else "FAIL", result.stderr or result.stdout))
    if result.returncode:
        return {"status": "failed", "artifacts": artifacts, "checks": checks, "assumptions": assumptions, "risks": risks, "manual_actions": manual}
    for name in ("main.tf", "variables.tf", "providers.tf", "versions.tf", "outputs.tf", "README.md", "terraform.tfvars.example"):
        target = output_dir / name
        if target.exists():
            artifacts.append(_artifact(target, "updated" if existed else "created", "Terraform", "Generated infrastructure configuration"))
    artifacts.append(_artifact(output_dir / "modules", "updated" if existed else "created", "Terraform modules", "Provider-specific reusable modules"))
    validator = infra_script_root / "validate_terraform.py"
    validation = run_command([sys.executable, str(validator), str(output_dir), "--json"], Path(handoff["project_root"]))
    try:
        validation_data = json.loads(validation.stdout)
    except json.JSONDecodeError:
        validation_data = {}
    if not validation_data.get("terraform_available", False):
        vstatus = "NOT_RUN"
        manual.append("Install Terraform CLI and run validate_terraform.py. No Terraform validation was performed.")
    elif validation_data.get("success"):
        vstatus = "PASS"
    else:
        vstatus = "FAIL"
        risks.extend(validation_data.get("errors", []))
    checks.append(_check("terraform-validation", vstatus, validation.stdout or validation.stderr))
    manual.append("Review the Terraform plan and provider permissions. This workflow never runs terraform apply or destroy.")
    status = "completed" if vstatus == "PASS" else "partial" if vstatus == "NOT_RUN" else "failed"
    return {"status": status, "artifacts": artifacts, "checks": checks, "assumptions": assumptions, "risks": risks, "manual_actions": manual}


def preflight_outputs(plan: dict[str, Any], run_dir: Path, overwrite: bool) -> list[str]:
    conflicts: list[str] = []
    for skill in plan["selected_skills"]:
        handoff = read_json(run_dir / "handoffs" / skill / "handoff.json")
        if skill == "app-containerizer":
            project_root = Path(handoff["project_root"])
            targets = [project_root / "Dockerfile", project_root / ".dockerignore"]
            if handoff.get("compose_services"):
                targets.append(project_root / "compose.yaml")
            conflicts.extend(str(path) for path in targets if path.exists())
        elif skill == "cicd-pipeline-creator":
            output_dir = Path(handoff["output_dir"])
            pipeline = "pipeline.yml" if handoff["platform"] == "github" else "azure-pipeline.yml"
            targets = [output_dir / pipeline, output_dir / "PIPELINE_NOTES.md"]
            conflicts.extend(str(path) for path in targets if path.exists())
        else:
            output_dir = Path(handoff["output_dir"])
            if output_dir.exists() and any(output_dir.iterdir()):
                conflicts.append(f"{output_dir} (non-empty Terraform output directory)")
    if conflicts and not overwrite:
        joined = "\\n- ".join(conflicts)
        raise OrchestratorError(
            "Existing output was found. No specialist was executed and no files were changed. "
            "Review these paths, then re-run with --overwrite only when replacement is intended:\\n- "
            + joined
        )
    return conflicts


def execute_run(args: argparse.Namespace) -> dict[str, Any]:
    run_dir = Path(args.run_dir).resolve()
    plan_path = run_dir / "execution-plan.json"
    context_path = run_dir / "project-context.json"
    if not plan_path.is_file() or not context_path.is_file():
        raise OrchestratorError(f"{run_dir} is not a valid orchestrator run directory.")
    plan = read_json(plan_path)
    context = read_json(context_path)
    if not args.approve:
        raise OrchestratorError("No project files were changed. Re-run with --approve after reviewing execution-plan.json and handoffs/.")
    _verify_run_fresh(plan, context, run_dir)
    existing_outputs = preflight_outputs(plan, run_dir, args.overwrite)

    started_at = utc_now()
    skill_results: dict[str, Any] = {}
    all_artifacts: list[dict[str, str]] = []
    all_checks: list[dict[str, str]] = [
        _check(
            "output-preflight",
            "WARNING" if existing_outputs else "PASS",
            "Existing files will be replaced under explicit --overwrite approval."
            if existing_outputs else "No existing output conflicts detected.",
        )
    ]
    assumptions = list(plan.get("assumptions", []))
    risks: list[str] = []
    manual: list[str] = []
    for skill in plan["selected_skills"]:
        handoff_path = run_dir / "handoffs" / skill / "handoff.json"
        handoff = read_json(handoff_path)
        if handoff.get("run_id") != plan.get("run_id") or handoff.get("skill") != skill:
            raise OrchestratorError(f"Invalid or mismatched handoff for {skill}")
        result = execute_skill(skill, handoff, run_dir, args.overwrite)
        skill_results[skill] = result
        all_artifacts.extend(result["artifacts"])
        all_checks.extend(result["checks"])
        assumptions.extend(result["assumptions"])
        risks.extend(result["risks"])
        manual.extend(result["manual_actions"])

    statuses = [result["status"] for result in skill_results.values()]
    if all(status == "completed" for status in statuses):
        overall = "completed"
    elif all(status == "blocked" for status in statuses):
        overall = "blocked"
    elif any(status in {"failed", "blocked"} for status in statuses):
        overall = "partial" if any(status in {"completed", "partial"} for status in statuses) else "failed"
    else:
        overall = "partial"
    report = {
        "schema_version": SCHEMA_VERSION,
        "status": overall,
        "skill": "cloud-engineering-orchestrator",
        "run_id": plan["run_id"],
        "project_revision": plan["project"].get("revision"),
        "overwrite_approved": bool(args.overwrite),
        "detected": {
            "languages": context["languages"],
            "frameworks": context["frameworks"],
            "databases": context["databases"],
            "projects": [project["id"] for project in context["projects"]],
            "snapshot_hash": context["snapshot_hash"],
        },
        "artifacts": all_artifacts,
        "checks": all_checks,
        "skill_reports": skill_results,
        "assumptions": sorted(set(assumptions)),
        "risks": sorted(set(risks)),
        "manual_actions": sorted(set(manual)),
        "started_at": started_at,
        "finished_at": utc_now(),
    }
    write_json(run_dir / "execution-report.json", report)
    return report


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Cloud Agent Skills executable orchestrator.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    plan = subparsers.add_parser("plan", help="Scan once and create versioned context and skill handoffs.")
    plan.add_argument("--project", required=True)
    plan.add_argument("--goal", required=True)
    plan.add_argument("--skills", required=True, help="Comma-separated skill IDs.")
    plan.add_argument("--run-dir", required=True, help="New or empty directory for the plan and handoffs.")
    plan.add_argument("--project-dir", help="Explicit subproject path for containerizer/CI when the repository contains multiple apps.")
    plan.add_argument("--provider", choices=sorted(PROVIDERS))
    plan.add_argument("--platform", choices=sorted(CI_PLATFORMS))
    plan.add_argument("--compose-services", default="", help="Explicit local services, comma-separated: postgresql,mysql,redis.")
    plan.add_argument("--infra-output")
    plan.add_argument("--ci-output")
    plan.add_argument("--output-root")
    plan.add_argument("--constraint", action="append", default=[])

    execute = subparsers.add_parser("execute", help="Execute local generators from a reviewed plan.")
    execute.add_argument("--run-dir", required=True)
    execute.add_argument("--approve", action="store_true", help="Approve local file generation described in the plan.")
    execute.add_argument("--overwrite", action="store_true", help="Separately approve replacing existing generated files.")
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    try:
        if args.command == "plan":
            plan = create_plan(args)
            print(json.dumps({
                "run_id": plan["run_id"],
                "plan": str(Path(args.run_dir).resolve() / "execution-plan.json"),
                "context": str(Path(args.run_dir).resolve() / "project-context.json"),
                "handoffs": plan["handoffs"],
                "selected_skills": plan["selected_skills"],
                "approval_required": True,
                "next_step": f"python {Path(__file__)} execute --run-dir {Path(args.run_dir).resolve()} --approve",
            }, indent=2))
            return 0
        report = execute_run(args)
        print(json.dumps(report, indent=2))
        return 0 if report["status"] == "completed" else 2 if report["status"] == "partial" else 1
    except OrchestratorError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    except Exception as exc:  # ensure the CLI returns a useful failure rather than a traceback
        print(f"ERROR: unexpected orchestrator failure: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
