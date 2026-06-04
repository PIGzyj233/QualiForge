from __future__ import annotations

from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.agents import AgentRun, EvidenceKind
from app.agents.coverage import classify_candidate_coverage, lookup_coverage_records
from app.agents.schemas import CoverageEntryCreate, EvidenceRef
from app.cases.diff_models import DiffAnalysis
from app.cases.domain import CaseRevision, TestCase, TestCaseLifecycle
from app.cases.step_models import steps_expected_text


class RecommendationDraftType(StrEnum):
    regression = "regression"
    case_candidate = "case_candidate"


class CoverageDecision(BaseModel):
    source: str = "coverage_index"
    classification: str = "coverage_gap"
    recommendation: str = "stage_new_candidate"
    matches: list[dict[str, Any]] = Field(default_factory=list)


class DraftQualityResult(BaseModel):
    passed: bool = True
    checks: list[str] = Field(default_factory=list)
    issues: list[str] = Field(default_factory=list)


class DiffRecommendationDraft(BaseModel):
    draft_type: RecommendationDraftType
    title: str
    rationale: str
    confidence: int
    module_id: str | None = None
    module_key: str = "UNMAPPED"
    source_diff: dict[str, Any] = Field(default_factory=dict)
    mapping_evidence: list[str] = Field(default_factory=list)
    code_paths: list[str] = Field(default_factory=list)
    interfaces: list[str] = Field(default_factory=list)
    config_keys: list[str] = Field(default_factory=list)
    related_case_ids: list[str] = Field(default_factory=list)
    selected_case_ids: list[str] = Field(default_factory=list)
    candidate_payload: dict[str, Any] = Field(default_factory=dict)
    evidence_refs: list[EvidenceRef] = Field(default_factory=list)
    coverage_entries: list[CoverageEntryCreate] = Field(default_factory=list)
    coverage_decision: CoverageDecision = Field(default_factory=CoverageDecision)
    quality_result: DraftQualityResult = Field(default_factory=DraftQualityResult)


class CoverageProbe(BaseModel):
    title: str
    expected_result: str
    steps: list[str]
    module_key: str
    observability: dict[str, Any] = Field(default_factory=dict)
    evidence_refs: list[EvidenceRef] = Field(default_factory=list)
    coverage_entries: list[CoverageEntryCreate] = Field(default_factory=list)
    duplicate_result: dict[str, Any] = Field(default_factory=dict)


def compact_strings(values: Any, *, limit: int = 8, max_length: int = 180) -> list[str]:
    if not isinstance(values, list):
        return []
    result: list[str] = []
    for value in values:
        text = str(value).strip()
        if text:
            result.append(text[:max_length])
        if len(result) >= limit:
            break
    return result


def compact_candidate_steps(values: Any) -> list[dict[str, str]]:
    if not isinstance(values, list):
        return []
    steps: list[dict[str, str]] = []
    for value in values:
        if isinstance(value, dict):
            action = str(value.get("action") or "").strip()
            expected = str(value.get("expected") or value.get("expected_result") or "").strip()
        else:
            action = str(value).strip()
            expected = "Actual behavior matches the release expectation"
        if not action:
            continue
        steps.append({"action": action[:240], "expected": (expected or "Behavior matches the change expectation")[:240]})
        if len(steps) >= 8:
            break
    return steps


def clamp_confidence(value: Any, fallback: int) -> int:
    try:
        return max(1, min(100, int(value)))
    except (TypeError, ValueError):
        return fallback


def structure_names(files: list[dict[str, Any]], structure_type: str) -> list[str]:
    names: list[str] = []
    for file in files:
        for item in file.get("structure_changes", []):
            if item.get("type") == structure_type and item.get("name"):
                names.append(str(item["name"]))
    return list(dict.fromkeys(names))


def case_revision_snapshot(db: Session, test_case: TestCase) -> dict[str, Any]:
    if not test_case.current_revision_id:
        return {}
    revision = db.get(CaseRevision, test_case.current_revision_id)
    return revision.content_snapshot if revision else {}


