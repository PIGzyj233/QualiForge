from __future__ import annotations

from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, Request, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.git.models import (
    GitLabCredentialResponse,
    GitLabCredentialUpsert,
    GitRepository,
    Job,
    JobResponse,
    JobStatus,
    RepositoryCreate,
    RepositoryResponse,
    RepositoryStatus,
    WorkspaceGitLabCredential,
)
from app.git.sandbox import (
    credential_to_response,
    directory_size_mb,
    ensure_safe_sandbox_path,
    get_gitlab_credential,
    get_repository_or_404,
    git_command_for_log,
    job_to_response,
    mask_token,
    repository_to_response,
    run_git,
    run_repository_sync,
    sandbox_path,
)
from app.workspace.routes import ActorEmail, audit, get_project_or_404, get_workspace_or_404, now_utc, require_workspace_owner


def get_db(request: Request):
    yield from request.app.state.database.session()


DbSession = Annotated[Session, Depends(get_db)]

router = APIRouter(prefix="/api/workspaces/{workspace_id}", tags=["gitlab"])


@router.get("/gitlab-token", response_model=GitLabCredentialResponse | None)
def get_gitlab_token(workspace_id: str, db: DbSession) -> GitLabCredentialResponse | None:
    get_workspace_or_404(db, workspace_id)
    credential = get_gitlab_credential(db, workspace_id)
    return credential_to_response(credential) if credential else None


@router.put("/gitlab-token", response_model=GitLabCredentialResponse)
def upsert_gitlab_token(
    workspace_id: str,
    payload: GitLabCredentialUpsert,
    db: DbSession,
    actor_email: ActorEmail,
) -> GitLabCredentialResponse:
    get_workspace_or_404(db, workspace_id)
    require_workspace_owner(db, workspace_id, actor_email)
    credential = get_gitlab_credential(db, workspace_id)
    before = None
    if credential is None:
        credential = WorkspaceGitLabCredential(
            workspace_id=workspace_id,
            gitlab_base_url=str(payload.gitlab_base_url).rstrip("/"),
            token_secret=payload.token,
            updated_by=actor_email,
        )
        db.add(credential)
        action = "gitlab_token.created"
    else:
        before = {"gitlab_base_url": credential.gitlab_base_url, "has_token": bool(credential.token_secret)}
        credential.gitlab_base_url = str(payload.gitlab_base_url).rstrip("/")
        credential.token_secret = payload.token
        credential.updated_by = actor_email
        credential.updated_at = now_utc()
        action = "gitlab_token.updated"
    db.flush()
    audit(
        db,
        workspace_id=workspace_id,
        actor_email=actor_email,
        action=action,
        entity_type="WorkspaceGitLabCredential",
        entity_id=credential.id,
        summary="Updated workspace GitLab token",
        before=before,
        after={"gitlab_base_url": credential.gitlab_base_url, "has_token": True},
    )
    db.commit()
    db.refresh(credential)
    return credential_to_response(credential)


@router.get("/repositories", response_model=list[RepositoryResponse])
def list_repositories(workspace_id: str, db: DbSession, project_id: str | None = Query(default=None)) -> list[RepositoryResponse]:
    get_workspace_or_404(db, workspace_id)
    statement = select(GitRepository).where(GitRepository.workspace_id == workspace_id).order_by(GitRepository.created_at)
    if project_id:
        get_project_or_404(db, workspace_id, project_id)
        statement = statement.where(GitRepository.project_id == project_id)
    repositories = db.scalars(statement).all()
    return [repository_to_response(repository) for repository in repositories]


@router.post("/repositories", response_model=RepositoryResponse, status_code=status.HTTP_201_CREATED)
def bind_repository(
    workspace_id: str,
    payload: RepositoryCreate,
    db: DbSession,
    request: Request,
    actor_email: ActorEmail,
) -> RepositoryResponse:
    get_workspace_or_404(db, workspace_id)
    get_project_or_404(db, workspace_id, payload.project_id)
    repository = GitRepository(
        workspace_id=workspace_id,
        project_id=payload.project_id,
        name=payload.name,
        remote_url=payload.remote_url,
        default_branch=payload.default_branch,
        mirror_path="pending",
        repo_size_limit_mb=payload.repo_size_limit_mb or request.app.state.settings.git_repo_size_limit_mb,
        diff_file_limit=payload.diff_file_limit or request.app.state.settings.git_diff_file_limit,
        sync_timeout_seconds=payload.sync_timeout_seconds or request.app.state.settings.git_sync_timeout_seconds,
    )
    db.add(repository)
    try:
        db.flush()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Repository already bound to project") from exc
    try:
        mirror_path = ensure_safe_sandbox_path(
            Path(request.app.state.settings.git_sandbox_root),
            sandbox_path(request.app.state.settings, workspace_id, payload.project_id, repository.id),
        )
    except ValueError as exc:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    repository.mirror_path = str(mirror_path)
    audit(
        db,
        workspace_id=workspace_id,
        actor_email=actor_email,
        action="repository.bound",
        entity_type="GitRepository",
        entity_id=repository.id,
        summary=f"Bound repository {repository.name}",
        after={
            "project_id": repository.project_id,
            "remote_url": repository.remote_url,
            "mirror_path": repository.mirror_path,
            "repo_size_limit_mb": repository.repo_size_limit_mb,
            "diff_file_limit": repository.diff_file_limit,
            "sync_timeout_seconds": repository.sync_timeout_seconds,
        },
    )
    db.commit()
    db.refresh(repository)
    return repository_to_response(repository)


@router.post("/repositories/{repository_id}/sync", response_model=JobResponse, status_code=status.HTTP_202_ACCEPTED)
def sync_repository(
    workspace_id: str,
    repository_id: str,
    background_tasks: BackgroundTasks,
    db: DbSession,
    request: Request,
    actor_email: ActorEmail,
) -> JobResponse:
    get_workspace_or_404(db, workspace_id)
    repository = get_repository_or_404(db, workspace_id, repository_id)
    job = Job(
        workspace_id=workspace_id,
        project_id=repository.project_id,
        repository_id=repository.id,
        job_type="git_sync",
        created_by=actor_email,
        input_summary=f"Sync repository {repository.name}",
        key_logs=["Queued git sync"],
        timeout_seconds=repository.sync_timeout_seconds,
        repo_size_limit_mb=repository.repo_size_limit_mb,
        diff_file_limit=repository.diff_file_limit,
    )
    db.add(job)
    db.flush()
    audit(
        db,
        workspace_id=workspace_id,
        actor_email=actor_email,
        action="repository_sync.queued",
        entity_type="Job",
        entity_id=job.id,
        summary=f"Queued sync for repository {repository.name}",
        after={"repository_id": repository.id, "mirror_path": repository.mirror_path},
    )
    db.commit()
    db.refresh(job)
    background_tasks.add_task(run_repository_sync, request.app.state.database, request.app.state.settings, job.id)
    return job_to_response(job)


@router.get("/jobs", response_model=list[JobResponse])
def list_jobs(
    workspace_id: str,
    db: DbSession,
    repository_id: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
) -> list[JobResponse]:
    get_workspace_or_404(db, workspace_id)
    statement = select(Job).where(Job.workspace_id == workspace_id).order_by(Job.created_at.desc(), Job.id.desc()).limit(limit)
    if repository_id:
        statement = statement.where(Job.repository_id == repository_id)
    jobs = db.scalars(statement).all()
    return [job_to_response(job) for job in jobs]
