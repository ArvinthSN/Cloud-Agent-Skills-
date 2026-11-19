import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "render_pipeline.py"
EXAMPLES = ROOT / "examples"


def run(*args):
    return subprocess.run(
        [sys.executable, str(SCRIPT), *map(str, args)],
        capture_output=True,
        text=True,
    )


def test_monorepo_requires_explicit_project_selection(tmp_path):
    result = run(EXAMPLES / "monorepo", "github", "--out", tmp_path)
    assert result.returncode != 0
    assert "--project-dir" in result.stderr + result.stdout
    assert not (tmp_path / "pipeline.yml").exists()


def test_existing_generated_pipeline_is_preserved_without_overwrite(tmp_path):
    example = EXAMPLES / "node-service"
    first = run(example, "github", "--out", tmp_path)
    assert first.returncode == 0, first.stderr + first.stdout
    target = tmp_path / "pipeline.yml"
    original = target.read_text(encoding="utf-8")
    second = run(example, "github", "--out", tmp_path)
    assert second.returncode != 0
    assert "Existing output preserved" in second.stderr + second.stdout
    assert target.read_text(encoding="utf-8") == original

def test_no_tests_pipeline_contains_explicit_fail_or_override_guard(tmp_path):
    example = EXAMPLES / "no-tests"
    result = run(example, "github", "--out", tmp_path)
    assert result.returncode == 0, result.stderr + result.stdout
    pipeline = (tmp_path / "pipeline.yml").read_text(encoding="utf-8")
    assert "NO_TESTS_DETECTED" in pipeline
    assert "ALLOW_NO_TESTS" in pipeline
    assert "No tests detected" in pipeline



def test_java_stack_is_rejected_by_current_renderer(tmp_path):
    project = tmp_path / "java-app"
    project.mkdir()
    (project / "pom.xml").write_text(
        "<project><modelVersion>4.0.0</modelVersion></project>",
        encoding="utf-8",
    )
    out = tmp_path / "out"
    result = run(project, "github", "--out", out)
    assert result.returncode != 0
    assert "supports Python and Node.js only" in result.stderr + result.stdout
    assert not (out / "pipeline.yml").exists()


def test_project_without_real_build_is_rejected(tmp_path):
    project = tmp_path / "no-build"
    project.mkdir()
    (project / "package.json").write_text(
        '{"name":"no-build","scripts":{"start":"node server.js"}}',
        encoding="utf-8",
    )
    (project / "package-lock.json").write_text(
        '{"name":"no-build","lockfileVersion":3,"requires":true,"packages":{"":{"name":"no-build","version":"1.0.0"}}}',
        encoding="utf-8",
    )
    (project / "server.js").write_text('console.log("ready");\n', encoding="utf-8")
    out = tmp_path / "out"
    result = run(project, "github", "--out", out)
    assert result.returncode != 0
    assert "artifact-producing build" in result.stderr + result.stdout
    assert not (out / "pipeline.yml").exists()



def test_python_package_project_is_installed_for_tests(tmp_path):
    project = tmp_path / "python-app"
    project.mkdir()
    (project / "pyproject.toml").write_text(
        "[build-system]\nrequires = [\"setuptools\"]\nbuild-backend = \"setuptools.build_meta\"\n"
        "[project]\nname = \"python-app\"\nversion = \"0.1.0\"\n",
        encoding="utf-8",
    )
    (project / "requirements.txt").write_text("pytest==8.3.3\n", encoding="utf-8")
    tests = project / "tests"
    tests.mkdir()
    (tests / "test_app.py").write_text("def test_sample():\n    assert True\n", encoding="utf-8")
    out = tmp_path / "out"
    result = run(project, "github", "--out", out)
    assert result.returncode == 0, result.stderr + result.stdout
    pipeline = (out / "pipeline.yml").read_text(encoding="utf-8")
    assert "python -m pip install ." in pipeline
    assert "python -m build --outdir dist" in pipeline


