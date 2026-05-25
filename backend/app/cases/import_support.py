from __future__ import annotations

import csv
import io
import re
import zipfile
from pathlib import Path
from xml.etree import ElementTree

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.cases.import_models import (
    DraftResponse,
    ImportBatch,
    ImportBatchResponse,
    ImportBatchStatus,
    ImportCaseDraft,
    ImportDraftStatus,
)
from app.cases.modules import MappingRelationship, MappingRuleStatus, ModuleMappingRule, ProjectModule
from app.cases.step_models import normalize_steps_with_legacy
from app.git.models import Job, JobStatus
from app.platform.database import Database
from app.workspace.routes import now_utc


HEADER_ALIASES = {
    "title": {"title", "case title", "name", "用例标题", "标题", "用例名称", "测试点"},
    "steps": {"steps", "step", "test steps", "操作步骤", "测试步骤", "步骤"},
    "expected_result": {"expected", "expected result", "expect", "预期", "预期结果", "期望结果"},
    "priority": {"priority", "优先级"},
    "risk": {"risk", "风险", "风险等级"},
    "tags": {"tags", "tag", "标签"},
    "module": {"module", "模块", "功能域", "业务域"},
}


def normalize_header(value: str) -> str:
    text = re.sub(r"[\s_/-]+", " ", value.strip().lower())
    for field, aliases in HEADER_ALIASES.items():
        if text in aliases:
            return field
    return value.strip() or "unnamed"


def safe_filename(filename: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9._-]+", "_", Path(filename).name).strip("._")
    return cleaned or "import.csv"


def import_file_type(filename: str) -> str:
    suffix = Path(filename).suffix.lower()
    if suffix == ".csv":
        return "csv"
    if suffix == ".xlsx":
        return "xlsx"
    raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Only CSV and XLSX imports are supported")


def decode_text(content: bytes) -> str:
    for encoding in ("utf-8-sig", "utf-8", "gb18030"):
        try:
            return content.decode(encoding)
        except UnicodeDecodeError:
            continue
    raise ValueError("Could not decode CSV file")


def parse_csv_rows(content: bytes) -> list[dict]:
    text = decode_text(content)
    sample = text[:2048]
    try:
        dialect = csv.Sniffer().sniff(sample)
    except csv.Error:
        dialect = csv.excel
    reader = csv.DictReader(io.StringIO(text), dialect=dialect)
    if not reader.fieldnames:
        return []
    rows = []
    for row in reader:
        compact = {}
        for key, value in row.items():
            if key is None:
                continue
            compact[normalize_header(key)] = (value or "").strip()
        if any(str(value).strip() for value in compact.values()):
            rows.append(compact)
    return rows


def column_index(cell_ref: str) -> int:
    letters = "".join(ch for ch in cell_ref if ch.isalpha()).upper()
    index = 0
    for ch in letters:
        index = index * 26 + ord(ch) - ord("A") + 1
    return max(index - 1, 0)


def parse_shared_strings(zf: zipfile.ZipFile) -> list[str]:
    try:
        xml = zf.read("xl/sharedStrings.xml")
    except KeyError:
        return []
    root = ElementTree.fromstring(xml)
    values = []
    for item in root.iter():
        if item.tag.endswith("}si") or item.tag == "si":
            pieces = [node.text or "" for node in item.iter() if node.tag.endswith("}t") or node.tag == "t"]
            values.append("".join(pieces))
    return values


def cell_text(cell: ElementTree.Element, shared_strings: list[str]) -> str:
    cell_type = cell.attrib.get("t")
    value_node = next((node for node in cell if node.tag.endswith("}v") or node.tag == "v"), None)
    if cell_type == "inlineStr":
        return "".join(node.text or "" for node in cell.iter() if node.tag.endswith("}t") or node.tag == "t").strip()
    if value_node is None or value_node.text is None:
        return ""
    if cell_type == "s":
        try:
            return shared_strings[int(value_node.text)].strip()
        except (ValueError, IndexError):
            return ""
    return value_node.text.strip()


