from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field
from sqlalchemy import JSON, DateTime, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from app.platform.database import Base
from app.workspace.routes import new_id, now_utc


class DiffAnalysisStatus(StrEnum):
    running = "running"
    succeeded = "succeeded"
    failed = "failed"


class ChangeType(StrEnum):
    added = "added"
    modified = "modified"
    deleted = "deleted"
    renamed = "renamed"


class RiskLevel(StrEnum):
    low = "low"
    medium = "medium"
    high = "high"


class DiffAnalysis(Base):
    __tablename__ = "diff_analyses"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    workspace_id: Mapped[str] = mapped_column(ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False, index=True)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True)
    repository_id: Mapped[str] = mapped_column(ForeignKey("git_repositories.id", ondelete="CASCADE"), nullable=False, index=True)
    job_id: Mapped[str] = mapped_column(ForeignKey("jobs.id", ondelete="CASCADE"), nullable=False, index=True)
    base_ref: Mapped[str] = mapped_column(String(160), nullable=False)
    target_ref: Mapped[str] = mapped_column(String(160), nullable=False)
    status: Mapped[str] = mapped_column(String(32), default=DiffAnalysisStatus.running.value, nullable=False, index=True)
    risk_level: Mapped[str] = mapped_column(String(32), default=RiskLevel.low.value, nullable=False)
    summary: Mapped[str] = mapped_column(String(700), default="", nullable=False)
    recommended_scope: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    file_changes: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list, nullable=False)
    module_impacts: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list, nullable=False)
    key_logs: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    error_summary: Mapped[str] = mapped_column(String(700), default="", nullable=False)
    created_by: Mapped[str] = mapped_column(String(254), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc, nullable=False, index=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class DiffAnalysisCreate(BaseModel):
    repository_id: str = Field(min_length=1, max_length=64)
    base_ref: str = Field(min_length=1, max_length=160)
    target_ref: str = Field(min_length=1, max_length=160)


class DiffAnalysisResponse(BaseModel):
    id: str
    workspace_id: str
    project_id: str
    repository_id: str
    job_id: str
    base_ref: str
    target_ref: str
    status: str
    risk_level: str
    summary: str
    recommended_scope: list[str]
    file_changes: list[dict[str, Any]]
    module_impacts: list[dict[str, Any]]
    key_logs: list[str]
    error_summary: str
    created_by: str
    created_at: datetime
    completed_at: datetime | None


