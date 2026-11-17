#!/usr/bin/env python3
"""Terraform validator — fmt, init -backend=false, validate. Never apply."""

from __future__ import annotations

import argparse
import json
import logging
import shutil
import subprocess
import sys
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger("validate_terraform")


@dataclass
class ValidationResult:
    success: bool
    terraform_available: bool
    fmt_ok: bool | None = None
    init_ok: bool | None = None
    validate_ok: bool | None = None
    messages: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def run_cmd(cmd: list[str], cwd: Path, timeout: int = 120) -> tuple[int, str, str]:
    try:
        proc = subprocess.run(cmd, cwd=str(cwd), capture_output=True, text=True, timeout=timeout, check=False)
        return proc.returncode, proc.stdout, proc.stderr
    except FileNotFoundError:
        return 127, "", f"Command not found: {cmd[0]}"
    except subprocess.TimeoutExpired:
        return 124, "", f"Timed out: {' '.join(cmd)}"


def validate(project_dir: Path) -> ValidationResult:
    result = ValidationResult(success=False, terraform_available=False)
    project_dir = project_dir.resolve()
    if not project_dir.is_dir():
        result.errors.append(f"Project directory does not exist: {project_dir}")
        return result

    tf = shutil.which("terraform")
    if not tf:
        result.errors.append("Terraform CLI not found on PATH.")
        result.messages.append("Skipping validation — install Terraform >= 1.5.")
        return result

    result.terraform_available = True

    code, _, err = run_cmd([tf, "fmt", "-recursive", "-check"], cwd=project_dir)
    if code == 0:
        result.fmt_ok = True
        result.messages.append("terraform fmt: OK")
    else:
        code2, _, err2 = run_cmd([tf, "fmt", "-recursive"], cwd=project_dir)
        result.fmt_ok = code2 == 0
        result.messages.append("terraform fmt: reformatted" if code2 == 0 else f"fmt failed: {err or err2}")

    code, out, err = run_cmd([tf, "init", "-backend=false", "-input=false", "-no-color"], cwd=project_dir)
    result.init_ok = code == 0
    result.messages.append("terraform init -backend=false: OK" if code == 0 else f"init failed:\n{err or out}")
    if not result.init_ok:
        result.errors.append(err or out)

    if result.init_ok:
        code, out, err = run_cmd([tf, "validate", "-no-color"], cwd=project_dir)
        result.validate_ok = code == 0
        result.messages.append("terraform validate: OK" if code == 0 else f"validate failed:\n{err or out}")
        if not result.validate_ok:
            result.errors.append(err or out)
    else:
        result.validate_ok = False

    result.success = bool(result.fmt_ok and result.init_ok and result.validate_ok)
    if result.success:
        result.messages.append("Validation succeeded. This does NOT mean infrastructure was deployed.")
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate a generated Terraform project")
    parser.add_argument("path")
    parser.add_argument("--json", action="store_true")
    parser.add_argument("-o", "--output")
    args = parser.parse_args()
    result = validate(Path(args.path))
    text = json.dumps(result.to_dict(), indent=2)
    if args.output:
        Path(args.output).write_text(text, encoding="utf-8")
    if args.json or args.output:
        print(text)
    else:
        for m in result.messages:
            logger.info("%s", m)
        for e in result.errors:
            logger.error("%s", e)
    return 0 if result.success or not result.terraform_available else 1


if __name__ == "__main__":
    sys.exit(main())