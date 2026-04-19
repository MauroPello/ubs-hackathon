from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from .models import DataSourceRegistration, DocEntry


class _UnsetType:
    pass


_UNSET = _UnsetType()
UpdateField = str | None | _UnsetType


META_SCHEMA = """
CREATE TABLE IF NOT EXISTS data_sources (
    name TEXT PRIMARY KEY,
    type TEXT NOT NULL,
    connection TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS source_docs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    data_source TEXT NOT NULL,
    doc_type TEXT NOT NULL,
    target TEXT,
    content TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    FOREIGN KEY (data_source) REFERENCES data_sources(name) ON DELETE CASCADE
);
"""


class MetaStore:
    def __init__(self, db_path: Path) -> None:
        self.db_path = db_path
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._ensure_schema()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        return conn

    def _ensure_schema(self) -> None:
        with self._connect() as conn:
            conn.executescript(META_SCHEMA)

    def _now(self) -> str:
        return datetime.now(timezone.utc).isoformat()

    def list_data_sources(self) -> list[DataSourceRegistration]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT name, type, connection, created_at, updated_at FROM data_sources ORDER BY name"
            ).fetchall()
        return [DataSourceRegistration(**dict(row)) for row in rows]

    def get_data_source(self, name: str) -> DataSourceRegistration | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT name, type, connection, created_at, updated_at FROM data_sources WHERE name = ?",
                (name,),
            ).fetchone()
        return DataSourceRegistration(**dict(row)) if row else None

    def create_data_source(self, name: str, type_: str, connection: str) -> DataSourceRegistration:
        now = self._now()
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO data_sources (name, type, connection, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (name, type_, connection, now, now),
            )
        created = self.get_data_source(name)
        if created is None:
            raise RuntimeError(f"Failed to create data source: {name}")
        return created

    def update_data_source(
        self,
        name: str,
        type_: str | None = None,
        connection: str | None = None,
    ) -> DataSourceRegistration | None:
        current = self.get_data_source(name)
        if current is None:
            return None
        next_type = type_ if type_ is not None else current.type
        next_connection = connection if connection is not None else current.connection
        now = self._now()
        with self._connect() as conn:
            conn.execute(
                """
                UPDATE data_sources
                SET type = ?, connection = ?, updated_at = ?
                WHERE name = ?
                """,
                (next_type, next_connection, now, name),
            )
        updated = self.get_data_source(name)
        if updated is None:
            raise RuntimeError(f"Failed to update data source: {name}")
        return updated

    def delete_data_source(self, name: str) -> bool:
        with self._connect() as conn:
            result = conn.execute("DELETE FROM data_sources WHERE name = ?", (name,))
        return result.rowcount > 0

    def list_docs(self, data_source: str) -> list[DocEntry]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT id, data_source, doc_type, target, content, created_at, updated_at
                FROM source_docs
                WHERE data_source = ?
                ORDER BY id
                """,
                (data_source,),
            ).fetchall()
        return [DocEntry(**dict(row)) for row in rows]

    def get_doc(self, data_source: str, doc_id: int) -> DocEntry | None:
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT id, data_source, doc_type, target, content, created_at, updated_at
                FROM source_docs
                WHERE data_source = ? AND id = ?
                """,
                (data_source, doc_id),
            ).fetchone()
        return DocEntry(**dict(row)) if row else None

    def create_doc(self, data_source: str, doc_type: str, target: str | None, content: str) -> DocEntry:
        now = self._now()
        with self._connect() as conn:
            cursor = conn.execute(
                """
                INSERT INTO source_docs (data_source, doc_type, target, content, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (data_source, doc_type, target, content, now, now),
            )
            doc_id = int(cursor.lastrowid)
        created = self.get_doc(data_source, doc_id)
        if created is None:
            raise RuntimeError(f"Failed to create doc entry {doc_id} for {data_source}")
        return created

    def update_doc(
        self,
        data_source: str,
        doc_id: int,
        doc_type: UpdateField = _UNSET,
        target: UpdateField = _UNSET,
        content: UpdateField = _UNSET,
    ) -> DocEntry | None:
        if doc_type is None:
            raise ValueError("doc_type cannot be null")
        if content is None:
            raise ValueError("content cannot be null")
        current = self.get_doc(data_source, doc_id)
        if current is None:
            return None
        next_doc_type = current.doc_type if doc_type is _UNSET else doc_type
        next_target = current.target if target is _UNSET else target
        next_content = current.content if content is _UNSET else content
        now = self._now()
        with self._connect() as conn:
            conn.execute(
                """
                UPDATE source_docs
                SET doc_type = ?, target = ?, content = ?, updated_at = ?
                WHERE data_source = ? AND id = ?
                """,
                (next_doc_type, next_target, next_content, now, data_source, doc_id),
            )
        updated = self.get_doc(data_source, doc_id)
        if updated is None:
            raise RuntimeError(f"Failed to update doc entry {doc_id} for {data_source}")
        return updated

    def delete_doc(self, data_source: str, doc_id: int) -> bool:
        with self._connect() as conn:
            result = conn.execute(
                "DELETE FROM source_docs WHERE data_source = ? AND id = ?",
                (data_source, doc_id),
            )
        return result.rowcount > 0
