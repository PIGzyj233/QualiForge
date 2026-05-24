from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from pathlib import Path
from typing import Annotated, Any

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, Request, UploadFile, status
from pydantic import BaseModel, Field
from sqlalchemy import JSON, DateTime, ForeignKey, String, select
from sqlalchemy.orm import Mapped, Session, mapped_column

from app.cases.domain import CaseRevision, TestCase, TestCaseLifecycle
from app.cases.imports import safe_filename
from app.platform.database import Base
from app.workspace.routes import ActorEmail, audit, get_project_or_404, get_workspace_or_404, new_id, now_utc

__test__ = False


class TestPlanType(StrEnum):
    release = "release"
    regression = "regression"
    smoke = "smoke"
    feature = "feature"
    custom = "custom"


class TestPlanStatus(StrEnum):
    draft = "draft"
    in_progress = "in_progress"
    completed = "completed"
    archived = "archived"


class PlanItemSource(StrEnum):
    formal_case = "formal_case"
    ai_temp = "ai_temp"
    manual = "manual"


class PlanItemStatus(StrEnum):
    not_run = "not_run"
    passed = "passed"
    failed = "failed"
    blocked = "blocked"
    skipped = "skipped"


class TestPlan(Base):
    __tablename__ = "test_plans"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    workspace_id: Mapped[str] = mapped_column(ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False, index=True)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    plan_type: Mapped[str] = mapped_column(String(40), default=TestPlanType.release.value, nullable=False)
    status: Mapped[str] = mapped_column(String(40), default=TestPlanStatus.draft.value, nullable=False, index=True)
    scope_summary: Mapped[str] = mapped_column(String(700), default="", nullable=False)
    version_ref: Mapped[str] = mapped_column(String(160), default="", nullable=False)
    owner_email: Mapped[str] = mapped_column(String(254), nullable=False)
    final_conclusion: Mapped[str] = mapped_column(String(700), default="", nullable=False)
    created_by: Mapped[str] = mapped_column(String(254), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc, nullable=False, index=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc, onupdate=now_utc, nullable=False)


class PlanItem(Base):
    __tablename__ = "plan_items"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    workspace_id: Mapped[str] = mapped_column(ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False, index=True)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True)
    plan_id: Mapped[str] = mapped_column(ForeignKey("test_plans.id", ondelete="CASCADE"), nullable=False, index=True)
    source_type: Mapped[str] = mapped_column(String(40), nullable=False)
    source_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    title: Mapped[str] = mapped_column(String(220), nullable=False)
    snapshot: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    rationale: Mapped[str] = mapped_column(String(700), default="", nullable=False)
    status: Mapped[str] = mapped_column(String(40), default=PlanItemStatus.not_run.value, nullable=False, index=True)
    assignee_email: Mapped[str] = mapped_column(String(254), default="", nullable=False, index=True)
    actual_result: Mapped[str] = mapped_column(String(1000), default="", nullable=False)
    failure_reason: Mapped[str] = mapped_column(String(700), default="", nullable=False)
    defect_links: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    evidence: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list, nullable=False)
    executed_by: Mapped[str | None] = mapped_column(String(254), nullable=True)
    executed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_by: Mapped[str] = mapped_column(String(254), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc, nullable=False, index=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc, onupdate=now_utc, nullable=False)


class TestPlanCreate(BaseModel):
    name: str = Field(min_length=1, max_length=160)
    plan_type: TestPlanType = TestPlanType.release
    scope_summary: str = Field(default="", max_length=700)
    version_ref: str = Field(default="", max_length=160)
    owner_email: str | None = Field(default=None, max_length=254)


class PlanItemCreate(BaseModel):
    source_type: PlanItemSource
    source_id: str | None = Field(default=None, max_length=64)
    title: str = Field(default="", max_length=220)
    snapshot: dict[str, Any] = Field(default_factory=dict)
    rationale: str = Field(default="", max_length=700)


class PlanItemExecutionUpdate(BaseModel):
    status: PlanItemStatus
    assignee_email: str | None = Field(default=None, max_length=254)
    actual_result: str = Field(default="", max_length=1000)
    failure_reason: str = Field(default="", max_length=700)
    defect_links: list[str] = Field(default_factory=list, max_length=10)


class TestPlanResponse(BaseModel):
    id: str
    workspace_id: str
    project_id: str
    name: str
    plan_type: str
    status: str
    scope_summary: str
    version_ref: str
    owner_email: str
    final_conclusion: str
    created_by: str
    created_at: datetime
    updated_at: datetime


