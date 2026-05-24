from __future__ import annotations

from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, Field, HttpUrl
from sqlalchemy import JSON, DateTime, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.platform.database import Base
from app.workspace.routes import new_id, now_utc


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


