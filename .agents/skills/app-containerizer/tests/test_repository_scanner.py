import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCANNER = ROOT / "scripts" / "scan_repository.py"


def run_scan(path: Path, *extra: str):
    return subprocess.run(
        [sys.executable, str(SCANNER), "--path", str(path), *extra],
        capture_output=True,
        text=True,
    )


def test_detect_fastapi(tmp_path):
    (tmp_path / "main.py").write_text(
        "from fastapi import FastAPI" + chr(10) + "app = FastAPI()",
        encoding="utf-8",
    )
    (tmp_path / "requirements.txt").write_text(
        "fastapi==1" + chr(10) + "uvicorn==1",
        encoding="utf-8",
    )
    result = run_scan(tmp_path)
    assert result.returncode == 0, result.stderr
    detected = json.loads(result.stdout)
    assert detected["project_type"] == "python"
    assert detected["framework"] == "fastapi"


def test_invalid_path():
    result = run_scan(Path("/not/a/real/path"))
    assert result.returncode != 0


def test_detect_mysql_and_redis_services(tmp_path):
    (tmp_path / "requirements.txt").write_text("mysql==1" + chr(10) + "redis==1")
    (tmp_path / "main.py").write_text("import redis" + chr(10))
    result = run_scan(tmp_path)
    assert result.returncode == 0, result.stderr
    detected = json.loads(result.stdout)["detected_services"]
    assert "mysql" in detected
    assert "redis" in detected


def test_output_file_returns_compact_receipt(tmp_path):
    (tmp_path / "main.py").write_text(
        "from fastapi import FastAPI" + chr(10) + "app = FastAPI()",
        encoding="utf-8",
    )
    (tmp_path / "requirements.txt").write_text("fastapi==1", encoding="utf-8")
    report_path = tmp_path.parent / (tmp_path.name + "-scan.json")
    result = run_scan(tmp_path, "--output", str(report_path))

    assert result.returncode == 0, result.stderr
    receipt = json.loads(result.stdout)
    full_report = json.loads(report_path.read_text(encoding="utf-8"))

    assert receipt["status"] == "completed"
    assert receipt["report"] == str(report_path)
    assert receipt["file_count"] == full_report["file_count"]
    assert "files_sample" not in receipt
    assert "files_sample" in full_report


def test_python_runtime_uses_pyproject_requires_python(tmp_path):
    # A minimum-version constraint must drive the image runtime, not the old global default.
    (tmp_path / "pyproject.toml").write_text(
        '[project]\nrequires-python = ">=3.14,<4.0"\n',
        encoding="utf-8",
    )
    (tmp_path / "uv.lock").write_text("version = 1\n", encoding="utf-8")
    (tmp_path / "app.py").write_text("from fastapi import FastAPI\napp = FastAPI()\n")
    result = run_scan(tmp_path)
    assert result.returncode == 0, result.stderr
    detected = json.loads(result.stdout)
    assert detected["runtime_version"] == "3.14"
    assert detected["runtime_version_source"] == "pyproject.toml"
    assert detected["runtime_constraint"] == ">=3.14,<4.0"
    assert detected["package_manager"] == "uv"


def test_detect_gradle_wrapper_and_java_toolchain(tmp_path):
    (tmp_path / "build.gradle").write_text(
        "plugins { id 'org.springframework.boot' version '3.4.0' }\n"
        "java { toolchain { languageVersion = JavaLanguageVersion.of(17) } }\n",
        encoding="utf-8",
    )
    (tmp_path / "gradlew").write_text("#!/bin/sh\n")
    wrapper = tmp_path / "gradle" / "wrapper"
    wrapper.mkdir(parents=True)
    (wrapper / "gradle-wrapper.properties").write_text(
        "distributionUrl=https://services.gradle.org/distributions/gradle-9.5.1-bin.zip\n",
        encoding="utf-8",
    )
    (tmp_path / "src" / "main" / "java").mkdir(parents=True)
    (tmp_path / "src" / "main" / "java" / "Application.java").write_text(
        "class Application {}\n", encoding="utf-8"
    )
    result = run_scan(tmp_path)
    assert result.returncode == 0, result.stderr
    detected = json.loads(result.stdout)
    assert detected["project_type"] == "java"
    assert detected["package_manager"] == "gradle"
    assert detected["dependency_file"] == "build.gradle"
    assert detected["runtime_version"] == "17"
    assert detected["build_tool_version"] == "9.5.1"
    assert detected["gradle_wrapper"] is True
