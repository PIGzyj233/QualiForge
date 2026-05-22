from __future__ import annotations

import shutil
import os
import subprocess
from datetime import datetime
from enum import StrEnum
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, Request, status
from pydantic import BaseModel, Field, HttpUrl
from sqlalchemy import JSON, DateTime, ForeignKey, Integer, String, UniqueConstraint, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Mapped, Session, mapped_column

from app.config import Settings
from app.database import Base, Database
from app.workspaces import (
    ActorEmail,
    audit,
    get_project_or_404,
    get_workspace_or_404,
    new_id,
    now_utc,
    require_workspace_owner,
)


class RepositoryStatus(StrEnum):
    pending = "pending"
    synced = "synced"
    sync_failed = "sync_failed"


class JobStatus(StrEnum):
    queued = "queued"
    running = "running"
    succeeded = "succeeded"
    failed = "failed"
    cancelled = "cancelled"


class WorkspaceGitLabCredential(Base):
    __tablename__ = "workspace_gitlab_credentials"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    workspace_id: Mapped[str] = mapped_column(ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False, unique=True, index=True)
    gitlab_base_url: Mapped[str] = mapped_column(String(500), nullable=False)
    token_secret: Mapped[str] = mapped_column(String(500), nullable=False)
    updated_by: Mapped[str] = mapped_column(String(254), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc, onupdate=now_utc, nullable=False)


class GitRepository(Base):
    __tablename__ = "git_repositories"
    __table_args__ = (UniqueConstraint("project_id", "remote_url", name="uq_repository_remote_per_project"),)

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    workspace_id: Mapped[str] = mapped_column(ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False, index=True)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    remote_url: Mapped[str] = mapped_column(String(700), nullable=False)
    default_branch: Mapped[str] = mapped_column(String(120), default="main", nullable=False)
    mirror_path: Mapped[str] = mapped_column(String(1000), nullable=False)
    status: Mapped[str] = mapped_column(String(32), default=RepositoryStatus.pending.value, nullable=False)
    last_synced_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    repo_size_limit_mb: Mapped[int] = mapped_column(Integer, default=1024, nullable=False)
    diff_file_limit: Mapped[int] = mapped_column(Integer, default=500, nullable=False)
    sync_timeout_seconds: Mapped[int] = mapped_column(Integer, default=120, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc, onupdate=now_utc, nullable=False)


