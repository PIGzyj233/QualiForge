from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, status
from pydantic import BaseModel, Field
from sqlalchemy import Boolean, DateTime, ForeignKey, JSON, String, select
from sqlalchemy.orm import Mapped, Session, mapped_column

from app.case_domain import (
    OPEN_REVIEW_STATUSES,
    CaseDraft,
    CaseDraftResponse,
    CaseDraftSource,
    CaseDraftStatus,
    CaseReviewCycle,
    CaseReviewCycleResponse,
    CaseReviewEvent,
    CaseReviewEventResponse,
    CaseRevision,
    CaseRevisionResponse,
    ReviewCycleStatus,
    ReviewEventAction,
    TestCase,
    TestCaseDetailResponse,
    TestCaseLifecycle,
    TestCaseResponse,
    cycle_to_response,
    draft_to_response,
    event_to_response,
    revision_to_response,
)
from app.database import Base
from app.modules import ProjectModule, descendant_module_ids, get_module_or_404
from app.workspaces import ActorEmail, audit, get_project_or_404, get_workspace_or_404, new_id, now_utc, require_workspace_owner


class ReviewAction(StrEnum):
    submitted = "submitted"
    approved = "approved"
    rejected = "rejected"
    changes_requested = "changes_requested"
    changes_addressed = "changes_addressed"
    commented = "commented"


class WorkspaceReviewSettings(Base):
    __tablename__ = "workspace_review_settings"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    workspace_id: Mapped[str] = mapped_column(ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False, unique=True, index=True)
    allow_self_review: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    require_review_on_case_update: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    allow_direct_revision_for_active_case: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    direct_revision_roles: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    updated_by: Mapped[str] = mapped_column(String(254), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc, onupdate=now_utc, nullable=False)


class ReviewSettingsUpdate(BaseModel):
    allow_self_review: bool = False
    require_review_on_case_update: bool = True
    allow_direct_revision_for_active_case: bool = False
    direct_revision_roles: list[str] = Field(default_factory=list, max_length=5)


class ReviewSettingsResponse(BaseModel):
    id: str
    workspace_id: str
    allow_self_review: bool
    require_review_on_case_update: bool
    allow_direct_revision_for_active_case: bool
    direct_revision_roles: list[str]
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
    custom_fields: dict[str, Any] = Field(default_factory=dict)
    source_type: CaseDraftSource = CaseDraftSource.manual
    source_ref: dict[str, Any] = Field(default_factory=dict)


class CaseDraftUpdate(BaseModel):
    module_id: str | None = None
    title: str | None = Field(default=None, min_length=1, max_length=300)
    steps: list[str] | None = Field(default=None, max_length=100)
    expected_result: str | None = Field(default=None, max_length=2000)
    priority: str | None = Field(default=None, max_length=32)
    risk: str | None = Field(default=None, max_length=80)
    tags: list[str] | None = Field(default=None, max_length=50)
    custom_fields: dict[str, Any] | None = None


class ReviewRequest(BaseModel):
    action: ReviewAction
    comment: str = Field(default="", max_length=1000)
    edits: CaseDraftUpdate | None = None


class ReviewCommentRequest(BaseModel):
    comment: str = Field(min_length=1, max_length=1000)


class ChangeAddressedRequest(BaseModel):
    comment: str = Field(min_length=1, max_length=1000)
    diff_summary: dict[str, Any] = Field(default_factory=dict)


class DirectRevisionRequest(CaseDraftUpdate):
    change_summary: str = Field(min_length=1, max_length=500)


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
        allow_direct_revision_for_active_case=settings.allow_direct_revision_for_active_case,
        direct_revision_roles=settings.direct_revision_roles,
        updated_by=settings.updated_by,
        created_at=settings.created_at,
        updated_at=settings.updated_at,
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


def get_draft_or_404(db: Session, workspace_id: str, project_id: str, draft_id: str) -> CaseDraft:
    draft = db.scalar(
        select(CaseDraft).where(
            CaseDraft.id == draft_id,
            CaseDraft.workspace_id == workspace_id,
            CaseDraft.project_id == project_id,
        )
    )
    if draft is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Case draft not found")
    return draft


def get_cycle_or_404(db: Session, workspace_id: str, project_id: str, cycle_id: str) -> CaseReviewCycle:
    cycle = db.scalar(
        select(CaseReviewCycle).where(
            CaseReviewCycle.id == cycle_id,
            CaseReviewCycle.workspace_id == workspace_id,
            CaseReviewCycle.project_id == project_id,
        )
    )
    if cycle is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Review cycle not found")
    return cycle


def get_current_revision(db: Session, test_case: TestCase) -> CaseRevision | None:
    if not test_case.current_revision_id:
        return None
    return db.get(CaseRevision, test_case.current_revision_id)


