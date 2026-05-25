from __future__ import annotations

from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, BackgroundTasks, Depends, File, HTTPException, Query, Request, Response, UploadFile, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.cases.domain import (
    CaseDraft,
    CaseDraftSource,
    CaseDraftStatus,
    CaseReviewCycle,
    CaseReviewEvent,
    ReviewCycleStatus,
    ReviewEventAction,
    TestCase,
    TestCaseLifecycle,
)
from app.cases.import_models import (
    BulkDraftUpdate,
    DraftResponse,
    DraftUpdate,
    ImportBatch,
    ImportBatchResponse,
    ImportBatchStatus,
    ImportCaseDraft,
    ImportDraftStatus,
    ImportResultResponse,
)
from app.cases.import_support import (
    batch_to_response,
    draft_to_response,
    get_batch_or_404,
    get_draft_or_404,
    import_file_type,
    run_import_conversion,
    safe_filename,
)
from app.cases.modules import get_module_or_404
from app.git.models import Job, JobStatus
from app.git.sandbox import job_to_response
from app.workspace.routes import ActorEmail, audit, get_project_or_404, get_workspace_or_404, new_id, now_utc, require_workspace_owner


def get_db(request: Request):
    yield from request.app.state.database.session()


DbSession = Annotated[Session, Depends(get_db)]

router = APIRouter(prefix="/api/workspaces/{workspace_id}/projects/{project_id}", tags=["case-imports"])


@router.post("/imports", response_model=ImportBatchResponse, status_code=status.HTTP_202_ACCEPTED)
async def upload_import_batch(
    workspace_id: str,
    project_id: str,
    background_tasks: BackgroundTasks,
    db: DbSession,
    request: Request,
    actor_email: ActorEmail,
    file: UploadFile = File(...),
) -> ImportBatchResponse:
    get_workspace_or_404(db, workspace_id)
    get_project_or_404(db, workspace_id, project_id)
    filename = safe_filename(file.filename or "import.csv")
    file_type = import_file_type(filename)
    content = await file.read()
    if not content:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Import file is empty")

    batch = ImportBatch(
        workspace_id=workspace_id,
        project_id=project_id,
        file_name=filename,
        file_type=file_type,
        original_file_path="pending",
        created_by=actor_email,
    )
    db.add(batch)
    db.flush()
    storage_dir = Path(request.app.state.settings.import_storage_root).expanduser() / workspace_id[:12] / project_id[:12] / batch.id
    storage_dir.mkdir(parents=True, exist_ok=True)
    storage_path = storage_dir / filename
    storage_path.write_bytes(content)
    batch.original_file_path = str(storage_path.resolve(strict=False))

    job = Job(
        workspace_id=workspace_id,
        project_id=project_id,
        job_type="import_cases",
        status=JobStatus.queued.value,
        created_by=actor_email,
        input_summary=f"Import historical cases from {filename}",
        key_logs=["Queued import normalization"],
        timeout_seconds=120,
        repo_size_limit_mb=0,
        diff_file_limit=0,
    )
    db.add(job)
    db.flush()
    batch.job_id = job.id
    audit(
        db,
        workspace_id=workspace_id,
        actor_email=actor_email,
        action="import_batch.uploaded",
        entity_type="ImportBatch",
        entity_id=batch.id,
        summary=f"Uploaded import file {filename}",
        after={"project_id": project_id, "file_name": filename, "file_type": file_type, "job_id": job.id},
    )
    db.commit()
    db.refresh(batch)
    background_tasks.add_task(run_import_conversion, request.app.state.database, batch.id)
    return batch_to_response(batch)


@router.get("/imports", response_model=list[ImportBatchResponse])
def list_import_batches(workspace_id: str, project_id: str, db: DbSession) -> list[ImportBatchResponse]:
    get_workspace_or_404(db, workspace_id)
    get_project_or_404(db, workspace_id, project_id)
    batches = db.scalars(
        select(ImportBatch)
        .where(ImportBatch.workspace_id == workspace_id, ImportBatch.project_id == project_id)
        .order_by(ImportBatch.created_at.desc(), ImportBatch.id.desc())
    ).all()
    return [batch_to_response(batch) for batch in batches]


@router.get("/imports/{batch_id}", response_model=ImportBatchResponse)
def get_import_batch(workspace_id: str, project_id: str, batch_id: str, db: DbSession) -> ImportBatchResponse:
    get_workspace_or_404(db, workspace_id)
    get_project_or_404(db, workspace_id, project_id)
    return batch_to_response(get_batch_or_404(db, workspace_id, project_id, batch_id))


@router.get("/imports/{batch_id}/drafts", response_model=list[DraftResponse])
def list_import_drafts(workspace_id: str, project_id: str, batch_id: str, db: DbSession) -> list[DraftResponse]:
    get_workspace_or_404(db, workspace_id)
    get_project_or_404(db, workspace_id, project_id)
    get_batch_or_404(db, workspace_id, project_id, batch_id)
    drafts = db.scalars(
        select(ImportCaseDraft)
        .where(ImportCaseDraft.workspace_id == workspace_id, ImportCaseDraft.project_id == project_id, ImportCaseDraft.batch_id == batch_id)
        .order_by(ImportCaseDraft.source_row_index, ImportCaseDraft.id)
    ).all()
    return [draft_to_response(draft) for draft in drafts]


