from __future__ import annotations
import sys
from pathlib import Path
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from scan_repository import scan_repository
from analyze_architecture import analyze
from generate_terraform import build_plan, generate_project, SUPPORTED_PROVIDERS
import validate_terraform

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

@pytest.mark.parametrize("provider", SUPPORTED_PROVIDERS)
def test_generated_infrastructure_passes_static_security_policy(tmp_path, provider):
    scan = scan_repository(EXAMPLES / "python-fastapi").to_dict()
    arch = analyze(scan).to_dict()
    plan = build_plan(scan, arch, provider)
    output = tmp_path / provider / "infra"
    generate_project(output, plan, project_name="secure-demo")

    findings = validate_terraform.static_security_policy(output)
    assert findings == [], "\\n".join(findings)

    root_variables = (output / "variables.tf").read_text(encoding="utf-8")
    assert 'variable "container_image"' in root_variables
    assert "@sha256:" in root_variables
    assert "[0-9a-f]{64}" in root_variables

    combined = "\\n".join(p.read_text(encoding="utf-8") for p in output.rglob("*.tf"))
    assert ":latest" not in combined
    if provider == "aws":
        assert 'image_tag_mutability = "IMMUTABLE"' in combined
        assert 'protocol    = "HTTPS"' in combined or 'protocol          = "HTTPS"' in combined
        assert 'certificate_arn   = var.certificate_arn' in combined
    elif provider == "azure":
        assert "admin_enabled       = false" in combined
        assert "public_network_access_enabled = false" in combined
        assert "delegated_subnet_id" in combined
    else:
        assert "member   = " + '"allUsers"' in combined
        assert "count    = var.allow_unauthenticated ? 1 : 0" in combined
        assert "default     = false" in combined


def test_static_policy_rejects_mutable_images_and_public_databases(tmp_path):
    (tmp_path / "main.tf").write_text(
        '''
        resource "example_service" "bad" {
          image = "registry.example.com/app:latest"
        }
        resource "azurerm_postgresql_flexible_server" "bad" {
          public_network_access_enabled = true
        }
        ''',
        encoding="utf-8",
    )
    findings = validate_terraform.static_security_policy(tmp_path)
    assert any("latest" in item for item in findings)
    assert any("Azure PostgreSQL" in item for item in findings)


def test_no_database_plan_does_not_emit_database_secret_inputs(tmp_path):
    from generate_terraform import InfraPlan, _variables_block

    variables = _variables_block("aws", "demo", "us-east-1", needs_database=False)
    assert 'variable "db_password"' not in variables
    assert 'variable "db_username"' not in variables
    assert 'variable "container_image"' in variables

    plan = InfraPlan(
        provider="aws",
        architecture="monolithic",
        needs_database=False,
        needs_compute=True,
        needs_network=True,
    )
    output = tmp_path / "no-database"
    generate_project(output, plan, project_name="no-db")
    generated_variables = (output / "variables.tf").read_text(encoding="utf-8")
    tfvars_example = (output / "terraform.tfvars.example").read_text(encoding="utf-8")
    assert 'variable "db_password"' not in generated_variables
    assert "db_username" not in tfvars_example
    assert "container_image" in tfvars_example


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



@pytest.mark.parametrize("provider", SUPPORTED_PROVIDERS)
def test_database_password_is_required_and_sensitive(provider):
    from generate_terraform import _variables_block

    variables = _variables_block(provider, "demo", "region-1")
    start = variables.index('variable "db_password"')
    block = variables[start:variables.index("}", start) + 1]
    assert "sensitive" in block
    assert "default" not in block



def test_project_name_rejects_hcl_injection(tmp_path):
    scan = scan_repository(EXAMPLES / "python-fastapi").to_dict()
    arch = analyze(scan).to_dict()
    plan = build_plan(scan, arch, "aws")
    with pytest.raises(ValueError, match="project_name"):
        generate_project(tmp_path / "infra", plan, project_name='demo" } resource "x" "y" {')


def test_database_engine_is_allowlisted(tmp_path):
    from generate_terraform import InfraPlan

    plan = InfraPlan(provider="gcp", architecture="monolithic", needs_database=True, db_engine='postgres" }')
    with pytest.raises(ValueError, match="Unsupported database engine"):
        generate_project(tmp_path / "infra", plan, project_name="demo")


@pytest.mark.parametrize("provider", SUPPORTED_PROVIDERS)
def test_generated_terraform_passes_native_validation_when_cli_available(tmp_path, provider):
    import shutil

    if not shutil.which("terraform"):
        pytest.skip("Terraform CLI is installed only in the dedicated Terraform validation CI job.")

    scan = scan_repository(EXAMPLES / "python-fastapi").to_dict()
    arch = analyze(scan).to_dict()
    plan = build_plan(scan, arch, provider)
    output = tmp_path / provider / "native-infra"
    generate_project(output, plan, project_name="native-check")

    result = validate_terraform.validate(output)
    assert result.terraform_available is True
    assert result.policy_ok is True
    assert result.fmt_ok is True, json.dumps(result.to_dict(), indent=2)
    assert result.init_ok is True, json.dumps(result.to_dict(), indent=2)
    assert result.validate_ok is True, json.dumps(result.to_dict(), indent=2)
    assert result.success is True, json.dumps(result.to_dict(), indent=2)