def get_open_cycle(db: Session, test_case_id: str) -> CaseReviewCycle | None:
    return db.scalar(
        select(CaseReviewCycle)
        .where(CaseReviewCycle.test_case_id == test_case_id, CaseReviewCycle.status.in_(OPEN_REVIEW_STATUSES))
        .order_by(CaseReviewCycle.created_at.desc(), CaseReviewCycle.id.desc())
    )


def get_active_draft(db: Session, test_case_id: str) -> CaseDraft | None:
    return db.scalar(
        select(CaseDraft)
        .where(
            CaseDraft.test_case_id == test_case_id,
            CaseDraft.draft_status.in_([CaseDraftStatus.editing.value, CaseDraftStatus.in_review.value]),
        )
        .order_by(CaseDraft.created_at.desc(), CaseDraft.id.desc())
    )


def module_path_label(db: Session, module_id: str | None) -> str:
    if not module_id:
        return "Unassigned"
    module = db.get(ProjectModule, module_id)
    return module.path_label if module else "Archived module"


def draft_content_snapshot(draft: CaseDraft, test_case_id: str | None = None) -> dict[str, Any]:
    return {
        "test_case_id": test_case_id or draft.test_case_id,
        "module_id": draft.module_id,
        "title": draft.title,
        "steps": draft.steps,
        "expected_result": draft.expected_result,
        "priority": draft.priority,
        "risk": draft.risk,
        "tags": draft.tags,
        "custom_fields": draft.custom_fields,
        "source_type": draft.source_type,
        "source_ref": draft.source_ref,
    }


def apply_draft_update(db: Session, workspace_id: str, project_id: str, draft: CaseDraft, payload: CaseDraftUpdate, actor_email: str) -> dict[str, Any]:
    update_data = payload.model_dump(exclude_unset=True)
    if "module_id" in update_data and update_data["module_id"]:
        get_module_or_404(db, workspace_id, project_id, update_data["module_id"])
    for field, value in update_data.items():
        if field in {"steps", "tags"} and value is not None:
            value = [item.strip() for item in value if item.strip()]
        setattr(draft, field, value)
    draft.updated_by = actor_email
    draft.updated_at = now_utc()
    return update_data


def create_case_draft(
    db: Session,
    *,
    workspace_id: str,
    project_id: str,
    test_case_id: str,
    actor_email: str,
    payload: TestCaseCreate | CaseDraftUpdate,
    source_type: str,
    source_ref: dict[str, Any] | None = None,
    base_revision_id: str | None = None,
) -> CaseDraft:
    data = payload.model_dump(exclude_unset=True)
    draft = CaseDraft(
        workspace_id=workspace_id,
        project_id=project_id,
        test_case_id=test_case_id,
        base_revision_id=base_revision_id,
        module_id=data.get("module_id"),
        title=str(data.get("title") or "Untitled case"),
        steps=[step.strip() for step in data.get("steps", []) if step.strip()],
        expected_result=str(data.get("expected_result") or ""),
        priority=str(data.get("priority") or "P2"),
        risk=str(data.get("risk") or "medium"),
        tags=[tag.strip() for tag in data.get("tags", []) if tag.strip()],
        custom_fields=data.get("custom_fields") or {},
        source_type=source_type,
        source_ref=source_ref or data.get("source_ref") or {},
        created_by=actor_email,
        updated_by=actor_email,
    )
    db.add(draft)
    db.flush()
    return draft


def create_revision_from_draft(db: Session, test_case: TestCase, draft: CaseDraft, actor_email: str, change_summary: str) -> CaseRevision:
    revision = CaseRevision(
        workspace_id=test_case.workspace_id,
        project_id=test_case.project_id,
        test_case_id=test_case.id,
        revision_number=test_case.current_revision_number + 1,
        module_id=draft.module_id,
        module_path_label=module_path_label(db, draft.module_id),
        content_snapshot=draft_content_snapshot(draft, test_case.id),
        change_summary=change_summary,
        created_by=actor_email,
    )
    db.add(revision)
    db.flush()
    test_case.lifecycle_status = TestCaseLifecycle.active.value
    test_case.current_revision_id = revision.id
    test_case.current_revision_number = revision.revision_number
    test_case.current_module_id = draft.module_id
    test_case.updated_at = now_utc()
    draft.draft_status = CaseDraftStatus.consumed.value
    draft.updated_by = actor_email
    draft.updated_at = now_utc()
    return revision


