import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
VALIDATOR = ROOT / "scripts" / "validate_pipeline.py"

BASE = """name: check
on: [push]
permissions:
  contents: read
jobs:
  build:
    runs-on: ubuntu-latest
    timeout-minutes: 10
    steps:
      - uses: actions/checkout@df4cb1c069e1874edd31b4311f1884172cec0e10
        with:
          fetch-depth: 0
      - uses: actions/cache@8ff5423e8b66eacab4e638ee52abbd2cb831366a
        with:
          path: ~/.cache
          key: sample
  scan:
    runs-on: ubuntu-latest
    timeout-minutes: 10
    steps:
      - run: gitleaks detect
  test:
    runs-on: ubuntu-latest
    timeout-minutes: 10
    steps:
      - run: pytest
  deploy:
    if: github.event_name != 'pull_request' && github.ref == 'refs/heads/main'
    runs-on: ubuntu-latest
    timeout-minutes: 10
    environment: production
    steps:
      - uses: actions/upload-artifact@615b319bd27bb32c3d64dca6b6ed6974d5fbe653
"""


def run(path):
    return subprocess.run(
        [sys.executable, str(VALIDATOR), str(path), "--json"],
        capture_output=True,
        text=True,
    )


def test_warning_only_result_uses_exit_code_two(tmp_path):
    pipeline = tmp_path / "pipeline.yml"
    pipeline.write_text(BASE, encoding="utf-8")
    result = run(pipeline)
    assert result.returncode == 2, result.stdout + result.stderr
    assert '"status": "warning"' in result.stdout
    assert "Artifact is published but not consumed" in result.stdout


def test_consumed_artifact_removes_warning(tmp_path):
    pipeline = tmp_path / "pipeline.yml"
    pipeline.write_text(BASE + "\n      - uses: actions/download-artifact@0d2ec9d4cbcefe257d822f108de2a1f15f8da9f6\n", encoding="utf-8")
    result = run(pipeline)
    assert result.returncode == 0, result.stdout + result.stderr
    assert '"status": "pass"' in result.stdout


def test_blocking_error_uses_exit_code_one(tmp_path):
    pipeline = tmp_path / "pipeline.yml"
    pipeline.write_text("jobs:\n  test:\n    steps: []\n", encoding="utf-8")
    result = run(pipeline)
    assert result.returncode == 1
    assert '"status": "fail"' in result.stdout


def test_mutable_github_action_reference_is_rejected(tmp_path):
    pipeline = tmp_path / "pipeline.yml"
    unsafe = BASE.replace(
        "actions/checkout@df4cb1c069e1874edd31b4311f1884172cec0e10",
        "actions/checkout@v7",
    )
    pipeline.write_text(unsafe, encoding="utf-8")
    result = run(pipeline)
    assert result.returncode == 1
    assert "full 40-character commit SHA" in result.stdout


def test_full_commit_sha_action_reference_is_accepted(tmp_path):
    pipeline = tmp_path / "pipeline.yml"
    pipeline.write_text(BASE, encoding="utf-8")
    result = run(pipeline)
    assert result.returncode in {0, 2}, result.stdout + result.stderr
    assert '"status": "fail"' not in result.stdout


def test_deploy_job_must_exclude_pull_requests_and_target_main(tmp_path):
    pipeline = tmp_path / "pipeline.yml"
    unsafe = BASE.replace(
        "github.event_name != 'pull_request' && github.ref == 'refs/heads/main'",
        "github.event_name == 'pull_request'",
    )
    pipeline.write_text(unsafe, encoding="utf-8")
    result = run(pipeline)
    assert result.returncode == 1
    assert "must exclude pull requests" in result.stdout
