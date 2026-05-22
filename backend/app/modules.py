from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, status
from pydantic import BaseModel, Field
from sqlalchemy import DateTime, ForeignKey, Integer, String, UniqueConstraint, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Mapped, Session, mapped_column

from app.database import Base
from app.workspaces import ActorEmail, audit, get_project_or_404, get_workspace_or_404, new_id, now_utc


class MappingRuleType(StrEnum):
    directory = "directory"
    file = "file"
    api = "api"
    service = "service"
    config_key = "config_key"
    database_migration = "database_migration"
    keyword = "keyword"


class MappingSource(StrEnum):
    manual = "manual"
    ai_repository = "ai_repository"
    ai_history = "ai_history"
    diff_confirmation = "diff_confirmation"


class ProjectModule(Base):
    __tablename__ = "project_modules"
    __table_args__ = (UniqueConstraint("project_id", "key", name="uq_module_key_per_project"),)

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    workspace_id: Mapped[str] = mapped_column(ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False, index=True)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True)
    key: Mapped[str] = mapped_column(String(48), nullable=False)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    description: Mapped[str] = mapped_column(String(500), default="", nullable=False)
    owner: Mapped[str] = mapped_column(String(120), default="", nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc, onupdate=now_utc, nullable=False)


class ModuleMappingRule(Base):
    __tablename__ = "module_mapping_rules"
    __table_args__ = (
        UniqueConstraint("module_id", "rule_type", "pattern", name="uq_mapping_rule_pattern_per_module"),
    )

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    workspace_id: Mapped[str] = mapped_column(ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False, index=True)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True)
    module_id: Mapped[str] = mapped_column(ForeignKey("project_modules.id", ondelete="CASCADE"), nullable=False, index=True)
    rule_type: Mapped[str] = mapped_column(String(40), nullable=False)
    pattern: Mapped[str] = mapped_column(String(500), nullable=False)
    source: Mapped[str] = mapped_column(String(40), nullable=False)
    description: Mapped[str] = mapped_column(String(500), default="", nullable=False)
    confidence: Mapped[int] = mapped_column(Integer, default=100, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc, onupdate=now_utc, nullable=False)


class ModuleCreate(BaseModel):
    key: str = Field(pattern=r"^[A-Z][A-Z0-9_]{1,47}$")
    name: str = Field(min_length=1, max_length=120)
    description: str = Field(default="", max_length=500)
    owner: str = Field(default="", max_length=120)


class ModuleUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    description: str | None = Field(default=None, max_length=500)
    owner: str | None = Field(default=None, max_length=120)


class MappingRuleCreate(BaseModel):
    rule_type: MappingRuleType
    pattern: str = Field(min_length=1, max_length=500)
    source: MappingSource = MappingSource.manual
    description: str = Field(default="", max_length=500)
    confidence: int = Field(default=100, ge=0, le=100)


class MappingRuleUpdate(BaseModel):
    rule_type: MappingRuleType | None = None
    pattern: str | None = Field(default=None, min_length=1, max_length=500)
    source: MappingSource | None = None
    description: str | None = Field(default=None, max_length=500)
    confidence: int | None = Field(default=None, ge=0, le=100)


class MappingRuleResponse(BaseModel):
    id: str
    workspace_id: str
    project_id: str
    module_id: str
    rule_type: str
    pattern: str
    source: str
    description: str
    confidence: int
    created_at: datetime
    updated_at: datetime


class ModuleResponse(BaseModel):
    id: str
    workspace_id: str
    project_id: str
    key: str
    name: str
    description: str
    owner: str
    mapping_rules: list[MappingRuleResponse]
    created_at: datetime
    updated_at: datetime


def get_db(request: Request):
    yield from request.app.state.database.session()


DbSession = Annotated[Session, Depends(get_db)]

router = APIRouter(prefix="/api/workspaces/{workspace_id}/projects/{project_id}", tags=["modules"])


def serialize_rule(rule: ModuleMappingRule) -> MappingRuleResponse:
    return MappingRuleResponse(
        id=rule.id,
        workspace_id=rule.workspace_id,
        project_id=rule.project_id,
        module_id=rule.module_id,
        rule_type=rule.rule_type,
        pattern=rule.pattern,
        source=rule.source,
        description=rule.description,
        confidence=rule.confidence,
        created_at=rule.created_at,
        updated_at=rule.updated_at,
    )


def serialize_module(module: ProjectModule, rules: list[ModuleMappingRule]) -> ModuleResponse:
    return ModuleResponse(
        id=module.id,
        workspace_id=module.workspace_id,
        project_id=module.project_id,
        key=module.key,
        name=module.name,
        description=module.description,
        owner=module.owner,
        mapping_rules=[serialize_rule(rule) for rule in rules],
        created_at=module.created_at,
        updated_at=module.updated_at,
    )


