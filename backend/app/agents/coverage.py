from __future__ import annotations

from sqlalchemy.orm import Session

from app.agents.models import CoverageIndexEntry
from app.agents.schemas import CoverageEntryCreate
from app.agents.serializers import evidence_refs_to_json


def add_coverage_entries(
    db: Session,
    *,
    workspace_id: str,
    project_id: str | None,
    source_type: str,
    source_id: str,
    coverage_state: str,
    entries: list[CoverageEntryCreate],
) -> list[CoverageIndexEntry]:
    created: list[CoverageIndexEntry] = []
    for payload in entries:
        entry = CoverageIndexEntry(
            workspace_id=workspace_id,
            project_id=project_id,
            source_type=source_type,
            source_id=source_id,
            coverage_state=coverage_state,
            module_id=payload.module_id,
            module_key=payload.module_key or "UNMAPPED",
            behavior_summary=payload.behavior_summary,
            signals=payload.signals,
            evidence_refs=evidence_refs_to_json(payload.evidence_refs),
            confidence=payload.confidence,
            verified_by_human=payload.verified_by_human,
        )
        db.add(entry)
        created.append(entry)
    return created


