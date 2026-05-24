from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, status
from pydantic import BaseModel, Field
from sqlalchemy import JSON, Boolean, DateTime, ForeignKey, Integer, String, UniqueConstraint, select
from sqlalchemy.orm import Mapped, Session, mapped_column

from app.ai_config import AIInvocationLog, AIInvocationResponse, invocation_to_response
from app.database import Base
from app.telemetry import (
    AGENT_APPROVAL_WAIT_SECONDS,
    AGENT_STAGED_OUTPUT_DECISIONS_TOTAL,
    AGENT_TOOL_CALLS_TOTAL,
    AGENT_TOOL_DURATION_SECONDS,
    elapsed_seconds,
)
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


class AgentSubagentRunStatus(StrEnum):
    queued = "queued"
    running = "running"
    succeeded = "succeeded"
    failed = "failed"
    skipped = "skipped"


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


class AgentSubagentRun(Base):
    __tablename__ = "agent_subagent_runs"
    __table_args__ = (UniqueConstraint("agent_run_id", "subagent_name", name="uq_agent_subagent_run_name"),)

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    agent_run_id: Mapped[str] = mapped_column(ForeignKey("agent_runs.id", ondelete="CASCADE"), nullable=False, index=True)
    workspace_id: Mapped[str] = mapped_column(ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False, index=True)
    project_id: Mapped[str | None] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), nullable=True, index=True)
    subagent_name: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    stage: Mapped[str] = mapped_column(String(80), default="", nullable=False, index=True)
    parallel_group: Mapped[str] = mapped_column(String(80), default="", nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(32), default=AgentSubagentRunStatus.queued.value, nullable=False, index=True)
    summary: Mapped[str] = mapped_column(String(1000), default="", nullable=False)
    input_summary: Mapped[str] = mapped_column(String(1000), default="", nullable=False)
    output_summary: Mapped[str] = mapped_column(String(1000), default="", nullable=False)
    result_snapshot: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    duration_ms: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    error_summary: Mapped[str] = mapped_column(String(700), default="", nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc, nullable=False, index=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
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
    idempotency_key: Mapped[str] = mapped_column(String(160), default="", nullable=False, index=True)
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


class AgentMemoryFile(Base):
    __tablename__ = "agent_memory_files"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    workspace_id: Mapped[str] = mapped_column(ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False, index=True)
    project_id: Mapped[str | None] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), nullable=True, index=True)
    user_id: Mapped[str] = mapped_column(String(254), default="", nullable=False, index=True)
    scope: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    path: Mapped[str] = mapped_column(String(1000), nullable=False, index=True)
    current_version: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    checksum: Mapped[str] = mapped_column(String(80), default="", nullable=False)
    updated_by: Mapped[str] = mapped_column(String(254), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc, onupdate=now_utc, nullable=False)


class AgentMemoryVersion(Base):
    __tablename__ = "agent_memory_versions"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    memory_file_id: Mapped[str] = mapped_column(ForeignKey("agent_memory_files.id", ondelete="CASCADE"), nullable=False, index=True)
    version: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    content: Mapped[str] = mapped_column(String(20000), nullable=False)
    patch_summary: Mapped[str] = mapped_column(String(700), default="", nullable=False)
    editor: Mapped[str] = mapped_column(String(254), nullable=False)
    reason: Mapped[str] = mapped_column(String(700), default="", nullable=False)
    checksum: Mapped[str] = mapped_column(String(80), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc, nullable=False, index=True)


class AgentBudgetPolicy(Base):
    __tablename__ = "agent_budget_policies"
    __table_args__ = (UniqueConstraint("workspace_id", "scope", "project_id", "purpose", name="uq_agent_budget_policy_scope"),)

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    workspace_id: Mapped[str] = mapped_column(ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False, index=True)
    project_id: Mapped[str | None] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), nullable=True, index=True)
    scope: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    purpose: Mapped[str] = mapped_column(String(80), default="agent_run", nullable=False, index=True)
    defaults: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    hard_caps: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    updated_by: Mapped[str] = mapped_column(String(254), nullable=False)
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


class AgentRunResumeRequest(BaseModel):
    budget_snapshot: dict[str, Any] = Field(default_factory=dict)
    resume_reason: str = Field(default="", max_length=700)


class AgentRunCancelRequest(BaseModel):
    cancel_reason: str = Field(default="", max_length=700)


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


