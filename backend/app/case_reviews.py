from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from pydantic import BaseModel, Field
from sqlalchemy import JSON, Boolean, DateTime, ForeignKey, Integer, String, select
from sqlalchemy.orm import Mapped, Session, mapped_column

from app.case_imports import TestCase, TestCaseResponse, TestCaseStatus, test_case_to_response
from app.database import Base
from app.modules import get_module_or_404
from app.workspaces import ActorEmail, audit, get_project_or_404, get_workspace_or_404, new_id, now_utc, require_workspace_owner


class ReviewAction(StrEnum):
    submitted = "submitted"
    approved = "approved"
    rejected = "rejected"
    changes_requested = "changes_requested"
    commented = "commented"
    edited = "edited"


class WorkspaceReviewSettings(Base):
    __tablename__ = "workspace_review_settings"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    workspace_id: Mapped[str] = mapped_column(ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False, unique=True, index=True)
    allow_self_review: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    require_review_on_case_update: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    updated_by: Mapped[str] = mapped_column(String(254), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc, onupdate=now_utc, nullable=False)


class CaseRevision(Base):
    __tablename__ = "case_revisions"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    workspace_id: Mapped[str] = mapped_column(ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False, index=True)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True)
    test_case_id: Mapped[str] = mapped_column(ForeignKey("test_cases.id", ondelete="CASCADE"), nullable=False, index=True)
    revision_number: Mapped[int] = mapped_column(Integer, nullable=False)
    content_snapshot: Mapped[dict] = mapped_column(JSON, nullable=False)
    change_summary: Mapped[str] = mapped_column(String(500), default="", nullable=False)
    created_by: Mapped[str] = mapped_column(String(254), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc, nullable=False)


class CaseReview(Base):
    __tablename__ = "case_reviews"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    workspace_id: Mapped[str] = mapped_column(ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False, index=True)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True)
    test_case_id: Mapped[str] = mapped_column(ForeignKey("test_cases.id", ondelete="CASCADE"), nullable=False, index=True)
    revision_id: Mapped[str | None] = mapped_column(ForeignKey("case_revisions.id", ondelete="SET NULL"), nullable=True, index=True)
    actor_email: Mapped[str] = mapped_column(String(254), nullable=False)
    action: Mapped[str] = mapped_column(String(40), nullable=False)
    comment: Mapped[str] = mapped_column(String(1000), default="", nullable=False)
    before: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    after: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc, nullable=False)


class ReviewSettingsUpdate(BaseModel):
    allow_self_review: bool = False
    require_review_on_case_update: bool = True


class ReviewSettingsResponse(BaseModel):
    id: str
    workspace_id: str
    allow_self_review: bool
    require_review_on_case_update: bool
    updated_by: str
    created_at: datetime
    updated_at: datetime


class TestCaseCreate(BaseModel):
    module_id: str | None = None
    title: str = Field(min_length=1, max_length=300)
    steps: list[str] = Field(default_factory=list, max_length=100)
    expected_result: str = Field(default="", max_length=2000)
    priority: str = Field(default="P2", max_length=32)
    risk: str = Field(default="medium", max_length=80)
    tags: list[str] = Field(default_factory=list, max_length=50)
    custom_fields: dict[str, str] = Field(default_factory=dict)


class TestCaseUpdate(BaseModel):
    module_id: str | None = None
    title: str | None = Field(default=None, min_length=1, max_length=300)
    steps: list[str] | None = Field(default=None, max_length=100)
    expected_result: str | None = Field(default=None, max_length=2000)
    priority: str | None = Field(default=None, max_length=32)
    risk: str | None = Field(default=None, max_length=80)
    tags: list[str] | None = Field(default=None, max_length=50)
    custom_fields: dict[str, str] | None = None


class ReviewRequest(BaseModel):
    action: ReviewAction
    comment: str = Field(default="", max_length=1000)
    edits: TestCaseUpdate | None = None


class CaseRevisionResponse(BaseModel):
    id: str
    workspace_id: str
    project_id: str
    test_case_id: str
    revision_number: int
    content_snapshot: dict
    change_summary: str
    created_by: str
    created_at: datetime


