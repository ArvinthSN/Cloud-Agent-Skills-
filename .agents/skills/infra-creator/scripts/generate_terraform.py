#!/usr/bin/env python3
"""
Multi-cloud Terraform generator for infra-creator.
Supports --provider aws | azure | gcp.
"""

from __future__ import annotations

import argparse
import json
import logging
import re
import shutil
import sys
import textwrap
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger("generate_terraform")

SKILL_ROOT = Path(__file__).resolve().parent.parent
TEMPLATES = SKILL_ROOT / "templates"
SUPPORTED_PROVIDERS = ("aws", "azure", "gcp")


@dataclass
class InfraPlan:
    provider: str
    architecture: str
    needs_network: bool = True
    needs_compute: bool = True
    needs_database: bool = False
    needs_registry: bool = False
    needs_load_balancer: bool = False
    needs_cache: bool = False
    db_engine: str = "postgres"
    compute_type: str = "container"  # container | serverless | vm
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "provider": self.provider,
            "architecture": self.architecture,
            "needs_network": self.needs_network,
            "needs_compute": self.needs_compute,
            "needs_database": self.needs_database,
            "needs_registry": self.needs_registry,
            "needs_load_balancer": self.needs_load_balancer,
            "needs_cache": self.needs_cache,
            "db_engine": self.db_engine,
            "compute_type": self.compute_type,
            "notes": self.notes,
        }


def build_plan(scan: dict[str, Any], arch: dict[str, Any], provider: str) -> InfraPlan:
    architecture = arch.get("architecture", "monolithic")
    plan = InfraPlan(provider=provider, architecture=architecture)

    databases = [d.lower() for d in (scan.get("databases") or [])]
    has_docker = bool(scan.get("has_dockerfile"))
    env_vars = [v.upper() for v in (scan.get("env_var_names") or [])]

    if architecture == "serverless" or any(
        x in env_vars for x in ("AWS_LAMBDA", "LAMBDA_TASK_ROOT", "K_SERVICE", "FUNCTIONS_WORKER_RUNTIME")
    ):
        plan.compute_type = "serverless"
        plan.needs_load_balancer = False
        plan.needs_registry = False
        plan.notes.append("Serverless signals → managed functions / Cloud Run style compute")
    elif has_docker or architecture in ("microservices", "hybrid"):
        plan.compute_type = "container"
        plan.needs_registry = True
        plan.needs_load_balancer = True
        plan.notes.append("Container signals → container platform + registry + load balancer")
    else:
        plan.compute_type = "container"
        plan.needs_registry = True
        plan.needs_load_balancer = True
        plan.notes.append("Defaulting to container platform for modern deployment")

    if any(d in databases for d in ("postgresql", "mysql", "sqlite")) or any(
        "DATABASE_URL" in v or v.startswith("DB_") for v in env_vars
    ):
        plan.needs_database = True
        plan.db_engine = "mysql" if "mysql" in databases else "postgres"
        plan.notes.append(f"Database detected → managed relational DB ({plan.db_engine})")

    if "redis" in databases or any("REDIS" in v for v in env_vars):
        plan.needs_cache = True
        plan.notes.append("Redis/cache signals present")

    if plan.compute_type == "serverless" and not plan.needs_database:
        plan.needs_network = False
        plan.notes.append("Pure serverless without DB → dedicated network optional")

    return plan


def _copy_module(src: Path, dest: Path, *, overwrite: bool = False) -> None:
    """Copy a module without deleting user data unless overwrite is explicit."""
    if not src.is_dir():
        raise FileNotFoundError(f"Template module not found: {src}")
    if dest.exists():
        if not overwrite:
            raise FileExistsError(
                f"Module directory already exists: {dest}. "
                "Choose a new output directory or explicitly enable overwrite."
            )
        shutil.rmtree(dest)
    shutil.copytree(src, dest)


def _write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    cleaned = textwrap.dedent(content).strip() + "\n"
    path.write_text(cleaned, encoding="utf-8")
    logger.info("Wrote %s", path)


def _provider_block(provider: str, region_var: str) -> str:
    if provider == "aws":
        return f"""
        provider "aws" {{
          region = var.{region_var}

          default_tags {{
            tags = {{
              Project     = var.project_name
              Environment = var.environment
              ManagedBy   = "terraform"
            }}
          }}
        }}
        """
    if provider == "azure":
        return f"""
        provider "azurerm" {{
          features {{}}
        }}
        """
    # gcp
    return f"""
        provider "google" {{
          project = var.project_id
          region  = var.{region_var}
        }}
        """


