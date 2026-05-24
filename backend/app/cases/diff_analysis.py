from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.cases.diff_engine import analysis_to_response, get_analysis_or_404, run_analysis
from app.cases.diff_models import ChangeType, DiffAnalysis, DiffAnalysisCreate, DiffAnalysisResponse, DiffAnalysisStatus, RiskLevel
from app.git.models import Job, JobStatus, RepositoryStatus
from app.git.sandbox import get_repository_or_404, job_to_response
from app.workspace.routes import ActorEmail, audit, get_project_or_404, get_workspace_or_404, now_utc


def get_db(request: Request):
    yield from request.app.state.database.session()


DbSession = Annotated[Session, Depends(get_db)]

router = APIRouter(prefix="/api/workspaces/{workspace_id}/projects/{project_id}", tags=["diff-analysis"])

RISK_ORDER = {RiskLevel.low.value: 1, RiskLevel.medium.value: 2, RiskLevel.high.value: 3}


@router.post("/diff-analyses", response_model=DiffAnalysisResponse, status_code=status.HTTP_201_CREATED)
def create_diff_analysis(
    workspace_id: str,
    project_id: str,
    payload: DiffAnalysisCreate,
    db: DbSession,
    request: Request,
    actor_email: ActorEmail,
) -> DiffAnalysisResponse:
    get_workspace_or_404(db, workspace_id)
    get_project_or_404(db, workspace_id, project_id)
    repository = get_repository_or_404(db, workspace_id, payload.repository_id)
    if repository.project_id != project_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Repository not found for project")
    if repository.status != RepositoryStatus.synced.value:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Repository must be synced before diff analysis")

    job = Job(
        workspace_id=workspace_id,
        project_id=project_id,
        repository_id=repository.id,
        job_type="diff_analysis",
        status=JobStatus.running.value,
        created_by=actor_email,
        input_summary=f"Analyze {repository.name}: {payload.base_ref}..{payload.target_ref}",
        key_logs=["Queued diff analysis"],
        timeout_seconds=repository.sync_timeout_seconds,
        repo_size_limit_mb=repository.repo_size_limit_mb,
        diff_file_limit=repository.diff_file_limit,
        started_at=now_utc(),
    )
    db.add(job)
    db.flush()
    analysis = DiffAnalysis(
        workspace_id=workspace_id,
        project_id=project_id,
        repository_id=repository.id,
        job_id=job.id,
        base_ref=payload.base_ref,
        target_ref=payload.target_ref,
        status=DiffAnalysisStatus.running.value,
        created_by=actor_email,
        key_logs=["Queued diff analysis"],
    )
    db.add(analysis)
    db.flush()

    try:
        run_analysis(db=db, settings_root=Path(request.app.state.settings.git_sandbox_root), repository=repository, analysis=analysis, job=job)
        audit(
            db,
            workspace_id=workspace_id,
            actor_email=actor_email,
            action="diff_analysis.completed",
            entity_type="DiffAnalysis",
            entity_id=analysis.id,
            summary=analysis.summary,
            after={
                "repository_id": repository.id,
                "base_ref": analysis.base_ref,
                "target_ref": analysis.target_ref,
                "risk_level": analysis.risk_level,
            },
        )
    except (subprocess.TimeoutExpired, RuntimeError, ValueError) as exc:
        analysis.status = DiffAnalysisStatus.failed.value
        analysis.error_summary = str(exc)[:700]
        analysis.key_logs = [*analysis.key_logs, analysis.error_summary]
        analysis.completed_at = now_utc()
        job.status = JobStatus.failed.value
        job.error_summary = analysis.error_summary
        job.key_logs = analysis.key_logs
    else:
        analysis.completed_at = now_utc()
    finally:
        job.finished_at = now_utc()
        db.commit()
        db.refresh(analysis)

    return analysis_to_response(analysis)


@router.get("/diff-analyses", response_model=list[DiffAnalysisResponse])
def list_diff_analyses(
    workspace_id: str,
    project_id: str,
    db: DbSession,
    repository_id: str | None = Query(default=None),
    limit: int = Query(default=30, ge=1, le=100),
) -> list[DiffAnalysisResponse]:
    get_workspace_or_404(db, workspace_id)
    get_project_or_404(db, workspace_id, project_id)
    statement = (
        select(DiffAnalysis)
        .where(DiffAnalysis.workspace_id == workspace_id, DiffAnalysis.project_id == project_id)
        .order_by(DiffAnalysis.created_at.desc(), DiffAnalysis.id.desc())
        .limit(limit)
    )
    if repository_id:
        statement = statement.where(DiffAnalysis.repository_id == repository_id)
    return [analysis_to_response(analysis) for analysis in db.scalars(statement).all()]


@router.get("/diff-analyses/{analysis_id}", response_model=DiffAnalysisResponse)
def get_diff_analysis(workspace_id: str, project_id: str, analysis_id: str, db: DbSession) -> DiffAnalysisResponse:
    return analysis_to_response(get_analysis_or_404(db, workspace_id, project_id, analysis_id))


@router.get("/diff-analyses/{analysis_id}/job")
def get_diff_analysis_job(workspace_id: str, project_id: str, analysis_id: str, db: DbSession):
    analysis = get_analysis_or_404(db, workspace_id, project_id, analysis_id)
    job = db.get(Job, analysis.job_id)
    if job is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found")
    return job_to_response(job)