class CaseReviewResponse(BaseModel):
    id: str
    workspace_id: str
    project_id: str
    test_case_id: str
    revision_id: str | None
    actor_email: str
    action: str
    comment: str
    before: dict | None
    after: dict | None
    created_at: datetime


def get_db(request: Request):
    yield from request.app.state.database.session()


DbSession = Annotated[Session, Depends(get_db)]

router = APIRouter(prefix="/api/workspaces/{workspace_id}", tags=["case-reviews"])


def settings_to_response(settings: WorkspaceReviewSettings) -> ReviewSettingsResponse:
    return ReviewSettingsResponse(
        id=settings.id,
        workspace_id=settings.workspace_id,
        allow_self_review=settings.allow_self_review,
        require_review_on_case_update=settings.require_review_on_case_update,
        updated_by=settings.updated_by,
        created_at=settings.created_at,
        updated_at=settings.updated_at,
    )


def revision_to_response(revision: CaseRevision) -> CaseRevisionResponse:
    return CaseRevisionResponse(
        id=revision.id,
        workspace_id=revision.workspace_id,
        project_id=revision.project_id,
        test_case_id=revision.test_case_id,
        revision_number=revision.revision_number,
        content_snapshot=revision.content_snapshot,
        change_summary=revision.change_summary,
        created_by=revision.created_by,
        created_at=revision.created_at,
    )


def review_to_response(review: CaseReview) -> CaseReviewResponse:
    return CaseReviewResponse(
        id=review.id,
        workspace_id=review.workspace_id,
        project_id=review.project_id,
        test_case_id=review.test_case_id,
        revision_id=review.revision_id,
        actor_email=review.actor_email,
        action=review.action,
        comment=review.comment,
        before=review.before,
        after=review.after,
        created_at=review.created_at,
    )


def get_or_create_review_settings(db: Session, workspace_id: str, actor_email: str = "system") -> WorkspaceReviewSettings:
    settings = db.scalar(select(WorkspaceReviewSettings).where(WorkspaceReviewSettings.workspace_id == workspace_id))
    if settings is not None:
        return settings
    settings = WorkspaceReviewSettings(workspace_id=workspace_id, updated_by=actor_email)
    db.add(settings)
    db.flush()
    return settings


def get_case_or_404(db: Session, workspace_id: str, project_id: str, case_id: str) -> TestCase:
    test_case = db.scalar(
        select(TestCase).where(
            TestCase.id == case_id,
            TestCase.workspace_id == workspace_id,
            TestCase.project_id == project_id,
        )
    )
    if test_case is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Test case not found")
    return test_case


def case_snapshot(test_case: TestCase) -> dict:
    return {
        "module_id": test_case.module_id,
        "title": test_case.title,
        "steps": test_case.steps,
        "expected_result": test_case.expected_result,
        "priority": test_case.priority,
        "risk": test_case.risk,
        "tags": test_case.tags,
        "custom_fields": test_case.custom_fields,
        "status": test_case.status,
        "submitted_by": test_case.submitted_by,
        "approved_by": test_case.approved_by,
        "current_revision_number": test_case.current_revision_number,
    }


def apply_case_update(db: Session, workspace_id: str, project_id: str, test_case: TestCase, payload: TestCaseUpdate) -> dict:
    update_data = payload.model_dump(exclude_unset=True)
    if "module_id" in update_data and update_data["module_id"]:
        get_module_or_404(db, workspace_id, project_id, update_data["module_id"])
    for field, value in update_data.items():
        if field in {"steps", "tags"} and value is not None:
            value = [item.strip() for item in value if item.strip()]
        setattr(test_case, field, value)
    test_case.updated_at = now_utc()
    return update_data


