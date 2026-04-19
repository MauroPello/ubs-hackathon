from __future__ import annotations

import re
import sqlite3
import threading
import time
from abc import ABC, abstractmethod
from typing import Any

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


class DataSource(ABC):
    def __init__(self, config: DataSourceConfig) -> None:
        self.config = config

    @abstractmethod
    def list_tables(self) -> list[str]:
        raise NotImplementedError

    @abstractmethod
    def table_doc(self, table: str) -> TableDoc:
        raise NotImplementedError

    @abstractmethod
    def execute_read_only(self, sql: str, limit: int = 200) -> dict[str, Any]:
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


class SQLiteDataSource(DataSource):
    def __init__(self, config: DataSourceConfig) -> None:
        super().__init__(config)
        self._lock = threading.RLock()
        self._conn: sqlite3.Connection | None = None
        self._temp_views: dict[str, dict[str, Any]] = {}
        self._temp_view_counter = 0

    def _connect(self, read_only: bool) -> sqlite3.Connection:
        if read_only:
            uri = f"file:{self.config.connection}?mode=ro"
            conn = sqlite3.connect(uri, uri=True)
        else:
            conn = sqlite3.connect(self.config.connection)
        conn.row_factory = sqlite3.Row
        return conn

    def _connection(self) -> sqlite3.Connection:
        if self._conn is None:
            self._conn = self._connect(read_only=True)
        return self._conn

    def _purge_expired_temp_views_locked(self) -> None:
        now = time.time()
        expired = [
            name
            for name, meta in self._temp_views.items()
            if float(meta["expires_at"]) <= now
        ]
        if not expired:
            return

        conn = self._connection()
        for name in expired:
            try:
                conn.execute(f'DROP VIEW IF EXISTS "{name}"')
            finally:
                self._temp_views.pop(name, None)
        conn.commit()

    def _existing_object_names_locked(self) -> set[str]:
        conn = self._connection()
        rows = conn.execute(
            "SELECT name FROM sqlite_master WHERE type IN ('table', 'view') "
            "AND name NOT LIKE 'sqlite_%' "
            "UNION SELECT name FROM sqlite_temp_master WHERE type IN ('table', 'view') "
            "AND name NOT LIKE 'sqlite_%'"
        ).fetchall()
        return {row["name"] for row in rows}

    def _make_temp_view_name(self, view_name: str | None) -> str:
        candidate_hint = (view_name or "").strip()
        if candidate_hint:
            cleaned_hint = re.sub(r"[^A-Za-z0-9_]+", "_", candidate_hint).strip("_")
            if cleaned_hint and not cleaned_hint[0].isdigit():
                base_name = f"mcp_view_{cleaned_hint}"
            else:
                base_name = f"mcp_view_{cleaned_hint}" if cleaned_hint else "mcp_view"
        else:
            base_name = "mcp_view"

        if not TEMP_VIEW_NAME.match(base_name):
            base_name = "mcp_view"

        existing = self._existing_object_names_locked() | set(self._temp_views)
        candidate = base_name
        suffix = 2
        while candidate in existing:
            candidate = f"{base_name}_{suffix}"
            suffix += 1
        return candidate

    def _normalize_session_id(self, session_id: str | None) -> str:
        raw_session_id = (session_id or "global").strip()
        if not raw_session_id:
            raw_session_id = "global"
        cleaned = re.sub(r"[^A-Za-z0-9_-]+", "_", raw_session_id).strip("_")
        if not cleaned:
            cleaned = "global"
        return cleaned

    def _session_view_prefix(self, session_id: str | None) -> str:
        return f"mcp_view_{self._normalize_session_id(session_id)}_"

    def _validate_select_sql(self, sql: str, allow_explain: bool = True) -> str:
        statement = sql.strip().rstrip(";")
        if not statement:
            raise ValueError("SQL cannot be empty")
        if ";" in statement:
            raise ValueError("Only a single SQL statement is allowed")
        pattern = ALLOWED_SQL_START if allow_explain else re.compile(
            r"^\s*(select|with)\b", re.IGNORECASE
        )
        if not pattern.search(statement):
            raise ValueError("Only SELECT/WITH statements are allowed")
        if FORBIDDEN_SQL.search(statement):
            raise ValueError("Potentially mutating SQL is not allowed")
        return statement

    def list_tables(self) -> list[str]:
        with self._lock:
            self._purge_expired_temp_views_locked()
            conn = self._connection()
            rows = conn.execute(
                "SELECT name FROM sqlite_master WHERE type IN ('table', 'view') "
                "AND name NOT LIKE 'sqlite_%' "
                "UNION SELECT name FROM sqlite_temp_master WHERE type IN ('table', 'view') "
                "AND name NOT LIKE 'sqlite_%' ORDER BY name"
            ).fetchall()
        return [r["name"] for r in rows]

    def _table_type(self, conn: sqlite3.Connection, table: str) -> str:
        row = conn.execute(
            "SELECT type FROM sqlite_master WHERE name = ? LIMIT 1", (table,)
        ).fetchone()
        return (row["type"] if row else "table").lower()

    def _row_count_estimate(self, conn: sqlite3.Connection, table: str) -> int | None:
        try:
            row = conn.execute(f"SELECT COUNT(*) AS c FROM \"{table}\"").fetchone()
            return int(row["c"]) if row else None
        except sqlite3.Error:
            return None

    def _sample_values(self, conn: sqlite3.Connection, table: str, column: str) -> list[str]:
        query = (
            f"SELECT DISTINCT \"{column}\" AS val FROM \"{table}\" "
            f"WHERE \"{column}\" IS NOT NULL LIMIT 5"
        )
        try:
            rows = conn.execute(query).fetchall()
        except sqlite3.Error:
            return []
        return [str(r["val"]) for r in rows if r["val"] is not None]

    def table_doc(self, table: str) -> TableDoc:
        with self._lock:
            self._purge_expired_temp_views_locked()
            conn = self._connection()
            info = conn.execute(f'PRAGMA table_info("{table}")').fetchall()
            if not info:
                raise ValueError(f"Table not found: {table}")

            columns: list[ColumnDoc] = []
            for c in info:
                samples = self._sample_values(conn, table, c["name"])
                columns.append(
                    ColumnDoc(
                        name=c["name"],
                        data_type=c["type"] or "TEXT",
                        nullable=not bool(c["notnull"]),
                        description=None,
                        sample_values=samples,
                    )
                )

            fk_rows = conn.execute(f'PRAGMA foreign_key_list("{table}")').fetchall()
            fks = [
                ForeignKeyDoc(
                    column=row["from"],
                    ref_table=row["table"],
                    ref_column=row["to"],
                )
                for row in fk_rows
            ]

            return TableDoc(
                data_source=self.config.name,
                table=table,
                table_type=self._table_type(conn, table),
                description=None,
                row_count_estimate=self._row_count_estimate(conn, table),
                columns=columns,
                foreign_keys=fks,
            )

    def execute_read_only(self, sql: str, limit: int = 200) -> dict[str, Any]:
        statement = self._validate_select_sql(sql)

        wrapped = f"SELECT * FROM ({statement.rstrip(';')}) AS subq LIMIT ?"

        with self._lock:
            self._purge_expired_temp_views_locked()
            conn = self._connection()
            rows = conn.execute(wrapped, (limit + 1,)).fetchall()

        truncated = len(rows) > limit
        rows = rows[:limit]

        payload_rows = [dict(r) for r in rows]
        columns = list(payload_rows[0].keys()) if payload_rows else []
        return {
            "columns": columns,
            "rows": payload_rows,
            "row_count": len(payload_rows),
            "truncated": truncated,
            "limit": limit,
        }

    def list_temporary_views(self, session_id: str | None = None) -> list[dict[str, Any]]:
        with self._lock:
            self._purge_expired_temp_views_locked()
            prefix = self._session_view_prefix(session_id)
            views = sorted(
                [item for item in self._temp_views.values() if item["name"].startswith(prefix)],
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
            conn = self._connection()
            session_prefix = self._session_view_prefix(session_id)
            actual_name = f"{session_prefix}{self._make_temp_view_name(view_name)}"
            conn.execute(f'CREATE TEMP VIEW "{actual_name}" AS {statement}')
            conn.commit()

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

            conn = self._connection()
            conn.execute(f'DROP VIEW IF EXISTS "{view_name}"')
            conn.commit()
            self._temp_views.pop(view_name, None)
            return {"name": view_name, "deleted": True}

    def __del__(self) -> None:
        conn = self._conn
        if conn is not None:
            try:
                conn.close()
            except Exception:
                pass


def build_data_source(config: DataSourceConfig) -> DataSource:
    if config.type == "sqlite":
        return SQLiteDataSource(config)
    raise ValueError(f"Unsupported data source type: {config.type}")
