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
