#!/usr/bin/env python3
"""Run isolated Terraform fmt/init/validate/plan checks against a harmless fixture.

The fixture declares no providers, resources, backends, data sources or cloud
credentials. This verifies the Terraform CLI lifecycle without provisioning.
"""
from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Any


def execute(command: list[str], cwd: Path, timeout: int = 180) -> dict[str, Any]:
    try:
        result = subprocess.run(
            command, cwd=cwd, capture_output=True, text=True,
            timeout=timeout, check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return {"status": "NOT_RUN", "detail": str(exc)}
    return {
        "status": "PASS" if result.returncode == 0 else "FAIL",
        "exit_code": result.returncode,
        "detail": (result.stderr or result.stdout)[-3000:],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True, help="Directory in which to retain the fixture and report.")
    args = parser.parse_args()
    terraform = shutil.which("terraform")
    output = Path(args.output).resolve()
    output.mkdir(parents=True, exist_ok=True)
    fixture = output / "fixture"
    fixture.mkdir(exist_ok=True)
    (fixture / "main.tf").write_text(
        'terraform {\n  required_version = ">= 1.8.0, < 2.0.0"\n}\n\n'
        'variable "service_name" {\n  type = string\n  default = "readiness-smoke"\n}\n\n'
        'output "service_name" {\n  value = var.service_name\n}\n',
        encoding="utf-8",
    )
    report: dict[str, Any] = {
        "scope": "provider-free local Terraform smoke fixture; no cloud resources",
        "terraform_version": None,
        "checks": {},
    }
    if not terraform:
        report["status"] = "NOT_RUN"
        report["reason"] = "Terraform CLI is not installed"
        (output / "terraform-report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
        print(json.dumps(report, indent=2))
        return 2

    version = execute([terraform, "version", "-json"], fixture)
    report["terraform_version"] = version
    with tempfile.TemporaryDirectory(prefix="cloud-agent-terraform-") as temp:
        workspace = Path(temp) / "workspace"
        shutil.copytree(fixture, workspace)
        report["checks"]["fmt"] = execute([terraform, "fmt", "-check", "-recursive"], workspace)
        report["checks"]["init"] = execute([
            terraform, "init", "-backend=false", "-input=false", "-no-color",
        ], workspace, timeout=300)
        if report["checks"]["init"]["status"] == "PASS":
            report["checks"]["validate"] = execute([terraform, "validate", "-no-color"], workspace)
            report["checks"]["plan"] = execute([
                terraform, "plan", "-refresh=false", "-input=false", "-lock=false", "-no-color",
            ], workspace, timeout=300)
        else:
            report["checks"]["validate"] = {"status": "SKIPPED", "detail": "init did not pass"}
            report["checks"]["plan"] = {"status": "SKIPPED", "detail": "init did not pass"}

    statuses = [item["status"] for item in report["checks"].values()]
    report["status"] = "PASS" if statuses and all(status == "PASS" for status in statuses) else "FAIL"
    (output / "terraform-report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))
    return 0 if report["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