class AgentSubagentRunResponse(BaseModel):
    id: str
    agent_run_id: str
    workspace_id: str
    project_id: str | None
    subagent_name: str
    stage: str
    parallel_group: str
    status: str
    summary: str
    input_summary: str
    output_summary: str
    result_snapshot: dict[str, Any]
    duration_ms: int
    error_summary: str
    created_at: datetime
    started_at: datetime | None
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
    idempotency_key: str
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


class AgentRunBudgetResponse(BaseModel):
    snapshot: dict[str, Any]
    usage: dict[str, Any]
    limits: dict[str, Any]


class AgentExecutionDetailResponse(BaseModel):
    run: AgentRunResponse
    staged_outputs: list[AgentStagedOutputResponse] = Field(default_factory=list)
    tool_calls: list[AgentToolCallResponse] = Field(default_factory=list)
    subagent_runs: list[AgentSubagentRunResponse] = Field(default_factory=list)
    ai_invocations: list[AIInvocationResponse] = Field(default_factory=list)
    repository_sandboxes: list[AgentRepositorySandboxResponse] = Field(default_factory=list)
    budget: AgentRunBudgetResponse
    pending_approvals: list[AgentApprovalResponse] = Field(default_factory=list)


class AgentBudgetPolicyUpsert(BaseModel):
    scope: Literal["workspace", "project"] = "workspace"
    project_id: str | None = Field(default=None, max_length=64)
    purpose: str = Field(default="agent_run", max_length=80)
    defaults: dict[str, Any] = Field(default_factory=dict)
    hard_caps: dict[str, Any] = Field(default_factory=dict)


class AgentBudgetPolicyResponse(BaseModel):
    id: str
    workspace_id: str
    project_id: str | None
    scope: str
    purpose: str
    defaults: dict[str, Any]
    hard_caps: dict[str, Any]
    updated_by: str
    created_at: datetime
    updated_at: datetime


class AgentMemoryFileResponse(BaseModel):
    id: str
    workspace_id: str
    project_id: str | None
    user_id: str
    scope: str
    path: str
    current_version: int
    checksum: str
    updated_by: str
    updated_at: datetime


class AgentMemoryVersionResponse(BaseModel):
    id: str
    memory_file_id: str
    version: int
    patch_summary: str
    editor: str
    reason: str
    checksum: str
    created_at: datetime


class AgentMemorySearchResult(BaseModel):
    memory_file: AgentMemoryFileResponse
    score: int
    snippet: str


class AgentMemoryCurateRequest(BaseModel):
    scope: Literal["workspace", "project", "user", "dreams"]
    project_id: str | None = Field(default=None, max_length=64)
    user_id: str = Field(default="", max_length=254)
    content: str = Field(min_length=1, max_length=20000)
    reason: str = Field(default="curated_update", max_length=700)
    patch_summary: str = Field(default="", max_length=700)


class AgentMemoryRollbackRequest(BaseModel):
    target_version: int = Field(ge=1)
    reason: str = Field(default="", max_length=700)


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


