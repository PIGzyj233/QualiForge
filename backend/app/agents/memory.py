from __future__ import annotations

from datetime import UTC, datetime
from hashlib import sha256
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.agents import AgentMemoryFile, AgentMemoryVersion, AgentRun, AgentStagedOutput, AgentStagedOutputType
from app.platform.config import Settings
from app.workspace.routes import audit, now_utc


def _safe_segment(value: str) -> str:
    return "".join(ch for ch in value if ch.isalnum() or ch in {"-", "_"})[:80] or "unknown"


def _memory_root(settings: Settings, workspace_id: str) -> Path:
    return Path(settings.agent_memory_root).expanduser() / _safe_segment(workspace_id)


def _daily_memory_path(settings: Settings, run: AgentRun) -> Path:
    project_id = _safe_segment(run.project_id or "workspace")
    today = datetime.now(UTC).date().isoformat()
    return (
        _memory_root(settings, run.workspace_id)
        / "projects"
        / project_id
        / "memory"
        / f"{today}.md"
    )


def curated_memory_path(
    settings: Settings,
    *,
    workspace_id: str,
    scope: str,
    project_id: str | None = None,
    user_id: str = "",
) -> Path:
    root = _memory_root(settings, workspace_id)
    if scope == "workspace":
        return root / "MEMORY.md"
    if scope == "project":
        if not project_id:
            raise ValueError("Project memory requires project_id")
        return root / "projects" / _safe_segment(project_id) / "MEMORY.md"
    if scope == "dreams":
        if not project_id:
            raise ValueError("Dream memory requires project_id")
        return root / "projects" / _safe_segment(project_id) / "DREAMS.md"
    if scope == "user":
        if not user_id:
            raise ValueError("User memory requires user_id")
        return root / "users" / _safe_segment(user_id) / "USER.md"
    raise ValueError(f"Unsupported memory scope: {scope}")


def _memory_header(path: Path, scope: str) -> str:
    return f"# {path.stem} {scope.replace('_', ' ').title()} Memory\n\n"


def _assert_memory_content_safe(content: str, *, settings: Settings) -> None:
    lowered = content.lower()
    forbidden_markers = [
        "system prompt:",
        "developer prompt:",
        "raw prompt",
        "provider key",
        "api_key",
        "api key",
        "secret key",
        "bearer ",
    ]
    if any(marker in lowered for marker in forbidden_markers):
        raise ValueError("Memory content appears to contain a prompt or secret")
    configured_key = settings.model_gateway_api_key.strip()
    if configured_key and configured_key in content:
        raise ValueError("Memory content contains the configured model gateway key")
    if "sk-" in content or "BEGIN OPENAI" in content:
        raise ValueError("Memory content appears to contain provider credentials")


def _run_memory_entry(db: Session, run: AgentRun, summary: str) -> str:
    outputs = db.scalars(
        select(AgentStagedOutput)
        .where(AgentStagedOutput.agent_run_id == run.id, AgentStagedOutput.workspace_id == run.workspace_id)
        .order_by(AgentStagedOutput.created_at, AgentStagedOutput.id)
    ).all()
    candidates = [output.title for output in outputs if output.output_type == AgentStagedOutputType.case_candidate.value]
    reuse_notes = [output.title for output in outputs if output.output_type == AgentStagedOutputType.agent_note.value]
    gaps: list[str] = []
    for output in outputs:
        observability = dict((output.payload or {}).get("observability") or {})
        for gap in observability.get("gaps", []) if isinstance(observability.get("gaps", []), list) else []:
            if isinstance(gap, dict):
                reason = str(gap.get("reason") or gap.get("type") or "").strip()
                if reason:
                    gaps.append(reason[:240])

    lines = [
        f"## Agent run {run.id}",
        "",
        f"- Goal: {run.goal[:500]}",
        f"- Status: {run.status}",
        f"- Summary: {summary[:700]}",
        f"- Repository/ref: {dict(run.budget_snapshot or {}).get('last_execute_request', {})}",
        f"- Staged outputs: {', '.join(candidates) if candidates else 'none'}",
        f"- Reuse notes: {', '.join(reuse_notes) if reuse_notes else 'none'}",
        f"- Observability gaps: {', '.join(gaps) if gaps else 'none'}",
        "",
    ]
    return "\n".join(lines)


