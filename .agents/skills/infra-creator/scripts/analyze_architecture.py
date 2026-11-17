#!/usr/bin/env python3
"""Architecture analyzer for infra-creator (cloud-agnostic)."""

from __future__ import annotations

import argparse
import json
import logging
import sys
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger("analyze_architecture")


@dataclass
class ArchitectureResult:
    architecture: str
    confidence: float
    evidence: list[str] = field(default_factory=list)
    secondary: list[str] = field(default_factory=list)
    uncertainty_notes: list[str] = field(default_factory=list)
    recommended_patterns: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def load_scan_report(source: str | Path | dict) -> dict[str, Any]:
    if isinstance(source, dict):
        return source
    path = Path(source)
    if path.is_file():
        return json.loads(path.read_text(encoding="utf-8"))
    raise ValueError(f"Cannot load scan report from {source}")


def score_monolithic(report: dict[str, Any]) -> tuple[float, list[str]]:
    score, evidence = 0.0, []
    service_dirs = report.get("service_dirs") or []
    langs = report.get("languages") or []
    top_dirs = report.get("top_level_dirs") or []
    has_compose = report.get("has_docker_compose", False)
    if len(service_dirs) <= 1:
        score += 0.35
        evidence.append("At most one service-like directory detected")
    if len(langs) == 1:
        score += 0.15
        evidence.append(f"Single primary language: {langs[0]}")
    if not has_compose:
        score += 0.1
        evidence.append("No docker-compose multi-service definition")
    if len(top_dirs) <= 5 and "services" not in top_dirs and "apps" not in top_dirs:
        score += 0.15
        evidence.append("Flat or simple top-level structure")
    if len(service_dirs) >= 3:
        score -= 0.3
    return max(0.0, min(1.0, score)), evidence


def score_microservices(report: dict[str, Any]) -> tuple[float, list[str]]:
    score, evidence = 0.0, []
    service_dirs = report.get("service_dirs") or []
    top_dirs = report.get("top_level_dirs") or []
    has_compose = report.get("has_docker_compose", False)
    docker_files = report.get("docker_files") or []
    langs = report.get("languages") or []
    if len(service_dirs) >= 2:
        score += 0.35
        evidence.append(f"Multiple service-like directories: {service_dirs}")
    if has_compose and len(docker_files) >= 2:
        score += 0.25
        evidence.append("docker-compose with multiple service definitions/files")
    if any(d in top_dirs for d in ("services", "apps", "microservices")):
        score += 0.15
        evidence.append("Top-level services/apps directory present")
    if len(langs) >= 2:
        score += 0.1
        evidence.append(f"Multiple languages: {langs}")
    if len(service_dirs) < 2 and not has_compose:
        score = min(score, 0.25)
        evidence.append("Insufficient independent service evidence")
    return max(0.0, min(1.0, score)), evidence


def score_serverless(report: dict[str, Any]) -> tuple[float, list[str]]:
    score, evidence = 0.0, []
    infra = " ".join(report.get("infra_files") or []).lower()
    env_vars = [v.upper() for v in (report.get("env_var_names") or [])]
    for m in ("serverless.yml", "serverless.yaml", "template.yaml", "sam.yaml", "cdk"):
        if m in infra:
            score += 0.4
            evidence.append(f"Serverless marker: {m}")
            break
    if any(h in env_vars for h in ("AWS_LAMBDA", "LAMBDA_TASK_ROOT", "FUNCTION_NAME", "K_SERVICE", "FUNCTIONS_WORKER_RUNTIME")):
        score += 0.2
        evidence.append("Serverless-related environment variables detected")
    if report.get("has_dockerfile") and "serverless" not in infra:
        score -= 0.1
    return max(0.0, min(1.0, score)), evidence


def score_event_driven(report: dict[str, Any]) -> tuple[float, list[str]]:
    score, evidence = 0.0, []
    signals = " ".join(
        (report.get("dependency_files") or [])
        + (report.get("infra_files") or [])
        + [v.upper() for v in (report.get("env_var_names") or [])]
        + (report.get("databases") or [])
    ).lower()
    for m in ("kafka", "rabbitmq", "sqs", "sns", "kinesis", "eventbridge", "pubsub", "servicebus", "celery", "bull"):
        if m in signals:
            score += 0.25
            evidence.append(f"Messaging/event signal: {m}")
    return max(0.0, min(1.0, score)), evidence


def analyze(report: dict[str, Any]) -> ArchitectureResult:
    scores = {
        "monolithic": score_monolithic(report),
        "microservices": score_microservices(report),
        "serverless": score_serverless(report),
        "event-driven": score_event_driven(report),
    }
    ranked = sorted(scores.items(), key=lambda x: x[1][0], reverse=True)
    primary_name, (primary_score, primary_evidence) = ranked[0]
    secondary = [n for n, (sc, _) in ranked[1:] if sc >= 0.35 and sc >= primary_score - 0.2]

    if primary_score >= 0.4 and any(scores[s][0] >= 0.4 for s in secondary):
        architecture = "hybrid"
        confidence = min(0.85, (primary_score + max(scores[s][0] for s in secondary)) / 2)
        evidence = primary_evidence + [f"Also strong signals for: {', '.join(secondary)}"]
        for s in secondary:
            evidence.extend(scores[s][1][:2])
        recommended = [primary_name] + secondary
    else:
        architecture = primary_name
        confidence = primary_score
        evidence = primary_evidence
        recommended = [architecture]

    notes = []
    if confidence < 0.45:
        notes.append(
            "Architecture confidence is low. Multiple folders alone do not indicate microservices. "
            "Please confirm the intended architecture."
        )
    return ArchitectureResult(
        architecture=architecture,
        confidence=round(confidence, 2),
        evidence=evidence,
        secondary=secondary if architecture != "hybrid" else [],
        uncertainty_notes=notes,
        recommended_patterns=recommended,
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Analyze repository architecture")
    parser.add_argument("report", help="Path to JSON scan report or '-' for stdin")
    parser.add_argument("--json", action="store_true")
    parser.add_argument("-o", "--output")
    args = parser.parse_args()
    try:
        data = json.load(sys.stdin) if args.report == "-" else load_scan_report(args.report)
        result = analyze(data)
    except Exception as exc:
        logger.error("%s", exc)
        return 1
    text = json.dumps(result.to_dict(), indent=2)
    if args.output:
        Path(args.output).write_text(text, encoding="utf-8")
        logger.info("Wrote analysis to %s", args.output)
    else:
        print(text)
    for n in result.uncertainty_notes:
        logger.warning("%s", n)
    return 0


if __name__ == "__main__":
    sys.exit(main())