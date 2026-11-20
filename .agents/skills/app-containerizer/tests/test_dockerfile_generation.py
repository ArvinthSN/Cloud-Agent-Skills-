import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "generate_dockerfile.py"


def run(tmp_path, plan, *flags):
    plan_file = tmp_path / "plan.json"
    plan_file.write_text(json.dumps(plan), encoding="utf-8")
    return subprocess.run(
        [sys.executable, str(SCRIPT), "--path", str(tmp_path), "--plan", str(plan_file), *flags],
        capture_output=True,
        text=True,
    )


def test_generate_fastapi_dockerfile(tmp_path):
    plan = {
        "stack": "python",
        "framework": "fastapi",
        "package_manager": "pip",
        "dependency_file": "requirements.txt",
        "startup_command": ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"],
        "port": 8000,
    }
    result = run(tmp_path, plan, "--approve")
    assert result.returncode == 0, result.stderr
    dockerfile = (tmp_path / "Dockerfile").read_text(encoding="utf-8")
    assert "USER app" in dockerfile
    assert "pip install --no-cache-dir -r requirements.txt" in dockerfile
    assert 'CMD ["uvicorn", "main:app"' in dockerfile


def test_existing_docker_assets_are_preserved_without_overwrite(tmp_path):
    (tmp_path / "Dockerfile").write_text("FROM scratch\n", encoding="utf-8")
    plan = {
        "stack": "python",
        "package_manager": "pip",
        "dependency_file": "requirements.txt",
        "startup_command": ["python", "app.py"],
        "port": 8000,
    }
    result = run(tmp_path, plan, "--approve")
    assert result.returncode != 0
    assert (tmp_path / "Dockerfile").read_text(encoding="utf-8") == "FROM scratch\n"
    assert not (tmp_path / ".dockerignore").exists()


def test_unsupported_node_package_manager_fails_closed(tmp_path):
    plan = {
        "stack": "nodejs",
        "package_manager": "pnpm",
        "dependency_file": "package.json",
        "startup_command": ["node", "server.js"],
        "port": 3000,
    }
    result = run(tmp_path, plan, "--approve")
    assert result.returncode != 0
    assert "npm with package-lock.json is required" in result.stderr
    assert not (tmp_path / "Dockerfile").exists()


def test_generation_requires_approval(tmp_path):
    plan = {
        "stack": "python",
        "package_manager": "pip",
        "dependency_file": "requirements.txt",
        "startup_command": ["python", "app.py"],
        "port": 8000,
    }
    result = run(tmp_path, plan)
    assert result.returncode != 0
    assert not (tmp_path / "Dockerfile").exists()


def test_generate_gradle_spring_boot_dockerfile(tmp_path):
    plan = {
        "stack": "java",
        "framework": "spring-boot",
        "package_manager": "gradle",
        "dependency_file": "build.gradle",
        "runtime_version": "17",
        "build_tool_version": "9.5.1",
        "startup_command": ["java", "-jar", "/app/app.jar"],
        "port": 8080,
    }
    result = run(tmp_path, plan, "--approve")
    assert result.returncode == 0, result.stderr
    dockerfile = (tmp_path / "Dockerfile").read_text(encoding="utf-8")
    assert "FROM gradle:9.5.1-jdk17 AS build" in dockerfile
    assert "gradle --no-daemon bootJar -x test" in dockerfile
    assert "! -name '*-plain.jar'" in dockerfile
    assert "FROM eclipse-temurin:17-jre" in dockerfile
    assert "COPY --from=build --chown=app:app /workspace/app.jar /app/app.jar" in dockerfile
    assert "USER app" in dockerfile
    assert 'ENTRYPOINT ["java", "-jar"' in dockerfile


def test_generate_python_dockerfile_uses_detected_runtime(tmp_path):
    plan = {
        "stack": "python",
        "framework": "fastapi",
        "package_manager": "uv",
        "dependency_file": "uv.lock",
        "runtime_version": "3.14",
        "runtime_version_source": "pyproject.toml",
        "runtime_constraint": ">=3.14,<4.0",
        "startup_command": ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"],
        "port": 8000,
    }
    result = run(tmp_path, plan, "--approve")
    assert result.returncode == 0, result.stderr
    dockerfile = (tmp_path / "Dockerfile").read_text(encoding="utf-8")
    assert dockerfile.startswith("FROM python:3.14-slim")
