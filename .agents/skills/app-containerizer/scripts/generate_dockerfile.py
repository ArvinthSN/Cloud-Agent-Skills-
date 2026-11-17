#!/usr/bin/env python3
"""Generate Dockerfile and .dockerignore only after approval."""
import argparse,json
from pathlib import Path
def render(p):
    stack=p.get("stack"); version=p.get("runtime_version") or {"python":"3.12","nodejs":"22","java":"21"}.get(stack)
    if stack=="python":
        dep=Path(p.get("dependency_file") or "requirements.txt").name
        cmd=p.get("startup_command") or []
        if not cmd: raise ValueError("Startup command unknown; edit plan JSON before generation.")
        return f"""FROM python:{version}-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app
RUN groupadd --system app && useradd --system --gid app --create-home app
COPY {dep} ./
RUN pip install --no-cache-dir --upgrade pip && pip install --no-cache-dir -r {dep}
COPY --chown=app:app . .
USER app
EXPOSE {p.get('port') or 8000}
CMD {json.dumps(cmd)}
"""
    if stack=="nodejs":
        return f"""FROM node:{version}-bookworm-slim AS build
WORKDIR /app
COPY package*.json ./
RUN npm ci
COPY . .
RUN npm run build --if-present
FROM node:{version}-bookworm-slim AS runtime
ENV NODE_ENV=production
WORKDIR /app
RUN groupadd --system app && useradd --system --gid app --create-home app
COPY --from=build --chown=app:app /app ./
USER app
EXPOSE {p.get('port') or 3000}
CMD ["npm","start"]
"""
    if stack=="java":
        return f"""FROM maven:3.9-eclipse-temurin-{version} AS build
WORKDIR /workspace
COPY pom.xml ./
RUN mvn -B -q dependency:go-offline
COPY src ./src
RUN mvn -B -DskipTests package
FROM eclipse-temurin:{version}-jre
WORKDIR /app
RUN groupadd --system app && useradd --system --gid app --create-home app
COPY --from=build /workspace/target/*.jar /app/app.jar
USER app
EXPOSE {p.get('port') or 8080}
ENTRYPOINT ["java","-jar","/app/app.jar"]
"""
    raise ValueError("Unsupported or unknown stack: "+str(stack))
def main():
    ap=argparse.ArgumentParser(); ap.add_argument("--path",required=True); ap.add_argument("--plan",required=True); ap.add_argument("--approve",action="store_true"); ap.add_argument("--overwrite",action="store_true")
    a=ap.parse_args(); repo=Path(a.path).resolve(); plan=json.loads(Path(a.plan).read_text())
    if not a.approve: ap.error("No files written; re-run with --approve after reviewing the plan.")
    targets=[repo/"Dockerfile",repo/".dockerignore"]; existing=[x.name for x in targets if x.exists()]
    if existing and not a.overwrite: ap.error(f"Existing files preserved: {existing}; use --overwrite only after review.")
    dockerfile=render(plan)
    ignore=""" .git
.venv
venv
__pycache__
.pytest_cache
.mypy_cache
.ruff_cache
node_modules
coverage
dist
build
target
.idea
.vscode
*.log
.env
.env.*
!.env.example
!.env.sample
*.pem
*.key
id_rsa
""".lstrip()
    (repo/"Dockerfile").write_text(dockerfile); (repo/".dockerignore").write_text(ignore)
    print(json.dumps({"generated":[str(x) for x in targets]},indent=2))
if __name__=="__main__": main()
