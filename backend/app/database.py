from __future__ import annotations

from collections.abc import Iterator
from threading import Lock

from sqlalchemy import create_engine
from sqlalchemy import text
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker
from sqlalchemy.pool import StaticPool


class Base(DeclarativeBase):
    pass


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