def subagent_run_to_response(subagent_run: AgentSubagentRun) -> AgentSubagentRunResponse:
    return AgentSubagentRunResponse(
        id=subagent_run.id,
        agent_run_id=subagent_run.agent_run_id,
        workspace_id=subagent_run.workspace_id,
        project_id=subagent_run.project_id,
        subagent_name=subagent_run.subagent_name,
        stage=subagent_run.stage,
        parallel_group=subagent_run.parallel_group,
        status=subagent_run.status,
        summary=subagent_run.summary,
        input_summary=subagent_run.input_summary,
        output_summary=subagent_run.output_summary,
        result_snapshot=subagent_run.result_snapshot,
        duration_ms=subagent_run.duration_ms,
        error_summary=subagent_run.error_summary,
        created_at=subagent_run.created_at,
        started_at=subagent_run.started_at,
        completed_at=subagent_run.completed_at,
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
        idempotency_key=output.idempotency_key,
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


def budget_policy_to_response(policy: AgentBudgetPolicy) -> AgentBudgetPolicyResponse:
    return AgentBudgetPolicyResponse(
        id=policy.id,
        workspace_id=policy.workspace_id,
        project_id=policy.project_id,
        scope=policy.scope,
        purpose=policy.purpose,
        defaults=policy.defaults,
        hard_caps=policy.hard_caps,
        updated_by=policy.updated_by,
        created_at=policy.created_at,
        updated_at=policy.updated_at,
    )


def memory_file_to_response(memory_file: AgentMemoryFile) -> AgentMemoryFileResponse:
    return AgentMemoryFileResponse(
        id=memory_file.id,
        workspace_id=memory_file.workspace_id,
        project_id=memory_file.project_id,
        user_id=memory_file.user_id,
        scope=memory_file.scope,
        path=memory_file.path,
        current_version=memory_file.current_version,
        checksum=memory_file.checksum,
        updated_by=memory_file.updated_by,
        updated_at=memory_file.updated_at,
    )


def memory_version_to_response(version: AgentMemoryVersion) -> AgentMemoryVersionResponse:
    return AgentMemoryVersionResponse(
        id=version.id,
        memory_file_id=version.memory_file_id,
        version=version.version,
        patch_summary=version.patch_summary,
        editor=version.editor,
        reason=version.reason,
        checksum=version.checksum,
        created_at=version.created_at,
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


def budget_response_for_run(run: AgentRun) -> AgentRunBudgetResponse:
    snapshot = dict(run.budget_snapshot or {})
    limits = dict(snapshot.get("limits") or {})
    if not limits:
        limits = {key: snapshot[key] for key in AGENT_BUDGET_NUMERIC_KEYS if key in snapshot}
    usage = dict(snapshot.get("usage") or {})
    if not usage:
        usage = {
            "tool_calls": 0,
            "subagents": 0,
            "parallel_subagents": 0,
            "model_calls": 0,
            "case_candidates": 0,
            "source_chars_sent": 0,
            "wall_time_seconds": 0,
        }
    return AgentRunBudgetResponse(
        snapshot=snapshot,
        usage=usage,
        limits=limits,
    )


AGENT_BUDGET_NUMERIC_KEYS = {
    "max_tool_calls",
    "max_subagents",
    "max_parallel_subagents",
    "max_model_calls",
    "max_case_candidates_per_run",
    "max_wall_time_minutes",
    "max_total_source_chars_sent",
}


def _settings_budget_defaults(settings) -> dict[str, int]:
    return {
        "max_tool_calls": settings.agent_default_max_tool_calls,
        "max_subagents": settings.agent_default_max_subagents,
        "max_parallel_subagents": settings.agent_default_max_parallel_subagents,
        "max_model_calls": settings.agent_default_max_model_calls,
        "max_case_candidates_per_run": settings.agent_default_max_case_candidates_per_run,
        "max_wall_time_minutes": settings.agent_default_max_wall_time_minutes,
        "max_total_source_chars_sent": settings.agent_default_max_total_source_chars_sent,
    }


def _settings_budget_caps(settings) -> dict[str, int]:
    return {
        "max_tool_calls": settings.agent_system_max_tool_calls,
        "max_subagents": settings.agent_system_max_subagents,
        "max_parallel_subagents": settings.agent_system_max_parallel_subagents,
        "max_model_calls": settings.agent_system_max_model_calls,
        "max_case_candidates_per_run": settings.agent_system_max_case_candidates_per_run,
        "max_wall_time_minutes": settings.agent_system_max_wall_time_minutes,
        "max_total_source_chars_sent": settings.agent_system_max_total_source_chars_sent,
    }


def _sanitize_budget_values(values: dict[str, Any], hard_caps: dict[str, int]) -> dict[str, Any]:
    sanitized: dict[str, Any] = {}
    for key, value in values.items():
        if key in {"usage", "last_execute_request", "limits"}:
            continue
        if key in AGENT_BUDGET_NUMERIC_KEYS:
            try:
                numeric = max(0, int(value))
            except (TypeError, ValueError):
                continue
            sanitized[key] = min(numeric, hard_caps.get(key, numeric))
        else:
            sanitized[key] = value
    return sanitized


def _budget_policy_for_scope(
    db: Session,
    *,
    workspace_id: str,
    scope: str,
    project_id: str | None,
    purpose: str,
) -> AgentBudgetPolicy | None:
    statement = select(AgentBudgetPolicy).where(
        AgentBudgetPolicy.workspace_id == workspace_id,
        AgentBudgetPolicy.scope == scope,
        AgentBudgetPolicy.purpose == purpose,
    )
    if project_id:
        statement = statement.where(AgentBudgetPolicy.project_id == project_id)
    else:
        statement = statement.where(AgentBudgetPolicy.project_id.is_(None))
    return db.scalar(statement.order_by(AgentBudgetPolicy.updated_at.desc(), AgentBudgetPolicy.id.desc()))


def build_agent_run_budget_snapshot(
    db: Session,
    *,
    settings,
    workspace_id: str,
    project_id: str | None,
    override: dict[str, Any],
    purpose: str = "agent_run",
) -> dict[str, Any]:
    hard_caps = _settings_budget_caps(settings)
    snapshot: dict[str, Any] = dict(_settings_budget_defaults(settings))
    sources: list[dict[str, Any]] = [{"scope": "system_defaults", "keys": sorted(snapshot)}]

    workspace_policy = _budget_policy_for_scope(
        db,
        workspace_id=workspace_id,
        scope="workspace",
        project_id=None,
        purpose=purpose,
    )
    project_policy = (
        _budget_policy_for_scope(db, workspace_id=workspace_id, scope="project", project_id=project_id, purpose=purpose)
        if project_id
        else None
    )
    for policy in [workspace_policy, project_policy]:
        if policy is None:
            continue
        hard_caps.update(_sanitize_budget_values(dict(policy.hard_caps or {}), hard_caps))
        sanitized_defaults = _sanitize_budget_values(dict(policy.defaults or {}), hard_caps)
        snapshot.update(sanitized_defaults)
        sources.append({"scope": policy.scope, "policy_id": policy.id, "keys": sorted(sanitized_defaults)})

    sanitized_override = _sanitize_budget_values(dict(override or {}), hard_caps)
    snapshot.update(sanitized_override)
    if sanitized_override:
        sources.append({"scope": "run_override", "keys": sorted(sanitized_override)})
    snapshot = _sanitize_budget_values(snapshot, hard_caps)
    snapshot["system_hard_caps"] = hard_caps
    snapshot["budget_sources"] = sources
    return snapshot


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
    request: Request,
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
        budget_snapshot=build_agent_run_budget_snapshot(
            db,
            settings=request.app.state.settings,
            workspace_id=workspace_id,
            project_id=project_id,
            override=payload.budget_snapshot,
        ),
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


@router.get("/agent/runs", response_model=list[AgentRunResponse])
def list_workspace_agent_runs(
    workspace_id: str,
    db: DbSession,
    project_id: str | None = Query(default=None, max_length=64),
    status_filter: AgentRunStatus | None = Query(default=None, alias="status"),
) -> list[AgentRunResponse]:
    get_workspace_or_404(db, workspace_id)
    statement = select(AgentRun).where(AgentRun.workspace_id == workspace_id)
    if project_id:
        statement = statement.where(AgentRun.project_id == project_id)
    if status_filter is not None:
        statement = statement.where(AgentRun.status == status_filter.value)
    runs = db.scalars(statement.order_by(AgentRun.created_at.desc(), AgentRun.id.desc()).limit(200)).all()
    return [run_to_response(run) for run in runs]


@router.get("/agent/runs/{run_id}", response_model=AgentRunResponse)
def get_agent_run(workspace_id: str, run_id: str, db: DbSession) -> AgentRunResponse:
    return run_to_response(get_run_or_404(db, workspace_id, run_id))


@router.get("/agent/budget-policies", response_model=list[AgentBudgetPolicyResponse])
def list_agent_budget_policies(
    workspace_id: str,
    db: DbSession,
    project_id: str | None = Query(default=None, max_length=64),
    purpose: str = Query(default="agent_run", max_length=80),
) -> list[AgentBudgetPolicyResponse]:
    get_workspace_or_404(db, workspace_id)
    statement = select(AgentBudgetPolicy).where(AgentBudgetPolicy.workspace_id == workspace_id, AgentBudgetPolicy.purpose == purpose)
    if project_id:
        statement = statement.where((AgentBudgetPolicy.project_id == project_id) | (AgentBudgetPolicy.project_id.is_(None)))
    policies = db.scalars(statement.order_by(AgentBudgetPolicy.scope, AgentBudgetPolicy.updated_at.desc())).all()
    return [budget_policy_to_response(policy) for policy in policies]


@router.put("/agent/budget-policies", response_model=AgentBudgetPolicyResponse)
def upsert_agent_budget_policy(
    workspace_id: str,
    payload: AgentBudgetPolicyUpsert,
    db: DbSession,
    request: Request,
    actor_email: ActorEmail,
) -> AgentBudgetPolicyResponse:
    get_workspace_or_404(db, workspace_id)
    project_id = payload.project_id if payload.scope == "project" else None
    if payload.scope == "project":
        if not project_id:
            raise HTTPException(status_code=422, detail="Project budget policy requires project_id")
        get_project_or_404(db, workspace_id, project_id)
    caps = _settings_budget_caps(request.app.state.settings)
    defaults = _sanitize_budget_values(payload.defaults, caps)
    hard_caps = _sanitize_budget_values(payload.hard_caps, caps)
    policy = _budget_policy_for_scope(
        db,
        workspace_id=workspace_id,
        scope=payload.scope,
        project_id=project_id,
        purpose=payload.purpose,
    )
    before = None
    if policy is None:
        policy = AgentBudgetPolicy(
            workspace_id=workspace_id,
            project_id=project_id,
            scope=payload.scope,
            purpose=payload.purpose,
            defaults=defaults,
            hard_caps=hard_caps,
            updated_by=actor_email,
        )
        db.add(policy)
        action = "agent_budget_policy.created"
    else:
        before = {"defaults": policy.defaults, "hard_caps": policy.hard_caps}
        policy.defaults = defaults
        policy.hard_caps = hard_caps
        policy.updated_by = actor_email
        policy.updated_at = now_utc()
        action = "agent_budget_policy.updated"
    db.flush()
    audit(
        db,
        workspace_id=workspace_id,
        actor_email=actor_email,
        action=action,
        entity_type="AgentBudgetPolicy",
        entity_id=policy.id,
        summary=f"Updated {policy.scope} agent budget policy",
        before=before,
        after={
            "scope": policy.scope,
            "project_id": policy.project_id,
            "purpose": policy.purpose,
            "defaults": policy.defaults,
            "hard_caps": policy.hard_caps,
        },
    )
    db.commit()
    db.refresh(policy)
    return budget_policy_to_response(policy)


def _agent_run_execution_response(db: Session, result) -> AgentRunExecuteResponse:
    return AgentRunExecuteResponse(
        run=run_to_response(result.run),
        summary=result.summary,
        staged_outputs=[staged_output_to_response(db, output) for output in result.staged_outputs],
        tool_calls=[tool_call_to_response(tool_call) for tool_call in result.tool_calls],
        sandboxes=[sandbox_to_response(sandbox) for sandbox in result.sandboxes],
    )


@router.post("/agent/runs/{run_id}/execute", response_model=AgentRunExecuteResponse)
def execute_agent_run(
    workspace_id: str,
    run_id: str,
    payload: AgentRunExecuteRequest,
    db: DbSession,
    request: Request,
    response: Response,
    actor_email: ActorEmail,
) -> AgentRunExecuteResponse:
    run = get_run_or_404(db, workspace_id, run_id)
    if run.mode != AgentRunMode.execute.value:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Agent execute requires an execute mode run")

    settings = request.app.state.settings
    if not settings.agent_execute_sync_mode:
        from app.agent_temporal import AgentTemporalUnavailable, start_agent_run_workflow

        starter = getattr(request.app.state, "agent_workflow_starter", start_agent_run_workflow)
        try:
            started = starter(
                db=db,
                settings=settings,
                run=run,
                workspace_id=workspace_id,
                repository_id=payload.repository_id,
                ref=payload.ref,
                candidate_limit=payload.candidate_limit,
                actor_email=actor_email,
            )
        except AgentTemporalUnavailable as exc:
            raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)) from exc
        response.status_code = status.HTTP_202_ACCEPTED
        db.refresh(run)
        return AgentRunExecuteResponse(
            run=run_to_response(run),
            summary=started.get("summary", "Agent workflow started"),
            staged_outputs=[],
            tool_calls=[],
            sandboxes=[],
        )

    from app.agent_graph import AgentGraphConflict, AgentPolicyViolation, execute_agent_graph

    try:
        result = execute_agent_graph(
            db=db,
            settings=settings,
            workspace_id=workspace_id,
            run_id=run_id,
            repository_id=payload.repository_id,
            ref=payload.ref,
            candidate_limit=payload.candidate_limit,
            actor_email=actor_email,
            model_gateway_transport=getattr(request.app.state, "model_gateway_transport", None),
        )
    except AgentPolicyViolation as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc
    except AgentGraphConflict as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc

    return _agent_run_execution_response(db, result)


