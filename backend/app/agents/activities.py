from __future__ import annotations

import subprocess
from collections import Counter
from pathlib import Path
from typing import Any

from sqlalchemy import select
from temporalio import activity

from app.agents import (
    AgentRun,
    AgentRunStateError,
    AgentRunStatus,
    apply_agent_run_budget_override,
    mark_run_cancelled,
    mark_run_failed,
)
from app.platform.config import Settings
from app.platform.database import Database
from app.platform.telemetry import agent_span
from app.cases.step_models import steps_expected_text
from app.workspace.routes import audit


TEMPORAL_CHILD_RESULT_LIMIT = 8
TEMPORAL_CHILD_RESULT_TEXT_LIMIT = 500
TEMPORAL_CHILD_RESULT_METADATA_KEYS = {
    "repository_id",
    "project_id",
    "ref",
    "resolved_ref",
    "file_count",
    "top_extensions",
    "top_directories",
    "batch_count",
    "draft_count",
    "row_count",
    "status_counts",
    "file_type_counts",
    "risk_counts",
    "priority_counts",
    "unmapped_draft_count",
    "missing_steps_count",
    "missing_expected_result_count",
    "average_ai_confidence",
}


def _child_result_text(value: Any, *, limit: int = TEMPORAL_CHILD_RESULT_TEXT_LIMIT) -> str:
    return str(value or "")[:limit]


def _metadata_value(value: Any) -> Any:
    if isinstance(value, bool) or value is None:
        return value
    if isinstance(value, (int, float)):
        return value
    if isinstance(value, str):
        return _child_result_text(value)
    if isinstance(value, dict):
        return {
            _child_result_text(key, limit=80): _metadata_value(nested)
            for key, nested in list(value.items())[:TEMPORAL_CHILD_RESULT_LIMIT]
        }
    if isinstance(value, list):
        return [_metadata_value(item) for item in value[:TEMPORAL_CHILD_RESULT_LIMIT]]
    return _child_result_text(value)


def _child_result_metadata(raw: dict[str, Any]) -> dict[str, Any]:
    metadata: dict[str, Any] = {}
    for key in TEMPORAL_CHILD_RESULT_METADATA_KEYS:
        if key in raw:
            metadata[key] = _metadata_value(raw[key])
    return metadata


