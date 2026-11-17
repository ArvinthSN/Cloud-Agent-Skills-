import subprocess, sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
def test_validator_detects_missing_dockerfile(tmp_path):
    p=subprocess.run([sys.executable,str(ROOT/'scripts/validate_container.py'),'--path',str(tmp_path)],capture_output=True,text=True)
    assert p.returncode==1 and 'FAIL' in p.stdout
