from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field
from sqlalchemy import Boolean, DateTime, ForeignKey, JSON, String
from sqlalchemy.orm import Mapped, mapped_column

from app.cases.domain import CaseDraftSource
from app.platform.database import Base
from app.workspace.routes import new_id, now_utc


class ReviewAction(StrEnum):
    submitted = "submitted"
    approved = "approved"
    rejected = "rejected"
    changes_requested = "changes_requested"
    changes_addressed = "changes_addressed"
    commented = "commented"


class WorkspaceReviewSettings(Base):
    __tablename__ = "workspace_review_settings"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    workspace_id: Mapped[str] = mapped_column(ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False, unique=True, index=True)
    allow_self_review: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    require_review_on_case_update: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    allow_direct_revision_for_active_case: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    direct_revision_roles: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    updated_by: Mapped[str] = mapped_column(String(254), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc, onupdate=now_utc, nullable=False)


class ReviewSettingsUpdate(BaseModel):
    allow_self_review: bool = False
    require_review_on_case_update: bool = True
    allow_direct_revision_for_active_case: bool = False
    direct_revision_roles: list[str] = Field(default_factory=list, max_length=5)


class ReviewSettingsResponse(BaseModel):
    id: str
    workspace_id: str
    allow_self_review: bool
    require_review_on_case_update: bool
    allow_direct_revision_for_active_case: bool
    direct_revision_roles: list[str]
    updated_by: str
    created_at: datetime
    updated_at: datetime


class TestCaseCreate(BaseModel):
    module_id: str | None = None
    title: str = Field(min_length=1, max_length=300)
    steps: list[str] = Field(default_factory=list, max_length=100)
    expected_result: str = Field(default="", max_length=2000)
    priority: str = Field(default="P2", max_length=32)
    risk: str = Field(default="medium", max_length=80)
    tags: list[str] = Field(default_factory=list, max_length=50)
    custom_fields: dict[str, Any] = Field(default_factory=dict)
    source_type: CaseDraftSource = CaseDraftSource.manual
    source_ref: dict[str, Any] = Field(default_factory=dict)


class CaseDraftUpdate(BaseModel):
    module_id: str | None = None
    title: str | None = Field(default=None, min_length=1, max_length=300)
    steps: list[str] | None = Field(default=None, max_length=100)
    expected_result: str | None = Field(default=None, max_length=2000)
    priority: str | None = Field(default=None, max_length=32)
    risk: str | None = Field(default=None, max_length=80)
    tags: list[str] | None = Field(default=None, max_length=50)
    custom_fields: dict[str, Any] | None = None


class ReviewRequest(BaseModel):
    action: ReviewAction
    comment: str = Field(default="", max_length=1000)
    edits: CaseDraftUpdate | None = None


class ReviewCommentRequest(BaseModel):
    comment: str = Field(min_length=1, max_length=1000)


class ChangeAddressedRequest(BaseModel):
    comment: str = Field(min_length=1, max_length=1000)
    diff_summary: dict[str, Any] = Field(default_factory=dict)


class DirectRevisionRequest(CaseDraftUpdate):
    change_summary: str = Field(min_length=1, max_length=500)