def parse_xlsx_rows(content: bytes) -> list[dict]:
    with zipfile.ZipFile(io.BytesIO(content)) as zf:
        sheet_names = sorted(name for name in zf.namelist() if name.startswith("xl/worksheets/sheet") and name.endswith(".xml"))
        if not sheet_names:
            return []
        shared_strings = parse_shared_strings(zf)
        root = ElementTree.fromstring(zf.read(sheet_names[0]))
        table_rows: list[list[str]] = []
        for row in (node for node in root.iter() if node.tag.endswith("}row") or node.tag == "row"):
            values: dict[int, str] = {}
            for cell in (node for node in row if node.tag.endswith("}c") or node.tag == "c"):
                values[column_index(cell.attrib.get("r", ""))] = cell_text(cell, shared_strings)
            if values:
                width = max(values) + 1
                table_rows.append([values.get(index, "") for index in range(width)])
    if not table_rows:
        return []
    headers = [normalize_header(header) for header in table_rows[0]]
    rows = []
    for row in table_rows[1:]:
        compact = {headers[index]: row[index].strip() if index < len(row) else "" for index in range(len(headers))}
        if any(str(value).strip() for value in compact.values()):
            rows.append(compact)
    return rows


def parse_rows(filename: str, content: bytes) -> list[dict]:
    file_type = import_file_type(filename)
    return parse_csv_rows(content) if file_type == "csv" else parse_xlsx_rows(content)


def split_steps(value: str) -> list[str]:
    parts = re.split(r"\r?\n|;|；", value or "")
    cleaned = [re.sub(r"^\s*\d+[.)、]\s*", "", part).strip() for part in parts]
    return [part for part in cleaned if part]


def split_tags(value: str) -> list[str]:
    parts = re.split(r"[,，;；\s]+", value or "")
    return [part.strip() for part in parts if part.strip()]


def load_modules_and_rules(db: Session, workspace_id: str, project_id: str) -> tuple[list[ProjectModule], list[ModuleMappingRule]]:
    modules = db.scalars(
        select(ProjectModule)
        .where(ProjectModule.workspace_id == workspace_id, ProjectModule.project_id == project_id)
        .order_by(ProjectModule.path)
    ).all()
    rules = db.scalars(
        select(ModuleMappingRule)
        .where(
            ModuleMappingRule.workspace_id == workspace_id,
            ModuleMappingRule.project_id == project_id,
            ModuleMappingRule.status == MappingRuleStatus.active.value,
            ModuleMappingRule.relationship != MappingRelationship.evidence.value,
        )
        .order_by(ModuleMappingRule.rule_type, ModuleMappingRule.pattern)
    ).all()
    return list(modules), list(rules)


def infer_module_id(row: dict, modules: list[ProjectModule], rules: list[ModuleMappingRule]) -> str | None:
    module_hint = str(row.get("module") or "").strip().lower()
    for module in modules:
        aliases = {module.name.lower(), module.slug.lower(), module.path.lower(), module.path_label.lower()}
        if module.code:
            aliases.add(module.code.lower())
        if module_hint and module_hint in aliases:
            return module.id

    searchable = " ".join(str(value) for value in row.values()).lower()
    for rule in rules:
        pattern = rule.pattern.lower().strip("*")
        if pattern and pattern in searchable:
            return rule.module_id
    return None


def convert_rows_to_drafts(rows: list[dict], modules: list[ProjectModule], rules: list[ModuleMappingRule]) -> list[dict]:
    drafts = []
    known_fields = {"title", "steps", "expected_result", "priority", "risk", "tags", "module"}
    for index, row in enumerate(rows, start=1):
        title = str(row.get("title") or row.get("测试点") or f"Imported case #{index}").strip()
        raw_steps = split_steps(str(row.get("steps") or ""))
        expected_result = str(row.get("expected_result") or "").strip()
        steps = [{"action": step, "expected": ""} for step in raw_steps]
        if expected_result and steps:
            steps[-1]["expected"] = expected_result[:1000]
        elif expected_result and not steps:
            steps = [{"action": title, "expected": expected_result[:1000]}]
        tags = split_tags(str(row.get("tags") or ""))
        custom_fields = {key: value for key, value in row.items() if key not in known_fields and str(value).strip()}
        confidence = 90 if title and steps and expected_result else 70
        drafts.append(
            {
                "source_row_index": index,
                "module_id": infer_module_id(row, modules, rules),
                "title": title[:300],
                "steps": steps,
                "expected_result": expected_result[:2000],
                "priority": str(row.get("priority") or "P2").strip()[:32],
                "risk": str(row.get("risk") or "medium").strip()[:80],
                "tags": tags,
                "custom_fields": custom_fields,
                "ai_confidence": confidence,
                "raw_row": row,
            }
        )
    return drafts


