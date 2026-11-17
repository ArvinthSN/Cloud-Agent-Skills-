# Security Guidelines (All Clouds)

- No hardcoded credentials
- Databases not publicly accessible
- Least-privilege identity (IAM / RBAC / service accounts)
- Encrypt storage and transit where supported
- Secrets via cloud secret stores, not committed tfvars
- Never commit state files or production secrets
- Private networking for app and data tiers by default