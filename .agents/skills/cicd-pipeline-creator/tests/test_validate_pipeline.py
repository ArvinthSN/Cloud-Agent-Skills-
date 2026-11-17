import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
VALIDATOR = ROOT / "scripts" / "validate_pipeline.py"

BASE = """name: check
on: [push]
jobs:
  build:
    runs-on: ubuntu-latest
    timeout-minutes: 10
    steps:
      - uses: actions/checkout@v4
        with:
          fetch-depth: 0
      - uses: actions/cache@v4
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
    runs-on: ubuntu-latest
    timeout-minutes: 10
    environment: production
    steps:
      - uses: actions/upload-artifact@v4
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
    pipeline.write_text(BASE + "\n      - uses: actions/download-artifact@v4\n", encoding="utf-8")
    result = run(pipeline)
    assert result.returncode == 0, result.stdout + result.stderr
    assert '"status": "pass"' in result.stdout


def test_blocking_error_uses_exit_code_one(tmp_path):
    pipeline = tmp_path / "pipeline.yml"
    pipeline.write_text("jobs:\n  test:\n    steps: []\n", encoding="utf-8")
    result = run(pipeline)
    assert result.returncode == 1
    assert '"status": "fail"' in result.stdout
