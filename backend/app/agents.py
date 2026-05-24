from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from pydantic import BaseModel, Field
from sqlalchemy import JSON, Boolean, DateTime, ForeignKey, Integer, String, select
from sqlalchemy.orm import Mapped, Session, mapped_column

from app.database import Base
from app.workspaces import ActorEmail, audit, get_project_or_404, get_workspace_or_404, new_id, now_utc


class AgentConversationStatus(StrEnum):
    active = "active"
    archived = "archived"


class AgentRunMode(StrEnum):
    preview = "preview"
    execute = "execute"


class AgentRunStatus(StrEnum):
    queued = "queued"
    running = "running"
    waiting_for_user = "waiting_for_user"
    succeeded = "succeeded"
    failed = "failed"
    cancelled = "cancelled"


class AgentMessageRole(StrEnum):
    user = "user"
    assistant = "assistant"
    system = "system"
    tool = "tool"


class AgentStagedOutputStatus(StrEnum):
    staged = "staged"
    accepted = "accepted"
    rejected = "rejected"


class AgentToolCallStatus(StrEnum):
    queued = "queued"
    running = "running"
    succeeded = "succeeded"
    failed = "failed"


class AgentRepositorySandboxStatus(StrEnum):
    preparing = "preparing"
    ready = "ready"
    failed = "failed"
    cleaned = "cleaned"


class AgentApprovalStatus(StrEnum):
    pending = "pending"
    approved = "approved"
    rejected = "rejected"
    cancelled = "cancelled"


class AgentStagedOutputType(StrEnum):
    case_candidate = "case_candidate"
    regression_recommendation = "regression_recommendation"
    report_draft = "report_draft"
    coverage_update = "coverage_update"
    agent_note = "agent_note"


class EvidenceKind(StrEnum):
    import_cell_range = "import_cell_range"
    import_row = "import_row"
    code_file = "code_file"
    grep_result = "grep_result"
    diff_hunk = "diff_hunk"
    diff_analysis = "diff_analysis"
    test_case = "test_case"
    case_revision = "case_revision"
    module_mapping_rule = "module_mapping_rule"
    user_message = "user_message"
    memory_entry = "memory_entry"
    audit_event = "audit_event"
    metric = "metric"
    trace_point = "trace_point"
    log_signal = "log_signal"


class AgentConversation(Base):
    __tablename__ = "agent_conversations"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    workspace_id: Mapped[str] = mapped_column(ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False, index=True)
    project_id: Mapped[str | None] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), nullable=True, index=True)
    title: Mapped[str] = mapped_column(String(220), nullable=False)
    status: Mapped[str] = mapped_column(String(32), default=AgentConversationStatus.active.value, nullable=False, index=True)
    created_by: Mapped[str] = mapped_column(String(254), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc, nullable=False, index=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc, onupdate=now_utc, nullable=False)


