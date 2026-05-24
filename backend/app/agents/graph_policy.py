from __future__ import annotations

import json
from hashlib import sha256
from typing import Any

from sqlalchemy.orm import Session

from app.ai.config import (
    AIDataPolicyName,
    AIInvocationLog,
    AIInvocationStatus,
    AIPurpose,
    get_or_create_ai_settings,
    is_internal_api_base_url,
)
from app.agents import AgentRun
from app.agents.graph_types import AgentPolicyViolation
from app.platform.config import Settings
from app.workspace.routes import audit, now_utc


AGENT_MODEL_INPUT_DATA_TYPES = [
    "goal",
    "coverage_index",
    "code_tool_observations",
    "source_code",
    "source_code_excerpt",
]

AGENT_SUPERVISOR_PROMPT_VERSION = "agent-supervisor-v1"


def prompt_hash_for_messages(messages: list[dict[str, str]]) -> str:
    payload = json.dumps(messages, ensure_ascii=False, sort_keys=True)
    return sha256(payload.encode("utf-8")).hexdigest()


def staged_output_idempotency_key(run_id: str, output_type: str, payload: dict[str, Any]) -> str:
    digest = sha256(json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8")).hexdigest()[:32]
    return f"{run_id}:{output_type}:{digest}"


def agent_ai_policy_rejection_reason(*, policy: str, settings: Settings, includes_source_code: bool) -> str:
    if policy == AIDataPolicyName.ai_disabled.value:
        return "AI tasks are disabled for this workspace"
    if policy == AIDataPolicyName.no_source_code.value and includes_source_code:
        return "Workspace policy forbids sending source code to AI providers"
    if policy == AIDataPolicyName.internal_only.value and not is_internal_api_base_url(settings.model_gateway_api_base_url):
        return "Workspace policy allows only internal model gateway endpoints"
    return ""


def enforce_agent_ai_policy(
    db: Session,
    *,
    settings: Settings,
    run: AgentRun,
    actor_email: str,
) -> None:
    workspace_ai_settings = get_or_create_ai_settings(db, run.workspace_id, actor_email)
    reason = agent_ai_policy_rejection_reason(
        policy=workspace_ai_settings.data_policy,
        settings=settings,
        includes_source_code=True,
    )
    if not reason:
        return

    invocation = AIInvocationLog(
        workspace_id=run.workspace_id,
        provider_id=None,
        model_profile_id=None,
        agent_run_id=run.id,
        tool_call_id=None,
        actor_email=actor_email,
        purpose=AIPurpose.case_generation.value,
        data_policy=workspace_ai_settings.data_policy,
            provider_name=settings.model_gateway_provider,
            model_alias=settings.model_gateway_default_model,
            model_name=settings.model_gateway_default_model,
            prompt_hash="",
            prompt_version=AGENT_SUPERVISOR_PROMPT_VERSION,
            subagent_name="CaseDesignSubAgent",
            status=AIInvocationStatus.rejected.value,
        input_summary=f"LangGraph supervisor case generation for agent run {run.id}",
        input_data_types=AGENT_MODEL_INPUT_DATA_TYPES,
        includes_source_code=True,
        failure_reason=reason,
        completed_at=now_utc(),
    )
    db.add(invocation)
    db.flush()
    audit(
        db,
        workspace_id=run.workspace_id,
        actor_email=actor_email,
        action="ai_invocation.rejected",
        entity_type="AIInvocationLog",
        entity_id=invocation.id,
        summary=reason,
        after={
            "agent_run_id": run.id,
            "purpose": invocation.purpose,
            "data_policy": invocation.data_policy,
            "status": invocation.status,
            "input_summary": invocation.input_summary,
            "input_data_types": invocation.input_data_types,
            "includes_source_code": invocation.includes_source_code,
            "provider_name": invocation.provider_name,
            "model_alias": invocation.model_alias,
            "prompt_hash": invocation.prompt_hash,
            "prompt_version": invocation.prompt_version,
            "subagent_name": invocation.subagent_name,
            "failure_reason": invocation.failure_reason,
        },
    )
    db.commit()
    raise AgentPolicyViolation(reason)


