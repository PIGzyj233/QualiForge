from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from enum import StrEnum
from ipaddress import ip_address
from typing import Annotated, Any, Literal
from urllib.parse import urlparse

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from pydantic import BaseModel, Field, HttpUrl, field_validator
from sqlalchemy import JSON, Boolean, DateTime, ForeignKey, Integer, Numeric, String, UniqueConstraint, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Mapped, Session, mapped_column

from app.database import Base
from app.workspaces import ActorEmail, audit, get_workspace_or_404, new_id, now_utc


class AIPurpose(StrEnum):
    import_cleanup = "import_cleanup"
    diff_analysis = "diff_analysis"
    case_generation = "case_generation"
    report_summary = "report_summary"


class AIDataPolicyName(StrEnum):
    external_allowed = "ExternalAllowed"
    no_source_code = "NoSourceCode"
    internal_only = "InternalOnly"
    ai_disabled = "AIDisabled"


class AIInvocationStatus(StrEnum):
    queued = "queued"
    rejected = "rejected"
    succeeded = "succeeded"
    failed = "failed"


class WorkspaceAISettings(Base):
    __tablename__ = "workspace_ai_settings"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    workspace_id: Mapped[str] = mapped_column(ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False, unique=True, index=True)
    data_policy: Mapped[str] = mapped_column(String(32), default=AIDataPolicyName.external_allowed.value, nullable=False)
    updated_by: Mapped[str] = mapped_column(String(254), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc, onupdate=now_utc, nullable=False)


