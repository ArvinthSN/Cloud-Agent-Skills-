# Shared execution output contract

The structured report is the canonical handoff between skills. Human-facing summaries may be shorter, but must not contradict it.

## Status vocabulary

- completed: requested local work completed; validation may still contain warnings.
- blocked: a required input, approval or dependency is missing.
- failed: an attempted operation failed.
- partial: some outputs completed, others did not.
- not_started: no generation or mutation was attempted.

## Check vocabulary

Each check uses one of:
- PASS — tool ran and the check passed.
- FAIL — tool ran and found a blocking issue.
- WARNING — tool ran and found a non-blocking concern.
- SKIPPED — intentionally not run due to scope or policy.
- NOT_RUN — could not run because a tool, credential or environment was unavailable.

Unavailable checks must never be reported as PASS.

## Artifact reporting

For each artifact include:
- repository-relative path where possible;
- artifact type;
- action (created, updated, preserved);
- brief purpose.

Do not include secret values, credentials, full environment contents or large source excerpts.

## Concise default response

Default human response:
1. outcome and status;
2. generated/changed artifact paths;
3. validation summary;
4. warnings and required manual actions.

Provide detailed logs or rationale only when requested or needed to resolve a failure.
