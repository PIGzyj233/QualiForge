from __future__ import annotations

from typing import Any, Callable

from langgraph.graph import END, START, StateGraph
from sqlalchemy.orm import Session

from app.ai.model_gateway import Transport, urllib_transport
from app.agents import AgentRun, AgentRunStatus, AgentStagedOutputType
from app.agents.graph_budget import BudgetTracker
from app.agents.graph_nodes.context import GraphContextNodesMixin
from app.agents.graph_nodes.generation import GraphGenerationNodesMixin
from app.agents.graph_nodes.staging import GraphStagingNodesMixin
from app.agents.graph_nodes.subagents import GraphSubagentRunsMixin
from app.agents.graph_nodes.tool_loop import GraphToolLoopNodesMixin
from app.agents.graph_nodes.verification import GraphVerificationNodesMixin
from app.agents.graph_types import AgentGraphState, AgentRunCancelled
from app.git.models import GitRepository
from app.platform.config import Settings
from app.platform.telemetry import agent_span


class AgentGraphExecutor(
    GraphSubagentRunsMixin,
    GraphContextNodesMixin,
    GraphToolLoopNodesMixin,
    GraphGenerationNodesMixin,
    GraphVerificationNodesMixin,
    GraphStagingNodesMixin,
):
    def __init__(
        self,
        *,
        db: Session,
        settings: Settings,
        run: AgentRun,
        actor_email: str,
        candidate_limit: int,
        model_gateway_transport: Transport | None,
        cancellation_checker: Callable[[str], None] | None = None,
    ):
        self.db = db
        self.settings = settings
        self.run_id = run.id
        self.actor_email = actor_email
        self.budget = BudgetTracker(db=db, settings=settings, run=run, requested_candidate_limit=candidate_limit)
        self.candidate_limit = self.budget.effective_candidate_limit
        self.model_gateway_transport = model_gateway_transport or urllib_transport
        self.cancellation_checker = cancellation_checker

    @staticmethod
    def _requested_output_type(run: AgentRun) -> str:
        snapshot = dict(run.budget_snapshot or {})
        return str(snapshot.get("output_type") or snapshot.get("requested_output_type") or AgentStagedOutputType.case_candidate.value)

    @classmethod
    def _is_module_tree_draft_run(cls, run: AgentRun) -> bool:
        return cls._requested_output_type(run) == AgentStagedOutputType.module_tree_draft.value

    def execute(self, initial_state: AgentGraphState) -> AgentGraphState:
        with agent_span("agent.graph.execute", run_id=self.run_id):
            return self._execute(initial_state)

    def _node(
        self, name: str, handler: Callable[[AgentGraphState], dict[str, Any]]
    ) -> Callable[[AgentGraphState], dict[str, Any]]:
        def wrapped(state: AgentGraphState) -> dict[str, Any]:
            with agent_span("agent.langgraph.node", run_id=str(state.get("run_id") or self.run_id), node=name):
                return handler(state)

        wrapped.__name__ = f"{name}_node"
        return wrapped

    def _execute(self, initial_state: AgentGraphState) -> AgentGraphState:
        builder = StateGraph(AgentGraphState)
        builder.add_node("load_context", self._node("load_context", self.load_context))
        builder.add_node("plan_subagents", self._node("plan_subagents", self.plan_subagents))
        builder.add_node("prepare_sandbox", self._node("prepare_sandbox", self.prepare_sandbox))
        builder.add_node("code_tool_loop", self._node("code_tool_loop", self.code_tool_loop))
        builder.add_node("generate_candidates", self._node("generate_candidates", self.generate_candidates))
        builder.add_node("verify", self._node("verify", self.verify))
        builder.add_node("write_staged_outputs", self._node("write_staged_outputs", self.write_staged_outputs))
        builder.add_node("summarize", self._node("summarize", self.summarize))
        builder.add_edge(START, "load_context")
        builder.add_edge("load_context", "plan_subagents")
        builder.add_edge("plan_subagents", "prepare_sandbox")
        builder.add_edge("prepare_sandbox", "code_tool_loop")
        builder.add_edge("code_tool_loop", "generate_candidates")
        builder.add_edge("generate_candidates", "verify")
        builder.add_edge("verify", "write_staged_outputs")
        builder.add_edge("write_staged_outputs", "summarize")
        builder.add_edge("summarize", END)
        return builder.compile().invoke(initial_state)

    def _run(self, state: AgentGraphState) -> AgentRun:
        run = self.db.get(AgentRun, state["run_id"])
        if run is None:
            raise RuntimeError("Agent run no longer exists")
        return run

    def _repository(self, state: AgentGraphState) -> GitRepository:
        repository = self.db.get(GitRepository, state["repository_id"])
        if repository is None:
            raise RuntimeError("Repository no longer exists")
        return repository

    def _set_run_phase(self, run: AgentRun, phase: str) -> None:
        self._check_cancelled(run, f"{phase}:phase")
        run.current_phase = phase
        self.db.commit()
        self._check_cancelled(run, f"{phase}:committed")

    def _check_cancelled(self, run: AgentRun, phase: str) -> None:
        if self.cancellation_checker is not None:
            self.cancellation_checker(phase)
        self.db.expire(run)
        if run.status == AgentRunStatus.cancelled.value:
            raise AgentRunCancelled("Agent run was cancelled")