def _versions_block(provider: str, project_name: str, region: str) -> str:
    if provider == "aws":
        return f"""
        terraform {{
          required_version = ">= 1.5.0"
          required_providers {{
            aws = {{
              source  = "hashicorp/aws"
              version = "~> 5.0"
            }}
          }}
          # backend "s3" {{
          #   bucket         = "your-terraform-state-bucket"
          #   key            = "{project_name}/terraform.tfstate"
          #   region         = "{region}"
          #   dynamodb_table = "terraform-locks"
          #   encrypt        = true
          # }}
        }}
        """
    if provider == "azure":
        return f"""
        terraform {{
          required_version = ">= 1.5.0"
          required_providers {{
            azurerm = {{
              source  = "hashicorp/azurerm"
              version = "~> 3.0"
            }}
          }}
          # backend "azurerm" {{
          #   resource_group_name  = "tfstate-rg"
          #   storage_account_name = "tfstateacct"
          #   container_name       = "tfstate"
          #   key                  = "{project_name}.tfstate"
          # }}
        }}
        """
    return f"""
        terraform {{
          required_version = ">= 1.5.0"
          required_providers {{
            google = {{
              source  = "hashicorp/google"
              version = "~> 5.0"
            }}
          }}
          # backend "gcs" {{
          #   bucket = "your-terraform-state-bucket"
          #   prefix = "{project_name}"
          # }}
        }}
        """


def _variables_block(provider: str, project_name: str, region: str) -> str:
    common = f"""
        variable "project_name" {{
          description = "Name of the project used for resource naming"
          type        = string
          default     = "{project_name}"
        }}

        variable "environment" {{
          description = "Deployment environment (dev, staging, prod)"
          type        = string
          default     = "dev"
        }}
        """
    if provider == "aws":
        return common + f"""
        variable "aws_region" {{
          description = "AWS region"
          type        = string
          default     = "{region}"
        }}

        variable "vpc_cidr" {{
          description = "CIDR block for the VPC"
          type        = string
          default     = "10.0.0.0/16"
        }}

        variable "container_port" {{
          type    = number
          default = 8000
        }}

        variable "desired_count" {{
          type    = number
          default = 2
        }}

        variable "db_username" {{
          type      = string
          default   = "appadmin"
          sensitive = true
        }}

        variable "db_password" {{
          description = "Database password supplied through TF_VAR_db_password or an approved secret workflow"
          type        = string
          sensitive   = true
        }}
        """
    if provider == "azure":
        return common + f"""
        variable "location" {{
          description = "Azure region"
          type        = string
          default     = "{region}"
        }}

        variable "vnet_cidr" {{
          type    = string
          default = "10.0.0.0/16"
        }}

        variable "container_port" {{
          type    = number
          default = 8000
        }}

        variable "db_username" {{
          type      = string
          default   = "appadmin"
          sensitive = true
        }}

        variable "db_password" {{
          type      = string
          sensitive = true
          default   = ""
        }}
        """
    # gcp
    return common + f"""
        variable "project_id" {{
          description = "GCP project ID"
          type        = string
        }}

        variable "region" {{
          description = "GCP region"
          type        = string
          default     = "{region}"
        }}

        variable "network_cidr" {{
          type    = string
          default = "10.0.0.0/16"
        }}

        variable "container_port" {{
          type    = number
          default = 8000
        }}

        variable "db_username" {{
          type      = string
          default   = "appadmin"
          sensitive = true
        }}

        variable "db_password" {{
          type      = string
          sensitive = true
          default   = ""
        }}
        """