class Job(Base):
    __tablename__ = "jobs"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    workspace_id: Mapped[str] = mapped_column(ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False, index=True)
    project_id: Mapped[str | None] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), nullable=True, index=True)
    repository_id: Mapped[str | None] = mapped_column(ForeignKey("git_repositories.id", ondelete="CASCADE"), nullable=True, index=True)
    job_type: Mapped[str] = mapped_column(String(80), nullable=False)
    status: Mapped[str] = mapped_column(String(32), default=JobStatus.queued.value, nullable=False, index=True)
    created_by: Mapped[str] = mapped_column(String(254), nullable=False)
    input_summary: Mapped[str] = mapped_column(String(500), nullable=False)
    output_summary: Mapped[str] = mapped_column(String(500), default="", nullable=False)
    error_summary: Mapped[str] = mapped_column(String(500), default="", nullable=False)
    key_logs: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    timeout_seconds: Mapped[int] = mapped_column(Integer, default=120, nullable=False)
    repo_size_limit_mb: Mapped[int] = mapped_column(Integer, default=1024, nullable=False)
    diff_file_limit: Mapped[int] = mapped_column(Integer, default=500, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc, nullable=False, index=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class GitLabCredentialUpsert(BaseModel):
    gitlab_base_url: HttpUrl
    token: str = Field(min_length=1, max_length=500)


class GitLabCredentialResponse(BaseModel):
    id: str
    workspace_id: str
    gitlab_base_url: str
    token_masked: str
    has_token: bool
    updated_by: str
    created_at: datetime
    updated_at: datetime


class RepositoryCreate(BaseModel):
    project_id: str
    name: str = Field(min_length=1, max_length=120)
    remote_url: str = Field(min_length=1, max_length=700)
    default_branch: str = Field(default="main", min_length=1, max_length=120)
    repo_size_limit_mb: int | None = Field(default=None, ge=1, le=100000)
    diff_file_limit: int | None = Field(default=None, ge=1, le=100000)
    sync_timeout_seconds: int | None = Field(default=None, ge=1, le=3600)


class RepositoryResponse(BaseModel):
    id: str
    workspace_id: str
    project_id: str
    name: str
    remote_url: str
    default_branch: str
    mirror_path: str
    status: str
    last_synced_at: datetime | None
    repo_size_limit_mb: int
    diff_file_limit: int
    sync_timeout_seconds: int
    created_at: datetime
    updated_at: datetime


class JobResponse(BaseModel):
    id: str
    workspace_id: str
    project_id: str | None
    repository_id: str | None
    job_type: str
    status: str
    created_by: str
    input_summary: str
    output_summary: str
    error_summary: str
    key_logs: list[str]
    timeout_seconds: int
    repo_size_limit_mb: int
    diff_file_limit: int
    created_at: datetime
    started_at: datetime | None
    finished_at: datetime | None


def get_db(request: Request):
    yield from request.app.state.database.session()


DbSession = Annotated[Session, Depends(get_db)]

router = APIRouter(prefix="/api/workspaces/{workspace_id}", tags=["gitlab"])


def mask_token(token: str) -> str:
    if len(token) <= 8:
        return "****"
    return f"{token[:4]}...{token[-4:]}"


def credential_to_response(credential: WorkspaceGitLabCredential) -> GitLabCredentialResponse:
    return GitLabCredentialResponse(
        id=credential.id,
        workspace_id=credential.workspace_id,
        gitlab_base_url=credential.gitlab_base_url,
        token_masked=mask_token(credential.token_secret),
        has_token=bool(credential.token_secret),
        updated_by=credential.updated_by,
        created_at=credential.created_at,
        updated_at=credential.updated_at,
    )


def repository_to_response(repository: GitRepository) -> RepositoryResponse:
    return RepositoryResponse(
        id=repository.id,
        workspace_id=repository.workspace_id,
        project_id=repository.project_id,
        name=repository.name,
        remote_url=repository.remote_url,
        default_branch=repository.default_branch,
        mirror_path=repository.mirror_path,
        status=repository.status,
        last_synced_at=repository.last_synced_at,
        repo_size_limit_mb=repository.repo_size_limit_mb,
        diff_file_limit=repository.diff_file_limit,
        sync_timeout_seconds=repository.sync_timeout_seconds,
        created_at=repository.created_at,
        updated_at=repository.updated_at,
    )


def job_to_response(job: Job) -> JobResponse:
    return JobResponse(
        id=job.id,
        workspace_id=job.workspace_id,
        project_id=job.project_id,
        repository_id=job.repository_id,
        job_type=job.job_type,
        status=job.status,
        created_by=job.created_by,
        input_summary=job.input_summary,
        output_summary=job.output_summary,
        error_summary=job.error_summary,
        key_logs=job.key_logs,
        timeout_seconds=job.timeout_seconds,
        repo_size_limit_mb=job.repo_size_limit_mb,
        diff_file_limit=job.diff_file_limit,
        created_at=job.created_at,
        started_at=job.started_at,
        finished_at=job.finished_at,
    )


def sandbox_path(settings: Settings, workspace_id: str, project_id: str, repository_id: str) -> Path:
    root = Path(settings.git_sandbox_root).expanduser()
    return root / workspace_id[:12] / project_id[:12] / f"{repository_id[:12]}.git"


def ensure_safe_sandbox_path(root: Path, target: Path) -> Path:
    root_resolved = root.expanduser().resolve(strict=False)
    target_resolved = target.expanduser().resolve(strict=False)
    if root_resolved != target_resolved and root_resolved not in target_resolved.parents:
        raise ValueError("Sandbox path escapes configured root")

    current = root_resolved
    relative_parts = target_resolved.relative_to(root_resolved).parts
    for part in relative_parts[:-1]:
        current = current / part
        if current.exists() and current.is_symlink():
            raise ValueError("Sandbox path contains a symlink")
    if target_resolved.exists() and target_resolved.is_symlink():
        raise ValueError("Repository mirror path is a symlink")
    return target_resolved


def directory_size_mb(path: Path) -> float:
    total = 0
    for item in path.rglob("*"):
        if item.is_file() and not item.is_symlink():
            total += item.stat().st_size
    return total / 1024 / 1024


def get_repository_or_404(db: Session, workspace_id: str, repository_id: str) -> GitRepository:
    repository = db.scalar(
        select(GitRepository).where(
            GitRepository.id == repository_id,
            GitRepository.workspace_id == workspace_id,
        )
    )
    if repository is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Repository not found")
    return repository


def get_gitlab_credential(db: Session, workspace_id: str) -> WorkspaceGitLabCredential | None:
    return db.scalar(select(WorkspaceGitLabCredential).where(WorkspaceGitLabCredential.workspace_id == workspace_id))


def git_command_for_log(command: list[str]) -> str:
    return " ".join("<redacted-git-header>" if "PRIVATE-TOKEN:" in part else part for part in command)


def run_git(command: list[str], timeout_seconds: int, key_logs: list[str]) -> subprocess.CompletedProcess[str]:
    key_logs.append(f"$ {git_command_for_log(command)}")
    return subprocess.run(
        command,
        capture_output=True,
        check=False,
        env={**os.environ, "GIT_TERMINAL_PROMPT": "0"},
        text=True,
        timeout=timeout_seconds,
    )


def run_repository_sync(database: Database, settings: Settings, job_id: str) -> None:
    with database.session_factory() as db:
        job = db.get(Job, job_id)
        if job is None:
            return
        repository = db.get(GitRepository, job.repository_id)
        if repository is None:
            job.status = JobStatus.failed.value
            job.error_summary = "Repository no longer exists"
            job.finished_at = now_utc()
            db.commit()
            return

        job.status = JobStatus.running.value
        job.started_at = now_utc()
        job.key_logs = [f"Sandbox root: {settings.git_sandbox_root}", "Git sync started"]
        db.commit()

        try:
            root = Path(settings.git_sandbox_root).expanduser()
            mirror_path = ensure_safe_sandbox_path(root, Path(repository.mirror_path))
            mirror_path.parent.mkdir(parents=True, exist_ok=True)

            credential = get_gitlab_credential(db, repository.workspace_id)
            auth_args = []
            if credential is not None and repository.remote_url.startswith(("http://", "https://")):
                auth_args = ["-c", f"http.extraHeader=PRIVATE-TOKEN: {credential.token_secret}"]

            if mirror_path.exists():
                command = ["git", *auth_args, "-C", str(mirror_path), "remote", "update", "--prune"]
            else:
                command = ["git", *auth_args, "clone", "--mirror", "--", repository.remote_url, str(mirror_path)]
            result = run_git(command, repository.sync_timeout_seconds, job.key_logs)
            if result.stdout.strip():
                job.key_logs = [*job.key_logs, result.stdout.strip()[:1000]]
            if result.returncode != 0:
                stderr = result.stderr.strip()[:500] or f"git exited with {result.returncode}"
                raise RuntimeError(stderr)

            size_mb = directory_size_mb(mirror_path)
            job.key_logs = [*job.key_logs, f"Mirror size: {size_mb:.2f} MB"]
            if size_mb > repository.repo_size_limit_mb:
                raise RuntimeError(f"Repository mirror exceeds {repository.repo_size_limit_mb} MB limit")

            repository.status = RepositoryStatus.synced.value
            repository.last_synced_at = now_utc()
            repository.updated_at = now_utc()
            job.status = JobStatus.succeeded.value
            job.output_summary = f"Repository mirror synced to {mirror_path}"
        except subprocess.TimeoutExpired:
            repository.status = RepositoryStatus.sync_failed.value
            job.status = JobStatus.failed.value
            job.error_summary = f"Git sync timed out after {repository.sync_timeout_seconds} seconds"
        except Exception as exc:
            repository.status = RepositoryStatus.sync_failed.value
            job.status = JobStatus.failed.value
            job.error_summary = str(exc)[:500]
        finally:
            job.finished_at = now_utc()
            db.commit()


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
