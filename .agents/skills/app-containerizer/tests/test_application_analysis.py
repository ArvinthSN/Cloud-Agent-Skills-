import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "analyze_application.py"


def analyze(tmp_path, payload):
    scan_file = tmp_path / "scan.json"
    scan_file.write_text(json.dumps(payload), encoding="utf-8")
    result = subprocess.run(
        [sys.executable, str(SCRIPT), "--input", str(scan_file)],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout)


def test_fastapi_plan(tmp_path):
    plan = analyze(tmp_path, {
        "project_type": "python",
        "framework": "fastapi",
        "entry_point": "main.py",
        "package_manager": "pip",
        "detected_services": [],
        "confidence": "high",
    })
    assert plan["port"] == 8000
    assert plan["startup_command"][:2] == ["uvicorn", "main:app"]


def test_flask_command_uses_detected_module(tmp_path):
    plan = analyze(tmp_path, {
        "project_type": "python",
        "framework": "flask",
        "entry_point": "src/service/app.py",
        "package_manager": "pip",
    })
    assert plan["startup_command"][:2] == ["gunicorn", "src.service.app:app"]


def test_django_placeholder_is_not_generated(tmp_path):
    plan = analyze(tmp_path, {
        "project_type": "python",
        "framework": "django",
        "entry_point": "manage.py",
        "package_manager": "pip",
    })
    assert plan["startup_command"] == []
    assert any("WSGI module" in item for item in plan["unknowns"])


def test_node_uses_scanner_start_command(tmp_path):
    plan = analyze(tmp_path, {
        "project_type": "nodejs",
        "framework": "express",
        "entry_point": "server.js",
        "start_command": ["node", "server.js"],
        "package_manager": "npm",
    })
    assert plan["startup_command"] == ["node", "server.js"]


def test_gradle_spring_boot_plan_has_executable_jar_command(tmp_path):
    plan = analyze(tmp_path, {
        "project_type": "java",
        "framework": "spring-boot",
        "entry_point": "src/main/java/Application.java",
        "package_manager": "gradle",
        "dependency_file": "build.gradle",
        "runtime_version": "17",
        "build_tool_version": "9.5.1",
        "gradle_wrapper": True,
    })
    assert plan["startup_command"] == ["java", "-jar", "/app/app.jar"]
    assert plan["build_tool_version"] == "9.5.1"
    assert plan["gradle_wrapper"] is True
