from __future__ import annotations

import re
from datetime import datetime
from enum import StrEnum
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, status
from pydantic import BaseModel, Field
from sqlalchemy import DateTime, ForeignKey, Integer, String, UniqueConstraint, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Mapped, Session, mapped_column

from app.cases.domain import CaseDraft, CaseRevision, TestCase
from app.platform.database import Base
from app.workspace.routes import ActorEmail, audit, get_project_or_404, get_workspace_or_404, new_id, now_utc, require_workspace_owner


class ModuleStatus(StrEnum):
    active = "active"
    archived = "archived"


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
    __table_args__ = (
        UniqueConstraint("project_id", "parent_id", "slug", name="uq_module_slug_per_parent"),
        UniqueConstraint("project_id", "path", name="uq_module_path_per_project"),
    )

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    workspace_id: Mapped[str] = mapped_column(ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False, index=True)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True)
    parent_id: Mapped[str | None] = mapped_column(ForeignKey("project_modules.id", ondelete="SET NULL"), nullable=True, index=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    slug: Mapped[str] = mapped_column(String(80), nullable=False)
    code: Mapped[str] = mapped_column(String(48), default="", nullable=False)
    path: Mapped[str] = mapped_column(String(500), nullable=False, index=True)
    path_label: Mapped[str] = mapped_column(String(500), nullable=False)
    depth: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    sort_order: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    status: Mapped[str] = mapped_column(String(32), default=ModuleStatus.active.value, nullable=False, index=True)
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
    name: str = Field(min_length=1, max_length=120)
    slug: str | None = Field(default=None, max_length=80)
    code: str = Field(default="", max_length=48)
    key: str = Field(default="", max_length=48)
    parent_id: str | None = None
    description: str = Field(default="", max_length=500)
    owner: str = Field(default="", max_length=120)
    sort_order: int = 0


class ModuleUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    slug: str | None = Field(default=None, min_length=1, max_length=80)
    code: str | None = Field(default=None, max_length=48)
    parent_id: str | None = None
    description: str | None = Field(default=None, max_length=500)
    owner: str | None = Field(default=None, max_length=120)
    sort_order: int | None = None
    status: ModuleStatus | None = None


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
    parent_id: str | None
    name: str
    slug: str
    code: str
    key: str
    path: str
    path_label: str
    depth: int
    sort_order: int
    status: str
    description: str
    owner: str
    reference_count: int
    mapping_rules: list[MappingRuleResponse]
    created_at: datetime
    updated_at: datetime


class ModuleTreeNode(ModuleResponse):
    children: list["ModuleTreeNode"] = Field(default_factory=list)


def get_db(request: Request):
    yield from request.app.state.database.session()


DbSession = Annotated[Session, Depends(get_db)]

router = APIRouter(prefix="/api/workspaces/{workspace_id}/projects/{project_id}", tags=["modules"])


PINYIN_HINTS = {
    "操": "cao",
    "控": "kong",
    "键": "jian",
    "鼠": "shu",
    "手": "shou",
    "柄": "bing",
    "支": "zhi",
    "付": "fu",
    "退": "tui",
    "款": "kuan",
    "登": "deng",
    "录": "lu",
    "注": "zhu",
    "册": "ce",
    "订": "ding",
    "单": "dan",
    "搜": "sou",
    "索": "suo",
    "报": "bao",
    "告": "gao",
    "用": "yong",
    "例": "li",
    "模": "mo",
    "块": "kuai",
}


def normalize_slug(value: str) -> str:
    pieces = []
    for char in value.strip():
        if char.isascii():
            pieces.append(char.lower())
        elif char in PINYIN_HINTS:
            pieces.append(f"-{PINYIN_HINTS[char]}-")
    slug = re.sub(r"[^a-z0-9-]+", "-", "".join(pieces))
    slug = re.sub(r"-{2,}", "-", slug).strip("-")
    return slug[:80]


def ensure_slug(value: str, fallback_seed: str | None = None) -> str:
    slug = normalize_slug(value)
    if slug:
        return slug
    return f"module-{(fallback_seed or new_id())[:6].lower()}"


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


def module_reference_count(db: Session, module_id: str) -> int:
    counts = [
        db.scalar(select(func.count()).select_from(TestCase).where(TestCase.current_module_id == module_id)) or 0,
        db.scalar(select(func.count()).select_from(CaseDraft).where(CaseDraft.module_id == module_id)) or 0,
        db.scalar(select(func.count()).select_from(CaseRevision).where(CaseRevision.module_id == module_id)) or 0,
    ]
    return int(sum(counts))


def serialize_module(module: ProjectModule, rules: list[ModuleMappingRule], reference_count: int = 0) -> ModuleResponse:
    code = module.code or ""
    return ModuleResponse(
        id=module.id,
        workspace_id=module.workspace_id,
        project_id=module.project_id,
        parent_id=module.parent_id,
        name=module.name,
        slug=module.slug,
        code=code,
        key=code or module.slug.upper().replace("-", "_"),
        path=module.path,
        path_label=module.path_label,
        depth=module.depth,
        sort_order=module.sort_order,
        status=module.status,
        description=module.description,
        owner=module.owner,
        reference_count=reference_count,
        mapping_rules=[serialize_rule(rule) for rule in rules],
        created_at=module.created_at,
        updated_at=module.updated_at,
    )


def module_snapshot(module: ProjectModule) -> dict[str, str | int | None]:
    return {
        "parent_id": module.parent_id,
        "name": module.name,
        "slug": module.slug,
        "code": module.code,
        "path": module.path,
        "path_label": module.path_label,
        "depth": module.depth,
        "sort_order": module.sort_order,
        "status": module.status,
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


def child_modules(db: Session, module_id: str) -> list[ProjectModule]:
    return list(db.scalars(select(ProjectModule).where(ProjectModule.parent_id == module_id).order_by(ProjectModule.sort_order, ProjectModule.name)).all())


def descendant_modules(db: Session, module: ProjectModule, include_self: bool = True) -> list[ProjectModule]:
    modules = [module] if include_self else []
    for child in child_modules(db, module.id):
        modules.extend(descendant_modules(db, child, include_self=True))
    return modules


def descendant_module_ids(db: Session, module: ProjectModule, include_self: bool = True) -> list[str]:
    return [item.id for item in descendant_modules(db, module, include_self)]


def assert_unique_slug(db: Session, module: ProjectModule | None, workspace_id: str, project_id: str, parent_id: str | None, slug: str) -> None:
    statement = select(ProjectModule).where(
        ProjectModule.workspace_id == workspace_id,
        ProjectModule.project_id == project_id,
        ProjectModule.slug == slug,
    )
    if parent_id is None:
        statement = statement.where(ProjectModule.parent_id.is_(None))
    else:
        statement = statement.where(ProjectModule.parent_id == parent_id)
    existing = db.scalar(statement)
    if existing is not None and (module is None or existing.id != module.id):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Module slug already exists under this parent")


def recalc_module_paths(db: Session, module: ProjectModule) -> None:
    parent = db.get(ProjectModule, module.parent_id) if module.parent_id else None
    if parent is not None:
        module.path = f"{parent.path}/{module.slug}"
        module.path_label = f"{parent.path_label} / {module.name}"
        module.depth = parent.depth + 1
    else:
        module.path = module.slug
        module.path_label = module.name
        module.depth = 0
    module.updated_at = now_utc()
    for child in child_modules(db, module.id):
        recalc_module_paths(db, child)


def build_tree(modules: list[ProjectModule], by_id: dict[str, ModuleTreeNode]) -> list[ModuleTreeNode]:
    roots: list[ModuleTreeNode] = []
    for module in modules:
        node = by_id[module.id]
        if module.parent_id and module.parent_id in by_id:
            by_id[module.parent_id].children.append(node)
        else:
            roots.append(node)
    return roots


@router.get("/modules", response_model=list[ModuleResponse])
def list_modules(
    workspace_id: str,
    project_id: str,
    db: DbSession,
    include_archived_modules: bool = Query(default=False),
) -> list[ModuleResponse]:
    get_workspace_or_404(db, workspace_id)
    get_project_or_404(db, workspace_id, project_id)
    statement = select(ProjectModule).where(ProjectModule.workspace_id == workspace_id, ProjectModule.project_id == project_id)
    if not include_archived_modules:
        statement = statement.where(ProjectModule.status == ModuleStatus.active.value)
    modules = db.scalars(statement.order_by(ProjectModule.path)).all()
    return [serialize_module(module, rules_for_module(db, module.id), module_reference_count(db, module.id)) for module in modules]


@router.get("/modules/tree", response_model=list[ModuleTreeNode])
def list_module_tree(
    workspace_id: str,
    project_id: str,
    db: DbSession,
    include_archived_modules: bool = Query(default=False),
) -> list[ModuleTreeNode]:
    modules = list_modules(workspace_id, project_id, db, include_archived_modules)
    nodes = {module.id: ModuleTreeNode(**module.model_dump(), children=[]) for module in modules}
    ordered = db.scalars(
        select(ProjectModule)
        .where(ProjectModule.id.in_(nodes.keys()))
        .order_by(ProjectModule.depth, ProjectModule.sort_order, ProjectModule.name)
    ).all()
    return build_tree(list(ordered), nodes)


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
    require_workspace_owner(db, workspace_id, actor_email)
    parent = get_module_or_404(db, workspace_id, project_id, payload.parent_id) if payload.parent_id else None
    slug = ensure_slug(payload.slug or payload.name)
    assert_unique_slug(db, None, workspace_id, project_id, parent.id if parent else None, slug)
    module = ProjectModule(
        workspace_id=workspace_id,
        project_id=project_id,
        parent_id=parent.id if parent else None,
        name=payload.name,
        slug=slug,
        code=payload.code or payload.key,
        path=slug,
        path_label=payload.name,
        depth=0,
        sort_order=payload.sort_order,
        description=payload.description,
        owner=payload.owner,
    )
    db.add(module)
    db.flush()
    recalc_module_paths(db, module)
    try:
        db.flush()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Module path already exists") from exc

    audit(
        db,
        workspace_id=workspace_id,
        actor_email=actor_email,
        action="module.created",
        entity_type="ProjectModule",
        entity_id=module.id,
        summary=f"Created module {module.path_label}",
        after=module_snapshot(module),
    )
    db.commit()
    db.refresh(module)
    return serialize_module(module, [], 0)


@router.patch("/modules/{module_id}", response_model=ModuleResponse)
def update_module(
    workspace_id: str,
    project_id: str,
    module_id: str,
    payload: ModuleUpdate,
    db: DbSession,
    actor_email: ActorEmail,
) -> ModuleResponse:
    require_workspace_owner(db, workspace_id, actor_email)
    module = get_module_or_404(db, workspace_id, project_id, module_id)
    before = module_snapshot(module)
    update_data = payload.model_dump(exclude_unset=True)

    if "parent_id" in update_data:
        next_parent_id = update_data["parent_id"]
        if next_parent_id == module.id:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Module cannot be its own parent")
        if next_parent_id:
            next_parent = get_module_or_404(db, workspace_id, project_id, next_parent_id)
            if next_parent.id in descendant_module_ids(db, module, include_self=False):
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Module cannot move under its descendant")
            module.parent_id = next_parent.id
        else:
            module.parent_id = None
    if payload.slug is not None:
        module.slug = ensure_slug(payload.slug)
    if payload.name is not None:
        module.name = payload.name
    if payload.code is not None:
        module.code = payload.code
    if payload.description is not None:
        module.description = payload.description
    if payload.owner is not None:
        module.owner = payload.owner
    if payload.sort_order is not None:
        module.sort_order = payload.sort_order
    if payload.status is not None:
        targets = descendant_modules(db, module, include_self=True) if payload.status == ModuleStatus.archived else [module]
        for target in targets:
            target.status = payload.status.value
            target.updated_at = now_utc()

    assert_unique_slug(db, module, workspace_id, project_id, module.parent_id, module.slug)
    recalc_module_paths(db, module)
    try:
        db.flush()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Module path already exists") from exc
    after = module_snapshot(module)
    audit(
        db,
        workspace_id=workspace_id,
        actor_email=actor_email,
        action="module.updated",
        entity_type="ProjectModule",
        entity_id=module.id,
        summary=f"Updated module {module.path_label}",
        before=before,
        after=after,
    )
    db.commit()
    db.refresh(module)
    return serialize_module(module, rules_for_module(db, module.id), module_reference_count(db, module.id))


@router.delete("/modules/{module_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_module(workspace_id: str, project_id: str, module_id: str, db: DbSession, actor_email: ActorEmail) -> Response:
    require_workspace_owner(db, workspace_id, actor_email)
    module = get_module_or_404(db, workspace_id, project_id, module_id)
    if child_modules(db, module.id):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Module has children; archive or move children first")
    references = module_reference_count(db, module.id)
    if references:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Referenced modules can only be archived")
    before = {**module_snapshot(module), "mapping_rule_count": len(rules_for_module(db, module_id)), "reference_count": references}
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
        summary=f"Deleted module {before['path_label']}",
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
        summary=f"Added {rule.rule_type} mapping to {module.path_label}",
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
