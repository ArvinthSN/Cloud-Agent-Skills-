#!/usr/bin/env python3
"""Generate a conservative Compose file for explicitly selected local dependencies."""
import argparse,json
from pathlib import Path
def render(plan,services):
    port=plan.get("port") or 8000
    lines=["services:","  app:","    build: .",f'    ports: ["{port}:{port}"]',"    environment:",
      "      DATABASE_URL: ${DATABASE_URL:-}","      REDIS_URL: ${REDIS_URL:-}"]
    if services:
        lines += ["    depends_on:"]
        for s in services: lines += [f"      {s}:","        condition: service_healthy"]
    if "postgresql" in services:
        lines += ["  postgresql:","    image: postgres:16","    environment:",
          "      POSTGRES_DB: ${POSTGRES_DB:-app}","      POSTGRES_USER: ${POSTGRES_USER:-app}",
          "      POSTGRES_PASSWORD: ${POSTGRES_PASSWORD:?Set POSTGRES_PASSWORD}",
          "    volumes:","      - postgres_data:/var/lib/postgresql/data","    healthcheck:",
          '      test: ["CMD-SHELL", "pg_isready -U $${POSTGRES_USER} -d $${POSTGRES_DB}"]',
          "      interval: 10s","      timeout: 5s","      retries: 5"]
    if "mysql" in services:
        lines += ["  mysql:","    image: mysql:8.4","    environment:",
          "      MYSQL_DATABASE: ${MYSQL_DATABASE:-app}","      MYSQL_USER: ${MYSQL_USER:-app}",
          "      MYSQL_PASSWORD: ${MYSQL_PASSWORD:?Set MYSQL_PASSWORD}",
          "      MYSQL_ROOT_PASSWORD: ${MYSQL_ROOT_PASSWORD:?Set MYSQL_ROOT_PASSWORD}",
          "    volumes:","      - mysql_data:/var/lib/mysql","    healthcheck:",
          '      test: ["CMD", "mysqladmin", "ping", "-h", "localhost"]',
          "      interval: 10s","      timeout: 5s","      retries: 5"]
    if "redis" in services:
        lines += ["  redis:","    image: redis:7-alpine","    healthcheck:",
          '      test: ["CMD", "redis-cli", "ping"]',"      interval: 10s","      timeout: 5s","      retries: 5"]
    vols=[]
    if "postgresql" in services: vols.append("  postgres_data:")
    if "mysql" in services: vols.append("  mysql_data:")
    if vols: lines += ["volumes:"]+vols
    return "\\n".join(lines)+"\\n"
def main():
    ap=argparse.ArgumentParser(); ap.add_argument("--path",required=True); ap.add_argument("--plan",required=True); ap.add_argument("--services",default=""); ap.add_argument("--approve",action="store_true"); ap.add_argument("--overwrite",action="store_true")
    a=ap.parse_args(); repo=Path(a.path).resolve(); plan=json.loads(Path(a.plan).read_text())
    if not a.approve: ap.error("No files written; re-run with --approve.")
    target=repo/"compose.yaml"
    if target.exists() and not a.overwrite: ap.error("compose.yaml exists; use --overwrite after review.")
    services=[x.strip() for x in a.services.split(",") if x.strip()]
    if set(services)-{"postgresql","mysql","redis"}: ap.error("Allowed services: postgresql,mysql,redis")
    target.write_text(render(plan,services))
    print(json.dumps({"generated":[str(target)],"services":services},indent=2))
if __name__=="__main__": main()
