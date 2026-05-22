from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from pydantic import BaseModel, Field
from sqlalchemy import JSON, DateTime, ForeignKey, String, select
from sqlalchemy.orm import Mapped, Session, mapped_column

from app.case_imports import TestCase, TestCaseStatus
from app.database import Base
from app.workspaces import ActorEmail, audit, get_project_or_404, get_workspace_or_404, new_id, now_utc


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
    todo = "todo"
    in_progress = "in_progress"
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
    status: Mapped[str] = mapped_column(String(40), default=PlanItemStatus.todo.value, nullable=False, index=True)
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
    created_by: str
    created_at: datetime
    updated_at: datetime


def get_db(request: Request):
    yield from request.app.state.database.session()


DbSession = Annotated[Session, Depends(get_db)]

router = APIRouter(prefix="/api/workspaces/{workspace_id}/projects/{project_id}", tags=["test-plans"])


def test_case_snapshot(test_case: TestCase) -> dict[str, Any]:
    return {
        "id": test_case.id,
        "module_id": test_case.module_id,
        "title": test_case.title,
        "steps": test_case.steps,
        "expected_result": test_case.expected_result,
        "priority": test_case.priority,
        "risk": test_case.risk,
        "tags": test_case.tags,
        "custom_fields": test_case.custom_fields,
        "status": test_case.status,
        "revision": test_case.current_revision_number,
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
def list_plan_items(workspace_id: str, project_id: str, plan_id: str, db: DbSession) -> list[PlanItemResponse]:
    get_plan_or_404(db, workspace_id, project_id, plan_id)
    items = db.scalars(
        select(PlanItem)
        .where(PlanItem.workspace_id == workspace_id, PlanItem.project_id == project_id, PlanItem.plan_id == plan_id)
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
        if test_case.status != TestCaseStatus.approved.value:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Only approved formal cases can be added to a plan")
        snapshot = test_case_snapshot(test_case)
        title = title or test_case.title
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
