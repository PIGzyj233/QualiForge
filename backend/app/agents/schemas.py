from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

from app.ai.config import AIInvocationResponse
from app.agents.models import (
    AgentApprovalStatus,
    AgentMessageRole,
    AgentRunMode,
    AgentStagedOutputStatus,
    AgentStagedOutputType,
    AgentToolCallStatus,
    EvidenceKind,
)


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


