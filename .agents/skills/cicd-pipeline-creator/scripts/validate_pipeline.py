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


def platform_name(path: str, text: str = "") -> str:
    normalized = path.replace("\\", "/").lower()
    name = Path(normalized).name
    if name == "jenkinsfile":
        return "jenkins"
    if ".gitlab-ci" in normalized:
        return "gitlab"
    if ".circleci/" in normalized or ("version: 2.1" in text.lower() and "workflows:" in text.lower()):
        return "circleci"
    if "azure" in normalized:
        return "azure"
    return "github"


def load_allowlist(platform: str):
    default_allowlist = {
        "github": {
            "actions", "docker", "ghcr.io", "github", "gitleaks", "aquasecurity",
            "azure", "microsoft", "octo-org", "codecov", "sonarsource", "docker.io"
        },
        "azure": {"azure", "microsoft", "docker", "ghcr.io", "gitleaks", "aquasecurity"},
        "gitlab": {"ghcr.io", "aquasec", "zricethezav", "python", "node", "alpine", "docker"},
        "circleci": {"cimg", "ghcr.io", "aquasec", "zricethezav", "python", "node", "docker"},
    }
    ref = PLATFORM_DIR / f"{platform}.md"
    if not ref.exists():
        return default_allowlist.get(platform, set())
    text = ref.read_text(encoding="utf-8", errors="ignore")
    return set(re.findall(r"^\s*[-*]\s*([A-Za-z0-9_.@:/-]+)", text, re.M)) | default_allowlist.get(platform, set())