def record_event(
    db: Session,
    *,
    test_case: TestCase,
    actor_email: str,
    action: ReviewEventAction,
    comment: str = "",
    cycle: CaseReviewCycle | None = None,
    draft: CaseDraft | None = None,
    revision: CaseRevision | None = None,
    diff_summary: dict[str, Any] | None = None,
    before: dict[str, Any] | None = None,
    after: dict[str, Any] | None = None,
) -> CaseReviewEvent:
    event = CaseReviewEvent(
        workspace_id=test_case.workspace_id,
        project_id=test_case.project_id,
        test_case_id=test_case.id,
        cycle_id=cycle.id if cycle else None,
        draft_id=draft.id if draft else None,
        revision_id=revision.id if revision else None,
        actor_email=actor_email,
        action=action.value,
        comment=comment,
        diff_summary=diff_summary,
        before=before,
        after=after,
    )
    db.add(event)
    db.flush()
    return event


def ensure_not_self_review(settings: WorkspaceReviewSettings, cycle: CaseReviewCycle, actor_email: str) -> None:
    if settings.allow_self_review:
        return
    if cycle.submitted_by == actor_email:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Submitter cannot review their own test case")


def build_case_response(db: Session, test_case: TestCase, *, include_history: bool = False) -> TestCaseResponse | TestCaseDetailResponse:
    active_draft = get_active_draft(db, test_case.id)
    current_revision = get_current_revision(db, test_case)
    open_cycle = get_open_cycle(db, test_case.id)
    title = active_draft.title if active_draft else str((current_revision.content_snapshot.get("title") if current_revision else "") or "Untitled case")
    module_id = active_draft.module_id if active_draft else test_case.current_module_id
    base = {
        "id": test_case.id,
        "workspace_id": test_case.workspace_id,
        "project_id": test_case.project_id,
        "lifecycle_status": test_case.lifecycle_status,
        "current_revision_id": test_case.current_revision_id,
        "current_revision_number": test_case.current_revision_number,
        "current_module_id": test_case.current_module_id,
        "source_type": test_case.source_type,
        "source_ref": test_case.source_ref,
        "created_by": test_case.created_by,
        "created_at": test_case.created_at,
        "updated_at": test_case.updated_at,
        "title": title,
        "module_id": module_id,
        "module_path_label": module_path_label(db, module_id),
        "review_status": open_cycle.status if open_cycle else None,
        "active_draft": draft_to_response(active_draft) if active_draft else None,
        "current_revision": revision_to_response(current_revision) if current_revision else None,
        "open_cycle": cycle_to_response(open_cycle) if open_cycle else None,
    }
    if not include_history:
        return TestCaseResponse(**base)
    revisions = db.scalars(
        select(CaseRevision)
        .where(CaseRevision.test_case_id == test_case.id)
        .order_by(CaseRevision.revision_number.desc(), CaseRevision.created_at.desc())
    ).all()
    cycles = db.scalars(
        select(CaseReviewCycle)
        .where(CaseReviewCycle.test_case_id == test_case.id)
        .order_by(CaseReviewCycle.created_at.desc(), CaseReviewCycle.id.desc())
    ).all()
    events = db.scalars(
        select(CaseReviewEvent)
        .where(CaseReviewEvent.test_case_id == test_case.id)
        .order_by(CaseReviewEvent.created_at.desc(), CaseReviewEvent.id.desc())
    ).all()
    return TestCaseDetailResponse(
        **base,
        revisions=[revision_to_response(item) for item in revisions],
        review_cycles=[cycle_to_response(item) for item in cycles],
        review_events=[event_to_response(item) for item in events],
    )


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
    settings.allow_direct_revision_for_active_case = payload.allow_direct_revision_for_active_case
    settings.direct_revision_roles = payload.direct_revision_roles
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


@router.get("/projects/{project_id}/test-cases", response_model=list[TestCaseResponse])
def list_test_cases(
    workspace_id: str,
    project_id: str,
    db: DbSession,
    module_id: str | None = Query(default=None),
    include_descendants: bool = Query(default=True),
    lifecycle_status: TestCaseLifecycle | None = None,
    review_status: ReviewCycleStatus | None = None,
    source_type: str | None = Query(default=None),
    priority: str | None = Query(default=None),
    tag: str | None = Query(default=None),
    search: str | None = Query(default=None),
) -> list[TestCaseResponse]:
    get_workspace_or_404(db, workspace_id)
    get_project_or_404(db, workspace_id, project_id)
    statement = select(TestCase).where(TestCase.workspace_id == workspace_id, TestCase.project_id == project_id)
    if lifecycle_status:
        statement = statement.where(TestCase.lifecycle_status == lifecycle_status.value)
    else:
        statement = statement.where(TestCase.lifecycle_status != TestCaseLifecycle.archived.value)
    if source_type:
        statement = statement.where(TestCase.source_type == source_type)
    module_ids: list[str] | None = None
    if module_id:
        module = get_module_or_404(db, workspace_id, project_id, module_id)
        module_ids = descendant_module_ids(db, module, include_self=True) if include_descendants else [module.id]
    cases = list(db.scalars(statement.order_by(TestCase.updated_at.desc(), TestCase.id.desc())).all())
    responses = [build_case_response(db, item) for item in cases]
    if module_ids is not None:
        responses = [item for item in responses if item.module_id in module_ids]
    if review_status:
        responses = [item for item in responses if item.review_status == review_status.value]
    if priority:
        responses = [
            item for item in responses
            if (item.active_draft and item.active_draft.priority == priority)
            or (item.current_revision and item.current_revision.content_snapshot.get("priority") == priority)
        ]
    if tag:
        responses = [
            item for item in responses
            if tag in (item.active_draft.tags if item.active_draft else item.current_revision.content_snapshot.get("tags", []) if item.current_revision else [])
        ]
    if search:
        lowered = search.lower()
        responses = [item for item in responses if lowered in item.title.lower()]
    return responses


