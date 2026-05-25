from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel
from sqlalchemy import JSON, DateTime, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.cases.step_models import CaseStep, normalize_steps_with_legacy
from app.platform.database import Base
from app.workspace.routes import new_id, now_utc


class TestCaseLifecycle(StrEnum):
    draft = "draft"
    active = "active"
    archived = "archived"


class CaseDraftStatus(StrEnum):
    editing = "editing"
    in_review = "in_review"
    consumed = "consumed"
    cancelled = "cancelled"


class CaseDraftSource(StrEnum):
    manual = "manual"
    import_ = "import"
    ai_suggestion = "ai_suggestion"
    active_edit = "active_edit"


class ReviewCycleStatus(StrEnum):
    pending_review = "pending_review"
    changes_requested = "changes_requested"
    approved = "approved"
    rejected = "rejected"
    cancelled = "cancelled"


class ReviewEventAction(StrEnum):
    submitted = "submitted"
    changes_requested = "changes_requested"
    changes_addressed = "changes_addressed"
    approved = "approved"
    rejected = "rejected"
    direct_revision = "direct_revision"
    commented = "commented"
    cancelled = "cancelled"


OPEN_REVIEW_STATUSES = {
    ReviewCycleStatus.pending_review.value,
    ReviewCycleStatus.changes_requested.value,
}


class TestCase(Base):
    __tablename__ = "test_cases"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    workspace_id: Mapped[str] = mapped_column(ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False, index=True)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True)
    lifecycle_status: Mapped[str] = mapped_column(String(32), default=TestCaseLifecycle.draft.value, nullable=False, index=True)
    current_revision_id: Mapped[str | None] = mapped_column(ForeignKey("case_revisions.id", ondelete="SET NULL"), nullable=True, index=True)
    current_revision_number: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    current_module_id: Mapped[str | None] = mapped_column(ForeignKey("project_modules.id", ondelete="SET NULL"), nullable=True, index=True)
    source_type: Mapped[str] = mapped_column(String(40), default=CaseDraftSource.manual.value, nullable=False, index=True)
    source_ref: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    created_by: Mapped[str] = mapped_column(String(254), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc, nullable=False, index=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc, onupdate=now_utc, nullable=False)


class CaseDraft(Base):
    __tablename__ = "case_drafts"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    test_case_id: Mapped[str] = mapped_column(ForeignKey("test_cases.id", ondelete="CASCADE"), nullable=False, index=True)
    workspace_id: Mapped[str] = mapped_column(ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False, index=True)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True)
    base_revision_id: Mapped[str | None] = mapped_column(ForeignKey("case_revisions.id", ondelete="SET NULL"), nullable=True, index=True)
    module_id: Mapped[str | None] = mapped_column(ForeignKey("project_modules.id", ondelete="SET NULL"), nullable=True, index=True)
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    steps: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    expected_result: Mapped[str] = mapped_column(String(2000), default="", nullable=False)
    priority: Mapped[str] = mapped_column(String(32), default="P2", nullable=False)
    risk: Mapped[str] = mapped_column(String(80), default="medium", nullable=False)
    tags: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    custom_fields: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    draft_status: Mapped[str] = mapped_column(String(32), default=CaseDraftStatus.editing.value, nullable=False, index=True)
    source_type: Mapped[str] = mapped_column(String(40), default=CaseDraftSource.manual.value, nullable=False, index=True)
    source_ref: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    created_by: Mapped[str] = mapped_column(String(254), nullable=False)
    updated_by: Mapped[str] = mapped_column(String(254), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc, nullable=False, index=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc, onupdate=now_utc, nullable=False)


class CaseRevision(Base):
    __tablename__ = "case_revisions"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    workspace_id: Mapped[str] = mapped_column(ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False, index=True)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True)
    test_case_id: Mapped[str] = mapped_column(ForeignKey("test_cases.id", ondelete="CASCADE"), nullable=False, index=True)
    revision_number: Mapped[int] = mapped_column(Integer, nullable=False)
    module_id: Mapped[str | None] = mapped_column(ForeignKey("project_modules.id", ondelete="SET NULL"), nullable=True, index=True)
    module_path_label: Mapped[str] = mapped_column(String(500), default="", nullable=False)
    content_snapshot: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    change_summary: Mapped[str] = mapped_column(String(500), default="", nullable=False)
    created_by: Mapped[str] = mapped_column(String(254), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc, nullable=False, index=True)


class CaseReviewCycle(Base):
    __tablename__ = "case_review_cycles"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    workspace_id: Mapped[str] = mapped_column(ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False, index=True)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True)
    test_case_id: Mapped[str] = mapped_column(ForeignKey("test_cases.id", ondelete="CASCADE"), nullable=False, index=True)
    draft_id: Mapped[str] = mapped_column(ForeignKey("case_drafts.id", ondelete="CASCADE"), nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(40), default=ReviewCycleStatus.pending_review.value, nullable=False, index=True)
    submitted_by: Mapped[str] = mapped_column(String(254), nullable=False)
    closed_by: Mapped[str] = mapped_column(String(254), default="", nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc, nullable=False, index=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc, onupdate=now_utc, nullable=False)
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class CaseReviewEvent(Base):
    __tablename__ = "case_review_events"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    workspace_id: Mapped[str] = mapped_column(ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False, index=True)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True)
    test_case_id: Mapped[str] = mapped_column(ForeignKey("test_cases.id", ondelete="CASCADE"), nullable=False, index=True)
    cycle_id: Mapped[str | None] = mapped_column(ForeignKey("case_review_cycles.id", ondelete="SET NULL"), nullable=True, index=True)
    draft_id: Mapped[str | None] = mapped_column(ForeignKey("case_drafts.id", ondelete="SET NULL"), nullable=True, index=True)
    revision_id: Mapped[str | None] = mapped_column(ForeignKey("case_revisions.id", ondelete="SET NULL"), nullable=True, index=True)
    actor_email: Mapped[str] = mapped_column(String(254), nullable=False)
    action: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    comment: Mapped[str] = mapped_column(String(1000), default="", nullable=False)
    diff_summary: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    before: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    after: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc, nullable=False, index=True)


