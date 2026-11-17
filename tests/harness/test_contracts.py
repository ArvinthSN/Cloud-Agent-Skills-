import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCHEMAS = ROOT / ".agents" / "schemas"


def test_execution_schemas_are_valid_json_and_versioned():
    for name in ("execution-plan.schema.json", "execution-report.schema.json"):
        schema = json.loads((SCHEMAS / name).read_text(encoding="utf-8"))
        assert schema["$schema"].endswith("/2020-12/schema")
        assert schema["type"] == "object"
        assert schema["additionalProperties"] is False


def test_execution_report_has_explicit_check_states():
    schema = json.loads((SCHEMAS / "execution-report.schema.json").read_text(encoding="utf-8"))
    states = schema["properties"]["checks"]["items"]["properties"]["status"]["enum"]
    assert states == ["PASS", "FAIL", "WARNING", "SKIPPED", "NOT_RUN"]


def test_shared_context_and_orchestrator_are_documented():
    standards = ROOT / ".agents" / "standards"
    for name in ("skill-contract.md", "output-contract.md", "token-efficiency.md"):
        assert (standards / name).is_file()
    orchestrator = ROOT / ".agents" / "skills" / "cloud-engineering-orchestrator" / "SKILL.md"
    content = orchestrator.read_text(encoding="utf-8")
    assert "Re-scan only" in content
    assert "Never run Terraform apply/destroy" in content



def test_handoff_schema_and_executable_orchestrator_are_present():
    schema = json.loads((SCHEMAS / "skill-handoff.schema.json").read_text(encoding="utf-8"))
    assert schema["properties"]["schema_version"]["const"] == "1.0"
    assert "snapshot_hash" in schema["required"]
    orchestrator = ROOT / ".agents" / "skills" / "cloud-engineering-orchestrator"
    assert (orchestrator / "scripts" / "orchestrate.py").is_file()
    content = (orchestrator / "SKILL.md").read_text(encoding="utf-8")
    assert "orchestrate.py plan" in content
    assert "orchestrate.py execute" in content