@router.get("/projects/{project_id}/review-cycles", response_model=list[TestCaseResponse])
def list_review_queue(
    workspace_id: str,
    project_id: str,
    db: DbSession,
    status_filter: ReviewCycleStatus = Query(default=ReviewCycleStatus.pending_review, alias="status"),
) -> list[TestCaseResponse]:
    get_workspace_or_404(db, workspace_id)
    get_project_or_404(db, workspace_id, project_id)
    cycles = db.scalars(
        select(CaseReviewCycle)
        .where(CaseReviewCycle.workspace_id == workspace_id, CaseReviewCycle.project_id == project_id, CaseReviewCycle.status == status_filter.value)
        .order_by(CaseReviewCycle.created_at.desc(), CaseReviewCycle.id.desc())
    ).all()
    cases = [get_case_or_404(db, workspace_id, project_id, cycle.test_case_id) for cycle in cycles]
    return [build_case_response(db, item) for item in cases]


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
    source_type = payload.source_type.value
    test_case = TestCase(
        workspace_id=workspace_id,
        project_id=project_id,
        lifecycle_status=TestCaseLifecycle.draft.value,
        current_module_id=None,
        source_type=source_type,
        source_ref=payload.source_ref,
        created_by=actor_email,
    )
    db.add(test_case)
    db.flush()
    draft = create_case_draft(
        db,
        workspace_id=workspace_id,
        project_id=project_id,
        test_case_id=test_case.id,
        actor_email=actor_email,
        payload=payload,
        source_type=source_type,
        source_ref=payload.source_ref,
    )
    record_event(
        db,
        test_case=test_case,
        actor_email=actor_email,
        action=ReviewEventAction.commented,
        comment="Created editable draft",
        draft=draft,
        after=draft_content_snapshot(draft, test_case.id),
    )
    audit(
        db,
        workspace_id=workspace_id,
        actor_email=actor_email,
        action="test_case.created",
        entity_type="TestCase",
        entity_id=test_case.id,
        summary=f"Created test case identity {draft.title}",
        after={"test_case_id": test_case.id, "draft_id": draft.id, "source_type": source_type},
    )
    db.commit()
    db.refresh(test_case)
    return build_case_response(db, test_case)


@router.get("/projects/{project_id}/test-cases/{case_id}", response_model=TestCaseDetailResponse)
def get_test_case(workspace_id: str, project_id: str, case_id: str, db: DbSession) -> TestCaseDetailResponse:
    get_workspace_or_404(db, workspace_id)
    get_project_or_404(db, workspace_id, project_id)
    return build_case_response(db, get_case_or_404(db, workspace_id, project_id, case_id), include_history=True)


@router.post("/projects/{project_id}/test-cases/{case_id}/drafts", response_model=CaseDraftResponse, status_code=status.HTTP_201_CREATED)
def create_active_edit_draft(workspace_id: str, project_id: str, case_id: str, db: DbSession, actor_email: ActorEmail) -> CaseDraftResponse:
    test_case = get_case_or_404(db, workspace_id, project_id, case_id)
    if test_case.lifecycle_status != TestCaseLifecycle.active.value:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Only active cases can create active edit drafts")
    existing = get_active_draft(db, test_case.id)
    if existing:
        return draft_to_response(existing)
    revision = get_current_revision(db, test_case)
    if revision is None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Active case has no current revision")
    snapshot = revision.content_snapshot
    draft = CaseDraft(
        workspace_id=workspace_id,
        project_id=project_id,
        test_case_id=test_case.id,
        base_revision_id=revision.id,
        module_id=str(snapshot.get("module_id") or "") or None,
        title=str(snapshot.get("title") or "Untitled case"),
        steps=[str(item) for item in snapshot.get("steps", [])],
        expected_result=str(snapshot.get("expected_result") or ""),
        priority=str(snapshot.get("priority") or "P2"),
        risk=str(snapshot.get("risk") or "medium"),
        tags=[str(item) for item in snapshot.get("tags", [])],
        custom_fields=snapshot.get("custom_fields", {}),
        source_type=CaseDraftSource.active_edit.value,
        source_ref={"base_revision_id": revision.id, "revision_number": revision.revision_number},
        created_by=actor_email,
        updated_by=actor_email,
    )
    db.add(draft)
    db.flush()
    record_event(db, test_case=test_case, actor_email=actor_email, action=ReviewEventAction.commented, comment="Created active edit draft", draft=draft)
    db.commit()
    db.refresh(draft)
    return draft_to_response(draft)


