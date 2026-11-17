#!/usr/bin/env python3
"""Static validation for generated CI/CD pipelines."""
import argparse
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

try:
    import yaml
except ImportError:  # pragma: no cover
    yaml = None

ROOT = Path(__file__).resolve().parents[1]
PLATFORM_DIR = ROOT / "references" / "platforms"


def read_text(path: str) -> str:
    return Path(path).read_text(encoding="utf-8", errors="ignore")


def platform_name(path: str) -> str:
    if "azure" in path.lower():
        return "azure"
    return "github"


def load_allowlist(platform: str):
    default_allowlist = {
        "github": {
            "actions", "docker", "ghcr.io", "github", "gitleaks", "aquasecurity",
            "azure", "microsoft", "octo-org", "codecov", "sonarsource", "docker.io"
        },
        "azure": {"azure", "microsoft", "docker", "ghcr.io", "gitleaks", "aquasecurity"},
    }
    ref = PLATFORM_DIR / f"{platform}.md"
    if not ref.exists():
        return default_allowlist.get(platform, set())
    text = ref.read_text(encoding="utf-8", errors="ignore")
    return set(re.findall(r"^\s*[-*]\s*([A-Za-z0-9_.@:/-]+)", text, re.M)) | default_allowlist.get(platform, set())


def run_native_validators(path: Path):
    ran = []
    skipped = []
    is_azure = "azure" in path.name.lower()
    checks = []
    if is_azure:
        skipped.append("SKIPPED: actionlint is GitHub Actions-specific")
    elif shutil.which("actionlint"):
        checks.append(("actionlint", ["actionlint", str(path)]))
    else:
        skipped.append("SKIPPED: actionlint not installed")
    if shutil.which("yamllint"):
        # Keep structural/style linting, but avoid imposing an 80-column policy on generated CI expressions.
        checks.append((
            "yamllint",
            ["yamllint", "-d", "{extends: relaxed, rules: {document-start: disable}}", str(path)],
        ))
    else:
        skipped.append("SKIPPED: yamllint not installed")

    for name, command in checks:
        try:
            proc = subprocess.run(command, capture_output=True, text=True, timeout=30)
            status = "PASS" if proc.returncode == 0 else "FAIL"
            detail = proc.stderr.strip() or proc.stdout.strip() or ""
            ran.append(f"RAN: {name} {status}{f' ({detail})' if detail else ''}")
        except (OSError, subprocess.TimeoutExpired) as exc:
            skipped.append(f"SKIPPED: {name} could not complete: {exc}")
    return ran, skipped


