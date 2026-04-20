from __future__ import annotations

import json
import re
import threading
import time
from abc import ABC, abstractmethod
from typing import Any, Sequence
from urllib import error as urllib_error
from urllib import request as urllib_request

from sqlalchemy import create_engine, inspect as sqlalchemy_inspect, text
from sqlalchemy.engine import Connection, Engine

from .models import ColumnDoc, DataSourceConfig, ForeignKeyDoc, TableDoc

FORBIDDEN_SQL = re.compile(
    r"\b(insert|update|delete|drop|alter|create|truncate|grant|revoke|merge|replace|vacuum|attach|detach|pragma)\b",
    re.IGNORECASE,
)
ALLOWED_SQL_START = re.compile(r"^\s*(select|with|explain)\b", re.IGNORECASE)
ALLOWED_CYPHER_START = re.compile(
    r"^\s*(match|with|call|unwind|return|profile|explain)\b", re.IGNORECASE
)
FORBIDDEN_CYPHER = re.compile(
    r"\b(create|merge|delete|detach|set|drop|remove|load\s+csv)\b",
    re.IGNORECASE,
)
TEMP_VIEW_NAME = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
SESSION_ID_NAME = re.compile(r"^[A-Za-z0-9_\-]+$")
IDENTIFIER_STRIP_CHARS = '"`[]'


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
    if not conn:
        raise ValueError(
            f"Data source '{config.name}' requires a connection string "
            f"but none was provided"
        )
    if config.type == "sqlite" and "://" not in conn:
        return f"sqlite:///{conn}"
    return conn


# ---------------------------------------------------------------------------
# Abstract base
# ---------------------------------------------------------------------------


class DataSource(ABC):
    def __init__(self, config: DataSourceConfig) -> None:
        self.config = config
        self._sensitive_unqualified: set[str] = set()
        self._sensitive_qualified: set[tuple[str, str]] = set()
        self._sensitive_any_qualified_column: set[str] = set()
        for raw in config.sensitive_columns or []:
            token = self._normalize_identifier_token(raw)
            if not token:
                continue
            if "." in token:
                entity, column = token.split(".", 1)
                if entity and column:
                    self._sensitive_qualified.add((entity, column))
                    self._sensitive_any_qualified_column.add(column)
                    continue
            self._sensitive_unqualified.add(token)

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

    def list_graph_entities(self) -> list[str]:
        raise NotImplementedError("Graph schema is not supported by this source")

    def describe_graph_entity(self, entity: str) -> TableDoc:
        raise NotImplementedError("Graph schema is not supported by this source")

    def execute_graph_read_only(
        self, query: str, limit: int = 200, session_id: str | None = None
    ) -> dict[str, Any]:
        raise NotImplementedError("Graph query is not supported by this source")

    def capabilities(self) -> list[str]:
        return [
            "search_schema",
            "describe_table",
            "execute_query",
            "list_temporary_views",
            "create_temporary_view",
            "drop_temporary_view",
        ]

    @staticmethod
    def _normalize_identifier_token(identifier: str | None) -> str:
        value = str(identifier or "").strip().strip(IDENTIFIER_STRIP_CHARS)
        if not value:
            return ""
        pieces = [
            part.strip().strip(IDENTIFIER_STRIP_CHARS).lower()
            for part in value.split(".")
        ]
        pieces = [part for part in pieces if part]
        if not pieces:
            return ""
        return ".".join(pieces)

    def _is_sensitive_column(self, column: str, table: str | None = None) -> bool:
        normalized_column = self._normalize_identifier_token(column)
        if not normalized_column:
            return False

        if normalized_column in self._sensitive_unqualified:
            return True
        if normalized_column in self._sensitive_any_qualified_column:
            return True

        if "." in normalized_column:
            left, right = normalized_column.split(".", 1)
            if (left, right) in self._sensitive_qualified:
                return True
            if right in self._sensitive_unqualified:
                return True

        normalized_table = self._normalize_identifier_token(table)
        if (
            normalized_table
            and (normalized_table, normalized_column) in self._sensitive_qualified
        ):
            return True

        return False

    def _sanitize_result_rows(
        self, columns: list[str], rows: Sequence[Any], table: str | None = None
    ) -> tuple[list[str], list[dict[str, Any]], list[str]]:
        safe_indexes: list[int] = []
        safe_columns: list[str] = []
        masked_columns: list[str] = []
        for index, column_name in enumerate(columns):
            if self._is_sensitive_column(column_name, table=table):
                masked_columns.append(column_name)
            else:
                safe_indexes.append(index)
                safe_columns.append(column_name)
        payload_rows = [{columns[i]: row[i] for i in safe_indexes} for row in rows]
        return safe_columns, payload_rows, masked_columns

    def catalog_docs(self) -> list[TableDoc]:
        docs: dict[str, TableDoc] = {}
        for name in self.list_tables():
            docs[name] = self.table_doc(name)
        try:
            for entity in self.list_graph_entities():
                docs[entity] = self.describe_graph_entity(entity)
        except NotImplementedError:
            pass
        return list(docs.values())


