from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field
from sqlalchemy import JSON, DateTime, ForeignKey, Integer, String, select
from sqlalchemy.orm import Mapped, Session, mapped_column

from app.case_domain import CaseDraft, CaseDraftSource, TestCase, TestCaseLifecycle
from app.case_reviews import TestCaseCreate, build_case_response
from app.database import Base
from app.diff_analysis import DiffAnalysis, DiffAnalysisStatus
from app.test_plans import (
    PlanItem,
    PlanItemSource,
    TestPlan,
    add_plan_item,
    get_or_create_release_plan,
    get_plan_or_404,
    plan_item_to_response,
    formal_case_snapshot,
)
from app.workspaces import ActorEmail, audit, get_project_or_404, get_workspace_or_404, new_id, now_utc


class AISuggestionType(StrEnum):
    regression = "regression"
    case_candidate = "case_candidate"


class AISuggestionStatus(StrEnum):
    suggested = "suggested"
    accepted = "accepted"
    ignored = "ignored"
    modified = "modified"


class AISuggestion(Base):
    __tablename__ = "ai_suggestions"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    workspace_id: Mapped[str] = mapped_column(ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False, index=True)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True)
    diff_analysis_id: Mapped[str] = mapped_column(ForeignKey("diff_analyses.id", ondelete="CASCADE"), nullable=False, index=True)
    suggestion_type: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(40), default=AISuggestionStatus.suggested.value, nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(220), nullable=False)
    rationale: Mapped[str] = mapped_column(String(900), nullable=False)
    confidence: Mapped[int] = mapped_column(Integer, default=80, nullable=False)
    module_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    module_key: Mapped[str] = mapped_column(String(80), default="UNMAPPED", nullable=False)
    source_diff: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    mapping_evidence: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    code_paths: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    interfaces: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    config_keys: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    related_case_ids: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    selected_case_ids: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    candidate_payload: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    candidate_case_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    plan_item_ids: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    feedback_history: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list, nullable=False)
    created_by: Mapped[str] = mapped_column(String(254), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc, nullable=False, index=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc, onupdate=now_utc, nullable=False)


class AISuggestionUpdate(BaseModel):
    status: AISuggestionStatus | None = None
    title: str | None = Field(default=None, min_length=1, max_length=220)
    feedback_comment: str | None = Field(default=None, max_length=700)
    selected_case_ids: list[str] | None = None


class AISuggestionPlanItemCreate(BaseModel):
    plan_id: str | None = Field(default=None, max_length=64)
    version_ref: str = Field(default="", max_length=160)
    test_case_ids: list[str] = Field(default_factory=list)
    include_ai_candidate: bool = False


class AISuggestionResponse(BaseModel):
    id: str
    workspace_id: str
    project_id: str
    diff_analysis_id: str
    suggestion_type: str
    status: str
    title: str
    rationale: str
    confidence: int
    module_id: str | None
    module_key: str
    source_diff: dict[str, Any]
    mapping_evidence: list[str]
    code_paths: list[str]
    interfaces: list[str]
    config_keys: list[str]
    related_case_ids: list[str]
    selected_case_ids: list[str]
    candidate_payload: dict[str, Any]
    candidate_case_id: str | None
    plan_item_ids: list[str]
    feedback_history: list[dict[str, Any]]
    created_by: str
    created_at: datetime
    updated_at: datetime


class AISuggestionPlanItemResponse(BaseModel):
    plan: dict[str, Any]
    items: list[dict[str, Any]]
    suggestion: AISuggestionResponse


def get_db(request: Request):
    yield from request.app.state.database.session()


DbSession = Annotated[Session, Depends(get_db)]

router = APIRouter(prefix="/api/workspaces/{workspace_id}/projects/{project_id}", tags=["ai-suggestions"])


def suggestion_to_response(suggestion: AISuggestion) -> AISuggestionResponse:
    return AISuggestionResponse(
        id=suggestion.id,
        workspace_id=suggestion.workspace_id,
        project_id=suggestion.project_id,
        diff_analysis_id=suggestion.diff_analysis_id,
        suggestion_type=suggestion.suggestion_type,
        status=suggestion.status,
        title=suggestion.title,
        rationale=suggestion.rationale,
        confidence=suggestion.confidence,
        module_id=suggestion.module_id,
        module_key=suggestion.module_key,
        source_diff=suggestion.source_diff,
        mapping_evidence=suggestion.mapping_evidence,
        code_paths=suggestion.code_paths,
        interfaces=suggestion.interfaces,
        config_keys=suggestion.config_keys,
        related_case_ids=suggestion.related_case_ids,
        selected_case_ids=suggestion.selected_case_ids,
        candidate_payload=suggestion.candidate_payload,
        candidate_case_id=suggestion.candidate_case_id,
        plan_item_ids=suggestion.plan_item_ids,
        feedback_history=suggestion.feedback_history,
        created_by=suggestion.created_by,
        created_at=suggestion.created_at,
        updated_at=suggestion.updated_at,
    )


