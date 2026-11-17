import importlib.util
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / ".agents" / "skills" / "cloud-engineering-orchestrator" / "scripts" / "orchestrate.py"
SPEC = importlib.util.spec_from_file_location("cloud_agent_orchestrator", SCRIPT)
orchestrator = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = orchestrator
SPEC.loader.exec_module(orchestrator)


def make_node_project(root: Path) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    (root / "package.json").write_text(
        json.dumps({
            "name": "tiny-service",
            "version": "1.0.0",
            "engines": {"node": ">=20"},
            "scripts": {"build": "node build.js", "start": "node server.js", "test": "node test.js"},
        }),
        encoding="utf-8",
    )
    (root / "package-lock.json").write_text(
        json.dumps({
            "name": "tiny-service",
            "version": "1.0.0",
            "lockfileVersion": 3,
            "requires": True,
            "packages": {"": {"name": "tiny-service", "version": "1.0.0"}},
        }),
        encoding="utf-8",
    )
    (root / "server.js").write_text('console.log("service started");\n', encoding="utf-8")
    (root / "build.js").write_text(
        'const fs = require("node:fs"); fs.mkdirSync("dist", {recursive:true}); fs.writeFileSync("dist/app.txt", "ok");\n',
        encoding="utf-8",
    )
    (root / "test.js").write_text('if (2 + 2 !== 4) process.exit(1);\n', encoding="utf-8")
    return root


def plan_for(project: Path, run_dir: Path, skills="app-containerizer,cicd-pipeline-creator"):
    args = orchestrator.build_parser().parse_args([
        "plan",
        "--project", str(project),
        "--goal", "Create local container and CI artifacts",
        "--skills", skills,
        "--platform", "github",
        "--run-dir", str(run_dir),
    ])
    return orchestrator.create_plan(args)


def test_scan_emits_only_bounded_metadata_and_never_env_values(tmp_path):
    project = make_node_project(tmp_path / "app")
    (project / ".env").write_text("DB_PASSWORD=do-not-copy-this\nAPI_TOKEN=secret-value\n", encoding="utf-8")
    (project / ".env.example").write_text("DB_PASSWORD=replace-me\n", encoding="utf-8")
    context = orchestrator.scan_project(project)

    assert context["schema_version"] == "1.0"
    assert context["snapshot_hash"]
    assert "DB_PASSWORD" in context["sensitive_env_var_names"]
    serialized = json.dumps(context)
    assert "do-not-copy-this" not in serialized
    assert "secret-value" not in serialized
    assert "replace-me" not in serialized
    assert context["projects"][0]["version"] == "20"


def test_plan_creates_versioned_handoffs_from_one_context(tmp_path):
    project = make_node_project(tmp_path / "app")
    run_dir = tmp_path / "run"
    plan = plan_for(project, run_dir)

    assert plan["approval_required"] is True
    assert plan["selected_skills"] == ["app-containerizer", "cicd-pipeline-creator"]
    context = json.loads((run_dir / "project-context.json").read_text(encoding="utf-8"))
    container = json.loads((run_dir / "handoffs" / "app-containerizer" / "handoff.json").read_text(encoding="utf-8"))
    cicd = json.loads((run_dir / "handoffs" / "cicd-pipeline-creator" / "handoff.json").read_text(encoding="utf-8"))
    assert container["snapshot_hash"] == context["snapshot_hash"]
    assert cicd["snapshot_hash"] == context["snapshot_hash"]
    assert container["input"]["start_command"] == ["npm", "start"]
    assert cicd["ci_project"]["install"] == "npm ci"
    assert cicd["ci_project"]["build"] == "npm run build"
    assert cicd["ci_project"]["lockfile"] == "package-lock.json"


def test_plan_requires_explicit_project_for_monorepo(tmp_path):
    project = tmp_path / "mono"
    make_node_project(project / "frontend")
    make_node_project(project / "backend")
    run_dir = tmp_path / "run"
    args = orchestrator.build_parser().parse_args([
        "plan", "--project", str(project), "--goal", "build pipelines",
        "--skills", "cicd-pipeline-creator", "--platform", "github", "--run-dir", str(run_dir),
    ])
    with pytest.raises(orchestrator.OrchestratorError, match="Select one with --project-dir"):
        orchestrator.create_plan(args)


def test_plan_rejects_unsupported_ci_stack_before_creating_run(tmp_path):
    project = tmp_path / "java"
    project.mkdir()
    (project / "pom.xml").write_text("<project />", encoding="utf-8")
    run_dir = tmp_path / "run"
    args = orchestrator.build_parser().parse_args([
        "plan", "--project", str(project), "--goal", "create pipeline",
        "--skills", "cicd-pipeline-creator", "--platform", "github", "--run-dir", str(run_dir),
    ])
    with pytest.raises(orchestrator.OrchestratorError, match="does not currently support"):
        orchestrator.create_plan(args)
    assert not run_dir.exists()


def test_run_directory_inside_project_must_be_ignored_state_location(tmp_path):
    project = make_node_project(tmp_path / "app")
    args = orchestrator.build_parser().parse_args([
        "plan", "--project", str(project), "--goal", "containerize",
        "--skills", "app-containerizer", "--run-dir", str(project / "temporary-run"),
    ])
    with pytest.raises(orchestrator.OrchestratorError, match="outside the project"):
        orchestrator.create_plan(args)


def test_execute_requires_explicit_approval_and_rejects_stale_project(tmp_path):
    project = make_node_project(tmp_path / "app")
    run_dir = tmp_path / "run"
    plan_for(project, run_dir)

    unapproved = orchestrator.build_parser().parse_args(["execute", "--run-dir", str(run_dir)])
    with pytest.raises(orchestrator.OrchestratorError, match="No project files were changed"):
        orchestrator.execute_run(unapproved)

    (project / "server.js").write_text('console.log("changed");\n', encoding="utf-8")
    approved = orchestrator.build_parser().parse_args(["execute", "--run-dir", str(run_dir), "--approve"])
    with pytest.raises(orchestrator.OrchestratorError, match="Project files changed"):
        orchestrator.execute_run(approved)


def test_approved_execute_generates_container_and_pipeline_artifacts(tmp_path):
    project = make_node_project(tmp_path / "app")
    run_dir = tmp_path / "run"
    plan_for(project, run_dir)
    args = orchestrator.build_parser().parse_args([
        "execute", "--run-dir", str(run_dir), "--approve",
    ])
    report = orchestrator.execute_run(args)

    assert report["status"] in {"completed", "partial"}
    assert (project / "Dockerfile").is_file()
    assert (project / ".dockerignore").is_file()
    pipeline = project / ".github" / "workflows" / "pipeline.yml"
    assert pipeline.is_file()
    assert "actions/download-artifact@v4" in pipeline.read_text(encoding="utf-8")
    assert (run_dir / "execution-report.json").is_file()
    assert report["skill_reports"]["app-containerizer"]["status"] == "completed"
    assert report["skill_reports"]["cicd-pipeline-creator"]["status"] in {"completed", "partial"}


def test_infra_plan_requires_provider(tmp_path):
    project = make_node_project(tmp_path / "app")
    args = orchestrator.build_parser().parse_args([
        "plan", "--project", str(project), "--goal", "create Terraform",
        "--skills", "infra-creator", "--run-dir", str(tmp_path / "run"),
    ])
    with pytest.raises(orchestrator.OrchestratorError, match="--provider is required"):
        orchestrator.create_plan(args)
