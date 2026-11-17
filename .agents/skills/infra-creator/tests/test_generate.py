from __future__ import annotations
import sys
from pathlib import Path
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from scan_repository import scan_repository
from analyze_architecture import analyze
from generate_terraform import build_plan, generate_project, SUPPORTED_PROVIDERS

EXAMPLES = ROOT / "examples"


@pytest.mark.parametrize("provider", SUPPORTED_PROVIDERS)
def test_plan_all_providers(provider):
    scan = scan_repository(EXAMPLES / "python-fastapi").to_dict()
    arch = analyze(scan).to_dict()
    plan = build_plan(scan, arch, provider)
    assert plan.provider == provider
    assert plan.needs_compute
    assert plan.needs_database


@pytest.mark.parametrize("provider", SUPPORTED_PROVIDERS)
def test_generate_all_providers(tmp_path, provider):
    scan = scan_repository(EXAMPLES / "python-fastapi").to_dict()
    arch = analyze(scan).to_dict()
    plan = build_plan(scan, arch, provider)
    out = tmp_path / provider / "infra"
    generate_project(out, plan, project_name="demo", region=None)
    assert (out / "main.tf").is_file()
    assert (out / "providers.tf").is_file()
    assert (out / "versions.tf").is_file()
    assert (out / "modules" / "networking").is_dir()
    assert (out / "modules" / "compute").is_dir()
    assert (out / "modules" / "database").is_dir()
    assert (out / "README.md").is_file()
    main = (out / "main.tf").read_text()
    assert "module" in main

def test_generate_preserves_non_empty_output_directory(tmp_path):
    scan = scan_repository(EXAMPLES / "python-fastapi").to_dict()
    arch = analyze(scan).to_dict()
    plan = build_plan(scan, arch, "aws")
    out = tmp_path / "infra"
    out.mkdir()
    marker = out / "keep.txt"
    marker.write_text("user data")
    with pytest.raises(FileExistsError):
        generate_project(out, plan)
    assert marker.read_text() == "user data"


def test_serverless_generation_is_rejected_until_template_exists(tmp_path):
    from generate_terraform import InfraPlan
    plan = InfraPlan(provider="aws", architecture="serverless", compute_type="serverless")
    with pytest.raises(ValueError, match="Serverless generation is not implemented"):
        generate_project(tmp_path / "infra", plan)


def test_compute_without_network_is_rejected(tmp_path):
    from generate_terraform import InfraPlan
    plan = InfraPlan(provider="aws", architecture="monolithic", needs_network=False, needs_compute=True)
    with pytest.raises(ValueError, match="require networking"):
        generate_project(tmp_path / "infra", plan)

def test_terraform_missing_cli_is_not_success(monkeypatch, tmp_path):
    import validate_terraform
    monkeypatch.setattr(validate_terraform.shutil, "which", lambda _: None)
    result = validate_terraform.validate(tmp_path)
    assert result.success is False
    assert result.terraform_available is False
    assert result.errors

def test_database_without_network_is_rejected(tmp_path):
    from generate_terraform import InfraPlan
    plan = InfraPlan(provider="azure", architecture="monolithic", needs_network=False, needs_compute=False, needs_database=True)
    with pytest.raises(ValueError, match="database templates require a networking"):
        generate_project(tmp_path / "infra", plan)


def test_aws_database_without_compute_is_rejected(tmp_path):
    from generate_terraform import InfraPlan
    plan = InfraPlan(provider="aws", architecture="monolithic", needs_compute=False, needs_database=True)
    with pytest.raises(ValueError, match="AWS database template requires the compute"):
        generate_project(tmp_path / "infra", plan)

def test_terraform_validation_uses_temporary_copy(monkeypatch, tmp_path):
    import validate_terraform
    calls = []
    monkeypatch.setattr(validate_terraform.shutil, "which", lambda _: "/usr/bin/terraform")

    def fake_run(cmd, cwd, timeout=120):
        calls.append(Path(cwd))
        if cmd[1] == "init":
            (Path(cwd) / ".terraform").mkdir()
        return 0, "ok", ""

    monkeypatch.setattr(validate_terraform, "run_cmd", fake_run)
    result = validate_terraform.validate(tmp_path)
    assert result.success is True
    assert calls
    assert all(path != tmp_path for path in calls)
    assert not (tmp_path / ".terraform").exists()
