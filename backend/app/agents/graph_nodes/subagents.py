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
from app.agents.graph_analysis import evidence_paths, jaccard, normalize_text, select_subagent_plan, signal_values, token_set
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


class GraphSubagentRunsMixin:
    def _subagent_group(self, plan: dict[str, Any], subagent_name: str) -> str:
        for group in plan.get("parallel_groups") or []:
            if isinstance(group, list) and subagent_name in group:
                return "+".join(str(item) for item in group)
        spec = SUBAGENT_REGISTRY.get(subagent_name)
        return spec.parallel_group if spec is not None else "selection"

    def _record_subagent_run(
        self,
        run: AgentRun,
        *,
        subagent_name: str,
        status: AgentSubagentRunStatus,
        stage: str = "",
        parallel_group: str = "",
        summary: str = "",
        input_summary: str = "",
        output_summary: str = "",
        result_snapshot: dict[str, Any] | None = None,
        error_summary: str = "",
    ) -> AgentSubagentRun:
        now = now_utc()
        record = self.db.scalar(
            select(AgentSubagentRun).where(
                AgentSubagentRun.agent_run_id == run.id,
                AgentSubagentRun.subagent_name == subagent_name,
            )
        )
        if record is None:
            spec = SUBAGENT_REGISTRY.get(subagent_name)
            record = AgentSubagentRun(
                agent_run_id=run.id,
                workspace_id=run.workspace_id,
                project_id=run.project_id,
                subagent_name=subagent_name,
                stage=stage or (spec.stage if spec is not None else "selection"),
                parallel_group=parallel_group or (spec.parallel_group if spec is not None else "selection"),
                created_at=now,
            )
            self.db.add(record)
            self.db.flush()
        if stage:
            record.stage = stage
        if parallel_group:
            record.parallel_group = parallel_group
        if summary:
            record.summary = summary[:1000]
        if input_summary:
            record.input_summary = input_summary[:1000]
        if output_summary:
            record.output_summary = output_summary[:1000]
        if result_snapshot is not None:
            record.result_snapshot = result_snapshot
            snapshot = dict(run.budget_snapshot or {})
            subagent_results = dict(snapshot.get("subagent_results") or {})
            subagent_results[subagent_name] = result_snapshot
            snapshot["subagent_results"] = subagent_results
            run.budget_snapshot = snapshot
        record.status = status.value
        record.error_summary = error_summary[:700]
        if status == AgentSubagentRunStatus.running:
            record.started_at = record.started_at or now
            record.completed_at = None
            record.duration_ms = 0
        if status in {
            AgentSubagentRunStatus.succeeded,
            AgentSubagentRunStatus.failed,
            AgentSubagentRunStatus.skipped,
        }:
            if record.started_at is None:
                record.started_at = now
            record.completed_at = now
            record.duration_ms = int(elapsed_seconds(record.started_at, now) * 1000)
        self.db.commit()
        return record

    def _record_planned_subagents(self, run: AgentRun, plan: dict[str, Any]) -> None:
        for name in plan.get("selected") or []:
            spec = SUBAGENT_REGISTRY.get(str(name))
            if spec is None:
                continue
            self._record_subagent_run(
                run,
                subagent_name=spec.name,
                status=AgentSubagentRunStatus.queued,
                stage=spec.stage,
                parallel_group=self._subagent_group(plan, spec.name),
                summary=f"Queued {spec.name}",
                input_summary=plan.get("selection_reasons", {}).get(spec.name, ""),
            )
        for skipped in plan.get("skipped_subagents") or []:
            if not isinstance(skipped, dict):
                continue
            name = str(skipped.get("name") or "")
            if not name:
                continue
            spec = SUBAGENT_REGISTRY.get(name)
            self._record_subagent_run(
                run,
                subagent_name=name,
                status=AgentSubagentRunStatus.skipped,
                stage=spec.stage if spec is not None else "selection",
                parallel_group=spec.parallel_group if spec is not None else "selection",
                summary=f"Skipped {name}: {skipped.get('reason') or 'not selected'}",
                result_snapshot={"reason": skipped.get("reason") or ""},
            )