class CaseDraftResponse(BaseModel):
    id: str
    test_case_id: str
    workspace_id: str
    project_id: str
    base_revision_id: str | None
    module_id: str | None
    title: str
    steps: list[CaseStep]
    priority: str
    risk: str
    tags: list[str]
    custom_fields: dict[str, Any]
    draft_status: str
    source_type: str
    source_ref: dict[str, Any]
    created_by: str
    updated_by: str
    created_at: datetime
    updated_at: datetime


class CaseRevisionResponse(BaseModel):
    id: str
    workspace_id: str
    project_id: str
    test_case_id: str
    revision_number: int
    module_id: str | None
    module_path_label: str
    content_snapshot: dict[str, Any]
    change_summary: str
    created_by: str
    created_at: datetime


class CaseReviewCycleResponse(BaseModel):
    id: str
    workspace_id: str
    project_id: str
    test_case_id: str
    draft_id: str
    status: str
    submitted_by: str
    closed_by: str
    created_at: datetime
    updated_at: datetime
    closed_at: datetime | None


class CaseReviewEventResponse(BaseModel):
    id: str
    workspace_id: str
    project_id: str
    test_case_id: str
    cycle_id: str | None
    draft_id: str | None
    revision_id: str | None
    actor_email: str
    action: str
    comment: str
    diff_summary: dict[str, Any] | None
    before: dict[str, Any] | None
    after: dict[str, Any] | None
    created_at: datetime


class TestCaseResponse(BaseModel):
    id: str
    workspace_id: str
    project_id: str
    lifecycle_status: str
    current_revision_id: str | None
    current_revision_number: int
    current_module_id: str | None
    source_type: str
    source_ref: dict[str, Any]
    created_by: str
    created_at: datetime
    updated_at: datetime
    title: str
    module_id: str | None
    module_path_label: str
    review_status: str | None
    active_draft: CaseDraftResponse | None
    current_revision: CaseRevisionResponse | None
    open_cycle: CaseReviewCycleResponse | None


class TestCaseDetailResponse(TestCaseResponse):
    revisions: list[CaseRevisionResponse]
    review_cycles: list[CaseReviewCycleResponse]
    review_events: list[CaseReviewEventResponse]


def draft_to_response(draft: CaseDraft) -> CaseDraftResponse:
    return CaseDraftResponse(
        id=draft.id,
        test_case_id=draft.test_case_id,
        workspace_id=draft.workspace_id,
        project_id=draft.project_id,
        base_revision_id=draft.base_revision_id,
        module_id=draft.module_id,
        title=draft.title,
        steps=normalize_steps_with_legacy(draft.steps, draft.expected_result),
        priority=draft.priority,
        risk=draft.risk,
        tags=draft.tags,
        custom_fields=draft.custom_fields,
        draft_status=draft.draft_status,
        source_type=draft.source_type,
        source_ref=draft.source_ref,
        created_by=draft.created_by,
        updated_by=draft.updated_by,
        created_at=draft.created_at,
        updated_at=draft.updated_at,
    )


def revision_to_response(revision: CaseRevision) -> CaseRevisionResponse:
    return CaseRevisionResponse(
        id=revision.id,
        workspace_id=revision.workspace_id,
        project_id=revision.project_id,
        test_case_id=revision.test_case_id,
        revision_number=revision.revision_number,
        module_id=revision.module_id,
        module_path_label=revision.module_path_label,
        content_snapshot=revision.content_snapshot,
        change_summary=revision.change_summary,
        created_by=revision.created_by,
        created_at=revision.created_at,
    )


def cycle_to_response(cycle: CaseReviewCycle) -> CaseReviewCycleResponse:
    return CaseReviewCycleResponse(
        id=cycle.id,
        workspace_id=cycle.workspace_id,
        project_id=cycle.project_id,
        test_case_id=cycle.test_case_id,
        draft_id=cycle.draft_id,
        status=cycle.status,
        submitted_by=cycle.submitted_by,
        closed_by=cycle.closed_by,
        created_at=cycle.created_at,
        updated_at=cycle.updated_at,
        closed_at=cycle.closed_at,
    )


def event_to_response(event: CaseReviewEvent) -> CaseReviewEventResponse:
    return CaseReviewEventResponse(
        id=event.id,
        workspace_id=event.workspace_id,
        project_id=event.project_id,
        test_case_id=event.test_case_id,
        cycle_id=event.cycle_id,
        draft_id=event.draft_id,
        revision_id=event.revision_id,
        actor_email=event.actor_email,
        action=event.action,
        comment=event.comment,
        diff_summary=event.diff_summary,
        before=event.before,
        after=event.after,
        created_at=event.created_at,
    )
