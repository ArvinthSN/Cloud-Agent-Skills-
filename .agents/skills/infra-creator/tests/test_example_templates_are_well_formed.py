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

def test_example_dockerfiles_run_as_non_root():
    paths = (
        SKILL_ROOT / "examples" / "microservices" / "services" / "api" / "Dockerfile",
        SKILL_ROOT / "examples" / "microservices" / "services" / "worker" / "Dockerfile",
        SKILL_ROOT / "examples" / "nodejs-webapp" / "Dockerfile",
        SKILL_ROOT / "examples" / "python-fastapi" / "Dockerfile",
    )
    for path in paths:
        assert "USER app" in path.read_text(encoding="utf-8")


def test_provider_templates_use_restrictive_network_defaults():
    aws_compute = (
        SKILL_ROOT / "templates" / "aws" / "compute" / "container" / "main.tf"
    ).read_text(encoding="utf-8")
    aws_variables = (
        SKILL_ROOT / "templates" / "aws" / "compute" / "container" / "variables.tf"
    ).read_text(encoding="utf-8")
    aws_network = (
        SKILL_ROOT / "templates" / "aws" / "networking" / "network" / "main.tf"
    ).read_text(encoding="utf-8")
    aws_database = (
        SKILL_ROOT / "templates" / "aws" / "database" / "sql" / "main.tf"
    ).read_text(encoding="utf-8")
    azure_network = (
        SKILL_ROOT / "templates" / "azure" / "networking" / "network" / "main.tf"
    ).read_text(encoding="utf-8")
    gcp_sql = (
        SKILL_ROOT / "templates" / "gcp" / "database" / "sql" / "main.tf"
    ).read_text(encoding="utf-8")

    assert "internal           = var.internal" in aws_compute
    assert 'default = true' in aws_variables
    assert "drop_invalid_header_fields = true" in aws_compute
    assert 'cidr_blocks = ["0.0.0.0/0"]' not in aws_compute
    assert 'cidr_blocks = ["0.0.0.0/0"]' not in aws_database
    assert "map_public_ip_on_launch = false" in aws_network
    assert "publicly_accessible     = false" in aws_database
    assert 'source_address_prefix      = var.vnet_cidr' in azure_network
    assert 'ssl_mode        = "ENCRYPTED_ONLY"' in gcp_sql