def apply_draft_update(draft: ImportCaseDraft, payload: DraftUpdate) -> dict:
    update_data = payload.model_dump(exclude_unset=True)
    update_data.pop("draft_ids", None)
    for field, value in update_data.items():
        if field == "tags" and value is not None:
            value = [item.strip() for item in value if item.strip()]
        setattr(draft, field, value)
    draft.updated_at = now_utc()
    return update_data


def create_review_case_from_import_draft(db: Session, batch: ImportBatch, draft: ImportCaseDraft, actor_email: str) -> None:
    if draft.review_cycle_id:
        return
    if not draft.module_id:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Imported drafts must be assigned to a module before review")
    source_ref = {"batch_id": batch.id, "row_index": draft.source_row_index, "raw_row": draft.raw_row}
    test_case = TestCase(
        workspace_id=batch.workspace_id,
        project_id=batch.project_id,
        lifecycle_status=TestCaseLifecycle.draft.value,
        source_type=CaseDraftSource.import_.value,
        source_ref=source_ref,
        created_by=actor_email,
    )
    db.add(test_case)
    db.flush()
    case_draft = CaseDraft(
        workspace_id=batch.workspace_id,
        project_id=batch.project_id,
        test_case_id=test_case.id,
        module_id=draft.module_id,
        title=draft.title,
        steps=draft.steps,
        expected_result="",
        priority=draft.priority,
        risk=draft.risk,
        tags=draft.tags,
        custom_fields=draft.custom_fields,
        draft_status=CaseDraftStatus.in_review.value,
        source_type=CaseDraftSource.import_.value,
        source_ref=source_ref,
        created_by=actor_email,
        updated_by=actor_email,
    )
    db.add(case_draft)
    db.flush()
    cycle = CaseReviewCycle(
        workspace_id=batch.workspace_id,
        project_id=batch.project_id,
        test_case_id=test_case.id,
        draft_id=case_draft.id,
        status=ReviewCycleStatus.pending_review.value,
        submitted_by=actor_email,
    )
    db.add(cycle)
    db.flush()
    event = CaseReviewEvent(
        workspace_id=batch.workspace_id,
        project_id=batch.project_id,
        test_case_id=test_case.id,
        cycle_id=cycle.id,
        draft_id=case_draft.id,
        actor_email=actor_email,
        action=ReviewEventAction.submitted.value,
        comment="Submitted imported draft for review",
        after={
            "batch_id": batch.id,
            "source_row_index": draft.source_row_index,
            "title": draft.title,
            "module_id": draft.module_id,
        },
    )
    db.add(event)
    draft.test_case_id = test_case.id
    draft.case_draft_id = case_draft.id
    draft.review_cycle_id = cycle.id
    draft.status = ImportDraftStatus.review_submitted.value
    draft.updated_at = now_utc()


def ensure_import_draft_is_approved(db: Session, batch: ImportBatch, draft: ImportCaseDraft) -> None:
    if not draft.test_case_id or not draft.case_draft_id or not draft.review_cycle_id:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Submit imported drafts for review before finalizing import")
    test_case = db.get(TestCase, draft.test_case_id)
    cycle = db.get(CaseReviewCycle, draft.review_cycle_id)
    if (
        test_case is None
        or cycle is None
        or test_case.workspace_id != batch.workspace_id
        or test_case.project_id != batch.project_id
        or cycle.workspace_id != batch.workspace_id
        or cycle.project_id != batch.project_id
        or cycle.test_case_id != test_case.id
        or cycle.draft_id != draft.case_draft_id
    ):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Imported draft review state is incomplete")
    if cycle.status != ReviewCycleStatus.approved.value or test_case.lifecycle_status != TestCaseLifecycle.active.value:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Imported drafts must be approved before finalizing import")


@router.patch("/imports/{batch_id}/drafts/{draft_id}", response_model=DraftResponse)
def update_import_draft(
    workspace_id: str,
    project_id: str,
    batch_id: str,
    draft_id: str,
    payload: DraftUpdate,
    db: DbSession,
    actor_email: ActorEmail,
) -> DraftResponse:
    batch = get_batch_or_404(db, workspace_id, project_id, batch_id)
    if payload.module_id:
        get_module_or_404(db, workspace_id, project_id, payload.module_id)
    draft = get_draft_or_404(db, workspace_id, project_id, batch_id, draft_id)
    changes = apply_draft_update(draft, payload)
    batch.manual_changes = [
        *batch.manual_changes,
        {"actor_email": actor_email, "updated_at": now_utc().isoformat(), "draft_ids": [draft.id], "changes": changes},
    ]
    batch.updated_at = now_utc()
    audit(
        db,
        workspace_id=workspace_id,
        actor_email=actor_email,
        action="import_draft.updated",
        entity_type="ImportCaseDraft",
        entity_id=draft.id,
        summary=f"Updated imported draft {draft.title}",
        after=changes,
    )
    db.commit()
    db.refresh(draft)
    return draft_to_response(draft)