def upsert_memory_file(
    db: Session,
    *,
    settings: Settings,
    workspace_id: str,
    project_id: str | None,
    user_id: str,
    scope: str,
    path: Path,
    content: str,
    actor_email: str,
    reason: str,
    patch_summary: str,
) -> AgentMemoryFile:
    _assert_memory_content_safe(content, settings=settings)
    path.parent.mkdir(parents=True, exist_ok=True)
    normalized_content = content.rstrip() + "\n"
    path.write_text(normalized_content, encoding="utf-8")
    checksum = sha256(normalized_content.encode("utf-8")).hexdigest()

    memory_file = db.scalar(
        select(AgentMemoryFile).where(
            AgentMemoryFile.workspace_id == workspace_id,
            AgentMemoryFile.project_id == project_id,
            AgentMemoryFile.user_id == user_id,
            AgentMemoryFile.scope == scope,
            AgentMemoryFile.path == str(path),
        )
    )
    if memory_file is None:
        memory_file = AgentMemoryFile(
            workspace_id=workspace_id,
            project_id=project_id,
            user_id=user_id,
            scope=scope,
            path=str(path),
            updated_by=actor_email,
        )
        db.add(memory_file)
        db.flush()

    memory_file.current_version += 1
    memory_file.checksum = checksum
    memory_file.updated_by = actor_email
    memory_file.updated_at = now_utc()
    version = AgentMemoryVersion(
        memory_file_id=memory_file.id,
        version=memory_file.current_version,
        content=normalized_content[-20000:],
        patch_summary=patch_summary[:700],
        editor=actor_email,
        reason=reason[:700],
        checksum=checksum,
    )
    db.add(version)
    audit(
        db,
        workspace_id=workspace_id,
        actor_email=actor_email,
        action="agent_memory.curated" if reason != "rollback" else "agent_memory.rolled_back",
        entity_type="AgentMemoryFile",
        entity_id=memory_file.id,
        summary=patch_summary[:500] or f"Updated {scope} memory",
        after={
            "path": str(path),
            "scope": scope,
            "project_id": project_id,
            "user_id": user_id,
            "version": memory_file.current_version,
            "checksum": checksum,
            "reason": reason,
        },
    )
    return memory_file


def curate_memory_file(
    db: Session,
    *,
    settings: Settings,
    workspace_id: str,
    scope: str,
    content: str,
    actor_email: str,
    project_id: str | None = None,
    user_id: str = "",
    reason: str = "curated_update",
    patch_summary: str = "",
) -> AgentMemoryFile:
    path = curated_memory_path(settings, workspace_id=workspace_id, scope=scope, project_id=project_id, user_id=user_id)
    return upsert_memory_file(
        db,
        settings=settings,
        workspace_id=workspace_id,
        project_id=project_id if scope in {"project", "dreams"} else None,
        user_id=user_id if scope == "user" else "",
        scope=scope,
        path=path,
        content=content or _memory_header(path, scope),
        actor_email=actor_email,
        reason=reason,
        patch_summary=patch_summary or f"Curated {scope} memory",
    )


def rollback_memory_file(
    db: Session,
    *,
    settings: Settings,
    memory_file: AgentMemoryFile,
    target_version: int,
    actor_email: str,
    reason: str,
) -> AgentMemoryFile:
    version = db.scalar(
        select(AgentMemoryVersion).where(
            AgentMemoryVersion.memory_file_id == memory_file.id,
            AgentMemoryVersion.version == target_version,
        )
    )
    if version is None:
        raise ValueError("Memory version not found")
    return upsert_memory_file(
        db,
        settings=settings,
        workspace_id=memory_file.workspace_id,
        project_id=memory_file.project_id,
        user_id=memory_file.user_id,
        scope=memory_file.scope,
        path=Path(memory_file.path),
        content=version.content,
        actor_email=actor_email,
        reason="rollback",
        patch_summary=reason or f"Rolled back memory to version {target_version}",
    )


