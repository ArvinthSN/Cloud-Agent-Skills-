#!/usr/bin/env python3
"""Build and smoke-test a generated container under restrictive local runtime settings.

The fixture is intentionally a tiny stdlib HTTP service. No application from an
external repository is executed by this test.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import subprocess
import sys
import tempfile
import time
import uuid
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
GENERATOR = ROOT / ".agents" / "skills" / "app-containerizer" / "scripts" / "generate_dockerfile.py"


def run(command: list[str], *, timeout: int = 120) -> subprocess.CompletedProcess[str]:
    return subprocess.run(command, capture_output=True, text=True, timeout=timeout, check=False)


def require_success(result: subprocess.CompletedProcess[str], label: str) -> None:
    if result.returncode:
        detail = (result.stderr or result.stdout)[-5000:]
        raise RuntimeError(f"{label} failed (exit {result.returncode}):\n{detail}")


def inspect_container(docker: str, container: str) -> dict[str, Any]:
    result = run([docker, "inspect", container])
    require_success(result, "docker inspect")
    payload = json.loads(result.stdout)
    if not isinstance(payload, list) or not payload:
        raise RuntimeError("docker inspect returned no container metadata")
    return payload[0]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--image-tag", default=f"cloud-agent-readiness:{uuid.uuid4().hex[:12]}")
    parser.add_argument("--keep-image", action="store_true", help="Keep the image for a subsequent security scan.")
    args = parser.parse_args()

    docker = shutil.which("docker")
    if not docker:
        print(json.dumps({"status": "NOT_RUN", "reason": "Docker CLI is unavailable"}))
        return 2

    container = f"cloud-agent-readiness-{uuid.uuid4().hex[:10]}"
    image_built = False
    result: dict[str, Any] = {"status": "FAIL", "image_tag": args.image_tag, "checks": []}
    try:
        with tempfile.TemporaryDirectory(prefix="cloud-agent-runtime-") as temporary:
            app = Path(temporary)
            (app / "requirements.txt").write_text("# stdlib-only smoke fixture\n", encoding="utf-8")
            (app / "app.py").write_text(
                "from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer\n"
                "class Handler(BaseHTTPRequestHandler):\n"
                "    def do_GET(self):\n"
                "        if self.path != '/health':\n"
                "            self.send_error(404); return\n"
                "        body = b'{\"status\":\"ok\"}'\n"
                "        self.send_response(200)\n"
                "        self.send_header('Content-Type', 'application/json')\n"
                "        self.send_header('Content-Length', str(len(body)))\n"
                "        self.end_headers()\n"
                "        self.wfile.write(body)\n"
                "    def log_message(self, *_args): pass\n"
                "ThreadingHTTPServer(('0.0.0.0', 8000), Handler).serve_forever()\n",
                encoding="utf-8",
            )
            plan = {
                "stack": "python",
                "framework": "stdlib-http-smoke",
                "package_manager": "pip",
                "dependency_file": "requirements.txt",
                "runtime_version": "3.12",
                "startup_command": ["python", "app.py"],
                "port": 8000,
            }
            plan_path = app / "plan.json"
            plan_path.write_text(json.dumps(plan), encoding="utf-8")
            generated = run([
                sys.executable, str(GENERATOR), "--path", str(app),
                "--plan", str(plan_path), "--approve",
            ])
            require_success(generated, "Dockerfile generation")
            dockerfile = (app / "Dockerfile").read_bytes()
            result["dockerfile_sha256"] = hashlib.sha256(dockerfile).hexdigest()
            result["checks"].append("generated-dockerfile")

            built = run([docker, "build", "--pull", "--tag", args.image_tag, str(app)], timeout=900)
            require_success(built, "Docker image build")
            image_built = True
            result["checks"].append("docker-build")

            started = run([
                docker, "run", "--detach", "--name", container,
                "--network", "none", "--read-only",
                "--tmpfs", "/tmp:rw,noexec,nosuid,size=16m",
                "--cap-drop", "ALL", "--security-opt", "no-new-privileges",
                "--pids-limit", "64", "--memory", "128m", "--cpus", "0.5",
                args.image_tag,
            ])
            require_success(started, "hardened container start")
            result["checks"].append("hardened-container-start")

            deadline = time.monotonic() + 30
            last_error = ""
            while time.monotonic() < deadline:
                probe = run([
                    docker, "exec", container, "python", "-c",
                    "import urllib.request; print(urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=2).read().decode())",
                ], timeout=5)
                if probe.returncode == 0 and json.loads(probe.stdout.strip()) == {"status": "ok"}:
                    last_error = ""
                    break
                last_error = (probe.stderr or probe.stdout)[-1000:]
                time.sleep(1)
            else:
                raise RuntimeError(f"Container health endpoint did not become ready: {last_error}")

            metadata = inspect_container(docker, container)
            config = metadata.get("Config") or {}
            host = metadata.get("HostConfig") or {}
            uid = run([
                docker, "exec", container, "python", "-c", "import os; print(os.getuid())",
            ])
            require_success(uid, "non-root UID check")
            uid_value = int(uid.stdout.strip())
            if uid_value == 0:
                raise RuntimeError("Container process is running as root")
            if not host.get("ReadonlyRootfs"):
                raise RuntimeError("Container root filesystem is not read-only")
            if "ALL" not in (host.get("CapDrop") or []):
                raise RuntimeError("Container capabilities were not fully dropped")
            if host.get("NetworkMode") != "none":
                raise RuntimeError("Container is not running with networking disabled")
            if not any("no-new-privileges" in item for item in (host.get("SecurityOpt") or [])):
                raise RuntimeError("no-new-privileges is not enabled")
            if int(host.get("PidsLimit") or 0) != 64:
                raise RuntimeError("Container PID limit was not applied")
            if int(host.get("Memory") or 0) != 128 * 1024 * 1024:
                raise RuntimeError("Container memory limit was not applied")
            if int(host.get("NanoCpus") or 0) != 500_000_000:
                raise RuntimeError("Container CPU limit was not applied")

            result["checks"].extend([
                "health-endpoint",
                "non-root-user",
                "read-only-rootfs",
                "drop-all-capabilities",
                "network-disabled",
                "no-new-privileges",
                "pid-limit",
                "memory-and-cpu-limits",
            ])
            result["runtime"] = {
                "uid": uid_value,
                "readonly_rootfs": bool(host.get("ReadonlyRootfs")),
                "cap_drop": host.get("CapDrop", []),
                "network_mode": host.get("NetworkMode"),
                "pids_limit": host.get("PidsLimit"),
                "memory_bytes": host.get("Memory"),
                "nano_cpus": host.get("NanoCpus"),
            }
            result["status"] = "PASS"
    except (OSError, subprocess.TimeoutExpired, RuntimeError, ValueError, json.JSONDecodeError) as exc:
        result["error"] = str(exc)
    finally:
        run([docker, "rm", "--force", container], timeout=60)
        if image_built and (not args.keep_image or result["status"] != "PASS"):
            run([docker, "image", "rm", "--force", args.image_tag], timeout=60)

    print(json.dumps(result, indent=2))
    return 0 if result["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
