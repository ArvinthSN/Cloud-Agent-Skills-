#!/usr/bin/env python3
"""Fail a benchmark comparison on security or material quality regressions."""
from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path
from typing import Any


def _score(value: Any, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise ValueError(f"{label} must be a finite number")
    if not 0 <= value <= 100:
        raise ValueError(f"{label} must be between 0 and 100")
    return float(value)


def _load(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"{path} contains invalid JSON: {exc}") from exc
    if not isinstance(value, dict) or not isinstance(value.get("results"), list):
        raise ValueError(f"{path} is not a benchmark report with a results array")
    cases: dict[str, dict[str, Any]] = {}
    for index, item in enumerate(value["results"]):
        if not isinstance(item, dict):
            raise ValueError(f"{path} result at index {index} must be an object")
        case_id = item.get("case_id")
        if not isinstance(case_id, str) or not case_id or case_id in cases:
            raise ValueError(f"{path} contains a missing or duplicate case_id")
        dimensions = item.get("dimensions")
        if not isinstance(dimensions, dict):
            raise ValueError(f"{path} case {case_id} has no dimensions object")
        _score(dimensions.get("correctness"), f"{path} case {case_id} correctness")
        if item.get("status") not in {"PASS", "FAIL"}:
            raise ValueError(f"{path} case {case_id} status must be PASS or FAIL")
        findings = item.get("security_findings")
        if not isinstance(findings, list) or any(
            not isinstance(finding, dict) or finding.get("severity") not in {"FAIL", "WARNING"}
            for finding in findings
        ):
            raise ValueError(f"{path} case {case_id} security_findings must be a list of valid findings")
        cases[case_id] = item
    if not cases:
        raise ValueError(f"{path} contains no benchmark cases")
    aggregate = _score(value.get("average_weighted_score"), f"{path} average_weighted_score")
    return {"raw": value, "cases": cases, "aggregate_score": aggregate}


def compare_reports(
    baseline_path: Path,
    current_path: Path,
    *,
    max_score_drop: float = 3.0,
    max_correctness_drop: float = 0.0,
) -> dict[str, Any]:
    if (
        isinstance(max_score_drop, bool) or not isinstance(max_score_drop, (int, float))
        or not math.isfinite(max_score_drop) or max_score_drop < 0
        or isinstance(max_correctness_drop, bool) or not isinstance(max_correctness_drop, (int, float))
        or not math.isfinite(max_correctness_drop) or max_correctness_drop < 0
    ):
        raise ValueError("Regression thresholds must be finite, non-negative numbers")

    baseline, current = _load(baseline_path), _load(current_path)
    base_cases, current_cases = baseline["cases"], current["cases"]
    if set(base_cases) != set(current_cases):
        raise ValueError("Baseline and current reports must contain exactly the same case IDs")

    failures, comparisons = [], []
    for case_id in sorted(base_cases):
        old, new = base_cases[case_id], current_cases[case_id]
        old_correct = _score(old["dimensions"]["correctness"], f"baseline {case_id} correctness")
        new_correct = _score(new["dimensions"]["correctness"], f"current {case_id} correctness")
        correctness_drop = round(old_correct - new_correct, 2)
        if correctness_drop > max_correctness_drop:
            failures.append({
                "case_id": case_id, "gate": "correctness",
                "drop": correctness_drop, "threshold": max_correctness_drop,
            })
        old_status, new_status = old["status"], new["status"]
        if old_status == "PASS" and new_status != "PASS":
            failures.append({
                "case_id": case_id, "gate": "case_status",
                "baseline": old_status, "current": new_status,
            })
        security = [finding for finding in new["security_findings"] if finding["severity"] == "FAIL"]
        if security:
            failures.append({"case_id": case_id, "gate": "security", "finding_count": len(security)})
        comparisons.append({
            "case_id": case_id,
            "correctness_drop": correctness_drop,
            "baseline_score": old.get("weighted_score"),
            "current_score": new.get("weighted_score"),
        })

    score_drop = round(baseline["aggregate_score"] - current["aggregate_score"], 2)
    if score_drop > max_score_drop:
        failures.append({
            "gate": "aggregate_score", "drop": score_drop, "threshold": max_score_drop,
        })

    return {
        "schema_version": "1.0",
        "status": "FAIL" if failures else "PASS",
        "baseline": str(baseline_path),
        "current": str(current_path),
        "thresholds": {
            "max_score_drop": max_score_drop,
            "max_correctness_drop": max_correctness_drop,
        },
        "aggregate_score_drop": score_drop,
        "case_count": len(comparisons),
        "failures": failures,
        "comparisons": comparisons,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--baseline", type=Path, required=True)
    parser.add_argument("--current", type=Path, required=True)
    parser.add_argument("--max-score-drop", type=float, default=3.0)
    parser.add_argument("--max-correctness-drop", type=float, default=0.0)
    parser.add_argument("--output", type=Path, default=Path("regression-report.json"))
    args = parser.parse_args()
    try:
        report = compare_reports(
            args.baseline,
            args.current,
            max_score_drop=args.max_score_drop,
            max_correctness_drop=args.max_correctness_drop,
        )
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    except (OSError, ValueError) as exc:
        print(f"Regression gate error: {exc}", file=sys.stderr)
        return 2
    print(f"Regression gate: {report['status']}; failures={len(report['failures'])}; report={args.output}")
    return 0 if report["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