def run_native_validators(path: Path, platform: str):
    ran = []
    skipped = []
    checks = []
    if platform == "github" and shutil.which("actionlint"):
        checks.append(("actionlint", ["actionlint", str(path)]))
    elif platform == "github":
        skipped.append("SKIPPED: actionlint not installed")
    elif platform == "circleci" and shutil.which("circleci"):
        checks.append(("circleci config validate", ["circleci", "config", "validate", str(path)]))
    elif platform == "circleci":
        skipped.append("SKIPPED: CircleCI CLI not installed")
    elif platform == "jenkins" and shutil.which("groovyc"):
        import tempfile
        temp_dir = tempfile.mkdtemp(prefix="jenkinsfile-validate-")
        checks.append(("Groovy syntax compile", ["groovyc", "-d", temp_dir, str(path)]))
    elif platform == "jenkins":
        skipped.append("SKIPPED: groovyc not installed; structural checks ran")
    elif platform == "gitlab":
        skipped.append("SKIPPED: GitLab CI Lint requires the target GitLab instance; static YAML checks ran")
    else:
        skipped.append("SKIPPED: platform-specific native validator unavailable")

    if platform != "jenkins" and shutil.which("yamllint"):
        checks.append((
            "yamllint",
            ["yamllint", "-d", "{extends: relaxed, rules: {document-start: disable}}", str(path)],
        ))
    elif platform != "jenkins":
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
    platform = platform_name(path, text)

    if platform == "jenkins":
        required_jenkins = [
            "pipeline {",
            "stages {",
            "stage('build')",
            "stage('scan and test')",
            "stage('deploy gate')",
            "stage('deploy staging')",
            "stage('approve production')",
            "stage('deploy production')",
        ]
        missing_jenkins = [item for item in required_jenkins if item not in lower]
        if missing_jenkins:
            errors.append("Jenkins declarative pipeline is missing required structure: " + ", ".join(missing_jenkins))
        if "@@" in text:
            errors.append("Unresolved template marker remains in Jenkinsfile")
        if "timeout(" not in lower or "disableconcurrentbuilds" not in lower:
            errors.append("Jenkinsfile must set a pipeline timeout and disable concurrent builds")
        if "echo todo:" in lower or 'echo "todo' in lower:
            errors.append("Jenkinsfile contains an unimplemented placeholder command")
    else:
        if yaml is not None:
            try:
                parsed = yaml.safe_load(text)
                if not isinstance(parsed, dict):
                    errors.append("Pipeline YAML root must be a mapping")
            except Exception:
                errors.append("YAML parse error")
        else:
            warnings.append("YAML parse skipped: PyYAML unavailable")

    required = ["build", "scan", "test", "deploy"]
    missing = [item for item in required if item not in lower]
    if missing:
        errors.append(f"Stages missing: {', '.join(missing)}")

    if re.search(r"\|\|\s*true|\|\|\s*exit\s+0|continue-on-error\s*:\s*true|allow_failure\s*:\s*true", lower):
        if not (platform == "gitlab" and "allow_failure:\n    exit_codes: 64" in text):
            errors.append("Forbidden failure suppression pattern found")

    action_refs = re.findall(r"^\s*(?:-\s*)?uses\s*:\s*['\"]?([^\s'\"]+)['\"]?(?:\s+#.*)?\s*$", text, re.M | re.I)
    for action_ref in action_refs:
        if action_ref.startswith(("./", "docker://")):
            continue
        _, separator, revision = action_ref.rpartition("@")
        if not separator or not re.fullmatch(r"[0-9a-f]{40}", revision):
            errors.append(
                f"GitHub Action must be pinned to a full 40-character commit SHA: {action_ref}"
            )

    if platform == "github" and any(token in lower for token in ("gitleaks", "trivy", "secret scan")):
        if not ("fetchdepth: 0" in lower or "fetch-depth: 0" in lower or 'fetchdepth: "0"' in lower or "fetchDepth: 0" in lower):
            errors.append("Secret scan missing full-history checkout")

    if re.search(r"AKIA[0-9A-Z]{16}|ghp_[A-Za-z0-9]{30,}|-----BEGIN (RSA|OPENSSH|DSA|EC|PGP) PRIVATE KEY-----|(?:password|secret|token|api[_-]?key)\s*[:=]\s*['\"][^'\"]+['\"]", text, re.I):
        errors.append("Hardcoded secret or private key found")

    if "timeout" not in lower and "timeoutinminutes" not in lower and "timeout-minutes" not in lower:
        errors.append("Missing timeout on jobs")

    if "cache" not in lower and "actions/cache" not in lower and "cache@2" not in lower:
        errors.append("Missing dependency cache configuration")

    production_environment = re.search(
        r"environment\s*:\s*(?:['"]?production['"]?|[\s\S]{0,160}?\bname\s*:\s*['"]?production['"]?)",
        text,
        re.I,
    )
    if platform not in {"jenkins", "circleci"} and "deploy" in lower and "production" in lower and not production_environment:
        errors.append("Production deploy missing environment approval gate")

    refs = re.findall(r"(?:uses|task|orb|image)\s*:\s*['\"]?([^\s'\"]+)", text, re.I)
    for ref in refs:
        if ref.startswith("$"):
            continue
        if ref in {"self", "checkout"}:
            continue
        if "/" in ref and ref.split("/", 1)[0] not in {"actions", "azure", "microsoft", "docker", "gitleaks", "aquase", "aquasecurity", "github"}:
            allow = load_allowlist(platform)
            if ref.split("/", 1)[0] not in allow:
                errors.append(f"Unapproved third-party owner: {ref}")
        if re.search(r"@main\b|@master\b|@latest\b", ref, re.I):
            errors.append(f"Unpinned ref used: {ref}")
        if "/" in ref and "@" not in ref and platform in {"github", "azure"}:
            errors.append(f"Unpinned ref missing version: {ref}")

    if re.search(r"""echo\s+['"](?:deploying\b|todo:\s*deploy\b)""", lower):
        errors.append("Deploy job echoes instead of performing a real deploy")

    if re.search(r"@@[A-Z_]+@@", text):
        errors.append("Unresolved template markers remain in generated pipeline")

    publishes_artifact = (
        "upload-artifact" in lower
        or "publishpipelineartifact@1" in lower
        or re.search(r"^\s*publish\s*:", text, re.M | re.I) is not None
        or "persist_to_workspace" in lower
        or "store_artifacts" in lower
        or "archiveartifacts" in lower
    )
    consumes_artifact = (
        "download-artifact" in lower
        or "downloadpipelineartifact@2" in lower
        or re.search(r"^\s*download\s*:\s*current\b", text, re.M | re.I) is not None
        or "attach_workspace" in lower
        or "unstash" in lower
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

    pipeline_text = read_text(str(path))
    errors, warnings = validate(str(path))
    platform = platform_name(str(path), pipeline_text)
    ran, skipped = run_native_validators(path, platform)
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
