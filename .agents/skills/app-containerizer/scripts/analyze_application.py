#!/usr/bin/env python3
"""Build an explicit containerization plan from scanner JSON."""
from __future__ import annotations

import argparse
import json
from pathlib import Path


DEFAULT_PORTS = {"python": 8000, "nodejs": 3000, "java": 8080}


def _module_name(entry: str) -> str:
    return Path(entry).with_suffix("").as_posix().replace("/", ".")


def analyze(scan: dict) -> dict:
    stack = scan.get("project_type", "unknown")
    framework = scan.get("framework", "unknown")
    package_manager = scan.get("package_manager", "unknown")
    entry = scan.get("entry_point", "unknown")
    port = DEFAULT_PORTS.get(stack)
    command: list[str] = []
    unknowns: list[str] = []

    if stack == "python" and framework == "fastapi" and entry != "unknown":
        command = ["uvicorn", f"{_module_name(entry)}:app", "--host", "0.0.0.0", "--port", str(port)]
    elif stack == "python" and framework == "flask" and entry != "unknown":
        command = ["gunicorn", f"{_module_name(entry)}:app", "--bind", f"0.0.0.0:{port}"]
        unknowns.append("Confirm the Flask application object is named 'app' and Gunicorn is a runtime dependency.")
    elif stack == "python" and framework == "django":
        unknowns.append("Confirm the Django project WSGI module before generating a startup command.")
    elif stack == "nodejs":
        command = scan.get("start_command") or []
        if not command:
            unknowns.append("No safe Node.js start command was detected; add a start script or confirm the entry point.")
        if package_manager not in ("npm",):
            unknowns.append(f"The detected package manager is {package_manager}; the current Dockerfile generator requires npm with package-lock.json.")
            command = []
    elif stack == "java" and package_manager == "maven":
        command = ["java", "-jar", "/app/app.jar"]
        unknowns.append("Confirm the Maven build produces one executable Spring Boot JAR.")
    elif stack == "java":
        unknowns.append(f"The detected Java build manager is {package_manager}; only Maven packaging is currently supported.")
    else:
        unknowns.append("Stack or framework is not supported for automatic startup command generation.")

    return {
        "stack": stack,
        "framework": framework,
        "package_manager": package_manager,
        "dependency_file": scan.get("dependency_file"),
        "entry_point": entry,
        "runtime_version": scan.get("runtime_version"),
        "port": port,
        "startup_command": command,
        "detected_services": scan.get("detected_services", []),
        "compose_recommended": bool(scan.get("detected_services")),
        "multi_stage_recommended": stack in ("nodejs", "java"),
        "confidence": scan.get("confidence"),
        "unknowns": unknowns,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True)
    parser.add_argument("--output")
    args = parser.parse_args()
    plan = analyze(json.loads(Path(args.input).read_text(encoding="utf-8")))
    rendered = json.dumps(plan, indent=2)
    if args.output:
        Path(args.output).write_text(rendered + "\n", encoding="utf-8")
    print(rendered)


if __name__ == "__main__":
    main()
