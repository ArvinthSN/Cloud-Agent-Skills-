#!/usr/bin/env python3
"""Score generated cloud artifacts against a versioned benchmark dataset."""
from __future__ import annotations
import argparse, hashlib, json, re, sys, time
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_DATASET = ROOT / "benchmarks" / "dataset.json"
DIMENSIONS = ("correctness", "completeness", "security", "reproducibility", "efficiency")

def load_dataset(path: Path) -> dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if data.get("schema_version") != "1.0" or not isinstance(data.get("cases"), list):
        raise ValueError("Dataset must use schema_version 1.0 and contain cases")
    ids = [case.get("id") for case in data["cases"]]
    if not ids or any(not isinstance(item, str) or not item for item in ids) or len(ids) != len(set(ids)):
        raise ValueError("Benchmark case ids must be non-empty and unique")
    weights = data.get("scoring", {}).get("weights", {})
    if set(weights) != set(DIMENSIONS) or sum(weights.values()) != 100:
        raise ValueError("Scoring weights must define five dimensions and sum to 100")
    for case in data["cases"]:
        case_path = Path(case["id"])
        if case_path.is_absolute() or len(case_path.parts) != 1 or case["id"] in {".", ".."}:
            raise ValueError("Unsafe benchmark case id: " + str(case["id"]))
        if not case.get("expected_artifacts") or not isinstance(case.get("expected_signals"), list):
            raise ValueError(f"Case {case['id']} needs expected_artifacts and expected_signals")
        for relative in case["expected_artifacts"]:
            candidate = Path(relative)
            if candidate.is_absolute() or ".." in candidate.parts:
                raise ValueError(f"Unsafe artifact path in {case['id']}: {relative}")
    return data

def safe_read(root: Path, relative: str) -> str | None:
    target = (root / relative).resolve()
    try: target.relative_to(root.resolve())
    except ValueError: return None
    if not target.is_file() or target.is_symlink(): return None
    try: return target.read_text(encoding="utf-8")
    except (UnicodeDecodeError, OSError): return None

def score_case(case: dict[str, Any], workspace: Path, rules: dict[str, Any]) -> dict[str, Any]:
    repo = workspace / case["id"]
    contents, missing = {}, []
    for relative in case["expected_artifacts"]:
        content = safe_read(repo, relative) if repo.is_dir() else None
        if content is None: missing.append(relative)
        else: contents[relative] = content
    combined = "\n".join(contents.values())
    expected = case["expected_signals"]
    found = [signal for signal in expected if signal.casefold() in combined.casefold()]
    correctness = round(100 * len(found) / len(expected), 2) if expected else (100.0 if contents else 0.0)
    completeness = round(100 * (len(case["expected_artifacts"])-len(missing))/len(case["expected_artifacts"]), 2)
    findings = []
    for pattern in rules.get("forbidden_patterns", []):
        if re.search(pattern, combined, re.I | re.M): findings.append({"severity":"FAIL","rule":pattern})
    for pattern in rules.get("warning_patterns", []):
        if re.search(pattern, combined, re.I | re.M): findings.append({"severity":"WARNING","rule":pattern})
    security = 0.0 if any(f["severity"]=="FAIL" for f in findings) else (80.0 if findings else (100.0 if contents else 0.0))
    metadata_text = safe_read(repo, "benchmark-metadata.json") if repo.is_dir() else None
    metadata = json.loads(metadata_text) if metadata_text is not None else {}
    first, second = metadata.get("first_run_sha256"), metadata.get("second_run_sha256")
    reproducibility = (100.0 if first == second else 0.0) if isinstance(first,str) and isinstance(second,str) else None
    elapsed = metadata.get("elapsed_seconds")
    efficiency = round(max(0.0,min(100.0,(300.0-elapsed)/270.0*100.0)),2) if isinstance(elapsed,(int,float)) and not isinstance(elapsed,bool) and elapsed >= 0 else None
    dimensions={"correctness":correctness,"completeness":completeness,"security":security,"reproducibility":reproducibility,"efficiency":efficiency}
    weights=rules["_weights"]
    measured=sum(weights[k] for k,v in dimensions.items() if v is not None)
    score=sum(weights[k]*v for k,v in dimensions.items() if v is not None)/measured if measured else None
    return {"case_id":case["id"],"category":case["category"],"stack":case["stack"],
      "status":"PASS" if not missing and not any(f["severity"]=="FAIL" for f in findings) else "FAIL",
      "dimensions":dimensions,"weighted_score":round(score,2) if score is not None else None,
      "measured_weight_percent":measured,"missing_artifacts":missing,"matched_signals":found,
      "expected_signal_count":len(expected),"security_findings":findings}

def run_benchmark(dataset_path: Path, workspace: Path, output: Path) -> dict[str, Any]:
    data=load_dataset(dataset_path); rules=dict(data["scoring"].get("security_rules",{})); rules["_weights"]=data["scoring"]["weights"]
    started=time.perf_counter(); results=[score_case(c,workspace,rules) for c in data["cases"]]
    elapsed=round(time.perf_counter()-started,4)
    scored=[r["weighted_score"] for r in results if r["weighted_score"] is not None]
    report={"schema_version":"1.0","dataset":str(dataset_path),"workspace":str(workspace),"case_count":len(results),
      "passed":sum(r["status"]=="PASS" for r in results),"failed":sum(r["status"]=="FAIL" for r in results),
      "average_weighted_score":round(sum(scored)/len(scored),2) if scored else None,
      "dimensions_measured":{k:sum(r["dimensions"][k] is not None for r in results) for k in DIMENSIONS},
      "harness_elapsed_seconds":elapsed,"results":results,
      "limitations":["Reproducibility and efficiency remain unmeasured without benchmark-metadata.json measurements.",
      "Scenario specifications are not evidence of real-world performance; run against reviewed repositories and generated outputs."]}
    output.parent.mkdir(parents=True,exist_ok=True); output.write_text(json.dumps(report,indent=2)+"\n",encoding="utf-8")
    return report

def main() -> int:
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset",type=Path,default=DEFAULT_DATASET)
    parser.add_argument("--workspace",type=Path,required=False,help="Directory containing one output directory per case id")
    parser.add_argument("--output",type=Path,default=Path("benchmark-report.json"))
    parser.add_argument("--validate-only",action="store_true")
    args=parser.parse_args()
    try:
        data=load_dataset(args.dataset)
        if args.validate_only: print(f"Valid dataset: {len(data['cases'])} cases"); return 0
        if args.workspace is None: parser.error("--workspace is required unless --validate-only is used")
        report=run_benchmark(args.dataset,args.workspace,args.output)
    except (OSError,ValueError,json.JSONDecodeError) as exc:
        print(f"Benchmark error: {exc}",file=sys.stderr); return 2
    print(f"Benchmark: {report['passed']}/{report['case_count']} passed; average score={report['average_weighted_score']}; report={args.output}")
    return 0 if report["failed"]==0 else 1

if __name__=="__main__": raise SystemExit(main())
