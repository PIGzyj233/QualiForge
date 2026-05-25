from __future__ import annotations

import subprocess
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.agents import (
    AgentRepositorySandbox,
    AgentRepositorySandboxStatus,
    AgentRun,
    AgentStagedOutput,
    AgentToolCall,
)
from app.agents.graph_types import AgentRunExecutionResult
from app.git.sandbox import remove_tree_readonly
from app.workspace.routes import now_utc


def execution_result_from_db(
    db: Session,
    *,
    run: AgentRun,
    workspace_id: str,
    repository_id: str,
    summary: str,
) -> AgentRunExecutionResult:
    staged_outputs = db.scalars(
        select(AgentStagedOutput)
        .where(AgentStagedOutput.agent_run_id == run.id, AgentStagedOutput.workspace_id == workspace_id)
        .order_by(AgentStagedOutput.created_at, AgentStagedOutput.id)
    ).all()
    tool_calls = db.scalars(
        select(AgentToolCall).where(AgentToolCall.agent_run_id == run.id).order_by(AgentToolCall.created_at, AgentToolCall.id)
    ).all()
    sandboxes = db.scalars(
        select(AgentRepositorySandbox)
        .where(AgentRepositorySandbox.agent_run_id == run.id, AgentRepositorySandbox.repository_id == repository_id)
        .order_by(AgentRepositorySandbox.created_at, AgentRepositorySandbox.id)
    ).all()
    return AgentRunExecutionResult(
        run=run,
        summary=summary,
        staged_outputs=list(staged_outputs),
        tool_calls=list(tool_calls),
        sandboxes=list(sandboxes),
    )


def cleanup_agent_sandboxes(db: Session, *, run_id: str, repository_id: str) -> None:
    sandboxes = db.scalars(
        select(AgentRepositorySandbox).where(
            AgentRepositorySandbox.agent_run_id == run_id,
            AgentRepositorySandbox.repository_id == repository_id,
            AgentRepositorySandbox.status.in_(
                [AgentRepositorySandboxStatus.preparing.value, AgentRepositorySandboxStatus.ready.value]
            ),
        )
    ).all()
    for sandbox in sandboxes:
        worktree = Path(sandbox.worktree_path)
        if not worktree.exists():
            sandbox.status = AgentRepositorySandboxStatus.cleaned.value
            sandbox.cleaned_at = now_utc()
            continue
        try:
            dirty = git_status_clean_check(worktree)
        except Exception as exc:
            sandbox.status = AgentRepositorySandboxStatus.failed.value
            sandbox.error_summary = f"cleanup_anomaly: could not inspect worktree: {str(exc)[:500]}"
            continue
        if dirty:
            sandbox.status = AgentRepositorySandboxStatus.failed.value
            sandbox.error_summary = f"cleanup_anomaly: dirty worktree retained: {dirty[:500]}"
            continue
        try:
            remove_tree_readonly(worktree)
        except OSError as exc:
            sandbox.status = AgentRepositorySandboxStatus.failed.value
            sandbox.error_summary = f"cleanup_failed: {str(exc)[:500]}"
            continue
        sandbox.status = AgentRepositorySandboxStatus.cleaned.value
        sandbox.error_summary = ""
        sandbox.cleaned_at = now_utc()
    if sandboxes:
        db.commit()


def git_status_clean_check(worktree: Path) -> str:
    result = subprocess.run(
        ["git", "-C", str(worktree), "-c", "core.filemode=false", "status", "--short"],
        capture_output=True,
        check=False,
        text=True,
        timeout=10,
    )
    if result.returncode != 0:
        raise RuntimeError((result.stderr or result.stdout).strip()[:500] or f"git status exited {result.returncode}")
    return result.stdout.strip()