class PlanItemResponse(BaseModel):
    id: str
    workspace_id: str
    project_id: str
    plan_id: str
    source_type: str
    source_id: str | None
    title: str
    snapshot: dict[str, Any]
    rationale: str
    status: str
    assignee_email: str
    actual_result: str
    failure_reason: str
    defect_links: list[str]
    evidence: list[dict[str, Any]]
    executed_by: str | None
    executed_at: datetime | None
    created_by: str
    created_at: datetime
    updated_at: datetime


def get_db(request: Request):
    yield from request.app.state.database.session()


DbSession = Annotated[Session, Depends(get_db)]

router = APIRouter(prefix="/api/workspaces/{workspace_id}/projects/{project_id}", tags=["test-plans"])


def formal_case_snapshot(db: Session, test_case: TestCase) -> dict[str, Any]:
    if test_case.lifecycle_status != TestCaseLifecycle.active.value or not test_case.current_revision_id:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Only active formal cases can be added to a plan")
    revision = db.get(CaseRevision, test_case.current_revision_id)
    if revision is None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Active formal case has no current revision")
    return {
        **revision.content_snapshot,
        "id": test_case.id,
        "revision_id": revision.id,
        "revision": revision.revision_number,
        "module_path_label": revision.module_path_label,
        "lifecycle_status": test_case.lifecycle_status,
    }


def plan_to_response(plan: TestPlan) -> TestPlanResponse:
    return TestPlanResponse(
        id=plan.id,
        workspace_id=plan.workspace_id,
        project_id=plan.project_id,
        name=plan.name,
        plan_type=plan.plan_type,
        status=plan.status,
        scope_summary=plan.scope_summary,
        version_ref=plan.version_ref,
        owner_email=plan.owner_email,
        final_conclusion=plan.final_conclusion,
        created_by=plan.created_by,
        created_at=plan.created_at,
        updated_at=plan.updated_at,
    )


def plan_item_to_response(item: PlanItem) -> PlanItemResponse:
    return PlanItemResponse(
        id=item.id,
        workspace_id=item.workspace_id,
        project_id=item.project_id,
        plan_id=item.plan_id,
        source_type=item.source_type,
        source_id=item.source_id,
        title=item.title,
        snapshot=item.snapshot,
        rationale=item.rationale,
        status=item.status,
        assignee_email=item.assignee_email,
        actual_result=item.actual_result,
        failure_reason=item.failure_reason,
        defect_links=item.defect_links,
        evidence=item.evidence,
        executed_by=item.executed_by,
        executed_at=item.executed_at,
        created_by=item.created_by,
        created_at=item.created_at,
        updated_at=item.updated_at,
    )


def get_plan_or_404(db: Session, workspace_id: str, project_id: str, plan_id: str) -> TestPlan:
    plan = db.scalar(
        select(TestPlan).where(
            TestPlan.id == plan_id,
            TestPlan.workspace_id == workspace_id,
            TestPlan.project_id == project_id,
        )
    )
    if plan is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Test plan not found")
    return plan


def get_plan_item_or_404(db: Session, workspace_id: str, project_id: str, plan_id: str, item_id: str) -> PlanItem:
    item = db.scalar(
        select(PlanItem).where(
            PlanItem.id == item_id,
            PlanItem.workspace_id == workspace_id,
            PlanItem.project_id == project_id,
            PlanItem.plan_id == plan_id,
        )
    )
    if item is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Plan item not found")
    return item


def normalize_links(links: list[str]) -> list[str]:
    return list(dict.fromkeys(link.strip() for link in links if link.strip()))[:10]


def get_or_create_release_plan(
    db: Session,
    *,
    workspace_id: str,
    project_id: str,
    actor_email: str,
    version_ref: str,
    scope_summary: str,
) -> TestPlan:
    plan = db.scalar(
        select(TestPlan).where(
            TestPlan.workspace_id == workspace_id,
            TestPlan.project_id == project_id,
            TestPlan.version_ref == version_ref,
            TestPlan.plan_type == TestPlanType.release.value,
            TestPlan.status == TestPlanStatus.draft.value,
        )
    )
    if plan is not None:
        return plan

    plan = TestPlan(
        workspace_id=workspace_id,
        project_id=project_id,
        name=f"Release plan {version_ref or now_utc().date().isoformat()}",
        plan_type=TestPlanType.release.value,
        scope_summary=scope_summary,
        version_ref=version_ref,
        owner_email=actor_email,
        created_by=actor_email,
    )
    db.add(plan)
    db.flush()
    return plan