def module_snapshot(module: ProjectModule) -> dict[str, str]:
    return {
        "key": module.key,
        "name": module.name,
        "description": module.description,
        "owner": module.owner,
        "project_id": module.project_id,
    }


def rule_snapshot(rule: ModuleMappingRule) -> dict[str, str | int]:
    return {
        "module_id": rule.module_id,
        "rule_type": rule.rule_type,
        "pattern": rule.pattern,
        "source": rule.source,
        "description": rule.description,
        "confidence": rule.confidence,
    }


def get_module_or_404(db: Session, workspace_id: str, project_id: str, module_id: str) -> ProjectModule:
    module = db.scalar(
        select(ProjectModule).where(
            ProjectModule.id == module_id,
            ProjectModule.workspace_id == workspace_id,
            ProjectModule.project_id == project_id,
        )
    )
    if module is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Module not found")
    return module


def get_rule_or_404(
    db: Session,
    workspace_id: str,
    project_id: str,
    module_id: str,
    rule_id: str,
) -> ModuleMappingRule:
    rule = db.scalar(
        select(ModuleMappingRule).where(
            ModuleMappingRule.id == rule_id,
            ModuleMappingRule.workspace_id == workspace_id,
            ModuleMappingRule.project_id == project_id,
            ModuleMappingRule.module_id == module_id,
        )
    )
    if rule is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Mapping rule not found")
    return rule


def rules_for_module(db: Session, module_id: str) -> list[ModuleMappingRule]:
    return list(
        db.scalars(
            select(ModuleMappingRule)
            .where(ModuleMappingRule.module_id == module_id)
            .order_by(ModuleMappingRule.rule_type, ModuleMappingRule.pattern)
        ).all()
    )


@router.get("/modules", response_model=list[ModuleResponse])
def list_modules(workspace_id: str, project_id: str, db: DbSession) -> list[ModuleResponse]:
    get_workspace_or_404(db, workspace_id)
    get_project_or_404(db, workspace_id, project_id)
    modules = db.scalars(
        select(ProjectModule)
        .where(ProjectModule.workspace_id == workspace_id, ProjectModule.project_id == project_id)
        .order_by(ProjectModule.key)
    ).all()
    return [serialize_module(module, rules_for_module(db, module.id)) for module in modules]


@router.get("/mapping-rules", response_model=list[MappingRuleResponse])
def list_mapping_rules(
    workspace_id: str,
    project_id: str,
    db: DbSession,
    module_id: str | None = Query(default=None),
    rule_type: MappingRuleType | None = Query(default=None),
    source: MappingSource | None = Query(default=None),
) -> list[MappingRuleResponse]:
    get_workspace_or_404(db, workspace_id)
    get_project_or_404(db, workspace_id, project_id)
    statement = (
        select(ModuleMappingRule)
        .where(ModuleMappingRule.workspace_id == workspace_id, ModuleMappingRule.project_id == project_id)
        .order_by(ModuleMappingRule.rule_type, ModuleMappingRule.pattern)
    )
    if module_id:
        get_module_or_404(db, workspace_id, project_id, module_id)
        statement = statement.where(ModuleMappingRule.module_id == module_id)
    if rule_type:
        statement = statement.where(ModuleMappingRule.rule_type == rule_type.value)
    if source:
        statement = statement.where(ModuleMappingRule.source == source.value)
    return [serialize_rule(rule) for rule in db.scalars(statement).all()]


@router.post("/modules", response_model=ModuleResponse, status_code=status.HTTP_201_CREATED)
def create_module(workspace_id: str, project_id: str, payload: ModuleCreate, db: DbSession, actor_email: ActorEmail) -> ModuleResponse:
    get_workspace_or_404(db, workspace_id)
    get_project_or_404(db, workspace_id, project_id)
    module = ProjectModule(
        workspace_id=workspace_id,
        project_id=project_id,
        key=payload.key,
        name=payload.name,
        description=payload.description,
        owner=payload.owner,
    )
    db.add(module)
    try:
        db.flush()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Module key already exists") from exc

    audit(
        db,
        workspace_id=workspace_id,
        actor_email=actor_email,
        action="module.created",
        entity_type="ProjectModule",
        entity_id=module.id,
        summary=f"Created module {module.key}",
        after=module_snapshot(module),
    )
    db.commit()
    db.refresh(module)
    return serialize_module(module, [])


