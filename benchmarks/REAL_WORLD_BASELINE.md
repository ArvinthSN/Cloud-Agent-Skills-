# Real-World Benchmark Baseline

**Run:** [GitHub Actions run #44692660049](https://github.com/ArvinthSN/Cloud-Agent-Skills-/actions/runs/44692660049)  
**Artifact:** [Download generated reports and evidence](https://github.com/ArvinthSN/Cloud-Agent-Skills-/actions/runs/44692660049/artifacts/14609037859)  
**Baseline date:** 2026-11-20  
**Cloud Agent Skills revision:** `2e157d965180dfcf71482008bb18e914f868c038`

## Baseline result

| Measure | Result |
|---|---:|
| Weighted artifact score | **73.73 / 100** |
| Cases passed | **2 / 7** |
| Cases failed | **5 / 7** |
| Reproducibility | 100% for generated cases with two comparable runs |
| Efficiency | 100% under the harness's 30-second full-score threshold |

Weights: correctness 30%, completeness 25%, security 25%, reproducibility 10%, efficiency 10%.

This is a **real-world, rule-based artifact baseline**. It is not a runtime, performance, vulnerability, or production-readiness certification. The score incorporates the native/static validator result; a generated artifact that fails validation is scored as incorrect even when expected marker strings are present.

## Pinned open-source targets

| Repository | Pinned source commit | Tested capabilities |
|---|---|---|
| [spring-projects/spring-petclinic](https://github.com/spring-projects/spring-petclinic) | `500158f732419217507c7656904b8e6aa1bcc0d6` | Containerizer, infra creator, CI/CD detection |
| [fastapi/full-stack-fastapi-template](https://github.com/fastapi/full-stack-fastapi-template) | `77e550a73bb49dd2967622c5ed11bf7a49603c93` | Containerizer, CI/CD pipeline creator, infra creator |
| [onemoretechie/sample-web-app](https://github.com/onemoretechie/sample-web-app) | `bc504c906ffc5c0ba825ef1c2634260b1f2690aa` | Containerizer, infra creator, orchestrator, Java CI/CD compatibility |

## Case results

| Case | Result | Main evidence |
|---|---|---|
| Spring PetClinic — container | **FAIL** | Scanner selected `build.gradle` as the dependency manifest; Dockerfile generator rejected that path as unsupported/unsafe, so required outputs were not created |
| Spring PetClinic — AWS infra | **FAIL** | Terraform validation found invalid semicolon-separated variable block syntax |
| FastAPI full stack — container | **FAIL** | Generated Dockerfile missed the expected `python:3.14-slim` signal required by the repository's declared Python version |
| FastAPI full stack — GitHub Actions | **PASS** | Pipeline and notes generated; static validation passed; repeated output hashes matched |
| FastAPI full stack — AWS infra | **FAIL** | Terraform validation found invalid semicolon-separated variable block syntax |
| Spring sample web app — container | **PASS** | Dockerfile and .dockerignore generated; static validation passed; repeated output hashes matched |
| Spring sample web app — AWS infra | **FAIL** | Terraform validation found invalid semicolon-separated variable block syntax |

## Findings to fix

### 1. Terraform generation emits invalid HCL

All three AWS infrastructure cases generated files, but Terraform validation rejected variable blocks such as:

```hcl
variable "container_port" { type = number; default = 8000 }
variable "vpc_cidr" { type = string; default = "10.0.0.0/16" }
```

HCL does not allow semicolons to separate arguments in a block. The generator should emit valid multi-line blocks and add a regression test that runs `terraform fmt -check` and `terraform validate` on generated module trees.

### 2. Containerizer does not handle a dual Maven/Gradle repository

Spring PetClinic contains both `pom.xml` and `build.gradle`. The scanner selected `build.gradle`, but the Dockerfile generator rejected it. The scanner should resolve the build system deterministically or the generator should safely support Gradle manifests.

### 3. Python runtime version is not aligned with the FastAPI project

The FastAPI backend declares a Python 3.14 requirement, but the generated Dockerfile did not contain the expected Python 3.14 base-image signal. The scanner should derive the runtime version from authoritative project metadata and the generator should preserve it.

### 4. CI/CD project detection needs a dual-manifest edge case

For PetClinic, the pipeline renderer reported two project entries both named `.` because Maven and Gradle manifests share the same directory. It should deduplicate manifests by project directory and then report the Java stack as unsupported, rather than presenting duplicate project choices.

### 5. Java pipeline generation is not supported yet

The sample Spring Boot project was safely rejected with: `Unsupported pipeline stack: java. Renderer currently supports Python and Node.js only.` This is an expected fail-closed capability boundary, not a successful Java pipeline test.

## Orchestrator result

The orchestrator planning step completed for the Spring sample application. Execution failed during infrastructure verification and rolled back the transaction. The execution report recorded **0 committed artifacts**, 4 failed checks, 1 warning, 3 skipped checks, and 4 not-run checks. This is the intended fail-safe behavior when generated infrastructure does not validate.

## Safety and scope

- Public repositories were checked out at pinned commits; their source repositories were not modified.
- Only this project's scanners, analyzers, artifact generators, and static validators were run.
- Terraform fmt/init/validate ran in isolated temporary copies with the backend disabled.
- No target application code, project tests, package lifecycle scripts, or Dockerfile instructions were executed.
- No Docker build, Terraform plan/apply/destroy, cloud resource creation, image push, or deployment was performed.
- Optional checks not available in the runner remain unmeasured or not run; they are not counted as passes.

## How to reproduce

Run the workflow **Real-world Cloud Agent Skills baseline** or execute:

```bash
python -m pip install pyyaml jsonschema
python benchmarks/scripts/run_real_world.py --output-dir artifacts/real-world-baseline
```

The workflow uploads the full JSON report, source snapshots, generated artifacts, validator outputs, repeated-run hashes, and command logs as the `cloud-agent-skills-real-world-baseline` artifact.

## Baseline interpretation

**73.73/100 is the starting measured baseline for this exact pinned test suite and skill revision.** It should be retained unchanged as the comparison point. Fixes to the Terraform generator, dual-manifest detection, and Python runtime inference should be evaluated as a new benchmark run against the same pinned source commits.