def add_plan_item(
    db: Session,
    *,
    plan: TestPlan,
    source_type: PlanItemSource,
    source_id: str | None,
    title: str,
    snapshot: dict[str, Any],
    rationale: str,
    actor_email: str,
) -> PlanItem:
    item = PlanItem(
        workspace_id=plan.workspace_id,
        project_id=plan.project_id,
        plan_id=plan.id,
        source_type=source_type.value,
        source_id=source_id,
        title=title,
        snapshot=snapshot,
        rationale=rationale,
        created_by=actor_email,
    )
    db.add(item)
    db.flush()
    return item


@router.get("/plans", response_model=list[TestPlanResponse])
def list_test_plans(workspace_id: str, project_id: str, db: DbSession) -> list[TestPlanResponse]:
    get_workspace_or_404(db, workspace_id)
    get_project_or_404(db, workspace_id, project_id)
    plans = db.scalars(
        select(TestPlan)
        .where(TestPlan.workspace_id == workspace_id, TestPlan.project_id == project_id)
        .order_by(TestPlan.created_at.desc(), TestPlan.id.desc())
    ).all()
    return [plan_to_response(plan) for plan in plans]


@router.post("/plans", response_model=TestPlanResponse, status_code=status.HTTP_201_CREATED)
def create_test_plan(
    workspace_id: str,
    project_id: str,
    payload: TestPlanCreate,
    db: DbSession,
    actor_email: ActorEmail,
) -> TestPlanResponse:
    get_workspace_or_404(db, workspace_id)
    get_project_or_404(db, workspace_id, project_id)
    plan = TestPlan(
        workspace_id=workspace_id,
        project_id=project_id,
        name=payload.name,
        plan_type=payload.plan_type.value,
        scope_summary=payload.scope_summary,
        version_ref=payload.version_ref,
        owner_email=payload.owner_email or actor_email,
        created_by=actor_email,
    )
    db.add(plan)
    db.flush()
    audit(
        db,
        workspace_id=workspace_id,
        actor_email=actor_email,
        action="test_plan.created",
        entity_type="TestPlan",
        entity_id=plan.id,
        summary=f"Created {plan.plan_type} test plan {plan.name}",
        after={"project_id": project_id, "version_ref": plan.version_ref, "scope_summary": plan.scope_summary},
    )
    db.commit()
    db.refresh(plan)
    return plan_to_response(plan)


@router.get("/plans/{plan_id}/items", response_model=list[PlanItemResponse])
def list_plan_items(
    workspace_id: str,
    project_id: str,
    plan_id: str,
    db: DbSession,
    status_filter: Annotated[list[PlanItemStatus] | None, Query(alias="status")] = None,
    assignee_email: Annotated[str | None, Query(max_length=254)] = None,
) -> list[PlanItemResponse]:
    get_plan_or_404(db, workspace_id, project_id, plan_id)
    filters = [PlanItem.workspace_id == workspace_id, PlanItem.project_id == project_id, PlanItem.plan_id == plan_id]
    if status_filter:
        filters.append(PlanItem.status.in_([item.value for item in status_filter]))
    if assignee_email:
        filters.append(PlanItem.assignee_email == assignee_email)
    items = db.scalars(
        select(PlanItem)
        .where(*filters)
        .order_by(PlanItem.created_at, PlanItem.id)
    ).all()
    return [plan_item_to_response(item) for item in items]


@router.post("/plans/{plan_id}/items", response_model=PlanItemResponse, status_code=status.HTTP_201_CREATED)
def create_plan_item(
    workspace_id: str,
    project_id: str,
    plan_id: str,
    payload: PlanItemCreate,
    db: DbSession,
    actor_email: ActorEmail,
) -> PlanItemResponse:
    plan = get_plan_or_404(db, workspace_id, project_id, plan_id)
    snapshot = payload.snapshot
    title = payload.title
    if payload.source_type == PlanItemSource.formal_case:
        if not payload.source_id:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="source_id required for formal case")
        test_case = db.get(TestCase, payload.source_id)
        if test_case is None or test_case.workspace_id != workspace_id or test_case.project_id != project_id:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Test case not found")
        if test_case.lifecycle_status != TestCaseLifecycle.active.value or not test_case.current_revision_id:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Only active formal cases can be added to a plan")
        snapshot = formal_case_snapshot(db, test_case)
        title = title or str(snapshot.get("title") or "Formal case")
    item = add_plan_item(
        db,
        plan=plan,
        source_type=payload.source_type,
        source_id=payload.source_id,
        title=title or "Manual plan item",
        snapshot=snapshot,
        rationale=payload.rationale,
        actor_email=actor_email,
    )
    plan.updated_at = now_utc()
    audit(
        db,
        workspace_id=workspace_id,
        actor_email=actor_email,
        action="plan_item.added",
        entity_type="PlanItem",
        entity_id=item.id,
        summary=f"Added {item.source_type} item to {plan.name}",
        after={"plan_id": plan.id, "source_type": item.source_type, "source_id": item.source_id, "title": item.title},
    )
    db.commit()
    db.refresh(item)
    return plan_item_to_response(item)


