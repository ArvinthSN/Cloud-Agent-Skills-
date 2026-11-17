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
    repo = ROOT / "examples" / "node-service"

    def replace_once(text, old, new, label):
        if old not in text:
            raise AssertionError(f"Could not apply mutation '{label}': expected fragment not found")
        return text.replace(old, new, 1)

    for label in (
        "|| true in scan",
        "typo'd action name",
        "echo-only deploy",
        "un pinned ref",
        "missing timeout",
        "secret scan no full history",
        "deploy on PRs",
        "test guard removed",
        "hardcoded token",
    ):
        with tempfile.TemporaryDirectory() as td:
            out = Path(td) / "out"
            rendered = run([sys.executable, str(RENDER), str(repo), "github", "--out", str(out)])
            assert_ok(rendered.returncode, f"baseline render failed: {rendered.stderr or rendered.stdout}")
            pipeline = out / "pipeline.yml"
            if not pipeline.is_file():
                raise AssertionError("baseline GitHub pipeline was not generated")
            data = pipeline.read_text(encoding="utf-8")

            if label == "|| true in scan":
                data += "\n# injected policy violation: trivy fs . || true\n"
            elif label == "typo'd action name":
                data = replace_once(
                    data,
                    "uses: aquasecurity/trivy-action@",
                    "uses: unapproved-owner/trivy-action@",
                    label,
                )
            elif label == "echo-only deploy":
                data = replace_once(
                    data,
                    'echo "::notice::Build, scan and test completed. Deployment is disabled; configure a target-specific job before enabling releases."',
                    'echo "deploying"',
                    label,
                )
            elif label == "un pinned ref":
                data = replace_once(
                    data,
                    "actions/checkout@df4cb1c069e1874edd31b4311f1884172cec0e10",
                    "actions/checkout@main",
                    label,
                )
            elif label == "missing timeout":
                data = replace_once(data, "timeout-minutes: 20", "timeout-minutes: 0", label)
            elif label == "secret scan no full history":
                data = replace_once(data, "fetch-depth: 0", "fetch-depth: 1", label)
            elif label == "deploy on PRs":
                data = replace_once(
                    data,
                    "github.event_name != 'pull_request' && github.ref == 'refs/heads/main'",
                    "github.event_name == 'pull_request'",
                    label,
                )
            elif label == "test guard removed":
                data = replace_once(
                    data,
                    'if [ "$ALLOW_NO_TESTS" = "true" ]; then exit 0; fi',
                    "if true; then exit 0; fi",
                    label,
                )
            elif label == "hardcoded token":
                data += '\n# injected secret: password: "supersecret"\n'

            pipeline.write_text(data, encoding="utf-8")
            res = run([sys.executable, str(VALIDATE), str(pipeline), "--json"])
            if res.returncode == 0:
                raise AssertionError(f"mutation check unexpectedly passed: {label}\n{res.stdout}\n{res.stderr}")



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
