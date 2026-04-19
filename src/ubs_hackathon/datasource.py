from __future__ import annotations

import re
import threading
import time
from abc import ABC, abstractmethod
from typing import Any

from sqlalchemy import create_engine, inspect as sqlalchemy_inspect, text
from sqlalchemy.engine import Connection, Engine

from .models import ColumnDoc, DataSourceConfig, ForeignKeyDoc, TableDoc

FORBIDDEN_SQL = re.compile(
    r"\b(insert|update|delete|drop|alter|create|truncate|grant|revoke|merge|replace|vacuum|attach|detach|pragma)\b",
    re.IGNORECASE,
)
ALLOWED_SQL_START = re.compile(r"^\s*(select|with|explain)\b", re.IGNORECASE)
TEMP_VIEW_NAME = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
SESSION_ID_NAME = re.compile(r"^[A-Za-z0-9_\-]+$")


class TemporaryViewError(ValueError):
    pass


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _resolve_connection_url(config: DataSourceConfig) -> str:
    """Return a SQLAlchemy connection URL for *config*.

    Legacy entries that set ``type: sqlite`` with a bare file path (no
    ``://`` scheme) are automatically promoted to ``sqlite:///path`` so
    existing configs keep working without modification.
    """
    conn = config.connection
    if config.type == "sqlite" and "://" not in conn:
        return f"sqlite:///{conn}"
    return conn


# ---------------------------------------------------------------------------
# Abstract base
# ---------------------------------------------------------------------------

class DataSource(ABC):
    def __init__(self, config: DataSourceConfig) -> None:
        self.config = config

    # ------------------------------------------------------------------
    # SQL safety helpers – shared by all relational data sources
    # ------------------------------------------------------------------

    @staticmethod
    def _validate_select_sql(sql: str, allow_explain: bool = True) -> str:
        statement = sql.strip().rstrip(";")
        if not statement:
            raise ValueError("SQL cannot be empty")
        if ";" in statement:
            raise ValueError("Only a single SQL statement is allowed")
        pattern = (
            ALLOWED_SQL_START
            if allow_explain
            else re.compile(r"^\s*(select|with)\b", re.IGNORECASE)
        )
        if not pattern.search(statement):
            raise ValueError("Only SELECT/WITH statements are allowed")
        if FORBIDDEN_SQL.search(statement):
            raise ValueError("Potentially mutating SQL is not allowed")
        return statement

    @abstractmethod
    def list_tables(self) -> list[str]:
        raise NotImplementedError

    @abstractmethod
    def table_doc(self, table: str) -> TableDoc:
        raise NotImplementedError

    @abstractmethod
    def execute_read_only(
        self, sql: str, limit: int = 200, session_id: str | None = None
    ) -> dict[str, Any]:
        raise NotImplementedError

    @abstractmethod
    def list_temporary_views(
        self, session_id: str | None = None
    ) -> list[dict[str, Any]]:
        raise NotImplementedError

    @abstractmethod
    def create_temporary_view(
        self,
        sql: str,
        view_name: str | None = None,
        ttl_seconds: int = 3600,
        session_id: str | None = None,
    ) -> dict[str, Any]:
        raise NotImplementedError

    @abstractmethod
    def drop_temporary_view(
        self, view_name: str, session_id: str | None = None
    ) -> dict[str, Any]:
        raise NotImplementedError


# ---------------------------------------------------------------------------
# Universal SQLAlchemy implementation
# ---------------------------------------------------------------------------

