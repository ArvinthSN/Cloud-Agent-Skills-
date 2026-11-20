# Phase 3 benchmark harness

This directory contains a deterministic evaluation harness for the Cloud Agent Skills. The checked-in dataset defines 20 representative scenarios across containerization, CI/CD, infrastructure and end-to-end workflows. It is a benchmark specification, **not a claim that the skills have already passed 20 real repositories**.

## Prepare a benchmark workspace

Create one directory per case ID. Put generated artifacts at their expected relative paths. The complete case list and artifact contract live in dataset.json.

Example:

~~~text
benchmark-workspace/
  python-fastapi/
    Dockerfile
  cicd-python/
    .github/workflows/pipeline.yml
  infra-aws/
    infra/main.tf
~~~

Only include repositories that you are authorized to inspect. The harness does not clone or execute third-party repositories, Dockerfiles, Terraform, CI workflows or generated scripts.

## Run

~~~bash
python benchmarks/scripts/benchmark.py --validate-only
python benchmarks/scripts/benchmark.py --workspace ./benchmark-workspace --output ./benchmark-report.json
~~~

Exit codes: 0 all cases complete without mandatory failures, 1 one or more cases fail, 2 invalid dataset or runtime input error.

## Scoring

| Dimension | Weight | Evaluation |
|---|---:|---|
| Correctness | 30% | Expected signals found in generated artifacts |
| Completeness | 25% | Required artifacts exist and are readable |
| Security | 25% | Forbidden patterns fail; warning patterns reduce the score |
| Reproducibility | 10% | Two externally measured artifact digests match |
| Efficiency | 10% | Recorded generation time against a documented 30s–300s scale |

Unmeasured reproducibility and efficiency are excluded from the weighted average and reported as unmeasured; they are never silently treated as passing. Efficiency metadata uses elapsed_seconds. Reproducibility metadata uses first_run_sha256 and second_run_sha256 in benchmark-metadata.json.

## Interpreting results

- status is a hard gate: missing required artifacts or a forbidden security pattern fails the case.
- weighted_score is calculated only over measured dimensions and measured_weight_percent shows how much of the rubric was actually measured.
- Review per-case findings; an aggregate score must not hide a critical security failure.
- Run against a versioned, reviewed corpus of real repositories before using scores as a release claim. Keep dataset version, skill commit, runtime versions and raw reports together for comparison.