@router.patch("/imports/{batch_id}/drafts-bulk", response_model=list[DraftResponse])
def bulk_update_import_drafts(
    workspace_id: str,
    project_id: str,
    batch_id: str,
    payload: BulkDraftUpdate,
    db: DbSession,
    actor_email: ActorEmail,
) -> list[DraftResponse]:
    batch = get_batch_or_404(db, workspace_id, project_id, batch_id)
    if payload.module_id:
        get_module_or_404(db, workspace_id, project_id, payload.module_id)
    statement = select(ImportCaseDraft).where(
        ImportCaseDraft.workspace_id == workspace_id,
        ImportCaseDraft.project_id == project_id,
        ImportCaseDraft.batch_id == batch_id,
    )
    if payload.draft_ids:
        statement = statement.where(ImportCaseDraft.id.in_(payload.draft_ids))
    drafts = list(db.scalars(statement.order_by(ImportCaseDraft.source_row_index, ImportCaseDraft.id)).all())
    changes = payload.model_dump(exclude_unset=True)
    changes.pop("draft_ids", None)
    for draft in drafts:
        apply_draft_update(draft, payload)
    batch.manual_changes = [
        *batch.manual_changes,
        {"actor_email": actor_email, "updated_at": now_utc().isoformat(), "draft_ids": [draft.id for draft in drafts], "changes": changes},
    ]
    batch.updated_at = now_utc()
    audit(
        db,
        workspace_id=workspace_id,
        actor_email=actor_email,
        action="import_draft.bulk_updated",
        entity_type="ImportBatch",
        entity_id=batch.id,
        summary=f"Bulk updated {len(drafts)} imported drafts",
        after={"draft_count": len(drafts), "changes": changes},
    )
    db.commit()
    return [draft_to_response(draft) for draft in drafts]


@router.post("/imports/{batch_id}/submit-review", response_model=ImportBatchResponse)
def submit_import_review(workspace_id: str, project_id: str, batch_id: str, db: DbSession, actor_email: ActorEmail) -> ImportBatchResponse:
    batch = get_batch_or_404(db, workspace_id, project_id, batch_id)
    if batch.status == ImportBatchStatus.imported.value:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Imported batches cannot be resubmitted for review")
    drafts = db.scalars(select(ImportCaseDraft).where(ImportCaseDraft.batch_id == batch.id)).all()
    if not drafts:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Import batch has no drafts to submit for review")
    for draft in drafts:
        create_review_case_from_import_draft(db, batch, draft, actor_email)
    batch.status = ImportBatchStatus.review_submitted.value
    batch.submitted_at = now_utc()
    batch.updated_at = now_utc()
    audit(
        db,
        workspace_id=workspace_id,
        actor_email=actor_email,
        action="import_batch.review_submitted",
        entity_type="ImportBatch",
        entity_id=batch.id,
        summary=f"Submitted {len(drafts)} imported drafts for review",
        after={"draft_count": len(drafts)},
    )
    db.commit()
    db.refresh(batch)
    return batch_to_response(batch)


@router.post("/imports/{batch_id}/bulk-import", response_model=ImportResultResponse)
def bulk_import_test_cases(workspace_id: str, project_id: str, batch_id: str, db: DbSession, actor_email: ActorEmail) -> ImportResultResponse:
    require_workspace_owner(db, workspace_id, actor_email)
    batch = get_batch_or_404(db, workspace_id, project_id, batch_id)
    if batch.status == ImportBatchStatus.imported.value:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Import batch has already been finalized")
    drafts = db.scalars(
        select(ImportCaseDraft)
        .where(ImportCaseDraft.workspace_id == workspace_id, ImportCaseDraft.project_id == project_id, ImportCaseDraft.batch_id == batch_id)
        .order_by(ImportCaseDraft.source_row_index, ImportCaseDraft.id)
    ).all()
    if not drafts:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Import batch has no drafts to finalize")
    for draft in drafts:
        ensure_import_draft_is_approved(db, batch, draft)
    finalized_at = now_utc()
    for draft in drafts:
        draft.status = ImportDraftStatus.imported.value
        draft.updated_at = finalized_at
    batch.status = ImportBatchStatus.imported.value
    batch.imported_at = finalized_at
    batch.updated_at = finalized_at
    audit(
        db,
        workspace_id=workspace_id,
        actor_email=actor_email,
        action="import_batch.imported",
        entity_type="ImportBatch",
        entity_id=batch.id,
        summary=f"Finalized {len(drafts)} approved imported drafts into the test case library",
        after={"draft_count": len(drafts)},
    )
    db.commit()
    db.refresh(batch)
    return ImportResultResponse(batch=batch_to_response(batch), imported_count=len(drafts))
