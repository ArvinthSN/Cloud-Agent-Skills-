import json, subprocess, sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
def test_detect_fastapi(tmp_path):
    (tmp_path/'main.py').write_text('from fastapi import FastAPI\\napp=FastAPI()')
    (tmp_path/'requirements.txt').write_text('fastapi==1\\nuvicorn==1')
    p=subprocess.run([sys.executable,str(ROOT/'scripts/scan_repository.py'),'--path',str(tmp_path)],capture_output=True,text=True)
    assert p.returncode==0
    d=json.loads(p.stdout)
    assert d['project_type']=='python' and d['framework']=='fastapi'
def test_invalid_path():
    p=subprocess.run([sys.executable,str(ROOT/'scripts/scan_repository.py'),'--path','/not/a/real/path'],capture_output=True,text=True)
    assert p.returncode!=0

def test_detect_mysql_and_redis_services(tmp_path):
    (tmp_path / "requirements.txt").write_text("mysql==1\\nredis==1")
    (tmp_path / "main.py").write_text("import redis\\n")
    p = subprocess.run(
        [sys.executable, str(ROOT / "scripts/scan_repository.py"), "--path", str(tmp_path)],
        capture_output=True, text=True,
    )
    assert p.returncode == 0, p.stderr
    detected = json.loads(p.stdout)["detected_services"]
    assert "mysql" in detected
    assert "redis" in detected


def test_output_file_returns_compact_receipt(tmp_path):
    (tmp_path / "main.py").write_text("from fastapi import FastAPI\\napp = FastAPI()")
    (tmp_path / "requirements.txt").write_text("fastapi==1")
    report_path = tmp_path / "scan.json"
    result = subprocess.run(
        [sys.executable, str(ROOT / "scripts/scan_repository.py"),
         "--path", str(tmp_path), "--output", str(report_path)],
        capture_output=True, text=True,
    )
    assert result.returncode == 0, result.stderr
    receipt = json.loads(result.stdout)
    full_report = json.loads(report_path.read_text(encoding="utf-8"))
    assert receipt["status"] == "completed"
    assert receipt["report"] == str(report_path)
    assert receipt["file_count"] == full_report["file_count"]
    assert "files_sample" not in receipt
