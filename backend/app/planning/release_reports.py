from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from pydantic import BaseModel, Field
from sqlalchemy import JSON, DateTime, ForeignKey, String, select
from sqlalchemy.orm import Mapped, Session, mapped_column

from app.platform.database import Base
from app.planning.test_plans import PlanItem, PlanItemStatus, TestPlan, get_plan_or_404
from app.workspace.routes import ActorEmail, audit, get_project_or_404, get_workspace_or_404, new_id, now_utc


class ReleaseReportStatus(StrEnum):
    draft = "draft"
    confirmed = "confirmed"


class ReleaseReport(Base):
    __tablename__ = "release_reports"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    workspace_id: Mapped[str] = mapped_column(ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False, index=True)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True)
    plan_id: Mapped[str] = mapped_column(ForeignKey("test_plans.id", ondelete="CASCADE"), nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(220), nullable=False)
    status: Mapped[str] = mapped_column(String(40), default=ReleaseReportStatus.draft.value, nullable=False, index=True)
    version_ref: Mapped[str] = mapped_column(String(160), default="", nullable=False)
    sections: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    ai_notes: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    release_suggestion: Mapped[str] = mapped_column(String(80), default="pending_review", nullable=False)
    release_decision: Mapped[str] = mapped_column(String(80), default="pending_owner_confirmation", nullable=False)
    decision_comment: Mapped[str] = mapped_column(String(1000), default="", nullable=False)
    confirmed_by: Mapped[str | None] = mapped_column(String(254), nullable=True)
    confirmed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_by: Mapped[str] = mapped_column(String(254), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc, nullable=False, index=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc, onupdate=now_utc, nullable=False)


class ReleaseReportDecisionUpdate(BaseModel):
    release_decision: str = Field(min_length=1, max_length=80)
    decision_comment: str = Field(default="", max_length=1000)


class ReleaseReportResponse(BaseModel):
    id: str
    workspace_id: str
    project_id: str
    plan_id: str
    title: str
    status: str
    version_ref: str
    sections: dict[str, Any]
    ai_notes: list[str]
    release_suggestion: str
    release_decision: str
    decision_comment: str
    confirmed_by: str | None
    confirmed_at: datetime | None
    created_by: str
    created_at: datetime
    updated_at: datetime


def get_db(request: Request):
    yield from request.app.state.database.session()


DbSession = Annotated[Session, Depends(get_db)]

router = APIRouter(prefix="/api/workspaces/{workspace_id}/projects/{project_id}", tags=["release-reports"])


def report_to_response(report: ReleaseReport) -> ReleaseReportResponse:
    return ReleaseReportResponse(
        id=report.id,
        workspace_id=report.workspace_id,
        project_id=report.project_id,
        plan_id=report.plan_id,
        title=report.title,
        status=report.status,
        version_ref=report.version_ref,
        sections=report.sections,
        ai_notes=report.ai_notes,
        release_suggestion=report.release_suggestion,
        release_decision=report.release_decision,
        decision_comment=report.decision_comment,
        confirmed_by=report.confirmed_by,
        confirmed_at=report.confirmed_at,
        created_by=report.created_by,
        created_at=report.created_at,
        updated_at=report.updated_at,
    )


def get_report_or_404(db: Session, workspace_id: str, project_id: str, report_id: str) -> ReleaseReport:
    report = db.scalar(
        select(ReleaseReport).where(
            ReleaseReport.id == report_id,
            ReleaseReport.workspace_id == workspace_id,
            ReleaseReport.project_id == project_id,
        )
    )
    if report is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Release report not found")
    return report


def plan_items(db: Session, plan: TestPlan) -> list[PlanItem]:
    return list(
        db.scalars(
            select(PlanItem)
            .where(PlanItem.workspace_id == plan.workspace_id, PlanItem.project_id == plan.project_id, PlanItem.plan_id == plan.id)
            .order_by(PlanItem.created_at, PlanItem.id)
        )
    )


