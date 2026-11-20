#!/usr/bin/env python3
"""Bounded, read-only heuristic scanner for Python, Node.js and Java repositories."""
from __future__ import annotations

import argparse
import json
import os
import re
from pathlib import Path

SKIP_DIRS = {
    ".git", ".venv", "venv", "node_modules", "__pycache__", ".pytest_cache",
    ".mypy_cache", ".ruff_cache", ".terraform", "vendor", "dist", "build",
    "target", "coverage", "htmlcov", ".next", ".cache", ".idea", ".vscode",
}
MAX_FILES = 5000
MAX_TEXT_BYTES = 64 * 1024
MANIFEST_NAMES = {
    "requirements.txt", "pyproject.toml", "uv.lock", "poetry.lock",
    "package.json", "pom.xml", "build.gradle", "build.gradle.kts",
}


def _read_text(path: Path, limit: int = MAX_TEXT_BYTES) -> str:
    try:
        if path.stat().st_size > limit:
            return ""
        return path.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return ""


def _walk_files(repo: Path) -> tuple[list[str], bool]:
    paths: list[str] = []
    truncated = False
    for current, dirs, files in os.walk(repo, followlinks=False):
        current_path = Path(current)
        dirs[:] = [
            name for name in dirs
            if name not in SKIP_DIRS and not (current_path / name).is_symlink()
        ]
        for name in sorted(files):
            candidate = current_path / name
            if candidate.is_symlink() or not candidate.is_file():
                continue
            paths.append(candidate.relative_to(repo).as_posix())
            if len(paths) >= MAX_FILES:
                truncated = True
                return sorted(paths), truncated
    return sorted(paths), truncated