def related_approved_cases(db: Session, workspace_id: str, project_id: str, module_id: str | None, module_key: str) -> list[TestCase]:
    statement = select(TestCase).where(
        TestCase.workspace_id == workspace_id,
        TestCase.project_id == project_id,
        TestCase.lifecycle_status == TestCaseLifecycle.active.value,
    )
    if module_id:
        statement = statement.where(TestCase.current_module_id == module_id)
    cases = list(db.scalars(statement.order_by(TestCase.updated_at.desc(), TestCase.id.desc())).all())
    if cases or not module_key:
        return cases[:8]
    fallback = db.scalars(
        select(TestCase).where(
            TestCase.workspace_id == workspace_id,
            TestCase.project_id == project_id,
            TestCase.lifecycle_status == TestCaseLifecycle.active.value,
        )
    ).all()
    lowered = module_key.lower()
    matches = []
    for case in fallback:
        snapshot = case_revision_snapshot(db, case)
        haystack = " ".join([str(snapshot.get("title") or ""), *(str(tag) for tag in snapshot.get("tags", []))]).lower()
        if lowered in haystack:
            matches.append(case)
    return matches[:8]


def focus_label(files: list[dict[str, Any]], interfaces: list[str], config_keys: list[str], module_key: str) -> str:
    if interfaces:
        return f"interface {interfaces[0]}"
    if config_keys:
        return f"configuration {config_keys[0]}"
    migration = next((str(file.get("path")) for file in files if file.get("is_migration")), "")
    if migration:
        return f"migration {migration}"
    path = str(files[0].get("path")) if files else ""
    return path or module_key


def source_diff_for_impact(analysis: DiffAnalysis, impact: dict[str, Any]) -> dict[str, Any]:
    return {
        "analysis_id": analysis.id,
        "base_ref": analysis.base_ref,
        "target_ref": analysis.target_ref,
        "risk_level": impact.get("risk_level"),
        "changed_file_count": impact.get("changed_file_count"),
        "draft_generation": "diff_recommendation_draft_v1",
    }


def build_candidate_payload(impact: dict[str, Any], files: list[dict[str, Any]], analysis: DiffAnalysis) -> dict[str, Any]:
    module_key = str(impact.get("module_key") or "UNMAPPED")
    high_signal = "high" if impact.get("risk_level") == "high" else "medium"
    code_paths = [str(file["path"]) for file in files[:5]]
    interfaces = structure_names(files, "api_route")
    config_keys = structure_names(files, "config_key")
    focus = focus_label(files, interfaces, config_keys, module_key)
    steps = [
        {
            "action": f"Prepare a release test environment on target ref {analysis.target_ref}",
            "expected": "The target revision is available and the impacted module can be tested normally",
        },
        {
            "action": f"Exercise the business behavior behind {focus}",
            "expected": f"{module_key} follows the expected release behavior without user-visible regressions",
        },
        {
            "action": "Compare the result with existing approved cases and release acceptance criteria",
            "expected": "Known covered behavior still passes, and any new behavior has clear evidence",
        },
    ]
    if config_keys:
        steps.append(
            {
                "action": f"Validate release behavior for config keys: {', '.join(config_keys[:3])}",
                "expected": "Config-driven behavior matches the target release values and fallback expectations",
            }
        )
    return {
        "module_id": impact.get("module_id"),
        "title": f"Validate {module_key} release behavior changed by {analysis.base_ref}..{analysis.target_ref}",
        "steps": steps,
        "expected_result": steps_expected_text(steps),
        "priority": "P1" if high_signal == "high" else "P2",
        "risk": high_signal,
        "tags": ["ai-diff", module_key.lower()],
        "custom_fields": {
            "source": "ai_suggestion",
            "diff_analysis_id": analysis.id,
            "code_paths": ", ".join(code_paths),
            "interfaces": ", ".join(interfaces),
            "config_keys": ", ".join(config_keys),
        },
    }