def _merge_budget_override(run: AgentRun, override: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    before = dict(run.budget_snapshot or {})
    after = dict(before)
    usage = before.get("usage")
    last_execute_request = before.get("last_execute_request")
    hard_caps = {key: int(value) for key, value in dict(before.get("system_hard_caps") or {}).items() if key in AGENT_BUDGET_NUMERIC_KEYS}
    changed_keys: list[str] = []
    for key, value in override.items():
        if key in {"usage", "last_execute_request", "limits", "system_hard_caps", "budget_sources"}:
            continue
        if key in AGENT_BUDGET_NUMERIC_KEYS:
            try:
                numeric = max(0, int(value))
            except (TypeError, ValueError):
                continue
            after[key] = min(numeric, hard_caps.get(key, numeric))
        else:
            after[key] = value
        changed_keys.append(key)
    if usage is not None:
        after["usage"] = usage
    if last_execute_request is not None:
        after["last_execute_request"] = last_execute_request
    if changed_keys:
        sources = [
            source
            for source in list(before.get("budget_sources") or [])
            if not (isinstance(source, dict) and source.get("scope") == "resume_override")
        ]
        sources.append({"scope": "resume_override", "keys": sorted(set(changed_keys))})
        after["budget_sources"] = sources
    run.budget_snapshot = after
    return before, after


def apply_agent_run_budget_override(
    db: Session,
    *,
    run: AgentRun,
    workspace_id: str,
    actor_email: str,
    budget_snapshot: dict[str, Any],
    resume_reason: str,
) -> tuple[dict[str, Any], dict[str, Any]]:
    before, after = _merge_budget_override(run, budget_snapshot)
    audit(
        db,
        workspace_id=workspace_id,
        actor_email=actor_email,
        action="agent_run.budget_overridden",
        entity_type="AgentRun",
        entity_id=run.id,
        summary=resume_reason or "Resumed agent run with budget override",
        before={"budget_snapshot": before},
        after={"budget_snapshot": after, "resume_reason": resume_reason},
    )
    return before, after


def _resume_execution_context(db: Session, run: AgentRun) -> tuple[str, str, int]:
    snapshot = dict(run.budget_snapshot or {})
    last_execute_request = dict(snapshot.get("last_execute_request") or {})
    repository_id = str(last_execute_request.get("repository_id") or "")
    ref = str(last_execute_request.get("ref") or "")
    try:
        candidate_limit = int(last_execute_request.get("candidate_limit") or 3)
    except (TypeError, ValueError):
        candidate_limit = 3

    if not repository_id:
        sandbox = db.scalar(
            select(AgentRepositorySandbox)
            .where(AgentRepositorySandbox.agent_run_id == run.id)
            .order_by(AgentRepositorySandbox.created_at.desc(), AgentRepositorySandbox.id.desc())
        )
        if sandbox is not None:
            repository_id = sandbox.repository_id
            ref = sandbox.ref
    if not repository_id:
        raise AgentRunStateError("Agent run has no previous execution context to resume")
    return repository_id, ref, min(max(candidate_limit, 1), 5)


@router.post("/agent/runs/{run_id}/resume", response_model=AgentRunExecuteResponse)
def resume_agent_run(
    workspace_id: str,
    run_id: str,
    payload: AgentRunResumeRequest,
    db: DbSession,
    request: Request,
    actor_email: ActorEmail,
) -> AgentRunExecuteResponse:
    run = get_run_or_404(db, workspace_id, run_id)
    if run.mode != AgentRunMode.execute.value:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Agent resume requires an execute mode run")
    if run.status == AgentRunStatus.cancelled.value:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Cancelled agent runs cannot be resumed")
    if run.status not in {AgentRunStatus.waiting_for_user.value, AgentRunStatus.failed.value}:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Only waiting or failed agent runs can be resumed")

    settings = request.app.state.settings
    if not settings.agent_execute_sync_mode and run.temporal_workflow_id:
        apply_agent_run_budget_override(
            db,
            run=run,
            workspace_id=workspace_id,
            actor_email=actor_email,
            budget_snapshot=payload.budget_snapshot,
            resume_reason=payload.resume_reason,
        )
        db.commit()
        from app.agent_temporal import AgentTemporalUnavailable, signal_agent_run_resume

        signal_resume = getattr(request.app.state, "agent_workflow_resume_signaler", signal_agent_run_resume)
        try:
            signal_resume(db=db, settings=settings, run=run, actor_email=actor_email, resume_reason=payload.resume_reason)
        except AgentTemporalUnavailable as exc:
            raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)) from exc
        db.refresh(run)
        return AgentRunExecuteResponse(
            run=run_to_response(run),
            summary="Agent workflow resume signal sent",
            staged_outputs=[],
            tool_calls=[],
            sandboxes=[],
        )

    try:
        repository_id, ref, candidate_limit = _resume_execution_context(db, run)
    except AgentRunStateError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc

    apply_agent_run_budget_override(
        db,
        run=run,
        workspace_id=workspace_id,
        actor_email=actor_email,
        budget_snapshot=payload.budget_snapshot,
        resume_reason=payload.resume_reason,
    )
    db.commit()

    from app.agent_graph import AgentGraphConflict, AgentPolicyViolation, execute_agent_graph

    try:
        result = execute_agent_graph(
            db=db,
            settings=settings,
            workspace_id=workspace_id,
            run_id=run_id,
            repository_id=repository_id,
            ref=ref,
            candidate_limit=candidate_limit,
            actor_email=actor_email,
            model_gateway_transport=getattr(request.app.state, "model_gateway_transport", None),
            explicit_resume=True,
        )
    except AgentPolicyViolation as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc
    except AgentGraphConflict as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc

    return _agent_run_execution_response(db, result)


