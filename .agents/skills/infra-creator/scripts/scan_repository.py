#!/usr/bin/env python3
"""Repository scanner for infra-creator (cloud-agnostic)."""

from __future__ import annotations

import argparse
import json
import logging
import os
import re
import sys
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger("scan_repository")

IGNORE_DIRS = {
    ".git", "node_modules", ".venv", "venv", "__pycache__", ".pytest_cache",
    ".mypy_cache", ".tox", "dist", "build", ".next", ".nuxt", "coverage",
    ".coverage", "htmlcov", ".idea", ".vscode", ".terraform", "vendor",
    "target", "bin", "obj",
}

LANGUAGE_MARKERS: dict[str, list[str]] = {
    "python": [".py", "requirements.txt", "pyproject.toml", "setup.py", "Pipfile", "poetry.lock"],
    "javascript": [".js", "package.json", "package-lock.json", "yarn.lock"],
    "typescript": [".ts", ".tsx", "tsconfig.json"],
    "go": [".go", "go.mod", "go.sum"],
    "java": [".java", "pom.xml", "build.gradle", "build.gradle.kts"],
    "ruby": [".rb", "Gemfile"],
    "php": [".php", "composer.json"],
    "rust": [".rs", "Cargo.toml"],
    "csharp": [".cs", ".csproj"],
}

FRAMEWORK_MARKERS: dict[str, list[str]] = {
    "fastapi": ["fastapi", "from fastapi"],
    "flask": ["flask", "from flask"],
    "django": ["django", "DJANGO_SETTINGS_MODULE"],
    "express": ["express", "require('express')", 'require("express")'],
    "nestjs": ["@nestjs", "nestjs"],
    "nextjs": ["next", "next.config"],
    "react": ["react", "react-dom"],
    "vue": ["vue", "createApp"],
    "spring": ["springframework", "spring-boot"],
    "gin": ["github.com/gin-gonic/gin"],
}

DATABASE_MARKERS: dict[str, list[str]] = {
    "postgresql": ["postgres", "postgresql", "psycopg2", "asyncpg", "pgx"],
    "mysql": ["mysql", "pymysql", "mysqlclient"],
    "mongodb": ["mongodb", "pymongo", "mongoose"],
    "redis": ["redis", "ioredis", "go-redis"],
    "sqlite": ["sqlite", "sqlite3"],
    "dynamodb": ["dynamodb"],
    "cosmosdb": ["cosmosdb", "azure.cosmos"],
    "firestore": ["firestore", "google.cloud.firestore"],
}

ENV_VAR_PATTERN = re.compile(
    r"""(?:os\.environ(?:\.get)?|os\.getenv|process\.env|ENV\[|getenv\(|dotenv|env\()[\(\[\"'\s]*([A-Z][A-Z0-9_]{2,})""",
    re.IGNORECASE,
)
SENSITIVE_ENV_HINTS = re.compile(
    r"(PASSWORD|SECRET|KEY|TOKEN|CREDENTIAL|AUTH|PRIVATE|API_KEY|ACCESS_KEY)",
    re.IGNORECASE,
)


@dataclass
class RepositoryReport:
    root: str
    languages: list[str] = field(default_factory=list)
    frameworks: list[str] = field(default_factory=list)
    has_dockerfile: bool = False
    has_docker_compose: bool = False
    docker_files: list[str] = field(default_factory=list)
    databases: list[str] = field(default_factory=list)
    dependency_files: list[str] = field(default_factory=list)
    env_var_names: list[str] = field(default_factory=list)
    sensitive_env_var_names: list[str] = field(default_factory=list)
    infra_files: list[str] = field(default_factory=list)
    top_level_dirs: list[str] = field(default_factory=list)
    entry_points: list[str] = field(default_factory=list)
    service_dirs: list[str] = field(default_factory=list)
    file_count: int = 0
    total_size_bytes: int = 0
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def should_ignore(path: Path, root: Path) -> bool:
    rel = path.relative_to(root)
    for part in rel.parts:
        if part in IGNORE_DIRS:
            return True
        if part.startswith(".") and path.is_dir() and part not in {".env.example"}:
            return True
    return False


def detect_languages(files: list[Path]) -> list[str]:
    found: set[str] = set()
    for f in files:
        name, ext = f.name.lower(), f.suffix.lower()
        for lang, markers in LANGUAGE_MARKERS.items():
            if ext in markers or name in markers:
                found.add(lang)
    return sorted(found)


def detect_frameworks(files: list[Path]) -> list[str]:
    found: set[str] = set()
    dep_names = {
        "requirements.txt", "pyproject.toml", "package.json", "go.mod",
        "pom.xml", "build.gradle", "gemfile", "composer.json", "cargo.toml",
    }
    for f in files:
        if f.name.lower() in dep_names or f.suffix.lower() in {".py", ".js", ".ts", ".go"}:
            try:
                if f.stat().st_size > 200_000:
                    continue
                text = f.read_text(encoding="utf-8", errors="ignore")[:40_000]
                for fw, markers in FRAMEWORK_MARKERS.items():
                    if any(m in text for m in markers):
                        found.add(fw)
            except OSError:
                continue
    return sorted(found)


def detect_databases(content_samples: list[str]) -> list[str]:
    found: set[str] = set()
    for text in content_samples:
        lower = text.lower()
        for db, markers in DATABASE_MARKERS.items():
            if any(m in lower for m in markers):
                found.add(db)
    return sorted(found)


