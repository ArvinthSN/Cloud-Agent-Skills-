"""Post-generation verification for Cloud Agent Skills.

Runs deterministic validators by default. Potentially executable operations
(Docker builds and Terraform plans) require explicit CLI opt-in.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

SCHEMA_VERSION = "1.0"
SKIP_DIRS = {
    ".git", ".terraform", ".cloud-agent", "node_modules", ".venv", "venv",
    "__pycache__", ".pytest_cache", ".mypy_cache", ".ruff_cache", "dist",
    "build", "target", "coverage", "htmlcov",
}
MAX_TERRAFORM_FILES = 500
MAX_TERRAFORM_BYTES = 20 * 1024 * 1024
VALID_STATUSES = {"PASS", "FAIL", "WARNING", "SKIPPED", "NOT_RUN"}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _check(
    checks: list[dict[str, str]],
    *,
    skill: str,
    category: str,
    name: str,
    status: str,
    tool: str,
    detail: str,
) -> None:
    if status not in VALID_STATUSES:
        raise ValueError(f"Unsupported verification status: {status}")
    checks.append({
        "skill": skill,
        "category": category,
        "name": name,
        "status": status,
        "tool": tool,
        "detail": detail[:1000],
    })


def _run(command: list[str], *, cwd: Path, timeout: int = 120, env: dict[str, str] | None = None):
    try:
        return subprocess.run(
            command,
            cwd=str(cwd),
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
            env=env,
        )
    except subprocess.TimeoutExpired:
        return None
    except OSError:
        return None


def _parse_json(text: str) -> Any:
    try:
        return json.loads(text)
    except (TypeError, json.JSONDecodeError):
        return None


def _safe_project_root(plan: dict[str, Any]) -> Path:
    root = Path(plan["workflow"]["project_dir"]).resolve()
    if not root.is_dir() or root.is_symlink():
        raise ValueError(f"Planned project directory is missing or unsafe: {root}")
    return root


def _artifact_paths(plan: dict[str, Any], run_dir: Path) -> list[tuple[str, Path]]:
    paths: list[tuple[str, Path]] = []
    for skill in plan["selected_skills"]:
        handoff_path = run_dir / "handoffs" / skill / "handoff.json"
        if handoff_path.is_symlink() or not handoff_path.is_file():
            raise ValueError(f"Missing or unsafe handoff for {skill}")
        handoff = json.loads(handoff_path.read_text(encoding="utf-8"))
        if skill == "app-containerizer":
            root = Path(handoff["project_root"]).resolve()
            paths.extend((("app-containerizer", root / name)) for name in handoff.get("outputs", []))
        elif skill == "cicd-pipeline-creator":
            output_dir = Path(handoff["output_dir"]).resolve()
            paths.extend((("cicd-pipeline-creator", output_dir / name)) for name in handoff.get("outputs", []))
        elif skill == "infra-creator":
            output_dir = Path(handoff["output_dir"]).resolve()
            paths.extend((("infra-creator", output_dir / name.rstrip("/"))) for name in handoff.get("outputs", []))
    return paths


def _verify_artifact_presence(paths: list[tuple[str, Path]], checks: list[dict[str, str]]) -> None:
    for skill, path in paths:
        safe = not path.is_symlink()
        exists = safe and (path.is_file() or path.is_dir())
        _check(
            checks, skill=skill, category="artifact",
            name=f"artifact:{path.name}",
            status="PASS" if exists else "FAIL",
            tool="filesystem",
            detail=f"Generated artifact exists: {path}" if exists else f"Generated artifact is missing or unsafe: {path}",
        )


def _verify_container(
    root: Path,
    checks: list[dict[str, str]],
    *,
    docker_build: bool,
    run_id: str,
) -> None:
    skill_root = Path(__file__).resolve().parents[1] / "skills" / "app-containerizer"
    validator = skill_root / "scripts" / "validate_container.py"
    result = _run([sys.executable, str(validator), "--path", str(root)], cwd=root, timeout=60)
    payload = _parse_json(result.stdout if result else "")
    if result is None or not isinstance(payload, list):
        _check(checks, skill="app-containerizer", category="static", name="container-static-validation",
               status="FAIL", tool="validate_container.py", detail="Container static validator could not complete or returned invalid JSON.")
    else:
        for item in payload:
            status = str(item.get("status", "WARNING")).upper()
            if status not in VALID_STATUSES:
                status = "WARNING"
            _check(checks, skill="app-containerizer", category="static",
                   name=str(item.get("check", "container-check")), status=status,
                   tool="validate_container.py", detail=str(item.get("detail", "")))

    docker = shutil.which("docker")
    if not docker_build:
        _check(checks, skill="app-containerizer", category="build", name="docker-image-build",
               status="SKIPPED", tool="docker", detail="Not requested. Use --docker-build to run an isolated, no-network local image build.")
    elif not docker:
        _check(checks, skill="app-containerizer", category="build", name="docker-image-build",
               status="NOT_RUN", tool="docker", detail="Docker CLI is not installed; an image was not built.")
    elif not (root / "Dockerfile").is_file():
        _check(checks, skill="app-containerizer", category="build", name="docker-image-build",
               status="FAIL", tool="docker", detail="Dockerfile is missing.")
    else:
        tag = f"cloud-agent-verify:{run_id.replace('-', '')[:12]}"
        built = _run(
            [docker, "build", "--network=none", "--pull=false", "--tag", tag, str(root)],
            cwd=root, timeout=600,
        )
        if built is None:
            status, detail = "FAIL", "Docker build could not complete (OS error or 10-minute timeout)."
        elif built.returncode == 0:
            status, detail = "PASS", "Docker image built successfully with network disabled and without pulling base images."
        else:
            status, detail = "FAIL", f"Docker build failed with exit code {built.returncode}. Build output is intentionally not copied into the report."
        _check(checks, skill="app-containerizer", category="build", name="docker-image-build",
               status=status, tool="docker", detail=detail)
        if built is not None and built.returncode == 0:
            removed = _run([docker, "image", "rm", tag], cwd=root, timeout=60)
            _check(checks, skill="app-containerizer", category="build", name="docker-image-cleanup",
                   status="PASS" if removed is not None and removed.returncode == 0 else "WARNING",
                   tool="docker", detail="Temporary verification image removed." if removed is not None and removed.returncode == 0 else "Temporary image cleanup could not be confirmed; remove it manually if it remains.")


def _verify_pipeline(root: Path, handoff: dict[str, Any], checks: list[dict[str, str]]) -> None:
    skill_root = Path(__file__).resolve().parents[1] / "skills" / "cicd-pipeline-creator"
    validator = skill_root / "scripts" / "validate_pipeline.py"
    output_dir = Path(handoff["output_dir"]).resolve()
    pipeline_names = {
        "github": "pipeline.yml",
        "azure": "azure-pipeline.yml",
        "gitlab": ".gitlab-ci.yml",
        "jenkins": "Jenkinsfile",
        "circleci": ".circleci/config.yml",
    }
    platform = handoff.get("platform", "")
    pipeline = output_dir / pipeline_names.get(platform, "")
    if not pipeline.is_file() or pipeline.is_symlink():
        _check(checks, skill="cicd-pipeline-creator", category="native",
               name="pipeline-validation", status="FAIL", tool="validate_pipeline.py",
               detail=f"Expected pipeline file is missing or unsafe: {pipeline}")
        return
    result = _run([sys.executable, str(validator), str(pipeline), "--json"], cwd=root, timeout=90)
    payload = _parse_json(result.stdout if result else "")
    if result is None or not isinstance(payload, dict):
        _check(checks, skill="cicd-pipeline-creator", category="native",
               name="pipeline-validation", status="FAIL", tool="validate_pipeline.py",
               detail="Pipeline validator could not complete or returned invalid JSON.")
        return
    status = {"pass": "PASS", "warning": "WARNING", "fail": "FAIL"}.get(payload.get("status"), "FAIL")
    _check(checks, skill="cicd-pipeline-creator", category="static",
           name="pipeline-policy-validation", status=status, tool="validate_pipeline.py",
           detail=f"{len(payload.get('errors', []))} errors; {len(payload.get('warnings', []))} warnings.")
    for item in payload.get("ran", []):
        upper = str(item).upper()
        check_status = "FAIL" if " FAIL" in upper else "PASS"
        _check(checks, skill="cicd-pipeline-creator", category="native",
               name="native:" + str(item).split(":", 1)[-1].split(" ", 1)[0],
               status=check_status, tool="native-validator", detail=str(item))
    for item in payload.get("skipped", []):
        _check(checks, skill="cicd-pipeline-creator", category="native",
               name="native-validator-availability", status="NOT_RUN",
               tool="native-validator", detail=str(item))


def _verify_terraform_static(
    infra_dir: Path,
    checks: list[dict[str, str]],
    *,
    run_plan: bool,
) -> None:
    skill_root = Path(__file__).resolve().parents[1] / "skills" / "infra-creator"
    validator = skill_root / "scripts" / "validate_terraform.py"
    result = _run([sys.executable, str(validator), str(infra_dir), "--json"], cwd=infra_dir, timeout=240)
    payload = _parse_json(result.stdout if result else "")
    if result is None or not isinstance(payload, dict):
        _check(checks, skill="infra-creator", category="static",
               name="terraform-static-validation", status="FAIL", tool="validate_terraform.py",
               detail="Terraform validator could not complete or returned invalid JSON.")
    else:
        policy = payload.get("policy_ok")
        _check(checks, skill="infra-creator", category="security",
               name="terraform-security-policy",
               status="PASS" if policy is True else "FAIL" if policy is False else "NOT_RUN",
               tool="validate_terraform.py",
               detail="Provider-aware static Terraform security policies evaluated.")
        if payload.get("terraform_available"):
            for field, label in (("fmt_ok", "terraform-fmt"), ("init_ok", "terraform-init"), ("validate_ok", "terraform-validate")):
                value = payload.get(field)
                _check(checks, skill="infra-creator", category="static", name=label,
                       status="PASS" if value is True else "FAIL" if value is False else "NOT_RUN",
                       tool="terraform", detail=f"{label} result: {value}.")
        else:
            _check(checks, skill="infra-creator", category="static",
                   name="terraform-cli-validation", status="NOT_RUN", tool="terraform",
                   detail="Terraform CLI unavailable; fmt, init and validate did not run.")

    if not run_plan:
        _check(checks, skill="infra-creator", category="plan", name="terraform-plan",
               status="SKIPPED", tool="terraform",
               detail="Not requested. Use --terraform-plan after reviewing the generated Terraform configuration.")
    else:
        _run_terraform_plan(infra_dir, checks)


def _terraform_environment(temp_home: Path) -> dict[str, str]:
    allowed = {"PATH", "SYSTEMROOT", "WINDIR", "TEMP", "TMP", "TMPDIR"}
    env = {key: value for key, value in os.environ.items() if key.upper() in allowed}
    env["HOME"] = str(temp_home)
    env["USERPROFILE"] = str(temp_home)
    env["TF_IN_AUTOMATION"] = "1"
    env["TF_INPUT"] = "0"
    return env


def _copy_terraform_sources(source: Path, target: Path) -> int:
    count = 0
    total = 0
    for current, dirs, names in os.walk(source, followlinks=False):
        base = Path(current)
        for directory in list(dirs):
            item = base / directory
            if item.is_symlink():
                raise ValueError(f"Terraform plan refuses symlinked directories: {item}")
            if directory in SKIP_DIRS:
                dirs.remove(directory)
        for name in names:
            item = base / name
            if item.is_symlink():
                raise ValueError(f"Terraform plan refuses symlinked files: {item}")
            if item.name.endswith((".tfstate", ".tfstate.backup", ".tfplan", ".tfvars", ".tfvars.json")):
                continue
            if item.name.startswith(".env") or item.suffix.lower() in {".pem", ".key", ".p12", ".pfx"}:
                continue
            if item.suffix not in {".tf", ".json"} and item.name != ".terraform.lock.hcl":
                continue
            if item.suffix == ".json" and not item.name.endswith(".tf.json"):
                continue
            size = item.stat().st_size
            count += 1
            total += size
            if count > MAX_TERRAFORM_FILES or total > MAX_TERRAFORM_BYTES:
                raise ValueError("Terraform plan input exceeds 500 files / 20 MiB.")
            destination = target / item.relative_to(source)
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(item, destination)
    if count == 0:
        raise ValueError("No Terraform configuration files were found.")
    return count


def _run_terraform_plan(infra_dir: Path, checks: list[dict[str, str]]) -> None:
    terraform = shutil.which("terraform")
    if not terraform:
        _check(checks, skill="infra-creator", category="plan", name="terraform-plan",
               status="NOT_RUN", tool="terraform", detail="Terraform CLI is not installed.")
        return
    try:
        with tempfile.TemporaryDirectory(prefix="cloud-agent-tf-plan-") as temporary:
            temp_root = Path(temporary)
            workspace = temp_root / "workspace"
            workspace.mkdir()
            copied = _copy_terraform_sources(infra_dir, workspace)
            env = _terraform_environment(temp_root / "home")
            (temp_root / "home").mkdir()
            init = _run([terraform, "init", "-backend=false", "-input=false", "-no-color"], cwd=workspace, timeout=300, env=env)
            if init is None or init.returncode != 0:
                _check(checks, skill="infra-creator", category="plan", name="terraform-plan-init",
                       status="FAIL", tool="terraform", detail="Isolated terraform init failed or timed out; no backend was initialized.")
                return
            validate = _run([terraform, "validate", "-no-color"], cwd=workspace, timeout=120, env=env)
            if validate is None or validate.returncode != 0:
                _check(checks, skill="infra-creator", category="plan", name="terraform-plan-validate",
                       status="FAIL", tool="terraform", detail="Terraform validate failed in the isolated workspace.")
                return
            plan_file = temp_root / "verification.tfplan"
            planned = _run(
                [terraform, "plan", "-refresh=false", "-input=false", "-lock=false", "-no-color", "-out", str(plan_file)],
                cwd=workspace, timeout=300, env=env,
            )
            if planned is None or planned.returncode != 0:
                _check(checks, skill="infra-creator", category="plan", name="terraform-plan",
                       status="FAIL", tool="terraform",
                       detail="Terraform plan failed. Required input variables, provider configuration or data sources may need review.")
            else:
                _check(checks, skill="infra-creator", category="plan", name="terraform-plan",
                       status="PASS", tool="terraform",
                       detail=f"Terraform plan completed for {copied} configuration/lock files in an isolated copy with backend disabled, refresh disabled and credentials removed from the process environment.")
    except (OSError, ValueError, shutil.Error) as exc:
        _check(checks, skill="infra-creator", category="plan", name="terraform-plan",
               status="FAIL", tool="terraform", detail=f"Terraform plan workspace could not be prepared safely: {exc}")


def _security_scans(root: Path, infra_dirs: list[Path], checks: list[dict[str, str]]) -> None:
    gitleaks = shutil.which("gitleaks")
    if not gitleaks:
        _check(checks, skill="security", category="secrets", name="gitleaks-secret-scan",
               status="NOT_RUN", tool="gitleaks", detail="Gitleaks is not installed.")
    else:
        result = _run([gitleaks, "dir", str(root), "--redact", "--no-banner", "--report-format", "json"], cwd=root, timeout=300)
        if result is None:
            status, detail = "NOT_RUN", "Gitleaks could not complete or timed out."
        else:
            findings = _parse_json(result.stdout)
            count = len(findings) if isinstance(findings, list) else 0
            status = "FAIL" if result.returncode != 0 or count else "PASS"
            detail = f"Gitleaks completed; findings={count}; exit_code={result.returncode}. Secret values are not copied into this report."
        _check(checks, skill="security", category="secrets", name="gitleaks-secret-scan",
               status=status, tool="gitleaks", detail=detail)

    trivy = shutil.which("trivy")
    if not trivy:
        _check(checks, skill="security", category="security", name="trivy-filesystem-scan",
               status="NOT_RUN", tool="trivy", detail="Trivy is not installed.")
    else:
        command = [trivy, "fs", "--scanners", "misconfig,secret", "--skip-db-update",
                   "--exit-code", "1", "--format", "json"]
        for directory in sorted(SKIP_DIRS):
            command.extend(["--skip-dirs", directory])
        command.append(str(root))
        result = _run(command, cwd=root, timeout=600)
        payload = _parse_json(result.stdout if result else "")
        if result is None or not isinstance(payload, dict):
            status, detail = "NOT_RUN", "Trivy could not complete or returned invalid JSON."
        else:
            results = payload.get("Results", [])
            findings = sum(len(item.get("Misconfigurations") or []) + len(item.get("Secrets") or []) for item in results)
            status = "FAIL" if result.returncode != 0 or findings else "PASS"
            detail = f"Trivy filesystem scan completed; misconfiguration/secret findings={findings}; exit_code={result.returncode}. Match contents are omitted."
        _check(checks, skill="security", category="security", name="trivy-filesystem-scan",
               status=status, tool="trivy", detail=detail)

    checkov = shutil.which("checkov")
    if not infra_dirs:
        _check(checks, skill="security", category="iac", name="checkov-terraform-scan",
               status="SKIPPED", tool="checkov", detail="No Terraform output was selected.")
    elif not checkov:
        _check(checks, skill="security", category="iac", name="checkov-terraform-scan",
               status="NOT_RUN", tool="checkov", detail="Checkov is not installed.")
    else:
        failures = 0
        exit_code = 0
        completed = True
        for directory in infra_dirs:
            result = _run([checkov, "-d", str(directory), "--framework", "terraform", "-o", "json"],
                          cwd=directory, timeout=300)
            if result is None:
                completed = False
                break
            exit_code = max(exit_code, result.returncode)
            payload = _parse_json(result.stdout)
            if isinstance(payload, dict):
                failures += len(payload.get("results", {}).get("failed_checks", []))
            elif isinstance(payload, list):
                failures += sum(len(item.get("results", {}).get("failed_checks", [])) for item in payload if isinstance(item, dict))
            elif result.returncode:
                completed = False
                break
        status = "NOT_RUN" if not completed else "FAIL" if exit_code or failures else "PASS"
        detail = "Checkov could not complete or return JSON." if not completed else f"Checkov completed; failed policy checks={failures}; exit_code={exit_code}."
        _check(checks, skill="security", category="iac", name="checkov-terraform-scan",
               status=status, tool="checkov", detail=detail)


def verify_artifacts(
    plan: dict[str, Any],
    run_dir: Path,
    *,
    docker_build: bool = False,
    terraform_plan: bool = False,
) -> dict[str, Any]:
    """Verify generated artifacts and return a bounded, secret-safe evidence report."""
    run_dir = run_dir.resolve()
    root = _safe_project_root(plan)
    checks: list[dict[str, str]] = []
    artifacts = _artifact_paths(plan, run_dir)
    _verify_artifact_presence(artifacts, checks)

    handoffs: dict[str, dict[str, Any]] = {}
    for skill in plan["selected_skills"]:
        handoffs[skill] = json.loads((run_dir / "handoffs" / skill / "handoff.json").read_text(encoding="utf-8"))

    if "app-containerizer" in handoffs:
        _verify_container(root, checks, docker_build=docker_build, run_id=plan["run_id"])
    if "cicd-pipeline-creator" in handoffs:
        _verify_pipeline(root, handoffs["cicd-pipeline-creator"], checks)
    infra_dirs: list[Path] = []
    if "infra-creator" in handoffs:
        infra_dir = Path(handoffs["infra-creator"]["output_dir"]).resolve()
        infra_dirs.append(infra_dir)
        _verify_terraform_static(infra_dir, checks, run_plan=terraform_plan)

    _security_scans(root, infra_dirs, checks)
    counts = {status: sum(1 for item in checks if item["status"] == status) for status in sorted(VALID_STATUSES)}
    has_failures = counts["FAIL"] > 0
    has_incomplete = counts["NOT_RUN"] > 0 or counts["WARNING"] > 0
    return {
        "schema_version": SCHEMA_VERSION,
        "run_id": plan["run_id"],
        "project_root": str(root),
        "status": "failed" if has_failures else "partial" if has_incomplete else "completed",
        "requested_verifications": {
            "docker_build": docker_build,
            "terraform_plan": terraform_plan,
        },
        "summary": counts,
        "checks": checks[:200],
        "generated_at": _now(),
    }