def generate_project(
    output_dir: Path,
    plan: InfraPlan,
    project_name: str = "app",
    region: str | None = None,
    *,
    overwrite: bool = False,
) -> None:
    provider = plan.provider
    if provider not in SUPPORTED_PROVIDERS:
        raise ValueError(f"Unsupported provider: {provider}")
    if not re.fullmatch(r"[a-z][a-z0-9-]{0,30}", project_name):
        raise ValueError("project_name must start with a lowercase letter and contain only lowercase letters, digits or hyphens (max 31 chars).")
    if plan.needs_database and plan.db_engine not in {"postgres", "mysql"}:
        raise ValueError(f"Unsupported database engine: {plan.db_engine}")

    defaults = {"aws": "us-east-1", "azure": "eastus", "gcp": "us-central1"}
    region = region or defaults[provider]
    if not re.fullmatch(r"[A-Za-z0-9-]{2,40}", region):
        raise ValueError(f"Invalid region value: {region}")

    output_dir = output_dir.resolve()
    if plan.compute_type == "serverless":
        raise ValueError(
            "Serverless generation is not implemented yet. "
            "The current templates are container-focused; do not generate a container module for a serverless plan."
        )
    if plan.needs_compute and not plan.needs_network:
        raise ValueError(
            "The selected compute templates require networking, but the plan disables networking. "
            "Revise the plan or select a supported network-attached architecture."
        )
    if plan.needs_database and not plan.needs_network:
        raise ValueError("The selected database templates require a networking module.")
    if provider == "aws" and plan.needs_database and not plan.needs_compute:
        raise ValueError("The AWS database template requires the compute module security group.")
    if output_dir.exists():
        existing = [p.name for p in output_dir.iterdir()]
        if existing and not overwrite:
            raise FileExistsError(
                f"Output directory is not empty: {output_dir}. "
                "Choose a new directory or pass --overwrite after reviewing existing files."
            )
    output_dir.mkdir(parents=True, exist_ok=True)
    modules_dir = output_dir / "modules"
    modules_dir.mkdir(parents=True, exist_ok=True)
    tmpl = TEMPLATES / provider

    if plan.needs_network:
        _copy_module(tmpl / "networking" / "network", modules_dir / "networking", overwrite=overwrite)
    if plan.needs_compute:
        _copy_module(tmpl / "compute" / "container", modules_dir / "compute", overwrite=overwrite)
    if plan.needs_database:
        _copy_module(tmpl / "database" / "sql", modules_dir / "database", overwrite=overwrite)

    _write(output_dir / "versions.tf", _versions_block(provider, project_name, region))
    region_var = "aws_region" if provider == "aws" else ("location" if provider == "azure" else "region")
    _write(output_dir / "providers.tf", _provider_block(provider, region_var))
    _write(output_dir / "variables.tf", _variables_block(provider, project_name, region))

    # main.tf
    parts: list[str] = [
        """
        locals {
          name_prefix = "${var.project_name}-${var.environment}"
        }
        """
    ]

    if provider == "aws":
        if plan.needs_network:
            parts.append(
                """
                module "networking" {
                  source      = "./modules/networking"
                  name_prefix = local.name_prefix
                  vpc_cidr    = var.vpc_cidr
                  environment = var.environment
                }
                """
            )
        if plan.needs_compute:
            parts.append(
                """
                module "compute" {
                  source             = "./modules/compute"
                  name_prefix        = local.name_prefix
                  environment        = var.environment
                  vpc_id             = module.networking.vpc_id
                  private_subnet_ids = module.networking.private_subnet_ids
                  public_subnet_ids  = module.networking.public_subnet_ids
                  container_port     = var.container_port
                  desired_count      = var.desired_count
                }
                """
            )
        if plan.needs_database:
            parts.append(
                f"""
                module "database" {{
                  source                     = "./modules/database"
                  name_prefix                = local.name_prefix
                  environment                = var.environment
                  vpc_id                     = module.networking.vpc_id
                  private_subnet_ids         = module.networking.private_subnet_ids
                  db_engine                  = "{plan.db_engine}"
                  db_username                = var.db_username
                  db_password                = var.db_password
                  allowed_security_group_ids = [module.compute.ecs_security_group_id]
                }}
                """
            )
    elif provider == "azure":
        if plan.needs_network:
            parts.append(
                """
                module "networking" {
                  source      = "./modules/networking"
                  name_prefix = local.name_prefix
                  location    = var.location
                  vnet_cidr   = var.vnet_cidr
                  environment = var.environment
                }
                """
            )
        if plan.needs_compute:
            parts.append(
                """
                module "compute" {
                  source         = "./modules/compute"
                  name_prefix    = local.name_prefix
                  location       = var.location
                  environment    = var.environment
                  subnet_id      = module.networking.app_subnet_id
                  container_port = var.container_port
                }
                """
            )
        if plan.needs_database:
            parts.append(
                f"""
                module "database" {{
                  source      = "./modules/database"
                  name_prefix = local.name_prefix
                  location    = var.location
                  environment = var.environment
                  subnet_id   = module.networking.data_subnet_id
                  db_engine   = "{plan.db_engine}"
                  db_username = var.db_username
                  db_password = var.db_password
                }}
                """
            )
    else:  # gcp
        if plan.needs_network:
            parts.append(
                """
                module "networking" {
                  source      = "./modules/networking"
                  name_prefix = local.name_prefix
                  project_id  = var.project_id
                  region      = var.region
                  network_cidr = var.network_cidr
                  environment = var.environment
                }
                """
            )
        if plan.needs_compute:
            parts.append(
                """
                module "compute" {
                  source         = "./modules/compute"
                  name_prefix    = local.name_prefix
                  project_id     = var.project_id
                  region         = var.region
                  environment    = var.environment
                  network_id     = module.networking.network_id
                  subnet_id      = module.networking.subnet_id
                  container_port = var.container_port
                }
                """
            )
        if plan.needs_database:
            parts.append(
                f"""
                module "database" {{
                  source      = "./modules/database"
                  name_prefix = local.name_prefix
                  project_id  = var.project_id
                  region      = var.region
                  environment = var.environment
                  network_id  = module.networking.network_id
                  db_engine   = "{plan.db_engine}"
                  db_username = var.db_username
                  db_password = var.db_password
                }}
                """
            )

    main_body = "\n\n".join(textwrap.dedent(p).strip() for p in parts)
    _write(output_dir / "main.tf", main_body)

    # outputs
    outs = [
        """
        output "name_prefix" {
          value = local.name_prefix
        }
        """
    ]
    if provider == "aws" and plan.needs_compute:
        outs.append(
            """
            output "alb_dns_name" {
              value = try(module.compute.alb_dns_name, null)
            }
            output "ecr_repository_url" {
              value = try(module.compute.ecr_repository_url, null)
            }
            """
        )
    if provider == "azure" and plan.needs_compute:
        outs.append(
            """
            output "container_app_fqdn" {
              value = try(module.compute.fqdn, null)
            }
            """
        )
    if provider == "gcp" and plan.needs_compute:
        outs.append(
            """
            output "cloud_run_url" {
              value = try(module.compute.service_url, null)
            }
            """
        )
    if plan.needs_database:
        outs.append(
            """
            output "database_endpoint" {
              value     = try(module.database.endpoint, null)
              sensitive = true
            }
            """
        )
    _write(output_dir / "outputs.tf", "\n\n".join(textwrap.dedent(o).strip() for o in outs))

    # tfvars example
    if provider == "aws":
        tfvars = f"""
        project_name   = "{project_name}"
        environment    = "dev"
        aws_region     = "{region}"
        vpc_cidr       = "10.0.0.0/16"
        container_port = 8000
        desired_count  = 2
        db_username    = "appadmin"
        # db_password  = ""  # set via TF_VAR_db_password
        """
    elif provider == "azure":
        tfvars = f"""
        project_name   = "{project_name}"
        environment    = "dev"
        location       = "{region}"
        vnet_cidr      = "10.0.0.0/16"
        container_port = 8000
        db_username    = "appadmin"
        # db_password  = ""
        """
    else:
        tfvars = f"""
        project_name   = "{project_name}"
        environment    = "dev"
        project_id     = "your-gcp-project-id"
        region         = "{region}"
        network_cidr   = "10.0.0.0/16"
        container_port = 8000
        db_username    = "appadmin"
        # db_password  = ""
        """
    _write(output_dir / "terraform.tfvars.example", tfvars)

    for env in ("dev", "staging", "prod"):
        env_dir = output_dir / "environments" / env
        env_dir.mkdir(parents=True, exist_ok=True)
        _write(env_dir / "terraform.tfvars", f'environment = "{env}"\n')

    plan_notes = "\n".join(f"- {n}" for n in plan.notes) or "- Baseline container platform"
    _write(
        output_dir / "README.md",
        f"""
        # Infrastructure – {project_name}

        Generated by **infra-creator** for **{provider.upper()}**.
        Architecture: `{plan.architecture}`.

        ## Plan Notes

        {plan_notes}

        ## Prerequisites

        - Terraform >= 1.5
        - Authenticated CLI for {provider.upper()}
        - Permissions to create network, compute, and database resources

        ## Quick Start

        ```bash
        cd infra
        terraform init
        terraform fmt
        terraform validate
        terraform plan -var-file=environments/dev/terraform.tfvars
        # Review carefully, then:
        terraform apply -var-file=environments/dev/terraform.tfvars
        ```

        ## Security

        - Never commit state files or secrets.
        - Databases are not publicly accessible by default.
        - Use secret stores for passwords in real deployments.
        - Prefer remote state for shared environments.

        ## Destroy

        ```bash
        terraform destroy -var-file=environments/dev/terraform.tfvars
        ```
        """,
    )
    logger.info("Terraform project (%s) generated at %s", provider, output_dir)


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate multi-cloud Terraform from scan + architecture")
    parser.add_argument("--scan", required=True)
    parser.add_argument("--arch", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--provider", choices=SUPPORTED_PROVIDERS, default="aws")
    parser.add_argument("--project-name", default="app")
    parser.add_argument("--region", default=None)
    parser.add_argument("--plan-only", action="store_true")
    parser.add_argument("--approve", action="store_true", help="Required to write generated Terraform files")
    parser.add_argument("--overwrite", action="store_true", help="Allow replacement of files in a non-empty output directory")
    args = parser.parse_args()

    try:
        scan = json.loads(Path(args.scan).read_text(encoding="utf-8"))
        arch = json.loads(Path(args.arch).read_text(encoding="utf-8"))
        plan = build_plan(scan, arch, args.provider)
        print(json.dumps(plan.to_dict(), indent=2))
        if args.plan_only:
            return 0
        if not args.approve:
            raise PermissionError("No files written. Re-run with --approve after reviewing the plan.")
        generate_project(
            Path(args.output),
            plan,
            project_name=args.project_name,
            region=args.region,
            overwrite=args.overwrite,
        )
    except Exception as exc:
        logger.error("%s", exc)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())