class AgentRun(Base):
    __tablename__ = "agent_runs"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    conversation_id: Mapped[str] = mapped_column(ForeignKey("agent_conversations.id", ondelete="CASCADE"), nullable=False, index=True)
    workspace_id: Mapped[str] = mapped_column(ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False, index=True)
    project_id: Mapped[str | None] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), nullable=True, index=True)
    goal: Mapped[str] = mapped_column(String(1000), nullable=False)
    mode: Mapped[str] = mapped_column(String(32), default=AgentRunMode.preview.value, nullable=False, index=True)
    trigger_type: Mapped[str] = mapped_column(String(40), default="user_message", nullable=False)
    status: Mapped[str] = mapped_column(String(32), default=AgentRunStatus.queued.value, nullable=False, index=True)
    current_phase: Mapped[str] = mapped_column(String(80), default="created", nullable=False)
    created_by: Mapped[str] = mapped_column(String(254), nullable=False)
    temporal_workflow_id: Mapped[str] = mapped_column(String(160), default="", nullable=False)
    langgraph_thread_id: Mapped[str] = mapped_column(String(160), default="", nullable=False)
    budget_snapshot: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    failure_reason: Mapped[str] = mapped_column(String(700), default="", nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc, nullable=False, index=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    cancelled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class AgentMessage(Base):
    __tablename__ = "agent_messages"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    conversation_id: Mapped[str] = mapped_column(ForeignKey("agent_conversations.id", ondelete="CASCADE"), nullable=False, index=True)
    agent_run_id: Mapped[str | None] = mapped_column(ForeignKey("agent_runs.id", ondelete="SET NULL"), nullable=True, index=True)
    role: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    content: Mapped[str] = mapped_column(String(8000), nullable=False)
    content_summary: Mapped[str] = mapped_column(String(700), default="", nullable=False)
    message_metadata: Mapped[dict[str, Any]] = mapped_column("metadata", JSON, default=dict, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc, nullable=False, index=True)


class AgentToolCall(Base):
    __tablename__ = "agent_tool_calls"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    agent_run_id: Mapped[str] = mapped_column(ForeignKey("agent_runs.id", ondelete="CASCADE"), nullable=False, index=True)
    parent_tool_call_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    subagent_name: Mapped[str] = mapped_column(String(80), default="", nullable=False, index=True)
    tool_name: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    permission_level: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    input_summary: Mapped[str] = mapped_column(String(700), nullable=False)
    output_summary: Mapped[str] = mapped_column(String(1000), default="", nullable=False)
    status: Mapped[str] = mapped_column(String(32), default=AgentToolCallStatus.queued.value, nullable=False, index=True)
    idempotency_key: Mapped[str] = mapped_column(String(160), default="", nullable=False, index=True)
    duration_ms: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    error_summary: Mapped[str] = mapped_column(String(700), default="", nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc, nullable=False, index=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class AgentRepositorySandbox(Base):
    __tablename__ = "agent_repository_sandboxes"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    agent_run_id: Mapped[str] = mapped_column(ForeignKey("agent_runs.id", ondelete="CASCADE"), nullable=False, index=True)
    repository_id: Mapped[str] = mapped_column(ForeignKey("git_repositories.id", ondelete="CASCADE"), nullable=False, index=True)
    workspace_id: Mapped[str] = mapped_column(ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False, index=True)
    project_id: Mapped[str | None] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), nullable=True, index=True)
    ref: Mapped[str] = mapped_column(String(160), nullable=False, index=True)
    resolved_ref: Mapped[str] = mapped_column(String(160), default="", nullable=False)
    worktree_path: Mapped[str] = mapped_column(String(1000), nullable=False)
    status: Mapped[str] = mapped_column(String(32), default=AgentRepositorySandboxStatus.preparing.value, nullable=False, index=True)
    error_summary: Mapped[str] = mapped_column(String(700), default="", nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc, nullable=False, index=True)
    cleaned_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class AgentApproval(Base):
    __tablename__ = "agent_approvals"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    agent_run_id: Mapped[str] = mapped_column(ForeignKey("agent_runs.id", ondelete="CASCADE"), nullable=False, index=True)
    approval_type: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(32), default=AgentApprovalStatus.pending.value, nullable=False, index=True)
    requested_by: Mapped[str] = mapped_column(String(254), nullable=False)
    decided_by: Mapped[str] = mapped_column(String(254), default="", nullable=False)
    request_summary: Mapped[str] = mapped_column(String(1000), nullable=False)
    decision_summary: Mapped[str] = mapped_column(String(1000), default="", nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc, nullable=False, index=True)
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class AgentStagedOutput(Base):
    __tablename__ = "agent_staged_outputs"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    agent_run_id: Mapped[str] = mapped_column(ForeignKey("agent_runs.id", ondelete="CASCADE"), nullable=False, index=True)
    workspace_id: Mapped[str] = mapped_column(ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False, index=True)
    project_id: Mapped[str | None] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), nullable=True, index=True)
    output_type: Mapped[str] = mapped_column(String(60), nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(32), default=AgentStagedOutputStatus.staged.value, nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(240), nullable=False)
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    evidence_refs: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list, nullable=False)
    quality_result: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    duplicate_result: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    coverage_entries: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list, nullable=False)
    decision_summary: Mapped[str] = mapped_column(String(700), default="", nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc, nullable=False, index=True)
    decided_by: Mapped[str] = mapped_column(String(254), default="", nullable=False)
    accepted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    rejected_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class CoverageIndexEntry(Base):
    __tablename__ = "coverage_index_entries"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    workspace_id: Mapped[str] = mapped_column(ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False, index=True)
    project_id: Mapped[str | None] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), nullable=True, index=True)
    source_type: Mapped[str] = mapped_column(String(60), nullable=False, index=True)
    source_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    coverage_state: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    module_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    module_key: Mapped[str] = mapped_column(String(80), default="UNMAPPED", nullable=False, index=True)
    behavior_summary: Mapped[str] = mapped_column(String(700), nullable=False)
    signals: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list, nullable=False)
    evidence_refs: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list, nullable=False)
    confidence: Mapped[int] = mapped_column(Integer, default=70, nullable=False)
    verified_by_human: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc, nullable=False, index=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc, onupdate=now_utc, nullable=False)


class AgentConversationCreate(BaseModel):
    title: str = Field(min_length=1, max_length=220)
    project_id: str | None = Field(default=None, max_length=64)


class AgentConversationResponse(BaseModel):
    id: str
    workspace_id: str
    project_id: str | None
    title: str
    status: str
    created_by: str
    created_at: datetime
    updated_at: datetime


class AgentRunCreate(BaseModel):
    goal: str = Field(min_length=1, max_length=1000)
    mode: AgentRunMode = AgentRunMode.preview
    trigger_type: str = Field(default="user_message", max_length=40)
    project_id: str | None = Field(default=None, max_length=64)
    budget_snapshot: dict[str, Any] = Field(default_factory=dict)


