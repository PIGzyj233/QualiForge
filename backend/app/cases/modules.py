from __future__ import annotations

import re
from datetime import datetime
from enum import StrEnum
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, status
from pydantic import BaseModel, Field
from sqlalchemy import JSON, Boolean, DateTime, ForeignKey, Integer, String, UniqueConstraint, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Mapped, Session, mapped_column

from app.cases.domain import CaseDraft, CaseRevision, TestCase
from app.git.models import GitRepository
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
    command = "command"
    library_api = "library_api"
    symbol = "symbol"
    package = "package"
    build_target = "build_target"
    config_key = "config_key"
    database_migration = "database_migration"
    protocol = "protocol"
    transport = "transport"
    format = "format"
    codec = "codec"
    media_pipeline = "media_pipeline"
    asset_fixture = "asset_fixture"
    keyword = "keyword"


class MappingRelationship(StrEnum):
    primary = "primary"
    related = "related"
    dependency = "dependency"
    evidence = "evidence"


class MappingRuleStatus(StrEnum):
    active = "active"
    stale = "stale"
    archived = "archived"


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
    keywords: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
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
    repository_id: Mapped[str | None] = mapped_column(ForeignKey("git_repositories.id", ondelete="SET NULL"), nullable=True, index=True)
    rule_type: Mapped[str] = mapped_column(String(40), nullable=False)
    pattern: Mapped[str] = mapped_column(String(500), nullable=False)
    relationship: Mapped[str] = mapped_column(String(32), default=MappingRelationship.primary.value, nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(32), default=MappingRuleStatus.active.value, nullable=False, index=True)
    source: Mapped[str] = mapped_column(String(40), nullable=False)
    description: Mapped[str] = mapped_column(String(500), default="", nullable=False)
    ai_confidence: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    confidence: Mapped[int] = mapped_column(Integer, default=100, nullable=False)
    evidence_refs: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list, nullable=False)
    accepted_from_output_id: Mapped[str | None] = mapped_column(String(32), nullable=True)
    verified_by: Mapped[str] = mapped_column(String(254), default="", nullable=False)
    verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    stale_reason: Mapped[str] = mapped_column(String(500), default="", nullable=False)
    conditions: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    case_sensitive: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
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
    keywords: list[str] = Field(default_factory=list)
    sort_order: int = 0


class ModuleUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    slug: str | None = Field(default=None, min_length=1, max_length=80)
    code: str | None = Field(default=None, max_length=48)
    parent_id: str | None = None
    description: str | None = Field(default=None, max_length=500)
    owner: str | None = Field(default=None, max_length=120)
    keywords: list[str] | None = None
    sort_order: int | None = None
    status: ModuleStatus | None = None


class MappingRuleCreate(BaseModel):
    repository_id: str | None = Field(default=None, max_length=32)
    rule_type: MappingRuleType
    pattern: str = Field(min_length=1, max_length=500)
    relationship: MappingRelationship = MappingRelationship.primary
    status: MappingRuleStatus = MappingRuleStatus.active
    source: MappingSource = MappingSource.manual
    description: str = Field(default="", max_length=500)
    ai_confidence: int = Field(default=0, ge=0, le=100)
    confidence: int = Field(default=100, ge=0, le=100)
    evidence_refs: list[dict[str, Any]] = Field(default_factory=list)
    accepted_from_output_id: str | None = Field(default=None, max_length=32)
    verified_by: str = Field(default="", max_length=254)
    verified_at: datetime | None = None
    stale_reason: str = Field(default="", max_length=500)
    conditions: dict[str, Any] = Field(default_factory=dict)
    case_sensitive: bool | None = None


class MappingRuleUpdate(BaseModel):
    repository_id: str | None = Field(default=None, max_length=32)
    rule_type: MappingRuleType | None = None
    pattern: str | None = Field(default=None, min_length=1, max_length=500)
    relationship: MappingRelationship | None = None
    status: MappingRuleStatus | None = None
    source: MappingSource | None = None
    description: str | None = Field(default=None, max_length=500)
    ai_confidence: int | None = Field(default=None, ge=0, le=100)
    confidence: int | None = Field(default=None, ge=0, le=100)
    evidence_refs: list[dict[str, Any]] | None = None
    accepted_from_output_id: str | None = Field(default=None, max_length=32)
    verified_by: str | None = Field(default=None, max_length=254)
    verified_at: datetime | None = None
    stale_reason: str | None = Field(default=None, max_length=500)
    conditions: dict[str, Any] | None = None
    case_sensitive: bool | None = None


