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


class GraphStagingNodesMixin:
    @staticmethod
    def _candidate_model(raw: dict[str, Any]) -> GeneratedCaseCandidate:
        return GeneratedCaseCandidate.model_validate(
            {key: raw[key] for key in GeneratedCaseCandidate.model_fields if key in raw}
        )

    def write_staged_outputs(self, state: AgentGraphState) -> dict[str, Any]:
        run = self._run(state)
        if run.mode != AgentRunMode.execute.value:
            raise RuntimeError("Staged outputs require execute mode")
        self._check_cancelled(run, "write_staged_outputs:start")
        self._set_run_phase(run, "write_staged_outputs")
        if self._is_module_tree_draft_run(run):
            return self.write_module_tree_draft_output(state)
        candidate_items = [
            (self._candidate_model(raw), dict(raw.get("critic_result") or {}))
            for raw in state.get("verified_candidates", [])
            if isinstance(raw, dict)
        ]
        created_ids: list[str] = []
        for candidate, critic_result in candidate_items:
            self._check_cancelled(run, "write_staged_outputs:candidate")
            output_payload = {
                "steps": candidate.steps,
                "expected_result": candidate.expected_result,
                "risk": candidate.risk,
                "priority": candidate.priority,
                "module_key": candidate.module_key,
                "unmapped_reason": candidate.unmapped_reason,
                "observability": candidate.observability,
                "repository_id": state["repository_id"],
                "ref": state["requested_ref"],
                "resolved_ref": state["resolved_ref"],
            }
            output_key = staged_output_idempotency_key(
                run.id,
                AgentStagedOutputType.case_candidate.value,
                {
                    "title": candidate.title,
                    "payload": output_payload,
                    "evidence_refs": evidence_refs_to_json(candidate.evidence_refs),
                    "coverage_entries": [entry.model_dump(mode="json") for entry in candidate.coverage_entries],
                },
            )
            existing_output = self.db.scalar(
                select(AgentStagedOutput).where(
                    AgentStagedOutput.agent_run_id == run.id,
                    AgentStagedOutput.idempotency_key == output_key,
                )
            )
            if existing_output is not None:
                created_ids.append(existing_output.id)
                continue
            output = AgentStagedOutput(
                agent_run_id=run.id,
                workspace_id=run.workspace_id,
                project_id=run.project_id,
                output_type=AgentStagedOutputType.case_candidate.value,
                idempotency_key=output_key,
                title=candidate.title,
                payload=output_payload,
                evidence_refs=evidence_refs_to_json(candidate.evidence_refs),
                quality_result={
                    "passed": bool(critic_result.get("passed", True)),
                    "checks": [
                        "schema_valid",
                        "steps_executable",
                        "expected_result_observable",
                        "module_mapping_present",
                        "evidence_refs_present",
                        "coverage_entries_present",
                        "critic_passed",
                    ],
                    "critic_result": critic_result,
                },
                duplicate_result=candidate.duplicate_result,
            )
            self.db.add(output)
            self.db.flush()
            coverage_entries = add_coverage_entries(
                self.db,
                workspace_id=run.workspace_id,
                project_id=run.project_id,
                source_type="staged_output",
                source_id=output.id,
                coverage_state=AgentStagedOutputStatus.staged.value,
                entries=candidate.coverage_entries,
            )
            self.db.flush()
            output.coverage_entries = [coverage_snapshot(entry) for entry in coverage_entries]
            audit(
                self.db,
                workspace_id=run.workspace_id,
                actor_email=self.actor_email,
                action="agent_staged_output.created",
                entity_type="AgentStagedOutput",
                entity_id=output.id,
                summary=f"Created staged {output.output_type}: {output.title}",
                after={"agent_run_id": run.id, "output_type": output.output_type, "coverage_entries": len(coverage_entries)},
            )
            created_ids.append(output.id)
        for recommendation in state.get("reuse_recommendations", []):
            self._check_cancelled(run, "write_staged_outputs:reuse_note")
            note_payload = {
                "note_type": "coverage_reuse",
                "candidate_title": recommendation["title"],
                "module_key": recommendation["module_key"],
                "risk": recommendation["risk"],
                "priority": recommendation["priority"],
                "recommendation": recommendation["recommendation"],
                "matches": recommendation["duplicate_result"].get("matches", []),
                "repository_id": state["repository_id"],
                "ref": state["requested_ref"],
                "resolved_ref": state["resolved_ref"],
            }
            note_evidence_refs = evidence_refs_to_json(self._candidate_model(recommendation["candidate"]).evidence_refs)
            note_key = staged_output_idempotency_key(
                run.id,
                AgentStagedOutputType.agent_note.value,
                {
                    "title": f"Reuse existing coverage for {recommendation['title']}",
                    "payload": note_payload,
                    "evidence_refs": note_evidence_refs,
                    "duplicate_result": recommendation["duplicate_result"],
                },
            )
            existing_note = self.db.scalar(
                select(AgentStagedOutput).where(
                    AgentStagedOutput.agent_run_id == run.id,
                    AgentStagedOutput.idempotency_key == note_key,
                )
            )
            if existing_note is not None:
                created_ids.append(existing_note.id)
                continue
            output = AgentStagedOutput(
                agent_run_id=run.id,
                workspace_id=run.workspace_id,
                project_id=run.project_id,
                output_type=AgentStagedOutputType.agent_note.value,
                idempotency_key=note_key,
                title=f"Reuse existing coverage for {recommendation['title']}",
                payload=note_payload,
                evidence_refs=note_evidence_refs,
                quality_result={"passed": True, "checks": ["duplicate_lookup_performed", "reuse_or_extend_recommended"]},
                duplicate_result=recommendation["duplicate_result"],
            )
            self.db.add(output)
            self.db.flush()
            audit(
                self.db,
                workspace_id=run.workspace_id,
                actor_email=self.actor_email,
                action="agent_staged_output.created",
                entity_type="AgentStagedOutput",
                entity_id=output.id,
                summary=f"Created staged agent note: {output.title}",
                after={"agent_run_id": run.id, "output_type": output.output_type, "coverage_entries": 0},
            )
            created_ids.append(output.id)
        return {"staged_output_ids": created_ids, "subagent_results": state.get("subagent_results", {})}

    def write_module_tree_draft_output(self, state: AgentGraphState) -> dict[str, Any]:
        run = self._run(state)
        payload = dict(state.get("verified_module_tree_draft") or {})
        if not payload.get("items"):
            raise RuntimeError("Verified module tree draft is empty")
        evidence_refs = []
        for item in payload.get("items", []):
            if isinstance(item, dict):
                evidence_refs.extend(ref for ref in item.get("evidence_refs", []) if isinstance(ref, dict))
            if len(evidence_refs) >= 30:
                break
        output_key = staged_output_idempotency_key(
            run.id,
            AgentStagedOutputType.module_tree_draft.value,
            {
                "repository_id": state["repository_id"],
                "resolved_ref": state["resolved_ref"],
                "items": payload.get("items", []),
            },
        )
        existing = self.db.scalar(
            select(AgentStagedOutput).where(
                AgentStagedOutput.agent_run_id == run.id,
                AgentStagedOutput.idempotency_key == output_key,
            )
        )
        if existing is not None:
            return {"staged_output_ids": [existing.id], "subagent_results": state.get("subagent_results", {})}
        output = AgentStagedOutput(
            agent_run_id=run.id,
            workspace_id=run.workspace_id,
            project_id=run.project_id,
            output_type=AgentStagedOutputType.module_tree_draft.value,
            idempotency_key=output_key,
            title=f"模块目录参考 - {payload.get('repository_name') or state['repository_id']} @ {state['resolved_ref'][:12]}",
            payload=payload,
            evidence_refs=evidence_refs[:30],
            quality_result=payload.get("quality_result") or {"passed": True},
            duplicate_result={},
        )
        self.db.add(output)
        self.db.flush()
        audit(
            self.db,
            workspace_id=run.workspace_id,
            actor_email=self.actor_email,
            action="agent_staged_output.created",
            entity_type="AgentStagedOutput",
            entity_id=output.id,
            summary=f"Created staged module tree draft: {output.title}",
            after={
                "agent_run_id": run.id,
                "output_type": output.output_type,
                "module_count": len(payload.get("items", [])),
                "repository_id": state["repository_id"],
                "resolved_ref": state["resolved_ref"],
            },
        )
        return {"staged_output_ids": [output.id], "subagent_results": state.get("subagent_results", {})}

    def summarize(self, state: AgentGraphState) -> dict[str, Any]:
        run = self._run(state)
        self._check_cancelled(run, "summarize:start")
        if self._is_module_tree_draft_run(run):
            module_count = len((state.get("verified_module_tree_draft") or {}).get("items", []))
            summary = (
                f"Generated {module_count} staged module draft item(s) from repository {state['repository_id']} "
                f"at {state['resolved_ref'][:12]}."
            )
        else:
            candidate_count = len(state.get("verified_candidates", []))
            reuse_count = len(state.get("reuse_recommendations", []))
            summary = (
                f"Generated {candidate_count} staged case candidate(s) and {reuse_count} reuse/extend note(s) "
                f"from repository {state['repository_id']} at {state['resolved_ref'][:12]}."
            )
        if state.get("subagent_results"):
            snapshot = dict(run.budget_snapshot or {})
            subagent_results = dict(snapshot.get("subagent_results") or {})
            subagent_results.update(state["subagent_results"])
            snapshot["subagent_results"] = subagent_results
            run.budget_snapshot = snapshot
        mark_run_succeeded(run)
        append_daily_project_memory(self.db, settings=self.settings, run=run, actor_email=self.actor_email, summary=summary)
        self.db.commit()
        return {"summary": summary}
