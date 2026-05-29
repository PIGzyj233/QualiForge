from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from app.agents.models import AgentRun
from app.platform.config import Settings


class AgentWorkflowUnavailable(RuntimeError):
    """Raised when the durable agent workflow backend cannot accept an operation."""


class AgentWorkflowGateway:
    """Small boundary between HTTP routes and the Temporal implementation."""

    def start_run(
        self,
        *,
        db: Session,
        settings: Settings,
        run: AgentRun,
        workspace_id: str,
        repository_id: str,
        ref: str,
        candidate_limit: int,
        actor_email: str,
    ) -> dict[str, str]:
        from app.agents.temporal import AgentTemporalUnavailable, start_agent_run_workflow

        try:
            return start_agent_run_workflow(
                db=db,
                settings=settings,
                run=run,
                workspace_id=workspace_id,
                repository_id=repository_id,
                ref=ref,
                candidate_limit=candidate_limit,
                actor_email=actor_email,
            )
        except AgentTemporalUnavailable as exc:
            raise AgentWorkflowUnavailable(str(exc)) from exc

    def start_ai_suggestion_run(
        self,
        *,
        db: Session,
        settings: Settings,
        run: AgentRun,
        workspace_id: str,
        project_id: str,
        analysis_id: str,
        actor_email: str,
        force: bool,
    ) -> dict[str, str]:
        from app.agents.temporal import AgentTemporalUnavailable, start_ai_suggestion_workflow

        try:
            return start_ai_suggestion_workflow(
                db=db,
                settings=settings,
                run=run,
                workspace_id=workspace_id,
                project_id=project_id,
                analysis_id=analysis_id,
                actor_email=actor_email,
                force=force,
            )
        except AgentTemporalUnavailable as exc:
            raise AgentWorkflowUnavailable(str(exc)) from exc

    def signal_resume(
        self,
        *,
        db: Session,
        settings: Settings,
        run: AgentRun,
        actor_email: str,
        resume_reason: str,
    ) -> None:
        from app.agents.temporal import AgentTemporalUnavailable, signal_agent_run_resume

        try:
            signal_agent_run_resume(
                db=db,
                settings=settings,
                run=run,
                actor_email=actor_email,
                resume_reason=resume_reason,
            )
        except AgentTemporalUnavailable as exc:
            raise AgentWorkflowUnavailable(str(exc)) from exc

    def cancel(
        self,
        *,
        settings: Settings,
        workflow_id: str,
        cancel_reason: str,
        actor_email: str,
    ) -> None:
        from app.agents.temporal import AgentTemporalUnavailable, cancel_agent_run_workflow

        try:
            cancel_agent_run_workflow(
                settings=settings,
                workflow_id=workflow_id,
                cancel_reason=cancel_reason,
                actor_email=actor_email,
            )
        except AgentTemporalUnavailable as exc:
            raise AgentWorkflowUnavailable(str(exc)) from exc


def get_agent_workflow_gateway(app_state: Any) -> AgentWorkflowGateway:
    gateway = getattr(app_state, "agent_workflow_gateway", None)
    if gateway is None:
        gateway = AgentWorkflowGateway()
        app_state.agent_workflow_gateway = gateway
    return gateway
