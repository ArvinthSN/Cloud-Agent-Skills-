#!/usr/bin/env python3
"""Read-only heuristic scanner for Python, Node.js and Java repositories."""
import argparse, json, re
from pathlib import Path

SKIP={".git",".venv","venv","node_modules","__pycache__",".pytest_cache","dist","build","target",".idea"}
def scan(repo):
    paths=[]
    for p in repo.rglob("*"):
        if p.is_file() and not any(part in SKIP for part in p.relative_to(repo).parts):
            paths.append(p.relative_to(repo).as_posix())
    low=[x.lower() for x in paths]
    readme=""
    for name in ("README.md","readme.md"):
        f=repo/name
        if f.exists():
            readme=f.read_text(errors="ignore")[:50000].lower()
            break
    manifest_text=[]
    for rel in paths:
        if Path(rel).name in ("requirements.txt","pyproject.toml","package.json","pom.xml","build.gradle","build.gradle.kts"):
            try: manifest_text.append((repo/rel).read_text(errors="ignore")[:50000].lower())
            except OSError: pass
    text=" ".join(low)+" "+readme+" "+" ".join(manifest_text)
    stack=framework=manager=dependency=entry=runtime="unknown"
    if any(x.endswith((".py","requirements.txt","pyproject.toml","setup.py")) for x in low):
        stack="python"
        framework=next((x for x in ("fastapi","django","flask") if x in text),"unknown")
        dependency=next((x for x in paths if Path(x).name in ("requirements.txt","pyproject.toml","poetry.lock")),"unknown")
        manager="poetry" if "poetry.lock" in low or "[tool.poetry]" in text else "pip"
        entry=next((x for x in paths if Path(x).name in ("main.py","app.py","manage.py")),"unknown")
        runtime="3.12"
    elif "package.json" in low:
        stack="nodejs"
        framework=next((x for x in ("nestjs","express","vite") if x in text),"unknown")
        if framework=="vite" and "react" in text: framework="react-vite"
        dependency="package.json"
        manager="pnpm" if "pnpm-lock.yaml" in low else "yarn" if "yarn.lock" in low else "npm" if "package-lock.json" in low else "unknown"
        entry=next((x for x in paths if Path(x).name in ("server.js","index.js","main.js","server.ts","main.ts")),"unknown")
        runtime="22"
    elif any(x in low for x in ("pom.xml","build.gradle","build.gradle.kts")):
        stack="java"; framework="spring-boot" if "spring-boot" in text else "java"
        dependency=next(x for x in paths if Path(x).name in ("pom.xml","build.gradle","build.gradle.kts"))
        manager="maven" if "pom.xml" in low else "gradle"; runtime="21"
    services=[]
    for name,pattern in (("postgresql",r"postgres|postgresql"),("mysql",r"\\bmysql\\b"),("redis",r"\\bredis\\b")):
        if re.search(pattern,text): services.append(name)
    return {"repository":str(repo.resolve()),"project_type":stack,"framework":framework,"package_manager":manager,
      "dependency_file":dependency,"entry_point":entry,"runtime_version":runtime,
      "existing_dockerfile":any(Path(x).name.lower()=="dockerfile" for x in paths),
      "existing_compose":any(Path(x).name.lower() in ("compose.yaml","compose.yml","docker-compose.yml","docker-compose.yaml") for x in paths),
      "env_files_detected":[x for x in paths if Path(x).name.startswith(".env")],
      "detected_services":services,"compose_required":bool(services),"file_count":len(paths),
      "confidence":"high" if framework!="unknown" else "low","files_sample":paths[:250]}
def main():
    ap=argparse.ArgumentParser(); ap.add_argument("--path",required=True); ap.add_argument("--output")
    a=ap.parse_args(); repo=Path(a.path)
    if not repo.is_dir(): ap.error("path must be an existing directory")
    result=json.dumps(scan(repo),indent=2)
    if a.output: Path(a.output).write_text(result+"\\n")
    print(result)
if __name__=="__main__": main()
