from __future__ import annotations

from collections.abc import Iterator
from threading import Lock

from sqlalchemy import create_engine
from sqlalchemy import inspect
from sqlalchemy import text
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker
from sqlalchemy.pool import StaticPool


class Base(DeclarativeBase):
    pass


AI_INVOCATION_LOG_COLUMN_UPGRADES = (
    ("agent_run_id", "VARCHAR(64)", None),
    ("tool_call_id", "VARCHAR(64)", None),
    ("provider_name", "VARCHAR(120)", "''"),
    ("model_alias", "VARCHAR(160)", "''"),
    ("model_name", "VARCHAR(160)", "''"),
    ("prompt_hash", "VARCHAR(80)", "''"),
    ("prompt_version", "VARCHAR(80)", "''"),
    ("subagent_name", "VARCHAR(80)", "''"),
    ("attempts", "INTEGER", "0"),
    ("usage", "JSON", "'{}'"),
    ("raw_invocation_id", "VARCHAR(160)", "''"),
)

AI_INVOCATION_LOG_INDEX_UPGRADES = (
    ("ix_ai_invocation_logs_agent_run_id", "agent_run_id"),
    ("ix_ai_invocation_logs_tool_call_id", "tool_call_id"),
    ("ix_ai_invocation_logs_provider_name", "provider_name"),
    ("ix_ai_invocation_logs_model_alias", "model_alias"),
    ("ix_ai_invocation_logs_model_name", "model_name"),
    ("ix_ai_invocation_logs_prompt_hash", "prompt_hash"),
    ("ix_ai_invocation_logs_prompt_version", "prompt_version"),
    ("ix_ai_invocation_logs_subagent_name", "subagent_name"),
)

AGENT_STAGED_OUTPUT_COLUMN_UPGRADES = (
    ("idempotency_key", "VARCHAR(160)", "''"),
)

AGENT_STAGED_OUTPUT_INDEX_UPGRADES = (
    ("ix_agent_staged_outputs_idempotency_key", "idempotency_key"),
)

TEST_CASE_COLUMN_UPGRADES = (
    ("lifecycle_status", "VARCHAR(32)", "'draft'"),
    ("current_revision_id", "VARCHAR(64)", None),
    ("current_module_id", "VARCHAR(64)", None),
    ("source_type", "VARCHAR(40)", "'manual'"),
    ("source_ref", "JSON", "'{}'"),
    ("created_by", "VARCHAR(254)", "''"),
)

TEST_CASE_INDEX_UPGRADES = (
    ("ix_test_cases_lifecycle_status", "lifecycle_status"),
    ("ix_test_cases_current_revision_id", "current_revision_id"),
    ("ix_test_cases_current_module_id", "current_module_id"),
    ("ix_test_cases_source_type", "source_type"),
)


def normalize_database_url(database_url: str) -> str:
    if database_url.startswith("postgresql://"):
        return database_url.replace("postgresql://", "postgresql+psycopg://", 1)
    return database_url


class Database:
    def __init__(self, database_url: str):
        url = normalize_database_url(database_url)
        connect_args = {}
        engine_kwargs = {}

        if url.startswith("sqlite"):
            connect_args["check_same_thread"] = False
            if url.endswith(":memory:"):
                engine_kwargs["poolclass"] = StaticPool

        self.engine = create_engine(url, connect_args=connect_args, **engine_kwargs)
        self.session_factory = sessionmaker(bind=self.engine, autocommit=False, autoflush=False, expire_on_commit=False)
        self._initialized = False
        self._lock = Lock()

    def init(self) -> None:
        with self._lock:
            if self._initialized:
                return
            from app.platform.model_registry import register_models

            register_models()
            Base.metadata.create_all(bind=self.engine)
            run_schema_upgrades(self.engine)
            self._initialized = True

    def session(self) -> Iterator[Session]:
        self.init()
        db = self.session_factory()
        try:
            yield db
        finally:
            db.close()

    def check(self) -> dict[str, str]:
        try:
            self.init()
            with self.engine.connect() as connection:
                connection.execute(text("select 1"))
        except Exception as exc:  # pragma: no cover - exact driver failures vary by environment
            return {"status": "unavailable", "detail": exc.__class__.__name__}

        return {"status": "ok", "detail": "reachable"}


