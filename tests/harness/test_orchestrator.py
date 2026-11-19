import importlib.util
import json
import subprocess
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

    assert context["schema_version"] == "1.1"
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
    assert (project / "Dockerfile").is_file(), json.dumps(report, indent=2)
    assert (project / ".dockerignore").is_file(), json.dumps(report, indent=2)
    pipeline = project / ".github" / "workflows" / "pipeline.yml"
    assert pipeline.is_file()
    assert "actions/download-artifact@0d2ec9d4cbcefe257d822f108de2a1f15f8da9f6" in pipeline.read_text(encoding="utf-8")
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



def test_execute_rejects_tampered_handoff(tmp_path):
    project = make_node_project(tmp_path / "app")
    run_dir = tmp_path / "run"
    plan_for(project, run_dir)
    handoff_path = run_dir / "handoffs" / "app-containerizer" / "handoff.json"
    handoff = json.loads(handoff_path.read_text(encoding="utf-8"))
    handoff["goal"] = "silently change the approved task"
    handoff_path.write_text(json.dumps(handoff), encoding="utf-8")
    args = orchestrator.build_parser().parse_args([
        "execute", "--run-dir", str(run_dir), "--approve",
    ])
    with pytest.raises(orchestrator.OrchestratorError, match="handoff changed"):
        orchestrator.execute_run(args)


def test_execute_rejects_tampered_project_context(tmp_path):
    project = make_node_project(tmp_path / "app")
    run_dir = tmp_path / "run"
    plan_for(project, run_dir)
    context_path = run_dir / "project-context.json"
    context = json.loads(context_path.read_text(encoding="utf-8"))
    context["languages"] = ["made-up-language"]
    context_path.write_text(json.dumps(context), encoding="utf-8")
    args = orchestrator.build_parser().parse_args([
        "execute", "--run-dir", str(run_dir), "--approve",
    ])
    with pytest.raises(orchestrator.OrchestratorError, match="context changed"):
        orchestrator.execute_run(args)


def test_mixed_language_manifests_in_one_directory_are_rejected(tmp_path):
    project = make_node_project(tmp_path / "mixed")
    (project / "pyproject.toml").write_text(
        "[project]\nname = \"mixed\"\nversion = \"0.1.0\"\n",
        encoding="utf-8",
    )
    with pytest.raises(orchestrator.OrchestratorError, match="Multiple language manifest groups"):
        orchestrator.scan_project(project)



def test_output_preflight_prevents_partial_multi_skill_generation(tmp_path):
    project = make_node_project(tmp_path / "app")
    existing = project / "Dockerfile"
    existing.write_text("FROM scratch\n", encoding="utf-8")
    run_dir = tmp_path / "run"
    plan_for(project, run_dir)
    args = orchestrator.build_parser().parse_args([
        "execute", "--run-dir", str(run_dir), "--approve",
    ])

    with pytest.raises(orchestrator.OrchestratorError, match="No specialist was executed"):
        orchestrator.execute_run(args)

    assert existing.read_text(encoding="utf-8") == "FROM scratch\n"
    assert not (project / ".dockerignore").exists()
    assert not (project / ".github" / "workflows" / "pipeline.yml").exists()
    assert not (project / "PIPELINE_NOTES.md").exists()



