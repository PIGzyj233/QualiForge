from __future__ import annotations

import asyncio
from datetime import timedelta
from typing import Any

from sqlalchemy.orm import Session
from temporalio.client import Client
from temporalio.exceptions import TemporalError, WorkflowAlreadyStartedError

from app.agents import AgentRun
from app.platform.config import Settings
from app.platform.telemetry import agent_span
from app.workspace.routes import audit
from app.agents.workflows import AISuggestionWorkflow, AgentRunWorkflow


class AgentTemporalUnavailable(RuntimeError):
    """Raised when the Temporal service cannot accept an agent operation."""


def agent_run_workflow_id(run_id: str) -> str:
    return f"agent-run-{run_id}"


async def _connect(settings: Settings) -> Client:
    return await Client.connect(settings.temporal_address, namespace=settings.temporal_namespace)


def _run_temporal(coro):
    try:
        return asyncio.run(coro)
    except TemporalError as exc:
        raise AgentTemporalUnavailable(f"Temporal unavailable: {exc.__class__.__name__}") from exc
    except OSError as exc:
        raise AgentTemporalUnavailable(f"Temporal unavailable: {exc.__class__.__name__}") from exc
    except Exception as exc:
        raise AgentTemporalUnavailable(f"Temporal unavailable: {exc.__class__.__name__}") from exc


def _workflow_payload(
    *,
    settings: Settings,
    workspace_id: str,
    run_id: str,
    project_id: str,
    repository_id: str,
    ref: str,
    candidate_limit: int,
    actor_email: str,
) -> dict[str, Any]:
    return {
        "workspace_id": workspace_id,
        "run_id": run_id,
        "project_id": project_id,
        "repository_id": repository_id,
        "ref": ref,
        "candidate_limit": candidate_limit,
        "actor_email": actor_email,
        "activity_start_to_close_timeout_seconds": settings.agent_activity_start_to_close_timeout_minutes * 60,
        "activity_heartbeat_timeout_seconds": settings.agent_activity_heartbeat_timeout_seconds,
        "activity_retry_attempts": settings.agent_activity_retry_attempts,
    }


def _ai_suggestion_workflow_payload(
    *,
    settings: Settings,
    workspace_id: str,
    project_id: str,
    analysis_id: str,
    run_id: str,
    actor_email: str,
    force: bool,
) -> dict[str, Any]:
    return {
        "workspace_id": workspace_id,
        "project_id": project_id,
        "analysis_id": analysis_id,
        "run_id": run_id,
        "actor_email": actor_email,
        "force": force,
        "activity_start_to_close_timeout_seconds": settings.agent_activity_start_to_close_timeout_minutes * 60,
        "activity_heartbeat_timeout_seconds": settings.agent_activity_heartbeat_timeout_seconds,
        "activity_retry_attempts": settings.agent_activity_retry_attempts,
    }


def _workflow_child_tasks(run: AgentRun) -> list[dict[str, Any]]:
    snapshot = dict(run.budget_snapshot or {})
    raw_tasks = snapshot.get("child_tasks") or []
    if not isinstance(raw_tasks, list):
        return []

    child_tasks: list[dict[str, Any]] = []
    for raw_task in raw_tasks[:8]:
        if not isinstance(raw_task, dict):
            continue
        task_kind = str(raw_task.get("task_kind") or raw_task.get("kind") or "").strip()
        if not task_kind:
            continue
        child_tasks.append(
            {
                "task_kind": task_kind[:80],
                "summary": str(raw_task.get("summary") or task_kind)[:500],
                "payload": raw_task.get("payload") if isinstance(raw_task.get("payload"), dict) else {},
            }
        )
    return child_tasks


