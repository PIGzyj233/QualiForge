from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.cases.domain import (
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
from app.cases.modules import descendant_module_ids, get_module_or_404
from app.cases.review_models import (
    CaseDraftUpdate,
    ChangeAddressedRequest,
    DirectRevisionRequest,
    ReviewAction,
    ReviewCommentRequest,
    ReviewRequest,
    ReviewSettingsResponse,
    ReviewSettingsUpdate,
    TestCaseCreate,
    WorkspaceReviewSettings,
)
from app.cases.review_workflow import (
    apply_draft_update,
    build_case_response,
    create_case_draft,
    create_revision_from_draft,
    draft_content_snapshot,
    ensure_not_self_review,
    get_active_draft,
    get_case_or_404,
    get_current_revision,
    get_cycle_or_404,
    get_draft_or_404,
    get_open_cycle,
    get_or_create_review_settings,
    record_event,
    settings_to_response,
)
from app.cases.step_models import normalize_steps_with_legacy
from app.workspace.routes import ActorEmail, audit, get_project_or_404, get_workspace_or_404, now_utc, require_workspace_owner


def get_db(request: Request):
    yield from request.app.state.database.session()


DbSession = Annotated[Session, Depends(get_db)]

router = APIRouter(prefix="/api/workspaces/{workspace_id}", tags=["case-reviews"])


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
        steps=normalize_steps_with_legacy(snapshot.get("steps"), str(snapshot.get("expected_result") or "") or None),
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
        steps=normalize_steps_with_legacy(snapshot.get("steps"), str(snapshot.get("expected_result") or "") or None),
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
