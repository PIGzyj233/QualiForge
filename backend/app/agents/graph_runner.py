from __future__ import annotations

import time
from pathlib import Path
from typing import Callable

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.agents import (
    AgentRepositorySandbox,
    AgentRun,
    AgentRunMode,
    AgentRunStatus,
    assert_run_can_execute,
    mark_run_failed,
    mark_run_running,
    mark_run_waiting,
)
from app.agents.graph_executor import AgentGraphExecutor
from app.agents.graph_policy import enforce_agent_ai_policy
from app.agents.graph_results import cleanup_agent_sandboxes, execution_result_from_db
from app.agents.graph_types import (
    AgentBudgetExceeded,
    AgentGraphConflict,
    AgentGraphState,
    AgentPolicyViolation,
    AgentRunCancelled,
    AgentRunExecutionResult,
)
from app.ai.model_gateway import Transport
from app.git.models import GitRepository, RepositoryStatus
from app.platform.config import Settings
from app.platform.telemetry import AGENT_RUN_DURATION_SECONDS, AGENT_RUN_QUEUE_TIME_SECONDS, AGENT_RUNS_TOTAL, elapsed_seconds


def execute_agent_graph(
    *,
    db: Session,
    settings: Settings,
    workspace_id: str,
    run_id: str,
    repository_id: str,
    ref: str,
    candidate_limit: int,
    actor_email: str,
    model_gateway_transport: Transport | None = None,
    explicit_resume: bool = False,
    cancellation_checker: Callable[[str], None] | None = None,
) -> AgentRunExecutionResult:
    execution_started = time.monotonic()
    run = db.get(AgentRun, run_id)
    repository = db.get(GitRepository, repository_id)
    if run is None or run.workspace_id != workspace_id:
        raise AgentGraphConflict("Agent run not found")
    if repository is None or repository.workspace_id != workspace_id:
        raise AgentGraphConflict("Repository not found")
    if run.mode != AgentRunMode.execute.value:
        raise AgentGraphConflict("Agent execute requires an execute mode run")
    if run.project_id and run.project_id != repository.project_id:
        raise AgentGraphConflict("Agent run project does not match repository project")
    requested_ref = ref or repository.default_branch
    if run.status == AgentRunStatus.succeeded.value:
        matching = db.scalar(
            select(AgentRepositorySandbox).where(
                AgentRepositorySandbox.agent_run_id == run.id,
                AgentRepositorySandbox.repository_id == repository.id,
                AgentRepositorySandbox.ref == requested_ref,
            )
        )
        if matching is not None:
            return execution_result_from_db(
                db,
                run=run,
                workspace_id=workspace_id,
                repository_id=repository_id,
                summary="Agent run already succeeded for this repository/ref; returning existing staged outputs.",
            )
        raise AgentGraphConflict("Agent run already succeeded for a different repository/ref")
    try:
        assert_run_can_execute(run, explicit_resume=explicit_resume)
    except ValueError as exc:
        raise AgentGraphConflict(str(exc)) from exc
    if repository.status != RepositoryStatus.synced.value or not Path(repository.mirror_path).exists():
        raise AgentGraphConflict("Repository must be synced before agent execute")

    snapshot = dict(run.budget_snapshot or {})
    snapshot["last_execute_request"] = {
        "repository_id": repository_id,
        "ref": requested_ref,
        "candidate_limit": candidate_limit,
    }
    run.budget_snapshot = snapshot
    if run.project_id is None:
        run.project_id = repository.project_id
    enforce_agent_ai_policy(db, settings=settings, run=run, actor_email=actor_email)
    had_started_at = run.started_at is not None
    mark_run_running(run, explicit_resume=explicit_resume)
    if not had_started_at and run.started_at is not None:
        AGENT_RUN_QUEUE_TIME_SECONDS.observe(elapsed_seconds(run.created_at, run.started_at))
    db.commit()

    try:
        executor = AgentGraphExecutor(
            db=db,
            settings=settings,
            run=run,
            actor_email=actor_email,
            candidate_limit=candidate_limit,
            model_gateway_transport=model_gateway_transport,
            cancellation_checker=cancellation_checker,
        )
        final_state = executor.execute(
            {
                "workspace_id": workspace_id,
                "run_id": run_id,
                "repository_id": repository_id,
                "requested_ref": requested_ref,
            }
        )
        summary = final_state.get("summary", "Agent run completed")
    except AgentBudgetExceeded as exc:
        db.rollback()
        run = db.get(AgentRun, run_id)
        if run is not None:
            mark_run_waiting(run, str(exc), phase="budget_waiting")
            db.commit()
        summary = f"Agent run is waiting for budget input: {str(exc)[:300]}"
    except AgentRunCancelled as exc:
        db.rollback()
        run = db.get(AgentRun, run_id)
        if run is not None and run.status != AgentRunStatus.cancelled.value:
            try:
                from app.agents import mark_run_cancelled

                mark_run_cancelled(run, str(exc))
            except ValueError:
                run.status = AgentRunStatus.cancelled.value
                run.current_phase = "cancelled"
                run.failure_reason = str(exc)[:700]
            db.commit()
        summary = f"Agent run cancelled: {str(exc)[:300]}"
    except Exception as exc:
        db.rollback()
        run = db.get(AgentRun, run_id)
        if run is not None:
            if run.status == AgentRunStatus.cancelled.value:
                summary = f"Agent run cancelled: {run.failure_reason[:300]}"
            else:
                mark_run_failed(run, str(exc))
                summary = f"Agent run failed: {str(exc)[:300]}"
            db.commit()
        else:
            summary = f"Agent run failed: {str(exc)[:300]}"
    finally:
        cleanup_agent_sandboxes(db, run_id=run_id, repository_id=repository_id)

    refreshed_run = db.get(AgentRun, run_id) or run
    AGENT_RUNS_TOTAL.labels(status=refreshed_run.status).inc()
    AGENT_RUN_DURATION_SECONDS.observe(time.monotonic() - execution_started)
    return execution_result_from_db(
        db,
        run=refreshed_run,
        workspace_id=workspace_id,
        repository_id=repository_id,
        summary=summary,
    )