@router.patch("/projects/{project_id}/case-drafts/{draft_id}", response_model=CaseDraftResponse)
def update_case_draft(
    workspace_id: str,
    project_id: str,
    draft_id: str,
    payload: CaseDraftUpdate,
    db: DbSession,
    actor_email: ActorEmail,
) -> CaseDraftResponse:
    draft = get_draft_or_404(db, workspace_id, project_id, draft_id)
    if draft.draft_status not in {CaseDraftStatus.editing.value, CaseDraftStatus.in_review.value}:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Closed drafts cannot be edited")
    if draft.draft_status == CaseDraftStatus.in_review.value:
        open_cycle = get_open_cycle(db, draft.test_case_id)
        if open_cycle and open_cycle.status == ReviewCycleStatus.pending_review.value:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Pending review drafts cannot be edited")
    before = draft_content_snapshot(draft)
    changes = apply_draft_update(db, workspace_id, project_id, draft, payload, actor_email)
    test_case = get_case_or_404(db, workspace_id, project_id, draft.test_case_id)
    record_event(
        db,
        test_case=test_case,
        actor_email=actor_email,
        action=ReviewEventAction.commented,
        comment="Edited draft",
        draft=draft,
        before=before,
        after={"changes": changes, "draft": draft_content_snapshot(draft)},
    )
    db.commit()
    db.refresh(draft)
    return draft_to_response(draft)


@router.patch("/projects/{project_id}/test-cases/{case_id}", response_model=TestCaseResponse)
def update_test_case(
    workspace_id: str,
    project_id: str,
    case_id: str,
    payload: CaseDraftUpdate,
    db: DbSession,
    actor_email: ActorEmail,
) -> TestCaseResponse:
    test_case = get_case_or_404(db, workspace_id, project_id, case_id)
    draft = get_active_draft(db, test_case.id)
    if draft is None:
        if test_case.lifecycle_status == TestCaseLifecycle.active.value:
            create_active_edit_draft(workspace_id, project_id, case_id, db, actor_email)
            draft = get_active_draft(db, test_case.id)
        else:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Draft not found")
    if draft is None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Draft not found")
    apply_draft_update(db, workspace_id, project_id, draft, payload, actor_email)
    db.commit()
    db.refresh(test_case)
    return build_case_response(db, test_case)


@router.post("/projects/{project_id}/case-drafts/{draft_id}/submit-review", response_model=CaseReviewCycleResponse, status_code=status.HTTP_201_CREATED)
def submit_draft_review(workspace_id: str, project_id: str, draft_id: str, db: DbSession, actor_email: ActorEmail) -> CaseReviewCycleResponse:
    draft = get_draft_or_404(db, workspace_id, project_id, draft_id)
    if not draft.module_id:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Draft must be assigned to a module before review")
    if draft.draft_status != CaseDraftStatus.editing.value:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Only editing drafts can be submitted")
    test_case = get_case_or_404(db, workspace_id, project_id, draft.test_case_id)
    if get_open_cycle(db, test_case.id):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Test case already has an open review cycle")
    cycle = CaseReviewCycle(
        workspace_id=workspace_id,
        project_id=project_id,
        test_case_id=test_case.id,
        draft_id=draft.id,
        status=ReviewCycleStatus.pending_review.value,
        submitted_by=actor_email,
    )
    draft.draft_status = CaseDraftStatus.in_review.value
    draft.updated_by = actor_email
    draft.updated_at = now_utc()
    test_case.updated_at = now_utc()
    db.add(cycle)
    db.flush()
    record_event(db, test_case=test_case, actor_email=actor_email, action=ReviewEventAction.submitted, comment="Submitted draft for review", cycle=cycle, draft=draft)
    audit(
        db,
        workspace_id=workspace_id,
        actor_email=actor_email,
        action="case_review_cycle.submitted",
        entity_type="CaseReviewCycle",
        entity_id=cycle.id,
        summary=f"Submitted {draft.title} for review",
        after={"test_case_id": test_case.id, "draft_id": draft.id},
    )
    db.commit()
    db.refresh(cycle)
    return cycle_to_response(cycle)


@router.post("/projects/{project_id}/test-cases/{case_id}/submit-review", response_model=TestCaseResponse)
def submit_case_review(workspace_id: str, project_id: str, case_id: str, db: DbSession, actor_email: ActorEmail) -> TestCaseResponse:
    test_case = get_case_or_404(db, workspace_id, project_id, case_id)
    draft = get_active_draft(db, test_case.id)
    if draft is None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="No editable draft to submit")
    submit_draft_review(workspace_id, project_id, draft.id, db, actor_email)
    db.refresh(test_case)
    return build_case_response(db, test_case)


