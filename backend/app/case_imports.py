from __future__ import annotations

import csv
import io
import re
import zipfile
from datetime import datetime
from enum import StrEnum
from pathlib import Path
from typing import Annotated
from xml.etree import ElementTree

from fastapi import APIRouter, BackgroundTasks, Depends, File, HTTPException, Query, Request, Response, UploadFile, status
from pydantic import BaseModel, Field
from sqlalchemy import JSON, DateTime, ForeignKey, Integer, String, select
from sqlalchemy.orm import Mapped, Session, mapped_column

from app.database import Base, Database
from app.gitlab import Job, JobStatus, job_to_response
from app.modules import ModuleMappingRule, ProjectModule, get_module_or_404
from app.workspaces import ActorEmail, audit, get_project_or_404, get_workspace_or_404, new_id, now_utc, require_workspace_owner


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


class TestCaseStatus(StrEnum):
    draft = "draft"
    pending_review = "pending_review"
    approved = "approved"
    rejected = "rejected"
    archived = "archived"


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


class TestCase(Base):
    __tablename__ = "test_cases"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    workspace_id: Mapped[str] = mapped_column(ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False, index=True)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True)
    module_id: Mapped[str | None] = mapped_column(ForeignKey("project_modules.id", ondelete="SET NULL"), nullable=True, index=True)
    import_batch_id: Mapped[str | None] = mapped_column(ForeignKey("import_batches.id", ondelete="SET NULL"), nullable=True, index=True)
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    steps: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    expected_result: Mapped[str] = mapped_column(String(2000), default="", nullable=False)
    priority: Mapped[str] = mapped_column(String(32), default="P2", nullable=False)
    risk: Mapped[str] = mapped_column(String(80), default="medium", nullable=False)
    tags: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    custom_fields: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    status: Mapped[str] = mapped_column(String(32), default=TestCaseStatus.draft.value, nullable=False, index=True)
    submitted_by: Mapped[str] = mapped_column(String(254), default="", nullable=False)
    approved_by: Mapped[str] = mapped_column(String(254), default="", nullable=False)
    current_revision_number: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
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
    title: str
    steps: list[str]
    expected_result: str
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


class DraftUpdate(BaseModel):
    module_id: str | None = None
    title: str | None = Field(default=None, min_length=1, max_length=300)
    steps: list[str] | None = Field(default=None, max_length=100)
    expected_result: str | None = Field(default=None, max_length=2000)
    priority: str | None = Field(default=None, max_length=32)
    risk: str | None = Field(default=None, max_length=80)
    tags: list[str] | None = Field(default=None, max_length=50)
    custom_fields: dict[str, str] | None = None


class BulkDraftUpdate(DraftUpdate):
    draft_ids: list[str] | None = Field(default=None, max_length=500)


class ImportResultResponse(BaseModel):
    batch: ImportBatchResponse
    imported_count: int


class TestCaseResponse(BaseModel):
    id: str
    workspace_id: str
    project_id: str
    module_id: str | None
    import_batch_id: str | None
    title: str
    steps: list[str]
    expected_result: str
    priority: str
    risk: str
    tags: list[str]
    custom_fields: dict
    status: str
    submitted_by: str
    approved_by: str
    current_revision_number: int
    created_at: datetime
    updated_at: datetime


def get_db(request: Request):
    yield from request.app.state.database.session()


DbSession = Annotated[Session, Depends(get_db)]

router = APIRouter(prefix="/api/workspaces/{workspace_id}/projects/{project_id}", tags=["case-imports"])


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
        .order_by(ProjectModule.key)
    ).all()
    rules = db.scalars(
        select(ModuleMappingRule)
        .where(ModuleMappingRule.workspace_id == workspace_id, ModuleMappingRule.project_id == project_id)
        .order_by(ModuleMappingRule.rule_type, ModuleMappingRule.pattern)
    ).all()
    return list(modules), list(rules)