class LLMProvider(Base):
    __tablename__ = "llm_providers"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    workspace_id: Mapped[str] = mapped_column(ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    api_base_url: Mapped[str] = mapped_column(String(500), nullable=False)
    api_key_secret: Mapped[str] = mapped_column(String(500), nullable=False)
    default_headers: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    organization: Mapped[str] = mapped_column(String(120), default="", nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc, onupdate=now_utc, nullable=False)


class ModelProfile(Base):
    __tablename__ = "model_profiles"
    __table_args__ = (UniqueConstraint("workspace_id", "purpose", name="uq_model_profile_workspace_purpose"),)

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    workspace_id: Mapped[str] = mapped_column(ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False, index=True)
    provider_id: Mapped[str] = mapped_column(ForeignKey("llm_providers.id", ondelete="CASCADE"), nullable=False, index=True)
    purpose: Mapped[str] = mapped_column(String(40), nullable=False)
    model_name: Mapped[str] = mapped_column(String(120), nullable=False)
    reasoning_effort: Mapped[str] = mapped_column(String(32), default="medium", nullable=False)
    max_context_tokens: Mapped[int] = mapped_column(Integer, default=128000, nullable=False)
    max_output_tokens: Mapped[int] = mapped_column(Integer, default=4096, nullable=False)
    input_token_price: Mapped[Decimal] = mapped_column(Numeric(12, 8), default=Decimal("0"), nullable=False)
    output_token_price: Mapped[Decimal] = mapped_column(Numeric(12, 8), default=Decimal("0"), nullable=False)
    cache_policy: Mapped[str] = mapped_column(String(40), default="semantic", nullable=False)
    timeout_seconds: Mapped[int] = mapped_column(Integer, default=90, nullable=False)
    retry_count: Mapped[int] = mapped_column(Integer, default=2, nullable=False)
    budget_limit: Mapped[Decimal] = mapped_column(Numeric(12, 4), default=Decimal("0"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc, onupdate=now_utc, nullable=False)


class AIInvocationLog(Base):
    __tablename__ = "ai_invocation_logs"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    workspace_id: Mapped[str] = mapped_column(ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False, index=True)
    provider_id: Mapped[str | None] = mapped_column(ForeignKey("llm_providers.id", ondelete="SET NULL"), nullable=True, index=True)
    model_profile_id: Mapped[str | None] = mapped_column(ForeignKey("model_profiles.id", ondelete="SET NULL"), nullable=True, index=True)
    agent_run_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    tool_call_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    actor_email: Mapped[str] = mapped_column(String(254), nullable=False)
    purpose: Mapped[str] = mapped_column(String(40), nullable=False)
    data_policy: Mapped[str] = mapped_column(String(32), nullable=False)
    provider_name: Mapped[str] = mapped_column(String(120), default="", nullable=False, index=True)
    model_alias: Mapped[str] = mapped_column(String(160), default="", nullable=False, index=True)
    model_name: Mapped[str] = mapped_column(String(160), default="", nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(32), default=AIInvocationStatus.queued.value, nullable=False, index=True)
    input_summary: Mapped[str] = mapped_column(String(500), nullable=False)
    input_data_types: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    includes_source_code: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    token_prompt: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    token_completion: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    estimated_cost: Mapped[Decimal] = mapped_column(Numeric(12, 6), default=Decimal("0"), nullable=False)
    cache_hit: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    latency_ms: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    attempts: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    usage: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    raw_invocation_id: Mapped[str] = mapped_column(String(160), default="", nullable=False)
    failure_reason: Mapped[str] = mapped_column(String(500), default="", nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc, nullable=False, index=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class ProviderCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    api_base_url: HttpUrl
    api_key: str = Field(min_length=1, max_length=500)
    default_headers: dict[str, str] = Field(default_factory=dict)
    organization: str = Field(default="", max_length=120)


class ProviderResponse(BaseModel):
    id: str
    workspace_id: str
    name: str
    api_base_url: str
    api_key_masked: str
    has_api_key: bool
    default_headers: dict[str, str]
    organization: str
    is_active: bool
    created_at: datetime
    updated_at: datetime


class ModelProfileCreate(BaseModel):
    provider_id: str
    purpose: AIPurpose
    model_name: str = Field(min_length=1, max_length=120)
    reasoning_effort: Literal["low", "medium", "high", "xhigh"] = "medium"
    max_context_tokens: int = Field(default=128000, ge=1)
    max_output_tokens: int = Field(default=4096, ge=1)
    input_token_price: Decimal = Field(default=Decimal("0"), ge=0)
    output_token_price: Decimal = Field(default=Decimal("0"), ge=0)
    cache_policy: Literal["disabled", "prompt", "semantic"] = "semantic"
    timeout_seconds: int = Field(default=90, ge=1, le=600)
    retry_count: int = Field(default=2, ge=0, le=10)
    budget_limit: Decimal = Field(default=Decimal("0"), ge=0)


class ModelProfileResponse(BaseModel):
    id: str
    workspace_id: str
    provider_id: str
    purpose: str
    model_name: str
    reasoning_effort: str
    max_context_tokens: int
    max_output_tokens: int
    input_token_price: Decimal
    output_token_price: Decimal
    cache_policy: str
    timeout_seconds: int
    retry_count: int
    budget_limit: Decimal
    created_at: datetime
    updated_at: datetime


class AISettingsUpdate(BaseModel):
    data_policy: AIDataPolicyName


class AISettingsResponse(BaseModel):
    id: str
    workspace_id: str
    data_policy: str
    updated_by: str
    created_at: datetime
    updated_at: datetime


class AIInvocationStart(BaseModel):
    purpose: AIPurpose
    input_summary: str = Field(min_length=1, max_length=500)
    input_data_types: list[str] = Field(default_factory=list, max_length=20)
    includes_source_code: bool = False

    @field_validator("input_data_types")
    @classmethod
    def compact_data_types(cls, value: list[str]) -> list[str]:
        return [item.strip()[:80] for item in value if item.strip()]


class AIInvocationComplete(BaseModel):
    status: Literal["succeeded", "failed"]
    token_prompt: int = Field(default=0, ge=0)
    token_completion: int = Field(default=0, ge=0)
    cache_hit: bool = False
    latency_ms: int = Field(default=0, ge=0)
    failure_reason: str = Field(default="", max_length=500)


class AIInvocationResponse(BaseModel):
    id: str
    workspace_id: str
    provider_id: str | None
    model_profile_id: str | None
    agent_run_id: str | None
    tool_call_id: str | None
    actor_email: str
    purpose: str
    data_policy: str
    provider_name: str
    model_alias: str
    model_name: str
    status: str
    input_summary: str
    input_data_types: list[str]
    includes_source_code: bool
    token_prompt: int
    token_completion: int
    estimated_cost: Decimal
    cache_hit: bool
    latency_ms: int
    attempts: int
    usage: dict[str, Any]
    raw_invocation_id: str
    failure_reason: str
    created_at: datetime
    completed_at: datetime | None


def get_db(request: Request):
    yield from request.app.state.database.session()


DbSession = Annotated[Session, Depends(get_db)]

router = APIRouter(prefix="/api/workspaces/{workspace_id}", tags=["ai-config"])


def mask_api_key(api_key: str) -> str:
    if len(api_key) <= 8:
        return "****"
    return f"{api_key[:4]}...{api_key[-4:]}"


def provider_to_response(provider: LLMProvider) -> ProviderResponse:
    return ProviderResponse(
        id=provider.id,
        workspace_id=provider.workspace_id,
        name=provider.name,
        api_base_url=provider.api_base_url,
        api_key_masked=mask_api_key(provider.api_key_secret),
        has_api_key=bool(provider.api_key_secret),
        default_headers=provider.default_headers,
        organization=provider.organization,
        is_active=provider.is_active,
        created_at=provider.created_at,
        updated_at=provider.updated_at,
    )


def model_profile_to_response(profile: ModelProfile) -> ModelProfileResponse:
    return ModelProfileResponse(
        id=profile.id,
        workspace_id=profile.workspace_id,
        provider_id=profile.provider_id,
        purpose=profile.purpose,
        model_name=profile.model_name,
        reasoning_effort=profile.reasoning_effort,
        max_context_tokens=profile.max_context_tokens,
        max_output_tokens=profile.max_output_tokens,
        input_token_price=profile.input_token_price,
        output_token_price=profile.output_token_price,
        cache_policy=profile.cache_policy,
        timeout_seconds=profile.timeout_seconds,
        retry_count=profile.retry_count,
        budget_limit=profile.budget_limit,
        created_at=profile.created_at,
        updated_at=profile.updated_at,
    )


def settings_to_response(settings: WorkspaceAISettings) -> AISettingsResponse:
    return AISettingsResponse(
        id=settings.id,
        workspace_id=settings.workspace_id,
        data_policy=settings.data_policy,
        updated_by=settings.updated_by,
        created_at=settings.created_at,
        updated_at=settings.updated_at,
    )


def invocation_to_response(invocation: AIInvocationLog) -> AIInvocationResponse:
    return AIInvocationResponse(
        id=invocation.id,
        workspace_id=invocation.workspace_id,
        provider_id=invocation.provider_id,
        model_profile_id=invocation.model_profile_id,
        agent_run_id=invocation.agent_run_id,
        tool_call_id=invocation.tool_call_id,
        actor_email=invocation.actor_email,
        purpose=invocation.purpose,
        data_policy=invocation.data_policy,
        provider_name=invocation.provider_name,
        model_alias=invocation.model_alias,
        model_name=invocation.model_name,
        status=invocation.status,
        input_summary=invocation.input_summary,
        input_data_types=invocation.input_data_types,
        includes_source_code=invocation.includes_source_code,
        token_prompt=invocation.token_prompt,
        token_completion=invocation.token_completion,
        estimated_cost=invocation.estimated_cost,
        cache_hit=invocation.cache_hit,
        latency_ms=invocation.latency_ms,
        attempts=invocation.attempts,
        usage=invocation.usage,
        raw_invocation_id=invocation.raw_invocation_id,
        failure_reason=invocation.failure_reason,
        created_at=invocation.created_at,
        completed_at=invocation.completed_at,
    )


def get_or_create_ai_settings(db: Session, workspace_id: str, actor_email: str = "system") -> WorkspaceAISettings:
    settings = db.scalar(select(WorkspaceAISettings).where(WorkspaceAISettings.workspace_id == workspace_id))
    if settings is not None:
        return settings
    settings = WorkspaceAISettings(workspace_id=workspace_id, updated_by=actor_email)
    db.add(settings)
    db.flush()
    return settings


def get_provider_or_404(db: Session, workspace_id: str, provider_id: str) -> LLMProvider:
    provider = db.scalar(select(LLMProvider).where(LLMProvider.id == provider_id, LLMProvider.workspace_id == workspace_id))
    if provider is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Provider not found")
    return provider


def get_profile_for_purpose(db: Session, workspace_id: str, purpose: AIPurpose) -> ModelProfile | None:
    return db.scalar(select(ModelProfile).where(ModelProfile.workspace_id == workspace_id, ModelProfile.purpose == purpose.value))


def is_internal_provider(provider: LLMProvider) -> bool:
    hostname = urlparse(provider.api_base_url).hostname or ""
    if hostname in {"localhost", "127.0.0.1", "::1"}:
        return True
    if hostname.endswith(".local") or hostname.endswith(".internal"):
        return True
    try:
        return ip_address(hostname).is_private
    except ValueError:
        return False


def rejection_reason(
    *,
    policy: str,
    provider: LLMProvider | None,
    includes_source_code: bool,
) -> str:
    if policy == AIDataPolicyName.ai_disabled.value:
        return "AI tasks are disabled for this workspace"
    if policy == AIDataPolicyName.no_source_code.value and includes_source_code:
        return "Workspace policy forbids sending source code to AI providers"
    if policy == AIDataPolicyName.internal_only.value:
        if provider is None:
            return "Workspace policy requires an internal model provider"
        if not is_internal_provider(provider):
            return "Workspace policy allows only internal model endpoints"
    return ""


def estimate_cost(profile: ModelProfile | None, prompt_tokens: int, completion_tokens: int) -> Decimal:
    if profile is None:
        return Decimal("0")
    prompt_cost = Decimal(prompt_tokens) * profile.input_token_price / Decimal(1_000_000)
    completion_cost = Decimal(completion_tokens) * profile.output_token_price / Decimal(1_000_000)
    return (prompt_cost + completion_cost).quantize(Decimal("0.000001"))


@router.get("/ai-settings", response_model=AISettingsResponse)
def get_ai_settings(workspace_id: str, db: DbSession) -> AISettingsResponse:
    get_workspace_or_404(db, workspace_id)
    settings = get_or_create_ai_settings(db, workspace_id)
    db.commit()
    db.refresh(settings)
    return settings_to_response(settings)


@router.put("/ai-settings", response_model=AISettingsResponse)
def update_ai_settings(workspace_id: str, payload: AISettingsUpdate, db: DbSession, actor_email: ActorEmail) -> AISettingsResponse:
    get_workspace_or_404(db, workspace_id)
    settings = get_or_create_ai_settings(db, workspace_id, actor_email)
    before = {"data_policy": settings.data_policy}
    settings.data_policy = payload.data_policy.value
    settings.updated_by = actor_email
    settings.updated_at = now_utc()
    audit(
        db,
        workspace_id=workspace_id,
        actor_email=actor_email,
        action="ai_policy.updated",
        entity_type="WorkspaceAISettings",
        entity_id=settings.id,
        summary=f"Updated AI data policy to {settings.data_policy}",
        before=before,
        after={"data_policy": settings.data_policy},
    )
    db.commit()
    db.refresh(settings)
    return settings_to_response(settings)


@router.get("/llm-providers", response_model=list[ProviderResponse])
def list_providers(workspace_id: str, db: DbSession) -> list[ProviderResponse]:
    get_workspace_or_404(db, workspace_id)
    providers = db.scalars(select(LLMProvider).where(LLMProvider.workspace_id == workspace_id).order_by(LLMProvider.created_at)).all()
    return [provider_to_response(provider) for provider in providers]


@router.post("/llm-providers", response_model=ProviderResponse, status_code=status.HTTP_201_CREATED)
def create_provider(workspace_id: str, payload: ProviderCreate, db: DbSession, actor_email: ActorEmail) -> ProviderResponse:
    get_workspace_or_404(db, workspace_id)
    provider = LLMProvider(
        workspace_id=workspace_id,
        name=payload.name,
        api_base_url=str(payload.api_base_url).rstrip("/"),
        api_key_secret=payload.api_key,
        default_headers=payload.default_headers,
        organization=payload.organization,
    )
    db.add(provider)
    db.flush()
    audit(
        db,
        workspace_id=workspace_id,
        actor_email=actor_email,
        action="llm_provider.created",
        entity_type="LLMProvider",
        entity_id=provider.id,
        summary=f"Created LLM provider {provider.name}",
        after={
            "name": provider.name,
            "api_base_url": provider.api_base_url,
            "default_headers": provider.default_headers,
            "organization": provider.organization,
            "has_api_key": True,
        },
    )
    db.commit()
    db.refresh(provider)
    return provider_to_response(provider)


@router.get("/model-profiles", response_model=list[ModelProfileResponse])
def list_model_profiles(workspace_id: str, db: DbSession) -> list[ModelProfileResponse]:
    get_workspace_or_404(db, workspace_id)
    profiles = db.scalars(select(ModelProfile).where(ModelProfile.workspace_id == workspace_id).order_by(ModelProfile.purpose)).all()
    return [model_profile_to_response(profile) for profile in profiles]


@router.post("/model-profiles", response_model=ModelProfileResponse, status_code=status.HTTP_201_CREATED)
def upsert_model_profile(workspace_id: str, payload: ModelProfileCreate, db: DbSession, actor_email: ActorEmail) -> ModelProfileResponse:
    get_workspace_or_404(db, workspace_id)
    get_provider_or_404(db, workspace_id, payload.provider_id)
    existing = get_profile_for_purpose(db, workspace_id, payload.purpose)
    if existing is None:
        profile = ModelProfile(workspace_id=workspace_id, **payload.model_dump(mode="json"))
        db.add(profile)
        action = "model_profile.created"
        before = None
    else:
        profile = existing
        before = model_profile_to_response(profile).model_dump(mode="json")
        for field, value in payload.model_dump(mode="json").items():
            setattr(profile, field, value)
        profile.updated_at = now_utc()
        action = "model_profile.updated"
    try:
        db.flush()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Model profile purpose already exists") from exc

    audit(
        db,
        workspace_id=workspace_id,
        actor_email=actor_email,
        action=action,
        entity_type="ModelProfile",
        entity_id=profile.id,
        summary=f"Configured {profile.purpose} model profile",
        before=before,
        after=model_profile_to_response(profile).model_dump(mode="json"),
    )
    db.commit()
    db.refresh(profile)
    return model_profile_to_response(profile)


@router.post("/ai-invocations", response_model=AIInvocationResponse, status_code=status.HTTP_201_CREATED)
def start_ai_invocation(workspace_id: str, payload: AIInvocationStart, db: DbSession, actor_email: ActorEmail) -> AIInvocationResponse:
    get_workspace_or_404(db, workspace_id)
    settings = get_or_create_ai_settings(db, workspace_id, actor_email)
    profile = get_profile_for_purpose(db, workspace_id, payload.purpose)
    provider = get_provider_or_404(db, workspace_id, profile.provider_id) if profile else None
    reason = rejection_reason(policy=settings.data_policy, provider=provider, includes_source_code=payload.includes_source_code)
    if reason == "" and profile is None:
        reason = f"No model profile configured for {payload.purpose.value}"

    invocation = AIInvocationLog(
        workspace_id=workspace_id,
        provider_id=provider.id if provider else None,
        model_profile_id=profile.id if profile else None,
        actor_email=actor_email,
        purpose=payload.purpose.value,
        data_policy=settings.data_policy,
        status=AIInvocationStatus.rejected.value if reason else AIInvocationStatus.queued.value,
        input_summary=payload.input_summary,
        input_data_types=payload.input_data_types,
        includes_source_code=payload.includes_source_code,
        failure_reason=reason,
        completed_at=now_utc() if reason else None,
    )
    db.add(invocation)
    db.flush()
    audit(
        db,
        workspace_id=workspace_id,
        actor_email=actor_email,
        action="ai_invocation.rejected" if reason else "ai_invocation.queued",
        entity_type="AIInvocationLog",
        entity_id=invocation.id,
        summary=reason or f"Queued {payload.purpose.value} AI task",
        after={
            "purpose": invocation.purpose,
            "data_policy": invocation.data_policy,
            "status": invocation.status,
            "input_summary": invocation.input_summary,
            "input_data_types": invocation.input_data_types,
            "includes_source_code": invocation.includes_source_code,
        },
    )
    db.commit()
    db.refresh(invocation)
    if reason:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=reason)
    return invocation_to_response(invocation)


@router.patch("/ai-invocations/{invocation_id}", response_model=AIInvocationResponse)
def complete_ai_invocation(
    workspace_id: str,
    invocation_id: str,
    payload: AIInvocationComplete,
    db: DbSession,
    actor_email: ActorEmail,
) -> AIInvocationResponse:
    get_workspace_or_404(db, workspace_id)
    invocation = db.scalar(
        select(AIInvocationLog).where(AIInvocationLog.id == invocation_id, AIInvocationLog.workspace_id == workspace_id)
    )
    if invocation is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="AI invocation not found")
    if invocation.status == AIInvocationStatus.rejected.value:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Rejected AI invocation cannot be completed")

    profile = db.get(ModelProfile, invocation.model_profile_id) if invocation.model_profile_id else None
    invocation.status = payload.status
    invocation.token_prompt = payload.token_prompt
    invocation.token_completion = payload.token_completion
    invocation.cache_hit = payload.cache_hit
    invocation.latency_ms = payload.latency_ms
    invocation.failure_reason = payload.failure_reason if payload.status == AIInvocationStatus.failed.value else ""
    invocation.estimated_cost = estimate_cost(profile, payload.token_prompt, payload.token_completion)
    invocation.completed_at = now_utc()
    audit(
        db,
        workspace_id=workspace_id,
        actor_email=actor_email,
        action=f"ai_invocation.{payload.status}",
        entity_type="AIInvocationLog",
        entity_id=invocation.id,
        summary=f"Recorded {invocation.purpose} AI call summary",
        after={
            "status": invocation.status,
            "token_prompt": invocation.token_prompt,
            "token_completion": invocation.token_completion,
            "estimated_cost": str(invocation.estimated_cost),
            "cache_hit": invocation.cache_hit,
            "latency_ms": invocation.latency_ms,
            "failure_reason": invocation.failure_reason,
        },
    )
    db.commit()
    db.refresh(invocation)
    return invocation_to_response(invocation)


@router.get("/ai-invocations", response_model=list[AIInvocationResponse])
def list_ai_invocations(workspace_id: str, db: DbSession, limit: int = Query(default=50, ge=1, le=200)) -> list[AIInvocationResponse]:
    get_workspace_or_404(db, workspace_id)
    invocations = db.scalars(
        select(AIInvocationLog)
        .where(AIInvocationLog.workspace_id == workspace_id)
        .order_by(AIInvocationLog.created_at.desc(), AIInvocationLog.id.desc())
        .limit(limit)
    ).all()
    return [invocation_to_response(invocation) for invocation in invocations]
