from __future__ import annotations

import concurrent.futures
import json
import re
import subprocess
from collections import Counter
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.ai.config import AIInvocationLog, AIInvocationStatus, AIPurpose, get_or_create_ai_settings
from app.ai.model_gateway import ModelGatewayError, build_model_gateway
from app.agents.memory import append_daily_project_memory
from app.agents import (
    AgentMessage,
    AgentRepositorySandbox,
    AgentRepositorySandboxStatus,
    AgentRun,
    AgentRunMode,
    AgentSubagentRun,
    AgentSubagentRunStatus,
    AgentStagedOutput,
    AgentStagedOutputStatus,
    AgentStagedOutputType,
    CoverageIndexEntry,
    EvidenceKind,
    add_coverage_entries,
    coverage_snapshot,
    evidence_refs_to_json,
    mark_run_succeeded,
)
from app.agents.graph_analysis import classify_duplicate, evidence_paths, jaccard, normalize_text, select_subagent_plan, signal_values, token_set
from app.agents.graph_policy import (
    AGENT_MODEL_INPUT_DATA_TYPES,
    AGENT_SUPERVISOR_PROMPT_VERSION,
    prompt_hash_for_messages,
    staged_output_idempotency_key,
)
from app.agents.graph_tools import ToolRegistry
from app.agents.graph_types import (
    AgentBudgetExceeded,
    AgentGraphState,
    AgentRunCancelled,
    GeneratedCandidateEnvelope,
    GeneratedCaseCandidate,
    GeneratedModuleTreeDraftEnvelope,
    SUBAGENT_REGISTRY,
)
from app.cases.step_models import steps_expected_text
from app.git.models import GitRepository
from app.git.sandbox import ensure_safe_sandbox_path, remove_tree_readonly
from app.platform.telemetry import (
    AGENT_MODEL_CALLS_TOTAL,
    AGENT_MODEL_COST_TOTAL,
    AGENT_MODEL_LATENCY_SECONDS,
    AGENT_MODEL_TOKENS_TOTAL,
    agent_span,
    elapsed_seconds,
    export_langfuse_generation,
)
from app.workspace.routes import audit, now_utc


