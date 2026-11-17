# Base Image Selection
Suggested starting points; verify current support and project compatibility before production:
- Python: `python:3.12-slim`
- Node.js: `node:22-bookworm-slim`
- Java runtime: `eclipse-temurin:21-jre`

Respect project runtime declarations such as `.python-version`, `runtime.txt`, `engines`, Maven/Gradle toolchains and documentation. Avoid silently upgrading major versions. Pin patch versions or digests according to organizational policy.
