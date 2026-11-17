#!/usr/bin/env python3
"""Build a cautious containerization plan from scanner JSON."""
import argparse,json
from pathlib import Path
def analyze(d):
    stack=d.get("project_type","unknown"); framework=d.get("framework","unknown")
    port={"python":8000,"nodejs":3000,"java":8080}.get(stack)
    entry=d.get("entry_point","unknown")
    if stack=="python" and framework=="fastapi":
        module=Path(entry if entry!="unknown" else "main.py").with_suffix("").as_posix().replace("/",".")
        cmd=["uvicorn",f"{module}:app","--host","0.0.0.0","--port",str(port)]
    elif stack=="python" and framework=="flask": cmd=["gunicorn","<module>:app","--bind",f"0.0.0.0:{port}"]
    elif stack=="python" and framework=="django": cmd=["gunicorn","<project>.wsgi:application","--bind",f"0.0.0.0:{port}"]
    elif stack=="nodejs": cmd=["npm","start"]
    elif stack=="java": cmd=["java","-jar","/app/app.jar"]
    else: cmd=[]
    return {"stack":stack,"framework":framework,"dependency_file":d.get("dependency_file"),
      "entry_point":entry,"runtime_version":d.get("runtime_version"),"port":port,
      "startup_command":cmd,"detected_services":d.get("detected_services",[]),
      "compose_recommended":bool(d.get("detected_services")),
      "multi_stage_recommended":stack in ("nodejs","java"),
      "confidence":d.get("confidence"),"unknowns":[] if cmd else ["Startup command needs user confirmation"]}
def main():
    ap=argparse.ArgumentParser(); ap.add_argument("--input",required=True); ap.add_argument("--output")
    a=ap.parse_args(); plan=analyze(json.loads(Path(a.input).read_text())); out=json.dumps(plan,indent=2)
    if a.output: Path(a.output).write_text(out+"\\n")
    print(out)
if __name__=="__main__": main()
