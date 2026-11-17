# Terraform Standards

- Provider selected via `--provider aws|azure|gcp`
- Modules under `templates/<provider>/{networking,compute,database}`
- Always emit versions.tf, providers.tf, variables.tf, outputs.tf, tfvars.example, environments/, README
- Sensitive vars marked `sensitive = true`
- Remote state commented as a reminder; not forced
- `terraform fmt` + `init -backend=false` + `validate` before handoff