def draft_evidence_refs(draft: DiffRecommendationDraft, analysis: DiffAnalysis) -> list[EvidenceRef]:
    confidence = max(0.0, min(1.0, draft.confidence / 100))
    refs = [
        EvidenceRef(
            kind=EvidenceKind.diff_analysis,
            ref_id=analysis.id,
            label=f"{analysis.base_ref}..{analysis.target_ref}",
            confidence=confidence,
            summary=draft.rationale[:700],
            source="recommendation_draft",
        )
    ]
    for path in draft.code_paths[:8]:
        refs.append(
            EvidenceRef(
                kind=EvidenceKind.code_file,
                ref_id=f"repo:{analysis.target_ref}:{path}",
                label=path[:300],
                confidence=confidence,
                summary=f"Changed file supporting {draft.module_key}",
                source="diff_analysis",
            )
        )
    for index, evidence in enumerate(draft.mapping_evidence[:6]):
        refs.append(
            EvidenceRef(
                kind=EvidenceKind.diff_hunk,
                ref_id=f"{analysis.id}:evidence:{index}",
                label=evidence[:300],
                confidence=confidence,
                summary=evidence[:700],
                source="diff_analysis",
            )
        )
    for case_id in draft.related_case_ids[:5]:
        refs.append(
            EvidenceRef(
                kind=EvidenceKind.test_case,
                ref_id=case_id,
                label=case_id,
                confidence=confidence,
                summary="Related approved case considered by recommendation drafting",
                source="coverage_lookup",
            )
        )
    return refs


def draft_coverage_entries(draft: DiffRecommendationDraft) -> list[CoverageEntryCreate]:
    signals: list[dict[str, Any]] = []
    for value in draft.interfaces:
        signals.append({"signal_type": "api_route", "value": value, "source": "diff_analysis", "confidence": draft.confidence})
    for value in draft.config_keys:
        signals.append({"signal_type": "config_key", "value": value, "source": "diff_analysis", "confidence": draft.confidence})
    return [
        CoverageEntryCreate(
            module_id=draft.module_id,
            module_key=draft.module_key or "UNMAPPED",
            behavior_summary=(draft.rationale or draft.title)[:700],
            signals=signals,
            evidence_refs=draft.evidence_refs[:8],
            confidence=draft.confidence,
        )
    ]


def assess_draft_quality(draft: DiffRecommendationDraft) -> DraftQualityResult:
    issues: list[str] = []
    checks = [
        "business_title_present",
        "rationale_has_test_intent",
        "evidence_present",
        "coverage_decision_present",
    ]
    if not draft.title.strip():
        issues.append("missing_title")
    if len(draft.rationale.strip()) < 20:
        issues.append("thin_rationale")
    if not (draft.evidence_refs or draft.mapping_evidence or draft.code_paths):
        issues.append("missing_evidence")
    if not draft.coverage_decision.recommendation:
        issues.append("missing_coverage_decision")
    if draft.draft_type == RecommendationDraftType.case_candidate:
        checks.extend(["case_steps_present", "expected_result_observable"])
        steps = draft.candidate_payload.get("steps") if isinstance(draft.candidate_payload, dict) else []
        if not steps:
            issues.append("missing_steps")
        if not (draft.candidate_payload.get("expected_result") or steps_expected_text(steps)):
            issues.append("missing_expected_result")
    return DraftQualityResult(passed=not issues, checks=checks, issues=issues)


