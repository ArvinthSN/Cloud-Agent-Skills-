# Containerization Standards
- Use explicit, supported runtime versions.
- Respect dependency lockfiles and use reproducible installs.
- Use multi-stage builds when build/runtime separation is beneficial.
- Minimize runtime packages and build context.
- Run as non-root where compatible.
- Externalize runtime configuration.
- Use exec-form startup commands.
- Add health checks only when a reliable check is known.
- Verify generated configuration with Docker when available; static checks do not prove runtime correctness.