@router.post("/agent/runs/{run_id}/cancel", response_model=AgentRunResponse)
def cancel_agent_run(
    workspace_id: str,
    run_id: str,
    payload: AgentRunCancelRequest,
    db: DbSession,
    request: Request,
    actor_email: ActorEmail,
) -> AgentRunResponse:
    run = get_run_or_404(db, workspace_id, run_id)
    try:
        mark_run_cancelled(run, payload.cancel_reason or "Agent run cancelled by user")
    except AgentRunStateError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    audit(
        db,
        workspace_id=workspace_id,
        actor_email=actor_email,
        action="agent_run.cancelled",
        entity_type="AgentRun",
        entity_id=run.id,
        summary=payload.cancel_reason or "Cancelled agent run",
        after={"status": run.status, "cancel_reason": payload.cancel_reason},
    )
    db.commit()
    db.refresh(run)
    if not request.app.state.settings.agent_execute_sync_mode and run.temporal_workflow_id:
        from app.agent_temporal import AgentTemporalUnavailable, cancel_agent_run_workflow

        cancel_workflow = getattr(request.app.state, "agent_workflow_canceller", cancel_agent_run_workflow)
        try:
            cancel_workflow(
                settings=request.app.state.settings,
                workflow_id=run.temporal_workflow_id,
                cancel_reason=payload.cancel_reason or "Agent run cancelled by user",
                actor_email=actor_email,
            )
        except AgentTemporalUnavailable:
            # The product cancellation state is still authoritative; Temporal may
            # already be down or the workflow may have completed between requests.
            pass
    return run_to_response(run)


