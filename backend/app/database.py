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
    if "ai_invocation_logs" not in inspector.get_table_names():
        return

    existing_columns = {column["name"] for column in inspector.get_columns("ai_invocation_logs")}
    dialect_name = engine.dialect.name
    with engine.begin() as connection:
        for column_name, column_type, default_sql in AI_INVOCATION_LOG_COLUMN_UPGRADES:
            if column_name in existing_columns:
                continue
            nullable = default_sql is None
            default_clause = ""
            if default_sql is not None:
                default_clause = f" NOT NULL DEFAULT {json_default_sql(dialect_name, column_name, default_sql)}"
            null_clause = "" if nullable else default_clause
            connection.execute(text(f'ALTER TABLE ai_invocation_logs ADD COLUMN "{column_name}" {column_type}{null_clause}'))

        existing_indexes = {index["name"] for index in inspector.get_indexes("ai_invocation_logs")}
        for index_name, column_name in AI_INVOCATION_LOG_INDEX_UPGRADES:
            if index_name in existing_indexes:
                continue
            connection.execute(text(f'CREATE INDEX IF NOT EXISTS "{index_name}" ON ai_invocation_logs ("{column_name}")'))


def json_default_sql(dialect_name: str, column_name: str, default_sql: str) -> str:
    if column_name == "usage" and dialect_name == "postgresql":
        return "'{}'::json"
    return default_sql