def create_revision(db: Session, test_case: TestCase, actor_email: str, change_summary: str) -> CaseRevision:
    revision = CaseRevision(
        workspace_id=test_case.workspace_id,
        project_id=test_case.project_id,
        test_case_id=test_case.id,
        revision_number=test_case.current_revision_number + 1,
        content_snapshot=case_snapshot(test_case),
        change_summary=change_summary,
        created_by=actor_email,
    )
    db.add(revision)
    db.flush()
    test_case.current_revision_number = revision.revision_number
    return revision


def record_case_review(
    db: Session,
    *,
    test_case: TestCase,
    actor_email: str,
    action: ReviewAction,
    comment: str = "",
    revision: CaseRevision | None = None,
    before: dict | None = None,
    after: dict | None = None,
) -> CaseReview:
    review = CaseReview(
        workspace_id=test_case.workspace_id,
        project_id=test_case.project_id,
        test_case_id=test_case.id,
        revision_id=revision.id if revision else None,
        actor_email=actor_email,
        action=action.value,
        comment=comment,
        before=before,
        after=after,
    )
    db.add(review)
    db.flush()
    return review


def ensure_not_self_review(settings: WorkspaceReviewSettings, test_case: TestCase, actor_email: str, action: ReviewAction) -> None:
    if action in {ReviewAction.commented, ReviewAction.submitted}:
        return
    if settings.allow_self_review:
        return
    if test_case.submitted_by and test_case.submitted_by == actor_email:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Submitter cannot review their own test case")


@router.get("/review-settings", response_model=ReviewSettingsResponse)
def get_review_settings(workspace_id: str, db: DbSession) -> ReviewSettingsResponse:
    get_workspace_or_404(db, workspace_id)
    settings = get_or_create_review_settings(db, workspace_id)
    db.commit()
    db.refresh(settings)
    return settings_to_response(settings)


@router.put("/review-settings", response_model=ReviewSettingsResponse)
def update_review_settings(
    workspace_id: str,
    payload: ReviewSettingsUpdate,
    db: DbSession,
    actor_email: ActorEmail,
) -> ReviewSettingsResponse:
    get_workspace_or_404(db, workspace_id)
    require_workspace_owner(db, workspace_id, actor_email)
    settings = get_or_create_review_settings(db, workspace_id, actor_email)
    before = settings_to_response(settings).model_dump(mode="json")
    settings.allow_self_review = payload.allow_self_review
    settings.require_review_on_case_update = payload.require_review_on_case_update
    settings.updated_by = actor_email
    settings.updated_at = now_utc()
    audit(
        db,
        workspace_id=workspace_id,
        actor_email=actor_email,
        action="review_settings.updated",
        entity_type="WorkspaceReviewSettings",
        entity_id=settings.id,
        summary="Updated case review settings",
        before=before,
        after=settings_to_response(settings).model_dump(mode="json"),
    )
    db.commit()
    db.refresh(settings)
    return settings_to_response(settings)


@router.post("/projects/{project_id}/test-cases", response_model=TestCaseResponse, status_code=status.HTTP_201_CREATED)
def create_test_case(
    workspace_id: str,
    project_id: str,
    payload: TestCaseCreate,
    db: DbSession,
    actor_email: ActorEmail,
) -> TestCaseResponse:
    get_workspace_or_404(db, workspace_id)
    get_project_or_404(db, workspace_id, project_id)
    if payload.module_id:
        get_module_or_404(db, workspace_id, project_id, payload.module_id)
    test_case = TestCase(
        workspace_id=workspace_id,
        project_id=project_id,
        module_id=payload.module_id,
        title=payload.title,
        steps=[step.strip() for step in payload.steps if step.strip()],
        expected_result=payload.expected_result,
        priority=payload.priority,
        risk=payload.risk,
        tags=[tag.strip() for tag in payload.tags if tag.strip()],
        custom_fields=payload.custom_fields,
        status=TestCaseStatus.draft.value,
        submitted_by=actor_email,
    )
    db.add(test_case)
    db.flush()
    audit(
        db,
        workspace_id=workspace_id,
        actor_email=actor_email,
        action="test_case.created",
        entity_type="TestCase",
        entity_id=test_case.id,
        summary=f"Created draft test case {test_case.title}",
        after=case_snapshot(test_case),
    )
    db.commit()
    db.refresh(test_case)
    return test_case_to_response(test_case)