class AgentRunResponse(BaseModel):
    id: str
    conversation_id: str
    workspace_id: str
    project_id: str | None
    goal: str
    mode: str
    trigger_type: str
    status: str
    current_phase: str
    created_by: str
    temporal_workflow_id: str
    langgraph_thread_id: str
    budget_snapshot: dict[str, Any]
    failure_reason: str
    created_at: datetime
    started_at: datetime | None
    completed_at: datetime | None
    cancelled_at: datetime | None


class AgentRunExecuteRequest(BaseModel):
    repository_id: str = Field(min_length=1, max_length=64)
    ref: str = Field(default="", max_length=160)
    candidate_limit: int = Field(default=3, ge=1, le=5)


class AgentMessageCreate(BaseModel):
    role: AgentMessageRole = AgentMessageRole.user
    content: str = Field(min_length=1, max_length=8000)
    agent_run_id: str | None = Field(default=None, max_length=64)
    metadata: dict[str, Any] = Field(default_factory=dict)


class AgentMessageResponse(BaseModel):
    id: str
    conversation_id: str
    agent_run_id: str | None
    role: str
    content: str
    content_summary: str
    metadata: dict[str, Any]
    created_at: datetime


class EvidenceRef(BaseModel):
    kind: EvidenceKind
    ref_id: str = Field(default="", max_length=240)
    label: str = Field(default="", max_length=300)
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    summary: str = Field(default="", max_length=700)
    source: str = Field(default="", max_length=120)


class CoverageEntryCreate(BaseModel):
    module_id: str | None = Field(default=None, max_length=64)
    module_key: str = Field(default="UNMAPPED", max_length=80)
    behavior_summary: str = Field(min_length=1, max_length=700)
    signals: list[dict[str, Any]] = Field(default_factory=list)
    evidence_refs: list[EvidenceRef] = Field(default_factory=list)
    confidence: int = Field(default=70, ge=0, le=100)
    verified_by_human: bool = False


class CoverageEntryResponse(BaseModel):
    id: str
    workspace_id: str
    project_id: str | None
    source_type: str
    source_id: str
    coverage_state: str
    module_id: str | None
    module_key: str
    behavior_summary: str
    signals: list[dict[str, Any]]
    evidence_refs: list[dict[str, Any]]
    confidence: int
    verified_by_human: bool
    created_at: datetime
    updated_at: datetime


class AgentToolCallCreate(BaseModel):
    tool_name: str = Field(min_length=1, max_length=120)
    permission_level: str = Field(min_length=1, max_length=40)
    input_summary: str = Field(min_length=1, max_length=700)
    parent_tool_call_id: str | None = Field(default=None, max_length=64)
    subagent_name: str = Field(default="", max_length=80)
    output_summary: str = Field(default="", max_length=1000)
    status: AgentToolCallStatus = AgentToolCallStatus.succeeded
    idempotency_key: str = Field(default="", max_length=160)
    duration_ms: int = Field(default=0, ge=0)
    error_summary: str = Field(default="", max_length=700)


class AgentToolCallResponse(BaseModel):
    id: str
    agent_run_id: str
    parent_tool_call_id: str | None
    subagent_name: str
    tool_name: str
    permission_level: str
    input_summary: str
    output_summary: str
    status: str
    idempotency_key: str
    duration_ms: int
    error_summary: str
    created_at: datetime
    completed_at: datetime | None


class AgentRepositorySandboxResponse(BaseModel):
    id: str
    agent_run_id: str
    repository_id: str
    workspace_id: str
    project_id: str | None
    ref: str
    resolved_ref: str
    worktree_path: str
    status: str
    error_summary: str
    created_at: datetime
    cleaned_at: datetime | None


class AgentApprovalCreate(BaseModel):
    approval_type: str = Field(min_length=1, max_length=80)
    request_summary: str = Field(min_length=1, max_length=1000)


class AgentApprovalDecision(BaseModel):
    status: AgentApprovalStatus
    decision_summary: str = Field(default="", max_length=1000)


class AgentApprovalResponse(BaseModel):
    id: str
    agent_run_id: str
    approval_type: str
    status: str
    requested_by: str
    decided_by: str
    request_summary: str
    decision_summary: str
    created_at: datetime
    decided_at: datetime | None


class AgentStagedOutputCreate(BaseModel):
    output_type: AgentStagedOutputType
    title: str = Field(min_length=1, max_length=240)
    payload: dict[str, Any] = Field(default_factory=dict)
    evidence_refs: list[EvidenceRef] = Field(default_factory=list)
    quality_result: dict[str, Any] = Field(default_factory=dict)
    duplicate_result: dict[str, Any] = Field(default_factory=dict)
    coverage_entries: list[CoverageEntryCreate] = Field(default_factory=list)


class AgentStagedOutputUpdate(BaseModel):
    status: AgentStagedOutputStatus
    decision_summary: str = Field(default="", max_length=500)