# ---------------------------------------------------------------------------
# SQLAlchemy data source — handles all SQL-like databases
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
                {"check_same_thread": False} if config.type == "sqlite" else {}
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

    def _quote_qualified_identifier(self, identifier: str) -> str:
        preparer = self._engine.dialect.identifier_preparer
        raw_parts = identifier.split(".")
        if not identifier or any(part == "" for part in raw_parts):
            raise ValueError(f"Malformed identifier: {identifier!r}")
        return ".".join(preparer.quote_identifier(part) for part in raw_parts)

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
            quoted_name = self._quote_qualified_identifier(name)
            conn.execute(text(f"DROP VIEW IF EXISTS {quoted_name}"))
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
            quoted_table = self._quote_qualified_identifier(table)
            row = conn.execute(text(f"SELECT COUNT(*) FROM {quoted_table}")).fetchone()
            return int(row[0]) if row else None
        except Exception:
            return None

    def _sample_values_locked(self, table: str, column: str) -> list[str]:
        try:
            conn = self._connection()
            quoted_table = self._quote_qualified_identifier(table)
            quoted_column = self._quote_qualified_identifier(column)
            rows = conn.execute(
                text(
                    f"SELECT DISTINCT {quoted_column} FROM {quoted_table}"
                    f" WHERE {quoted_column} IS NOT NULL LIMIT 5"
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
            names: set[str] = set(insp.get_table_names()) | set(insp.get_view_names())
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
                is_sensitive = self._is_sensitive_column(col["name"], table=table)
                samples = (
                    []
                    if is_sensitive
                    else self._sample_values_locked(table, col["name"])
                )
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
            try:
                rows = result.fetchmany(limit + 1)
                columns = list(result.keys())
            finally:
                result.close()

        truncated = len(rows) > limit
        rows = rows[:limit]
        safe_columns, payload_rows, masked_columns = self._sanitize_result_rows(
            columns, rows
        )
        return {
            "columns": safe_columns,
            "rows": payload_rows,
            "row_count": len(payload_rows),
            "truncated": truncated,
            "limit": limit,
            "masked_columns": masked_columns,
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
            quoted_name = self._quote_qualified_identifier(actual_name)
            temp_kw = "TEMP " if self._supports_temp_view_syntax() else ""
            conn = self._connection()
            try:
                conn.execute(text(f"CREATE {temp_kw}VIEW {quoted_name} AS {statement}"))
                conn.commit()
            except Exception as exc:
                if temp_kw:
                    # Dialect advertised TEMP VIEW support but failed; fall back
                    # to a regular CREATE VIEW.
                    conn.rollback()
                    try:
                        conn.execute(text(f"CREATE VIEW {quoted_name} AS {statement}"))
                        conn.commit()
                    except Exception as fallback_exc:
                        conn.rollback()
                        raise TemporaryViewError(
                            f"Failed to create view '{actual_name}': "
                            f"TEMP VIEW failed ({exc}); VIEW fallback failed "
                            f"({fallback_exc})"
                        ) from fallback_exc
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
        conn = getattr(self, "_conn", None)
        if conn is not None:
            try:
                conn.close()
            except Exception:
                pass
        engine = getattr(self, "_engine", None)
        if engine is not None:
            try:
                engine.dispose()
            except Exception:
                pass


# Backward-compat alias – existing code that imports SQLiteDataSource keeps
# working; the SQLAlchemy implementation handles SQLite automatically.
SQLiteDataSource = SQLAlchemyDataSource


# ---------------------------------------------------------------------------
# Upstream MCP data source — proxies tool calls to an external MCP server
# ---------------------------------------------------------------------------


class UpstreamMCPDataSource(DataSource):
    """Data source that proxies tool calls to a configured upstream MCP server.

    Used for **graph** and **documents** source types.  The ``endpoint`` and
    ``exposed_tools`` are read from ``config.options`` which is populated by
    :func:`~.source_runtime.build_runtime_source_config`.
    """

    def __init__(self, config: DataSourceConfig) -> None:
        super().__init__(config)
        opts: dict[str, Any] = dict(config.options or {})
        self._endpoint: str = str(opts.get("endpoint") or "").strip()
        self._exposed_tools: list[str] = list(opts.get("exposed_tools") or [])

    # ------------------------------------------------------------------
    # Delegation helper
    # ------------------------------------------------------------------

    def _delegate_tool(self, tool: str, arguments: dict[str, Any]) -> dict[str, Any]:
        if not self._endpoint:
            return {
                "delegated": False,
                "reason": "No endpoint configured for upstream MCP server",
                "tool": tool,
                "arguments": arguments,
            }
        payload = json.dumps(
            {
                "data_source": self.config.name,
                "tool": tool,
                "arguments": arguments,
            }
        ).encode("utf-8")
        req = urllib_request.Request(
            self._endpoint,
            data=payload,
            method="POST",
            headers={"Content-Type": "application/json"},
        )
        try:
            with urllib_request.urlopen(req, timeout=30) as resp:
                body = resp.read().decode("utf-8")
            data = json.loads(body) if body else {}
            return {"delegated": True, "tool": tool, "result": data}
        except (urllib_error.URLError, json.JSONDecodeError) as exc:
            raise ValueError(f"Upstream MCP call failed for '{tool}': {exc}") from exc

    # ------------------------------------------------------------------
    # DataSource interface – minimal SQL stubs
    # ------------------------------------------------------------------

    def list_tables(self) -> list[str]:
        return []

    def table_doc(self, table: str) -> TableDoc:
        raise ValueError(
            f"Data source '{self.config.name}' does not support SQL schema discovery"
        )

    def execute_read_only(
        self, sql: str, limit: int = 200, session_id: str | None = None
    ) -> dict[str, Any]:
        raise ValueError(
            f"Data source '{self.config.name}' does not support SQL queries; use call_upstream_tool"
        )

    def list_temporary_views(
        self, session_id: str | None = None
    ) -> list[dict[str, Any]]:
        return []

    def create_temporary_view(
        self,
        sql: str,
        view_name: str | None = None,
        ttl_seconds: int = 3600,
        session_id: str | None = None,
    ) -> dict[str, Any]:
        raise TemporaryViewError(
            f"Data source '{self.config.name}' does not support temporary SQL views"
        )

    def drop_temporary_view(
        self, view_name: str, session_id: str | None = None
    ) -> dict[str, Any]:
        raise TemporaryViewError(
            f"Data source '{self.config.name}' does not support temporary SQL views"
        )

    # ------------------------------------------------------------------
    # Upstream MCP operations
    # ------------------------------------------------------------------

    def get_exposed_tools(self) -> list[str]:
        """Return the list of tool names exposed by this data source."""
        return list(self._exposed_tools)

    def call_upstream_tool(
        self, tool_name: str, arguments: dict[str, Any]
    ) -> dict[str, Any]:
        """Forward a tool call to the upstream MCP server."""
        if tool_name not in self._exposed_tools:
            raise ValueError(
                f"Tool '{tool_name}' is not exposed by data source '{self.config.name}'. "
                f"Available: {self._exposed_tools}"
            )
        return self._delegate_tool(tool_name, arguments)

    def capabilities(self) -> list[str]:
        return list(self._exposed_tools)


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------

# Source types that are handled by UpstreamMCPDataSource.
_UPSTREAM_TYPES: frozenset[str] = frozenset({"graph", "documents"})

# Source types handled by SQLAlchemyDataSource (common SQL dialects).
_SQL_TYPES: frozenset[str] = frozenset(
    {"sql", "sqlite", "postgresql", "postgres", "mysql", "mssql", "oracle"}
)


def build_data_source(config: DataSourceConfig) -> DataSource:
    """Create the appropriate :class:`DataSource` for *config*.

    Dispatch rules (checked in order):

    1. ``config.type`` in ``{graph, documents}`` → :class:`UpstreamMCPDataSource`
    2. Everything else → :class:`SQLAlchemyDataSource`
    """
    source_type = (config.type or "").strip().lower()

    if source_type in _UPSTREAM_TYPES:
        return UpstreamMCPDataSource(config)

    # Default: SQL-like source (SQLite, PostgreSQL, MySQL, etc.)
    return SQLAlchemyDataSource(config)
