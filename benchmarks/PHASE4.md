# Phase 4 — Optimization & Continuous Improvement

Phase 4 adds privacy-conscious telemetry, deterministic cache observability, bounded repair planning and a benchmark regression gate.

## Telemetry

Each orchestrator execution writes `telemetry.json` and adds a compact `optimization` summary to `execution-report.json`. It records elapsed time, per-skill duration, artifact/check counts and the existing deterministic project-context cache hit/miss state. Token counts are **metadata-size estimates** (serialized handoff/artifact metadata characters divided by four), not provider token billing or actual model token usage. Source files, generated artifact contents, environment values and credentials are not collected.

The existing project-context cache remains keyed by project root, scanner version and full repository snapshot hash. Use `plan --no-cache` to disable it; changed files or scanner versions invalidate the key.

## Bounded repair

Generate a repair plan after a failed run:

~~~bash
python .agents/skills/cloud-engineering-orchestrator/scripts/orchestrate.py repair-plan \
  --run-dir ./.cloud-agent/runs/my-app \
  --max-attempts 1 \
  --attempts-used 0
~~~

The controller proposes at most two retries across the entire execution run (one by default), not per failed check, and only for explicit transient tool/network failure markers. Security, secret and policy failures are never retryable. Unknown or deterministic validation failures escalate. The command writes `repair-plan.json`; it does not edit files, run shell commands, or bypass the existing approval, transaction and verification gates. After an approved repair/retry, run verification again.

## Benchmark regression gate

Compare a reviewed baseline report with a candidate report:

~~~bash
python benchmarks/scripts/regression_gate.py \
  --baseline ./benchmarks/baselines/approved.json \
  --current ./benchmark-report.json \
  --max-score-drop 3 \
  --max-correctness-drop 0 \
  --output ./regression-report.json
~~~

The gate fails on any security FAIL finding, a case changing from PASS to non-PASS, a correctness decline beyond the configured threshold, or an aggregate score drop beyond the configured threshold. Both reports must contain the same case IDs and valid finite correctness/aggregate scores from 0–100. Missing or malformed metrics/findings are rejected as invalid input (fail closed), rather than silently treated as no regression. Exit codes: 0 pass, 1 regression, 2 invalid inputs.

Do not commit an unreviewed or synthetic report as a production baseline. Establish a baseline from a versioned, authorized repository corpus and preserve the benchmark dataset, skill commit, runtime versions and reports together.
