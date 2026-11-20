from pathlib import Path

SKILL_ROOT = Path(__file__).resolve().parents[1]


def test_azure_network_outputs_have_one_block_per_line():
    outputs = (
        SKILL_ROOT / "templates" / "azure" / "networking" / "network" / "outputs.tf"
    ).read_text(encoding="utf-8")

    assert "}output" not in outputs
    assert outputs.count('output "') == 5
    assert outputs.endswith("\n")


def test_microservice_example_dockerfiles_use_real_line_endings():
    for service in ("api", "worker"):
        dockerfile = (
            SKILL_ROOT / "examples" / "microservices" / "services" / service / "Dockerfile"
        ).read_text(encoding="utf-8")

        assert r"\n" not in dockerfile
        assert dockerfile.count("\n") >= 3
        assert dockerfile.startswith("FROM python:3.12-slim\n")
