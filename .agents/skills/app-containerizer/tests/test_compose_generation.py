import json, subprocess, sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
def test_compose_explicit_service(tmp_path):
    f=tmp_path/'plan.json'; f.write_text(json.dumps({'stack':'python','port':8000}))
    p=subprocess.run([sys.executable,str(ROOT/'scripts/generate_compose.py'),'--path',str(tmp_path),'--plan',str(f),'--services','postgresql','--approve'],capture_output=True,text=True)
    assert p.returncode==0 and 'postgres:16' in (tmp_path/'compose.yaml').read_text()