def apply_llm_override_to_draft(
    draft: DiffRecommendationDraft,
    override: dict[str, Any] | None,
    *,
    prompt_hash: str,
    source_metadata: dict[str, Any] | None = None,
) -> DiffRecommendationDraft:
    draft.source_diff = {
        **draft.source_diff,
        "llm_used": True,
        "llm_prompt_hash": prompt_hash,
        "llm_prompt_version": "ai-suggestions-v1",
        **(source_metadata or {}),
    }
    if not override:
        return draft
    title = str(override.get("title") or "").strip()
    rationale = str(override.get("rationale") or "").strip()
    if title:
        draft.title = title[:220]
    if rationale:
        draft.rationale = rationale[:900]
    draft.confidence = clamp_confidence(override.get("confidence"), draft.confidence)
    draft.interfaces = list(dict.fromkeys([*draft.interfaces, *compact_strings(override.get("interfaces"), limit=8)]))
    draft.config_keys = list(dict.fromkeys([*draft.config_keys, *compact_strings(override.get("config_keys"), limit=8)]))
    evidence = compact_strings(override.get("evidence"), limit=8)
    context_needed = [f"context gap: {item}" for item in compact_strings(override.get("context_needed"), limit=4)]
    if evidence or context_needed:
        draft.mapping_evidence = list(dict.fromkeys([*draft.mapping_evidence, *evidence, *context_needed]))
    if draft.draft_type == RecommendationDraftType.case_candidate:
        steps = compact_candidate_steps(override.get("steps") or override.get("candidate_steps"))
        if steps:
            draft.candidate_payload = {
                **draft.candidate_payload,
                "title": draft.title,
                "steps": steps,
                "expected_result": steps_expected_text(steps),
            }
    return draft


def coverage_decision_for_candidate(db: Session, run: AgentRun | None, draft: DiffRecommendationDraft) -> CoverageDecision:
    if run is None:
        return CoverageDecision(source="coverage_index_unavailable")
    query = " ".join(
        [
            draft.title,
            draft.rationale,
            str(draft.candidate_payload.get("expected_result") or ""),
            " ".join(str(step.get("action") or "") for step in draft.candidate_payload.get("steps", []) if isinstance(step, dict)),
        ]
    )
    records = lookup_coverage_records(db, run=run, query=query, module_key=draft.module_key, max_results=40)
    probe = CoverageProbe(
        title=draft.title,
        expected_result=str(draft.candidate_payload.get("expected_result") or steps_expected_text(draft.candidate_payload.get("steps", []))),
        steps=[str(step.get("action") or step) for step in draft.candidate_payload.get("steps", [])],
        module_key=draft.module_key,
        evidence_refs=draft.evidence_refs,
        coverage_entries=draft.coverage_entries,
        duplicate_result={},
    )
    result = classify_candidate_coverage(probe, records)
    return CoverageDecision(
        source=str(result.get("source") or "coverage_index"),
        classification=str(result.get("classification") or "coverage_gap"),
        recommendation=str(result.get("recommendation") or "stage_new_candidate"),
        matches=[item for item in result.get("matches", []) if isinstance(item, dict)],
    )


def selected_case_ids_from_decision(decision: CoverageDecision) -> list[str]:
    ids: list[str] = []
    for match in decision.matches:
        if match.get("source_type") == "formal_case" and match.get("source_id"):
            ids.append(str(match["source_id"]))
    return list(dict.fromkeys(ids))


def enrich_regression_with_coverage(regression: DiffRecommendationDraft, decision: CoverageDecision) -> DiffRecommendationDraft:
    regression.coverage_decision = decision
    regression.source_diff = {**regression.source_diff, "coverage_decision": decision.model_dump(mode="json")}
    matched_case_ids = selected_case_ids_from_decision(decision)
    if matched_case_ids:
        regression.related_case_ids = list(dict.fromkeys([*regression.related_case_ids, *matched_case_ids]))
        regression.selected_case_ids = list(dict.fromkeys([*regression.selected_case_ids, *matched_case_ids]))
    if decision.recommendation == "reuse_existing_coverage" and decision.matches:
        titles = [str(match.get("title") or match.get("source_id") or "") for match in decision.matches[:3] if match.get("title") or match.get("source_id")]
        if titles:
            regression.rationale = f"{regression.rationale} Existing coverage is a strong match; reuse {', '.join(titles)}."
    return regression


