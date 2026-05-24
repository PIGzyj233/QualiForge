from __future__ import annotations

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.agents.models import AgentApproval, AgentConversation, AgentMemoryFile, AgentRun, AgentStagedOutput
from app.workspace.routes import get_project_or_404


def get_conversation_or_404(db: Session, workspace_id: str, conversation_id: str) -> AgentConversation:
    conversation = db.scalar(
        select(AgentConversation).where(
            AgentConversation.id == conversation_id,
            AgentConversation.workspace_id == workspace_id,
        )
    )
    if conversation is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Agent conversation not found")
    return conversation


def get_run_or_404(db: Session, workspace_id: str, run_id: str) -> AgentRun:
    run = db.scalar(select(AgentRun).where(AgentRun.id == run_id, AgentRun.workspace_id == workspace_id))
    if run is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Agent run not found")
    return run


def get_staged_output_or_404(db: Session, workspace_id: str, output_id: str) -> AgentStagedOutput:
    output = db.scalar(
        select(AgentStagedOutput).where(
            AgentStagedOutput.id == output_id,
            AgentStagedOutput.workspace_id == workspace_id,
        )
    )
    if output is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Agent staged output not found")
    return output


def get_approval_or_404(db: Session, workspace_id: str, approval_id: str) -> AgentApproval:
    approval = db.scalar(
        select(AgentApproval)
        .join(AgentRun, AgentRun.id == AgentApproval.agent_run_id)
        .where(AgentApproval.id == approval_id, AgentRun.workspace_id == workspace_id)
    )
    if approval is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Agent approval not found")
    return approval


def get_memory_file_or_404(db: Session, workspace_id: str, memory_file_id: str) -> AgentMemoryFile:
    memory_file = db.scalar(
        select(AgentMemoryFile).where(AgentMemoryFile.id == memory_file_id, AgentMemoryFile.workspace_id == workspace_id)
    )
    if memory_file is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Agent memory file not found")
    return memory_file


def assert_project_scope(db: Session, workspace_id: str, project_id: str | None) -> None:
    if project_id:
        get_project_or_404(db, workspace_id, project_id)
