#!/usr/bin/env python3
"""Run Cloud Agent Skills against pinned public application repositories.

This harness clones public source at fixed commits, runs only this repository's
read-only scanners and artifact generators, and never executes target app code,
Docker builds, Terraform init/plan/apply, or deployment commands.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
PY = sys.executable
TARGETS = [
    {
        "id": "spring-petclinic",
        "url": "https://github.com/spring-projects/spring-petclinic.git",
        "commit": "500158f732419217507c7656904b8e6aa1bcc0d6",
        "app_subdir": ".",
        "pipeline_project_dir": None,
        "pipeline_expected_block": True,
    },
    {
        "id": "fastapi-full-stack",
        "url": "https://github.com/fastapi/full-stack-fastapi-template.git",
        "commit": "77e550a73bb49dd2967622c5ed11bf7a49603c93",
        "app_subdir": "backend",
        "pipeline_project_dir": "backend",
        "pipeline_expected_block": False,
    },
    {
        "id": "spring-sample-web-app",
        "url": "https://github.com/onemoretechie/sample-web-app.git",
        "commit": "bc504c906ffc5c0ba825ef1c2634260b1f2690aa",
        "app_subdir": ".",
        "pipeline_project_dir": None,
        "pipeline_expected_block": True,
    },
]

COMMANDS: list[dict[str, Any]] = []


def run(label: str, args: list[str], cwd: Path | None = None, timeout: int = 300) -> dict[str, Any]:
    started = time.perf_counter()
    try:
        proc = subprocess.run(
            [str(part) for part in args],
            cwd=str(cwd) if cwd else None,
            text=True,
            capture_output=True,
            timeout=timeout,
            check=False,
        )
        item = {
            "label": label,
            "command": [str(part) for part in args],
            "cwd": str(cwd) if cwd else None,
            "return_code": proc.returncode,
            "elapsed_seconds": round(time.perf_counter() - started, 4),
            "stdout": proc.stdout[-5000:],
            "stderr": proc.stderr[-5000:],
            "status": "PASS" if proc.returncode == 0 else "FAIL",
        }
    except subprocess.TimeoutExpired as exc:
        item = {
            "label": label,
            "command": [str(part) for part in args],
            "cwd": str(cwd) if cwd else None,
            "return_code": None,
            "elapsed_seconds": round(time.perf_counter() - started, 4),
            "stdout": str(exc.stdout or "")[-5000:],
            "stderr": "Timed out",
            "status": "TIMEOUT",
        }
    COMMANDS.append(item)
    return item


def digest(paths: list[Path]) -> str | None:
    files = [p for p in paths if p.is_file()]
    if not files:
        return None
    h = hashlib.sha256()
    for path in sorted(files, key=lambda p: str(p)):
        h.update(path.name.encode("utf-8"))
        h.update(b"\0")
        h.update(path.read_bytes())
        h.update(b"\0")
    return h.hexdigest()


def copy_case_files(case_dir: Path, files: list[tuple[Path, str]]) -> None:
    for source, relative in files:
        if source.is_file():
            destination = case_dir / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, destination)


def write_case_metadata(
    case_dir: Path,
    first_hash: str | None,
    second_hash: str | None,
    elapsed: float,
    validation_passed: bool | None = None,
) -> None:
    case_dir.mkdir(parents=True, exist_ok=True)
    metadata = {
        "first_run_sha256": first_hash,
        "second_run_sha256": second_hash,
        "elapsed_seconds": round(elapsed, 4),
    }
    if validation_passed is not None:
        metadata["validation_passed"] = validation_passed
    (case_dir / "benchmark-metadata.json").write_text(
        json.dumps(metadata, indent=2) + "\n",
        encoding="utf-8",
    )


def validator_passed(result: dict[str, Any]) -> bool:
    if result.get("return_code") != 0:
        return False
    try:
        payload = json.loads(result.get("stdout") or "")
    except (TypeError, json.JSONDecodeError):
        return result.get("return_code") == 0
    if isinstance(payload, list):
        return not any(
            isinstance(item, dict) and item.get("status") == "FAIL"
            for item in payload
        )
    if isinstance(payload, dict) and "success" in payload:
        return payload.get("success") is True
    return result.get("return_code") == 0


def clone_target(target: dict[str, Any], destination: Path) -> bool:
    destination.parent.mkdir(parents=True, exist_ok=True)
    clone = run(f"{target['id']}: clone", ["git", "clone", "--no-checkout", target["url"], destination])
    if clone["return_code"] != 0:
        return False
    fetched = run(
        f"{target['id']}: fetch pinned commit",
        ["git", "fetch", "--depth", "1", "origin", target["commit"]],
        cwd=destination,
    )
    if fetched["return_code"] != 0:
        return False
    checked = run(
        f"{target['id']}: checkout pinned commit",
        ["git", "checkout", "--detach", target["commit"]],
        cwd=destination,
    )
    if checked["return_code"] != 0:
        return False
    actual = run(f"{target['id']}: resolve commit", ["git", "rev-parse", "HEAD"], cwd=destination)
    target["resolved_commit"] = actual["stdout"].strip()
    return target["resolved_commit"] == target["commit"]


def run_containerizer(target: dict[str, Any], repo: Path, app_dir: Path, out: Path) -> dict[str, Any]:
    skill = ROOT / ".agents/skills/app-containerizer/scripts"
    scan = out / "container-scan.json"
    plan = out / "container-plan.json"
    scan_result = run(
        f"{target['id']}: container scan",
        [PY, skill / "scan_repository.py", "--path", app_dir, "--output", scan],
    )
    if scan_result["return_code"] != 0:
        return {"status": "FAIL", "scan": scan_result}
    analyze = run(
        f"{target['id']}: container analyze",
        [PY, skill / "analyze_application.py", "--input", scan, "--output", plan],
    )
    if analyze["return_code"] != 0:
        return {"status": "FAIL", "scan": scan_result, "analyze": analyze}
    generated_paths = [app_dir / "Dockerfile", app_dir / ".dockerignore"]
    started = time.perf_counter()
    first = run(
        f"{target['id']}: container generate run 1",
        [PY, skill / "generate_dockerfile.py", "--path", app_dir, "--plan", plan, "--approve", "--overwrite"],
    )
    first_hash = digest(generated_paths) if first["return_code"] == 0 else None
    second = run(
        f"{target['id']}: container generate run 2",
        [PY, skill / "generate_dockerfile.py", "--path", app_dir, "--plan", plan, "--approve", "--overwrite"],
    ) if first["return_code"] == 0 else {"return_code": 1, "status": "SKIPPED", "elapsed_seconds": 0}
    second_hash = digest(generated_paths) if second["return_code"] == 0 else None
    elapsed = time.perf_counter() - started
    case_dir = out.parents[1] / "benchmark-workspace" / f"{target['id']}-container"
    copy_case_files(case_dir, [(generated_paths[0], "Dockerfile"), (generated_paths[1], ".dockerignore")])
    write_case_metadata(case_dir, first_hash, second_hash, elapsed)
    validation = run(
        f"{target['id']}: container static validation",
        [PY, skill / "validate_container.py", "--path", app_dir],
    )
    validation_ok = validator_passed(validation)
    write_case_metadata(case_dir, first_hash, second_hash, elapsed, validation_ok)
    return {
        "status": "PASS" if first["return_code"] == 0 and second["return_code"] == 0 and validation_ok else "FAIL",
        "scan": scan_result,
        "analysis": analyze,
        "generation_run_1": first,
        "generation_run_2": second,
        "validation": validation,
        "validation_passed": validation_ok,
        "first_hash": first_hash,
        "second_hash": second_hash,
        "elapsed_seconds": round(elapsed, 4),
        "plan": json.loads(plan.read_text(encoding="utf-8")) if plan.exists() else None,
    }


def run_infra(target: dict[str, Any], repo: Path, out: Path) -> dict[str, Any]:
    skill = ROOT / ".agents/skills/infra-creator/scripts"
    scan = out / "infra-scan.json"
    arch = out / "architecture.json"
    first_dir = out / "infra-run-1"
    second_dir = out / "infra-run-2"
    scan_result = run(
        f"{target['id']}: infra scan",
        [PY, skill / "scan_repository.py", repo, "--json", "-o", scan],
    )
    if scan_result["return_code"] != 0:
        return {"status": "FAIL", "scan": scan_result}
    analyze = run(
        f"{target['id']}: architecture analysis",
        [PY, skill / "analyze_architecture.py", scan, "--json", "-o", arch],
    )
    if analyze["return_code"] != 0:
        return {"status": "FAIL", "scan": scan_result, "analysis": analyze}
    started = time.perf_counter()
    first = run(
        f"{target['id']}: Terraform generation run 1",
        [PY, skill / "generate_terraform.py", "--scan", scan, "--arch", arch, "--provider", "aws",
         "--output", first_dir, "--project-name", target["id"], "--approve"],
    )
    first_files = [p for p in first_dir.rglob("*") if p.is_file()] if first_dir.exists() else []
    first_hash = digest(first_files) if first["return_code"] == 0 else None
    second = run(
        f"{target['id']}: Terraform generation run 2",
        [PY, skill / "generate_terraform.py", "--scan", scan, "--arch", arch, "--provider", "aws",
         "--output", second_dir, "--project-name", target["id"], "--approve"],
    ) if first["return_code"] == 0 else {"return_code": 1, "status": "SKIPPED", "elapsed_seconds": 0}
    second_files = [p for p in second_dir.rglob("*") if p.is_file()] if second_dir.exists() else []
    second_hash = digest(second_files) if second["return_code"] == 0 else None
    elapsed = time.perf_counter() - started
    case_dir = out.parents[1] / "benchmark-workspace" / f"{target['id']}-infra"
    if first_dir.exists():
        shutil.copytree(first_dir, case_dir / "infra", dirs_exist_ok=True)
    write_case_metadata(case_dir, first_hash, second_hash, elapsed)
    validation = run(
        f"{target['id']}: Terraform static validation",
        [PY, skill / "validate_terraform.py", first_dir, "--json"],
    ) if first["return_code"] == 0 else {"status": "SKIPPED", "return_code": None, "stdout": ""}
    validation_ok = validator_passed(validation)
    write_case_metadata(case_dir, first_hash, second_hash, elapsed, validation_ok)
    architecture = json.loads(arch.read_text(encoding="utf-8")) if arch.exists() else None
    plan = json.loads(first["stdout"]) if first["return_code"] == 0 and first["stdout"].lstrip().startswith("{") else None
    return {
        "status": "PASS" if first["return_code"] == 0 and second["return_code"] == 0 and validation_ok else "FAIL",
        "scan": scan_result,
        "analysis": analyze,
        "generation_run_1": first,
        "generation_run_2": second,
        "validation": validation,
        "validation_passed": validation_ok,
        "architecture": architecture,
        "plan": plan,
        "first_hash": first_hash,
        "second_hash": second_hash,
        "elapsed_seconds": round(elapsed, 4),
    }


def run_pipeline(target: dict[str, Any], repo: Path, out: Path) -> dict[str, Any]:
    skill = ROOT / ".agents/skills/cicd-pipeline-creator/scripts/render_pipeline.py"
    first_dir = out / "pipeline-run-1"
    second_dir = out / "pipeline-run-2"
    command = [PY, skill, repo, "github", "--out", first_dir]
    if target.get("pipeline_project_dir"):
        command += ["--project-dir", target["pipeline_project_dir"]]
    started = time.perf_counter()
    first = run(f"{target['id']}: pipeline generation run 1", command)
    if first["return_code"] != 0:
        expected = target.get("pipeline_expected_block") and "Unsupported pipeline stack" in (first["stderr"] + first["stdout"])
        return {
            "status": "EXPECTED_BLOCKED" if expected else "FAIL",
            "expected_block": bool(expected),
            "generation_run_1": first,
            "reason": (first["stderr"] + first["stdout"])[-2000:],
        }
    command2 = [PY, skill, repo, "github", "--out", second_dir]
    if target.get("pipeline_project_dir"):
        command2 += ["--project-dir", target["pipeline_project_dir"]]
    second = run(f"{target['id']}: pipeline generation run 2", command2)
    elapsed = time.perf_counter() - started
    generated = [first_dir / "pipeline.yml", first_dir / "PIPELINE_NOTES.md"]
    second_generated = [second_dir / "pipeline.yml", second_dir / "PIPELINE_NOTES.md"]
    first_hash = digest(generated)
    second_hash = digest(second_generated) if second["return_code"] == 0 else None
    case_dir = out.parents[1] / "benchmark-workspace" / f"{target['id']}-pipeline"
    copy_case_files(case_dir, [
        (first_dir / "pipeline.yml", ".github/workflows/pipeline.yml"),
        (first_dir / "PIPELINE_NOTES.md", "PIPELINE_NOTES.md"),
    ])
    write_case_metadata(case_dir, first_hash, second_hash, elapsed)
    validation = run(
        f"{target['id']}: pipeline static validation",
        [PY, ROOT / ".agents/skills/cicd-pipeline-creator/scripts/validate_pipeline.py",
         first_dir / "pipeline.yml", "--json"],
    )
    validation_ok = validator_passed(validation)
    write_case_metadata(case_dir, first_hash, second_hash, elapsed, validation_ok)
    return {
        "status": "PASS" if second["return_code"] == 0 and validation_ok else "FAIL",
        "generation_run_1": first,
        "generation_run_2": second,
        "validation": validation,
        "first_hash": first_hash,
        "second_hash": second_hash,
        "elapsed_seconds": round(elapsed, 4),
    }


def run_orchestrator(repo: Path, out: Path) -> dict[str, Any]:
    script = ROOT / ".agents/skills/cloud-engineering-orchestrator/scripts/orchestrate.py"
    run_dir = out / "orchestrator-run"
    plan = run(
        "spring-sample-web-app: orchestrator plan",
        [PY, script, "plan", "--project", repo,
         "--goal", "Containerize this Spring Boot application and prepare AWS Terraform infrastructure",
         "--skills", "app-containerizer,infra-creator",
         "--provider", "aws", "--run-dir", run_dir],
    )
    if plan["return_code"] != 0:
        return {"status": "FAIL", "plan": plan}
    execute = run(
        "spring-sample-web-app: orchestrator execute",
        [PY, script, "execute", "--run-dir", run_dir, "--approve", "--overwrite"],
        timeout=600,
    )
    return {"status": "PASS" if execute["return_code"] == 0 else "FAIL", "plan": plan, "execute": execute}


def make_dataset(path: Path) -> None:
    cases = []
    def add(case_id: str, category: str, stack: str, artifacts: list[str], signals: list[str]) -> None:
        cases.append({
            "id": case_id,
            "category": category,
            "stack": stack,
            "expected_artifacts": artifacts,
            "expected_signals": signals,
        })
    add("spring-petclinic-container", "container", "java-spring-maven",
        ["Dockerfile", ".dockerignore"], ["FROM", "WORKDIR", "USER", "EXPOSE", "ENTRYPOINT"])
    add("spring-petclinic-infra", "infra", "java-spring-maven-aws",
        ["infra/main.tf", "infra/variables.tf", "infra/providers.tf", "infra/versions.tf", "infra/terraform.tfvars.example"],
        ["module", "container_image", "provider", "terraform"])
    add("fastapi-full-stack-container", "container", "python-fastapi",
        ["Dockerfile", ".dockerignore"], ["FROM", "WORKDIR", "USER", "EXPOSE", "CMD", "python:3.14-slim"])
    add("fastapi-full-stack-pipeline", "cicd", "python-uv",
        [".github/workflows/pipeline.yml", "PIPELINE_NOTES.md"],
        ["name:", "jobs:", "permissions:", "timeout-minutes:"])
    add("fastapi-full-stack-infra", "infra", "python-fastapi-aws",
        ["infra/main.tf", "infra/variables.tf", "infra/providers.tf", "infra/versions.tf", "infra/terraform.tfvars.example"],
        ["module", "container_image", "provider", "terraform"])
    add("spring-sample-web-app-container", "container", "java-spring-maven",
        ["Dockerfile", ".dockerignore"], ["FROM", "WORKDIR", "USER", "EXPOSE", "ENTRYPOINT"])
    add("spring-sample-web-app-infra", "infra", "java-spring-maven-aws",
        ["infra/main.tf", "infra/variables.tf", "infra/providers.tf", "infra/versions.tf", "infra/terraform.tfvars.example"],
        ["module", "container_image", "provider", "terraform"])
    data = {
        "schema_version": "1.0",
        "description": "Pinned real-world public repository baseline for Cloud Agent Skills; static artifact evaluation only.",
        "scoring": {
            "weights": {"correctness": 30, "completeness": 25, "security": 25, "reproducibility": 10, "efficiency": 10},
            "security_rules": {
                "forbidden_patterns": [
                    "privileged:\\s*true",
                    "AKIA[0-9A-Z]{16}",
                    "-----BEGIN (RSA |EC |OPENSSH )?PRIVATE KEY-----",
                    "(?im)^\\s*(?:password|secret|token)\\s*[:=]\\s*['\\\"][^'\\\"]{8,}['\\\"]",
                    "terraform\\s+(apply|destroy)",
                ],
                "warning_patterns": [":latest\\b", "curl\\s+[^|]+\\|\\s*(sudo\\s+)?(sh|bash)"],
            },
        },
        "cases": cases,
    }
    path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=Path("artifacts/real-world-baseline"))
    args = parser.parse_args()
    out = args.output_dir.resolve()
    if out.exists():
        shutil.rmtree(out)
    out.mkdir(parents=True)
    clones = out / "sources"
    benchmark_workspace = out / "benchmark-workspace"
    benchmark_workspace.mkdir()
    summary: dict[str, Any] = {
        "schema_version": "1.0",
        "method": "Pinned source checkout; run repository scanners, generators and static validators only.",
        "safety": {
            "target_application_code_executed": False,
            "docker_builds": False,
            "terraform_init_in_isolated_copy": True,
            "terraform_plan": False,
            "terraform_apply_or_destroy": False,
            "cloud_resources_created": False,
            "third_party_repositories_modified": False,
        },
        "targets": [],
        "orchestrator": None,
    }
    for target in TARGETS:
        target_out = out / "runs" / target["id"]
        target_out.mkdir(parents=True, exist_ok=True)
        repo = clones / target["id"]
        ok = clone_target(target, repo)
        target_result: dict[str, Any] = {
            "id": target["id"],
            "url": target["url"],
            "pinned_commit": target["commit"],
            "resolved_commit": target.get("resolved_commit"),
            "clone_status": "PASS" if ok else "FAIL",
        }
        if ok:
            app_dir = repo if target["app_subdir"] == "." else repo / target["app_subdir"]
            target_result["containerizer"] = run_containerizer(target, repo, app_dir, target_out)
            target_result["infra_creator"] = run_infra(target, repo, target_out)
            target_result["cicd_pipeline_creator"] = run_pipeline(target, repo, target_out)
            if target["id"] == "spring-sample-web-app":
                summary["orchestrator"] = run_orchestrator(repo, target_out)
        summary["targets"].append(target_result)

    dataset = out / "real-world-dataset.json"
    make_dataset(dataset)
    report = out / "real-world-benchmark-report.json"
    benchmark = run(
        "rule-based benchmark scoring",
        [PY, ROOT / "benchmarks/scripts/benchmark.py", "--dataset", dataset,
         "--workspace", benchmark_workspace, "--output", report],
    )
    summary["benchmark_command"] = benchmark
    summary["benchmark_report"] = str(report)
    summary["commands"] = COMMANDS
    (out / "real-world-run-summary.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    (out / "README.md").write_text(
        "# Cloud Agent Skills — Real-World Baseline\n\n"
        "This baseline runs the skills against three pinned public repositories. "
        "It records generated artifacts, static validation, deterministic output hashes, and measured generation time.\n\n"
        "## Safety boundary\n\n"
        "- No application code, project test scripts, Dockerfile instructions, or package lifecycle scripts were executed.\n"
        "- Terraform fmt/init/validate ran only in isolated temporary copies with backend disabled; no Terraform plan/apply/destroy was performed.\n"

        "- All generated files were written only into ephemeral GitHub Actions workspaces. Public source repositories were not modified.\n\n"
        "## Interpretation\n\n"
        "The benchmark is a deterministic, rule-based artifact baseline. It is not a runtime, vulnerability, performance, or production-readiness certification. "
        "A missing optional validator is reported as NOT_RUN by its validator output, not treated as a pass. "
        "Java CI/CD generation is expected to fail closed because the current renderer supports Python and Node.js only.\n",
        encoding="utf-8",
    )
    report_data = json.loads(report.read_text(encoding="utf-8")) if report.exists() else {}
    compact_targets = []
    for item in summary["targets"]:
        compact_targets.append({
            "id": item["id"],
            "clone_status": item["clone_status"],
            "containerizer": item.get("containerizer", {}).get("status"),
            "infra_creator": item.get("infra_creator", {}).get("status"),
            "cicd_pipeline_creator": item.get("cicd_pipeline_creator", {}).get("status"),
            "pipeline_reason": item.get("cicd_pipeline_creator", {}).get("reason"),
        })
    failures = [
        {"label": item["label"], "return_code": item["return_code"], "stdout": item["stdout"][-1200:], "stderr": item["stderr"][-1200:]}
        for item in COMMANDS if item["status"] not in {"PASS", "SKIPPED"}
    ]
    print(json.dumps({
        "output_dir": str(out),
        "benchmark_report": str(report),
        "summary": str(out / "real-world-run-summary.json"),
        "benchmark_exit_code": benchmark["return_code"],
        "average_weighted_score": report_data.get("average_weighted_score"),
        "passed_cases": report_data.get("passed"),
        "failed_cases": report_data.get("failed"),
        "case_results": [
            {"case_id": item["case_id"], "status": item["status"], "dimensions": item["dimensions"],
             "validation_passed": item.get("validation_passed"),
             "missing_artifacts": item["missing_artifacts"], "matched_signals": item["matched_signals"]}
            for item in report_data.get("results", [])
        ],
        "target_results": compact_targets,
        "command_failures": failures,
    }, indent=2))
    # A benchmark may legitimately contain failing skill cases. Preserve the
    # report as evidence; fail the workflow only if the report itself is absent.
    return 0 if report.exists() else 1


if __name__ == "__main__":
    raise SystemExit(main())
