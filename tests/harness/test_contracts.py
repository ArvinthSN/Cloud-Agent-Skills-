import json
from pathlib import Path

from jsonschema import Draft202012Validator

ROOT = Path(__file__).resolve().parents[2]
SCHEMAS = ROOT / ".agents" / "schemas"


def test_execution_schemas_are_valid_json_and_versioned():
    for name in (
        "execution-plan.schema.json",
        "execution-report.schema.json",
        "skill-handoff.schema.json",
        "project-context.schema.json",
        "execution-state.schema.json",
        "architecture-profile.schema.json",
        "skill-selection.schema.json",
        "verification-report.schema.json",
    ):
        schema = json.loads((SCHEMAS / name).read_text(encoding="utf-8"))
        assert schema["$schema"].endswith("/2020-12/schema")
        assert schema["type"] == "object"
        assert schema["additionalProperties"] is False
        Draft202012Validator.check_schema(schema)


def test_execution_report_has_explicit_check_states():
    schema = json.loads((SCHEMAS / "execution-report.schema.json").read_text(encoding="utf-8"))
    states = schema["$defs"]["check"]["properties"]["status"]["enum"]
    assert states == ["PASS", "FAIL", "WARNING", "SKIPPED", "NOT_RUN"]


def test_shared_context_and_orchestrator_are_documented():
    standards = ROOT / ".agents" / "standards"
    for name in ("skill-contract.md", "output-contract.md", "token-efficiency.md"):
        assert (standards / name).is_file()
    orchestrator = ROOT / ".agents" / "skills" / "cloud-engineering-orchestrator" / "SKILL.md"
    content = orchestrator.read_text(encoding="utf-8")
    assert "one bounded read-only scan" in content
    assert "Never execute terraform apply/destroy" in content



def test_handoff_schema_and_executable_orchestrator_are_present():
    schema = json.loads((SCHEMAS / "skill-handoff.schema.json").read_text(encoding="utf-8"))
    assert schema["properties"]["schema_version"]["const"] == "1.1"
    assert "snapshot_hash" in schema["required"]
    orchestrator = ROOT / ".agents" / "skills" / "cloud-engineering-orchestrator"
    assert (orchestrator / "scripts" / "orchestrate.py").is_file()
    content = (orchestrator / "SKILL.md").read_text(encoding="utf-8")
    assert "orchestrate.py plan" in content
    assert "orchestrate.py execute" in content



def test_production_orchestration_contracts_are_documented():
    orchestrator = ROOT / ".agents" / "skills" / "cloud-engineering-orchestrator"
    content = (orchestrator / "SKILL.md").read_text(encoding="utf-8")
    assert "dependency order" in content
    assert "rolled back" in content
    assert "--no-cache" in content
    assert "Draft 2020-12" in content



def test_execution_state_contract_covers_lock_recovery_and_resume():
    schema = json.loads((SCHEMAS / "execution-state.schema.json").read_text(encoding="utf-8"))
    assert schema["properties"]["status"]["enum"] == [
        "ready", "running", "interrupted", "failed", "completed"
    ]
    assert schema["properties"]["transaction"]["properties"]["phase"]["enum"] == [
        "idle", "preparing", "prepared", "running", "committing",
        "rolling_back", "rolled_back", "committed"
    ]
    orchestrator = ROOT / ".agents" / "skills" / "cloud-engineering-orchestrator" / "scripts" / "orchestrate.py"
    source = orchestrator.read_text(encoding="utf-8")
    assert "class ExecutionLock" in source
    assert "def resume_run" in source
    assert "def recover_run" in source



def test_verification_contract_documents_opt_in_builds_and_statuses():
    schema = json.loads((SCHEMAS / "verification-report.schema.json").read_text(encoding="utf-8"))
    assert schema["properties"]["status"]["enum"] == ["completed", "partial", "failed"]
    assert schema["properties"]["requested_verifications"]["properties"]["docker_build"]["type"] == "boolean"
    assert schema["properties"]["requested_verifications"]["properties"]["terraform_plan"]["type"] == "boolean"
    assert schema["properties"]["checks"]["items"]["properties"]["status"]["enum"] == [
        "PASS", "FAIL", "WARNING", "SKIPPED", "NOT_RUN"
    ]