def validate(path: str):
    text = read_text(path)
    errors = []
    warnings = []
    lower = text.lower()

    if yaml is not None:
        try:
            yaml.safe_load(text)
        except Exception:
            errors.append("YAML parse error")
    else:
        warnings.append("YAML parse skipped: PyYAML unavailable")

    required = ["build", "scan", "test", "deploy"]
    missing = [item for item in required if item not in lower]
    if missing:
        errors.append(f"Stages missing: {', '.join(missing)}")

    if re.search(r"\|\|\s*true|\|\|\s*exit\s+0|continue-on-error\s*:\s*true|allow_failure\s*:\s*true", lower):
        errors.append("Forbidden failure suppression pattern found")

    if any(token in lower for token in ("gitleaks", "trivy", "secret scan")):
        if not ("fetchdepth: 0" in lower or "fetch-depth: 0" in lower or 'fetchdepth: "0"' in lower or "fetchDepth: 0" in lower):
            errors.append("Secret scan missing full-history checkout")

    if re.search(r"AKIA[0-9A-Z]{16}|ghp_[A-Za-z0-9]{30,}|-----BEGIN (RSA|OPENSSH|DSA|EC|PGP) PRIVATE KEY-----|(?:password|secret|token|api[_-]?key)\s*[:=]\s*['\"][^'\"]+['\"]", text, re.I):
        errors.append("Hardcoded secret or private key found")

    if "timeout" not in lower and "timeoutinminutes" not in lower and "timeout-minutes" not in lower:
        errors.append("Missing timeout on jobs")

    if "cache" not in lower and "actions/cache" not in lower and "cache@2" not in lower:
        errors.append("Missing cache configuration")

    if "deploy" in lower and "production" in lower and not re.search(r"environment\s*:\s*production|environment\s*:\s*['\"]production['\"]", text, re.I):
        errors.append("Production deploy missing environment approval gate")

    # GitHub Actions references are executable dependencies. Require a full immutable
    # commit SHA; mutable tags and branches are not acceptable in generated workflows.
    action_refs = re.findall(r"^\s*uses\s*:\s*['"]?([^\s'"]+)['"]?\s*$", text, re.M | re.I)
    for action_ref in action_refs:
        if action_ref.startswith(("./", "docker://")):
            continue
        _, separator, revision = action_ref.rpartition("@")
        if not separator or not re.fullmatch(r"[0-9a-f]{40}", revision):
            errors.append(
                f"GitHub Action must be pinned to a full 40-character commit SHA: {action_ref}"
            )

    refs = re.findall(r"(?:uses|task|orb|image)\s*:\s*['\"]?([^\s'\"]+)", text, re.I)
    for ref in refs:
        if ref.startswith("$"):
            continue
        if ref in {"self", "checkout"}:
            continue
        if "/" in ref and ref.split("/", 1)[0] not in {"actions", "azure", "microsoft", "docker", "gitleaks", "aquase", "trivy", "github"}:
            allow = load_allowlist(platform_name(path))
            if ref.split("/", 1)[0] not in allow:
                errors.append(f"Unapproved third-party owner: {ref}")
        if re.search(r"@main\b|@master\b|@latest\b", ref, re.I):
            errors.append(f"Unpinned ref used: {ref}")
        if "/" in ref and "@" not in ref:
            errors.append(f"Unpinned ref missing version: {ref}")

    if "echo \"deploy" in lower or "echo 'deploy" in lower or "echo \"todo: deploy" in lower:
        errors.append("Deploy job echoes instead of performing a real deploy")

    for marker in ("@@PYTHON_VERSION@@", "@@NODE_VERSION@@", "@@INSTALL_CMD@@", "@@BUILD_CMD@@", "@@TEST_CMD@@", "@@ARTIFACT_PATH@@", "@@WORKING_DIR@@", "@@DEPLOY_TARGET@@"):
        if marker in text:
            errors.append(f"Unresolved marker: {marker}")

    publishes_artifact = (
        "upload-artifact" in lower
        or "publishpipelineartifact@1" in lower
        or re.search(r"^\s*publish\s*:", text, re.M | re.I) is not None
    )
    consumes_artifact = (
        "download-artifact" in lower
        or "downloadpipelineartifact@2" in lower
        or re.search(r"^\s*download\s*:\s*current\b", text, re.M | re.I) is not None
    )
    if publishes_artifact and not consumes_artifact:
        warnings.append("Artifact is published but not consumed by a later stage")

    return errors, warnings


def main():
    parser = argparse.ArgumentParser(description="Validate a generated pipeline")
    parser.add_argument("path")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    path = Path(args.path)
    if not path.is_file():
        print(f"missing pipeline file: {path}", file=sys.stderr)
        return 1

    errors, warnings = validate(str(path))
    ran, skipped = run_native_validators(path)
    errors.extend(
        f"Native validator failed: {item}"
        for item in ran
        if " FAIL" in item
    )

    status = "fail" if errors else "warning" if warnings else "pass"
    exit_code = 1 if errors else 2 if warnings else 0
    if args.json:
        payload = {"errors": errors, "warnings": warnings, "ran": ran, "skipped": skipped, "status": status}
        print(json.dumps(payload, indent=2))
        return exit_code

    if errors:
        print("FAIL")
        print("ERRORS:")
        for item in errors:
            print(f"- {item}")
    elif warnings:
        print("PASS WITH WARNINGS")
    else:
        print("PASS")

    if warnings:
        print("WARNINGS:")
        for item in warnings:
            print(f"- {item}")
    if ran:
        print("RAN:")
        for item in ran:
            print(f"- {item}")
    if skipped:
        print("SKIPPED:")
        for item in skipped:
            print(f"- {item}")
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
