import json
import sys
import uuid
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / ".agents"))

from verification import runner


def make_run(tmp_path, skills):
    project = tmp_path / "application"
    project.mkdir()
    run_dir = tmp_path / "run"
    (run_dir / "handoffs").mkdir(parents=True)
    plan = {
        "run_id": str(uuid.uuid4()),
        "selected_skills": skills,
        "workflow": {"project_dir": str(project)},
    }

    if "app-containerizer" in skills:
        (project / "Dockerfile").write_text("FROM python:3.12-slim\n", encoding="utf-8")
        (project / ".dockerignore").write_text(".git\n.env\n", encoding="utf-8")
        handoff_dir = run_dir / "handoffs" / "app-containerizer"
        handoff_dir.mkdir()
        (handoff_dir / "handoff.json").write_text(json.dumps({
            "project_root": str(project),
            "outputs": ["Dockerfile", ".dockerignore"],
        }), encoding="utf-8")

    if "cicd-pipeline-creator" in skills:
        pipeline_dir = project / ".github" / "workflows"
        pipeline_dir.mkdir(parents=True)
        (pipeline_dir / "pipeline.yml").write_text("name: CI\n", encoding="utf-8")
        (pipeline_dir / "PIPELINE_NOTES.md").write_text("# Notes\n", encoding="utf-8")
        handoff_dir = run_dir / "handoffs" / "cicd-pipeline-creator"
        handoff_dir.mkdir()
        (handoff_dir / "handoff.json").write_text(json.dumps({
            "project_root": str(project),
            "platform": "github",
            "output_dir": str(pipeline_dir),
            "outputs": ["pipeline.yml", "PIPELINE_NOTES.md"],
        }), encoding="utf-8")

    if "infra-creator" in skills:
        infra_dir = project / "infra"
        (infra_dir / "modules").mkdir(parents=True)
        (infra_dir / "main.tf").write_text('terraform { required_version = ">= 1.5" }\n', encoding="utf-8")
        handoff_dir = run_dir / "handoffs" / "infra-creator"
        handoff_dir.mkdir()
        (handoff_dir / "handoff.json").write_text(json.dumps({
            "project_root": str(project),
            "provider": "aws",
            "output_dir": str(infra_dir),
            "outputs": ["main.tf", "modules/"],
        }), encoding="utf-8")

    return plan, run_dir, project


def fake_validator(command):
    script = Path(command[1]).name
    if script == "validate_container.py":
        return SimpleNamespace(returncode=0, stdout=json.dumps([
            {"check": "Dockerfile exists", "status": "PASS", "detail": "present"},
            {"check": "secret patterns", "status": "PASS", "detail": "clean"},
        ]), stderr="")
    if script == "validate_pipeline.py":
        return SimpleNamespace(returncode=0, stdout=json.dumps({
            "status": "pass", "errors": [], "warnings": [], "ran": [], "skipped": [],
        }), stderr="")
    if script == "validate_terraform.py":
        return SimpleNamespace(returncode=0, stdout=json.dumps({
            "policy_ok": True, "terraform_available": False,
            "fmt_ok": None, "init_ok": None, "validate_ok": None,
        }), stderr="")
    return SimpleNamespace(returncode=0, stdout="", stderr="")


def test_static_verification_emits_structured_checks_and_never_runs_docker(tmp_path, monkeypatch):
    plan, run_dir, _ = make_run(tmp_path, ["app-containerizer", "cicd-pipeline-creator"])
    calls = []

    def fake_run(command, **kwargs):
        calls.append(command)
        return fake_validator(command)

    monkeypatch.setattr(runner, "_run", fake_run)
    monkeypatch.setattr(runner.shutil, "which", lambda _: None)

    report = runner.verify_artifacts(plan, run_dir)

    assert report["status"] == "partial"  # optional security/native tools are unavailable
    assert any(item["name"] == "pipeline-policy-validation" and item["status"] == "PASS" for item in report["checks"])
    assert any(item["name"] == "docker-image-build" and item["status"] == "SKIPPED" for item in report["checks"])
    assert not any(command and command[0] == "docker" for command in calls)
    assert all(item["status"] in runner.VALID_STATUSES for item in report["checks"])


def test_docker_build_is_opt_in_network_is_disabled_and_image_is_removed(tmp_path, monkeypatch):
    plan, run_dir, project = make_run(tmp_path, ["app-containerizer"])
    calls = []

    def fake_run(command, **kwargs):
        calls.append((command, kwargs))
        return fake_validator(command)

    monkeypatch.setattr(runner, "_run", fake_run)
    monkeypatch.setattr(
        runner.shutil, "which",
        lambda name: "/usr/bin/docker" if name == "docker" else None,
    )

    report = runner.verify_artifacts(plan, run_dir, docker_build=True)

    build = next(command for command, _ in calls if command[0] == "/usr/bin/docker" and command[1] == "build")
    assert "--network=none" in build
    assert "--pull=false" in build
    assert any(command[1:3] == ["image", "rm"] for command, _ in calls if command[0] == "/usr/bin/docker")
    assert any(item["name"] == "docker-image-build" and item["status"] == "PASS" for item in report["checks"])


def test_terraform_plan_uses_backend_refresh_and_credential_safe_flags(tmp_path, monkeypatch):
    plan, run_dir, project = make_run(tmp_path, ["infra-creator"])
    calls = []

    def fake_run(command, **kwargs):
        calls.append((command, kwargs))
        return fake_validator(command)

    monkeypatch.setattr(runner, "_run", fake_run)
    monkeypatch.setattr(
        runner.shutil, "which",
        lambda name: "/usr/bin/terraform" if name == "terraform" else None,
    )
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "must-not-be-forwarded")
    monkeypatch.setenv("GOOGLE_APPLICATION_CREDENTIALS", "/tmp/private.json")

    report = runner.verify_artifacts(plan, run_dir, terraform_plan=True)

    terraform_calls = [(command, kwargs) for command, kwargs in calls if command[0] == "/usr/bin/terraform"]
    assert [command[1] for command, _ in terraform_calls] == ["init", "validate", "plan"]
    init = terraform_calls[0][0]
    plan_command, plan_kwargs = terraform_calls[-1]
    assert "-backend=false" in init
    assert "-refresh=false" in plan_command
    assert "-lock=false" in plan_command
    assert "apply" not in plan_command
    assert "AWS_SECRET_ACCESS_KEY" not in plan_kwargs["env"]
    assert "GOOGLE_APPLICATION_CREDENTIALS" not in plan_kwargs["env"]
    assert any(item["name"] == "terraform-plan" and item["status"] == "PASS" for item in report["checks"])


def test_secret_scan_failure_does_not_copy_secret_values_into_report(tmp_path, monkeypatch):
    plan, run_dir, _ = make_run(tmp_path, ["app-containerizer"])

    def fake_run(command, **kwargs):
        if command[0] == "/usr/bin/gitleaks":
            return SimpleNamespace(returncode=1, stdout='[{"RuleID":"aws-access-token","Secret":"very-secret-value"}]', stderr="")
        return fake_validator(command)

    monkeypatch.setattr(runner, "_run", fake_run)
    monkeypatch.setattr(
        runner.shutil, "which",
        lambda name: "/usr/bin/gitleaks" if name == "gitleaks" else None,
    )

    report = runner.verify_artifacts(plan, run_dir)

    serialized = json.dumps(report)
    assert report["status"] == "failed"
    assert "very-secret-value" not in serialized
    assert any(item["name"] == "gitleaks-secret-scan" and item["status"] == "FAIL" for item in report["checks"])
