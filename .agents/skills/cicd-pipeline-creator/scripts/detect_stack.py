#!/usr/bin/env python3
"""Detect repo stack facts and emit compact JSON."""
import json
import os
import re
import sys
from pathlib import Path

SKIP = {".git", "node_modules", "venv", ".venv", "dist", "build", "target", "__pycache__", ".tox", ".mypy_cache", "vendor"}
MANIFESTS = {"package.json", "pyproject.toml", "requirements.txt", "setup.py", "Pipfile", "poetry.lock", "uv.lock"}
TEST_RE = re.compile(r"(^|/)(tests?|__tests__|spec|test_.*|.*_test\.|.*\.spec\.)")
CI_PATTERNS = {
    "azure-devops": lambda f: f.endswith("azure-pipeline.yml") or f.endswith("azure-pipeline.yaml") or f.endswith("azure-pipelines.yml") or f.endswith("azure-pipelines.yaml") or f.startswith(".azure-pipelines/"),
    "github-actions": lambda f: f.startswith(".github/workflows/"),
    "gitlab-ci": lambda f: f == ".gitlab-ci.yml",
    "jenkins": lambda f: f.endswith("Jenkinsfile"),
    "circleci": lambda f: f.startswith(".circleci/"),
}


def walk(root: Path):
    for current, dirs, files in os.walk(root):
        rel = Path(current).relative_to(root)
        depth = 0 if rel == Path('.') else len(rel.parts)
        dirs[:] = [d for d in dirs if d not in SKIP and depth < 4]
        for name in files:
            yield (Path(current) / name).relative_to(root).as_posix()


def read_text(path: Path):
    try:
        return path.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return ""


def clean(obj):
    if isinstance(obj, dict):
        return {k: clean(v) for k, v in obj.items() if v not in (None, "", [], {}, ())}
    if isinstance(obj, list):
        return [clean(v) for v in obj if v not in (None, "", [], {}, ())]
    return obj


def detect_node(root: Path, dir_name: str, names: set[str], has_tests: bool):
    package = root / dir_name / "package.json"
    scripts = {}
    if package.exists():
        try:
            scripts = json.loads(read_text(package)).get("scripts", {})
        except json.JSONDecodeError:
            scripts = {}
    if "pnpm-lock.yaml" in names:
        pm, lock, install = "pnpm", "pnpm-lock.yaml", "pnpm install --frozen-lockfile"
    elif "yarn.lock" in names:
        pm, lock, install = "yarn", "yarn.lock", "yarn install --frozen-lockfile"
    elif "package-lock.json" in names:
        pm, lock, install = "npm", "package-lock.json", "npm ci"
    else:
        pm, lock, install = "npm", None, "npm install"
    version = None
    for candidate in (".nvmrc", ".node-version"):
        if candidate in names:
            version = read_text(root / dir_name / candidate).strip().splitlines()[0]
            break
    if version is None and package.exists():
        try:
            version = json.loads(read_text(package)).get("engines", {}).get("node")
        except json.JSONDecodeError:
            version = None
    test_cmd = scripts.get("test") if has_tests else None
    build_cmd = scripts.get("build") if scripts.get("build") else None
    return {
        "dir": dir_name or ".",
        "lang": "node",
        "pm": pm,
        "install": install,
        "build": build_cmd,
        "test": test_cmd or ("npm test" if has_tests else None),
        "version": version,
        "lockfile": lock,
        "has_tests": has_tests,
    }


def detect_python(root: Path, dir_name: str, names: set[str], has_tests: bool):
    if "poetry.lock" in names:
        pm, lock, install = "poetry", "poetry.lock", "poetry install"
    elif "uv.lock" in names:
        pm, lock, install = "uv", "uv.lock", "uv sync --frozen"
    elif "requirements.txt" in names:
        pm, lock, install = "pip", "requirements.txt", "python -m pip install -r requirements.txt"
    elif "pyproject.toml" in names:
        pm, lock, install = "pip", "pyproject.toml", "python -m pip install ."
    else:
        pm, lock, install = "pip", None, "python -m pip install ."
    version = None
    for candidate in (".python-version", ".tool-versions"):
        if candidate in names:
            text = read_text(root / dir_name / candidate)
            for line in text.splitlines():
                if "python" in line.lower():
                    version = line.strip().split()[-1]
                    break
            if version:
                break
    if version is None:
        pyproject = root / dir_name / "pyproject.toml"
        if pyproject.exists():
            m = re.search(r'requires-python\s*=\s*"([^"]+)"', read_text(pyproject))
            if m:
                version = m.group(1)
    # Produce a real distributable only for projects with packaging metadata.
    # A compile-only check must not be advertised as a deployable build artifact.
    pyproject = root / dir_name / "pyproject.toml"
    has_package_metadata = "setup.py" in names or (
        pyproject.is_file() and (
            "[build-system]" in read_text(pyproject) or "[project]" in read_text(pyproject)
        )
    )
    build_cmd = "python -m build --outdir dist" if has_package_metadata else None
    if build_cmd:
        install = "python -m pip install --upgrade build && " + install
    return {
        "dir": dir_name or ".",
        "lang": "python",
        "pm": pm,
        "install": install,
        "build": build_cmd,
        "test": "pytest -q" if has_tests else None,
        "version": version,
        "lockfile": lock,
        "has_tests": has_tests,
    }


