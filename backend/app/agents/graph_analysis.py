from __future__ import annotations

from typing import Any

from app.agents.coverage import (
    classify_candidate_coverage,
    evidence_paths,
    jaccard,
    lookup_coverage_records,
    normalize_text,
    signal_values,
    token_set,
)
from app.agents.models import AgentRun, AgentRunMode, AgentStagedOutputType
from app.agents.graph_types import SUBAGENT_REGISTRY

# Backward-compatible names for older graph node imports. New code should call
# the CoverageIndex module through app.agents.coverage.
collect_coverage_records = lookup_coverage_records
classify_duplicate = classify_candidate_coverage


def _subagent_list(value: Any) -> list[str]:
    if isinstance(value, str):
        raw_items = value.split(",")
    elif isinstance(value, list):
        raw_items = value
    else:
        raw_items = []
    return [str(item).strip() for item in raw_items if str(item).strip()]


def select_subagent_plan(*, run: AgentRun, snapshot: dict[str, Any]) -> dict[str, Any]:
    goal_tokens = token_set(run.goal)
    requested = _subagent_list(snapshot.get("requested_subagents"))
    disabled = set(_subagent_list(snapshot.get("disabled_subagents")))
    if snapshot.get("disable_critic"):
        disabled.add("CriticSubAgent")

    selected: list[str] = []
    reasons: dict[str, str] = {}
    skipped: list[dict[str, str]] = []

    def add(name: str, reason: str) -> None:
        spec = SUBAGENT_REGISTRY.get(name)
        if spec is None:
            skipped.append({"name": name, "reason": "unknown_subagent"})
            return
        if name in disabled and not spec.required:
            skipped.append({"name": name, "reason": "disabled"})
            return
        if name not in selected:
            selected.append(name)
            reasons[name] = reason

    if snapshot.get("output_type") == AgentStagedOutputType.module_tree_draft.value:
        add("CodeAnalysisSubAgent", "required_for_module_tree_repository_evidence")
        add("ModuleTreeDraftSubAgent", "requested_module_tree_draft_output")
        for name in requested:
            add(name, "requested_by_run_budget")
        grouped: dict[str, list[str]] = {}
        for name in selected:
            spec = SUBAGENT_REGISTRY[name]
            grouped.setdefault(spec.parallel_group, []).append(name)
        group_order = ["read_analysis", "module_tree_draft"]
        parallel_groups = [grouped[group] for group in group_order if group in grouped]
        return {
            "selected": selected,
            "parallel_groups": parallel_groups,
            "selection_policy": "module_tree_draft_v1",
            "selection_reasons": reasons,
            "requested_subagents": requested,
            "disabled_subagents": sorted(disabled),
            "skipped_subagents": skipped,
            "available_subagents": [
                {
                    "name": spec.name,
                    "stage": spec.stage,
                    "required": spec.required,
                    "parallel_group": spec.parallel_group,
                    "purpose": spec.purpose,
                }
                for spec in SUBAGENT_REGISTRY.values()
            ],
            "supervisor_writes_staged_outputs": True,
        }

    for spec in SUBAGENT_REGISTRY.values():
        if spec.required:
            add(spec.name, "required_by_agent_graph")

    for name in requested:
        add(name, "requested_by_run_budget")

    regression_spec = SUBAGENT_REGISTRY["RegressionScopeSubAgent"]
    if run.mode == AgentRunMode.execute.value or goal_tokens & regression_spec.trigger_tokens:
        add("RegressionScopeSubAgent", "execute_mode_or_regression_goal")

    import_spec = SUBAGENT_REGISTRY["ImportAnalysisSubAgent"]
    if goal_tokens & import_spec.trigger_tokens:
        add("ImportAnalysisSubAgent", "import_or_cleanup_goal")

    critic_spec = SUBAGENT_REGISTRY["CriticSubAgent"]
    if run.mode == AgentRunMode.execute.value or goal_tokens & critic_spec.trigger_tokens:
        add("CriticSubAgent", "execute_mode_or_risk_goal")

    report_spec = SUBAGENT_REGISTRY["ReportDraftSubAgent"]
    if goal_tokens & report_spec.trigger_tokens:
        add("ReportDraftSubAgent", "report_or_release_goal")

    grouped: dict[str, list[str]] = {}
    for name in selected:
        spec = SUBAGENT_REGISTRY[name]
        grouped.setdefault(spec.parallel_group, []).append(name)
    group_order = ["read_analysis", "case_design", "module_tree_draft", "critic", "report_draft"]
    parallel_groups = [grouped[group] for group in group_order if group in grouped]

    return {
        "selected": selected,
        "parallel_groups": parallel_groups,
        "selection_policy": "registry_dynamic_v1",
        "selection_reasons": reasons,
        "requested_subagents": requested,
        "disabled_subagents": sorted(disabled),
        "skipped_subagents": skipped,
        "available_subagents": [
            {
                "name": spec.name,
                "stage": spec.stage,
                "required": spec.required,
                "parallel_group": spec.parallel_group,
                "purpose": spec.purpose,
            }
            for spec in SUBAGENT_REGISTRY.values()
        ],
        "supervisor_writes_staged_outputs": True,
    }
