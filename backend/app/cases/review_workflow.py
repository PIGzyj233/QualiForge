from __future__ import annotations

from typing import Any

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.cases.domain import (
    OPEN_REVIEW_STATUSES,
    CaseDraft,
    CaseDraftResponse,
    CaseDraftStatus,
    CaseReviewCycle,
    CaseReviewEvent,
    CaseRevision,
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
from app.cases.modules import ProjectModule, get_module_or_404
from app.cases.review_models import (
    CaseDraftUpdate,
    ReviewSettingsResponse,
    TestCaseCreate,
    WorkspaceReviewSettings,
)
from app.workspace.routes import now_utc


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
