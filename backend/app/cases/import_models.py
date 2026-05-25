from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field
from sqlalchemy import JSON, DateTime, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.cases.step_models import CaseStep, StepValidatorMixin
from app.platform.database import Base
from app.workspace.routes import new_id, now_utc


class ImportBatchStatus(StrEnum):
    uploaded = "uploaded"
    preview_ready = "preview_ready"
    review_submitted = "review_submitted"
    imported = "imported"
    failed = "failed"


class ImportDraftStatus(StrEnum):
    draft = "draft"
    review_submitted = "review_submitted"
    imported = "imported"


class ImportBatch(Base):
    __tablename__ = "import_batches"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    workspace_id: Mapped[str] = mapped_column(ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False, index=True)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True)
    job_id: Mapped[str | None] = mapped_column(ForeignKey("jobs.id", ondelete="SET NULL"), nullable=True, index=True)
    file_name: Mapped[str] = mapped_column(String(255), nullable=False)
    file_type: Mapped[str] = mapped_column(String(32), nullable=False)
    original_file_path: Mapped[str] = mapped_column(String(1000), nullable=False)
    status: Mapped[str] = mapped_column(String(32), default=ImportBatchStatus.uploaded.value, nullable=False, index=True)
    created_by: Mapped[str] = mapped_column(String(254), nullable=False)
    row_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    raw_rows: Mapped[list[dict]] = mapped_column(JSON, default=list, nullable=False)
    ai_conversion_result: Mapped[list[dict]] = mapped_column(JSON, default=list, nullable=False)
    manual_changes: Mapped[list[dict]] = mapped_column(JSON, default=list, nullable=False)
    error_summary: Mapped[str] = mapped_column(String(500), default="", nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc, nullable=False, index=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc, onupdate=now_utc, nullable=False)
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    imported_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class ImportCaseDraft(Base):
    __tablename__ = "import_case_drafts"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    workspace_id: Mapped[str] = mapped_column(ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False, index=True)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True)
    batch_id: Mapped[str] = mapped_column(ForeignKey("import_batches.id", ondelete="CASCADE"), nullable=False, index=True)
    module_id: Mapped[str | None] = mapped_column(ForeignKey("project_modules.id", ondelete="SET NULL"), nullable=True, index=True)
    test_case_id: Mapped[str | None] = mapped_column(ForeignKey("test_cases.id", ondelete="SET NULL"), nullable=True, index=True)
    case_draft_id: Mapped[str | None] = mapped_column(ForeignKey("case_drafts.id", ondelete="SET NULL"), nullable=True, index=True)
    review_cycle_id: Mapped[str | None] = mapped_column(ForeignKey("case_review_cycles.id", ondelete="SET NULL"), nullable=True, index=True)
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    steps: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    expected_result: Mapped[str] = mapped_column(String(2000), default="", nullable=False)
    priority: Mapped[str] = mapped_column(String(32), default="P2", nullable=False)
    risk: Mapped[str] = mapped_column(String(80), default="medium", nullable=False)
    tags: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    custom_fields: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    source_row_index: Mapped[int] = mapped_column(Integer, nullable=False)
    raw_row: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    ai_confidence: Mapped[int] = mapped_column(Integer, default=75, nullable=False)
    status: Mapped[str] = mapped_column(String(32), default=ImportDraftStatus.draft.value, nullable=False, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc, onupdate=now_utc, nullable=False)


class ImportBatchResponse(BaseModel):
    id: str
    workspace_id: str
    project_id: str
    job_id: str | None
    file_name: str
    file_type: str
    original_file_path: str
    status: str
    created_by: str
    row_count: int
    raw_rows: list[dict]
    ai_conversion_result: list[dict]
    manual_changes: list[dict]
    error_summary: str
    created_at: datetime
    updated_at: datetime
    submitted_at: datetime | None
    imported_at: datetime | None


class DraftResponse(BaseModel):
    id: str
    workspace_id: str
    project_id: str
    batch_id: str
    module_id: str | None
    test_case_id: str | None
    case_draft_id: str | None
    review_cycle_id: str | None
    title: str
    steps: list[CaseStep]
    priority: str
    risk: str
    tags: list[str]
    custom_fields: dict
    source_row_index: int
    raw_row: dict
    ai_confidence: int
    status: str
    created_at: datetime
    updated_at: datetime


class DraftUpdate(StepValidatorMixin, BaseModel):
    module_id: str | None = None
    title: str | None = Field(default=None, min_length=1, max_length=300)
    steps: list[CaseStep] | None = Field(default=None, max_length=100)
    priority: str | None = Field(default=None, max_length=32)
    risk: str | None = Field(default=None, max_length=80)
    tags: list[str] | None = Field(default=None, max_length=50)
    custom_fields: dict[str, str] | None = None


class BulkDraftUpdate(DraftUpdate):
    draft_ids: list[str] | None = Field(default=None, max_length=500)


class ImportResultResponse(BaseModel):
    batch: ImportBatchResponse
    imported_count: int


