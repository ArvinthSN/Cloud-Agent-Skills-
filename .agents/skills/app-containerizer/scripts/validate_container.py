#!/usr/bin/env python3
"""Static container checks and an explicitly requested isolated Docker build."""
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import uuid
from pathlib import Path


def validate(repo: Path, build: bool = False) -> list[dict[str, str]]:
    checks: list[dict[str, str]] = []

    def add(name: str, status: str, detail: str) -> None:
        checks.append({"check": name, "status": status, "detail": detail})

    dockerfile = repo / "Dockerfile"
    dockerignore = repo / ".dockerignore"
    add("Dockerfile exists", "PASS" if dockerfile.is_file() else "FAIL", str(dockerfile))
    add(".dockerignore exists", "PASS" if dockerignore.is_file() else "WARNING", str(dockerignore))

    if dockerfile.is_file():
        text = dockerfile.read_text(encoding="utf-8", errors="replace")
        add(
            "exec-form startup",
            "PASS" if ("CMD [" in text or "ENTRYPOINT [" in text) else "WARNING",
            "Check CMD/ENTRYPOINT exec form.",
        )
        add("non-root user", "PASS" if "USER " in text else "WARNING", "Check for an explicit non-root runtime user.")
        risky = any(token in text for token in (
            "COPY .env", "COPY id_rsa", "ENV PASSWORD=", "ARG AWS_SECRET_ACCESS_KEY",
        ))
        add(
            "obvious secret patterns",
            "FAIL" if risky else "PASS",
            "Potential secret pattern found." if risky else "No obvious secret pattern found.",
        )
        add("pinned base tag", "WARNING" if ":latest" in text else "PASS", "Avoid mutable latest tags.")

    if not build:
        add("Docker build", "SKIPPED", "Not requested; static checks only.")
    else:
        docker = shutil.which("docker")
        if not docker:
            add("Docker build", "NOT_RUN", "Docker CLI is not installed; no image was built.")
        elif not dockerfile.is_file():
            add("Docker build", "SKIPPED", "Dockerfile is missing.")
        else:
            tag = f"app-containerizer:verify-{uuid.uuid4().hex[:12]}"
            try:
                result = subprocess.run(
                    [docker, "build", "--network=none", "--pull=false", "--tag", tag, str(repo)],
                    cwd=str(repo),
                    capture_output=True,
                    text=True,
                    timeout=600,
                    check=False,
                )
                add(
                    "Docker build",
                    "PASS" if result.returncode == 0 else "FAIL",
                    "Built with network disabled and no base-image pull."
                    if result.returncode == 0
                    else f"Docker build failed with exit code {result.returncode}; raw build output is not copied into this report.",
                )
            except (OSError, subprocess.TimeoutExpired) as exc:
                result = None
                add("Docker build", "FAIL", f"Docker build could not complete: {type(exc).__name__}.")
            try:
                cleanup = subprocess.run(
                    [docker, "image", "rm", tag],
                    cwd=str(repo),
                    capture_output=True,
                    text=True,
                    timeout=60,
                    check=False,
                )
                if cleanup.returncode == 0:
                    add("Docker image cleanup", "PASS", "Temporary verification image removed.")
                elif result is not None and result.returncode == 0:
                    add("Docker image cleanup", "WARNING", "Temporary image cleanup could not be confirmed; remove it manually if it remains.")
            except (OSError, subprocess.TimeoutExpired):
                if result is not None and result.returncode == 0:
                    add("Docker image cleanup", "WARNING", "Temporary image cleanup could not be confirmed; remove it manually if it remains.")

    return checks


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate generated container artifacts.")
    parser.add_argument("--path", required=True, help="Application directory containing Dockerfile.")
    parser.add_argument("--build", action="store_true", help="Explicitly build locally with network disabled.")
    args = parser.parse_args()
    repo = Path(args.path).resolve()
    if not repo.is_dir():
        parser.error("path must be an existing directory")
    results = validate(repo, args.build)
    print(json.dumps(results, indent=2))
    return 1 if any(item["status"] == "FAIL" for item in results) else 0


if __name__ == "__main__":
    raise SystemExit(main())