def get_diff_analysis_or_404(db: Session, workspace_id: str, project_id: str, analysis_id: str) -> DiffAnalysis:
    analysis = db.scalar(
        select(DiffAnalysis).where(
            DiffAnalysis.id == analysis_id,
            DiffAnalysis.workspace_id == workspace_id,
            DiffAnalysis.project_id == project_id,
        )
    )
    if analysis is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Diff analysis not found")
    return analysis


def get_suggestion_or_404(db: Session, workspace_id: str, project_id: str, suggestion_id: str) -> AISuggestion:
    suggestion = db.scalar(
        select(AISuggestion).where(
            AISuggestion.id == suggestion_id,
            AISuggestion.workspace_id == workspace_id,
            AISuggestion.project_id == project_id,
        )
    )
    if suggestion is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="AI suggestion not found")
    return suggestion


def case_revision_snapshot(db: Session, test_case: TestCase) -> dict[str, Any]:
    if not test_case.current_revision_id:
        return {}
    from app.case_domain import CaseRevision

    revision = db.get(CaseRevision, test_case.current_revision_id)
    return revision.content_snapshot if revision else {}


def related_approved_cases(db: Session, workspace_id: str, project_id: str, module_id: str | None, module_key: str) -> list[TestCase]:
    statement = select(TestCase).where(
        TestCase.workspace_id == workspace_id,
        TestCase.project_id == project_id,
        TestCase.lifecycle_status == TestCaseLifecycle.active.value,
    )
    if module_id:
        statement = statement.where(TestCase.current_module_id == module_id)
    cases = list(db.scalars(statement.order_by(TestCase.updated_at.desc(), TestCase.id.desc())).all())
    if cases or not module_key:
        return cases[:8]
    fallback = db.scalars(
        select(TestCase).where(
            TestCase.workspace_id == workspace_id,
            TestCase.project_id == project_id,
            TestCase.lifecycle_status == TestCaseLifecycle.active.value,
        )
    ).all()
    lowered = module_key.lower()
    matches = []
    for case in fallback:
        snapshot = case_revision_snapshot(db, case)
        haystack = " ".join([str(snapshot.get("title") or ""), *(str(tag) for tag in snapshot.get("tags", []))]).lower()
        if lowered in haystack:
            matches.append(case)
    return matches[:8]


def structure_names(files: list[dict[str, Any]], structure_type: str) -> list[str]:
    names: list[str] = []
    for file in files:
        for item in file.get("structure_changes", []):
            if item.get("type") == structure_type and item.get("name"):
                names.append(str(item["name"]))
    return list(dict.fromkeys(names))


def build_candidate_payload(impact: dict[str, Any], files: list[dict[str, Any]], analysis: DiffAnalysis) -> dict[str, Any]:
    module_key = str(impact.get("module_key") or "UNMAPPED")
    high_signal = "high" if impact.get("risk_level") == "high" else "medium"
    code_paths = [str(file["path"]) for file in files[:5]]
    interfaces = structure_names(files, "api_route")
    config_keys = structure_names(files, "config_key")
    focus = interfaces[0] if interfaces else code_paths[0] if code_paths else module_key
    steps = [
        f"Deploy or checkout target ref {analysis.target_ref}",
        f"Exercise changed surface {focus}",
        "Verify impacted module behavior and rollback-safe side effects",
    ]
    if config_keys:
        steps.append(f"Validate config keys: {', '.join(config_keys[:3])}")
    return {
        "module_id": impact.get("module_id"),
        "title": f"Validate {module_key} changes from {analysis.base_ref} to {analysis.target_ref}",
        "steps": steps,
        "expected_result": f"{module_key} behaves correctly on changed paths without regressions.",
        "priority": "P1" if high_signal == "high" else "P2",
        "risk": high_signal,
        "tags": ["ai-diff", module_key.lower()],
        "custom_fields": {
            "source": "ai_suggestion",
            "diff_analysis_id": analysis.id,
            "code_paths": ", ".join(code_paths),
            "interfaces": ", ".join(interfaces),
            "config_keys": ", ".join(config_keys),
        },
    }