def start_agent_run_workflow(
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
    workflow_id = agent_run_workflow_id(run.id)
    payload = _workflow_payload(
        settings=settings,
        workspace_id=workspace_id,
        run_id=run.id,
        project_id=run.project_id or "",
        repository_id=repository_id,
        ref=ref,
        candidate_limit=candidate_limit,
        actor_email=actor_email,
    )
    child_tasks = _workflow_child_tasks(run)
    if child_tasks:
        payload["child_tasks"] = child_tasks

    async def _start() -> None:
        client = await _connect(settings)
        try:
            await client.start_workflow(
                AgentRunWorkflow.run,
                payload,
                id=workflow_id,
                task_queue=settings.agent_task_queue,
                execution_timeout=timedelta(minutes=settings.agent_workflow_timeout_minutes),
            )
        except WorkflowAlreadyStartedError:
            return

    with agent_span(
        "temporal.workflow.start",
        run_id=run.id,
        workflow_id=workflow_id,
        task_queue=settings.agent_task_queue,
        child_task_count=len(child_tasks),
    ):
        _run_temporal(_start())
    run.temporal_workflow_id = workflow_id
    run.current_phase = "temporal_queued"
    db.flush()
    audit(
        db,
        workspace_id=workspace_id,
        actor_email=actor_email,
        action="agent_run.workflow_started",
        entity_type="AgentRun",
        entity_id=run.id,
        summary=f"Started Temporal workflow {workflow_id}",
        after={"temporal_workflow_id": workflow_id, "task_queue": settings.agent_task_queue, "child_task_count": len(child_tasks)},
    )
    db.commit()
    return {"workflow_id": workflow_id, "summary": "Agent workflow started"}


def start_ai_suggestion_workflow(
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
    workflow_id = agent_run_workflow_id(run.id)
    payload = _ai_suggestion_workflow_payload(
        settings=settings,
        workspace_id=workspace_id,
        project_id=project_id,
        analysis_id=analysis_id,
        run_id=run.id,
        actor_email=actor_email,
        force=force,
    )

    async def _start() -> None:
        client = await _connect(settings)
        try:
            await client.start_workflow(
                AISuggestionWorkflow.run,
                payload,
                id=workflow_id,
                task_queue=settings.agent_task_queue,
                execution_timeout=timedelta(minutes=settings.agent_workflow_timeout_minutes),
            )
        except WorkflowAlreadyStartedError:
            return

    with agent_span("temporal.workflow.start", run_id=run.id, workflow_id=workflow_id, task_queue=settings.agent_task_queue):
        _run_temporal(_start())
    run.temporal_workflow_id = workflow_id
    run.current_phase = "temporal_queued"
    db.flush()
    audit(
        db,
        workspace_id=workspace_id,
        actor_email=actor_email,
        action="agent_run.workflow_started",
        entity_type="AgentRun",
        entity_id=run.id,
        summary=f"Started AI suggestion Temporal workflow {workflow_id}",
        after={"temporal_workflow_id": workflow_id, "task_queue": settings.agent_task_queue, "diff_analysis_id": analysis_id},
    )
    db.commit()
    return {"workflow_id": workflow_id, "summary": "AI suggestion workflow started"}


def signal_agent_run_resume(
    *,
    db: Session,
    settings: Settings,
    run: AgentRun,
    actor_email: str,
    resume_reason: str,
) -> None:
    workflow_id = run.temporal_workflow_id or agent_run_workflow_id(run.id)
    payload = {
        "budget_snapshot": dict(run.budget_snapshot or {}),
        "resume_reason": resume_reason,
        "actor_email": actor_email,
    }

    async def _signal() -> None:
        client = await _connect(settings)
        handle = client.get_workflow_handle(workflow_id)
        await handle.signal(AgentRunWorkflow.resume_with_budget, payload)

    with agent_span("temporal.workflow.signal", run_id=run.id, workflow_id=workflow_id, signal="resume_with_budget"):
        _run_temporal(_signal())
    run.current_phase = "resume_signal_sent"
    db.commit()


def cancel_agent_run_workflow(*, settings: Settings, workflow_id: str, cancel_reason: str = "", actor_email: str = "") -> None:
    async def _cancel() -> None:
        client = await _connect(settings)
        handle = client.get_workflow_handle(workflow_id)
        await handle.signal(
            AgentRunWorkflow.cancel_with_reason,
            {
                "cancel_reason": cancel_reason or "Agent run cancelled by user",
                "actor_email": actor_email,
            },
        )
        await handle.cancel()

    with agent_span("temporal.workflow.cancel", workflow_id=workflow_id):
        _run_temporal(_cancel())