class MappingRuleResponse(BaseModel):
    id: str
    workspace_id: str
    project_id: str
    module_id: str
    repository_id: str | None
    rule_type: str
    pattern: str
    relationship: str
    status: str
    source: str
    description: str
    ai_confidence: int
    confidence: int
    evidence_refs: list[dict[str, Any]]
    accepted_from_output_id: str | None
    verified_by: str
    verified_at: datetime | None
    stale_reason: str
    conditions: dict[str, Any]
    case_sensitive: bool | None
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
    keywords: list[str]
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


def normalize_module_code(value: str) -> str:
    return value.strip()


def clean_keywords(values: list[str] | None) -> list[str]:
    cleaned: list[str] = []
    seen: set[str] = set()
    for raw in values or []:
        keyword = raw.strip()
        key = keyword.lower()
        if not keyword or key in seen:
            continue
        cleaned.append(keyword[:80])
        seen.add(key)
        if len(cleaned) >= 30:
            break
    return cleaned


def assert_repository_scope(db: Session, workspace_id: str, project_id: str, repository_id: str | None) -> None:
    if repository_id is None:
        return
    repository = db.scalar(
        select(GitRepository).where(
            GitRepository.id == repository_id,
            GitRepository.workspace_id == workspace_id,
            GitRepository.project_id == project_id,
        )
    )
    if repository is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Repository not found")


def serialize_rule(rule: ModuleMappingRule) -> MappingRuleResponse:
    return MappingRuleResponse(
        id=rule.id,
        workspace_id=rule.workspace_id,
        project_id=rule.project_id,
        module_id=rule.module_id,
        repository_id=rule.repository_id,
        rule_type=rule.rule_type,
        pattern=rule.pattern,
        relationship=rule.relationship,
        status=rule.status,
        source=rule.source,
        description=rule.description,
        ai_confidence=rule.ai_confidence,
        confidence=rule.confidence,
        evidence_refs=rule.evidence_refs or [],
        accepted_from_output_id=rule.accepted_from_output_id,
        verified_by=rule.verified_by,
        verified_at=rule.verified_at,
        stale_reason=rule.stale_reason,
        conditions=rule.conditions or {},
        case_sensitive=rule.case_sensitive,
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
        keywords=module.keywords or [],
        reference_count=reference_count,
        mapping_rules=[serialize_rule(rule) for rule in rules],
        created_at=module.created_at,
        updated_at=module.updated_at,
    )


def module_snapshot(module: ProjectModule) -> dict[str, Any]:
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
        "keywords": module.keywords or [],
        "project_id": module.project_id,
    }


