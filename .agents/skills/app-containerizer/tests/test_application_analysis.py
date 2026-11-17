import json, subprocess, sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
def test_fastapi_plan(tmp_path):
    f=tmp_path/'scan.json'
    f.write_text(json.dumps({'project_type':'python','framework':'fastapi','entry_point':'main.py','detected_services':[],'confidence':'high'}))
    p=subprocess.run([sys.executable,str(ROOT/'scripts/analyze_application.py'),'--input',str(f)],capture_output=True,text=True)
    assert p.returncode==0 and json.loads(p.stdout)['port']==8000