def build_suggestions(db: Session, analysis: DiffAnalysis, actor_email: str) -> list[AISuggestion]:
    existing = db.scalars(select(AISuggestion).where(AISuggestion.diff_analysis_id == analysis.id)).all()
    if existing:
        return list(existing)

    suggestions: list[AISuggestion] = []
    for impact in analysis.module_impacts:
        module_id = impact.get("module_id")
        module_key = str(impact.get("module_key") or "UNMAPPED")
        files = [file for file in analysis.file_changes if (file.get("module_id") or "UNMAPPED") == (module_id or "UNMAPPED")]
        code_paths = [str(file["path"]) for file in files]
        interfaces = structure_names(files, "api_route")
        config_keys = structure_names(files, "config_key")
        mapping_evidence = list(dict.fromkeys(str(entry) for file in files for entry in file.get("evidence", [])))
        related_cases = related_approved_cases(db, analysis.workspace_id, analysis.project_id, module_id, module_key)
        related_case_ids = [case.id for case in related_cases]
        source_diff = {
            "analysis_id": analysis.id,
            "base_ref": analysis.base_ref,
            "target_ref": analysis.target_ref,
            "risk_level": impact.get("risk_level"),
            "changed_file_count": impact.get("changed_file_count"),
        }

        regression = AISuggestion(
            workspace_id=analysis.workspace_id,
            project_id=analysis.project_id,
            diff_analysis_id=analysis.id,
            suggestion_type=AISuggestionType.regression.value,
            title=f"Run {module_key} regression for {analysis.target_ref}",
            rationale=(
                f"{module_key} has {impact.get('changed_file_count')} changed files with {impact.get('risk_level')} risk; "
                "reuse approved cases that cover the impacted module before release."
            ),
            confidence=int(impact.get("confidence") or 70),
            module_id=str(module_id) if module_id else None,
            module_key=module_key,
            source_diff=source_diff,
            mapping_evidence=mapping_evidence,
            code_paths=code_paths,
            interfaces=interfaces,
            config_keys=config_keys,
            related_case_ids=related_case_ids,
            selected_case_ids=related_case_ids,
            created_by=actor_email,
        )
        candidate_payload = build_candidate_payload(impact, files, analysis)
        candidate = AISuggestion(
            workspace_id=analysis.workspace_id,
            project_id=analysis.project_id,
            diff_analysis_id=analysis.id,
            suggestion_type=AISuggestionType.case_candidate.value,
            title=str(candidate_payload["title"]),
            rationale=(
                f"Generate a temporary case because {module_key} changed code/config surfaces "
                f"({', '.join(code_paths[:3])}). It must pass review before entering the formal library."
            ),
            confidence=max(65, int(impact.get("confidence") or 70) - 5),
            module_id=str(module_id) if module_id else None,
            module_key=module_key,
            source_diff=source_diff,
            mapping_evidence=mapping_evidence,
            code_paths=code_paths,
            interfaces=interfaces,
            config_keys=config_keys,
            candidate_payload=candidate_payload,
            created_by=actor_email,
        )
        db.add_all([regression, candidate])
        suggestions.extend([regression, candidate])
    db.flush()
    return suggestions


@router.post("/diff-analyses/{analysis_id}/ai-suggestions", response_model=list[AISuggestionResponse], status_code=status.HTTP_201_CREATED)
def generate_ai_suggestions(
    workspace_id: str,
    project_id: str,
    analysis_id: str,
    db: DbSession,
    actor_email: ActorEmail,
) -> list[AISuggestionResponse]:
    get_workspace_or_404(db, workspace_id)
    get_project_or_404(db, workspace_id, project_id)
    analysis = get_diff_analysis_or_404(db, workspace_id, project_id, analysis_id)
    if analysis.status != DiffAnalysisStatus.succeeded.value:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Diff analysis must succeed before AI suggestions")
    suggestions = build_suggestions(db, analysis, actor_email)
    audit(
        db,
        workspace_id=workspace_id,
        actor_email=actor_email,
        action="ai_suggestions.generated",
        entity_type="DiffAnalysis",
        entity_id=analysis.id,
        summary=f"Generated {len(suggestions)} AI suggestions from diff",
        after={"diff_analysis_id": analysis.id, "suggestion_count": len(suggestions)},
    )
    db.commit()
    return [suggestion_to_response(suggestion) for suggestion in suggestions]