def infer_module_id(row: dict, modules: list[ProjectModule], rules: list[ModuleMappingRule]) -> str | None:
    module_hint = str(row.get("module") or "").strip().lower()
    for module in modules:
        if module_hint and module_hint in {module.key.lower(), module.name.lower()}:
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
        steps = split_steps(str(row.get("steps") or ""))
        expected_result = str(row.get("expected_result") or "").strip()
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
        title=draft.title,
        steps=draft.steps,
        expected_result=draft.expected_result,
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


def test_case_to_response(test_case: TestCase) -> TestCaseResponse:
    return TestCaseResponse(
        id=test_case.id,
        workspace_id=test_case.workspace_id,
        project_id=test_case.project_id,
        module_id=test_case.module_id,
        import_batch_id=test_case.import_batch_id,
        title=test_case.title,
        steps=test_case.steps,
        expected_result=test_case.expected_result,
        priority=test_case.priority,
        risk=test_case.risk,
        tags=test_case.tags,
        custom_fields=test_case.custom_fields,
        status=test_case.status,
        submitted_by=test_case.submitted_by,
        approved_by=test_case.approved_by,
        current_revision_number=test_case.current_revision_number,
        created_at=test_case.created_at,
        updated_at=test_case.updated_at,
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


@router.post("/imports", response_model=ImportBatchResponse, status_code=status.HTTP_202_ACCEPTED)
async def upload_import_batch(
    workspace_id: str,
    project_id: str,
    background_tasks: BackgroundTasks,
    db: DbSession,
    request: Request,
    actor_email: ActorEmail,
    file: UploadFile = File(...),
) -> ImportBatchResponse:
    get_workspace_or_404(db, workspace_id)
    get_project_or_404(db, workspace_id, project_id)
    filename = safe_filename(file.filename or "import.csv")
    file_type = import_file_type(filename)
    content = await file.read()
    if not content:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Import file is empty")

    batch = ImportBatch(
        workspace_id=workspace_id,
        project_id=project_id,
        file_name=filename,
        file_type=file_type,
        original_file_path="pending",
        created_by=actor_email,
    )
    db.add(batch)
    db.flush()
    storage_dir = Path(request.app.state.settings.import_storage_root).expanduser() / workspace_id[:12] / project_id[:12] / batch.id
    storage_dir.mkdir(parents=True, exist_ok=True)
    storage_path = storage_dir / filename
    storage_path.write_bytes(content)
    batch.original_file_path = str(storage_path.resolve(strict=False))

    job = Job(
        workspace_id=workspace_id,
        project_id=project_id,
        job_type="import_cases",
        status=JobStatus.queued.value,
        created_by=actor_email,
        input_summary=f"Import historical cases from {filename}",
        key_logs=["Queued import normalization"],
        timeout_seconds=120,
        repo_size_limit_mb=0,
        diff_file_limit=0,
    )
    db.add(job)
    db.flush()
    batch.job_id = job.id
    audit(
        db,
        workspace_id=workspace_id,
        actor_email=actor_email,
        action="import_batch.uploaded",
        entity_type="ImportBatch",
        entity_id=batch.id,
        summary=f"Uploaded import file {filename}",
        after={"project_id": project_id, "file_name": filename, "file_type": file_type, "job_id": job.id},
    )
    db.commit()
    db.refresh(batch)
    background_tasks.add_task(run_import_conversion, request.app.state.database, batch.id)
    return batch_to_response(batch)


@router.get("/imports", response_model=list[ImportBatchResponse])
def list_import_batches(workspace_id: str, project_id: str, db: DbSession) -> list[ImportBatchResponse]:
    get_workspace_or_404(db, workspace_id)
    get_project_or_404(db, workspace_id, project_id)
    batches = db.scalars(
        select(ImportBatch)
        .where(ImportBatch.workspace_id == workspace_id, ImportBatch.project_id == project_id)
        .order_by(ImportBatch.created_at.desc(), ImportBatch.id.desc())
    ).all()
    return [batch_to_response(batch) for batch in batches]


@router.get("/imports/{batch_id}", response_model=ImportBatchResponse)
def get_import_batch(workspace_id: str, project_id: str, batch_id: str, db: DbSession) -> ImportBatchResponse:
    get_workspace_or_404(db, workspace_id)
    get_project_or_404(db, workspace_id, project_id)
    return batch_to_response(get_batch_or_404(db, workspace_id, project_id, batch_id))


@router.get("/imports/{batch_id}/drafts", response_model=list[DraftResponse])
def list_import_drafts(workspace_id: str, project_id: str, batch_id: str, db: DbSession) -> list[DraftResponse]:
    get_workspace_or_404(db, workspace_id)
    get_project_or_404(db, workspace_id, project_id)
    get_batch_or_404(db, workspace_id, project_id, batch_id)
    drafts = db.scalars(
        select(ImportCaseDraft)
        .where(ImportCaseDraft.workspace_id == workspace_id, ImportCaseDraft.project_id == project_id, ImportCaseDraft.batch_id == batch_id)
        .order_by(ImportCaseDraft.source_row_index, ImportCaseDraft.id)
    ).all()
    return [draft_to_response(draft) for draft in drafts]


def apply_draft_update(draft: ImportCaseDraft, payload: DraftUpdate) -> dict:
    update_data = payload.model_dump(exclude_unset=True)
    update_data.pop("draft_ids", None)
    for field, value in update_data.items():
        setattr(draft, field, [item.strip() for item in value if item.strip()] if field in {"steps", "tags"} and value else value)
    draft.updated_at = now_utc()
    return update_data


@router.patch("/imports/{batch_id}/drafts/{draft_id}", response_model=DraftResponse)
def update_import_draft(
    workspace_id: str,
    project_id: str,
    batch_id: str,
    draft_id: str,
    payload: DraftUpdate,
    db: DbSession,
    actor_email: ActorEmail,
) -> DraftResponse:
    batch = get_batch_or_404(db, workspace_id, project_id, batch_id)
    if payload.module_id:
        get_module_or_404(db, workspace_id, project_id, payload.module_id)
    draft = get_draft_or_404(db, workspace_id, project_id, batch_id, draft_id)
    changes = apply_draft_update(draft, payload)
    batch.manual_changes = [
        *batch.manual_changes,
        {"actor_email": actor_email, "updated_at": now_utc().isoformat(), "draft_ids": [draft.id], "changes": changes},
    ]
    batch.updated_at = now_utc()
    audit(
        db,
        workspace_id=workspace_id,
        actor_email=actor_email,
        action="import_draft.updated",
        entity_type="ImportCaseDraft",
        entity_id=draft.id,
        summary=f"Updated imported draft {draft.title}",
        after=changes,
    )
    db.commit()
    db.refresh(draft)
    return draft_to_response(draft)


@router.patch("/imports/{batch_id}/drafts-bulk", response_model=list[DraftResponse])
def bulk_update_import_drafts(
    workspace_id: str,
    project_id: str,
    batch_id: str,
    payload: BulkDraftUpdate,
    db: DbSession,
    actor_email: ActorEmail,
) -> list[DraftResponse]:
    batch = get_batch_or_404(db, workspace_id, project_id, batch_id)
    if payload.module_id:
        get_module_or_404(db, workspace_id, project_id, payload.module_id)
    statement = select(ImportCaseDraft).where(
        ImportCaseDraft.workspace_id == workspace_id,
        ImportCaseDraft.project_id == project_id,
        ImportCaseDraft.batch_id == batch_id,
    )
    if payload.draft_ids:
        statement = statement.where(ImportCaseDraft.id.in_(payload.draft_ids))
    drafts = list(db.scalars(statement.order_by(ImportCaseDraft.source_row_index, ImportCaseDraft.id)).all())
    changes = payload.model_dump(exclude_unset=True)
    changes.pop("draft_ids", None)
    for draft in drafts:
        apply_draft_update(draft, payload)
    batch.manual_changes = [
        *batch.manual_changes,
        {"actor_email": actor_email, "updated_at": now_utc().isoformat(), "draft_ids": [draft.id for draft in drafts], "changes": changes},
    ]
    batch.updated_at = now_utc()
    audit(
        db,
        workspace_id=workspace_id,
        actor_email=actor_email,
        action="import_draft.bulk_updated",
        entity_type="ImportBatch",
        entity_id=batch.id,
        summary=f"Bulk updated {len(drafts)} imported drafts",
        after={"draft_count": len(drafts), "changes": changes},
    )
    db.commit()
    return [draft_to_response(draft) for draft in drafts]


@router.post("/imports/{batch_id}/submit-review", response_model=ImportBatchResponse)
def submit_import_review(workspace_id: str, project_id: str, batch_id: str, db: DbSession, actor_email: ActorEmail) -> ImportBatchResponse:
    batch = get_batch_or_404(db, workspace_id, project_id, batch_id)
    drafts = db.scalars(select(ImportCaseDraft).where(ImportCaseDraft.batch_id == batch.id)).all()
    for draft in drafts:
        draft.status = ImportDraftStatus.review_submitted.value
        draft.updated_at = now_utc()
    batch.status = ImportBatchStatus.review_submitted.value
    batch.submitted_at = now_utc()
    batch.updated_at = now_utc()
    audit(
        db,
        workspace_id=workspace_id,
        actor_email=actor_email,
        action="import_batch.review_submitted",
        entity_type="ImportBatch",
        entity_id=batch.id,
        summary=f"Submitted {len(drafts)} imported drafts for review",
        after={"draft_count": len(drafts)},
    )
    db.commit()
    db.refresh(batch)
    return batch_to_response(batch)


@router.post("/imports/{batch_id}/bulk-import", response_model=ImportResultResponse)
def bulk_import_test_cases(workspace_id: str, project_id: str, batch_id: str, db: DbSession, actor_email: ActorEmail) -> ImportResultResponse:
    require_workspace_owner(db, workspace_id, actor_email)
    batch = get_batch_or_404(db, workspace_id, project_id, batch_id)
    if batch.status == ImportBatchStatus.imported.value:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Import batch already imported")
    drafts = db.scalars(
        select(ImportCaseDraft)
        .where(ImportCaseDraft.workspace_id == workspace_id, ImportCaseDraft.project_id == project_id, ImportCaseDraft.batch_id == batch_id)
        .order_by(ImportCaseDraft.source_row_index, ImportCaseDraft.id)
    ).all()
    for draft in drafts:
        db.add(
            TestCase(
                workspace_id=workspace_id,
                project_id=project_id,
                module_id=draft.module_id,
                import_batch_id=batch.id,
                title=draft.title,
                steps=draft.steps,
                expected_result=draft.expected_result,
                priority=draft.priority,
                risk=draft.risk,
                tags=draft.tags,
                custom_fields=draft.custom_fields,
                status=TestCaseStatus.approved.value,
                submitted_by=actor_email,
                approved_by=actor_email,
                current_revision_number=1,
            )
        )
        draft.status = ImportDraftStatus.imported.value
        draft.updated_at = now_utc()
    batch.status = ImportBatchStatus.imported.value
    batch.imported_at = now_utc()
    batch.updated_at = now_utc()
    audit(
        db,
        workspace_id=workspace_id,
        actor_email=actor_email,
        action="import_batch.imported",
        entity_type="ImportBatch",
        entity_id=batch.id,
        summary=f"Imported {len(drafts)} drafts into test case library",
        after={"imported_count": len(drafts)},
    )
    db.commit()
    db.refresh(batch)
    return ImportResultResponse(batch=batch_to_response(batch), imported_count=len(drafts))


@router.get("/test-cases", response_model=list[TestCaseResponse])
def list_test_cases(
    workspace_id: str,
    project_id: str,
    db: DbSession,
    module_id: str | None = Query(default=None),
    case_status: TestCaseStatus | None = Query(default=None, alias="status"),
) -> list[TestCaseResponse]:
    get_workspace_or_404(db, workspace_id)
    get_project_or_404(db, workspace_id, project_id)
    statement = (
        select(TestCase)
        .where(TestCase.workspace_id == workspace_id, TestCase.project_id == project_id)
        .order_by(TestCase.created_at.desc(), TestCase.id.desc())
    )
    if module_id:
        statement = statement.where(TestCase.module_id == module_id)
    if case_status:
        statement = statement.where(TestCase.status == case_status.value)
    return [test_case_to_response(test_case) for test_case in db.scalars(statement).all()]