@router.get("/agent/runs/{run_id}/execution-detail", response_model=AgentExecutionDetailResponse)
def get_agent_execution_detail(workspace_id: str, run_id: str, db: DbSession) -> AgentExecutionDetailResponse:
    run = get_run_or_404(db, workspace_id, run_id)
    staged_outputs = db.scalars(
        select(AgentStagedOutput)
        .where(AgentStagedOutput.agent_run_id == run.id, AgentStagedOutput.workspace_id == workspace_id)
        .order_by(AgentStagedOutput.created_at, AgentStagedOutput.id)
    ).all()
    tool_calls = db.scalars(
        select(AgentToolCall).where(AgentToolCall.agent_run_id == run.id).order_by(AgentToolCall.created_at, AgentToolCall.id)
    ).all()
    subagent_runs = db.scalars(
        select(AgentSubagentRun)
        .where(AgentSubagentRun.agent_run_id == run.id, AgentSubagentRun.workspace_id == workspace_id)
        .order_by(AgentSubagentRun.created_at, AgentSubagentRun.id)
    ).all()
    invocations = db.scalars(
        select(AIInvocationLog)
        .where(AIInvocationLog.agent_run_id == run.id, AIInvocationLog.workspace_id == workspace_id)
        .order_by(AIInvocationLog.created_at, AIInvocationLog.id)
    ).all()
    sandboxes = db.scalars(
        select(AgentRepositorySandbox)
        .where(AgentRepositorySandbox.agent_run_id == run.id, AgentRepositorySandbox.workspace_id == workspace_id)
        .order_by(AgentRepositorySandbox.created_at, AgentRepositorySandbox.id)
    ).all()
    pending_approvals = db.scalars(
        select(AgentApproval)
        .where(AgentApproval.agent_run_id == run.id, AgentApproval.status == AgentApprovalStatus.pending.value)
        .order_by(AgentApproval.created_at, AgentApproval.id)
    ).all()
    return AgentExecutionDetailResponse(
        run=run_to_response(run),
        staged_outputs=[staged_output_to_response(db, output) for output in staged_outputs],
        tool_calls=[tool_call_to_response(tool_call) for tool_call in tool_calls],
        subagent_runs=[subagent_run_to_response(subagent_run) for subagent_run in subagent_runs],
        ai_invocations=[invocation_to_response(invocation) for invocation in invocations],
        repository_sandboxes=[sandbox_to_response(sandbox) for sandbox in sandboxes],
        budget=budget_response_for_run(run),
        pending_approvals=[approval_to_response(approval) for approval in pending_approvals],
    )