def build_report_sections(plan: TestPlan, items: list[PlanItem]) -> tuple[dict[str, Any], list[str], str]:
    counts = {PlanItemStatus.not_run.value: 0, PlanItemStatus.passed.value: 0, PlanItemStatus.failed.value: 0, PlanItemStatus.blocked.value: 0, PlanItemStatus.skipped.value: 0}
    for item in items:
        status_value = item.status if item.status in counts else PlanItemStatus.not_run.value
        counts[status_value] += 1

    failed_blocked = [item for item in items if item.status in {PlanItemStatus.failed.value, PlanItemStatus.blocked.value}]
    untested = [item for item in items if item.status in {PlanItemStatus.not_run.value, PlanItemStatus.skipped.value, "todo", "in_progress"}]
    tested = [item for item in items if item.status in {PlanItemStatus.passed.value, PlanItemStatus.failed.value, PlanItemStatus.blocked.value}]
    total = len(items)
    recorded = counts[PlanItemStatus.passed.value] + counts[PlanItemStatus.failed.value] + counts[PlanItemStatus.blocked.value] + counts[PlanItemStatus.skipped.value]
    completion_rate = round((recorded / total) * 100) if total else 0
    has_release_blocker = counts[PlanItemStatus.failed.value] > 0 or counts[PlanItemStatus.blocked.value] > 0
    suggestion = "hold_release" if has_release_blocker else "approve_release"
    if not total or counts[PlanItemStatus.not_run.value] > 0:
        suggestion = "conditional_release"

    failed_blocked_rows = [
        {
            "id": item.id,
            "title": item.title,
            "status": item.status,
            "assignee_email": item.assignee_email,
            "actual_result": item.actual_result,
            "failure_reason": item.failure_reason,
            "defect_links": item.defect_links,
            "evidence_count": len(item.evidence),
        }
        for item in failed_blocked
    ]
    appendix_items = [
        {
            "id": item.id,
            "title": item.title,
            "source_type": item.source_type,
            "status": item.status,
            "assignee_email": item.assignee_email,
            "executed_by": item.executed_by,
            "executed_at": item.executed_at.isoformat() if item.executed_at else None,
            "evidence": [{"file_name": evidence.get("file_name"), "note": evidence.get("note")} for evidence in item.evidence],
        }
        for item in items
    ]
    ai_notes = [
        f"AI draft summary: {recorded}/{total} plan items have recorded outcomes; failed={counts[PlanItemStatus.failed.value]}, blocked={counts[PlanItemStatus.blocked.value]}.",
        "AI release suggestion: hold release until failed or blocked items are resolved." if has_release_blocker else "AI release suggestion: release risk is acceptable if owner confirms scope coverage.",
    ]
    sections = {
        "summary": {
            "text": f"{plan.name} covers {total} planned item(s) for {plan.version_ref or 'an unspecified version'} with {completion_rate}% execution recorded.",
            "tested": [item.title for item in tested],
            "not_tested": [item.title for item in untested],
        },
        "version_diff": {
            "version_ref": plan.version_ref,
            "diff_summary": "No DiffAnalysis is directly linked to this plan in MVP storage; include linked AI suggestion or changed-code evidence in appendix when available.",
        },
        "scope": {
            "scope_summary": plan.scope_summary,
            "plan_type": plan.plan_type,
            "items": [{"title": item.title, "source_type": item.source_type, "rationale": item.rationale} for item in items],
        },
        "execution_statistics": {"total": total, "recorded": recorded, "completion_rate": completion_rate, "counts": counts},
        "failed_blocked_items": failed_blocked_rows,
        "risk_assessment": {
            "risk_level": "high" if has_release_blocker else "medium" if untested else "low",
            "risk_acceptable": not has_release_blocker,
            "text": "Release risk is not acceptable while failed or blocked plan items remain." if has_release_blocker else "No failed or blocked items are currently recorded.",
        },
        "ai_notes": ai_notes,
        "release_decision": {
            "owner_required": True,
            "current_decision": "pending_owner_confirmation",
            "suggestion": suggestion,
        },
        "appendix": {"items": appendix_items},
    }
    return sections, ai_notes, suggestion


def render_markdown(report: ReleaseReport) -> str:
    sections = report.sections
    stats = sections.get("execution_statistics", {})
    counts = stats.get("counts", {})
    failed_blocked = sections.get("failed_blocked_items", [])
    appendix = sections.get("appendix", {}).get("items", [])
    scope_items = sections.get("scope", {}).get("items", [])

    lines = [
        f"# {report.title}",
        "",
        "## Summary",
        str(sections.get("summary", {}).get("text", "")),
        "",
        "## Version & Diff",
        f"- Version: {sections.get('version_diff', {}).get('version_ref') or 'n/a'}",
        f"- Diff: {sections.get('version_diff', {}).get('diff_summary', '')}",
        "",
        "## Scope",
        str(sections.get("scope", {}).get("scope_summary", "")),
    ]
    lines.extend(f"- {item.get('title')} ({item.get('source_type')}): {item.get('rationale') or 'no rationale'}" for item in scope_items)
    lines.extend(
        [
            "",
            "## Execution Statistics",
            f"- Total: {stats.get('total', 0)}",
            f"- Recorded: {stats.get('recorded', 0)}",
            f"- Completion: {stats.get('completion_rate', 0)}%",
            f"- Passed / Failed / Blocked / Skipped / Not Run: {counts.get('passed', 0)} / {counts.get('failed', 0)} / {counts.get('blocked', 0)} / {counts.get('skipped', 0)} / {counts.get('not_run', 0)}",
            "",
            "## Failed / Blocked Items",
        ]
    )
    if failed_blocked:
        for item in failed_blocked:
            links = ", ".join(item.get("defect_links", [])) or "no defects linked"
            lines.append(f"- {item.get('title')} [{item.get('status')}]: {item.get('failure_reason') or item.get('actual_result') or 'no result'}; defects: {links}; evidence: {item.get('evidence_count', 0)}")
    else:
        lines.append("- None")
    lines.extend(
        [
            "",
            "## Risk Assessment",
            f"- Level: {sections.get('risk_assessment', {}).get('risk_level', 'unknown')}",
            f"- Acceptable: {sections.get('risk_assessment', {}).get('risk_acceptable', False)}",
            f"- Notes: {sections.get('risk_assessment', {}).get('text', '')}",
            "",
            "## AI Notes",
        ]
    )
    lines.extend(f"- {note}" for note in report.ai_notes)
    lines.extend(
        [
            "",
            "## Release Decision",
            f"- AI suggestion: {report.release_suggestion}",
            f"- Owner decision: {report.release_decision}",
            f"- Decision comment: {report.decision_comment or 'pending'}",
            f"- Confirmed by: {report.confirmed_by or 'pending'}",
            "",
            "## Appendix",
        ]
    )
    lines.extend(f"- {item.get('title')} [{item.get('status')}] assignee={item.get('assignee_email') or 'unassigned'} evidence={len(item.get('evidence', []))}" for item in appendix)
    return "\n".join(lines).strip() + "\n"


