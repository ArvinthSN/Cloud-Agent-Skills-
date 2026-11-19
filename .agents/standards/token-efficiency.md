# Token-efficient context policy

Reduce irrelevant context without omitting facts required for correctness or safety. This policy is mandatory for every specialist and the orchestrator.

## Progressive disclosure

1. Read only the selected skill's `SKILL.md`.
2. Inspect the smallest authoritative inputs first: manifests, lockfiles, entry points, deployment configuration and explicitly selected files.
3. Load only the reference section needed for the detected stack, provider or platform. Never preload every reference.
4. Reuse validated project context and handoffs. Do not repeat discovery in downstream skills unless the context is stale, incomplete, invalid or the user changes scope.
5. Read source files only to resolve a specific uncertainty. Prefer a bounded excerpt with a path and line range over a whole-file dump.

## Context budget

- Keep the initial project summary to: stack/framework, runtime, package manager, entry point, build/test/start commands, database/services, target platform/provider, confidence and unknowns.
- Keep lists to the smallest relevant set. Default to at most 20 paths/findings in human-facing output; include an omitted count when truncated.
- Never include source code, lockfile contents, full dependency trees, full logs or environment values in a handoff.
- Use structured JSON handoffs as the canonical machine context. Pass paths, hashes and concise detected facts, not copied source text.
- Do not restate the same project facts in every skill response.
- When a command writes a report to a file, return a compact receipt (status, report path and key counts) rather than printing the entire report again.
- Keep normal completion output to: outcome, artifact paths, validation summary, warnings and manual actions. Put detailed diagnostics in report/log files and print only the relevant failure excerpt.

## Scan boundaries

Exclude by default:
- VCS metadata (.git);
- dependency trees (node_modules, .venv, venv, vendor folders);
- caches and bytecode (__pycache__, .pytest_cache, .mypy_cache);
- build output (dist, build, target, coverage output);
- Terraform state, plans and .terraform;
- binaries, secrets files and files above a configurable size threshold.

Never follow symlinks outside the selected repository root. Never read secret values. Environment variable names may be reported only when useful; redact values.

## Determinism and caching

- Prefer deterministic scripts for scanning, rendering, schema validation and static checks. Use the LLM for interpretation, ambiguity resolution and explaining trade-offs—not for repeating deterministic work.
- A cached project summary is reusable only when it identifies the canonical repository root, content/revision fingerprint, scanner version, schema version and relevant project paths.
- Re-scan when the project fingerprint, selected subproject, scanner version or relevant manifests change. Do not treat an unversioned summary as authoritative.
- Use one scan per project run. A downstream skill must consume the validated handoff rather than rescan.

## Safe output discipline

- Do not reduce or omit approval gates, secret checks, security controls, validation evidence or failure details needed to resolve a blocker.
- Never claim a check passed if it was skipped or unavailable. Use PASS, FAIL, WARNING, SKIPPED or NOT_RUN.
- Do not suppress uncertainty to make a response shorter. Record unknowns and ask only for information that blocks safe progress.
- Prefer concise explanations with links/paths to generated artifacts; expand only when the user asks or a failure needs diagnosis.
