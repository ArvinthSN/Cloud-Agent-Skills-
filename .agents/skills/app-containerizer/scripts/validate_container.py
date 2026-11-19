#!/usr/bin/env python3
"""Static checks and optional Docker image build."""
import argparse,json,shutil,subprocess
from pathlib import Path
def validate(repo,build=False):
    out=[]
    def add(name,status,detail): out.append({"check":name,"status":status,"detail":detail})
    df=repo/"Dockerfile"; di=repo/".dockerignore"
    add("Dockerfile exists","PASS" if df.is_file() else "FAIL",str(df))
    add(".dockerignore exists","PASS" if di.is_file() else "WARNING",str(di))
    if df.exists():
        t=df.read_text(errors="ignore")
        add("exec-form startup","PASS" if ("CMD [" in t or "ENTRYPOINT [" in t) else "WARNING","Check CMD/ENTRYPOINT form.")
        add("non-root user","PASS" if "USER " in t else "WARNING","USER instruction check.")
        risky=any(x in t for x in ("COPY .env","COPY id_rsa","ENV PASSWORD=","ARG AWS_SECRET_ACCESS_KEY"))
        add("obvious secret patterns","FAIL" if risky else "PASS","Potential secret pattern found." if risky else "No obvious secret pattern found.")
        add("pinned base tag","WARNING" if ":latest" in t else "PASS","Avoid latest tags.")
    if build:
        docker=shutil.which("docker")
        if not docker: add("Docker build","NOT_RUN","Docker CLI not found; image was not built.")
        elif not df.exists(): add("Docker build","SKIPPED","Dockerfile missing.")
        else:
            p=subprocess.run([docker,"build","-t","app-containerizer:local",str(repo)],capture_output=True,text=True)
            add("Docker build","PASS" if p.returncode==0 else "FAIL",(p.stdout+"\\n"+p.stderr)[-3000:])
    else: add("Docker build","SKIPPED","Not requested; static checks only.")
    return out
def main():
    ap=argparse.ArgumentParser(); ap.add_argument("--path",required=True); ap.add_argument("--build",action="store_true")
    a=ap.parse_args(); repo=Path(a.path).resolve()
    if not repo.is_dir(): ap.error("path must be an existing directory")
    results=validate(repo,a.build); print(json.dumps(results,indent=2))
    raise SystemExit(1 if any(x["status"]=="FAIL" for x in results) else 0)
if __name__=="__main__": main()