class AgentStagedOutputResponse(BaseModel):
    id: str
    agent_run_id: str
    workspace_id: str
    project_id: str | None
    output_type: str
    status: str
    title: str
    payload: dict[str, Any]
    evidence_refs: list[dict[str, Any]]
    quality_result: dict[str, Any]
    duplicate_result: dict[str, Any]
    created_at: datetime
    decided_by: str
    decision_summary: str
    accepted_at: datetime | None
    rejected_at: datetime | None
    coverage_entries: list[CoverageEntryResponse] = Field(default_factory=list)


class AgentRunExecuteResponse(BaseModel):
    run: AgentRunResponse
    summary: str
    staged_outputs: list[AgentStagedOutputResponse] = Field(default_factory=list)
    tool_calls: list[AgentToolCallResponse] = Field(default_factory=list)
    sandboxes: list[AgentRepositorySandboxResponse] = Field(default_factory=list)


def get_db(request: Request):
    yield from request.app.state.database.session()


DbSession = Annotated[Session, Depends(get_db)]

router = APIRouter(prefix="/api/workspaces/{workspace_id}", tags=["agents"])


def evidence_refs_to_json(refs: list[EvidenceRef]) -> list[dict[str, Any]]:
    return [ref.model_dump(mode="json") for ref in refs]


def conversation_to_response(conversation: AgentConversation) -> AgentConversationResponse:
    return AgentConversationResponse(
        id=conversation.id,
        workspace_id=conversation.workspace_id,
        project_id=conversation.project_id,
        title=conversation.title,
        status=conversation.status,
        created_by=conversation.created_by,
        created_at=conversation.created_at,
        updated_at=conversation.updated_at,
    )


def run_to_response(run: AgentRun) -> AgentRunResponse:
    return AgentRunResponse(
        id=run.id,
        conversation_id=run.conversation_id,
        workspace_id=run.workspace_id,
        project_id=run.project_id,
        goal=run.goal,
        mode=run.mode,
        trigger_type=run.trigger_type,
        status=run.status,
        current_phase=run.current_phase,
        created_by=run.created_by,
        temporal_workflow_id=run.temporal_workflow_id,
        langgraph_thread_id=run.langgraph_thread_id,
        budget_snapshot=run.budget_snapshot,
        failure_reason=run.failure_reason,
        created_at=run.created_at,
        started_at=run.started_at,
        completed_at=run.completed_at,
        cancelled_at=run.cancelled_at,
    )


def message_to_response(message: AgentMessage) -> AgentMessageResponse:
    return AgentMessageResponse(
        id=message.id,
        conversation_id=message.conversation_id,
        agent_run_id=message.agent_run_id,
        role=message.role,
        content=message.content,
        content_summary=message.content_summary,
        metadata=message.message_metadata,
        created_at=message.created_at,
    )


def coverage_to_response(entry: CoverageIndexEntry) -> CoverageEntryResponse:
    return CoverageEntryResponse(
        id=entry.id,
        workspace_id=entry.workspace_id,
        project_id=entry.project_id,
        source_type=entry.source_type,
        source_id=entry.source_id,
        coverage_state=entry.coverage_state,
        module_id=entry.module_id,
        module_key=entry.module_key,
        behavior_summary=entry.behavior_summary,
        signals=entry.signals,
        evidence_refs=entry.evidence_refs,
        confidence=entry.confidence,
        verified_by_human=entry.verified_by_human,
        created_at=entry.created_at,
        updated_at=entry.updated_at,
    )


def tool_call_to_response(tool_call: AgentToolCall) -> AgentToolCallResponse:
    return AgentToolCallResponse(
        id=tool_call.id,
        agent_run_id=tool_call.agent_run_id,
        parent_tool_call_id=tool_call.parent_tool_call_id,
        subagent_name=tool_call.subagent_name,
        tool_name=tool_call.tool_name,
        permission_level=tool_call.permission_level,
        input_summary=tool_call.input_summary,
        output_summary=tool_call.output_summary,
        status=tool_call.status,
        idempotency_key=tool_call.idempotency_key,
        duration_ms=tool_call.duration_ms,
        error_summary=tool_call.error_summary,
        created_at=tool_call.created_at,
        completed_at=tool_call.completed_at,
    )


def sandbox_to_response(sandbox: AgentRepositorySandbox) -> AgentRepositorySandboxResponse:
    return AgentRepositorySandboxResponse(
        id=sandbox.id,
        agent_run_id=sandbox.agent_run_id,
        repository_id=sandbox.repository_id,
        workspace_id=sandbox.workspace_id,
        project_id=sandbox.project_id,
        ref=sandbox.ref,
        resolved_ref=sandbox.resolved_ref,
        worktree_path=sandbox.worktree_path,
        status=sandbox.status,
        error_summary=sandbox.error_summary,
        created_at=sandbox.created_at,
        cleaned_at=sandbox.cleaned_at,
    )


def approval_to_response(approval: AgentApproval) -> AgentApprovalResponse:
    return AgentApprovalResponse(
        id=approval.id,
        agent_run_id=approval.agent_run_id,
        approval_type=approval.approval_type,
        status=approval.status,
        requested_by=approval.requested_by,
        decided_by=approval.decided_by,
        request_summary=approval.request_summary,
        decision_summary=approval.decision_summary,
        created_at=approval.created_at,
        decided_at=approval.decided_at,
    )