@router.get("/diff-analyses/{analysis_id}/ai-suggestions", response_model=list[AISuggestionResponse])
def list_ai_suggestions(workspace_id: str, project_id: str, analysis_id: str, db: DbSession) -> list[AISuggestionResponse]:
    get_diff_analysis_or_404(db, workspace_id, project_id, analysis_id)
    suggestions = db.scalars(
        select(AISuggestion)
        .where(AISuggestion.workspace_id == workspace_id, AISuggestion.project_id == project_id, AISuggestion.diff_analysis_id == analysis_id)
        .order_by(AISuggestion.created_at, AISuggestion.suggestion_type)
    ).all()
    return [suggestion_to_response(suggestion) for suggestion in suggestions]


@router.patch("/ai-suggestions/{suggestion_id}", response_model=AISuggestionResponse)
def update_ai_suggestion(
    workspace_id: str,
    project_id: str,
    suggestion_id: str,
    payload: AISuggestionUpdate,
    db: DbSession,
    actor_email: ActorEmail,
) -> AISuggestionResponse:
    suggestion = get_suggestion_or_404(db, workspace_id, project_id, suggestion_id)
    if payload.status is not None:
        suggestion.status = payload.status.value
    if payload.title is not None:
        suggestion.title = payload.title
        suggestion.status = AISuggestionStatus.modified.value if payload.status is None else suggestion.status
    if payload.selected_case_ids is not None:
        suggestion.selected_case_ids = payload.selected_case_ids
    if payload.feedback_comment:
        suggestion.feedback_history = [
            *suggestion.feedback_history,
            {"actor_email": actor_email, "comment": payload.feedback_comment, "created_at": now_utc().isoformat()},
        ]
    suggestion.updated_at = now_utc()
    audit(
        db,
        workspace_id=workspace_id,
        actor_email=actor_email,
        action="ai_suggestion.feedback",
        entity_type="AISuggestion",
        entity_id=suggestion.id,
        summary=f"Updated AI suggestion {suggestion.title}",
        after={"status": suggestion.status, "selected_case_ids": suggestion.selected_case_ids},
    )
    db.commit()
    db.refresh(suggestion)
    return suggestion_to_response(suggestion)


@router.post("/ai-suggestions/{suggestion_id}/candidate", response_model=dict, status_code=status.HTTP_201_CREATED)
def create_candidate_from_ai_suggestion(
    workspace_id: str,
    project_id: str,
    suggestion_id: str,
    db: DbSession,
    actor_email: ActorEmail,
) -> dict:
    suggestion = get_suggestion_or_404(db, workspace_id, project_id, suggestion_id)
    if suggestion.suggestion_type != AISuggestionType.case_candidate.value:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Only case_candidate suggestions can create AI cases")
    if suggestion.candidate_case_id:
        test_case = db.get(TestCase, suggestion.candidate_case_id)
        if test_case is not None:
            return {"test_case": build_case_response(db, test_case), "suggestion": suggestion_to_response(suggestion)}

    payload = TestCaseCreate(**suggestion.candidate_payload)
    source_ref = {
        "suggestion_id": suggestion.id,
        "diff_analysis_id": suggestion.diff_analysis_id,
        "source_diff": suggestion.source_diff,
    }
    test_case = TestCase(
        workspace_id=workspace_id,
        project_id=project_id,
        lifecycle_status=TestCaseLifecycle.draft.value,
        source_type=CaseDraftSource.ai_suggestion.value,
        source_ref=source_ref,
        created_by=actor_email,
    )
    db.add(test_case)
    db.flush()
    case_draft = CaseDraft(
        workspace_id=workspace_id,
        project_id=project_id,
        test_case_id=test_case.id,
        module_id=payload.module_id,
        title=payload.title,
        steps=payload.steps,
        expected_result=payload.expected_result,
        priority=payload.priority,
        risk=payload.risk,
        tags=payload.tags,
        custom_fields=payload.custom_fields,
        source_type=CaseDraftSource.ai_suggestion.value,
        source_ref=source_ref,
        created_by=actor_email,
        updated_by=actor_email,
    )
    db.add(case_draft)
    db.flush()
    suggestion.candidate_case_id = test_case.id
    suggestion.status = AISuggestionStatus.accepted.value
    suggestion.updated_at = now_utc()
    audit(
        db,
        workspace_id=workspace_id,
        actor_email=actor_email,
        action="ai_candidate.created",
        entity_type="TestCase",
        entity_id=test_case.id,
        summary=f"Created draft AI candidate {case_draft.title}",
        after={"suggestion_id": suggestion.id, "draft_id": case_draft.id, "lifecycle_status": test_case.lifecycle_status},
    )
    db.commit()
    db.refresh(test_case)
    db.refresh(suggestion)
    return {"test_case": build_case_response(db, test_case), "suggestion": suggestion_to_response(suggestion)}