@router.post("/projects/{project_id}/review-cycles/{cycle_id}/request-changes", response_model=CaseReviewEventResponse, status_code=status.HTTP_201_CREATED)
def request_changes(
    workspace_id: str,
    project_id: str,
    cycle_id: str,
    payload: ReviewCommentRequest,
    db: DbSession,
    actor_email: ActorEmail,
) -> CaseReviewEventResponse:
    settings = get_or_create_review_settings(db, workspace_id, actor_email)
    cycle = get_cycle_or_404(db, workspace_id, project_id, cycle_id)
    if cycle.status != ReviewCycleStatus.pending_review.value:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Only pending reviews can request changes")
    ensure_not_self_review(settings, cycle, actor_email)
    test_case = get_case_or_404(db, workspace_id, project_id, cycle.test_case_id)
    draft = get_draft_or_404(db, workspace_id, project_id, cycle.draft_id)
    before = cycle_to_response(cycle).model_dump(mode="json")
    cycle.status = ReviewCycleStatus.changes_requested.value
    cycle.updated_at = now_utc()
    draft.draft_status = CaseDraftStatus.editing.value
    draft.updated_at = now_utc()
    event = record_event(db, test_case=test_case, actor_email=actor_email, action=ReviewEventAction.changes_requested, comment=payload.comment, cycle=cycle, draft=draft, before=before, after=cycle_to_response(cycle).model_dump(mode="json"))
    db.commit()
    db.refresh(event)
    return event_to_response(event)


@router.post("/projects/{project_id}/review-cycles/{cycle_id}/address-changes", response_model=CaseReviewEventResponse, status_code=status.HTTP_201_CREATED)
def address_changes(
    workspace_id: str,
    project_id: str,
    cycle_id: str,
    payload: ChangeAddressedRequest,
    db: DbSession,
    actor_email: ActorEmail,
) -> CaseReviewEventResponse:
    cycle = get_cycle_or_404(db, workspace_id, project_id, cycle_id)
    if cycle.status != ReviewCycleStatus.changes_requested.value:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Only changes_requested cycles can be addressed")
    test_case = get_case_or_404(db, workspace_id, project_id, cycle.test_case_id)
    draft = get_draft_or_404(db, workspace_id, project_id, cycle.draft_id)
    if draft.updated_by != actor_email and cycle.submitted_by != actor_email:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Only the author can address requested changes")
    before = cycle_to_response(cycle).model_dump(mode="json")
    cycle.status = ReviewCycleStatus.pending_review.value
    cycle.updated_at = now_utc()
    draft.draft_status = CaseDraftStatus.in_review.value
    draft.updated_at = now_utc()
    event = record_event(
        db,
        test_case=test_case,
        actor_email=actor_email,
        action=ReviewEventAction.changes_addressed,
        comment=payload.comment,
        cycle=cycle,
        draft=draft,
        diff_summary=payload.diff_summary,
        before=before,
        after=cycle_to_response(cycle).model_dump(mode="json"),
    )
    db.commit()
    db.refresh(event)
    return event_to_response(event)


@router.post("/projects/{project_id}/review-cycles/{cycle_id}/approve", response_model=CaseReviewEventResponse, status_code=status.HTTP_201_CREATED)
def approve_review(
    workspace_id: str,
    project_id: str,
    cycle_id: str,
    payload: ReviewCommentRequest,
    db: DbSession,
    actor_email: ActorEmail,
) -> CaseReviewEventResponse:
    settings = get_or_create_review_settings(db, workspace_id, actor_email)
    cycle = get_cycle_or_404(db, workspace_id, project_id, cycle_id)
    if cycle.status != ReviewCycleStatus.pending_review.value:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Only pending reviews can be approved")
    ensure_not_self_review(settings, cycle, actor_email)
    test_case = get_case_or_404(db, workspace_id, project_id, cycle.test_case_id)
    draft = get_draft_or_404(db, workspace_id, project_id, cycle.draft_id)
    revision = create_revision_from_draft(db, test_case, draft, actor_email, payload.comment or "Approved test case")
    cycle.status = ReviewCycleStatus.approved.value
    cycle.closed_by = actor_email
    cycle.closed_at = now_utc()
    cycle.updated_at = now_utc()
    event = record_event(db, test_case=test_case, actor_email=actor_email, action=ReviewEventAction.approved, comment=payload.comment, cycle=cycle, draft=draft, revision=revision, after=revision.content_snapshot)
    audit(
        db,
        workspace_id=workspace_id,
        actor_email=actor_email,
        action="case_review_cycle.approved",
        entity_type="CaseRevision",
        entity_id=revision.id,
        summary=f"Approved {draft.title} as revision {revision.revision_number}",
        after={"test_case_id": test_case.id, "revision_id": revision.id, "revision_number": revision.revision_number},
    )
    db.commit()
    db.refresh(event)
    return event_to_response(event)


