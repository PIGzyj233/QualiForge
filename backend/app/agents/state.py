from __future__ import annotations

from app.agents.models import AgentRun, AgentRunStatus
from app.workspace.routes import now_utc


AGENT_RUN_ALLOWED_TRANSITIONS: dict[str, set[str]] = {
    AgentRunStatus.queued.value: {AgentRunStatus.running.value, AgentRunStatus.cancelled.value},
    AgentRunStatus.running.value: {
        AgentRunStatus.succeeded.value,
        AgentRunStatus.failed.value,
        AgentRunStatus.waiting_for_user.value,
        AgentRunStatus.cancelled.value,
    },
    AgentRunStatus.waiting_for_user.value: {AgentRunStatus.running.value, AgentRunStatus.cancelled.value},
    AgentRunStatus.failed.value: {AgentRunStatus.running.value},
    AgentRunStatus.succeeded.value: set(),
    AgentRunStatus.cancelled.value: set(),
}


class AgentRunStateError(ValueError):
    """Raised when an AgentRun status transition is not allowed."""


def _assert_transition(
    run: AgentRun,
    next_status: AgentRunStatus,
    *,
    explicit_resume: bool = False,
    explicit_retry: bool = False,
) -> None:
    current_status = run.status
    target_status = next_status.value
    if target_status not in AGENT_RUN_ALLOWED_TRANSITIONS.get(current_status, set()):
        raise AgentRunStateError(f"Agent run cannot transition from {current_status} to {target_status}")
    if (
        current_status == AgentRunStatus.failed.value
        and target_status == AgentRunStatus.running.value
        and not (explicit_resume or explicit_retry)
    ):
        raise AgentRunStateError("Failed agent runs require an explicit retry or resume")


def assert_run_can_execute(run: AgentRun, *, explicit_resume: bool = False, explicit_retry: bool = False) -> None:
    if run.status == AgentRunStatus.succeeded.value:
        raise AgentRunStateError("Agent run already succeeded")
    if run.status == AgentRunStatus.running.value:
        raise AgentRunStateError("Agent run is already running")
    if run.status == AgentRunStatus.cancelled.value:
        raise AgentRunStateError("Cancelled agent runs cannot be executed")
    _assert_transition(run, AgentRunStatus.running, explicit_resume=explicit_resume, explicit_retry=explicit_retry)


def mark_run_running(run: AgentRun, *, explicit_resume: bool = False, explicit_retry: bool = False) -> None:
    _assert_transition(run, AgentRunStatus.running, explicit_resume=explicit_resume, explicit_retry=explicit_retry)
    run.status = AgentRunStatus.running.value
    run.current_phase = "starting"
    run.started_at = run.started_at or now_utc()
    run.completed_at = None
    run.cancelled_at = None
    run.failure_reason = ""
    run.langgraph_thread_id = run.langgraph_thread_id or f"lg-{run.id}"


def mark_run_waiting(run: AgentRun, reason: str, *, phase: str = "waiting_for_user") -> None:
    _assert_transition(run, AgentRunStatus.waiting_for_user)
    run.status = AgentRunStatus.waiting_for_user.value
    run.current_phase = phase
    run.failure_reason = reason[:700]
    run.completed_at = None


def mark_run_succeeded(run: AgentRun, *, phase: str = "summarize") -> None:
    _assert_transition(run, AgentRunStatus.succeeded)
    run.status = AgentRunStatus.succeeded.value
    run.current_phase = phase
    run.failure_reason = ""
    run.completed_at = now_utc()


def mark_run_failed(run: AgentRun, reason: str, *, phase: str = "failed") -> None:
    _assert_transition(run, AgentRunStatus.failed)
    run.status = AgentRunStatus.failed.value
    run.current_phase = phase
    run.failure_reason = reason[:700]
    run.completed_at = now_utc()


def mark_run_cancelled(run: AgentRun, reason: str = "") -> None:
    _assert_transition(run, AgentRunStatus.cancelled)
    run.status = AgentRunStatus.cancelled.value
    run.current_phase = "cancelled"
    run.failure_reason = reason[:700]
    run.completed_at = now_utc()
    run.cancelled_at = now_utc()