def coverage_snapshot(entry: CoverageIndexEntry) -> dict[str, Any]:
    return {
        "id": entry.id,
        "workspace_id": entry.workspace_id,
        "project_id": entry.project_id,
        "source_type": entry.source_type,
        "source_id": entry.source_id,
        "coverage_state": entry.coverage_state,
        "module_id": entry.module_id,
        "module_key": entry.module_key,
        "behavior_summary": entry.behavior_summary,
        "signals": entry.signals,
        "evidence_refs": entry.evidence_refs,
        "confidence": entry.confidence,
        "verified_by_human": entry.verified_by_human,
    }


def staged_output_to_response(db: Session, output: AgentStagedOutput) -> AgentStagedOutputResponse:
    coverage = db.scalars(
        select(CoverageIndexEntry)
        .where(CoverageIndexEntry.source_type == "staged_output", CoverageIndexEntry.source_id == output.id)
        .order_by(CoverageIndexEntry.created_at, CoverageIndexEntry.id)
    ).all()
    return AgentStagedOutputResponse(
        id=output.id,
        agent_run_id=output.agent_run_id,
        workspace_id=output.workspace_id,
        project_id=output.project_id,
        output_type=output.output_type,
        status=output.status,
        title=output.title,
        payload=output.payload,
        evidence_refs=output.evidence_refs,
        quality_result=output.quality_result,
        duplicate_result=output.duplicate_result,
        created_at=output.created_at,
        decided_by=output.decided_by,
        decision_summary=output.decision_summary,
        accepted_at=output.accepted_at,
        rejected_at=output.rejected_at,
        coverage_entries=[coverage_to_response(entry) for entry in coverage],
    )


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


def assert_project_scope(db: Session, workspace_id: str, project_id: str | None) -> None:
    if project_id:
        get_project_or_404(db, workspace_id, project_id)


def add_coverage_entries(
    db: Session,
    *,
    workspace_id: str,
    project_id: str | None,
    source_type: str,
    source_id: str,
    coverage_state: str,
    entries: list[CoverageEntryCreate],
) -> list[CoverageIndexEntry]:
    created: list[CoverageIndexEntry] = []
    for payload in entries:
        entry = CoverageIndexEntry(
            workspace_id=workspace_id,
            project_id=project_id,
            source_type=source_type,
            source_id=source_id,
            coverage_state=coverage_state,
            module_id=payload.module_id,
            module_key=payload.module_key or "UNMAPPED",
            behavior_summary=payload.behavior_summary,
            signals=payload.signals,
            evidence_refs=evidence_refs_to_json(payload.evidence_refs),
            confidence=payload.confidence,
            verified_by_human=payload.verified_by_human,
        )
        db.add(entry)
        created.append(entry)
    return created


@router.post("/agent/conversations", response_model=AgentConversationResponse, status_code=status.HTTP_201_CREATED)
def create_agent_conversation(
    workspace_id: str,
    payload: AgentConversationCreate,
    db: DbSession,
    actor_email: ActorEmail,
) -> AgentConversationResponse:
    get_workspace_or_404(db, workspace_id)
    assert_project_scope(db, workspace_id, payload.project_id)
    conversation = AgentConversation(
        workspace_id=workspace_id,
        project_id=payload.project_id,
        title=payload.title,
        created_by=actor_email,
    )
    db.add(conversation)
    db.flush()
    audit(
        db,
        workspace_id=workspace_id,
        actor_email=actor_email,
        action="agent_conversation.created",
        entity_type="AgentConversation",
        entity_id=conversation.id,
        summary=f"Created agent conversation {conversation.title}",
        after={"project_id": conversation.project_id, "title": conversation.title},
    )
    db.commit()
    db.refresh(conversation)
    return conversation_to_response(conversation)


@router.get("/agent/conversations", response_model=list[AgentConversationResponse])
def list_agent_conversations(
    workspace_id: str,
    db: DbSession,
    project_id: str | None = Query(default=None, max_length=64),
) -> list[AgentConversationResponse]:
    get_workspace_or_404(db, workspace_id)
    statement = select(AgentConversation).where(AgentConversation.workspace_id == workspace_id)
    if project_id:
        statement = statement.where(AgentConversation.project_id == project_id)
    conversations = db.scalars(statement.order_by(AgentConversation.updated_at.desc(), AgentConversation.id.desc())).all()
    return [conversation_to_response(conversation) for conversation in conversations]