def test_cli_plan_and_execute_commands_work_end_to_end(tmp_path):
    project = make_node_project(tmp_path / "cli-app")
    run_dir = tmp_path / "cli-run"
    planned = subprocess.run(
        [
            sys.executable, str(SCRIPT), "plan",
            "--project", str(project),
            "--goal", "Verify documented CLI commands",
            "--skills", "app-containerizer",
            "--run-dir", str(run_dir),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert planned.returncode == 0, planned.stderr
    plan_payload = json.loads(planned.stdout)
    assert plan_payload["approval_required"] is True
    assert Path(plan_payload["plan"]).is_file()

    executed = subprocess.run(
        [
            sys.executable, str(SCRIPT), "execute",
            "--run-dir", str(run_dir),
            "--approve",
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert executed.returncode == 0, executed.stderr + executed.stdout
    receipt = json.loads(executed.stdout)
    assert receipt["status"] == "completed"
    assert receipt["skill"] == "cloud-engineering-orchestrator"
    assert receipt["artifact_count"] >= 2
    assert receipt["report"] == str(run_dir / "execution-report.json")
    assert receipt["checks"]["PASS"] > 0
    full_report_text = Path(receipt["report"]).read_text(encoding="utf-8")
    full_report = json.loads(full_report_text)
    assert len(executed.stdout) < len(full_report_text)
    assert full_report["overwrite_approved"] is False
    assert full_report["skill_reports"]["app-containerizer"]["status"] == "completed"
    assert (project / "Dockerfile").is_file()



def test_dependency_graph_is_explicit_and_topologically_ordered(tmp_path):
    project = make_node_project(tmp_path / "app")
    run_dir = tmp_path / "run"
    plan = plan_for(project, run_dir, "cicd-pipeline-creator,app-containerizer")
    assert plan["execution_order"] == ["app-containerizer", "cicd-pipeline-creator"]
    assert plan["dependencies"] == {
        "app-containerizer": [],
        "cicd-pipeline-creator": ["app-containerizer"],
    }
    handoff = json.loads(
        (run_dir / "handoffs" / "cicd-pipeline-creator" / "handoff.json").read_text(encoding="utf-8")
    )
    assert handoff["depends_on"] == ["app-containerizer"]


def test_project_context_cache_reuses_only_matching_snapshot(tmp_path):
    project = make_node_project(tmp_path / "cache-app")
    first_info = {}
    first = orchestrator.scan_project(project, cache_info=first_info)
    assert first_info["status"] == "miss"
    second_info = {}
    second = orchestrator.scan_project(project, cache_info=second_info)
    assert second_info["status"] == "hit"
    assert second["snapshot_hash"] == first["snapshot_hash"]

    (project / "server.js").write_text('console.log("cache invalidation");\\n', encoding="utf-8")
    third_info = {}
    third = orchestrator.scan_project(project, cache_info=third_info)
    assert third_info["status"] == "miss"
    assert third["snapshot_hash"] != first["snapshot_hash"]


def test_failed_prerequisite_blocks_dependants_and_rolls_back_all_outputs(tmp_path, monkeypatch):
    project = make_node_project(tmp_path / "rollback-app")
    existing_dockerfile = project / "Dockerfile"
    existing_dockerfile.write_text("FROM scratch\\n", encoding="utf-8")
    run_dir = tmp_path / "rollback-run"
    plan_for(project, run_dir)
    args = orchestrator.build_parser().parse_args([
        "execute", "--run-dir", str(run_dir), "--approve", "--overwrite",
    ])
    invoked = []

    def fake_execute_skill(skill, handoff, current_run_dir, overwrite):
        invoked.append(skill)
        assert overwrite is True
        (project / "Dockerfile").write_text("FROM node:latest\\n", encoding="utf-8")
        (project / ".dockerignore").write_text(".env\\n", encoding="utf-8")
        return {
            "status": "failed",
            "artifacts": [],
            "checks": [{"name": "forced-failure", "status": "FAIL", "detail": "simulated partial write"}],
            "assumptions": [],
            "risks": [],
            "manual_actions": [],
        }

    monkeypatch.setattr(orchestrator, "execute_skill", fake_execute_skill)
    report = orchestrator.execute_run(args)
    assert invoked == ["app-containerizer"]
    assert report["transaction"]["status"] == "rolled_back"
    assert existing_dockerfile.read_text(encoding="utf-8") == "FROM scratch\\n"
    assert not (project / ".dockerignore").exists()
    assert not (project / ".github" / "workflows").exists()
    assert report["skill_reports"]["cicd-pipeline-creator"]["status"] == "blocked"
    assert report["artifacts"] == []


def test_runtime_json_schema_validation_rejects_invalid_handoff():
    with pytest.raises(orchestrator.OrchestratorError, match="Invalid skill handoff"):
        orchestrator.validate_payload(
            "skill-handoff.schema.json",
            {"schema_version": "1.1", "skill": "unknown"},
            "skill handoff",
        )



def test_execution_lock_rejects_a_second_active_runner(tmp_path):
    run_dir = tmp_path / "locked-run"
    with orchestrator.ExecutionLock(run_dir):
        with pytest.raises(orchestrator.OrchestratorError, match="holds the execution lock"):
            orchestrator.ExecutionLock(run_dir).acquire()


def test_execution_lock_releases_after_context_exit(tmp_path):
    run_dir = tmp_path / "lock-release"
    with orchestrator.ExecutionLock(run_dir):
        pass
    with orchestrator.ExecutionLock(run_dir):
        pass


def test_recover_restores_outputs_after_simulated_process_crash(tmp_path):
    project = make_node_project(tmp_path / "crash-app")
    dockerfile = project / "Dockerfile"
    dockerfile.write_text("FROM scratch\n", encoding="utf-8")
    run_dir = tmp_path / "crash-run"
    plan = plan_for(project, run_dir)
    state = orchestrator.create_run_state(plan)
    orchestrator.write_run_state(run_dir, state)

    transaction = orchestrator.OutputTransaction(
        orchestrator.transaction_targets(plan, run_dir), run_dir, state
    )
    transaction.begin()
    transaction.mark_running()
    dockerfile.write_text("FROM node:latest\n", encoding="utf-8")
    (project / ".dockerignore").write_text(".env\n", encoding="utf-8")
    (project / ".github" / "workflows").mkdir(parents=True)
    (project / ".github" / "workflows" / "pipeline.yml").write_text("bad: true\n", encoding="utf-8")
    state["status"] = "running"
    state["current_skill"] = "app-containerizer"
    orchestrator.write_run_state(run_dir, state)

    args = orchestrator.build_parser().parse_args([
        "recover", "--run-dir", str(run_dir), "--approve",
    ])
    recovered = orchestrator.recover_run(args)
    assert recovered["status"] == "interrupted"
    assert recovered["transaction"]["phase"] == "rolled_back"
    assert dockerfile.read_text(encoding="utf-8") == "FROM scratch\n"
    assert not (project / ".dockerignore").exists()
    assert not (project / ".github" / "workflows").exists()
    assert not (run_dir / orchestrator.TRANSACTION_DIR).exists()


def test_resume_recovers_crash_then_restarts_all_skills_from_clean_state(tmp_path, monkeypatch):
    project = make_node_project(tmp_path / "resume-app")
    original = project / "Dockerfile"
    original.write_text("FROM scratch\n", encoding="utf-8")
    run_dir = tmp_path / "resume-run"
    plan = plan_for(project, run_dir)
    state = orchestrator.create_run_state(plan)
    orchestrator.write_run_state(run_dir, state)
    tx = orchestrator.OutputTransaction(orchestrator.transaction_targets(plan, run_dir), run_dir, state)
    tx.begin()
    tx.mark_running()
    original.write_text("PARTIAL WRITE\n", encoding="utf-8")
    (project / ".dockerignore").write_text("PARTIAL\n", encoding="utf-8")
    state["status"] = "running"
    state["current_skill"] = "app-containerizer"
    orchestrator.write_run_state(run_dir, state)

    executed = []

    def successful_skill(skill, handoff, current_run_dir, overwrite):
        executed.append(skill)
        if skill == "app-containerizer":
            assert original.read_text(encoding="utf-8") == "FROM scratch\n"
            original.write_text("FROM node:22\n", encoding="utf-8")
            (project / ".dockerignore").write_text(".env\n", encoding="utf-8")
        else:
            assert original.read_text(encoding="utf-8") == "FROM node:22\n"
            pipeline = project / ".github" / "workflows" / "pipeline.yml"
            pipeline.parent.mkdir(parents=True, exist_ok=True)
            pipeline.write_text("name: generated\n", encoding="utf-8")
            (project / "PIPELINE_NOTES.md").write_text("notes\n", encoding="utf-8")
        return {
            "status": "completed",
            "artifacts": [],
            "checks": [{"name": f"{skill}-test", "status": "PASS", "detail": "ok"}],
            "assumptions": [],
            "risks": [],
            "manual_actions": [],
        }

    monkeypatch.setattr(orchestrator, "execute_skill", successful_skill)
    args = orchestrator.build_parser().parse_args([
        "resume", "--run-dir", str(run_dir), "--approve", "--overwrite",
    ])
    report = orchestrator.resume_run(args)
    assert executed == ["app-containerizer", "cicd-pipeline-creator"]
    assert report["status"] == "completed"
    assert report["transaction"]["status"] == "committed"
    final_state = orchestrator.read_run_state(run_dir)
    assert final_state["attempt"] == 1
    assert final_state["status"] == "completed"
    assert final_state["completed_skills"] == ["app-containerizer", "cicd-pipeline-creator"]
    assert not (run_dir / orchestrator.TRANSACTION_DIR).exists()


def test_resume_rejects_a_tampered_or_mismatched_journal(tmp_path):
    project = make_node_project(tmp_path / "tamper-journal")
    run_dir = tmp_path / "tamper-run"
    plan_for(project, run_dir)
    plan = json.loads((run_dir / "execution-plan.json").read_text(encoding="utf-8"))
    state = orchestrator.create_run_state(plan)
    state["run_id"] = "00000000-0000-0000-0000-000000000000"
    orchestrator.write_run_state(run_dir, state)
    args = orchestrator.build_parser().parse_args([
        "resume", "--run-dir", str(run_dir), "--approve",
    ])
    with pytest.raises(orchestrator.OrchestratorError, match="does not match this plan"):
        orchestrator.resume_run(args)



def test_resume_does_not_require_overwrite_for_interrupted_generated_files(tmp_path, monkeypatch):
    project = make_node_project(tmp_path / "resume-new-app")
    run_dir = tmp_path / "resume-new-run"
    plan = plan_for(project, run_dir)
    state = orchestrator.create_run_state(plan)
    orchestrator.write_run_state(run_dir, state)
    tx = orchestrator.OutputTransaction(orchestrator.transaction_targets(plan, run_dir), run_dir, state)
    tx.begin()
    tx.mark_running()
    (project / "Dockerfile").write_text("INTERRUPTED\n", encoding="utf-8")
    (project / ".dockerignore").write_text("INTERRUPTED\n", encoding="utf-8")
    state["status"] = "running"
    orchestrator.write_run_state(run_dir, state)

    def successful_skill(skill, handoff, current_run_dir, overwrite):
        assert overwrite is False
        if skill == "app-containerizer":
            (project / "Dockerfile").write_text("FROM node:22\n", encoding="utf-8")
            (project / ".dockerignore").write_text(".env\n", encoding="utf-8")
        else:
            pipeline = project / ".github" / "workflows" / "pipeline.yml"
            pipeline.parent.mkdir(parents=True, exist_ok=True)
            pipeline.write_text("name: generated\n", encoding="utf-8")
            (project / "PIPELINE_NOTES.md").write_text("notes\n", encoding="utf-8")
        return {
            "status": "completed", "artifacts": [],
            "checks": [{"name": "resume-test", "status": "PASS", "detail": "ok"}],
            "assumptions": [], "risks": [], "manual_actions": [],
        }

    monkeypatch.setattr(orchestrator, "execute_skill", successful_skill)
    args = orchestrator.build_parser().parse_args([
        "resume", "--run-dir", str(run_dir), "--approve",
    ])
    report = orchestrator.resume_run(args)
    assert report["status"] == "completed"
    assert (project / "Dockerfile").read_text(encoding="utf-8") == "FROM node:22\n"


def test_project_lock_serializes_distinct_run_directories(tmp_path):
    project = make_node_project(tmp_path / "shared-project")
    first_run = tmp_path / "run-a"
    second_run = tmp_path / "run-b"
    assert first_run != second_run

    first = orchestrator.project_execution_lock(project)
    second = orchestrator.project_execution_lock(project)

    with first:
        with pytest.raises(orchestrator.OrchestratorError, match="Another orchestrator process holds"):
            with second:
                pass

    # The OS lock is released even though the persistent lock file remains.
    with second:
        pass


def test_project_lock_directory_rejects_symlinked_state_directory(tmp_path):
    project = make_node_project(tmp_path / "symlink-project")
    real_state = tmp_path / "real-state"
    real_state.mkdir()
    link = project / ".cloud-agent"
    try:
        link.symlink_to(real_state, target_is_directory=True)
    except (OSError, NotImplementedError):
        pytest.skip("Directory symlinks are unavailable on this runner.")

    with pytest.raises(orchestrator.OrchestratorError, match="must not be symlinks"):
        orchestrator.project_execution_lock(project)



def test_auto_plan_writes_architecture_and_selection_contracts(tmp_path):
    project = make_node_project(tmp_path / "auto-app")
    run_dir = tmp_path / "auto-run"
    args = orchestrator.build_parser().parse_args([
        "plan",
        "--project", str(project),
        "--goal", "Dockerize this application",
        "--skills", "auto",
        "--run-dir", str(run_dir),
    ])

    plan = orchestrator.create_plan(args)
    profile = json.loads((run_dir / "architecture-profile.json").read_text(encoding="utf-8"))
    selection = json.loads((run_dir / "skill-selection.json").read_text(encoding="utf-8"))
    handoff = json.loads(
        (run_dir / "handoffs" / "app-containerizer" / "handoff.json").read_text(encoding="utf-8")
    )

    assert plan["selected_skills"] == ["app-containerizer"]
    assert plan["intelligence"]["selection_mode"] == "auto"
    assert plan["project"]["architecture"] == "monolith"
    assert plan["project"]["confidence"] == profile["confidence"]
    assert selection["selected_skills"] == ["app-containerizer"]
    assert handoff["architecture_profile"]["file"] == str(run_dir / "architecture-profile.json")
