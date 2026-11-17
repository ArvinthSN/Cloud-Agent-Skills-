#!/usr/bin/env python3
"""Render a reviewed CI/CD starter for one detected Python or Node.js project."""
import argparse
import datetime
import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SUPPORTED = {
    "azure": ROOT / "templates" / "azure" / "azure-pipelines.yml",
    "github": ROOT / "templates" / "github" / "pipeline.yml",
    "gitlab": ROOT / "templates" / "gitlab" / ".gitlab-ci.yml",
    "jenkins": ROOT / "templates" / "jenkins" / "Jenkinsfile",
    "circleci": ROOT / "templates" / "circleci" / "config.yml",
}
OUTPUT_NAMES = {
    "azure": "azure-pipeline.yml",
    "github": "pipeline.yml",
    "gitlab": ".gitlab-ci.yml",
    "jenkins": "Jenkinsfile",
    "circleci": ".circleci/config.yml",
}
SUPPORTED_LANGUAGES = {"python", "node"}


def detect_values(repo: Path, project_dir: str | None = None, context_path: str | None = None) -> dict:
    if context_path:
        try:
            context = json.loads(Path(context_path).read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise SystemExit(f"Could not load orchestrator handoff context: {exc}") from exc
        project = context.get("ci_project") if isinstance(context, dict) else None
        if not isinstance(project, dict):
            raise SystemExit("Context file must contain a ci_project object.")
        projects = [project]
        data = {"projects": projects}
    else:
        proc = subprocess.run(
            [sys.executable, str(ROOT / "scripts" / "detect_stack.py"), str(repo)],
            capture_output=True,
            text=True,
            check=False,
        )
        if proc.returncode:
            raise SystemExit(f"Stack detection failed: {proc.stderr.strip() or proc.stdout.strip()}")
        try:
            data = json.loads(proc.stdout)
        except json.JSONDecodeError as exc:
            raise SystemExit(f"Stack detector returned invalid JSON: {exc}") from exc
        projects = data.get("projects", [])

    if project_dir is not None:
        matches = [item for item in projects if item.get("dir") == project_dir]
        if len(matches) != 1:
            raise SystemExit(f"Project directory not found or ambiguous: {project_dir}")
        project = matches[0]
    elif len(projects) == 1:
        project = projects[0]
    elif len(projects) > 1:
        choices = ", ".join(item.get("dir", ".") for item in projects)
        raise SystemExit(f"Monorepo detected. Select one project with --project-dir. Available: {choices}")
    else:
        raise SystemExit("No supported project manifest detected; refusing to generate placeholder commands.")

    lang = project.get("lang", "unknown")
    if lang not in SUPPORTED_LANGUAGES:
        raise SystemExit(
            f"Unsupported pipeline stack: {lang}. Renderer currently supports Python and Node.js only."
        )

    package_manager = project.get("pm", "unknown")
    lockfile = project.get("lockfile")
    if lang == "node" and (package_manager != "npm" or lockfile != "package-lock.json"):
        raise SystemExit("The Node.js pipeline renderer currently requires npm and package-lock.json. pnpm/yarn and unlocked projects are not supported yet.")
    if lang == "python" and package_manager not in {"pip", "poetry", "uv"}:
        raise SystemExit(f"Unsupported Python package manager: {package_manager}")
    install = project.get("install")
    build = project.get("build")
    if not install or not build or str(install).lstrip().startswith("echo ") or str(build).lstrip().startswith("echo "):
        raise SystemExit(
            "A real install and artifact-producing build command could not be detected. "
            "Use a supported manifest and configure an artifact-producing build before rendering."
        )

    version = str(project.get("version") or ("3.11" if lang == "python" else "20"))
    version_match = re.search(r"\d+(?:\.\d+)?", version)
    if not version_match:
        raise SystemExit(f"Could not resolve a concrete runtime version from: {version}")
    resolved_version = version_match.group(0)
    test = project.get("test") or "NO_TESTS_DETECTED"
    working_dir = project.get("dir", ".") or "."
    working_path = Path(working_dir)
    if working_path.is_absolute() or ".." in working_path.parts or (not re.fullmatch(r"[A-Za-z0-9._/-]+", working_dir)):
        raise SystemExit(f"Unsafe project working directory: {working_dir!r}")
    for label, command in (("install", install), ("build", build), ("test", test)):
        if not isinstance(command, str) or len(command) > 512 or any(ch in command for ch in "\r\n\0") or "'''" in command:
            raise SystemExit(f"Unsafe or oversized {label} command; use a single-line command of at most 512 characters.")
    lockfile = lockfile or ("pyproject.toml" if lang == "python" else "package-lock.json")
    cache_paths = {
        "pip": "~/.cache/pip",
        "poetry": "~/.cache/pypoetry",
        "uv": "~/.cache/uv",
        "npm": "~/.npm",
    }
    return {
        "PYTHON_VERSION": resolved_version if lang == "python" else "3.11",
        "NODE_VERSION": resolved_version if lang == "node" else "20",
        "INSTALL_CMD": install,
        "BUILD_CMD": build,
        "TEST_CMD": test,
        "ARTIFACT_PATH": "dist",
        "WORKING_DIR": working_path.as_posix(),
        "RUNNER_IMAGE": f"python:{resolved_version}-slim" if lang == "python" else f"node:{resolved_version}-bookworm",
        "BUILD_IMAGE": f"python:{resolved_version}-slim" if lang == "python" else f"node:{resolved_version}-bookworm",
        "DEPLOY_IMAGE": "alpine:3.21",
        "AGENT_LABEL": "linux-docker",
        "LANGUAGE": lang,
        "VERSION": resolved_version,
        "PACKAGE_MANAGER": package_manager,
        "LOCKFILE": lockfile,
        "CACHE_PATH": cache_paths[package_manager],
        "FETCH_DATE": datetime.date.today().isoformat(),
        "UPSTREAM_REF": "reviewed-template",
        "GITLEAKS_VERSION": "v8.30.0",
        "TRIVY_VERSION": "0.70.0",
        "OIDC_AUDIENCE": "cloud-agent-skills/unconfigured",
        "DEPLOY_CREDENTIALS_ID": "UNCONFIGURED_DEPLOY_CREDENTIALS",
        "APPROVERS": "jenkins-admins",
        "STAGING_URL": "https://invalid.invalid",
        "PRODUCTION_URL": "https://invalid.invalid",
        "STAGING_HEALTH_URL": "https://invalid.invalid",
        "PRODUCTION_HEALTH_URL": "https://invalid.invalid",
        "DEPLOY_CMD_STAGING": 'echo "Target-specific staging deployment is not configured."; exit 1',
        "DEPLOY_CMD_PRODUCTION": 'echo "Target-specific production deployment is not configured."; exit 1',
        "SERVICE_CONNECTION": "$(AZURE_SERVICE_CONNECTION)",
        "APP_TYPE": "webAppLinux",
        "TEST_REPORT_GLOB": "**/test-results.xml",
        "TEST_REPORT_PATH": "test-results.xml",
        "COVERAGE_REPORT": "coverage.xml",
    }


def render_template(template: str, values: dict) -> str:
    rendered = template
    for key, value in values.items():
        rendered = rendered.replace(f"@@{key}@@", str(value))
    unresolved = re.findall(r"@@[A-Z_]+@@", rendered)
    if unresolved:
        raise SystemExit(f"Unresolved template markers remain: {sorted(set(unresolved))}")
    return rendered


def write_notes(out_dir: Path, platform: str, values: dict) -> None:
    lines = [
        f"Detected: {values['LANGUAGE']} {values['VERSION']} ({values['PACKAGE_MANAGER']})",
        f"Platform: {platform}",
        "Secrets/Variables: configure platform-native secret storage; never commit values",
        "Assumptions: artifact output is ./dist; review build output before enabling deployment",
        "TODO(verify): review action/task versions and provider-specific deployment configuration",
        "Validation: generated only; run validate_pipeline.py and the platform-native validator",
    ]
    if platform == "github":
        lines.append("Required variable: ALLOW_NO_TESTS. DEPLOY_ENABLED must remain false until a target-specific deploy job is configured.")
        lines.append("All GitHub Actions dependencies are pinned to full commit SHAs; review and refresh pins deliberately.")
    elif platform == "azure":
        lines.append("Required variables/service connection: ALLOW_NO_TESTS, DEPLOY_ENABLED, DEPLOY_TARGET, DEPLOY_RESOURCE_GROUP, STAGING_URL, PRODUCTION_URL, AZURE_SERVICE_CONNECTION.")
    elif platform == "gitlab":
        lines.append("Deployment is disabled by default. Configure protected environments, OIDC trust, and target-specific commands before enabling DEPLOY_ENABLED.")
        lines.append("Review container image tags and pin approved images to registry digests for high-assurance environments.")
    elif platform == "jenkins":
        lines.append("Requires a Docker-capable agent labeled linux-docker, Pipeline and Workspace Cleanup plugins, and configured approval/credential IDs.")
        lines.append("Deployment commands intentionally fail closed until target-specific staging and production commands are configured.")
    else:
        lines.append("Configure CircleCI contexts, restricted environment variables, and a target-specific deploy job before enabling deployment.")
        lines.append("Review scanner image tags and pin approved images to registry digests for high-assurance environments.")
    (out_dir / "PIPELINE_NOTES.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Render a repository-specific CI/CD starter.")
    parser.add_argument("repo")
    parser.add_argument("platform")
    parser.add_argument("--out", default=".")
    parser.add_argument("--project-dir", help="Exact project directory for a monorepo")
    parser.add_argument("--context", help="Use a precomputed orchestrator ci_project handoff; skip repository re-scan")
    parser.add_argument("--overwrite", action="store_true", help="Allow replacing generated output after review")
    args = parser.parse_args()

    platform = args.platform.lower()
    if platform not in SUPPORTED:
        raise SystemExit(f"Unsupported renderer platform: {platform}. Supported: {', '.join(sorted(SUPPORTED))}")
    repo = Path(args.repo).resolve()
    if not repo.is_dir():
        raise SystemExit(f"Repository directory does not exist: {repo}")

    template_path = SUPPORTED[platform]
    if not template_path.is_file():
        raise SystemExit(f"Template not found: {template_path}")
    values = detect_values(repo, args.project_dir, args.context)
    rendered = render_template(template_path.read_text(encoding="utf-8"), values)

    out_dir = Path(args.out).resolve()
    out_file = out_dir / OUTPUT_NAMES[platform]
    notes_file = out_dir / "PIPELINE_NOTES.md"
    existing = [item.name for item in (out_file, notes_file) if item.exists()]
    if existing and not args.overwrite:
        raise SystemExit(f"Existing output preserved: {existing}. Pass --overwrite only after review.")

    out_dir.mkdir(parents=True, exist_ok=True)
    out_file.parent.mkdir(parents=True, exist_ok=True)
    out_file.write_text(rendered, encoding="utf-8")
    write_notes(out_dir, platform, values)
    print(str(out_file))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
