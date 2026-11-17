import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "render_pipeline.py"
EXAMPLES = ROOT / "examples"


def run(*args):
    return subprocess.run(
        [sys.executable, str(SCRIPT), *map(str, args)],
        capture_output=True,
        text=True,
    )


def test_monorepo_requires_explicit_project_selection(tmp_path):
    result = run(EXAMPLES / "monorepo", "github", "--out", tmp_path)
    assert result.returncode != 0
    assert "--project-dir" in result.stderr + result.stdout
    assert not (tmp_path / "pipeline.yml").exists()


def test_existing_generated_pipeline_is_preserved_without_overwrite(tmp_path):
    example = EXAMPLES / "node-service"
    first = run(example, "github", "--out", tmp_path)
    assert first.returncode == 0, first.stderr + first.stdout
    target = tmp_path / "pipeline.yml"
    original = target.read_text(encoding="utf-8")
    second = run(example, "github", "--out", tmp_path)
    assert second.returncode != 0
    assert "Existing output preserved" in second.stderr + second.stdout
    assert target.read_text(encoding="utf-8") == original

def test_no_tests_pipeline_contains_explicit_fail_or_override_guard(tmp_path):
    example = EXAMPLES / "no-tests"
    result = run(example, "github", "--out", tmp_path)
    assert result.returncode == 0, result.stderr + result.stdout
    pipeline = (tmp_path / "pipeline.yml").read_text(encoding="utf-8")
    assert "NO_TESTS_DETECTED" in pipeline
    assert "ALLOW_NO_TESTS" in pipeline
    assert "No tests detected" in pipeline