def run_schema_upgrades(engine) -> None:
    """Apply small additive upgrades for installs that predate Alembic."""
    inspector = inspect(engine)
    dialect_name = engine.dialect.name
    table_names = inspector.get_table_names()
    with engine.begin() as connection:
        if "ai_invocation_logs" in table_names:
            _upgrade_table(
                connection,
                inspector,
                dialect_name=dialect_name,
                table_name="ai_invocation_logs",
                columns=AI_INVOCATION_LOG_COLUMN_UPGRADES,
                indexes=AI_INVOCATION_LOG_INDEX_UPGRADES,
            )
        if "agent_staged_outputs" in table_names:
            _upgrade_table(
                connection,
                inspector,
                dialect_name=dialect_name,
                table_name="agent_staged_outputs",
                columns=AGENT_STAGED_OUTPUT_COLUMN_UPGRADES,
                indexes=AGENT_STAGED_OUTPUT_INDEX_UPGRADES,
            )
        if "test_cases" in table_names:
            existing_columns = {column["name"] for column in inspector.get_columns("test_cases")}
            _upgrade_table(
                connection,
                inspector,
                dialect_name=dialect_name,
                table_name="test_cases",
                columns=TEST_CASE_COLUMN_UPGRADES,
                indexes=TEST_CASE_INDEX_UPGRADES,
            )
            _backfill_legacy_test_case_columns(connection, existing_columns)


def _upgrade_table(connection, inspector, *, dialect_name: str, table_name: str, columns, indexes) -> None:
    existing_columns = {column["name"] for column in inspector.get_columns(table_name)}
    for column_name, column_type, default_sql in columns:
        if column_name in existing_columns:
            continue
        nullable = default_sql is None
        default_clause = ""
        if default_sql is not None:
            default_clause = f" NOT NULL DEFAULT {json_default_sql(dialect_name, column_name, default_sql)}"
        null_clause = "" if nullable else default_clause
        connection.execute(text(f'ALTER TABLE {table_name} ADD COLUMN "{column_name}" {column_type}{null_clause}'))

    existing_indexes = {index["name"] for index in inspector.get_indexes(table_name)}
    for index_name, column_name in indexes:
        if index_name in existing_indexes:
            continue
        connection.execute(text(f'CREATE INDEX IF NOT EXISTS "{index_name}" ON {table_name} ("{column_name}")'))


def json_default_sql(dialect_name: str, column_name: str, default_sql: str) -> str:
    if default_sql == "'{}'" and dialect_name == "postgresql":
        return "'{}'::json"
    return default_sql


def _backfill_legacy_test_case_columns(connection, existing_columns: set[str]) -> None:
    if "lifecycle_status" not in existing_columns and "status" in existing_columns:
        connection.execute(
            text(
                """
                UPDATE test_cases
                SET lifecycle_status = CASE
                    WHEN status = 'approved' THEN 'active'
                    WHEN status = 'archived' THEN 'archived'
                    ELSE 'draft'
                END
                """
            )
        )

    if "current_module_id" not in existing_columns and "module_id" in existing_columns:
        connection.execute(
            text(
                """
                UPDATE test_cases
                SET current_module_id = module_id
                WHERE current_module_id IS NULL AND module_id IS NOT NULL
                """
            )
        )

    if "source_type" not in existing_columns and "import_batch_id" in existing_columns:
        connection.execute(
            text(
                """
                UPDATE test_cases
                SET source_type = 'import'
                WHERE import_batch_id IS NOT NULL AND import_batch_id != ''
                """
            )
        )

    if "created_by" not in existing_columns and "submitted_by" in existing_columns:
        connection.execute(
            text(
                """
                UPDATE test_cases
                SET created_by = submitted_by
                WHERE submitted_by IS NOT NULL AND submitted_by != ''
                """
            )
        )
