"""Deterministic architecture profiling, requirement resolution and skill selection.

This module intentionally uses repository evidence and explicit rules. It does not
invent deployment providers, CI platforms or missing application requirements.
"""
from __future__ import annotations

import re
from statistics import mean
from typing import Any

PROFILE_SCHEMA_VERSION = "1.0"
SUPPORTED_SKILLS = {
    "app-containerizer",
    "cicd-pipeline-creator",
    "infra-creator",
}
SUPPORTED_CONTAINER_LANGUAGES = {"python", "node", "java"}
FRONTEND_FRAMEWORKS = {"react", "vue", "nextjs", "angular"}
BACKEND_FRAMEWORKS = {"fastapi", "flask", "django", "express", "nestjs", "spring", "gin"}
GOAL_INTENTS = {
    "app-containerizer": re.compile(r"\b(container|containerize|docker|image build)\b", re.I),
    "cicd-pipeline-creator": re.compile(r"\b(ci/?cd|pipeline|github actions|gitlab ci|jenkins|circleci|azure pipeline)\b", re.I),
    "infra-creator": re.compile(r"\b(terraform|infrastructure|infra|cloud resources|provision)\b", re.I),
}


def _component_confidence(project: dict[str, Any]) -> tuple[float, list[str]]:
    evidence = [f"manifest:{project.get('manifest', 'unknown')}"]
    score = 0.78
    if project.get("framework") and project["framework"] != "unknown":
        score += 0.17
        evidence.append(f"framework:{project['framework']}")
    if project.get("entry_point") and project["entry_point"] != "unknown":
        score += 0.03
        evidence.append(f"entry-point:{project['entry_point']}")
    if project.get("lockfile"):
        score += 0.02
        evidence.append(f"lockfile:{project['lockfile']}")
    return min(score, 0.99), evidence


def build_architecture_profile(context: dict[str, Any]) -> dict[str, Any]:
    """Build a bounded architecture profile from the orchestrator's canonical scan."""
    projects = context.get("projects", [])
    components: list[dict[str, Any]] = []
    signals: list[str] = []
    uncertainties: list[str] = []

    for index, project in enumerate(projects):
        framework = str(project.get("framework", "unknown")).lower()
        language = str(project.get("language", "unknown")).lower()
        if framework in FRONTEND_FRAMEWORKS:
            component_type = "frontend"
        elif framework in BACKEND_FRAMEWORKS or language in {"python", "java", "go", "node"}:
            component_type = "backend"
        else:
            component_type = "unknown"
        confidence, evidence = _component_confidence(project)
        if component_type == "unknown":
            confidence = min(confidence, 0.55)
            uncertainties.append(f"Could not classify application component at '{project.get('dir', '.')}'; review its role.")
        components.append({
            "id": f"application-{index + 1}",
            "type": component_type,
            "technology": framework if framework != "unknown" else language,
            "project_dir": project.get("dir", "."),
            "confidence": round(confidence, 2),
            "evidence": evidence[:6],
        })
        signals.append(f"Application manifest found at '{project.get('dir', '.')}/{project.get('manifest', '')}'.")

    for database in context.get("databases", []):
        components.append({
            "id": f"data-store-{database}",
            "type": "data_store",
            "technology": database,
            "project_dir": ".",
            "confidence": 0.78,
            "evidence": [f"dependency-or-source-marker:{database}"],
        })

    app_components = [item for item in components if item["type"] != "data_store"]
    frontends = [item for item in app_components if item["type"] == "frontend"]
    backends = [item for item in app_components if item["type"] == "backend"]
    service_dirs = context.get("service_dirs", [])

    if len(backends) > 1 or len(service_dirs) >= 3:
        architecture = "microservices"
        signals.append("Multiple backend projects or service directories were detected.")
    elif frontends and backends:
        architecture = "frontend_backend"
        signals.append("Both frontend and backend application components were detected.")
    elif len(app_components) == 1:
        architecture = "monolith"
        signals.append("One application project manifest was detected.")
    elif len(app_components) > 1:
        architecture = "multi_project"
        signals.append("Multiple application projects were detected; service boundaries are not conclusive.")
        uncertainties.append("Multiple projects do not automatically imply independently deployable microservices.")
    else:
        architecture = "unknown"
        uncertainties.append("No supported application manifest was detected.")

    component_scores = [item["confidence"] for item in app_components]
    if component_scores:
        confidence = mean(component_scores)
        if architecture in {"microservices", "frontend_backend"}:
            confidence *= 0.92
        elif architecture in {"multi_project", "unknown"}:
            confidence *= 0.72
    else:
        confidence = 0.0

    if context.get("scan_truncated"):
        confidence = 0.0
        uncertainties.append("Repository scan was truncated; architecture confidence is invalid.")
    if len(context.get("projects", [])) > 1:
        uncertainties.append("Select an application with --project-dir before generating application-specific artifacts.")

    return {
        "schema_version": PROFILE_SCHEMA_VERSION,
        "project_root": context["root"],
        "snapshot_hash": context["snapshot_hash"],
        "architecture": architecture,
        "confidence": round(max(0.0, min(confidence, 1.0)), 2),
        "project_count": len(projects),
        "components": components[:40],
        "signals": signals[:30],
        "uncertainties": uncertainties[:20],
    }


