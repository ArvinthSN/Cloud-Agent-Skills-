# Docker Security Guidelines
- Never copy `.env`, private keys, tokens or cloud credentials into an image.
- Never hardcode credentials in Dockerfile or Compose files.
- Prefer non-root runtime users.
- Pin maintained base-image versions and review provenance.
- Avoid privileged mode, host networking and Docker socket mounts by default.
- Do not publish database ports unless explicitly needed.
- Scan images and dependencies with organization-approved tools before production.