class GraphVerificationNodesMixin:
    def verify(self, state: AgentGraphState) -> dict[str, Any]:
        run = self._run(state)
        if self._is_module_tree_draft_run(run):
            return self.verify_module_tree_draft(state)
        self._check_cancelled(run, "critic:start")
        self._set_run_phase(run, "verify")
        critic_selected = "CriticSubAgent" in set((state.get("subagent_plan") or {}).get("selected") or [])
        verified: list[dict[str, Any]] = []
        reuse_recommendations: list[dict[str, Any]] = []
        coverage_records = state.get("tool_results", {}).get("coverage_lookup", [])
        critic_rejections: list[dict[str, Any]] = []
        result_key = "CriticSubAgent" if critic_selected else "SupervisorVerifier"
        plan = state.get("subagent_plan") or {}
        self._record_subagent_run(
            run,
            subagent_name=result_key,
            status=AgentSubagentRunStatus.running,
            stage="critic",
            parallel_group=self._subagent_group(plan, result_key),
            input_summary="Check candidate quality, evidence support, duplicate risk, and observability gaps",
        )
        try:
            with agent_span("agent.subagent", run_id=run.id, subagent=result_key, stage="critic"):
                for raw in state.get("candidates", []):
                    candidate = GeneratedCaseCandidate.model_validate(raw)
                    candidate = self._validate_candidate_quality(candidate)
                    duplicate_result = classify_duplicate(candidate, coverage_records)
                    critic_result = self._critic_candidate(candidate, duplicate_result=duplicate_result, critic_selected=critic_selected)
                    candidate_data = candidate.model_dump(mode="json")
                    candidate_data["duplicate_result"] = duplicate_result
                    candidate_data["critic_result"] = critic_result
                    if duplicate_result["classification"] in {"high_confidence_duplicate", "partial_duplicate"}:
                        reuse_recommendations.append(
                            {
                                "title": candidate.title,
                                "module_key": candidate.module_key,
                                "risk": candidate.risk,
                                "priority": candidate.priority,
                                "duplicate_result": duplicate_result,
                                "recommendation": duplicate_result["recommendation"],
                                "candidate": candidate_data,
                            }
                        )
                    elif not critic_result["passed"]:
                        critic_rejections.append(
                            {
                                "title": candidate.title,
                                "module_key": candidate.module_key,
                                "risk": candidate.risk,
                                "priority": candidate.priority,
                                "critic_result": critic_result,
                            }
                        )
                    else:
                        verified.append(candidate_data)
        except Exception as exc:
            self._record_subagent_run(
                run,
                subagent_name=result_key,
                status=AgentSubagentRunStatus.failed,
                stage="critic",
                parallel_group=self._subagent_group(plan, result_key),
                summary="Critic pass failed",
                error_summary=str(exc),
            )
            raise
        if not verified and not reuse_recommendations:
            failure_reason = (
                critic_rejections[0]["critic_result"]["issues"][0]["reason"]
                if critic_rejections
                else "Model returned no case candidates"
            )
            self._record_subagent_run(
                run,
                subagent_name=result_key,
                status=AgentSubagentRunStatus.failed,
                stage="critic",
                parallel_group=self._subagent_group(plan, result_key),
                summary="Critic rejected all candidates",
                result_snapshot={"accepted": 0, "reuse_recommendations": 0, "rejected": len(critic_rejections)},
                error_summary=failure_reason,
            )
            if critic_rejections:
                raise RuntimeError(f"Critic rejected all candidate(s): {failure_reason}")
            raise RuntimeError("Model returned no case candidates")
        critic_summary = {
            "accepted": len(verified),
            "reuse_recommendations": len(reuse_recommendations),
            "rejected": len(critic_rejections),
            "checks": [
                "candidate_quality",
                "duplication_risk",
                "evidence_support",
                "hallucination_risk",
                "observability_gaps",
            ],
        }
        self._record_subagent_run(
            run,
            subagent_name=result_key,
            status=AgentSubagentRunStatus.succeeded,
            stage="critic",
            parallel_group=self._subagent_group(plan, result_key),
            summary="Critic pass completed",
            output_summary=f"Accepted {len(verified)} candidate(s), flagged {len(reuse_recommendations)} reuse recommendation(s)",
            result_snapshot=critic_summary,
        )
        subagent_results = {
            **dict(state.get("subagent_results") or {}),
            result_key: critic_summary,
        }
        if "ReportDraftSubAgent" in set((state.get("subagent_plan") or {}).get("selected") or []):
            self._record_subagent_run(
                run,
                subagent_name="ReportDraftSubAgent",
                status=AgentSubagentRunStatus.running,
                stage="report_draft",
                parallel_group=self._subagent_group(plan, "ReportDraftSubAgent"),
                input_summary="Prepare report-ready summary metadata from verified run facts",
            )
            with agent_span("agent.subagent", run_id=run.id, subagent="ReportDraftSubAgent", stage="report_draft"):
                subagent_results["ReportDraftSubAgent"] = {
                    "structured_summary_available": True,
                    "candidate_count": len(verified),
                    "reuse_recommendations": len(reuse_recommendations),
                    "supervisor_writes_staged_outputs": True,
                }
            self._record_subagent_run(
                run,
                subagent_name="ReportDraftSubAgent",
                status=AgentSubagentRunStatus.succeeded,
                stage="report_draft",
                parallel_group=self._subagent_group(plan, "ReportDraftSubAgent"),
                summary="Report draft metadata prepared",
                output_summary=f"Prepared report summary metadata for {len(verified)} candidate(s)",
                result_snapshot=subagent_results["ReportDraftSubAgent"],
            )
        return {
            "verified_candidates": verified,
            "reuse_recommendations": reuse_recommendations,
            "subagent_results": subagent_results,
        }

    def verify_module_tree_draft(self, state: AgentGraphState) -> dict[str, Any]:
        run = self._run(state)
        self._check_cancelled(run, "module_tree_verify:start")
        self._set_run_phase(run, "verify_module_tree_draft")
        payload = dict(state.get("module_tree_draft") or {})
        items = [item for item in payload.get("items", []) if isinstance(item, dict)]
        if not items:
            raise RuntimeError("Model returned no module draft items")
        seen_ids: set[str] = set()
        seen_slugs: set[tuple[str | None, str]] = set()
        parent_by_id: dict[str, str] = {}
        issues: list[dict[str, Any]] = []
        for item in items:
            draft_id = str(item.get("draft_id") or "")
            parent_id = str(item.get("parent_draft_id") or "")
            slug = self._normalized_module_slug(str(item.get("slug") or item.get("name") or ""))
            if not draft_id or draft_id in seen_ids:
                issues.append({"draft_id": draft_id, "reason": "missing_or_duplicate_draft_id"})
            seen_ids.add(draft_id)
            if draft_id:
                parent_by_id[draft_id] = parent_id
            key = (parent_id or None, slug)
            if not slug or key in seen_slugs:
                issues.append({"draft_id": draft_id, "reason": "missing_or_duplicate_sibling_slug"})
            seen_slugs.add(key)
            if parent_id and parent_id not in seen_ids and not any(str(candidate.get("draft_id") or "") == parent_id for candidate in items):
                issues.append({"draft_id": draft_id, "reason": "parent_draft_id_not_found"})
            if not item.get("evidence_refs"):
                issues.append({"draft_id": draft_id, "reason": "missing_evidence_refs"})
            if not item.get("source_paths"):
                issues.append({"draft_id": draft_id, "reason": "missing_source_paths"})
        for draft_id in parent_by_id:
            ancestors: set[str] = set()
            cursor = draft_id
            while parent_by_id.get(cursor):
                cursor = parent_by_id[cursor]
                if cursor in ancestors or cursor == draft_id:
                    issues.append({"draft_id": draft_id, "reason": "parent_cycle_detected"})
                    break
                ancestors.add(cursor)
        if issues:
            raise RuntimeError(f"Module tree draft failed verification: {issues[:3]}")
        quality_result = {
            "passed": True,
            "checks": [
                "modules_present",
                "draft_ids_unique",
                "sibling_slugs_unique",
                "parents_resolvable",
                "evidence_refs_present",
                "source_paths_present",
            ],
            "module_count": len(items),
        }
        payload["quality_result"] = quality_result
        return {
            "verified_module_tree_draft": payload,
            "subagent_results": {
                **dict(state.get("subagent_results") or {}),
                "ModuleTreeVerifier": quality_result,
            },
        }

    def _validate_candidate_quality(self, candidate: GeneratedCaseCandidate) -> GeneratedCaseCandidate:
        risk = candidate.risk.strip().lower()
        if risk not in {"low", "medium", "high"}:
            raise RuntimeError(f"Candidate {candidate.title} has invalid risk {candidate.risk}")
        priority = candidate.priority.strip().upper()
        if priority not in {"P0", "P1", "P2", "P3"}:
            raise RuntimeError(f"Candidate {candidate.title} has invalid priority {candidate.priority}")
        module_key = candidate.module_key.strip().upper() or "UNMAPPED"
        if module_key == "UNMAPPED" and not candidate.unmapped_reason.strip():
            raise RuntimeError(f"Candidate {candidate.title} must include unmapped_reason when module_key is UNMAPPED")
        steps = [step.strip() for step in candidate.steps if step.strip()]
        if len(steps) < 2:
            raise RuntimeError(f"Candidate {candidate.title} must include at least two executable steps")
        generic_steps = {"test", "verify", "check", "validate", "run test", "do test", "execute"}
        if any(normalize_text(step) in generic_steps or len(step) < 8 for step in steps):
            raise RuntimeError(f"Candidate {candidate.title} has non-executable placeholder steps")
        observability = dict(candidate.observability or {})
        for key in ("signals", "log_keywords", "metrics", "audit_events", "trace_points", "job_states", "entity_ids", "gaps"):
            value = observability.get(key, [])
            observability[key] = value if isinstance(value, list) else [value]
        observable_signals = signal_values(observability)
        expected_tokens = token_set(candidate.expected_result)
        observable_words = {
            "audit",
            "event",
            "log",
            "metric",
            "trace",
            "status",
            "visible",
            "record",
            "history",
            "message",
            "id",
            "error",
            "state",
            "includes",
            "emits",
        }
        if not observable_signals and not (expected_tokens & observable_words):
            raise RuntimeError(f"Candidate {candidate.title} expected_result is not observable")
        if risk == "high" and not observable_signals:
            observability["gaps"] = [
                *observability.get("gaps", []),
                {
                    "type": "observability_gap",
                    "reason": "High-risk candidate has no concrete audit, log, metric, trace, job, or entity signal.",
                },
            ]
        if not candidate.evidence_refs:
            raise RuntimeError(f"Candidate {candidate.title} has no evidence refs")
        if not candidate.coverage_entries:
            raise RuntimeError(f"Candidate {candidate.title} has no coverage entries")
        for entry in candidate.coverage_entries:
            entry.module_key = (entry.module_key or module_key).strip().upper()
            if entry.module_key == "UNMAPPED" and module_key != "UNMAPPED":
                entry.module_key = module_key
        candidate.risk = risk
        candidate.priority = priority
        candidate.module_key = module_key
        candidate.steps = steps
        candidate.observability = observability
        return candidate

    def _critic_candidate(
        self,
        candidate: GeneratedCaseCandidate,
        *,
        duplicate_result: dict[str, Any],
        critic_selected: bool,
    ) -> dict[str, Any]:
        issues: list[dict[str, str]] = []
        evidence_refs = evidence_refs_to_json(candidate.evidence_refs)
        missing_locators = [
            ref for ref in evidence_refs if not str(ref.get("ref_id") or "").strip() and not str(ref.get("label") or "").strip()
        ]
        low_confidence = [ref for ref in evidence_refs if float(ref.get("confidence") or 0) < 0.35]
        if missing_locators:
            issues.append(
                {
                    "severity": "blocker",
                    "code": "evidence_locator_missing",
                    "reason": "Evidence refs must include a ref_id or label so a human can inspect the source.",
                }
            )
        if low_confidence:
            issues.append(
                {
                    "severity": "blocker",
                    "code": "evidence_confidence_too_low",
                    "reason": "Evidence confidence below 0.35 is too weak to stage as a supported candidate.",
                }
            )

        evidence_text = " ".join(
            str(ref.get(key) or "") for ref in evidence_refs for key in ("ref_id", "label", "summary", "source")
        )
        candidate_tokens = token_set(" ".join([candidate.title, candidate.expected_result, *candidate.steps]))
        evidence_tokens = token_set(evidence_text)
        support_score = round(jaccard(candidate_tokens, evidence_tokens), 3)
        if support_score == 0 and not any(str(ref.get("kind") or "") == EvidenceKind.code_file.value for ref in evidence_refs):
            issues.append(
                {
                    "severity": "blocker",
                    "code": "evidence_support_missing",
                    "reason": "Candidate language has no overlap with cited evidence and no code-file evidence anchor.",
                }
            )

        observability_signals = signal_values(candidate.observability, [entry.model_dump(mode="json") for entry in candidate.coverage_entries])
        observability_gaps = candidate.observability.get("gaps") if isinstance(candidate.observability, dict) else []
        if candidate.risk == "high" and not observability_signals:
            issues.append(
                {
                    "severity": "warning",
                    "code": "high_risk_observability_gap",
                    "reason": "High-risk candidate has no concrete observability signal; keep the gap visible for review.",
                }
            )

        blocker_count = len([issue for issue in issues if issue["severity"] == "blocker"])
        duplicate_classification = str(duplicate_result.get("classification") or "unknown")
        hallucination_risk = "high" if blocker_count else ("medium" if support_score < 0.1 else "low")
        return {
            "critic": "CriticSubAgent" if critic_selected else "SupervisorVerifier",
            "passed": blocker_count == 0,
            "issues": issues,
            "evidence_support": {
                "evidence_ref_count": len(evidence_refs),
                "low_confidence_ref_count": len(low_confidence),
                "missing_locator_count": len(missing_locators),
                "token_overlap": support_score,
            },
            "duplication_risk": {
                "classification": duplicate_classification,
                "match_count": len(duplicate_result.get("matches") or []),
                "recommendation": duplicate_result.get("recommendation") or "",
            },
            "hallucination_risk": hallucination_risk,
            "observability": {
                "signal_count": len(observability_signals),
                "gap_count": len(observability_gaps) if isinstance(observability_gaps, list) else 0,
            },
        }

    @staticmethod
    def _normalized_module_slug(value: str) -> str:
        slug = re.sub(r"[^a-z0-9-]+", "-", value.strip().lower())
        slug = re.sub(r"-{2,}", "-", slug).strip("-")
        return slug[:80]
