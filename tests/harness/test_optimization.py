import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / ".agents"))
sys.path.insert(0, str(ROOT / "benchmarks" / "scripts"))

from optimization.repair import build_repair_plan
from optimization.telemetry import build_optimization_report, write_optimization_report
from regression_gate import compare_reports


def test_telemetry_uses_metadata_only_and_reports_cache(tmp_path):
    handoff_dir = tmp_path / "handoffs" / "app-containerizer"
    handoff_dir.mkdir(parents=True)
    (handoff_dir / "handoff.json").write_text(json.dumps({"goal": "containerize"}))
    report = {"started_at": "2026-01-01T00:00:00+00:00", "finished_at": "2026-01-01T00:00:02+00:00",
              "artifacts": [{"path": "Dockerfile"}], "checks": [], "skill_reports": {"app-containerizer": {}}}
    payload = build_optimization_report(
        {"execution_order": ["app-containerizer"], "workflow": {"context_cache": {"enabled": True, "status": "hit", "key": "abc"}}},
        report, tmp_path, {"app-containerizer": 1.25})
    assert payload["duration_seconds"] == 2
    assert payload["context_cache"]["status"] == "hit"
    assert payload["metadata_size"]["estimated_input_tokens"] > 0
    assert payload["skill_durations_seconds"]["app-containerizer"] == 1.25
    target = tmp_path / "telemetry.json"
    write_optimization_report(target, payload)
    assert json.loads(target.read_text())["counts"]["artifacts"] == 1


def test_repair_plan_retries_only_allowlisted_transient_failures():
    report = {"checks": [
        {"name": "network-install", "status": "FAIL", "detail": "Temporary failure: connection reset"},
        {"name": "terraform-security-policy", "status": "FAIL", "detail": "Security policy violation"},
        {"name": "dockerfile-validation", "status": "FAIL", "detail": "Invalid Dockerfile syntax"},
    ]}
    plan = build_repair_plan(report, max_attempts=1)
    assert plan["status"] == "partial_escalation"
    assert len(plan["proposals"]) == 1
    assert len(plan["escalations"]) == 2
    assert plan["policy"]["automatic_file_mutation"] is False


def test_repair_budget_exhaustion_escalates():
    report = {"checks": [{"name": "network", "status": "FAIL", "detail": "HTTP 503 service unavailable"}]}
    plan = build_repair_plan(report, max_attempts=1, attempts_used=1)
    assert plan["status"] == "escalate"
    assert plan["policy"]["attempts_remaining"] == 0


def _report(score, correctness, status="PASS", findings=None):
    return {"average_weighted_score": score, "results": [{
        "case_id": "python-fastapi", "status": status,
        "weighted_score": score, "dimensions": {"correctness": correctness},
        "security_findings": findings or [],
    }]}


def test_regression_gate_passes_unchanged_baseline(tmp_path):
    baseline, current = tmp_path / "base.json", tmp_path / "current.json"
    baseline.write_text(json.dumps(_report(95, 100)))
    current.write_text(json.dumps(_report(94, 100)))
    result = compare_reports(baseline, current)
    assert result["status"] == "PASS"


def test_regression_gate_fails_security_and_correctness_regressions(tmp_path):
    baseline, current = tmp_path / "base.json", tmp_path / "current.json"
    baseline.write_text(json.dumps(_report(95, 100)))
    current.write_text(json.dumps(_report(88, 80, findings=[{"severity": "FAIL", "rule": "secret"}])))
    result = compare_reports(baseline, current)
    assert result["status"] == "FAIL"
    assert {item["gate"] for item in result["failures"]} >= {"security", "correctness", "aggregate_score"}


def test_regression_gate_rejects_changed_case_sets(tmp_path):
    baseline, current = tmp_path / "base.json", tmp_path / "current.json"
    baseline.write_text(json.dumps(_report(95, 100)))
    changed = _report(95, 100)
    changed["results"][0]["case_id"] = "different-case"
    current.write_text(json.dumps(changed))
    import pytest
    with pytest.raises(ValueError, match="same case IDs"):
        compare_reports(baseline, current)
