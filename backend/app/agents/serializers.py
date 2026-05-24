from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.agents.models import (
    AgentApproval,
    AgentBudgetPolicy,
    AgentConversation,
    AgentMemoryFile,
    AgentMemoryVersion,
    AgentMessage,
    AgentRepositorySandbox,
    AgentRun,
    AgentStagedOutput,
    AgentSubagentRun,
    AgentToolCall,
    CoverageIndexEntry,
)
from app.agents.schemas import (
    AgentApprovalResponse,
    AgentBudgetPolicyResponse,
    AgentConversationResponse,
    AgentMemoryFileResponse,
    AgentMemoryVersionResponse,
    AgentMessageResponse,
    AgentRepositorySandboxResponse,
    AgentRunResponse,
    AgentStagedOutputResponse,
    AgentSubagentRunResponse,
    AgentToolCallResponse,
    CoverageEntryResponse,
    EvidenceRef,
)


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


