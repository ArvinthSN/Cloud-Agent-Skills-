#!/usr/bin/env python3
"""Terraform validator — fmt, init -backend=false, validate. Never apply."""

from __future__ import annotations

import argparse
import json
import logging
import re
import os
import shutil
import subprocess
import sys
import tempfile
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
    policy_ok: bool | None = None
    messages: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    policy_findings: list[str] = field(default_factory=list)

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


def static_security_policy(project_dir: Path) -> list[str]:
    """Run provider-aware security checks without requiring cloud credentials or Terraform."""
    terraform_files: list[Path] = []
    total_bytes = 0
    for current, dirs, names in os.walk(project_dir, followlinks=False):
        base = Path(current)
        dirs[:] = sorted(
            name for name in dirs
            if name not in {".git", ".terraform", ".cloud-agent"} and not (base / name).is_symlink()
        )
        for name in names:
            candidate = base / name
            if candidate.is_symlink():
                raise ValueError(f"Terraform validation does not follow symlinks: {candidate}")
            if candidate.suffix == ".tf":
                terraform_files.append(candidate)
                total_bytes += candidate.stat().st_size
                if len(terraform_files) > 500 or total_bytes > 20 * 1024 * 1024:
                    raise ValueError("Terraform policy scan exceeds its safety limit (500 files / 20 MiB).")

    combined = "\\n".join(
        path.read_text(encoding="utf-8", errors="replace")
        for path in sorted(terraform_files)
    )
    lower = combined.lower()
    findings: list[str] = []

    def require(condition: bool, message: str) -> None:
        if not condition:
            findings.append(message)

    require(
        not re.search(r'''(?i)image\\s*=\\s*["'][^"']+:latest["']''', combined),
        "Mutable :latest container image references are prohibited; use a SHA-256 digest.",
    )
    if 'resource "aws_ecr_repository"' in combined:
        require(
            'image_tag_mutability = "IMMUTABLE"' in combined,
            "ECR repositories must enforce immutable image tags.",
        )
    if 'resource "azurerm_container_registry"' in combined:
        require(
            re.search(r"(?im)^\\s*admin_enabled\\s*=\\s*false\\s*$", combined) is not None,
            "Azure Container Registry admin credentials must be disabled.",
        )
        require(
            'role_definition_name = "AcrPull"' in combined and 'identity_ids = [azurerm_user_assigned_identity.' in combined,
            "Azure container apps must use managed identity and AcrPull rather than registry admin credentials.",
        )
    if 'member   = "allUsers"' in combined or 'member = "allUsers"' in combined:
        require(
            re.search(r"(?im)^\\s*count\\s*=\\s*var\\.allow_unauthenticated\\s*\\?\\s*1\\s*:\\s*0\\s*$", combined) is not None
            and re.search(r'''(?is)variable\\s+"allow_unauthenticated"\\s*\\{[^}]*default\\s*=\\s*false''', combined) is not None,
            "Unauthenticated Cloud Run access must be opt-in and default to false.",
        )
    if 'resource "azurerm_postgresql_flexible_server"' in combined:
        require(
            re.search(r"(?im)^\\s*public_network_access_enabled\\s*=\\s*false\\s*$", combined) is not None
            and "delegated_subnet_id" in combined
            and "private_dns_zone_id" in combined,
            "Azure PostgreSQL must use delegated private networking, private DNS and public access disabled.",
        )
    if 'resource "aws_lb_listener" "http"' in combined:
        require(
            re.search(r'''(?is)resource\\s+"aws_lb_listener"\\s+"https"\\s*\\{[^}]*protocol\\s*=\\s*"HTTPS"[^}]*certificate_arn\\s*=\\s*var\\.certificate_arn''', combined) is not None,
            "Public AWS load balancers must configure an HTTPS listener with an explicit ACM certificate.",
        )
        require(
            re.search(r'''(?is)resource\\s+"aws_lb_listener"\\s+"http"\\s*\\{.*?protocol\\s*=\\s*"HTTPS".*?status_code\\s*=\\s*"HTTP_301"''', combined) is not None,
            "AWS HTTP listeners must redirect to HTTPS instead of forwarding plaintext traffic.",
        )
    if 'variable "container_image"' in combined:
        require(
            '@sha256:' in combined and '[0-9a-f]{64}' in combined,
            "container_image must be validated as an immutable OCI SHA-256 digest reference.",
        )

    return findings


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

    try:
        result.policy_findings = static_security_policy(project_dir)
        result.policy_ok = not result.policy_findings
        result.messages.append(
            "Static Terraform security policy: PASS"
            if result.policy_ok else "Static Terraform security policy: FAIL"
        )
        result.errors.extend(result.policy_findings)
    except (OSError, ValueError) as exc:
        result.policy_ok = False
        result.errors.append(f"Static Terraform security policy could not complete safely: {exc}")
        return result

    tf = shutil.which("terraform")
    if not tf:
        result.terraform_available = False
        result.messages.append("Terraform CLI unavailable; fmt/init/validate are NOT_RUN.")
        return result

    result.terraform_available = True

    # Run init/validate against an isolated copy so checks never create .terraform,
    # lock files, state, or other validation artifacts in the user's output folder.
    try:
        with tempfile.TemporaryDirectory(prefix="infra-creator-validate-") as temp_dir:
            validation_dir = Path(temp_dir) / "project"
            shutil.copytree(
                project_dir,
                validation_dir,
                symlinks=True,
                ignore=shutil.ignore_patterns(".git", ".terraform", "*.tfstate", "*.tfstate.*", "*.tfplan"),
            )

            code, out, err = run_cmd([tf, "fmt", "-recursive", "-check"], cwd=validation_dir)
            result.fmt_ok = code == 0
            result.messages.append("terraform fmt -check: OK" if code == 0 else f"terraform fmt -check failed: {err or out}")
            if not result.fmt_ok:
                result.errors.append(err or out or "terraform fmt check failed; run terraform fmt -recursive manually.")

            code, out, err = run_cmd([tf, "init", "-backend=false", "-input=false", "-no-color"], cwd=validation_dir)
            result.init_ok = code == 0
            result.messages.append("terraform init -backend=false: OK" if code == 0 else f"terraform init failed:\n{err or out}")
            if not result.init_ok:
                result.errors.append(err or out or "terraform init failed")

            if result.init_ok:
                code, out, err = run_cmd([tf, "validate", "-no-color"], cwd=validation_dir)
                result.validate_ok = code == 0
                result.messages.append("terraform validate: OK" if code == 0 else f"terraform validate failed:\n{err or out}")
                if not result.validate_ok:
                    result.errors.append(err or out or "terraform validate failed")
            else:
                result.validate_ok = False
    except OSError as exc:
        result.errors.append(f"Could not prepare isolated validation workspace: {exc}")
        result.messages.append("Validation NOT RUN because the project could not be copied safely.")

    result.success = bool(result.policy_ok and result.fmt_ok and result.init_ok and result.validate_ok)
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
    # A missing Terraform CLI is NOT_RUN and must not look like a successful validation.
    return 0 if result.success else 1


if __name__ == "__main__":
    sys.exit(main())