@router.post(
    "/agent/conversations/{conversation_id}/messages",
    response_model=AgentMessageResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_agent_message(
    workspace_id: str,
    conversation_id: str,
    payload: AgentMessageCreate,
    db: DbSession,
    actor_email: ActorEmail,
) -> AgentMessageResponse:
    conversation = get_conversation_or_404(db, workspace_id, conversation_id)
    if payload.agent_run_id:
        run = get_run_or_404(db, workspace_id, payload.agent_run_id)
        if run.conversation_id != conversation.id:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Agent run is not in this conversation")
    content_summary = payload.content[:240]
    message = AgentMessage(
        conversation_id=conversation.id,
        agent_run_id=payload.agent_run_id,
        role=payload.role.value,
        content=payload.content,
        content_summary=content_summary,
        message_metadata=payload.metadata,
    )
    conversation.updated_at = now_utc()
    db.add(message)
    db.flush()
    audit(
        db,
        workspace_id=workspace_id,
        actor_email=actor_email,
        action="agent_message.created",
        entity_type="AgentMessage",
        entity_id=message.id,
        summary=f"Recorded {message.role} agent message",
        after={"conversation_id": conversation.id, "agent_run_id": message.agent_run_id, "role": message.role},
    )
    db.commit()
    db.refresh(message)
    return message_to_response(message)


@router.get("/agent/conversations/{conversation_id}/messages", response_model=list[AgentMessageResponse])
def list_agent_messages(workspace_id: str, conversation_id: str, db: DbSession) -> list[AgentMessageResponse]:
    get_conversation_or_404(db, workspace_id, conversation_id)
    messages = db.scalars(
        select(AgentMessage).where(AgentMessage.conversation_id == conversation_id).order_by(AgentMessage.created_at, AgentMessage.id)
    ).all()
    return [message_to_response(message) for message in messages]


@router.post("/agent/conversations/{conversation_id}/runs", response_model=AgentRunResponse, status_code=status.HTTP_201_CREATED)
def create_agent_run(
    workspace_id: str,
    conversation_id: str,
    payload: AgentRunCreate,
    db: DbSession,
    actor_email: ActorEmail,
) -> AgentRunResponse:
    conversation = get_conversation_or_404(db, workspace_id, conversation_id)
    project_id = payload.project_id or conversation.project_id
    assert_project_scope(db, workspace_id, project_id)
    run = AgentRun(
        conversation_id=conversation.id,
        workspace_id=workspace_id,
        project_id=project_id,
        goal=payload.goal,
        mode=payload.mode.value,
        trigger_type=payload.trigger_type,
        created_by=actor_email,
        budget_snapshot=payload.budget_snapshot,
    )
    conversation.updated_at = now_utc()
    db.add(run)
    db.flush()
    audit(
        db,
        workspace_id=workspace_id,
        actor_email=actor_email,
        action="agent_run.created",
        entity_type="AgentRun",
        entity_id=run.id,
        summary=f"Created {run.mode} agent run",
        after={"conversation_id": conversation.id, "goal": run.goal, "mode": run.mode, "project_id": run.project_id},
    )
    db.commit()
    db.refresh(run)
    return run_to_response(run)


@router.get("/agent/conversations/{conversation_id}/runs", response_model=list[AgentRunResponse])
def list_agent_runs(workspace_id: str, conversation_id: str, db: DbSession) -> list[AgentRunResponse]:
    get_conversation_or_404(db, workspace_id, conversation_id)
    runs = db.scalars(
        select(AgentRun).where(AgentRun.conversation_id == conversation_id).order_by(AgentRun.created_at.desc(), AgentRun.id.desc())
    ).all()
    return [run_to_response(run) for run in runs]


@router.post("/agent/runs/{run_id}/execute", response_model=AgentRunExecuteResponse)
def execute_agent_run(
    workspace_id: str,
    run_id: str,
    payload: AgentRunExecuteRequest,
    db: DbSession,
    request: Request,
    actor_email: ActorEmail,
) -> AgentRunExecuteResponse:
    run = get_run_or_404(db, workspace_id, run_id)
    if run.mode != AgentRunMode.execute.value:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Agent execute requires an execute mode run")

    from app.agent_graph import AgentGraphConflict, execute_agent_graph

    try:
        result = execute_agent_graph(
            db=db,
            settings=request.app.state.settings,
            workspace_id=workspace_id,
            run_id=run_id,
            repository_id=payload.repository_id,
            ref=payload.ref,
            candidate_limit=payload.candidate_limit,
            actor_email=actor_email,
            model_gateway_transport=getattr(request.app.state, "model_gateway_transport", None),
        )
    except AgentGraphConflict as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc

    return AgentRunExecuteResponse(
        run=run_to_response(result.run),
        summary=result.summary,
        staged_outputs=[staged_output_to_response(db, output) for output in result.staged_outputs],
        tool_calls=[tool_call_to_response(tool_call) for tool_call in result.tool_calls],
        sandboxes=[sandbox_to_response(sandbox) for sandbox in result.sandboxes],
    )


@router.post("/agent/runs/{run_id}/staged-outputs", response_model=AgentStagedOutputResponse, status_code=status.HTTP_201_CREATED)
def create_staged_output(
    workspace_id: str,
    run_id: str,
    payload: AgentStagedOutputCreate,
    db: DbSession,
    actor_email: ActorEmail,
) -> AgentStagedOutputResponse:
    run = get_run_or_404(db, workspace_id, run_id)
    if run.mode != AgentRunMode.execute.value:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Staged outputs require an execute agent run")

    output = AgentStagedOutput(
        agent_run_id=run.id,
        workspace_id=workspace_id,
        project_id=run.project_id,
        output_type=payload.output_type.value,
        title=payload.title,
        payload=payload.payload,
        evidence_refs=evidence_refs_to_json(payload.evidence_refs),
        quality_result=payload.quality_result,
        duplicate_result=payload.duplicate_result,
    )
    db.add(output)
    db.flush()
    coverage_entries = add_coverage_entries(
        db,
        workspace_id=workspace_id,
        project_id=run.project_id,
        source_type="staged_output",
        source_id=output.id,
        coverage_state=AgentStagedOutputStatus.staged.value,
        entries=payload.coverage_entries,
    )
    db.flush()
    output.coverage_entries = [coverage_snapshot(entry) for entry in coverage_entries]
    audit(
        db,
        workspace_id=workspace_id,
        actor_email=actor_email,
        action="agent_staged_output.created",
        entity_type="AgentStagedOutput",
        entity_id=output.id,
        summary=f"Created staged {output.output_type}: {output.title}",
        after={"agent_run_id": run.id, "output_type": output.output_type, "coverage_entries": len(payload.coverage_entries)},
    )
    db.commit()
    db.refresh(output)
    return staged_output_to_response(db, output)


@router.get("/agent/runs/{run_id}/staged-outputs", response_model=list[AgentStagedOutputResponse])
def list_staged_outputs(workspace_id: str, run_id: str, db: DbSession) -> list[AgentStagedOutputResponse]:
    get_run_or_404(db, workspace_id, run_id)
    outputs = db.scalars(
        select(AgentStagedOutput)
        .where(AgentStagedOutput.agent_run_id == run_id, AgentStagedOutput.workspace_id == workspace_id)
        .order_by(AgentStagedOutput.created_at, AgentStagedOutput.id)
    ).all()
    return [staged_output_to_response(db, output) for output in outputs]


@router.post("/agent/runs/{run_id}/tool-calls", response_model=AgentToolCallResponse, status_code=status.HTTP_201_CREATED)
def record_tool_call(
    workspace_id: str,
    run_id: str,
    payload: AgentToolCallCreate,
    db: DbSession,
    actor_email: ActorEmail,
) -> AgentToolCallResponse:
    get_run_or_404(db, workspace_id, run_id)
    now = now_utc()
    tool_call = AgentToolCall(
        agent_run_id=run_id,
        parent_tool_call_id=payload.parent_tool_call_id,
        subagent_name=payload.subagent_name,
        tool_name=payload.tool_name,
        permission_level=payload.permission_level,
        input_summary=payload.input_summary,
        output_summary=payload.output_summary,
        status=payload.status.value,
        idempotency_key=payload.idempotency_key,
        duration_ms=payload.duration_ms,
        error_summary=payload.error_summary,
        completed_at=now if payload.status in {AgentToolCallStatus.succeeded, AgentToolCallStatus.failed} else None,
    )
    db.add(tool_call)
    db.flush()
    audit(
        db,
        workspace_id=workspace_id,
        actor_email=actor_email,
        action="agent_tool_call.recorded",
        entity_type="AgentToolCall",
        entity_id=tool_call.id,
        summary=f"Recorded {tool_call.permission_level} tool call {tool_call.tool_name}",
        after={
            "agent_run_id": run_id,
            "tool_name": tool_call.tool_name,
            "permission_level": tool_call.permission_level,
            "status": tool_call.status,
            "subagent_name": tool_call.subagent_name,
        },
    )
    db.commit()
    db.refresh(tool_call)
    return tool_call_to_response(tool_call)


@router.get("/agent/runs/{run_id}/tool-calls", response_model=list[AgentToolCallResponse])
def list_tool_calls(workspace_id: str, run_id: str, db: DbSession) -> list[AgentToolCallResponse]:
    get_run_or_404(db, workspace_id, run_id)
    tool_calls = db.scalars(
        select(AgentToolCall).where(AgentToolCall.agent_run_id == run_id).order_by(AgentToolCall.created_at, AgentToolCall.id)
    ).all()
    return [tool_call_to_response(tool_call) for tool_call in tool_calls]


@router.post("/agent/runs/{run_id}/approvals", response_model=AgentApprovalResponse, status_code=status.HTTP_201_CREATED)
def request_approval(
    workspace_id: str,
    run_id: str,
    payload: AgentApprovalCreate,
    db: DbSession,
    actor_email: ActorEmail,
) -> AgentApprovalResponse:
    get_run_or_404(db, workspace_id, run_id)
    approval = AgentApproval(
        agent_run_id=run_id,
        approval_type=payload.approval_type,
        requested_by=actor_email,
        request_summary=payload.request_summary,
    )
    db.add(approval)
    db.flush()
    audit(
        db,
        workspace_id=workspace_id,
        actor_email=actor_email,
        action="agent_approval.requested",
        entity_type="AgentApproval",
        entity_id=approval.id,
        summary=f"Requested agent approval for {approval.approval_type}",
        after={"agent_run_id": run_id, "approval_type": approval.approval_type, "status": approval.status},
    )
    db.commit()
    db.refresh(approval)
    return approval_to_response(approval)


@router.get("/agent/runs/{run_id}/approvals", response_model=list[AgentApprovalResponse])
def list_approvals(workspace_id: str, run_id: str, db: DbSession) -> list[AgentApprovalResponse]:
    get_run_or_404(db, workspace_id, run_id)
    approvals = db.scalars(
        select(AgentApproval).where(AgentApproval.agent_run_id == run_id).order_by(AgentApproval.created_at, AgentApproval.id)
    ).all()
    return [approval_to_response(approval) for approval in approvals]


@router.patch("/agent/approvals/{approval_id}", response_model=AgentApprovalResponse)
def decide_approval(
    workspace_id: str,
    approval_id: str,
    payload: AgentApprovalDecision,
    db: DbSession,
    actor_email: ActorEmail,
) -> AgentApprovalResponse:
    approval = get_approval_or_404(db, workspace_id, approval_id)
    if approval.status != AgentApprovalStatus.pending.value:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Agent approval has already been decided")
    if payload.status == AgentApprovalStatus.pending:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Approval decision cannot be pending")
    approval.status = payload.status.value
    approval.decided_by = actor_email
    approval.decision_summary = payload.decision_summary
    approval.decided_at = now_utc()
    audit(
        db,
        workspace_id=workspace_id,
        actor_email=actor_email,
        action=f"agent_approval.{approval.status}",
        entity_type="AgentApproval",
        entity_id=approval.id,
        summary=payload.decision_summary or f"{approval.status.title()} agent approval {approval.approval_type}",
        after={"status": approval.status, "approval_type": approval.approval_type},
    )
    db.commit()
    db.refresh(approval)
    return approval_to_response(approval)


@router.patch("/agent/staged-outputs/{output_id}", response_model=AgentStagedOutputResponse)
def decide_staged_output(
    workspace_id: str,
    output_id: str,
    payload: AgentStagedOutputUpdate,
    db: DbSession,
    actor_email: ActorEmail,
) -> AgentStagedOutputResponse:
    output = get_staged_output_or_404(db, workspace_id, output_id)
    if output.status != AgentStagedOutputStatus.staged.value:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Staged output has already been decided")
    now = now_utc()
    output.status = payload.status.value
    output.decided_by = actor_email
    output.decision_summary = payload.decision_summary
    if payload.status == AgentStagedOutputStatus.accepted:
        output.accepted_at = now
        next_coverage_state = "candidate"
        action = "agent_staged_output.accepted"
    elif payload.status == AgentStagedOutputStatus.rejected:
        output.rejected_at = now
        next_coverage_state = "rejected"
        action = "agent_staged_output.rejected"
    else:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Decision must accept or reject staged output")

    coverage_entries = db.scalars(
        select(CoverageIndexEntry).where(CoverageIndexEntry.source_type == "staged_output", CoverageIndexEntry.source_id == output.id)
    ).all()
    for entry in coverage_entries:
        entry.coverage_state = next_coverage_state
        entry.updated_at = now
        entry.verified_by_human = payload.status == AgentStagedOutputStatus.accepted
    output.coverage_entries = [coverage_snapshot(entry) for entry in coverage_entries]

    audit(
        db,
        workspace_id=workspace_id,
        actor_email=actor_email,
        action=action,
        entity_type="AgentStagedOutput",
        entity_id=output.id,
        summary=payload.decision_summary or f"{payload.status.value.title()} staged output {output.title}",
        after={"status": output.status, "coverage_state": next_coverage_state},
    )
    db.commit()
    db.refresh(output)
    return staged_output_to_response(db, output)


@router.get("/projects/{project_id}/coverage-index", response_model=list[CoverageEntryResponse])
def list_project_coverage(
    workspace_id: str,
    project_id: str,
    db: DbSession,
    coverage_state: str | None = Query(default=None, max_length=32),
    module_key: str | None = Query(default=None, max_length=80),
) -> list[CoverageEntryResponse]:
    get_project_or_404(db, workspace_id, project_id)
    statement = select(CoverageIndexEntry).where(
        CoverageIndexEntry.workspace_id == workspace_id,
        CoverageIndexEntry.project_id == project_id,
    )
    if coverage_state:
        statement = statement.where(CoverageIndexEntry.coverage_state == coverage_state)
    if module_key:
        statement = statement.where(CoverageIndexEntry.module_key == module_key)
    entries = db.scalars(statement.order_by(CoverageIndexEntry.updated_at.desc(), CoverageIndexEntry.id.desc())).all()
    return [coverage_to_response(entry) for entry in entries]