@router.get("/plans/{plan_id}/reports", response_model=list[ReleaseReportResponse])
def list_release_reports(workspace_id: str, project_id: str, plan_id: str, db: DbSession) -> list[ReleaseReportResponse]:
    get_plan_or_404(db, workspace_id, project_id, plan_id)
    reports = db.scalars(
        select(ReleaseReport)
        .where(ReleaseReport.workspace_id == workspace_id, ReleaseReport.project_id == project_id, ReleaseReport.plan_id == plan_id)
        .order_by(ReleaseReport.created_at.desc(), ReleaseReport.id.desc())
    ).all()
    return [report_to_response(report) for report in reports]


@router.post("/plans/{plan_id}/reports/draft", response_model=ReleaseReportResponse, status_code=status.HTTP_201_CREATED)
def create_release_report_draft(
    workspace_id: str,
    project_id: str,
    plan_id: str,
    db: DbSession,
    actor_email: ActorEmail,
) -> ReleaseReportResponse:
    get_workspace_or_404(db, workspace_id)
    get_project_or_404(db, workspace_id, project_id)
    plan = get_plan_or_404(db, workspace_id, project_id, plan_id)
    items = plan_items(db, plan)
    sections, ai_notes, suggestion = build_report_sections(plan, items)
    report = ReleaseReport(
        workspace_id=workspace_id,
        project_id=project_id,
        plan_id=plan.id,
        title=f"Release Test Report - {plan.name}",
        version_ref=plan.version_ref,
        sections=sections,
        ai_notes=ai_notes,
        release_suggestion=suggestion,
        created_by=actor_email,
    )
    db.add(report)
    db.flush()
    audit(
        db,
        workspace_id=workspace_id,
        actor_email=actor_email,
        action="release_report.draft_generated",
        entity_type="ReleaseReport",
        entity_id=report.id,
        summary=f"Generated release report draft for {plan.name}",
        after={"plan_id": plan.id, "release_suggestion": suggestion, "status": report.status},
    )
    db.commit()
    db.refresh(report)
    return report_to_response(report)


@router.get("/reports/{report_id}", response_model=ReleaseReportResponse)
def get_release_report(workspace_id: str, project_id: str, report_id: str, db: DbSession) -> ReleaseReportResponse:
    return report_to_response(get_report_or_404(db, workspace_id, project_id, report_id))


@router.patch("/reports/{report_id}/decision", response_model=ReleaseReportResponse)
def confirm_release_report_decision(
    workspace_id: str,
    project_id: str,
    report_id: str,
    payload: ReleaseReportDecisionUpdate,
    db: DbSession,
    actor_email: ActorEmail,
) -> ReleaseReportResponse:
    report = get_report_or_404(db, workspace_id, project_id, report_id)
    before = {"status": report.status, "release_decision": report.release_decision, "decision_comment": report.decision_comment}
    report.status = ReleaseReportStatus.confirmed.value
    report.release_decision = payload.release_decision
    report.decision_comment = payload.decision_comment
    report.confirmed_by = actor_email
    report.confirmed_at = now_utc()
    report.updated_at = report.confirmed_at
    report.sections = {
        **report.sections,
        "release_decision": {
            **report.sections.get("release_decision", {}),
            "current_decision": report.release_decision,
            "decision_comment": report.decision_comment,
            "confirmed_by": actor_email,
            "confirmed_at": report.confirmed_at.isoformat(),
        },
    }
    audit(
        db,
        workspace_id=workspace_id,
        actor_email=actor_email,
        action="release_report.decision_confirmed",
        entity_type="ReleaseReport",
        entity_id=report.id,
        summary=f"Confirmed release decision {report.release_decision}",
        before=before,
        after={"status": report.status, "release_decision": report.release_decision, "decision_comment": report.decision_comment},
    )
    db.commit()
    db.refresh(report)
    return report_to_response(report)


@router.get("/reports/{report_id}/markdown")
def export_release_report_markdown(workspace_id: str, project_id: str, report_id: str, db: DbSession) -> Response:
    report = get_report_or_404(db, workspace_id, project_id, report_id)
    filename = f"{report.title.lower().replace(' ', '-')}.md"
    return Response(
        render_markdown(report),
        media_type="text/markdown; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
