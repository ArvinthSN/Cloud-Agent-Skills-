# Shared skill contract

All specialist skills follow this contract. Keep each top-level SKILL.md short; put detailed provider, framework and platform knowledge in references.

## Frontmatter

Each skill declares:
- name: stable kebab-case identifier.
- description: concise trigger and outcome; do not duplicate the whole workflow.

## Invocation contract

A skill defines:
1. Purpose — one sentence describing the outcome.
2. When to use / not use — explicit boundaries.
3. Inputs — required and optional inputs, including defaults.
4. Outputs — files and structured report fields.
5. Workflow — ordered, bounded steps.
6. Approval gates — actions requiring explicit user authorization.
7. Validation — tools, exit meanings and unavailable-tool behavior.
8. Failure behavior — stop conditions, cleanup and partial-output reporting.

## Execution rules

- Inspect before modifying.
- Treat detection as heuristic unless backed by authoritative project configuration.
- Never invent a runtime version, deploy target, cloud resource, command or credential.
- Preserve unknown values as unknown; do not silently substitute echo commands or fake success.
- Keep generation deterministic for the same inputs and template revision.
- Write only inside the requested output directory.
- Refuse to overwrite existing files unless the user explicitly opts in.
- Keep tool invocations scoped to the current task.
- Do not deploy, provision, push images or run destructive commands as an implicit step.

## Context handoff

Pass facts through the execution-plan and execution-report schemas. A receiving skill consumes the handoff rather than re-scanning unless:
- the requested project directory differs;
- the handoff is missing, stale or invalid;
- the user changed requirements after the handoff;
- the receiving skill needs a fact not collected previously.

## Completion

A skill is complete only when it reports:
- status and skill name;
- relevant detected facts;
- artifacts created or updated;
- checks actually executed and their outcomes;
- assumptions, warnings and unresolved risks;
- manual actions still required.

Never label generation alone as validation, or validation alone as deployment.
