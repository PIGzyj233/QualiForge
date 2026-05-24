from __future__ import annotations

import re
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.agents import (
    AgentRun,
    AgentRunMode,
    AgentStagedOutput,
    AgentStagedOutputStatus,
    AgentStagedOutputType,
    CoverageIndexEntry,
    evidence_refs_to_json,
)
from app.agents.graph_types import GeneratedCaseCandidate, SUBAGENT_REGISTRY
from app.cases.ai_suggestions import AISuggestion, AISuggestionType
from app.cases.domain import CaseDraft, CaseRevision, TestCase, TestCaseLifecycle
from app.cases.modules import ProjectModule


def normalize_text(value: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9]+", " ", value.lower())).strip()


def token_set(value: str) -> set[str]:
    return {token for token in normalize_text(value).split() if len(token) >= 3}


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
    group_order = ["read_analysis", "case_design", "critic", "report_draft"]
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


def jaccard(left: set[str], right: set[str]) -> float:
    if not left or not right:
        return 0.0
    return len(left & right) / len(left | right)


def module_key_for_id(db: Session, module_id: str | None) -> str:
    if not module_id:
        return "UNMAPPED"
    module = db.get(ProjectModule, module_id)
    if module is None:
        return "UNMAPPED"
    return module.code or module.slug.upper().replace("-", "_")


def evidence_paths(refs: list[dict[str, Any]]) -> list[str]:
    paths: list[str] = []
    for ref in refs:
        label = str(ref.get("label") or "")
        ref_id = str(ref.get("ref_id") or "")
        if label:
            paths.append(label.split(":", 1)[0])
        if ref_id.startswith("repo:"):
            parts = ref_id.split(":", 2)
            if len(parts) == 3:
                paths.append(parts[2])
        elif ref_id:
            paths.append(ref_id.split(":", 1)[0])
    return list(dict.fromkeys(paths))


def signal_values(*items: Any) -> list[str]:
    values: list[str] = []
    for item in items:
        if isinstance(item, dict):
            for key in ("audit_events", "log_keywords", "metrics", "trace_points", "job_states", "entity_ids"):
                raw = item.get(key, [])
                if isinstance(raw, list):
                    values.extend(str(value) for value in raw if str(value).strip())
            signals = item.get("signals", [])
            for raw in signals if isinstance(signals, list) else []:
                if isinstance(raw, dict):
                    value = raw.get("value") or raw.get("name") or raw.get("signal")
                    if value:
                        values.append(str(value))
        elif isinstance(item, list):
            for raw in item:
                if isinstance(raw, dict):
                    nested = raw.get("signals", [])
                    if isinstance(nested, list):
                        values.extend(signal_values(nested))
                    value = raw.get("value") or raw.get("name") or raw.get("signal")
                    if value:
                        values.append(str(value))
    return list(dict.fromkeys(normalize_text(value) for value in values if normalize_text(value)))