def scan(repo: Path) -> dict:
    repo = repo.resolve()
    paths, truncated = _walk_files(repo)
    lowered = [path.lower() for path in paths]

    readme = _read_text(repo / "README.md").lower()
    manifest_parts = [
        _read_text(repo / rel).lower()
        for rel in paths
        if Path(rel).name in MANIFEST_NAMES
    ]
    search_text = " ".join(lowered) + " " + readme + " " + " ".join(manifest_parts)

    stack = framework = manager = dependency = entry = runtime = "unknown"
    start_command: list[str] = []
    runtime_source = "default"
    runtime_constraint = ""
    build_tool_version = ""
    gradle_wrapper = False

    if any(path.endswith((".py", "requirements.txt", "pyproject.toml", "setup.py")) for path in lowered):
        stack = "python"
        framework = next((name for name in ("fastapi", "django", "flask") if name in search_text), "unknown")
        if "uv.lock" in lowered:
            manager, dependency = "uv", next(path for path in paths if Path(path).name == "uv.lock")
        elif "poetry.lock" in lowered:
            manager, dependency = "poetry", next(path for path in paths if Path(path).name == "poetry.lock")
        elif "requirements.txt" in lowered:
            manager, dependency = "pip", next(path for path in paths if Path(path).name == "requirements.txt")
        elif "pyproject.toml" in lowered:
            manager, dependency = "pip", next(path for path in paths if Path(path).name == "pyproject.toml")
        elif "setup.py" in lowered:
            manager, dependency = "pip", next(path for path in paths if Path(path).name == "setup.py")
        entry = next(
            (path for path in paths if Path(path).name in ("main.py", "app.py", "manage.py")),
            "unknown",
        )

        # Prefer the declared Python constraint over a global default so the
        # generated image cannot be older than the project's minimum version.
        pyproject_path = next((repo / path for path in paths if Path(path).name == "pyproject.toml"), None)
        if pyproject_path:
            pyproject_text = _read_text(pyproject_path)
            requires_match = re.search(
                r"(?m)^\s*requires-python\s*=\s*['\"]([^'\"]+)['\"]",
                pyproject_text,
            )
            poetry_match = re.search(
                r"(?m)^\s*python\s*=\s*['\"]([^'\"]+)['\"]",
                pyproject_text,
            )
            runtime_constraint = (requires_match or poetry_match).group(1) if (requires_match or poetry_match) else ""
            version_match = re.search(r"(?:>=|~=|==|>|\^|~)\s*(3\.\d+)", runtime_constraint)
            if version_match:
                runtime = version_match.group(1)
                if runtime_constraint.lstrip().startswith(">") and not runtime_constraint.lstrip().startswith(">="):
                    minor = int(runtime.split(".")[1]) + 1
                    runtime = f"3.{minor}"
                runtime_source = "pyproject.toml"
            else:
                upper_match = re.search(r"(?:<=|<)\s*(3\.\d+)", runtime_constraint)
                runtime = upper_match.group(1) if upper_match else "3.12"
                if upper_match and runtime_constraint.lstrip().startswith("<") and not runtime_constraint.lstrip().startswith("<="):
                    minor = max(0, int(runtime.split(".")[1]) - 1)
                    runtime = f"3.{minor}"
                runtime_source = "pyproject.toml" if upper_match else "default"
        else:
            runtime = "3.12"

    elif "package.json" in lowered:
        stack = "nodejs"
        framework = next((name for name in ("nestjs", "express", "vite") if name in search_text), "unknown")
        if framework == "vite" and "react" in search_text:
            framework = "react-vite"
        dependency = next(path for path in paths if Path(path).name == "package.json")
        if "pnpm-lock.yaml" in lowered:
            manager = "pnpm"
        elif "yarn.lock" in lowered:
            manager = "yarn"
        elif "package-lock.json" in lowered:
            manager = "npm"
        else:
            manager = "unknown"
        entry = next(
            (path for path in paths if Path(path).name in ("server.js", "index.js", "main.js", "server.ts", "main.ts")),
            "unknown",
        )
        try:
            package_data = json.loads(_read_text(repo / dependency))
            scripts = package_data.get("scripts", {})
            if scripts.get("start"):
                start_command = ["npm", "start"] if manager == "npm" else []
        except (json.JSONDecodeError, OSError, AttributeError):
            scripts = {}
        if not start_command and entry.endswith(".js"):
            start_command = ["node", entry]
        runtime = "22"

    elif any(name in lowered for name in ("pom.xml", "build.gradle", "build.gradle.kts")):
        stack = "java"
        framework = "spring-boot" if "spring-boot" in search_text else "java"

        # Prefer a root Gradle manifest over nested sample Maven projects.
        root_gradle = next(
            (path for path in paths if Path(path).parent == Path(".")
             and Path(path).name in ("build.gradle", "build.gradle.kts")),
            None,
        )
        root_maven = next(
            (path for path in paths if Path(path).parent == Path(".") and Path(path).name == "pom.xml"),
            None,
        )
        wrapper_properties = next(
            (path for path in paths if path.endswith("gradle/wrapper/gradle-wrapper.properties")),
            None,
        )
        gradle_wrapper = bool(wrapper_properties and "gradlew" in lowered)
        if root_gradle and root_maven:
            # A checked-in Gradle wrapper is authoritative when both manifests exist.
            # Without that signal, preserve fail-closed behavior for ambiguous builds.
            if gradle_wrapper:
                manager, dependency = "gradle", root_gradle
            else:
                manager, dependency = "unknown", None
        elif root_gradle:
            manager, dependency = "gradle", root_gradle
        elif root_maven:
            manager, dependency = "maven", root_maven
        else:
            dependency = next(
                path for path in paths
                if Path(path).name in ("pom.xml", "build.gradle", "build.gradle.kts")
            )
            manager = "gradle" if Path(dependency).name.startswith("build.gradle") else "maven"

        runtime = "21"
        build_text = _read_text(repo / dependency) if dependency else ""
        java_match = (
            re.search(r"JavaLanguageVersion\.of\(\s*(\d+)\s*\)", build_text)
            or re.search(r"VERSION_(\d+)", build_text)
            or re.search(r"sourceCompatibility\s*=\s*['\"]?(?:VERSION_)?(\d+)", build_text)
        )
        if java_match:
            runtime = java_match.group(1)

        if wrapper_properties:
            wrapper_text = _read_text(repo / wrapper_properties)
            gradle_match = re.search(r"gradle-(\d+(?:\.\d+)+)-(?:bin|all)\.zip", wrapper_text)
            if gradle_match:
                build_tool_version = gradle_match.group(1)

    services: list[str] = []
    for name, pattern in (
        ("postgresql", r"\bpostgres(?:ql)?\b"),
        ("mysql", r"\bmysql\b"),
        ("redis", r"\bredis\b"),
    ):
        if re.search(pattern, search_text):
            services.append(name)

    return {
        "repository": str(repo),
        "project_type": stack,
        "framework": framework,
        "package_manager": manager,
        "dependency_file": dependency,
        "entry_point": entry,
        "start_command": start_command,
        "runtime_version": runtime,
        "runtime_version_source": runtime_source,
        "runtime_constraint": runtime_constraint,
        "build_tool_version": build_tool_version,
        "gradle_wrapper": gradle_wrapper,
        "existing_dockerfile": any(Path(path).name.lower() == "dockerfile" for path in paths),
        "existing_compose": any(
            Path(path).name.lower() in ("compose.yaml", "compose.yml", "docker-compose.yml", "docker-compose.yaml")
            for path in paths
        ),
        "env_files_detected": [path for path in paths if Path(path).name.startswith(".env")],
        "detected_services": services,
        "compose_required": bool(services),
        "file_count": len(paths),
        "confidence": "high" if framework != "unknown" else "low",
        "scan_truncated": truncated,
        "scan_limit": MAX_FILES,
        "files_sample": paths[:250],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Scan an application repository without modifying it.")
    parser.add_argument("--path", required=True)
    parser.add_argument("--output")
    args = parser.parse_args()
    repo = Path(args.path)
    if not repo.is_dir():
        parser.error("--path must be an existing directory")
    report = scan(repo)
    result = json.dumps(report, indent=2)
    if args.output:
        output_path = Path(args.output)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(result + "\n", encoding="utf-8")
        # Keep agent stdout small; the complete report remains available as an artifact.
        print(json.dumps({
            "status": "completed",
            "report": str(output_path),
            "project_type": report["project_type"],
            "framework": report["framework"],
            "file_count": report["file_count"],
            "scan_truncated": report["scan_truncated"],
        }, separators=(",", ":")))
    else:
        # Preserve machine-readable stdout when no artifact path is supplied.
        print(result)


if __name__ == "__main__":
    main()