@router.get("/projects/{project_id}/test-cases/{case_id}", response_model=TestCaseResponse)
def get_test_case(workspace_id: str, project_id: str, case_id: str, db: DbSession) -> TestCaseResponse:
    get_workspace_or_404(db, workspace_id)
    get_project_or_404(db, workspace_id, project_id)
    return test_case_to_response(get_case_or_404(db, workspace_id, project_id, case_id))


@router.patch("/projects/{project_id}/test-cases/{case_id}", response_model=TestCaseResponse)
def update_test_case(
    workspace_id: str,
    project_id: str,
    case_id: str,
    payload: TestCaseUpdate,
    db: DbSession,
    actor_email: ActorEmail,
) -> TestCaseResponse:
    settings = get_or_create_review_settings(db, workspace_id, actor_email)
    test_case = get_case_or_404(db, workspace_id, project_id, case_id)
    before = case_snapshot(test_case)
    was_approved = test_case.status == TestCaseStatus.approved.value
    changes = apply_case_update(db, workspace_id, project_id, test_case, payload)
    revision = None
    if was_approved:
        if settings.require_review_on_case_update:
            test_case.status = TestCaseStatus.pending_review.value
            test_case.approved_by = ""
        revision = create_revision(db, test_case, actor_email, "Updated approved test case")
    record_case_review(
        db,
        test_case=test_case,
        actor_email=actor_email,
        action=ReviewAction.edited,
        comment="Edited test case content",
        revision=revision,
        before=before,
        after={"changes": changes, "case": case_snapshot(test_case)},
    )
    audit(
        db,
        workspace_id=workspace_id,
        actor_email=actor_email,
        action="test_case.updated",
        entity_type="TestCase",
        entity_id=test_case.id,
        summary=f"Updated test case {test_case.title}",
        before=before,
        after=case_snapshot(test_case),
    )
    db.commit()
    db.refresh(test_case)
    return test_case_to_response(test_case)


@router.post("/projects/{project_id}/test-cases/{case_id}/submit-review", response_model=TestCaseResponse)
def submit_case_review(workspace_id: str, project_id: str, case_id: str, db: DbSession, actor_email: ActorEmail) -> TestCaseResponse:
    test_case = get_case_or_404(db, workspace_id, project_id, case_id)
    before = case_snapshot(test_case)
    test_case.status = TestCaseStatus.pending_review.value
    test_case.submitted_by = actor_email
    test_case.approved_by = ""
    test_case.updated_at = now_utc()
    record_case_review(
        db,
        test_case=test_case,
        actor_email=actor_email,
        action=ReviewAction.submitted,
        comment="Submitted test case for review",
        before=before,
        after=case_snapshot(test_case),
    )
    audit(
        db,
        workspace_id=workspace_id,
        actor_email=actor_email,
        action="test_case.review_submitted",
        entity_type="TestCase",
        entity_id=test_case.id,
        summary=f"Submitted test case {test_case.title} for review",
        before=before,
        after=case_snapshot(test_case),
    )
    db.commit()
    db.refresh(test_case)
    return test_case_to_response(test_case)