def _sanitize_temporal_child_results(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    sanitized: list[dict[str, Any]] = []
    for raw in value[:TEMPORAL_CHILD_RESULT_LIMIT]:
        if not isinstance(raw, dict):
            continue
        task_kind = _child_result_text(raw.get("task_kind") or raw.get("kind"), limit=80)
        if not task_kind:
            continue
        sanitized.append(
            {
                "status": _child_result_text(raw.get("status") or "unknown", limit=40),
                "task_kind": task_kind,
                "parent_run_id": _child_result_text(raw.get("parent_run_id") or raw.get("run_id"), limit=80),
                "workflow_id": _child_result_text(raw.get("workflow_id"), limit=160),
                "summary": _child_result_text(raw.get("summary")),
            }
        )
        metadata = _child_result_metadata(raw)
        if metadata:
            sanitized[-1]["metadata"] = metadata
    return sanitized


def _child_activity_failure(payload: dict[str, Any], reason: str) -> dict[str, Any]:
    task_kind = _child_result_text(payload.get("task_kind") or payload.get("kind") or "agent_child_task", limit=80)
    return {
        "status": "failed",
        "task_kind": task_kind,
        "parent_run_id": _child_result_text(payload.get("parent_run_id") or payload.get("run_id"), limit=80),
        "summary": reason[:TEMPORAL_CHILD_RESULT_TEXT_LIMIT],
    }


def _child_payload_map(payload: dict[str, Any]) -> dict[str, Any]:
    raw_payload = payload.get("payload")
    return raw_payload if isinstance(raw_payload, dict) else {}


def _child_timeout_seconds(value: Any, default_seconds: int) -> int:
    try:
        return max(1, min(int(value), 120))
    except (TypeError, ValueError):
        return default_seconds


def _run_child_git(command: list[str], timeout_seconds: int) -> subprocess.CompletedProcess[str]:
    return subprocess.run(command, capture_output=True, check=False, text=True, timeout=timeout_seconds)


def _scan_repository_child_task(payload: dict[str, Any], *, settings: Settings) -> dict[str, Any]:
    from app.git.models import GitRepository, RepositoryStatus
    from app.git.sandbox import ensure_safe_sandbox_path

    database = Database(settings.database_url)
    database.init()
    with database.session_factory() as db:
        repository = db.get(GitRepository, payload.get("repository_id"))
        if repository is None or repository.workspace_id != payload.get("workspace_id"):
            return _child_activity_failure(payload, "Repository not found for child scan")
        if repository.status != RepositoryStatus.synced.value:
            return _child_activity_failure(payload, "Repository must be synced before child scan")

        try:
            root = Path(settings.git_sandbox_root).expanduser()
            mirror_path = ensure_safe_sandbox_path(root, Path(repository.mirror_path))
        except ValueError as exc:
            return _child_activity_failure(payload, str(exc))
        if not mirror_path.exists():
            return _child_activity_failure(payload, "Repository mirror is missing")

        task_payload = _child_payload_map(payload)
        requested_ref = str(payload.get("ref") or task_payload.get("ref") or repository.default_branch)
        timeout_seconds = _child_timeout_seconds(task_payload.get("timeout_seconds"), min(repository.sync_timeout_seconds, 60))
        try:
            rev_parse = _run_child_git(
                ["git", "--git-dir", str(mirror_path), "rev-parse", "--verify", f"{requested_ref}^{{commit}}"],
                timeout_seconds,
            )
            if rev_parse.returncode != 0:
                detail = rev_parse.stderr.strip()[:300] or f"ref {requested_ref} is not available"
                return _child_activity_failure(payload, detail)
            resolved_ref = rev_parse.stdout.strip()
            if activity.in_activity():
                activity.heartbeat({"phase": "child_repo_scan_resolved_ref", "ref": requested_ref})
            ls_tree = _run_child_git(
                ["git", "--git-dir", str(mirror_path), "ls-tree", "-r", "--name-only", resolved_ref],
                timeout_seconds,
            )
            if ls_tree.returncode != 0:
                detail = ls_tree.stderr.strip()[:300] or "Unable to list repository tree"
                return _child_activity_failure(payload, detail)
        except subprocess.TimeoutExpired:
            return _child_activity_failure(payload, "Repository child scan timed out")

    paths = [line.strip() for line in ls_tree.stdout.splitlines() if line.strip()]
    extensions = Counter((Path(path).suffix.lower() or "[no_ext]") for path in paths)
    directories = Counter(path.split("/", 1)[0] if "/" in path else "." for path in paths)
    top_extensions = [{"extension": extension, "count": count} for extension, count in extensions.most_common(8)]
    top_directories = [{"directory": directory, "count": count} for directory, count in directories.most_common(8)]
    extension_summary = ", ".join(f"{item['extension']} {item['count']}" for item in top_extensions[:4]) or "no files"
    return {
        "status": "succeeded",
        "task_kind": "large_repo_scan",
        "parent_run_id": _child_result_text(payload.get("parent_run_id") or payload.get("run_id"), limit=80),
        "repository_id": str(payload.get("repository_id") or ""),
        "project_id": str(payload.get("project_id") or ""),
        "ref": requested_ref,
        "resolved_ref": resolved_ref,
        "file_count": len(paths),
        "top_extensions": top_extensions,
        "top_directories": top_directories,
        "summary": f"Scanned {len(paths)} repository files at {resolved_ref[:12]}; top extensions: {extension_summary}",
    }


def _top_counts(values: list[str], *, default: str = "unknown") -> list[dict[str, Any]]:
    counter = Counter(value or default for value in values)
    return [{"value": value, "count": count} for value, count in counter.most_common(8)]


def _analyze_import_child_task(payload: dict[str, Any], *, settings: Settings) -> dict[str, Any]:
    from app.cases.imports import ImportBatch, ImportCaseDraft

    database = Database(settings.database_url)
    database.init()
    with database.session_factory() as db:
        run = db.get(AgentRun, payload.get("parent_run_id") or payload.get("run_id"))
        if run is None or run.workspace_id != payload.get("workspace_id"):
            return _child_activity_failure(payload, "Agent run not found for import analysis")

        task_payload = _child_payload_map(payload)
        project_id = str(payload.get("project_id") or task_payload.get("project_id") or run.project_id or "")
        if not project_id:
            return _child_activity_failure(payload, "Agent run has no project for import analysis")

        batch_id = str(task_payload.get("batch_id") or "")
        try:
            batch_limit = max(1, min(int(task_payload.get("batch_limit") or 10), 50))
        except (TypeError, ValueError):
            batch_limit = 10

        batch_statement = select(ImportBatch).where(ImportBatch.workspace_id == run.workspace_id, ImportBatch.project_id == project_id)
        if batch_id:
            batch_statement = batch_statement.where(ImportBatch.id == batch_id)
        batches = db.scalars(batch_statement.order_by(ImportBatch.created_at.desc(), ImportBatch.id.desc()).limit(batch_limit)).all()
        batch_ids = [batch.id for batch in batches]
        drafts = (
            db.scalars(
                select(ImportCaseDraft)
                .where(ImportCaseDraft.workspace_id == run.workspace_id, ImportCaseDraft.project_id == project_id)
                .where(ImportCaseDraft.batch_id.in_(batch_ids))
            ).all()
            if batch_ids
            else []
        )

    row_count = sum(batch.row_count for batch in batches)
    draft_count = len(drafts)
    confidence_values = [draft.ai_confidence for draft in drafts]
    average_confidence = round(sum(confidence_values) / len(confidence_values), 1) if confidence_values else 0
    unmapped_count = sum(1 for draft in drafts if not draft.module_id)
    missing_steps_count = sum(1 for draft in drafts if not draft.steps)
    missing_expected_count = sum(1 for draft in drafts if not (draft.expected_result or "").strip() and not steps_expected_text(draft.steps))
    status_counts = {item["value"]: item["count"] for item in _top_counts([batch.status for batch in batches])}
    file_type_counts = {item["value"]: item["count"] for item in _top_counts([batch.file_type for batch in batches])}
    risk_counts = {item["value"]: item["count"] for item in _top_counts([draft.risk for draft in drafts])}
    priority_counts = {item["value"]: item["count"] for item in _top_counts([draft.priority for draft in drafts])}
    if batches:
        summary = (
            f"Analyzed {len(batches)} import batch(es), {row_count} raw row(s), {draft_count} draft(s); "
            f"{unmapped_count} unmapped, {missing_steps_count} missing steps"
        )
    else:
        summary = "No import batches found for this project"
    return {
        "status": "succeeded",
        "task_kind": "large_import_analysis",
        "parent_run_id": _child_result_text(payload.get("parent_run_id") or payload.get("run_id"), limit=80),
        "project_id": project_id,
        "batch_count": len(batches),
        "draft_count": draft_count,
        "row_count": row_count,
        "status_counts": status_counts,
        "file_type_counts": file_type_counts,
        "risk_counts": risk_counts,
        "priority_counts": priority_counts,
        "unmapped_draft_count": unmapped_count,
        "missing_steps_count": missing_steps_count,
        "missing_expected_result_count": missing_expected_count,
        "average_ai_confidence": average_confidence,
        "summary": summary,
    }


def execute_agent_child_task_activity_with_settings(payload: dict[str, Any], *, settings: Settings) -> dict[str, Any]:
    task_kind = str(payload.get("task_kind") or payload.get("kind") or "agent_child_task")
    with agent_span(
        "temporal.activity",
        temporal_activity="execute_agent_child_task",
        run_id=str(payload.get("parent_run_id") or payload.get("run_id") or ""),
        task_kind=task_kind[:80],
    ):
        if task_kind == "large_repo_scan":
            return _scan_repository_child_task(payload, settings=settings)
        if task_kind == "large_import_analysis":
            return _analyze_import_child_task(payload, settings=settings)
        return {
            "status": "succeeded",
            "task_kind": task_kind[:80],
            "parent_run_id": _child_result_text(payload.get("parent_run_id") or payload.get("run_id"), limit=80),
            "summary": _child_result_text(payload.get("summary") or f"Completed child task {task_kind}"),
        }


@activity.defn
def execute_agent_child_task_activity(payload: dict[str, Any]) -> dict[str, Any]:
    return execute_agent_child_task_activity_with_settings(payload, settings=Settings())


def persist_temporal_child_results(
    db,
    *,
    run: AgentRun,
    workspace_id: str,
    actor_email: str,
    payload: dict[str, Any],
) -> list[dict[str, Any]]:
    child_results = _sanitize_temporal_child_results(payload.get("child_results"))
    if not child_results:
        return []

    before = dict(run.budget_snapshot or {})
    if before.get("temporal_child_results") == child_results:
        return child_results

    after = dict(before)
    after["temporal_child_results"] = child_results
    run.budget_snapshot = after
    audit(
        db,
        workspace_id=workspace_id,
        actor_email=actor_email,
        action="agent_run.child_tasks_completed",
        entity_type="AgentRun",
        entity_id=run.id,
        summary=f"Persisted {len(child_results)} Temporal child task result(s)",
        before={"temporal_child_results": before.get("temporal_child_results")},
        after={"temporal_child_results": child_results},
    )
    return child_results


def _activity_checkpoint(phase: str) -> None:
    if not activity.in_activity():
        return
    activity.heartbeat({"phase": phase})
    if activity.is_cancelled():
        from app.agents.graph import AgentRunCancelled

        raise AgentRunCancelled("Temporal cancellation requested")


def _activity_result_from_run(run: AgentRun, summary: str | None = None) -> dict[str, Any]:
    return {
        "run_id": run.id,
        "status": run.status,
        "summary": summary or run.failure_reason or f"Agent run is {run.status}",
        "staged_output_count": 0,
    }


def execute_agent_graph_activity_with_settings(
    payload: dict[str, Any],
    *,
    settings: Settings,
) -> dict[str, Any]:
    from app.agents.graph import AgentGraphConflict, execute_agent_graph

    with agent_span(
        "temporal.activity",
        temporal_activity="execute_agent_graph",
        run_id=str(payload.get("run_id") or ""),
        explicit_resume=bool(payload.get("explicit_resume")),
    ):
        database = Database(settings.database_url)
        database.init()
        with database.session_factory() as db:
            run = db.get(AgentRun, payload["run_id"])
            if run is None or run.workspace_id != payload["workspace_id"]:
                raise RuntimeError("Agent run not found")

            if run.status == AgentRunStatus.cancelled.value:
                return _activity_result_from_run(run)

            if payload.get("explicit_resume"):
                apply_agent_run_budget_override(
                    db,
                    run=run,
                    workspace_id=payload["workspace_id"],
                    actor_email=payload["actor_email"],
                    budget_snapshot=dict(payload.get("budget_snapshot") or {}),
                    resume_reason=str(payload.get("resume_reason") or ""),
                )
                db.commit()

            child_results = persist_temporal_child_results(
                db,
                run=run,
                workspace_id=payload["workspace_id"],
                actor_email=payload["actor_email"],
                payload=payload,
            )
            if child_results:
                db.commit()

            try:
                result = execute_agent_graph(
                    db=db,
                    settings=settings,
                    workspace_id=payload["workspace_id"],
                    run_id=payload["run_id"],
                    repository_id=payload["repository_id"],
                    ref=payload.get("ref") or "",
                    candidate_limit=int(payload.get("candidate_limit") or 3),
                    actor_email=payload["actor_email"],
                    explicit_resume=bool(payload.get("explicit_resume")),
                    cancellation_checker=_activity_checkpoint,
                )
            except AgentGraphConflict as exc:
                db.rollback()
                refreshed_run = db.get(AgentRun, payload["run_id"])
                if refreshed_run and refreshed_run.status == AgentRunStatus.cancelled.value:
                    return _activity_result_from_run(refreshed_run, str(exc))
                raise
            return {
                "run_id": result.run.id,
                "status": result.run.status,
                "summary": result.summary,
                "staged_output_count": len(result.staged_outputs),
            }


@activity.defn
def execute_agent_graph_activity(payload: dict[str, Any]) -> dict[str, Any]:
    return execute_agent_graph_activity_with_settings(payload, settings=Settings())


def mark_agent_run_cancelled_with_settings(payload: dict[str, Any], *, settings: Settings) -> dict[str, Any]:
    with agent_span(
        "temporal.activity",
        temporal_activity="mark_agent_run_cancelled",
        run_id=str(payload.get("run_id") or ""),
    ):
        database = Database(settings.database_url)
        database.init()
        with database.session_factory() as db:
            run = db.get(AgentRun, payload["run_id"])
            if run is None or run.workspace_id != payload["workspace_id"]:
                raise RuntimeError("Agent run not found")
            if run.status not in {AgentRunStatus.succeeded.value, AgentRunStatus.cancelled.value}:
                try:
                    mark_run_cancelled(run, str(payload.get("cancel_reason") or "Agent run cancelled"))
                except AgentRunStateError:
                    run.status = AgentRunStatus.cancelled.value
                    run.current_phase = "cancelled"
                    run.failure_reason = str(payload.get("cancel_reason") or "Agent run cancelled")[:700]
            audit(
                db,
                workspace_id=payload["workspace_id"],
                actor_email=str(payload.get("actor_email") or "system"),
                action="agent_run.cancelled",
                entity_type="AgentRun",
                entity_id=run.id,
                summary=str(payload.get("cancel_reason") or "Temporal cancelled agent run"),
                after={"status": run.status, "cancel_reason": str(payload.get("cancel_reason") or "")},
            )
            db.commit()
            db.refresh(run)
            return {"run_id": run.id, "status": run.status, "summary": run.failure_reason or "Agent run cancelled"}


@activity.defn
def mark_agent_run_cancelled_activity(payload: dict[str, Any]) -> dict[str, Any]:
    return mark_agent_run_cancelled_with_settings(payload, settings=Settings())


def mark_agent_run_failed_with_settings(payload: dict[str, Any], *, settings: Settings) -> dict[str, Any]:
    with agent_span(
        "temporal.activity",
        temporal_activity="mark_agent_run_failed",
        run_id=str(payload.get("run_id") or ""),
    ):
        database = Database(settings.database_url)
        database.init()
        with database.session_factory() as db:
            run = db.get(AgentRun, payload["run_id"])
            if run is None or run.workspace_id != payload["workspace_id"]:
                raise RuntimeError("Agent run not found")
            failure_reason = str(payload.get("failure_reason") or "Temporal activity failed")[:700]
            if run.status not in {AgentRunStatus.succeeded.value, AgentRunStatus.cancelled.value}:
                try:
                    mark_run_failed(run, failure_reason, phase=str(payload.get("phase") or "temporal_failed"))
                except AgentRunStateError:
                    run.status = AgentRunStatus.failed.value
                    run.current_phase = str(payload.get("phase") or "temporal_failed")
                    run.failure_reason = failure_reason
            audit(
                db,
                workspace_id=payload["workspace_id"],
                actor_email=str(payload.get("actor_email") or "system"),
                action="agent_run.failed",
                entity_type="AgentRun",
                entity_id=run.id,
                summary=failure_reason[:500],
                after={"status": run.status, "failure_reason": run.failure_reason, "phase": run.current_phase},
            )
            db.commit()
            db.refresh(run)
            return {"run_id": run.id, "status": run.status, "summary": run.failure_reason or failure_reason}


@activity.defn
def mark_agent_run_failed_activity(payload: dict[str, Any]) -> dict[str, Any]:
    return mark_agent_run_failed_with_settings(payload, settings=Settings())