def build_diff_recommendation_drafts(
    db: Session,
    analysis: DiffAnalysis,
    actor_email: str,
    *,
    run: AgentRun | None = None,
    llm_overrides: dict[tuple[str, str], dict[str, Any]] | None = None,
    llm_prompt_hash: str = "",
    llm_source_metadata: dict[str, Any] | None = None,
) -> list[DiffRecommendationDraft]:
    drafts: list[DiffRecommendationDraft] = []
    for impact in analysis.module_impacts:
        module_id = impact.get("module_id")
        module_key = str(impact.get("module_key") or "UNMAPPED")
        files = [file for file in analysis.file_changes if (file.get("module_id") or "UNMAPPED") == (module_id or "UNMAPPED")]
        code_paths = [str(file["path"]) for file in files]
        interfaces = structure_names(files, "api_route")
        config_keys = structure_names(files, "config_key")
        mapping_evidence = list(dict.fromkeys(str(entry) for file in files for entry in file.get("evidence", [])))
        related_cases = related_approved_cases(db, analysis.workspace_id, analysis.project_id, str(module_id) if module_id else None, module_key)
        related_case_ids = [case.id for case in related_cases]
        source_diff = source_diff_for_impact(analysis, impact)

        regression = DiffRecommendationDraft(
            draft_type=RecommendationDraftType.regression,
            title=f"Run {module_key} regression for {analysis.target_ref}",
            rationale=(
                f"{module_key} has {impact.get('changed_file_count')} changed files with {impact.get('risk_level')} risk; "
                "reuse approved cases and verify the user-visible behavior behind the changed surfaces before release."
            ),
            confidence=int(impact.get("confidence") or 70),
            module_id=str(module_id) if module_id else None,
            module_key=module_key,
            source_diff=source_diff,
            mapping_evidence=mapping_evidence,
            code_paths=code_paths,
            interfaces=interfaces,
            config_keys=config_keys,
            related_case_ids=related_case_ids,
            selected_case_ids=related_case_ids,
        )
        candidate_payload = build_candidate_payload(impact, files, analysis)
        candidate = DiffRecommendationDraft(
            draft_type=RecommendationDraftType.case_candidate,
            title=str(candidate_payload["title"]),
            rationale=(
                f"{module_key} changed release behavior around {focus_label(files, interfaces, config_keys, module_key)}; "
                "stage a reviewable candidate only if existing coverage cannot fully cover the behavior."
            ),
            confidence=max(65, int(impact.get("confidence") or 70) - 5),
            module_id=str(module_id) if module_id else None,
            module_key=module_key,
            source_diff=source_diff,
            mapping_evidence=mapping_evidence,
            code_paths=code_paths,
            interfaces=interfaces,
            config_keys=config_keys,
            candidate_payload=candidate_payload,
        )

        if llm_prompt_hash:
            regression = apply_llm_override_to_draft(
                regression,
                (llm_overrides or {}).get((RecommendationDraftType.regression.value, module_key)),
                prompt_hash=llm_prompt_hash,
                source_metadata=llm_source_metadata,
            )
            candidate = apply_llm_override_to_draft(
                candidate,
                (llm_overrides or {}).get((RecommendationDraftType.case_candidate.value, module_key)),
                prompt_hash=llm_prompt_hash,
                source_metadata=llm_source_metadata,
            )

        regression.evidence_refs = draft_evidence_refs(regression, analysis)
        regression.coverage_entries = draft_coverage_entries(regression)
        regression.quality_result = assess_draft_quality(regression)

        candidate.evidence_refs = draft_evidence_refs(candidate, analysis)
        candidate.coverage_entries = draft_coverage_entries(candidate)
        decision = coverage_decision_for_candidate(db, run, candidate)
        candidate.coverage_decision = decision
        candidate.source_diff = {**candidate.source_diff, "coverage_decision": decision.model_dump(mode="json")}
        candidate.selected_case_ids = selected_case_ids_from_decision(decision)
        candidate.related_case_ids = list(dict.fromkeys([*candidate.related_case_ids, *candidate.selected_case_ids]))
        if decision.recommendation == "extend_existing_coverage":
            candidate.rationale = f"{candidate.rationale} Existing coverage partially matches; use this draft to extend it."
        candidate.quality_result = assess_draft_quality(candidate)

        regression = enrich_regression_with_coverage(regression, decision)
        regression.quality_result = assess_draft_quality(regression)
        drafts.append(regression)
        if decision.recommendation != "reuse_existing_coverage":
            drafts.append(candidate)
    return drafts
