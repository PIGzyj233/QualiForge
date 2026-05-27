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


class GraphContextNodesMixin:
    def load_context(self, state: AgentGraphState) -> dict[str, Any]:
        run = self._run(state)
        self._check_cancelled(run, "load_context:start")
        self._set_run_phase(run, "load_context")

        messages = self.db.scalars(
            select(AgentMessage)
            .where(AgentMessage.conversation_id == run.conversation_id)
            .order_by(AgentMessage.created_at, AgentMessage.id)
            .limit(10)
        ).all()
        coverage = self.db.scalars(
            select(CoverageIndexEntry)
            .where(CoverageIndexEntry.workspace_id == run.workspace_id, CoverageIndexEntry.project_id == run.project_id)
            .order_by(CoverageIndexEntry.updated_at.desc(), CoverageIndexEntry.id.desc())
            .limit(20)
        ).all()
        return {
            "context": {
                "goal": run.goal,
                "project_id": run.project_id,
                "messages": [{"role": item.role, "content_summary": item.content_summary} for item in messages],
                "coverage": [
                    {
                        "module_key": item.module_key,
                        "coverage_state": item.coverage_state,
                        "behavior_summary": item.behavior_summary,
                    }
                    for item in coverage
                ],
            }
        }

    def plan_subagents(self, state: AgentGraphState) -> dict[str, Any]:
        run = self._run(state)
        self._check_cancelled(run, "plan_subagents:start")
        self._set_run_phase(run, "plan_subagents")
        snapshot = dict(run.budget_snapshot or {})
        plan = select_subagent_plan(run=run, snapshot=snapshot)
        selected = list(plan["selected"])
        parallel_groups = list(plan["parallel_groups"])
        max_parallel = max(len(group) for group in parallel_groups)
        existing_plan = dict(snapshot.get("subagent_plan") or {})
        if existing_plan.get("selected") != selected:
            self.budget.check_subagents(selected, parallel_group_size=max_parallel)
        snapshot = dict(run.budget_snapshot or {})
        snapshot["subagent_plan"] = plan
        run.budget_snapshot = snapshot
        self.db.flush()
        self._record_planned_subagents(run, plan)
        return {"subagent_plan": plan}

    def prepare_sandbox(self, state: AgentGraphState) -> dict[str, Any]:
        run = self._run(state)
        repository = self._repository(state)
        self._check_cancelled(run, "prepare_sandbox:start")
        self._set_run_phase(run, "prepare_sandbox")
        sandbox = self._prepare_repository_sandbox(run, repository, state.get("requested_ref") or repository.default_branch)
        return {"sandbox_id": sandbox.id, "worktree_path": sandbox.worktree_path, "resolved_ref": sandbox.resolved_ref}

    def _prepare_repository_sandbox(self, run: AgentRun, repository: GitRepository, requested_ref: str) -> AgentRepositorySandbox:
        root = Path(self.settings.git_sandbox_root).expanduser()
        worktree_path = ensure_safe_sandbox_path(
            root,
            root / run.workspace_id[:8] / repository.project_id[:8] / "agent-worktrees" / run.id[:12] / repository.id[:12],
        )
        sandbox = self.db.scalar(
            select(AgentRepositorySandbox).where(
                AgentRepositorySandbox.agent_run_id == run.id,
                AgentRepositorySandbox.repository_id == repository.id,
                AgentRepositorySandbox.ref == requested_ref,
            )
        )
        if sandbox is None:
            sandbox = AgentRepositorySandbox(
                agent_run_id=run.id,
                repository_id=repository.id,
                workspace_id=run.workspace_id,
                project_id=repository.project_id,
                ref=requested_ref,
                worktree_path=str(worktree_path),
                status=AgentRepositorySandboxStatus.preparing.value,
            )
            self.db.add(sandbox)
            self.db.flush()
        else:
            sandbox.status = AgentRepositorySandboxStatus.preparing.value
            sandbox.error_summary = ""
            sandbox.worktree_path = str(worktree_path)
        self.db.commit()

        try:
            repository_path = ensure_safe_sandbox_path(root, Path(repository.mirror_path))
            resolved_ref = self._resolve_ref(repository_path, requested_ref, repository.sync_timeout_seconds)
            worktree_path.parent.mkdir(parents=True, exist_ok=True)
            if worktree_path.exists():
                remove_tree_readonly(worktree_path)
            self._run_git(["git", "clone", "--shared", "--no-checkout", "--", str(repository_path), str(worktree_path)], repository.sync_timeout_seconds)
            self._run_git(["git", "-C", str(worktree_path), "checkout", "--detach", resolved_ref], repository.sync_timeout_seconds)
            self._mark_files_readonly(worktree_path)
            sandbox.resolved_ref = resolved_ref
            sandbox.status = AgentRepositorySandboxStatus.ready.value
            sandbox.error_summary = ""
            self.db.commit()
            return sandbox
        except Exception as exc:
            sandbox.status = AgentRepositorySandboxStatus.failed.value
            sandbox.error_summary = str(exc)[:700]
            self.db.commit()
            raise

    @staticmethod
    def _resolve_ref(repository_path: Path, requested_ref: str, timeout_seconds: int) -> str:
        result = subprocess.run(
            ["git", "-C", str(repository_path), "rev-parse", "--verify", f"{requested_ref}^{{commit}}"],
            capture_output=True,
            check=False,
            text=True,
            timeout=timeout_seconds,
        )
        if result.returncode != 0:
            detail = result.stderr.strip()[:300] or f"ref {requested_ref} is not available"
            raise RuntimeError(detail)
        return result.stdout.strip()

    @staticmethod
    def _run_git(command: list[str], timeout_seconds: int) -> None:
        result = subprocess.run(command, capture_output=True, check=False, text=True, timeout=timeout_seconds)
        if result.returncode != 0:
            detail = result.stderr.strip()[:500] or f"git exited with {result.returncode}"
            raise RuntimeError(detail)

    @staticmethod
    def _mark_files_readonly(root: Path) -> None:
        for path in root.rglob("*"):
            if path.is_file() and not path.is_symlink():
                path.chmod(0o444)