@router.post("/ai-suggestions/{suggestion_id}/plan-items", response_model=AISuggestionPlanItemResponse, status_code=status.HTTP_201_CREATED)
def create_plan_items_from_ai_suggestion(
    workspace_id: str,
    project_id: str,
    suggestion_id: str,
    payload: AISuggestionPlanItemCreate,
    db: DbSession,
    actor_email: ActorEmail,
) -> AISuggestionPlanItemResponse:
    suggestion = get_suggestion_or_404(db, workspace_id, project_id, suggestion_id)
    plan: TestPlan
    if payload.plan_id:
        plan = get_plan_or_404(db, workspace_id, project_id, payload.plan_id)
    else:
        version_ref = payload.version_ref or str(suggestion.source_diff.get("target_ref") or "")
        plan = get_or_create_release_plan(
            db,
            workspace_id=workspace_id,
            project_id=project_id,
            actor_email=actor_email,
            version_ref=version_ref,
            scope_summary=f"AI suggestions from diff {suggestion.diff_analysis_id}",
        )

    items: list[PlanItem] = []
    for case_id in payload.test_case_ids or suggestion.selected_case_ids:
        test_case = db.get(TestCase, case_id)
        if test_case is None or test_case.workspace_id != workspace_id or test_case.project_id != project_id:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Test case not found: {case_id}")
        if test_case.lifecycle_status != TestCaseLifecycle.active.value or not test_case.current_revision_id:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Only approved formal cases can be selected for regression")
        snapshot = formal_case_snapshot(db, test_case)
        items.append(
            add_plan_item(
                db,
                plan=plan,
                source_type=PlanItemSource.formal_case,
                source_id=test_case.id,
                title=str(snapshot.get("title") or "Formal case"),
                snapshot=snapshot,
                rationale=f"{suggestion.title}: {suggestion.rationale}",
                actor_email=actor_email,
            )
        )

    if payload.include_ai_candidate:
        items.append(
            add_plan_item(
                db,
                plan=plan,
                source_type=PlanItemSource.ai_temp,
                source_id=suggestion.id,
                title=suggestion.title,
                snapshot=suggestion.candidate_payload or {
                    "title": suggestion.title,
                    "code_paths": suggestion.code_paths,
                    "interfaces": suggestion.interfaces,
                    "config_keys": suggestion.config_keys,
                },
                rationale=f"Temporary AI plan item from suggestion {suggestion.id}; formal library entry requires review approval.",
                actor_email=actor_email,
            )
        )

    if not items:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="No plan items requested")

    suggestion.plan_item_ids = [*suggestion.plan_item_ids, *(item.id for item in items)]
    suggestion.status = AISuggestionStatus.accepted.value
    suggestion.updated_at = now_utc()
    plan.updated_at = now_utc()
    audit(
        db,
        workspace_id=workspace_id,
        actor_email=actor_email,
        action="ai_suggestion.plan_items_created",
        entity_type="AISuggestion",
        entity_id=suggestion.id,
        summary=f"Added {len(items)} AI suggestion items to {plan.name}",
        after={"plan_id": plan.id, "plan_item_ids": [item.id for item in items]},
    )
    db.commit()
    db.refresh(plan)
    db.refresh(suggestion)
    for item in items:
        db.refresh(item)
    return {
        "plan": {
            "id": plan.id,
            "name": plan.name,
            "plan_type": plan.plan_type,
            "status": plan.status,
            "version_ref": plan.version_ref,
        },
        "items": [plan_item_to_response(item).model_dump(mode="json") for item in items],
        "suggestion": suggestion_to_response(suggestion),
    }