@router.patch("/plans/{plan_id}/items/{item_id}/execution", response_model=PlanItemResponse)
def update_plan_item_execution(
    workspace_id: str,
    project_id: str,
    plan_id: str,
    item_id: str,
    payload: PlanItemExecutionUpdate,
    db: DbSession,
    actor_email: ActorEmail,
) -> PlanItemResponse:
    plan = get_plan_or_404(db, workspace_id, project_id, plan_id)
    item = get_plan_item_or_404(db, workspace_id, project_id, plan_id, item_id)
    before = {
        "status": item.status,
        "assignee_email": item.assignee_email,
        "actual_result": item.actual_result,
        "failure_reason": item.failure_reason,
        "defect_links": item.defect_links,
        "executed_by": item.executed_by,
        "executed_at": item.executed_at.isoformat() if item.executed_at else None,
    }

    item.status = payload.status.value
    item.assignee_email = payload.assignee_email or ""
    item.actual_result = payload.actual_result
    item.failure_reason = payload.failure_reason
    item.defect_links = normalize_links(payload.defect_links)
    if payload.status == PlanItemStatus.not_run:
        item.executed_by = None
        item.executed_at = None
    else:
        item.executed_by = actor_email
        item.executed_at = now_utc()
        if plan.status == TestPlanStatus.draft.value:
            plan.status = TestPlanStatus.in_progress.value
    item.updated_at = now_utc()
    plan.updated_at = now_utc()
    audit(
        db,
        workspace_id=workspace_id,
        actor_email=actor_email,
        action="plan_item.execution_updated",
        entity_type="PlanItem",
        entity_id=item.id,
        summary=f"Updated execution result for {item.title}",
        before=before,
        after={
            "plan_id": plan.id,
            "status": item.status,
            "assignee_email": item.assignee_email,
            "actual_result": item.actual_result,
            "failure_reason": item.failure_reason,
            "defect_links": item.defect_links,
            "executed_by": item.executed_by,
            "executed_at": item.executed_at.isoformat() if item.executed_at else None,
        },
    )
    db.commit()
    db.refresh(item)
    return plan_item_to_response(item)


@router.post("/plans/{plan_id}/items/{item_id}/evidence", response_model=PlanItemResponse, status_code=status.HTTP_201_CREATED)
async def upload_plan_item_evidence(
    workspace_id: str,
    project_id: str,
    plan_id: str,
    item_id: str,
    db: DbSession,
    request: Request,
    actor_email: ActorEmail,
    note: Annotated[str, Form(max_length=500)] = "",
    file: UploadFile = File(...),
) -> PlanItemResponse:
    plan = get_plan_or_404(db, workspace_id, project_id, plan_id)
    item = get_plan_item_or_404(db, workspace_id, project_id, plan_id, item_id)
    content = await file.read()
    if not content:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Evidence file is empty")

    evidence_id = new_id()
    filename = safe_filename(file.filename or "evidence.bin")
    storage_dir = (
        Path(request.app.state.settings.evidence_storage_root).expanduser()
        / workspace_id[:12]
        / project_id[:12]
        / plan_id
        / item_id
    )
    storage_dir.mkdir(parents=True, exist_ok=True)
    storage_path = storage_dir / f"{evidence_id}-{filename}"
    storage_path.write_bytes(content)
    uploaded_at = now_utc()
    record = {
        "id": evidence_id,
        "file_name": filename,
        "content_type": file.content_type or "application/octet-stream",
        "size_bytes": len(content),
        "storage_path": str(storage_path.resolve(strict=False)),
        "note": note,
        "uploaded_by": actor_email,
        "uploaded_at": uploaded_at.isoformat(),
    }
    item.evidence = [*item.evidence, record]
    item.updated_at = uploaded_at
    plan.updated_at = uploaded_at
    audit(
        db,
        workspace_id=workspace_id,
        actor_email=actor_email,
        action="plan_item.evidence_uploaded",
        entity_type="PlanItem",
        entity_id=item.id,
        summary=f"Uploaded execution evidence for {item.title}",
        after={"plan_id": plan.id, "evidence_id": evidence_id, "file_name": filename, "size_bytes": len(content)},
    )
    db.commit()
    db.refresh(item)
    return plan_item_to_response(item)
