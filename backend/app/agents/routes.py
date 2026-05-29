from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.ai.config import AIInvocationLog, invocation_to_response
from app.agents.budget import (
    AGENT_BUDGET_NUMERIC_KEYS,
    _budget_policy_for_scope,
    _sanitize_budget_values,
    _settings_budget_caps,
    budget_response_for_run,
    build_agent_run_budget_snapshot,
)
from app.agents.coverage import add_coverage_entries, transition_staged_output_coverage
from app.agents.models import (
    AgentApproval,
    AgentApprovalStatus,
    AgentBudgetPolicy,
    AgentConversation,
    AgentConversationStatus,
    AgentMemoryFile,
    AgentMemoryVersion,
    AgentMessage,
    AgentMessageRole,
    AgentRepositorySandbox,
    AgentRun,
    AgentRunMode,
    AgentRunStatus,
    AgentStagedOutput,
    AgentStagedOutputStatus,
    AgentStagedOutputType,
    AgentSubagentRun,
    AgentToolCall,
    AgentToolCallStatus,
    CoverageIndexEntry,
)
from app.agents.repository import (
    assert_project_scope,
    get_approval_or_404,
    get_conversation_or_404,
    get_memory_file_or_404,
    get_run_or_404,
    get_staged_output_or_404,
)
from app.agents.schemas import (
    AgentApprovalCreate,
    AgentApprovalDecision,
    AgentApprovalResponse,
    AgentBudgetPolicyResponse,
    AgentBudgetPolicyUpsert,
    AgentConversationCreate,
    AgentConversationResponse,
    AgentExecutionDetailResponse,
    AgentMemoryCurateRequest,
    AgentMemoryFileResponse,
    AgentMemoryRollbackRequest,
    AgentMemorySearchResult,
    AgentMemoryVersionResponse,
    AgentMessageCreate,
    AgentMessageResponse,
    AgentRepositorySandboxResponse,
    AgentRunCancelRequest,
    AgentRunCreate,
    AgentRunExecuteRequest,
    AgentRunExecuteResponse,
    AgentRunResponse,
    AgentRunResumeRequest,
    AgentStagedOutputCreate,
    AgentStagedOutputResponse,
    AgentStagedOutputUpdate,
    AgentSubagentRunResponse,
    AgentToolCallCreate,
    AgentToolCallResponse,
    CoverageEntryResponse,
)
from app.agents.serializers import (
    approval_to_response,
    budget_policy_to_response,
    conversation_to_response,
    coverage_snapshot,
    coverage_to_response,
    evidence_refs_to_json,
    memory_file_to_response,
    memory_version_to_response,
    message_to_response,
    run_to_response,
    sandbox_to_response,
    staged_output_to_response,
    subagent_run_to_response,
    tool_call_to_response,
)
from app.agents.state import (
    AgentRunStateError,
    assert_run_can_execute,
    mark_run_cancelled,
    mark_run_failed,
    mark_run_running,
    mark_run_succeeded,
    mark_run_waiting,
)
from app.agents.workflow_gateway import AgentWorkflowUnavailable, get_agent_workflow_gateway
from app.platform.telemetry import (
    AGENT_APPROVAL_WAIT_SECONDS,
    AGENT_STAGED_OUTPUT_DECISIONS_TOTAL,
    AGENT_TOOL_CALLS_TOTAL,
    AGENT_TOOL_DURATION_SECONDS,
    elapsed_seconds,
)
from app.workspace.routes import ActorEmail, audit, get_project_or_404, get_workspace_or_404, now_utc, require_workspace_owner


def get_db(request: Request):
    yield from request.app.state.database.session()


DbSession = Annotated[Session, Depends(get_db)]

router = APIRouter(prefix="/api/workspaces/{workspace_id}", tags=["agents"])


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
        gateway = get_agent_workflow_gateway(request.app.state)
        try:
            started = gateway.start_run(
                db=db,
                settings=settings,
                run=run,
                workspace_id=workspace_id,
                repository_id=payload.repository_id,
                ref=payload.ref,
                candidate_limit=payload.candidate_limit,
                actor_email=actor_email,
            )
        except AgentWorkflowUnavailable as exc:
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

    from app.agents.graph import AgentGraphConflict, AgentPolicyViolation, execute_agent_graph

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

        gateway = get_agent_workflow_gateway(request.app.state)
        try:
            gateway.signal_resume(db=db, settings=settings, run=run, actor_email=actor_email, resume_reason=payload.resume_reason)
        except AgentWorkflowUnavailable as exc:
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

    from app.agents.graph import AgentGraphConflict, AgentPolicyViolation, execute_agent_graph

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
        gateway = get_agent_workflow_gateway(request.app.state)
        try:
            gateway.cancel(
                settings=request.app.state.settings,
                workflow_id=run.temporal_workflow_id,
                cancel_reason=payload.cancel_reason or "Agent run cancelled by user",
                actor_email=actor_email,
            )
        except AgentWorkflowUnavailable:
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
    from app.agents.memory import list_memory_files

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
    from app.agents.memory import search_memory

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
    from app.agents.memory import curate_memory_file

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
    from app.agents.memory import rollback_memory_file

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
    if payload.output_type in {AgentStagedOutputType.module_tree_draft, AgentStagedOutputType.module_mapping_suggestions}:
        require_workspace_owner(db, workspace_id, actor_email)

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
        action = "agent_staged_output.accepted"
        if output.output_type == AgentStagedOutputType.module_tree_draft.value:
            require_workspace_owner(db, workspace_id, actor_email)
            from app.cases.modules import accept_module_tree_draft_output

            acceptance_result = accept_module_tree_draft_output(db, output=output, actor_email=actor_email)
            output.payload = {**dict(output.payload or {}), "acceptance_result": acceptance_result}
        elif output.output_type == AgentStagedOutputType.module_mapping_suggestions.value:
            require_workspace_owner(db, workspace_id, actor_email)
            from app.cases.modules import accept_module_mapping_suggestions_output

            acceptance_result = accept_module_mapping_suggestions_output(db, output=output, actor_email=actor_email)
            output.payload = {**dict(output.payload or {}), "acceptance_result": acceptance_result}
    elif payload.status == AgentStagedOutputStatus.rejected:
        output.rejected_at = now
        action = "agent_staged_output.rejected"
    else:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Decision must accept or reject staged output")
    AGENT_STAGED_OUTPUT_DECISIONS_TOTAL.labels(output_type=output.output_type, status=output.status).inc()

    next_coverage_state, _coverage_entries = transition_staged_output_coverage(
        db,
        output=output,
        decision_status=payload.status,
        changed_at=now,
    )

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