def extract_env_vars(files: list[Path]) -> tuple[list[str], list[str]]:
    names: set[str] = set()
    for f in files:
        if f.suffix.lower() in {".py", ".js", ".ts", ".go", ".env", ".yml", ".yaml", ".toml", ".json"} or f.name in {
            ".env.example", ".env.sample", ".env.template"
        }:
            try:
                if f.stat().st_size > 200_000:
                    continue
                text = f.read_text(encoding="utf-8", errors="ignore")
                for match in ENV_VAR_PATTERN.finditer(text):
                    names.add(match.group(1).upper())
                if f.name.startswith(".env"):
                    for line in text.splitlines():
                        line = line.strip()
                        if line and not line.startswith("#") and "=" in line:
                            key = line.split("=", 1)[0].strip().upper()
                            if key:
                                names.add(key)
            except OSError:
                continue
    all_names = sorted(names)
    sensitive = sorted(n for n in all_names if SENSITIVE_ENV_HINTS.search(n))
    return all_names, sensitive


def find_entry_points(root: Path, files: list[Path]) -> list[str]:
    common = {"main.py", "app.py", "server.py", "index.js", "index.ts", "main.go", "manage.py", "wsgi.py", "asgi.py"}
    return sorted(str(f.relative_to(root)) for f in files if f.name.lower() in common)


def find_service_dirs(root: Path, top_dirs: list[str]) -> list[str]:
    service_like = []
    for d in top_dirs:
        p = root / d
        if not p.is_dir():
            continue
        markers = list(p.glob("Dockerfile")) + list(p.glob("package.json")) + list(p.glob("requirements.txt")) + list(p.glob("go.mod"))
        if markers:
            service_like.append(d)
        # nested services/
        if d in {"services", "apps", "microservices"}:
            for sub in p.iterdir():
                if sub.is_dir() and (
                    list(sub.glob("Dockerfile")) or list(sub.glob("package.json")) or list(sub.glob("requirements.txt"))
                ):
                    service_like.append(f"{d}/{sub.name}")
    return sorted(set(service_like))


def scan_repository(repo_path: str | Path) -> RepositoryReport:
    root = Path(repo_path).resolve()
    if not root.is_dir():
        raise FileNotFoundError(f"Repository path does not exist or is not a directory: {root}")

    report = RepositoryReport(root=str(root))
    all_files: list[Path] = []

    for dirpath, dirnames, filenames in os.walk(root):
        current = Path(dirpath)
        dirnames[:] = [d for d in dirnames if d not in IGNORE_DIRS]
        if should_ignore(current, root) and current != root:
            dirnames.clear()
            continue
        if current == root:
            report.top_level_dirs = sorted(d for d in dirnames if d not in IGNORE_DIRS and not d.startswith("."))
        for name in filenames:
            fp = current / name
            try:
                size = fp.stat().st_size
            except OSError:
                continue
            all_files.append(fp)
            report.file_count += 1
            report.total_size_bytes += size

    for f in all_files:
        name = f.name.lower()
        rel = str(f.relative_to(root))
        if name == "dockerfile" or name.startswith("dockerfile."):
            report.has_dockerfile = True
            report.docker_files.append(rel)
        if name in {"docker-compose.yml", "docker-compose.yaml", "compose.yml", "compose.yaml"}:
            report.has_docker_compose = True
            report.docker_files.append(rel)
        if name in {
            "requirements.txt", "pyproject.toml", "pipfile", "package.json", "go.mod",
            "pom.xml", "build.gradle", "build.gradle.kts", "gemfile", "composer.json", "cargo.toml",
        }:
            report.dependency_files.append(rel)
        if any(x in rel.lower() for x in ["terraform", ".tf", "cloudformation", "cdk", "pulumi", "serverless.yml", "bicep", "arm.json"]):
            report.infra_files.append(rel)

    report.languages = detect_languages(all_files)
    report.frameworks = detect_frameworks(all_files)

    samples: list[str] = []
    for f in all_files:
        if f.name.lower() in {
            "requirements.txt", "package.json", "go.mod", "pyproject.toml"
        } or f.suffix.lower() in {".py", ".js", ".ts", ".go"} or f.name.startswith(".env"):
            try:
                samples.append(f.read_text(encoding="utf-8", errors="ignore")[:30_000])
            except OSError:
                pass
    report.databases = detect_databases(samples)
    report.env_var_names, report.sensitive_env_var_names = extract_env_vars(all_files)
    report.entry_points = find_entry_points(root, all_files)
    report.service_dirs = find_service_dirs(root, report.top_level_dirs)

    if not report.languages:
        report.notes.append("No clear programming language detected")
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description="Scan an application repository")
    parser.add_argument("path", help="Path to the application repository")
    parser.add_argument("--json", action="store_true")
    parser.add_argument("-o", "--output", help="Write report to file")
    parser.add_argument("-v", "--verbose", action="store_true")
    args = parser.parse_args()
    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)
    try:
        report = scan_repository(args.path)
    except Exception as exc:
        logger.error("%s", exc)
        return 1
    text = json.dumps(report.to_dict(), indent=2)
    if args.output:
        Path(args.output).write_text(text, encoding="utf-8")
        logger.info("Wrote report to %s", args.output)
    else:
        print(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())