@router.post("/projects/{project_id}/test-cases/{case_id}/reviews", response_model=CaseReviewResponse, status_code=status.HTTP_201_CREATED)
def review_test_case(
    workspace_id: str,
    project_id: str,
    case_id: str,
    payload: ReviewRequest,
    db: DbSession,
    actor_email: ActorEmail,
) -> CaseReviewResponse:
    settings = get_or_create_review_settings(db, workspace_id, actor_email)
    test_case = get_case_or_404(db, workspace_id, project_id, case_id)
    ensure_not_self_review(settings, test_case, actor_email, payload.action)
    before = case_snapshot(test_case)
    revision = None

    if payload.action == ReviewAction.approved:
        test_case.status = TestCaseStatus.approved.value
        test_case.approved_by = actor_email
        test_case.updated_at = now_utc()
        revision = create_revision(db, test_case, actor_email, payload.comment or "Approved test case")
    elif payload.action == ReviewAction.rejected:
        test_case.status = TestCaseStatus.rejected.value
        test_case.approved_by = ""
        test_case.updated_at = now_utc()
    elif payload.action == ReviewAction.changes_requested:
        test_case.status = TestCaseStatus.draft.value
        test_case.approved_by = ""
        test_case.updated_at = now_utc()
    elif payload.action == ReviewAction.edited:
        if payload.edits is None:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Review edit requires edits")
        was_approved = test_case.status == TestCaseStatus.approved.value
        apply_case_update(db, workspace_id, project_id, test_case, payload.edits)
        if was_approved:
            if settings.require_review_on_case_update:
                test_case.status = TestCaseStatus.pending_review.value
                test_case.approved_by = ""
            revision = create_revision(db, test_case, actor_email, payload.comment or "Edited approved test case")
    elif payload.action == ReviewAction.commented:
        pass
    elif payload.action == ReviewAction.submitted:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Use submit-review endpoint to submit cases")

    review = record_case_review(
        db,
        test_case=test_case,
        actor_email=actor_email,
        action=payload.action,
        comment=payload.comment,
        revision=revision,
        before=before,
        after=case_snapshot(test_case),
    )
    audit(
        db,
        workspace_id=workspace_id,
        actor_email=actor_email,
        action=f"test_case_review.{payload.action.value}",
        entity_type="TestCase",
        entity_id=test_case.id,
        summary=f"{payload.action.value} review for {test_case.title}",
        before=before,
        after=case_snapshot(test_case),
    )
    db.commit()
    db.refresh(review)
    return review_to_response(review)


@router.get("/projects/{project_id}/test-cases/{case_id}/reviews", response_model=list[CaseReviewResponse])
def list_case_reviews(workspace_id: str, project_id: str, case_id: str, db: DbSession) -> list[CaseReviewResponse]:
    get_case_or_404(db, workspace_id, project_id, case_id)
    reviews = db.scalars(
        select(CaseReview)
        .where(CaseReview.workspace_id == workspace_id, CaseReview.project_id == project_id, CaseReview.test_case_id == case_id)
        .order_by(CaseReview.created_at.desc(), CaseReview.id.desc())
    ).all()
    return [review_to_response(review) for review in reviews]


@router.get("/projects/{project_id}/test-cases/{case_id}/revisions", response_model=list[CaseRevisionResponse])
def list_case_revisions(workspace_id: str, project_id: str, case_id: str, db: DbSession) -> list[CaseRevisionResponse]:
    get_case_or_404(db, workspace_id, project_id, case_id)
    revisions = db.scalars(
        select(CaseRevision)
        .where(CaseRevision.workspace_id == workspace_id, CaseRevision.project_id == project_id, CaseRevision.test_case_id == case_id)
        .order_by(CaseRevision.revision_number.desc(), CaseRevision.created_at.desc())
    ).all()
    return [revision_to_response(revision) for revision in revisions]


@router.delete("/projects/{project_id}/test-cases/{case_id}", status_code=status.HTTP_204_NO_CONTENT)
def archive_test_case(workspace_id: str, project_id: str, case_id: str, db: DbSession, actor_email: ActorEmail) -> Response:
    test_case = get_case_or_404(db, workspace_id, project_id, case_id)
    before = case_snapshot(test_case)
    test_case.status = TestCaseStatus.archived.value
    test_case.updated_at = now_utc()
    record_case_review(
        db,
        test_case=test_case,
        actor_email=actor_email,
        action=ReviewAction.edited,
        comment="Archived test case",
        before=before,
        after=case_snapshot(test_case),
    )
    audit(
        db,
        workspace_id=workspace_id,
        actor_email=actor_email,
        action="test_case.archived",
        entity_type="TestCase",
        entity_id=test_case.id,
        summary=f"Archived test case {test_case.title}",
        before=before,
        after=case_snapshot(test_case),
    )
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
