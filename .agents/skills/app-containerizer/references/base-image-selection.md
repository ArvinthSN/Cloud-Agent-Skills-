# Base Image Selection
Suggested starting points; verify current support and project compatibility before production:
- Python: `python:3.12-slim`
- Node.js: `node:22-bookworm-slim`
- Java runtime: `eclipse-temurin:21-jre`

Respect project runtime declarations such as `.python-version`, `runtime.txt`, `engines`, Maven/Gradle toolchains and documentation. Avoid silently upgrading major versions. Pin patch versions or digests according to organizational policy.

## Python version selection

The containerizer reads the PEP 621 `project.requires-python` value or Poetry's Python constraint in `pyproject.toml`. For a lower-bounded range (for example, `>=3.14,<4.0`), it uses the lower bound for the image tag (`python:3.14-slim`) and records the full constraint and its source in the analysis plan. This avoids silently building on an older interpreter than the project declares. When no supported constraint is found, the scanner uses Python 3.12 as a clearly marked fallback; reviewers should confirm it against the application's CI/runtime policy.

## Java and Gradle version selection

For Gradle projects, the scanner reads the Java toolchain/source compatibility from the root build file and the Gradle distribution version from `gradle/wrapper/gradle-wrapper.properties`. The generated builder image combines those versions (for example, `gradle:9.5.1-jdk17`); the runtime image uses the matching Temurin JRE. If wrapper metadata is absent, the generator uses Gradle 8.14 as a fallback, which must be reviewed against the project plugins.