def collect_coverage_records(
    db: Session,
    *,
    run: AgentRun,
    query: str = "",
    module_key: str = "",
    max_results: int = 80,
) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    wanted_module = normalize_text(module_key)
    query_tokens = token_set(query)

    def append(record: dict[str, Any]) -> None:
        record_module = normalize_text(str(record.get("module_key") or "UNMAPPED"))
        haystack = " ".join(
            str(record.get(key) or "")
            for key in ("title", "behavior_summary", "expected_result")
        )
        if wanted_module and record_module != wanted_module:
            return
        if query_tokens and len(records) >= max_results:
            return
        record["tokens"] = sorted(token_set(haystack + " " + " ".join(record.get("steps", []))))
        records.append(record)

    coverage_entries = db.scalars(
        select(CoverageIndexEntry)
        .where(
            CoverageIndexEntry.workspace_id == run.workspace_id,
            CoverageIndexEntry.project_id == run.project_id,
            CoverageIndexEntry.coverage_state != "rejected",
        )
        .order_by(CoverageIndexEntry.updated_at.desc(), CoverageIndexEntry.id.desc())
        .limit(200)
    ).all()
    for entry in coverage_entries:
        append(
            {
                "source_type": "coverage_index",
                "source_id": entry.id,
                "coverage_state": entry.coverage_state,
                "module_key": entry.module_key or "UNMAPPED",
                "title": "",
                "behavior_summary": entry.behavior_summary,
                "steps": [],
                "expected_result": "",
                "signals": signal_values(entry.signals),
                "evidence_paths": evidence_paths(entry.evidence_refs),
            }
        )

    staged_outputs = db.scalars(
        select(AgentStagedOutput)
        .where(
            AgentStagedOutput.workspace_id == run.workspace_id,
            AgentStagedOutput.project_id == run.project_id,
            AgentStagedOutput.output_type == AgentStagedOutputType.case_candidate.value,
            AgentStagedOutput.status != AgentStagedOutputStatus.rejected.value,
        )
        .order_by(AgentStagedOutput.created_at.desc(), AgentStagedOutput.id.desc())
        .limit(100)
    ).all()
    for output in staged_outputs:
        payload = output.payload or {}
        append(
            {
                "source_type": "staged_output",
                "source_id": output.id,
                "coverage_state": output.status,
                "module_key": str(payload.get("module_key") or "UNMAPPED"),
                "title": output.title,
                "behavior_summary": str((output.coverage_entries or [{}])[0].get("behavior_summary") if output.coverage_entries else ""),
                "steps": [str(step) for step in payload.get("steps", [])],
                "expected_result": str(payload.get("expected_result") or ""),
                "signals": signal_values(payload.get("observability", {}), output.coverage_entries),
                "evidence_paths": evidence_paths(output.evidence_refs),
            }
        )

    suggestions = db.scalars(
        select(AISuggestion)
        .where(
            AISuggestion.workspace_id == run.workspace_id,
            AISuggestion.project_id == run.project_id,
            AISuggestion.suggestion_type == AISuggestionType.case_candidate.value,
        )
        .order_by(AISuggestion.updated_at.desc(), AISuggestion.id.desc())
        .limit(100)
    ).all()
    for suggestion in suggestions:
        payload = suggestion.candidate_payload or {}
        append(
            {
                "source_type": "ai_suggestion",
                "source_id": suggestion.id,
                "coverage_state": suggestion.status,
                "module_key": suggestion.module_key or "UNMAPPED",
                "title": suggestion.title,
                "behavior_summary": suggestion.rationale,
                "steps": [str(step) for step in payload.get("steps", [])],
                "expected_result": str(payload.get("expected_result") or ""),
                "signals": signal_values(payload.get("custom_fields", {})),
                "evidence_paths": [str(path) for path in suggestion.code_paths],
            }
        )

    test_cases = db.scalars(
        select(TestCase)
        .where(
            TestCase.workspace_id == run.workspace_id,
            TestCase.project_id == run.project_id,
            TestCase.lifecycle_status != "archived",
        )
        .order_by(TestCase.updated_at.desc(), TestCase.id.desc())
        .limit(100)
    ).all()
    for test_case in test_cases:
        revision = db.get(CaseRevision, test_case.current_revision_id) if test_case.current_revision_id else None
        draft = db.scalar(
            select(CaseDraft)
            .where(CaseDraft.test_case_id == test_case.id)
            .order_by(CaseDraft.updated_at.desc(), CaseDraft.id.desc())
        )
        snapshot = revision.content_snapshot if revision else {}
        title = str((draft.title if draft else "") or snapshot.get("title") or "")
        steps = [str(step) for step in ((draft.steps if draft else None) or snapshot.get("steps", []))]
        expected = str((draft.expected_result if draft else "") or snapshot.get("expected_result") or "")
        module_id = (draft.module_id if draft else None) or test_case.current_module_id or str(snapshot.get("module_id") or "") or None
        append(
            {
                "source_type": "formal_case" if test_case.lifecycle_status == TestCaseLifecycle.active.value else "case_candidate",
                "source_id": test_case.id,
                "coverage_state": test_case.lifecycle_status,
                "module_key": module_key_for_id(db, module_id),
                "title": title,
                "behavior_summary": expected,
                "steps": steps,
                "expected_result": expected,
                "signals": signal_values((draft.custom_fields if draft else None) or snapshot.get("custom_fields", {})),
                "evidence_paths": [],
            }
        )

    if query_tokens:
        records.sort(
            key=lambda item: jaccard(query_tokens, set(item.get("tokens", []))),
            reverse=True,
        )
    return records[:max_results]


def classify_duplicate(candidate: GeneratedCaseCandidate, records: list[dict[str, Any]]) -> dict[str, Any]:
    candidate_text = " ".join([candidate.title, candidate.expected_result, *candidate.steps])
    candidate_tokens = token_set(candidate_text)
    candidate_module = normalize_text(candidate.module_key)
    candidate_signals = set(
        signal_values(candidate.observability, [entry.model_dump(mode="json") for entry in candidate.coverage_entries])
    )
    candidate_evidence = set(evidence_paths(evidence_refs_to_json(candidate.evidence_refs)))
    matches: list[dict[str, Any]] = []
    for record in records:
        record_module = normalize_text(str(record.get("module_key") or "UNMAPPED"))
        if candidate_module and record_module != candidate_module:
            continue
        record_tokens = set(record.get("tokens") or [])
        text_score = jaccard(candidate_tokens, record_tokens)
        title_exact = normalize_text(candidate.title) == normalize_text(str(record.get("title") or ""))
        behavior_exact = any(
            normalize_text(entry.behavior_summary) == normalize_text(str(record.get("behavior_summary") or ""))
            for entry in candidate.coverage_entries
        )
        signal_overlap = sorted(candidate_signals & set(record.get("signals") or []))
        evidence_overlap = sorted(candidate_evidence & set(record.get("evidence_paths") or []))
        if title_exact or behavior_exact or (signal_overlap and text_score >= 0.35) or text_score >= 0.70:
            confidence = "high"
        elif signal_overlap or evidence_overlap or text_score >= 0.45:
            confidence = "partial"
        else:
            continue
        matches.append(
            {
                "source_type": record.get("source_type"),
                "source_id": record.get("source_id"),
                "coverage_state": record.get("coverage_state"),
                "module_key": record.get("module_key"),
                "title": record.get("title"),
                "behavior_summary": record.get("behavior_summary"),
                "confidence": confidence,
                "text_overlap": round(text_score, 3),
                "signal_overlap": signal_overlap,
                "evidence_overlap": evidence_overlap,
            }
        )

    high = [match for match in matches if match["confidence"] == "high"]
    if high:
        classification = "high_confidence_duplicate"
        recommendation = "reuse_existing_coverage"
    elif matches:
        classification = "partial_duplicate"
        recommendation = "extend_existing_coverage"
    else:
        classification = "coverage_gap"
        recommendation = "stage_new_candidate"
    return {
        "source": "deterministic_lookup",
        "classification": classification,
        "recommendation": recommendation,
        "matches": (high or matches)[:5],
        "model_explanation": candidate.duplicate_result,
    }


