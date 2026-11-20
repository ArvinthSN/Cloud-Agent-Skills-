import json, sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/"benchmarks"/"scripts"))
from benchmark import load_dataset, run_benchmark, score_case

def test_dataset_has_twenty_unique_cases():
    data=load_dataset(ROOT/"benchmarks"/"dataset.json")
    assert len(data["cases"])==24
    assert len({c["id"] for c in data["cases"]})==24
    assert sum(data["scoring"]["weights"].values())==100

def test_missing_artifacts_and_security_findings_fail_case(tmp_path):
    case={"id":"sample","category":"container","stack":"python","expected_artifacts":["Dockerfile",".github/workflows/pipeline.yml"],"expected_signals":["FROM","WORKDIR","COPY"]}
    repo=tmp_path/"sample"; repo.mkdir()
    (repo/"Dockerfile").write_text("FROM python:latest\nWORKDIR /app\nCOPY . .\npassword=hardcoded-secret-value\n")
    rules={"forbidden_patterns":[r"password\s*[:=]\s*(?:['\"][^'\"]{6,}['\"]|[^\s'\"]{6,})"],"warning_patterns":[r":latest\b"],"_weights":{"correctness":30,"completeness":25,"security":25,"reproducibility":10,"efficiency":10}}
    result=score_case(case,tmp_path,rules)
    assert result["status"]=="FAIL" and result["dimensions"]["security"]==0
    assert result["missing_artifacts"]==[".github/workflows/pipeline.yml"]

def test_reproducibility_and_efficiency_require_metadata(tmp_path):
    case={"id":"sample","category":"container","stack":"python","expected_artifacts":["Dockerfile"],"expected_signals":["FROM"]}
    repo=tmp_path/"sample"; repo.mkdir(); (repo/"Dockerfile").write_text("FROM python:3.12-slim\n")
    rules={"forbidden_patterns":[],"warning_patterns":[],"_weights":{"correctness":30,"completeness":25,"security":25,"reproducibility":10,"efficiency":10}}
    assert score_case(case,tmp_path,rules)["dimensions"]["reproducibility"] is None
    (repo/"benchmark-metadata.json").write_text(json.dumps({"first_run_sha256":"a"*64,"second_run_sha256":"a"*64,"elapsed_seconds":30}))
    result=score_case(case,tmp_path,rules)
    assert result["dimensions"]["reproducibility"]==100 and result["dimensions"]["efficiency"]==100

def test_report_is_machine_readable_and_does_not_fake_passes(tmp_path):
    report=run_benchmark(ROOT/"benchmarks"/"dataset.json",tmp_path/"empty",tmp_path/"report.json")
    saved=json.loads((tmp_path/"report.json").read_text())
    assert saved["case_count"]==24 and report["failed"]==24
    assert saved["dimensions_measured"]["reproducibility"]==0