@router.patch("/modules/{module_id}", response_model=ModuleResponse)
def update_module(
    workspace_id: str,
    project_id: str,
    module_id: str,
    payload: ModuleUpdate,
    db: DbSession,
    actor_email: ActorEmail,
) -> ModuleResponse:
    module = get_module_or_404(db, workspace_id, project_id, module_id)
    before = module_snapshot(module)
    update_data = payload.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(module, field, value)
    module.updated_at = now_utc()
    db.flush()
    after = module_snapshot(module)
    audit(
        db,
        workspace_id=workspace_id,
        actor_email=actor_email,
        action="module.updated",
        entity_type="ProjectModule",
        entity_id=module.id,
        summary=f"Updated module {module.key}",
        before=before,
        after=after,
    )
    db.commit()
    db.refresh(module)
    return serialize_module(module, rules_for_module(db, module.id))


@router.delete("/modules/{module_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_module(workspace_id: str, project_id: str, module_id: str, db: DbSession, actor_email: ActorEmail) -> Response:
    module = get_module_or_404(db, workspace_id, project_id, module_id)
    rule_count = db.scalar(select(func.count()).select_from(ModuleMappingRule).where(ModuleMappingRule.module_id == module_id))
    before = {**module_snapshot(module), "mapping_rule_count": int(rule_count or 0)}
    for rule in rules_for_module(db, module_id):
        db.delete(rule)
    db.delete(module)
    audit(
        db,
        workspace_id=workspace_id,
        actor_email=actor_email,
        action="module.deleted",
        entity_type="ProjectModule",
        entity_id=module_id,
        summary=f"Deleted module {before['key']}",
        before=before,
    )
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/modules/{module_id}/mapping-rules", response_model=MappingRuleResponse, status_code=status.HTTP_201_CREATED)
def create_mapping_rule(
    workspace_id: str,
    project_id: str,
    module_id: str,
    payload: MappingRuleCreate,
    db: DbSession,
    actor_email: ActorEmail,
) -> MappingRuleResponse:
    module = get_module_or_404(db, workspace_id, project_id, module_id)
    rule = ModuleMappingRule(
        workspace_id=workspace_id,
        project_id=project_id,
        module_id=module.id,
        rule_type=payload.rule_type.value,
        pattern=payload.pattern,
        source=payload.source.value,
        description=payload.description,
        confidence=payload.confidence,
    )
    db.add(rule)
    try:
        db.flush()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Mapping rule already exists") from exc

    audit(
        db,
        workspace_id=workspace_id,
        actor_email=actor_email,
        action="mapping_rule.created",
        entity_type="ModuleMappingRule",
        entity_id=rule.id,
        summary=f"Added {rule.rule_type} mapping to {module.key}",
        after=rule_snapshot(rule),
    )
    db.commit()
    db.refresh(rule)
    return serialize_rule(rule)


@router.patch("/modules/{module_id}/mapping-rules/{rule_id}", response_model=MappingRuleResponse)
def update_mapping_rule(
    workspace_id: str,
    project_id: str,
    module_id: str,
    rule_id: str,
    payload: MappingRuleUpdate,
    db: DbSession,
    actor_email: ActorEmail,
) -> MappingRuleResponse:
    get_module_or_404(db, workspace_id, project_id, module_id)
    rule = get_rule_or_404(db, workspace_id, project_id, module_id, rule_id)
    before = rule_snapshot(rule)
    update_data = payload.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(rule, field, value.value if isinstance(value, StrEnum) else value)
    rule.updated_at = now_utc()
    try:
        db.flush()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Mapping rule already exists") from exc
    after = rule_snapshot(rule)
    audit(
        db,
        workspace_id=workspace_id,
        actor_email=actor_email,
        action="mapping_rule.updated",
        entity_type="ModuleMappingRule",
        entity_id=rule.id,
        summary=f"Updated {rule.rule_type} mapping",
        before=before,
        after=after,
    )
    db.commit()
    db.refresh(rule)
    return serialize_rule(rule)


@router.delete("/modules/{module_id}/mapping-rules/{rule_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_mapping_rule(
    workspace_id: str,
    project_id: str,
    module_id: str,
    rule_id: str,
    db: DbSession,
    actor_email: ActorEmail,
) -> Response:
    get_module_or_404(db, workspace_id, project_id, module_id)
    rule = get_rule_or_404(db, workspace_id, project_id, module_id, rule_id)
    before = rule_snapshot(rule)
    db.delete(rule)
    audit(
        db,
        workspace_id=workspace_id,
        actor_email=actor_email,
        action="mapping_rule.deleted",
        entity_type="ModuleMappingRule",
        entity_id=rule_id,
        summary=f"Deleted {before['rule_type']} mapping",
        before=before,
    )
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
