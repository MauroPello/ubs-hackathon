from __future__ import annotations

import re
import sqlite3
from abc import ABC, abstractmethod
from typing import Any

from .models import ColumnDoc, DataSourceConfig, ForeignKeyDoc, TableDoc

FORBIDDEN_SQL = re.compile(
    r"\b(insert|update|delete|drop|alter|create|truncate|grant|revoke|merge|replace|vacuum|attach|detach|pragma)\b",
    re.IGNORECASE,
)
ALLOWED_SQL_START = re.compile(r"^\s*(select|with|explain)\b", re.IGNORECASE)


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


class SQLiteDataSource(DataSource):
    def _connect(self, read_only: bool) -> sqlite3.Connection:
        if read_only:
            uri = f"file:{self.config.connection}?mode=ro"
            conn = sqlite3.connect(uri, uri=True)
        else:
            conn = sqlite3.connect(self.config.connection)
        conn.row_factory = sqlite3.Row
        return conn

    def list_tables(self) -> list[str]:
        with self._connect(read_only=True) as conn:
            rows = conn.execute(
                "SELECT name FROM sqlite_master WHERE type IN ('table', 'view') "
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
        with self._connect(read_only=True) as conn:
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
        statement = sql.strip()
        if not ALLOWED_SQL_START.search(statement):
            raise ValueError("Only SELECT/WITH/EXPLAIN statements are allowed")
        if FORBIDDEN_SQL.search(statement):
            raise ValueError("Potentially mutating SQL is not allowed")

        wrapped = f"SELECT * FROM ({statement.rstrip(';')}) AS subq LIMIT ?"

        with self._connect(read_only=True) as conn:
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


def build_data_source(config: DataSourceConfig) -> DataSource:
    if config.type == "sqlite":
        return SQLiteDataSource(config)
    raise ValueError(f"Unsupported data source type: {config.type}")
