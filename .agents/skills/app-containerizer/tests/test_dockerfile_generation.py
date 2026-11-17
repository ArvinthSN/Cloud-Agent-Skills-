import json, subprocess, sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
def test_generate_fastapi_dockerfile(tmp_path):
    plan={'stack':'python','framework':'fastapi','dependency_file':'requirements.txt','startup_command':['uvicorn','main:app','--host','0.0.0.0','--port','8000'],'port':8000}
    f=tmp_path/'plan.json'; f.write_text(json.dumps(plan))
    p=subprocess.run([sys.executable,str(ROOT/'scripts/generate_dockerfile.py'),'--path',str(tmp_path),'--plan',str(f),'--approve'],capture_output=True,text=True)
    assert p.returncode==0
    assert 'USER app' in (tmp_path/'Dockerfile').read_text()
