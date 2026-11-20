"""Privacy-conscious optimization telemetry for orchestrated local runs."""
from __future__ import annotations

import json
import math
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def _json_chars(value: Any) -> int:
    return len(json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True))


def build_optimization_report(
    plan: dict[str, Any],
    execution_report: dict[str, Any],
    run_dir: Path,
    skill_durations: dict[str, float] | None = None,
) -> dict[str, Any]:
    """Build estimates from metadata only; never read generated artifact contents."""
    skill_durations = skill_durations or {}
    input_chars = 0
    for skill in plan.get("execution_order", []):
        handoff_path = run_dir / "handoffs" / skill / "handoff.json"
        if handoff_path.is_file() and not handoff_path.is_symlink():
            try:
                handoff = json.loads(handoff_path.read_text(encoding="utf-8"))
                input_chars += _json_chars(handoff)
            except (OSError, json.JSONDecodeError):
                continue

    artifact_metadata = execution_report.get("artifacts", [])
    output_chars = _json_chars(artifact_metadata)
    cache = plan.get("workflow", {}).get("context_cache", {})
    finished = execution_report.get("finished_at")
    started = execution_report.get("started_at")
    duration_seconds = None
    if isinstance(started, str) and isinstance(finished, str):
        try:
            begin = datetime.fromisoformat(started.replace("Z", "+00:00"))
            end = datetime.fromisoformat(finished.replace("Z", "+00:00"))
            duration_seconds = max(0.0, (end - begin).total_seconds())
        except ValueError:
            pass

    return {
        "schema_version": "1.0",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "duration_seconds": round(duration_seconds, 4) if duration_seconds is not None else None,
        "skill_durations_seconds": {
            name: round(max(0.0, value), 4) for name, value in sorted(skill_durations.items())
        },
        "context_cache": {
            "enabled": bool(cache.get("enabled", False)),
            "status": cache.get("status", "unknown"),
            "key": cache.get("key"),
        },
        "metadata_size": {
            "handoff_chars": input_chars,
            "artifact_metadata_chars": output_chars,
            "estimated_input_tokens": math.ceil(input_chars / 4),
            "estimated_output_tokens": math.ceil(output_chars / 4),
            "method": "serialized metadata characters divided by four; not provider token usage",
        },
        "counts": {
            "skills": len(execution_report.get("skill_reports", {})),
            "artifacts": len(artifact_metadata),
            "checks": len(execution_report.get("checks", [])),
        },
    }


def write_optimization_report(path: Path, payload: dict[str, Any]) -> None:
    """Atomically write telemetry without exposing source files or secret values."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=".telemetry-", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
            json.dump(payload, handle, indent=2, sort_keys=True)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)
