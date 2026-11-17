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