from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.agents.models import AgentBudgetPolicy, AgentRun
from app.agents.schemas import AgentRunBudgetResponse


def budget_response_for_run(run: AgentRun) -> AgentRunBudgetResponse:
    snapshot = dict(run.budget_snapshot or {})
    limits = dict(snapshot.get("limits") or {})
    if not limits:
        limits = {key: snapshot[key] for key in AGENT_BUDGET_NUMERIC_KEYS if key in snapshot}
    usage = dict(snapshot.get("usage") or {})
    if not usage:
        usage = {
            "tool_calls": 0,
            "subagents": 0,
            "parallel_subagents": 0,
            "model_calls": 0,
            "case_candidates": 0,
            "source_chars_sent": 0,
            "wall_time_seconds": 0,
        }
    return AgentRunBudgetResponse(
        snapshot=snapshot,
        usage=usage,
        limits=limits,
    )


AGENT_BUDGET_NUMERIC_KEYS = {
    "max_tool_calls",
    "max_subagents",
    "max_parallel_subagents",
    "max_model_calls",
    "max_case_candidates_per_run",
    "max_wall_time_minutes",
    "max_total_source_chars_sent",
}


def _settings_budget_defaults(settings) -> dict[str, int]:
    return {
        "max_tool_calls": settings.agent_default_max_tool_calls,
        "max_subagents": settings.agent_default_max_subagents,
        "max_parallel_subagents": settings.agent_default_max_parallel_subagents,
        "max_model_calls": settings.agent_default_max_model_calls,
        "max_case_candidates_per_run": settings.agent_default_max_case_candidates_per_run,
        "max_wall_time_minutes": settings.agent_default_max_wall_time_minutes,
        "max_total_source_chars_sent": settings.agent_default_max_total_source_chars_sent,
    }


def _settings_budget_caps(settings) -> dict[str, int]:
    return {
        "max_tool_calls": settings.agent_system_max_tool_calls,
        "max_subagents": settings.agent_system_max_subagents,
        "max_parallel_subagents": settings.agent_system_max_parallel_subagents,
        "max_model_calls": settings.agent_system_max_model_calls,
        "max_case_candidates_per_run": settings.agent_system_max_case_candidates_per_run,
        "max_wall_time_minutes": settings.agent_system_max_wall_time_minutes,
        "max_total_source_chars_sent": settings.agent_system_max_total_source_chars_sent,
    }


def _sanitize_budget_values(values: dict[str, Any], hard_caps: dict[str, int]) -> dict[str, Any]:
    sanitized: dict[str, Any] = {}
    for key, value in values.items():
        if key in {"usage", "last_execute_request", "limits"}:
            continue
        if key in AGENT_BUDGET_NUMERIC_KEYS:
            try:
                numeric = max(0, int(value))
            except (TypeError, ValueError):
                continue
            sanitized[key] = min(numeric, hard_caps.get(key, numeric))
        else:
            sanitized[key] = value
    return sanitized


def _budget_policy_for_scope(
    db: Session,
    *,
    workspace_id: str,
    scope: str,
    project_id: str | None,
    purpose: str,
) -> AgentBudgetPolicy | None:
    statement = select(AgentBudgetPolicy).where(
        AgentBudgetPolicy.workspace_id == workspace_id,
        AgentBudgetPolicy.scope == scope,
        AgentBudgetPolicy.purpose == purpose,
    )
    if project_id:
        statement = statement.where(AgentBudgetPolicy.project_id == project_id)
    else:
        statement = statement.where(AgentBudgetPolicy.project_id.is_(None))
    return db.scalar(statement.order_by(AgentBudgetPolicy.updated_at.desc(), AgentBudgetPolicy.id.desc()))


def build_agent_run_budget_snapshot(
    db: Session,
    *,
    settings,
    workspace_id: str,
    project_id: str | None,
    override: dict[str, Any],
    purpose: str = "agent_run",
) -> dict[str, Any]:
    hard_caps = _settings_budget_caps(settings)
    snapshot: dict[str, Any] = dict(_settings_budget_defaults(settings))
    sources: list[dict[str, Any]] = [{"scope": "system_defaults", "keys": sorted(snapshot)}]

    workspace_policy = _budget_policy_for_scope(
        db,
        workspace_id=workspace_id,
        scope="workspace",
        project_id=None,
        purpose=purpose,
    )
    project_policy = (
        _budget_policy_for_scope(db, workspace_id=workspace_id, scope="project", project_id=project_id, purpose=purpose)
        if project_id
        else None
    )
    for policy in [workspace_policy, project_policy]:
        if policy is None:
            continue
        hard_caps.update(_sanitize_budget_values(dict(policy.hard_caps or {}), hard_caps))
        sanitized_defaults = _sanitize_budget_values(dict(policy.defaults or {}), hard_caps)
        snapshot.update(sanitized_defaults)
        sources.append({"scope": policy.scope, "policy_id": policy.id, "keys": sorted(sanitized_defaults)})

    sanitized_override = _sanitize_budget_values(dict(override or {}), hard_caps)
    snapshot.update(sanitized_override)
    if sanitized_override:
        sources.append({"scope": "run_override", "keys": sorted(sanitized_override)})
    snapshot = _sanitize_budget_values(snapshot, hard_caps)
    snapshot["system_hard_caps"] = hard_caps
    snapshot["budget_sources"] = sources
    return snapshot