def test_pnpm_project_is_rejected_until_renderer_supports_it(tmp_path):
    project = tmp_path / "pnpm-app"
    project.mkdir()
    (project / "package.json").write_text(
        '{"name":"pnpm-app","scripts":{"build":"node build.js","start":"node server.js"}}',
        encoding="utf-8",
    )
    (project / "pnpm-lock.yaml").write_text("lockfileVersion: '9.0'\n", encoding="utf-8")
    (project / "build.js").write_text('require("fs").mkdirSync("dist", {recursive:true});\n', encoding="utf-8")
    (project / "server.js").write_text('console.log("ready");\n', encoding="utf-8")
    out = tmp_path / "out"
    result = run(project, "github", "--out", out)
    assert result.returncode != 0
    assert "requires npm and package-lock.json" in result.stderr + result.stdout
    assert not (out / "pipeline.yml").exists()



def test_precomputed_orchestrator_context_skips_repository_discovery(tmp_path):
    import json

    project = tmp_path / "empty-project"
    project.mkdir()
    context = tmp_path / "ci-context.json"
    context.write_text(
        json.dumps({
            "ci_project": {
                "dir": ".",
                "lang": "node",
                "pm": "npm",
                "install": "npm ci",
                "build": "npm run build",
                "test": "npm test",
                "version": "20",
                "lockfile": "package-lock.json",
                "has_tests": True,
            }
        }),
        encoding="utf-8",
    )
    out = tmp_path / "out"
    result = run(project, "github", "--out", out, "--context", context)
    assert result.returncode == 0, result.stderr + result.stdout
    rendered = (out / "pipeline.yml").read_text(encoding="utf-8")
    assert "npm ci" in rendered
    assert "npm run build" in rendered


def test_all_five_platforms_render_and_pass_static_validation(tmp_path):
    outputs = {
        "github": "pipeline.yml",
        "azure": "azure-pipeline.yml",
        "gitlab": ".gitlab-ci.yml",
        "jenkins": "Jenkinsfile",
        "circleci": ".circleci/config.yml",
    }
    example = EXAMPLES / "node-service"
    for platform, relative_output in outputs.items():
        target_dir = tmp_path / platform
        result = run(example, platform, "--out", target_dir)
        assert result.returncode == 0, result.stderr + result.stdout
        pipeline = target_dir / relative_output
        assert pipeline.is_file(), f"{platform} output missing: {pipeline}"
        text = pipeline.read_text(encoding="utf-8")
        assert "@@" not in text
        assert "npm ci" in text
        assert "node build.js" in text
        checked = subprocess.run(
            [sys.executable, str(ROOT / "scripts" / "validate_pipeline.py"), str(pipeline), "--json"],
            capture_output=True,
            text=True,
        )
        assert checked.returncode in {0, 2}, checked.stdout + checked.stderr
        assert '"status": "fail"' not in checked.stdout


def test_renderer_rejects_newline_in_shell_command(tmp_path):
    import json

    project = tmp_path / "newline-command"
    project.mkdir()
    context = tmp_path / "context.json"
    context.write_text(
        json.dumps({
            "ci_project": {
                "dir": ".",
                "lang": "node",
                "pm": "npm",
                "install": "npm ci",
                "build": "npm run build\necho injected",
                "test": "npm test",
                "version": "20",
                "lockfile": "package-lock.json",
                "has_tests": True,
            }
        }),
        encoding="utf-8",
    )
    result = run(project, "gitlab", "--out", tmp_path / "out", "--context", context)
    assert result.returncode != 0
    assert "Unsafe or oversized build command" in result.stderr + result.stdout


def test_renderer_rejects_unsafe_working_directory(tmp_path):
    import json

    project = tmp_path / "unsafe-path"
    project.mkdir()
    context = tmp_path / "context.json"
    context.write_text(
        json.dumps({
            "ci_project": {
                "dir": "../escape",
                "lang": "node",
                "pm": "npm",
                "install": "npm ci",
                "build": "npm run build",
                "test": "npm test",
                "version": "20",
                "lockfile": "package-lock.json",
                "has_tests": True,
            }
        }),
        encoding="utf-8",
    )
    result = run(project, "jenkins", "--out", tmp_path / "out", "--context", context)
    assert result.returncode != 0
    assert "Unsafe project working directory" in result.stderr + result.stdout