class SQLAlchemyDataSource(DataSource):
    """Universal data source backed by any SQLAlchemy-supported DBMS.

    The ``connection`` field in :class:`~.models.DataSourceConfig` must be a
    `SQLAlchemy connection URL
    <https://docs.sqlalchemy.org/en/20/core/engines.html#database-urls>`_
    (e.g. ``postgresql+psycopg2://user:pw@host/db``,
    ``mysql+pymysql://user:pw@host/db``, ``sqlite:///path/to/file.db``).

    Legacy configs that use ``type: sqlite`` with a bare file path are
    auto-converted to a valid SQLite URL so they continue to work unchanged.

    Dialect-specific drivers (``psycopg2``, ``pymysql``, ``pyodbc``, etc.)
    must be installed separately; see the optional dependency groups in
    ``pyproject.toml``.
    """

    # Dialects whose engines support CREATE TEMP VIEW natively.
    # For all other dialects a regular CREATE VIEW is used (and dropped on
    # TTL expiry or explicit drop_temporary_view call).
    _TEMP_VIEW_DIALECTS: frozenset[str] = frozenset({"sqlite", "postgresql"})

    def __init__(self, config: DataSourceConfig) -> None:
        super().__init__(config)
        self._lock = threading.RLock()
        url = _resolve_connection_url(config)
        self._engine: Engine = create_engine(
            url,
            pool_pre_ping=True,
            # SQLite needs check_same_thread=False when used across threads.
            connect_args=(
                {"check_same_thread": False}
                if config.type == "sqlite"
                else {}
            ),
        )
        # A single persistent connection is kept open so that session-local
        # TEMP VIEWs (SQLite / PostgreSQL) remain visible across queries.
        self._conn: Connection | None = None
        self._temp_views: dict[str, dict[str, Any]] = {}

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _dialect(self) -> str:
        return self._engine.dialect.name

    def _connection(self) -> Connection:
        if self._conn is None or self._conn.closed:
            self._conn = self._engine.connect()
        return self._conn

    def _supports_temp_view_syntax(self) -> bool:
        return self._dialect() in self._TEMP_VIEW_DIALECTS

    def _purge_expired_temp_views_locked(self) -> None:
        now = time.time()
        expired = [
            name
            for name, meta in self._temp_views.items()
            if float(meta["expires_at"]) <= now
        ]
        for name in expired:
            self._try_drop_view_locked(name)
            self._temp_views.pop(name, None)

    def _try_drop_view_locked(self, name: str) -> None:
        try:
            conn = self._connection()
            conn.execute(text(f'DROP VIEW IF EXISTS "{name}"'))
            conn.commit()
        except Exception:
            pass

    def _existing_names_locked(self) -> set[str]:
        insp = sqlalchemy_inspect(self._engine)
        names: set[str] = set(insp.get_table_names()) | set(insp.get_view_names())
        names |= set(self._temp_views.keys())
        return names

    def _normalize_session_id(self, session_id: str | None) -> str:
        raw = (session_id or "").strip() or "global"
        cleaned = re.sub(r"[^A-Za-z0-9_-]+", "_", raw).strip("_") or "global"
        return cleaned

    def _session_view_prefix(self, session_id: str | None) -> str:
        return f"mcp_view_{self._normalize_session_id(session_id)}_"

    def _make_temp_view_name(self, view_name: str | None) -> str:
        candidate_hint = (view_name or "").strip()
        if candidate_hint:
            cleaned = re.sub(r"[^A-Za-z0-9_]+", "_", candidate_hint).strip("_")
            base = (
                f"mcp_view_{cleaned}"
                if (cleaned and not cleaned[0].isdigit())
                else "mcp_view"
            )
        else:
            base = "mcp_view"

        if not TEMP_VIEW_NAME.match(base):
            base = "mcp_view"

        existing = self._existing_names_locked()
        candidate = base
        suffix = 2
        while candidate in existing:
            candidate = f"{base}_{suffix}"
            suffix += 1
        return candidate

    def _row_count_estimate_locked(self, table: str) -> int | None:
        try:
            conn = self._connection()
            row = conn.execute(text(f'SELECT COUNT(*) FROM "{table}"')).fetchone()
            return int(row[0]) if row else None
        except Exception:
            return None

    def _sample_values_locked(self, table: str, column: str) -> list[str]:
        try:
            conn = self._connection()
            rows = conn.execute(
                text(
                    f'SELECT DISTINCT "{column}" FROM "{table}"'
                    f' WHERE "{column}" IS NOT NULL LIMIT 5'
                )
            ).fetchall()
            return [str(r[0]) for r in rows if r[0] is not None]
        except Exception:
            return []

    # ------------------------------------------------------------------
    # DataSource interface
    # ------------------------------------------------------------------

    def list_tables(self) -> list[str]:
        with self._lock:
            self._purge_expired_temp_views_locked()
            insp = sqlalchemy_inspect(self._engine)
            names: set[str] = (
                set(insp.get_table_names()) | set(insp.get_view_names())
            )
            # TEMP VIEWs may not appear in the inspector; add tracked ones.
            names |= set(self._temp_views.keys())
            return sorted(names)

    def table_doc(self, table: str) -> TableDoc:
        with self._lock:
            self._purge_expired_temp_views_locked()
            insp = sqlalchemy_inspect(self._engine)
            try:
                cols_info = insp.get_columns(table)
            except Exception as exc:
                raise ValueError(f"Table not found: {table}") from exc
            if not cols_info:
                raise ValueError(f"Table not found: {table}")

            columns: list[ColumnDoc] = []
            for col in cols_info:
                samples = self._sample_values_locked(table, col["name"])
                columns.append(
                    ColumnDoc(
                        name=col["name"],
                        data_type=str(col["type"]),
                        nullable=bool(col.get("nullable", True)),
                        description=None,
                        sample_values=samples,
                    )
                )

            fks: list[ForeignKeyDoc] = []
            try:
                for fk in insp.get_foreign_keys(table):
                    for local_col, ref_col in zip(
                        fk["constrained_columns"], fk["referred_columns"]
                    ):
                        fks.append(
                            ForeignKeyDoc(
                                column=local_col,
                                ref_table=fk["referred_table"],
                                ref_column=ref_col,
                            )
                        )
            except Exception:
                pass

            obj_type = "view" if table in insp.get_view_names() else "table"

            return TableDoc(
                data_source=self.config.name,
                table=table,
                table_type=obj_type,
                description=None,
                row_count_estimate=self._row_count_estimate_locked(table),
                columns=columns,
                foreign_keys=fks,
            )

    def execute_read_only(
        self, sql: str, limit: int = 200, session_id: str | None = None
    ) -> dict[str, Any]:
        statement = self._validate_select_sql(sql)

        with self._lock:
            self._purge_expired_temp_views_locked()
            conn = self._connection()
            result = conn.execute(text(statement))
            rows = result.fetchmany(limit + 1)
            columns = list(result.keys())

        truncated = len(rows) > limit
        rows = rows[:limit]
        payload_rows = [dict(zip(columns, row)) for row in rows]
        return {
            "columns": columns,
            "rows": payload_rows,
            "row_count": len(payload_rows),
            "truncated": truncated,
            "limit": limit,
        }

    def list_temporary_views(
        self, session_id: str | None = None
    ) -> list[dict[str, Any]]:
        with self._lock:
            self._purge_expired_temp_views_locked()
            prefix = self._session_view_prefix(session_id)
            views = sorted(
                [
                    item
                    for item in self._temp_views.values()
                    if item["name"].startswith(prefix)
                ],
                key=lambda item: (float(item["created_at"]), str(item["name"])),
            )
            return [
                {
                    "name": item["name"],
                    "created_at": item["created_at"],
                    "expires_at": item["expires_at"],
                    "ttl_seconds": item["ttl_seconds"],
                    "sql": item["sql"],
                }
                for item in views
            ]

    def create_temporary_view(
        self,
        sql: str,
        view_name: str | None = None,
        ttl_seconds: int = 3600,
        session_id: str | None = None,
    ) -> dict[str, Any]:
        if ttl_seconds <= 0:
            raise TemporaryViewError("ttl_seconds must be greater than zero")

        statement = self._validate_select_sql(sql, allow_explain=False)

        with self._lock:
            self._purge_expired_temp_views_locked()
            session_prefix = self._session_view_prefix(session_id)
            actual_name = f"{session_prefix}{self._make_temp_view_name(view_name)}"
            temp_kw = "TEMP " if self._supports_temp_view_syntax() else ""
            conn = self._connection()
            try:
                conn.execute(
                    text(f'CREATE {temp_kw}VIEW "{actual_name}" AS {statement}')
                )
                conn.commit()
            except Exception as exc:
                if temp_kw:
                    # Dialect advertised TEMP VIEW support but failed; fall back
                    # to a regular CREATE VIEW.
                    conn.rollback()
                    conn.execute(
                        text(f'CREATE VIEW "{actual_name}" AS {statement}')
                    )
                    conn.commit()
                else:
                    conn.rollback()
                    raise TemporaryViewError(
                        f"Failed to create view '{actual_name}': {exc}"
                    ) from exc

            created_at = time.time()
            expires_at = created_at + ttl_seconds
            self._temp_views[actual_name] = {
                "name": actual_name,
                "session_id": self._normalize_session_id(session_id),
                "created_at": created_at,
                "expires_at": expires_at,
                "ttl_seconds": ttl_seconds,
                "sql": statement,
            }
            return self._temp_views[actual_name].copy()

    def drop_temporary_view(
        self, view_name: str, session_id: str | None = None
    ) -> dict[str, Any]:
        with self._lock:
            self._purge_expired_temp_views_locked()
            meta = self._temp_views.get(view_name)
            if meta is None:
                raise TemporaryViewError(f"Unknown temporary view: {view_name}")
            if meta["session_id"] != self._normalize_session_id(session_id):
                raise TemporaryViewError(f"Unknown temporary view: {view_name}")

            self._try_drop_view_locked(view_name)
            self._temp_views.pop(view_name, None)
            return {"name": view_name, "deleted": True}

    def __del__(self) -> None:
        conn = self._conn
        if conn is not None:
            try:
                conn.close()
            except Exception:
                pass
        try:
            self._engine.dispose()
        except Exception:
            pass


# ---------------------------------------------------------------------------
# Backward-compat alias – existing code that imports SQLiteDataSource keeps
# working; the SQLAlchemy implementation handles SQLite automatically.
# ---------------------------------------------------------------------------
SQLiteDataSource = SQLAlchemyDataSource


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------

def build_data_source(config: DataSourceConfig) -> DataSource:
    """Return a :class:`DataSource` for *config*.

    Any SQLAlchemy-supported database is accepted.  The ``connection`` field
    must be a valid `SQLAlchemy database URL
    <https://docs.sqlalchemy.org/en/20/core/engines.html#database-urls>`_.
    Legacy ``type: sqlite`` entries with a bare file path are promoted to a
    ``sqlite:///`` URL automatically.
    """
    return SQLAlchemyDataSource(config)