def detect_other(root: Path, dir_name: str, language: str, names: set[str], has_tests: bool):
    if language == "java":
        return {"dir": dir_name or ".", "lang": "java", "pm": "maven", "install": "mvn -B -DskipTests package", "build": "mvn -B -DskipTests package", "test": "mvn -B verify" if has_tests else None, "has_tests": has_tests}
    if language == "go":
        return {"dir": dir_name or ".", "lang": "go", "pm": "gomod", "install": "go mod download", "build": "go build ./...", "test": "go test ./..." if has_tests else None, "has_tests": has_tests}
    if language == "rust":
        return {"dir": dir_name or ".", "lang": "rust", "pm": "cargo", "install": "cargo fetch --locked", "build": "cargo build --release --locked", "test": "cargo test --locked" if has_tests else None, "lockfile": "Cargo.lock", "has_tests": has_tests}
    return {"dir": dir_name or ".", "lang": language, "pm": "unknown", "install": "echo install", "build": "echo build", "test": "echo test" if has_tests else None, "has_tests": has_tests}


def pipeline_has_tests(dir_name: str, files: list[str], project_path: Path, manifest_name: str):
    package = project_path / manifest_name
    if package.exists():
        try:
            data = json.loads(read_text(package))
            scripts = data.get("scripts", {})
            if "test" in scripts and scripts["test"] and "no test" not in str(scripts["test"]).lower():
                return True
        except json.JSONDecodeError:
            pass
    if dir_name == ".":
        relevant = files
    else:
        relevant = [f for f in files if f.startswith(f"{dir_name}/")]
    return any(TEST_RE.search(f) for f in relevant)


def main():
    root = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else Path(".").resolve()
    files = sorted(walk(root))
    by_dir = {}
    for path in files:
        parent = str(Path(path).parent)
        name = Path(path).name
        by_dir.setdefault(parent if parent != "." else ".", set()).add(name)

    project_dirs = []
    for dir_name, names in by_dir.items():
        if names & {"package.json", "pyproject.toml", "requirements.txt", "setup.py", "Pipfile", "pom.xml", "build.gradle", "build.gradle.kts", "go.mod", "Cargo.toml", "Gemfile"} or any(name.endswith((".csproj", ".sln")) for name in names):
            project_dirs.append(dir_name)

    projects = []
    for dir_name in sorted(set(project_dirs)):
        names = by_dir.get(dir_name, set())
        project_path = root / dir_name if dir_name != "." else root
        if "package.json" in names:
            has_tests = pipeline_has_tests(dir_name, files, project_path, "package.json")
            projects.append(detect_node(root, dir_name, names, has_tests))
        if {"requirements.txt", "pyproject.toml", "setup.py", "Pipfile", "poetry.lock", "uv.lock"} & names:
            has_tests = pipeline_has_tests(dir_name, files, project_path, "pyproject.toml") or pipeline_has_tests(dir_name, files, project_path, "requirements.txt")
            projects.append(detect_python(root, dir_name, names, has_tests))
        if "pom.xml" in names:
            projects.append(detect_other(root, dir_name, "java", names, pipeline_has_tests(dir_name, files, project_path, "pom.xml")))
        if names & {"build.gradle", "build.gradle.kts"}:
            projects.append(detect_other(root, dir_name, "java", names, pipeline_has_tests(dir_name, files, project_path, "build.gradle")))
        if "go.mod" in names:
            projects.append(detect_other(root, dir_name, "go", names, pipeline_has_tests(dir_name, files, project_path, "go.mod")))
        if "Cargo.toml" in names:
            projects.append(detect_other(root, dir_name, "rust", names, pipeline_has_tests(dir_name, files, project_path, "Cargo.toml")))

    docker = sorted({p for p in files if Path(p).name.startswith("Dockerfile") or Path(p).name in {"docker-compose.yml", "compose.yaml"}})
    iac = sorted({p for p in files if p.endswith(".tf") or Path(p).name in {"serverless.yml", "template.yaml", "cdk.json", "Pulumi.yaml", "Chart.yaml"}})[:10]
    deploy_hints = sorted({label for name, label in (("vercel.json", "vercel"), ("netlify.toml", "netlify"), ("app.yaml", "gcp-app-engine"), ("fly.toml", "fly.io"), ("Procfile", "heroku")) for p in files if Path(p).name == name})
    ci_platforms = sorted({name for name, fn in CI_PATTERNS.items() if any(fn(f) for f in files)})
    payload = {
        "projects": sorted(projects, key=lambda item: item.get("dir", ".")),
        "docker": docker,
        "iac": iac,
        "deploy_hints": deploy_hints,
        "ci_platforms": ci_platforms,
        "monorepo": len(projects) > 1,
    }
    print(json.dumps(clean(payload), separators=(",", ":")))


if __name__ == "__main__":
    main()
