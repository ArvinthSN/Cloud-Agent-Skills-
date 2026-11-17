#!/usr/bin/env python3
"""Golden and mutation tests for the pipeline skill."""
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RENDER = ROOT / "scripts" / "render_pipeline.py"
VALIDATE = ROOT / "scripts" / "validate_pipeline.py"


def run(cmd):
    return subprocess.run(cmd, capture_output=True, text=True)


def assert_ok(code, msg):
    if code != 0:
        raise AssertionError(msg)


OUTPUT_PATHS = {
    "azure": "azure-pipeline.yml",
    "github": "pipeline.yml",
    "gitlab": ".gitlab-ci.yml",
    "jenkins": "Jenkinsfile",
    "circleci": ".circleci/config.yml",
}


def golden_checks():
    examples = [
        ROOT / "examples" / "node-service",
        ROOT / "examples" / "python-service",
        ROOT / "examples" / "monorepo" / "backend",
        ROOT / "examples" / "monorepo" / "frontend",
        ROOT / "examples" / "no-tests",
    ]
    for example in examples:
        for platform in ("azure", "github", "gitlab", "jenkins", "circleci"):
            with tempfile.TemporaryDirectory() as td:
                out = Path(td)
                res = run([sys.executable, str(RENDER), str(example), platform, "--out", str(out)])
                assert_ok(res.returncode, f"render failed for {example} {platform}: {res.stderr or res.stdout}")
                pipeline = out / OUTPUT_PATHS[platform]
                assert pipeline.exists(), f"missing pipeline {pipeline}"
                res2 = run([sys.executable, str(VALIDATE), str(pipeline)])
                assert_ok(res2.returncode, f"validate failed for {example} {platform}: {res2.stdout}\n{res2.stderr}")


def mutation_checks():
    repo = ROOT / "examples" / "python-service"
    bad_cases = [
        ("|| true in scan", "trivy fs . || true"),
        ("typo'd action name", "uses: aquase/trivy-action@main"),
        ("echo-only deploy", "echo \"deploying\""),
        ("un pinned ref", "uses: actions/checkout@main"),
        ("missing timeout", "timeout-minutes: 0"),
        ("secret scan no full history", "gitleaks detect --source ."),
        ("deploy on PRs", "if: github.event_name == 'pull_request'"),
        ("test guard removed", "ALLOW_NO_TESTS=false"),
        ("hardcoded token", "password: \"supersecret\""),
    ]
    for label, inject in bad_cases:
        with tempfile.TemporaryDirectory() as td:
            src = Path(td)
            shutil.copytree(repo, src / "repo")
            pipeline = src / "repo" / "azure-pipeline.yml"
            if not pipeline.exists():
                pipeline = src / "repo" / "pipeline.yml"
            if not pipeline.exists():
                pipeline.write_text("name: test\n")
            data = pipeline.read_text(encoding="utf-8")
            if label == "deploy on PRs":
                data = data.replace(
                    "github.event_name != 'pull_request' && github.ref == 'refs/heads/main'",
                    "github.event_name == 'pull_request'",
                )
            else:
                data = data + "\n" + inject + "\n"
            pipeline.write_text(data, encoding="utf-8")
            res = run([sys.executable, str(VALIDATE), str(pipeline)])
            if res.returncode == 0:
                raise AssertionError(f"mutation check failed: {label}")


def detect_checks():
    monorepo = ROOT / "examples" / "monorepo"
    data = json.loads(run([sys.executable, str(ROOT / "scripts" / "detect_stack.py"), str(monorepo)]).stdout)
    assert len(data["projects"]) == 2, data
    dirs = sorted(p["dir"] for p in data["projects"])
    assert dirs == ["backend", "frontend"], dirs
    no_tests = ROOT / "examples" / "no-tests"
    data2 = json.loads(run([sys.executable, str(ROOT / "scripts" / "detect_stack.py"), str(no_tests)]).stdout)
    assert "test" not in data2["projects"][0], data2
    azure_repo = ROOT / "examples" / "node-service"
    res = json.loads(run([sys.executable, str(ROOT / "scripts" / "detect_stack.py"), str(azure_repo)]).stdout)
    assert res["ci_platforms"] == ["azure-devops"] or not res["ci_platforms"], res


def main():
    golden_checks()
    mutation_checks()
    detect_checks()
    print("all checks passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
