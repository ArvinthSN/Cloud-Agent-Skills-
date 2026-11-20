"""Bounded, approval-gated repair planning. This module never edits project files."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

TRANSIENT_MARKERS = (
    "timed out", "timeout", "temporarily unavailable", "temporary failure",
    "connection reset", "service unavailable", "rate limit", "http 429",
    "http 502", "http 503", "http 504",
)
NEVER_RETRY_MARKERS = (
    "security", "gitleaks", "trivy", "checkov", "secret", "credential",
    "policy", "terraform-security",
)


def build_repair_plan(
    execution_report: dict[str, Any],
    *,
    max_attempts: int = 1,
    attempts_used: int = 0,
) -> dict[str, Any]:
    if not 0 <= max_attempts <= 2:
        raise ValueError("max_attempts must be between 0 and 2")
    if not 0 <= attempts_used <= max_attempts:
        raise ValueError("attempts_used must be between 0 and max_attempts")

    failures = [item for item in execution_report.get("checks", []) if item.get("status") == "FAIL"]
    proposals = []
    escalations = []
    for item in failures:
        name = str(item.get("name", "unknown"))
        detail = str(item.get("detail", ""))
        identity = (name + " " + detail).casefold()
        if any(marker in identity for marker in NEVER_RETRY_MARKERS):
            escalations.append({"check": name, "reason": "Security or policy findings require human review; automatic retry is prohibited."})
        elif any(marker in identity for marker in TRANSIENT_MARKERS) and attempts_used < max_attempts:
            proposals.append({
                "check": name,
                "action": "retry_same_step_once",
                "reason": "The failure matches an allow-listed transient infrastructure/tool condition.",
                "requires_approval": True,
                "must_rerun_verification": True,
            })
        else:
            escalations.append({
                "check": name,
                "reason": "Failure is not classified as safely retryable or the retry budget is exhausted.",
            })

    if not failures:
        status = "no_repair_needed"
    elif proposals and not escalations:
        status = "approval_required"
    elif proposals:
        status = "partial_escalation"
    else:
        status = "escalate"

    return {
        "schema_version": "1.0",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "status": status,
        "policy": {
            "max_attempts": max_attempts,
            "attempts_used": attempts_used,
            "attempts_remaining": max_attempts - attempts_used,
            "automatic_file_mutation": False,
            "security_failures_retryable": False,
        },
        "proposals": proposals,
        "escalations": escalations,
        "message": "This is a bounded repair plan, not an execution. Review and approve any repair, then rerun the orchestrator and verification.",
    }
