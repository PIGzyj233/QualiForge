from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Any

from sqlalchemy import JSON, Boolean, DateTime, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.platform.database import Base
from app.workspace.routes import new_id, now_utc


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