@router.get("/agent/memory/files", response_model=list[AgentMemoryFileResponse])
def list_agent_memory_files(
    workspace_id: str,
    db: DbSession,
    project_id: str | None = Query(default=None, max_length=64),
    scope: str | None = Query(default=None, max_length=40),
) -> list[AgentMemoryFileResponse]:
    get_workspace_or_404(db, workspace_id)
    if project_id:
        get_project_or_404(db, workspace_id, project_id)
    from app.agent_memory import list_memory_files

    return [
        memory_file_to_response(memory_file)
        for memory_file in list_memory_files(db, workspace_id=workspace_id, project_id=project_id, scope=scope)
    ]


@router.get("/agent/memory/files/{memory_file_id}/versions", response_model=list[AgentMemoryVersionResponse])
def list_agent_memory_versions(workspace_id: str, memory_file_id: str, db: DbSession) -> list[AgentMemoryVersionResponse]:
    memory_file = get_memory_file_or_404(db, workspace_id, memory_file_id)
    versions = db.scalars(
        select(AgentMemoryVersion)
        .where(AgentMemoryVersion.memory_file_id == memory_file.id)
        .order_by(AgentMemoryVersion.version.desc(), AgentMemoryVersion.id.desc())
    ).all()
    return [memory_version_to_response(version) for version in versions]