def _skill_requirements(
    skill: str,
    *,
    goal: str,
    profile: dict[str, Any],
    context: dict[str, Any],
    provider: str | None,
    platform: str | None,
    project_dir: str | None,
) -> list[str]:
    missing: list[str] = []
    projects = context.get("projects", [])
    selected = next((item for item in projects if item.get("dir") == (project_dir or ".")), None)

    if skill in {"app-containerizer", "cicd-pipeline-creator"}:
        if not projects:
            missing.append("supported_application_manifest")
        elif len(projects) > 1 and not project_dir:
            missing.append("project_dir")
        elif selected is None and project_dir:
            missing.append("valid_project_dir")
        elif selected:
            if skill == "app-containerizer" and selected.get("language") not in SUPPORTED_CONTAINER_LANGUAGES:
                missing.append("supported_container_stack")
            if skill == "cicd-pipeline-creator":
                if selected.get("ci_lang") not in {"python", "node"}:
                    missing.append("supported_ci_stack")
                if not selected.get("install_command") or not selected.get("build_command"):
                    missing.append("install_and_build_commands")
                if selected.get("ci_lang") == "node" and (
                    selected.get("package_manager") != "npm" or selected.get("lockfile") != "package-lock.json"
                ):
                    missing.append("npm_package_lock")
    if skill == "infra-creator" and not provider:
        missing.append("cloud_provider")
    if skill == "cicd-pipeline-creator" and not platform:
        missing.append("ci_platform")
    return missing


def build_skill_selection(
    *,
    mode: str,
    goal: str,
    requested_skills: list[str],
    profile: dict[str, Any],
    context: dict[str, Any],
    provider: str | None,
    platform: str | None,
    project_dir: str | None,
) -> dict[str, Any]:
    """Resolve goal intent and prerequisites into an auditable skill-selection contract."""
    if mode not in {"explicit", "auto"}:
        raise ValueError(f"Unsupported selection mode: {mode}")
    if mode == "auto":
        candidates = [skill for skill, pattern in GOAL_INTENTS.items() if pattern.search(goal)]
    else:
        candidates = list(requested_skills)

    selected: list[str] = []
    blocked: list[dict[str, Any]] = []
    recommendations: list[dict[str, Any]] = []
    for skill in candidates:
        if skill not in SUPPORTED_SKILLS:
            blocked.append({"skill": skill, "missing_requirements": ["supported_skill_id"], "reason": "Unknown skill."})
            continue
        missing = _skill_requirements(
            skill, goal=goal, profile=profile, context=context,
            provider=provider, platform=platform, project_dir=project_dir,
        )
        ready = not missing
        reason = {
            "app-containerizer": "Containerization intent detected in the goal." if mode == "auto" else "Explicitly requested.",
            "cicd-pipeline-creator": "CI/CD pipeline intent detected in the goal." if mode == "auto" else "Explicitly requested.",
            "infra-creator": "Infrastructure intent detected in the goal." if mode == "auto" else "Explicitly requested.",
        }[skill]
        recommendations.append({
            "skill": skill,
            "ready": ready,
            "reason": reason,
            "missing_requirements": missing,
        })
        if ready or mode == "explicit":
            # Explicit mode preserves the user's requested set; blockers remain visible
            # and the orchestrator's existing validation gates still fail closed.
            selected.append(skill)
        if not ready:
            blocked.append({
                "skill": skill,
                "missing_requirements": missing,
                "reason": "Required inputs or supported project evidence are missing.",
            })

    if mode == "auto" and not candidates:
        blocked.append({
            "skill": "selection",
            "missing_requirements": ["goal_intent"],
            "reason": "The goal does not clearly request containerization, CI/CD or infrastructure generation.",
        })

    return {
        "schema_version": "1.0",
        "mode": mode,
        "goal": goal,
        "requested_skills": requested_skills,
        "selected_skills": selected,
        "recommendations": recommendations,
        "blocked": blocked,
        "unresolved_requirements": sorted({
            requirement
            for item in blocked
            for requirement in item["missing_requirements"]
        }),
        "architecture": profile["architecture"],
        "architecture_confidence": profile["confidence"],
        "project_snapshot_hash": context["snapshot_hash"],
    }