@router.post("/projects/{project_id}/review-cycles/{cycle_id}/reject", response_model=CaseReviewEventResponse, status_code=status.HTTP_201_CREATED)
def reject_review(
    workspace_id: str,
    project_id: str,
    cycle_id: str,
    payload: ReviewCommentRequest,
    db: DbSession,
    actor_email: ActorEmail,
) -> CaseReviewEventResponse:
    settings = get_or_create_review_settings(db, workspace_id, actor_email)
    cycle = get_cycle_or_404(db, workspace_id, project_id, cycle_id)
    if cycle.status != ReviewCycleStatus.pending_review.value:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Only pending reviews can be rejected")
    ensure_not_self_review(settings, cycle, actor_email)
    test_case = get_case_or_404(db, workspace_id, project_id, cycle.test_case_id)
    draft = get_draft_or_404(db, workspace_id, project_id, cycle.draft_id)
    cycle.status = ReviewCycleStatus.rejected.value
    cycle.closed_by = actor_email
    cycle.closed_at = now_utc()
    cycle.updated_at = now_utc()
    draft.draft_status = CaseDraftStatus.cancelled.value
    draft.updated_at = now_utc()
    test_case.updated_at = now_utc()
    event = record_event(db, test_case=test_case, actor_email=actor_email, action=ReviewEventAction.rejected, comment=payload.comment, cycle=cycle, draft=draft)
    db.commit()
    db.refresh(event)
    return event_to_response(event)


@router.post("/projects/{project_id}/review-cycles/{cycle_id}/comments", response_model=CaseReviewEventResponse, status_code=status.HTTP_201_CREATED)
def comment_review(
    workspace_id: str,
    project_id: str,
    cycle_id: str,
    payload: ReviewCommentRequest,
    db: DbSession,
    actor_email: ActorEmail,
) -> CaseReviewEventResponse:
    cycle = get_cycle_or_404(db, workspace_id, project_id, cycle_id)
    test_case = get_case_or_404(db, workspace_id, project_id, cycle.test_case_id)
    draft = get_draft_or_404(db, workspace_id, project_id, cycle.draft_id)
    event = record_event(db, test_case=test_case, actor_email=actor_email, action=ReviewEventAction.commented, comment=payload.comment, cycle=cycle, draft=draft)
    db.commit()
    db.refresh(event)
    return event_to_response(event)


@router.post("/projects/{project_id}/test-cases/{case_id}/reviews", response_model=CaseReviewEventResponse, status_code=status.HTTP_201_CREATED)
def review_test_case(
    workspace_id: str,
    project_id: str,
    case_id: str,
    payload: ReviewRequest,
    db: DbSession,
    actor_email: ActorEmail,
) -> CaseReviewEventResponse:
    test_case = get_case_or_404(db, workspace_id, project_id, case_id)
    cycle = get_open_cycle(db, test_case.id)
    if cycle is None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="No open review cycle")
    if payload.edits:
        draft = get_draft_or_404(db, workspace_id, project_id, cycle.draft_id)
        if cycle.status != ReviewCycleStatus.changes_requested.value:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Draft edits require changes_requested")
        apply_draft_update(db, workspace_id, project_id, draft, payload.edits, actor_email)
    if payload.action == ReviewAction.changes_requested:
        return request_changes(workspace_id, project_id, cycle.id, ReviewCommentRequest(comment=payload.comment), db, actor_email)
    if payload.action == ReviewAction.changes_addressed:
        return address_changes(workspace_id, project_id, cycle.id, ChangeAddressedRequest(comment=payload.comment), db, actor_email)
    if payload.action == ReviewAction.approved:
        return approve_review(workspace_id, project_id, cycle.id, ReviewCommentRequest(comment=payload.comment or "Approved"), db, actor_email)
    if payload.action == ReviewAction.rejected:
        return reject_review(workspace_id, project_id, cycle.id, ReviewCommentRequest(comment=payload.comment or "Rejected"), db, actor_email)
    if payload.action == ReviewAction.commented:
        return comment_review(workspace_id, project_id, cycle.id, ReviewCommentRequest(comment=payload.comment or "Commented"), db, actor_email)
    raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Use submit-review endpoint to submit cases")