def batch_to_response(batch: ImportBatch) -> ImportBatchResponse:
    return ImportBatchResponse(
        id=batch.id,
        workspace_id=batch.workspace_id,
        project_id=batch.project_id,
        job_id=batch.job_id,
        file_name=batch.file_name,
        file_type=batch.file_type,
        original_file_path=batch.original_file_path,
        status=batch.status,
        created_by=batch.created_by,
        row_count=batch.row_count,
        raw_rows=batch.raw_rows,
        ai_conversion_result=batch.ai_conversion_result,
        manual_changes=batch.manual_changes,
        error_summary=batch.error_summary,
        created_at=batch.created_at,
        updated_at=batch.updated_at,
        submitted_at=batch.submitted_at,
        imported_at=batch.imported_at,
    )


def draft_to_response(draft: ImportCaseDraft) -> DraftResponse:
    return DraftResponse(
        id=draft.id,
        workspace_id=draft.workspace_id,
        project_id=draft.project_id,
        batch_id=draft.batch_id,
        module_id=draft.module_id,
        test_case_id=draft.test_case_id,
        case_draft_id=draft.case_draft_id,
        review_cycle_id=draft.review_cycle_id,
        title=draft.title,
        steps=normalize_steps_with_legacy(draft.steps, draft.expected_result),
        priority=draft.priority,
        risk=draft.risk,
        tags=draft.tags,
        custom_fields=draft.custom_fields,
        source_row_index=draft.source_row_index,
        raw_row=draft.raw_row,
        ai_confidence=draft.ai_confidence,
        status=draft.status,
        created_at=draft.created_at,
        updated_at=draft.updated_at,
    )

def get_batch_or_404(db: Session, workspace_id: str, project_id: str, batch_id: str) -> ImportBatch:
    batch = db.scalar(
        select(ImportBatch).where(
            ImportBatch.id == batch_id,
            ImportBatch.workspace_id == workspace_id,
            ImportBatch.project_id == project_id,
        )
    )
    if batch is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Import batch not found")
    return batch


def get_draft_or_404(db: Session, workspace_id: str, project_id: str, batch_id: str, draft_id: str) -> ImportCaseDraft:
    draft = db.scalar(
        select(ImportCaseDraft).where(
            ImportCaseDraft.id == draft_id,
            ImportCaseDraft.workspace_id == workspace_id,
            ImportCaseDraft.project_id == project_id,
            ImportCaseDraft.batch_id == batch_id,
        )
    )
    if draft is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Import draft not found")
    return draft


def run_import_conversion(database: Database, batch_id: str) -> None:
    with database.session_factory() as db:
        batch = db.get(ImportBatch, batch_id)
        if batch is None:
            return
        job = db.get(Job, batch.job_id) if batch.job_id else None
        if job:
            job.status = JobStatus.running.value
            job.started_at = now_utc()
            job.key_logs = ["Import file preserved", "AI normalization started"]
        try:
            content = Path(batch.original_file_path).read_bytes()
            rows = parse_rows(batch.file_name, content)
            modules, rules = load_modules_and_rules(db, batch.workspace_id, batch.project_id)
            converted = convert_rows_to_drafts(rows, modules, rules)
            batch.raw_rows = rows
            batch.ai_conversion_result = converted
            batch.row_count = len(rows)
            batch.status = ImportBatchStatus.preview_ready.value
            batch.error_summary = ""
            for item in converted:
                db.add(
                    ImportCaseDraft(
                        workspace_id=batch.workspace_id,
                        project_id=batch.project_id,
                        batch_id=batch.id,
                        module_id=item["module_id"],
                        title=item["title"],
                        steps=item["steps"],
                        expected_result=item["expected_result"],
                        priority=item["priority"],
                        risk=item["risk"],
                        tags=item["tags"],
                        custom_fields=item["custom_fields"],
                        source_row_index=item["source_row_index"],
                        raw_row=item["raw_row"],
                        ai_confidence=item["ai_confidence"],
                    )
                )
            if job:
                job.status = JobStatus.succeeded.value
                job.output_summary = f"Normalized {len(converted)} imported case drafts"
                job.key_logs = [*job.key_logs, f"Detected {len(rows)} rows", f"Generated {len(converted)} drafts"]
        except Exception as exc:
            batch.status = ImportBatchStatus.failed.value
            batch.error_summary = str(exc)[:500]
            if job:
                job.status = JobStatus.failed.value
                job.error_summary = batch.error_summary
        finally:
            batch.updated_at = now_utc()
            if job:
                job.finished_at = now_utc()
            db.commit()