@router.get("/agent/memory/search", response_model=list[AgentMemorySearchResult])
def search_agent_memory(
    workspace_id: str,
    db: DbSession,
    query: str = Query(default="", max_length=500),
    project_id: str | None = Query(default=None, max_length=64),
    scope: str | None = Query(default=None, max_length=40),
    limit: int = Query(default=10, ge=1, le=50),
) -> list[AgentMemorySearchResult]:
    get_workspace_or_404(db, workspace_id)
    if project_id:
        get_project_or_404(db, workspace_id, project_id)
    from app.agent_memory import search_memory

    results = search_memory(
        db,
        workspace_id=workspace_id,
        project_id=project_id,
        scope=scope,
        query=query,
        limit=limit,
    )
    return [
        AgentMemorySearchResult(
            memory_file=memory_file_to_response(item["memory_file"]),
            score=int(item["score"]),
            snippet=str(item["snippet"]),
        )
        for item in results
    ]


@router.post("/agent/memory/curate", response_model=AgentMemoryFileResponse)
def curate_agent_memory(
    workspace_id: str,
    payload: AgentMemoryCurateRequest,
    db: DbSession,
    request: Request,
    actor_email: ActorEmail,
) -> AgentMemoryFileResponse:
    get_workspace_or_404(db, workspace_id)
    if payload.project_id:
        get_project_or_404(db, workspace_id, payload.project_id)
    from app.agent_memory import curate_memory_file

    try:
        memory_file = curate_memory_file(
            db,
            settings=request.app.state.settings,
            workspace_id=workspace_id,
            scope=payload.scope,
            project_id=payload.project_id,
            user_id=payload.user_id,
            content=payload.content,
            actor_email=actor_email,
            reason=payload.reason,
            patch_summary=payload.patch_summary,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    db.commit()
    db.refresh(memory_file)
    return memory_file_to_response(memory_file)


@router.post("/agent/memory/files/{memory_file_id}/rollback", response_model=AgentMemoryFileResponse)
def rollback_agent_memory(
    workspace_id: str,
    memory_file_id: str,
    payload: AgentMemoryRollbackRequest,
    db: DbSession,
    request: Request,
    actor_email: ActorEmail,
) -> AgentMemoryFileResponse:
    memory_file = get_memory_file_or_404(db, workspace_id, memory_file_id)
    from app.agent_memory import rollback_memory_file

    try:
        rolled_back = rollback_memory_file(
            db,
            settings=request.app.state.settings,
            memory_file=memory_file,
            target_version=payload.target_version,
            actor_email=actor_email,
            reason=payload.reason,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    db.commit()
    db.refresh(rolled_back)
    return memory_file_to_response(rolled_back)


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
    AGENT_TOOL_CALLS_TOTAL.labels(tool=tool_call.tool_name, status=tool_call.status).inc()
    AGENT_TOOL_DURATION_SECONDS.labels(tool=tool_call.tool_name, status=tool_call.status).observe(max(0, tool_call.duration_ms) / 1000)
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
    AGENT_APPROVAL_WAIT_SECONDS.labels(approval_type=approval.approval_type, status=approval.status).observe(
        elapsed_seconds(approval.created_at, approval.decided_at)
    )
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
    AGENT_STAGED_OUTPUT_DECISIONS_TOTAL.labels(output_type=output.output_type, status=output.status).inc()

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