def rule_snapshot(rule: ModuleMappingRule) -> dict[str, str | int | bool | None]:
    return {
        "module_id": rule.module_id,
        "repository_id": rule.repository_id,
        "rule_type": rule.rule_type,
        "pattern": rule.pattern,
        "relationship": rule.relationship,
        "status": rule.status,
        "source": rule.source,
        "description": rule.description,
        "ai_confidence": rule.ai_confidence,
        "confidence": rule.confidence,
        "evidence_count": len(rule.evidence_refs or []),
        "accepted_from_output_id": rule.accepted_from_output_id,
        "verified_by": rule.verified_by,
        "verified_at": rule.verified_at.isoformat() if rule.verified_at else None,
        "stale_reason": rule.stale_reason,
        "condition_count": len(rule.conditions or {}),
        "case_sensitive": rule.case_sensitive,
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


def apply_rule_status_filter(statement, status_filter: Literal["active", "stale", "archived", "all"]):
    if status_filter == "all":
        return statement
    return statement.where(ModuleMappingRule.status == status_filter)


def rules_for_module(
    db: Session,
    module_id: str,
    status_filter: Literal["active", "stale", "archived", "all"] = "active",
) -> list[ModuleMappingRule]:
    statement = (
        select(ModuleMappingRule)
        .where(ModuleMappingRule.module_id == module_id)
        .order_by(ModuleMappingRule.rule_type, ModuleMappingRule.pattern)
    )
    statement = apply_rule_status_filter(statement, status_filter)
    return list(
        db.scalars(
            statement
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


def assert_unique_code(db: Session, module: ProjectModule | None, workspace_id: str, project_id: str, code: str) -> None:
    normalized = normalize_module_code(code)
    if not normalized:
        return
    statement = select(ProjectModule).where(
        ProjectModule.workspace_id == workspace_id,
        ProjectModule.project_id == project_id,
        ProjectModule.code == normalized,
    )
    existing = db.scalar(statement)
    if existing is not None and (module is None or existing.id != module.id):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Module code already exists in this project")


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
    mapping_rule_status: Literal["active", "stale", "archived", "all"] = Query(default="active"),
) -> list[ModuleResponse]:
    get_workspace_or_404(db, workspace_id)
    get_project_or_404(db, workspace_id, project_id)
    statement = select(ProjectModule).where(ProjectModule.workspace_id == workspace_id, ProjectModule.project_id == project_id)
    if not include_archived_modules:
        statement = statement.where(ProjectModule.status == ModuleStatus.active.value)
    modules = db.scalars(statement.order_by(ProjectModule.path)).all()
    return [serialize_module(module, rules_for_module(db, module.id, mapping_rule_status), module_reference_count(db, module.id)) for module in modules]


@router.get("/modules/tree", response_model=list[ModuleTreeNode])
def list_module_tree(
    workspace_id: str,
    project_id: str,
    db: DbSession,
    include_archived_modules: bool = Query(default=False),
    mapping_rule_status: Literal["active", "stale", "archived", "all"] = Query(default="active"),
) -> list[ModuleTreeNode]:
    modules = list_modules(workspace_id, project_id, db, include_archived_modules, mapping_rule_status)
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
    repository_id: str | None = Query(default=None),
    rule_type: MappingRuleType | None = Query(default=None),
    relationship: MappingRelationship | None = Query(default=None),
    status_filter: Literal["active", "stale", "archived", "all"] = Query(default="active", alias="status"),
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
    if repository_id:
        assert_repository_scope(db, workspace_id, project_id, repository_id)
        statement = statement.where(ModuleMappingRule.repository_id == repository_id)
    if rule_type:
        statement = statement.where(ModuleMappingRule.rule_type == rule_type.value)
    if relationship:
        statement = statement.where(ModuleMappingRule.relationship == relationship.value)
    statement = apply_rule_status_filter(statement, status_filter)
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
    code = normalize_module_code(payload.code or payload.key)
    assert_unique_slug(db, None, workspace_id, project_id, parent.id if parent else None, slug)
    assert_unique_code(db, None, workspace_id, project_id, code)
    module = ProjectModule(
        workspace_id=workspace_id,
        project_id=project_id,
        parent_id=parent.id if parent else None,
        name=payload.name,
        slug=slug,
        code=code,
        path=slug,
        path_label=payload.name,
        depth=0,
        sort_order=payload.sort_order,
        description=payload.description,
        owner=payload.owner,
        keywords=clean_keywords(payload.keywords),
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
        module.code = normalize_module_code(payload.code)
    if payload.description is not None:
        module.description = payload.description
    if payload.owner is not None:
        module.owner = payload.owner
    if payload.keywords is not None:
        module.keywords = clean_keywords(payload.keywords)
    if payload.sort_order is not None:
        module.sort_order = payload.sort_order
    if payload.status is not None:
        targets = descendant_modules(db, module, include_self=True) if payload.status == ModuleStatus.archived else [module]
        for target in targets:
            target.status = payload.status.value
            target.updated_at = now_utc()

    assert_unique_slug(db, module, workspace_id, project_id, module.parent_id, module.slug)
    assert_unique_code(db, module, workspace_id, project_id, module.code)
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
    module_rules = rules_for_module(db, module_id, "all")
    before = {**module_snapshot(module), "mapping_rule_count": len(module_rules), "reference_count": references}
    for rule in module_rules:
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
    assert_repository_scope(db, workspace_id, project_id, payload.repository_id)
    rule = ModuleMappingRule(
        workspace_id=workspace_id,
        project_id=project_id,
        module_id=module.id,
        repository_id=payload.repository_id,
        rule_type=payload.rule_type.value,
        pattern=payload.pattern,
        relationship=payload.relationship.value,
        status=payload.status.value,
        source=payload.source.value,
        description=payload.description,
        ai_confidence=payload.ai_confidence,
        confidence=payload.confidence,
        evidence_refs=payload.evidence_refs,
        accepted_from_output_id=payload.accepted_from_output_id,
        verified_by=payload.verified_by or actor_email,
        verified_at=payload.verified_at or now_utc(),
        stale_reason=payload.stale_reason,
        conditions=payload.conditions,
        case_sensitive=payload.case_sensitive,
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
    if "repository_id" in update_data:
        assert_repository_scope(db, workspace_id, project_id, update_data["repository_id"])
    for field, value in update_data.items():
        setattr(rule, field, value.value if isinstance(value, StrEnum) else value)
    if "verified_by" not in update_data:
        rule.verified_by = actor_email
    if "verified_at" not in update_data:
        rule.verified_at = now_utc()
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