@router.get("/projects/{project_id}/test-cases/{case_id}/reviews", response_model=list[CaseReviewEventResponse])
def list_case_reviews(workspace_id: str, project_id: str, case_id: str, db: DbSession) -> list[CaseReviewEventResponse]:
    get_case_or_404(db, workspace_id, project_id, case_id)
    events = db.scalars(
        select(CaseReviewEvent)
        .where(CaseReviewEvent.workspace_id == workspace_id, CaseReviewEvent.project_id == project_id, CaseReviewEvent.test_case_id == case_id)
        .order_by(CaseReviewEvent.created_at.desc(), CaseReviewEvent.id.desc())
    ).all()
    return [event_to_response(event) for event in events]


@router.get("/projects/{project_id}/test-cases/{case_id}/revisions", response_model=list[CaseRevisionResponse])
def list_case_revisions(workspace_id: str, project_id: str, case_id: str, db: DbSession) -> list[CaseRevisionResponse]:
    get_case_or_404(db, workspace_id, project_id, case_id)
    revisions = db.scalars(
        select(CaseRevision)
        .where(CaseRevision.workspace_id == workspace_id, CaseRevision.project_id == project_id, CaseRevision.test_case_id == case_id)
        .order_by(CaseRevision.revision_number.desc(), CaseRevision.created_at.desc())
    ).all()
    return [revision_to_response(revision) for revision in revisions]


@router.post("/projects/{project_id}/test-cases/{case_id}/direct-revision", response_model=CaseRevisionResponse, status_code=status.HTTP_201_CREATED)
def direct_revision(
    workspace_id: str,
    project_id: str,
    case_id: str,
    payload: DirectRevisionRequest,
    db: DbSession,
    actor_email: ActorEmail,
) -> CaseRevisionResponse:
    settings = get_or_create_review_settings(db, workspace_id, actor_email)
    if not settings.allow_direct_revision_for_active_case:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Direct revision is disabled for this workspace")
    require_workspace_owner(db, workspace_id, actor_email)
    test_case = get_case_or_404(db, workspace_id, project_id, case_id)
    if test_case.lifecycle_status != TestCaseLifecycle.active.value:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Only active cases can use direct revision")
    high_impact = {"module_id", "steps", "expected_result"}
    requested = set(payload.model_dump(exclude_unset=True)) - {"change_summary"}
    if requested & high_impact:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="High-impact changes must go through review")
    revision = get_current_revision(db, test_case)
    if revision is None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Active case has no current revision")
    snapshot = dict(revision.content_snapshot)
    update_data = payload.model_dump(exclude_unset=True)
    update_data.pop("change_summary", None)
    snapshot.update(update_data)
    draft = CaseDraft(
        workspace_id=workspace_id,
        project_id=project_id,
        test_case_id=test_case.id,
        base_revision_id=revision.id,
        module_id=str(snapshot.get("module_id") or "") or None,
        title=str(snapshot.get("title") or "Untitled case"),
        steps=[str(item) for item in snapshot.get("steps", [])],
        expected_result=str(snapshot.get("expected_result") or ""),
        priority=str(snapshot.get("priority") or "P2"),
        risk=str(snapshot.get("risk") or "medium"),
        tags=[str(item) for item in snapshot.get("tags", [])],
        custom_fields=snapshot.get("custom_fields", {}),
        draft_status=CaseDraftStatus.consumed.value,
        source_type=CaseDraftSource.active_edit.value,
        source_ref={"direct_revision": True, "base_revision_id": revision.id},
        created_by=actor_email,
        updated_by=actor_email,
    )
    db.add(draft)
    db.flush()
    new_revision = create_revision_from_draft(db, test_case, draft, actor_email, payload.change_summary)
    record_event(db, test_case=test_case, actor_email=actor_email, action=ReviewEventAction.direct_revision, comment=payload.change_summary, draft=draft, revision=new_revision, before=revision.content_snapshot, after=new_revision.content_snapshot)
    db.commit()
    db.refresh(new_revision)
    return revision_to_response(new_revision)


@router.delete("/projects/{project_id}/test-cases/{case_id}", status_code=status.HTTP_204_NO_CONTENT)
def archive_test_case(workspace_id: str, project_id: str, case_id: str, db: DbSession, actor_email: ActorEmail) -> Response:
    test_case = get_case_or_404(db, workspace_id, project_id, case_id)
    before = build_case_response(db, test_case).model_dump(mode="json")
    test_case.lifecycle_status = TestCaseLifecycle.archived.value
    test_case.updated_at = now_utc()
    record_event(
        db,
        test_case=test_case,
        actor_email=actor_email,
        action=ReviewEventAction.cancelled,
        comment="Archived test case",
        before=before,
        after={"lifecycle_status": TestCaseLifecycle.archived.value},
    )
    audit(
        db,
        workspace_id=workspace_id,
        actor_email=actor_email,
        action="test_case.archived",
        entity_type="TestCase",
        entity_id=test_case.id,
        summary=f"Archived test case {before['title']}",
        before=before,
        after={"lifecycle_status": TestCaseLifecycle.archived.value},
    )
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