def list_memory_files(
    db: Session,
    *,
    workspace_id: str,
    project_id: str | None = None,
    scope: str | None = None,
) -> list[AgentMemoryFile]:
    statement = select(AgentMemoryFile).where(AgentMemoryFile.workspace_id == workspace_id)
    if project_id:
        statement = statement.where((AgentMemoryFile.project_id == project_id) | (AgentMemoryFile.project_id.is_(None)))
    if scope:
        statement = statement.where(AgentMemoryFile.scope == scope)
    return list(db.scalars(statement.order_by(AgentMemoryFile.updated_at.desc(), AgentMemoryFile.id.desc())).all())


def _snippet_for_query(content: str, query: str) -> str:
    compact = " ".join(line.strip() for line in content.splitlines() if line.strip())
    if not query:
        return compact[:500]
    index = compact.lower().find(query.lower())
    if index < 0:
        return compact[:500]
    start = max(0, index - 180)
    end = min(len(compact), index + len(query) + 280)
    prefix = "..." if start else ""
    suffix = "..." if end < len(compact) else ""
    return f"{prefix}{compact[start:end]}{suffix}"[:700]


def search_memory(
    db: Session,
    *,
    workspace_id: str,
    query: str,
    project_id: str | None = None,
    scope: str | None = None,
    limit: int = 10,
) -> list[dict[str, Any]]:
    normalized_query = query.strip().lower()
    files = list_memory_files(db, workspace_id=workspace_id, project_id=project_id, scope=scope)
    matches: list[dict[str, Any]] = []
    for memory_file in files:
        path = Path(memory_file.path)
        if path.exists():
            content = path.read_text(encoding="utf-8", errors="replace")
        else:
            latest = db.scalar(
                select(AgentMemoryVersion)
                .where(AgentMemoryVersion.memory_file_id == memory_file.id)
                .order_by(AgentMemoryVersion.version.desc(), AgentMemoryVersion.id.desc())
            )
            content = latest.content if latest is not None else ""
        searchable = content.lower()
        if normalized_query and normalized_query not in searchable:
            continue
        score = searchable.count(normalized_query) if normalized_query else 1
        matches.append(
            {
                "memory_file": memory_file,
                "score": score,
                "snippet": _snippet_for_query(content, query),
            }
        )
    matches.sort(key=lambda item: (item["score"], item["memory_file"].updated_at), reverse=True)
    return matches[: max(1, min(limit, 50))]


def append_daily_project_memory(db: Session, *, settings: Settings, run: AgentRun, actor_email: str, summary: str) -> None:
    if not run.project_id:
        return
    path = _daily_memory_path(settings, run)
    path.parent.mkdir(parents=True, exist_ok=True)
    entry = _run_memory_entry(db, run, summary)
    previous = path.read_text(encoding="utf-8") if path.exists() else f"# {path.stem} Agent Memory\n\n"
    content = previous.rstrip() + "\n\n" + entry
    checksum = sha256(content.encode("utf-8")).hexdigest()
    path.write_text(content, encoding="utf-8")

    memory_file = db.scalar(
        select(AgentMemoryFile).where(
            AgentMemoryFile.workspace_id == run.workspace_id,
            AgentMemoryFile.project_id == run.project_id,
            AgentMemoryFile.path == str(path),
        )
    )
    if memory_file is None:
        memory_file = AgentMemoryFile(
            workspace_id=run.workspace_id,
            project_id=run.project_id,
            user_id="",
            scope="daily_project",
            path=str(path),
            updated_by=actor_email,
        )
        db.add(memory_file)
        db.flush()

    memory_file.current_version += 1
    memory_file.checksum = checksum
    memory_file.updated_by = actor_email
    memory_file.updated_at = now_utc()
    version = AgentMemoryVersion(
        memory_file_id=memory_file.id,
        version=memory_file.current_version,
        content=content[-20000:],
        patch_summary=f"Appended successful agent run {run.id}",
        editor=actor_email,
        reason="successful_agent_run",
        checksum=checksum,
    )
    db.add(version)
    audit(
        db,
        workspace_id=run.workspace_id,
        actor_email=actor_email,
        action="agent_memory.appended",
        entity_type="AgentMemoryFile",
        entity_id=memory_file.id,
        summary=f"Appended daily project memory for agent run {run.id}",
        after={
            "path": str(path),
            "scope": memory_file.scope,
            "version": memory_file.current_version,
            "checksum": checksum,
        },
    )
