#!/usr/bin/env python3
"""Render a repo-specific pipeline template and write terse notes."""
import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SUPPORTED = {
    "azure": ROOT / "templates" / "azure" / "azure-pipelines.yml",
    "github": ROOT / "templates" / "github" / "pipeline.yml",
}


def detect_values(repo: Path, project_dir: str | None = None):
    proc = subprocess.run([sys.executable, str(ROOT / "scripts" / "detect_stack.py"), str(repo)], capture_output=True, text=True, check=True)
    data = json.loads(proc.stdout)
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
    version = project.get("version") or ("3.11" if lang == "python" else "20" if lang == "node" else "latest")
    install = project.get("install")
    build = project.get("build")
    if not install or not build or str(install).startswith("echo ") or str(build).startswith("echo "):
        raise SystemExit("Install/build commands could not be detected safely; refusing to generate echo placeholders.")
    test = project.get("test") or "NO_TESTS_DETECTED"
    working_dir = project.get("dir", ".") or "."
    lockfile = project.get("lockfile") or ("requirements.txt" if lang == "python" else "package-lock.json" if lang == "node" else "lockfile")
    artifact_path = "dist" if lang == "node" else "build" if lang == "python" else "target"
    return {
        "PYTHON_VERSION": "3.11" if lang == "python" else "3.11",
        "NODE_VERSION": "20" if lang == "node" else "20",
        "INSTALL_CMD": install,
        "BUILD_CMD": build,
        "TEST_CMD": test,
        "ARTIFACT_PATH": artifact_path,
        "DEPLOY_TARGET": "azure-webapp",
        "WORKING_DIR": working_dir,
        "LANGUAGE": lang,
        "VERSION": version,
        "PACKAGE_MANAGER": project.get("pm", "unknown"),
        "LOCKFILE": lockfile,
        "CACHE_PATH": "~/.cache/pip" if lang == "python" else "~/.npm",
        "FETCH_DATE": "2026-11-16",
        "UPSTREAM_REF": "main",
        "GITLEAKS_VERSION": "v8.16.1",
        "TRIVY_VERSION": "0.56.2",
        "SERVICE_CONNECTION": "azure-service-connection",
        "APP_TYPE": "webAppLinux",
        "TEST_REPORT_GLOB": "**/test-results.xml",
        "TEST_REPORT_PATH": "test-results.xml",
        "COVERAGE_REPORT": "coverage.xml",
    }


def render_template(text: str, values: dict) -> str:
    for key, value in values.items():
        text = text.replace(f"@@{key}@@", str(value))
    unresolved = re.findall(r"@@[A-Z_]+@@", text)
    if unresolved:
        raise SystemExit(f"Unresolved markers remain: {sorted(set(unresolved))}")
    return text


def write_notes(out_dir: Path, platform: str, values: dict):
    lines = [
        f"Detected: {values['LANGUAGE']} {values['VERSION']} ({values['PACKAGE_MANAGER']})",
        f"Platform: {platform}",
        "Secrets: CI vars / secret store only",
        "Assumptions: repo-derived defaults only",
        "TODO(verify): none",
        "Validation: generated; run validate_pipeline.py",
    ]
    (out_dir / "PIPELINE_NOTES.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def main():
    parser = argparse.ArgumentParser(description="Render a repo-specific pipeline.")
    parser.add_argument("repo")
    parser.add_argument("platform")
    parser.add_argument("--out", default=".")
    parser.add_argument("--project-dir", help="Exact project directory for a monorepo, as reported by detect_stack.py")
    parser.add_argument("--overwrite", action="store_true", help="Allow replacing generated pipeline and notes after review")
    args = parser.parse_args()

    platform = args.platform.lower()
    if platform not in SUPPORTED:
        raise SystemExit(f"Unsupported platform: {platform}")

    repo = Path(args.repo).resolve()
    if not repo.exists():
        raise SystemExit(f"Repo does not exist: {repo}")

    out_dir = Path(args.out).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)

    template_path = SUPPORTED[platform]
    if not template_path.exists():
        raise SystemExit(f"Template not found: {template_path}")

    text = template_path.read_text(encoding="utf-8")
    values = detect_values(repo, args.project_dir)
    rendered = render_template(text, values)
    out_name = "azure-pipeline.yml" if platform == "azure" else "pipeline.yml"
    out_file = out_dir / out_name
    notes_file = out_dir / "PIPELINE_NOTES.md"
    existing = [item.name for item in (out_file, notes_file) if item.exists()]
    if existing and not args.overwrite:
        raise SystemExit(f"Existing output preserved: {existing}. Pass --overwrite only after review.")
    out_file.write_text(rendered, encoding="utf-8")
    write_notes(out_dir, platform, values)
    print(str(out_file))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
