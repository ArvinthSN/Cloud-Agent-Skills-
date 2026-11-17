---
name: cloud-engineering-orchestrator
description: Coordinate application containerization, CI/CD pipeline creation and Terraform planning using shared project context, approval gates and consistent execution reports.
---

# Cloud Engineering Orchestrator

## Purpose
Plan and coordinate cloud-engineering skills for one application repository without repeating discovery or bypassing approvals.

## Use when
The user requests an end-to-end cloud setup, a coordinated workflow across multiple cloud skills, or asks to run the Cloud Agent Skills harness. Use a specialist skill directly for one isolated deliverable.

## Inputs
- Application repository path (required).
- Desired outcome and constraints (required).
- Cloud provider and CI/CD platform (optional; ask only if a safe choice cannot be inferred).
- Output directory (optional; choose a clearly named directory under the repository only after approval).

## Workflow
1. Read this skill and the shared skill, output and token-efficiency contracts.
2. Inspect the repository once. Exclude VCS, dependency, cache, generated, binary and oversized files.
3. Produce an execution plan conforming to the execution-plan schema.
4. Select only necessary specialist skills: app-containerizer for Docker/Compose, infra-creator for Terraform, cicd-pipeline-creator for CI/CD.
5. Load selected SKILL.md files; load only references relevant to the selected stack, provider and platform.
6. Reuse project facts. Re-scan only when the target differs, the handoff is invalid/stale or a required fact is missing.
7. Present the combined plan, assumptions, files to be written and external actions. Obtain approval before writing/replacing files, provisioning, deploying or publishing.
8. Execute in dependency order. Do not assume an artifact exists unless its producing skill reports it.
9. Validate outputs and create a combined report conforming to the execution-report schema.
10. Summarize artifact paths, executed checks, warnings, risks and manual actions.

## Handoffs
- Use one project context and one report per skill.
- Refer to artifacts by path; do not embed full files in handoffs.
- Pass only facts required by the next skill.
- Do not duplicate scans or validators without a reason.
- Reject malformed or unsupported handoffs rather than guessing.

## Safety
- Planning does not authorize file writes.
- Never run Terraform apply/destroy, deploy, publish images, modify cloud accounts or push commits implicitly.
- Never ask for or expose secret values.
- Preserve existing files. Require explicit overwrite approval.
- Stop if deployment target, resource scope or permissions are ambiguous.
- Report unavailable tools as NOT_RUN, never PASS.

## Completion
Return a concise summary and structured execution report. Local generation does not mean a pipeline ran, infrastructure was provisioned or an application was deployed.
