import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / ".agents"))

from intelligence.engine import build_architecture_profile, build_skill_selection


def project(directory, language, framework, manifest, ci_lang=None, package_manager="npm", lockfile="package-lock.json"):
    return {
        "id": f"{directory}:{language}",
        "dir": directory,
        "language": language,
        "ci_lang": ci_lang or language,
        "framework": framework,
        "databases": [],
        "package_manager": package_manager,
        "manifest": manifest,
        "version": "22",
        "entry_point": "main",
        "start_command": ["npm", "start"],
        "install_command": "npm ci",
        "build_command": "npm run build",
        "test_command": "npm test",
        "lockfile": lockfile,
    }


def context(projects):
    return {
        "root": "/workspace/sample",
        "snapshot_hash": "a" * 64,
        "projects": projects,
        "databases": ["postgresql"],
        "service_dirs": [],
        "scan_truncated": False,
    }


def test_architecture_profile_detects_frontend_backend_with_evidence():
    scan = context([
        project("web", "node", "react", "package.json"),
        project("api", "java", "spring", "pom.xml", ci_lang="java", package_manager="maven", lockfile=None),
    ])

    profile = build_architecture_profile(scan)

    assert profile["architecture"] == "frontend_backend"
    assert profile["confidence"] >= 0.7
    assert {item["type"] for item in profile["components"]} >= {"frontend", "backend", "data_store"}
    assert all(item["evidence"] for item in profile["components"])


def test_auto_selection_selects_ready_skill_and_reports_missing_ci_platform():
    scan = context([project(".", "node", "express", "package.json")])
    profile = build_architecture_profile(scan)

    selection = build_skill_selection(
        mode="auto",
        goal="Dockerize this app and create a CI pipeline",
        requested_skills=[],
        profile=profile,
        context=scan,
        provider=None,
        platform=None,
        project_dir=".",
    )

    assert selection["selected_skills"] == ["app-containerizer"]
    blocked = {item["skill"]: item["missing_requirements"] for item in selection["blocked"]}
    assert blocked["cicd-pipeline-creator"] == ["ci_platform"]
    assert selection["unresolved_requirements"] == ["ci_platform"]


def test_auto_selection_never_guesses_cloud_provider():
    scan = context([project(".", "python", "fastapi", "pyproject.toml", ci_lang="python", package_manager="pip", lockfile="requirements.txt")])
    profile = build_architecture_profile(scan)

    selection = build_skill_selection(
        mode="auto",
        goal="Create Terraform infrastructure",
        requested_skills=[],
        profile=profile,
        context=scan,
        provider=None,
        platform=None,
        project_dir=".",
    )

    assert selection["selected_skills"] == []
    assert selection["blocked"][0]["missing_requirements"] == ["cloud_provider"]


def test_auto_selection_requires_explicit_monorepo_project():
    scan = context([
        project("frontend", "node", "react", "package.json"),
        project("backend", "python", "fastapi", "pyproject.toml", ci_lang="python", package_manager="pip", lockfile="requirements.txt"),
    ])
    profile = build_architecture_profile(scan)

    selection = build_skill_selection(
        mode="auto",
        goal="Containerize the application",
        requested_skills=[],
        profile=profile,
        context=scan,
        provider=None,
        platform=None,
        project_dir=None,
    )

    assert selection["selected_skills"] == []
    assert "project_dir" in selection["unresolved_requirements"]
