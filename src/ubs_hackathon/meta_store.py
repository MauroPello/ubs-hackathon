from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone, timedelta
from pathlib import Path

from .models import DataSourceRegistration, DocEntry, UpstreamMCPServerConfigRecord, AuditLogEntry


class _Unset:
    pass


_UNSET = _Unset()
UpdateField = str | None | _Unset


META_SCHEMA = """
CREATE TABLE IF NOT EXISTS data_sources (
    name TEXT PRIMARY KEY,
    type TEXT NOT NULL,
    connection TEXT NOT NULL,
    sensitive_columns TEXT NOT NULL DEFAULT '[]',
    description TEXT,
    upstream_mcp_server_config_id TEXT,
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

CREATE TABLE IF NOT EXISTS audit_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp TEXT NOT NULL,
    action TEXT NOT NULL,
    details TEXT,
    actor TEXT NOT NULL DEFAULT 'System',
    status TEXT NOT NULL DEFAULT 'Success',
    latency_ms INTEGER
);

CREATE TABLE IF NOT EXISTS upstream_mcp_server_configs (
    id TEXT PRIMARY KEY,
    server_id TEXT NOT NULL,
    name TEXT NOT NULL,
    endpoint TEXT,
    auth TEXT NOT NULL DEFAULT '{}',
    exposed_tools TEXT NOT NULL DEFAULT '[]',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
"""


def _column_exists(conn: sqlite3.Connection, table: str, column: str) -> bool:
    rows = conn.execute(f"PRAGMA table_info({table})").fetchall()
    return any(row[1] == column for row in rows)


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
            if not _column_exists(conn, "data_sources", "description"):
                conn.execute("ALTER TABLE data_sources ADD COLUMN description TEXT")
            if not _column_exists(conn, "data_sources", "sensitive_columns"):
                conn.execute(
                    "ALTER TABLE data_sources ADD COLUMN sensitive_columns TEXT NOT NULL DEFAULT '[]'"
                )
            if not _column_exists(conn, "data_sources", "upstream_mcp_server_config_id"):
                conn.execute(
                    "ALTER TABLE data_sources ADD COLUMN upstream_mcp_server_config_id TEXT"
                )

    def _now(self) -> str:
        return datetime.now(timezone.utc).isoformat()

    @staticmethod
    def _normalize_sensitive_columns(columns: list[str] | None) -> list[str]:
        normalized: list[str] = []
        seen: set[str] = set()
        for raw in columns or []:
            value = str(raw).strip()
            if not value or value in seen:
                continue
            seen.add(value)
            normalized.append(value)
        return normalized

    @staticmethod
    def _decode_sensitive_columns(raw: str | None) -> list[str]:
        if not raw:
            return []
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError:
            return []
        if not isinstance(parsed, list):
            return []
        return MetaStore._normalize_sensitive_columns([str(item) for item in parsed])

    @staticmethod
    def _row_to_registration(row: sqlite3.Row) -> DataSourceRegistration:
        payload = dict(row)
        payload["sensitive_columns"] = MetaStore._decode_sensitive_columns(
            payload.get("sensitive_columns")
        )
        return DataSourceRegistration(**payload)

    def list_data_sources(self) -> list[DataSourceRegistration]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT name, type, connection, sensitive_columns, description, upstream_mcp_server_config_id, created_at, updated_at FROM data_sources ORDER BY name"
            ).fetchall()
        return [self._row_to_registration(row) for row in rows]

    def get_data_source(self, name: str) -> DataSourceRegistration | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT name, type, connection, sensitive_columns, description, upstream_mcp_server_config_id, created_at, updated_at FROM data_sources WHERE name = ?",
                (name,),
            ).fetchone()
        return self._row_to_registration(row) if row else None

    def upsert_data_source(
        self,
        name: str,
        type_: str,
        connection: str,
        sensitive_columns: list[str] | None = None,
        description: str | None = None,
        upstream_mcp_server_config_id: str | None = None,
    ) -> DataSourceRegistration:
        if self.get_data_source(name):
            return self.update_data_source(
                name,
                type_=type_,
                connection=connection,
                sensitive_columns=sensitive_columns,
                description=description,
                upstream_mcp_server_config_id=upstream_mcp_server_config_id,
            )
        return self.create_data_source(
            name,
            type_,
            connection,
            sensitive_columns=sensitive_columns,
            description=description,
            upstream_mcp_server_config_id=upstream_mcp_server_config_id,
        )

    def create_data_source(
        self,
        name: str,
        type_: str,
        connection: str,
        sensitive_columns: list[str] | None = None,
        description: str | None = None,
        upstream_mcp_server_config_id: str | None = None,
    ) -> DataSourceRegistration:
        now = self._now()
        encoded_sensitive_columns = json.dumps(
            self._normalize_sensitive_columns(sensitive_columns)
        )
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO data_sources (name, type, connection, sensitive_columns, description, upstream_mcp_server_config_id, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    name,
                    type_,
                    connection,
                    encoded_sensitive_columns,
                    description,
                    upstream_mcp_server_config_id,
                    now,
                    now,
                ),
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
        sensitive_columns: list[str] | None = None,
        description: str | None | _Unset = _UNSET,
        upstream_mcp_server_config_id: str | None | _Unset = _UNSET,
    ) -> DataSourceRegistration | None:
        current = self.get_data_source(name)
        if current is None:
            return None
        next_type = type_ if type_ is not None else current.type
        next_connection = connection if connection is not None else current.connection
        next_sensitive_columns = (
            self._normalize_sensitive_columns(sensitive_columns)
            if sensitive_columns is not None
            else current.sensitive_columns
        )
        next_description = current.description if description is _UNSET else description
        next_upstream_id = (
            current.upstream_mcp_server_config_id
            if upstream_mcp_server_config_id is _UNSET
            else upstream_mcp_server_config_id
        )
        now = self._now()
        with self._connect() as conn:
            conn.execute(
                """
                UPDATE data_sources
                SET type = ?, connection = ?, sensitive_columns = ?, description = ?, upstream_mcp_server_config_id = ?, updated_at = ?
                WHERE name = ?
                """,
                (
                    next_type,
                    next_connection,
                    json.dumps(next_sensitive_columns),
                    next_description,
                    next_upstream_id,
                    now,
                    name,
                ),
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

    def create_doc(
        self, data_source: str, doc_type: str, target: str | None, content: str
    ) -> DocEntry:
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

    def upsert_doc(
        self, data_source: str, doc_type: str, target: str | None, content: str
    ) -> DocEntry:
        with self._connect() as conn:
            if target is None:
                row = conn.execute(
                    "SELECT id FROM source_docs WHERE data_source = ? AND doc_type = ? AND target IS NULL",
                    (data_source, doc_type),
                ).fetchone()
            else:
                row = conn.execute(
                    "SELECT id FROM source_docs WHERE data_source = ? AND doc_type = ? AND target = ?",
                    (data_source, doc_type, target),
                ).fetchone()

        if row:
            return self.update_doc(data_source, int(row["id"]), content=content)
        return self.create_doc(data_source, doc_type, target, content)

    def delete_doc(self, data_source: str, doc_id: int) -> bool:
        with self._connect() as conn:
            result = conn.execute(
                "DELETE FROM source_docs WHERE data_source = ? AND id = ?",
                (data_source, doc_id),
            )
        return result.rowcount > 0

    # ------------------------------------------------------------------
    # Upstream MCP server config CRUD
    # ------------------------------------------------------------------

    @staticmethod
    def _row_to_upstream_config(row: sqlite3.Row) -> UpstreamMCPServerConfigRecord:
        payload = dict(row)
        for json_field, default in (("auth", {}), ("exposed_tools", [])):
            raw = payload.get(json_field)
            try:
                payload[json_field] = json.loads(raw) if raw else default
            except (json.JSONDecodeError, TypeError):
                payload[json_field] = default
        return UpstreamMCPServerConfigRecord(**payload)

    def list_upstream_configs(self) -> list[UpstreamMCPServerConfigRecord]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT id, server_id, name, endpoint, auth, exposed_tools, created_at, updated_at FROM upstream_mcp_server_configs ORDER BY name"
            ).fetchall()
        return [self._row_to_upstream_config(row) for row in rows]

    def list_upstream_configs_for_server(self, server_id: str) -> list[UpstreamMCPServerConfigRecord]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT id, server_id, name, endpoint, auth, exposed_tools, created_at, updated_at FROM upstream_mcp_server_configs WHERE server_id = ? ORDER BY name",
                (server_id,),
            ).fetchall()
        return [self._row_to_upstream_config(row) for row in rows]

    def get_upstream_config(self, config_id: str) -> UpstreamMCPServerConfigRecord | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT id, server_id, name, endpoint, auth, exposed_tools, created_at, updated_at FROM upstream_mcp_server_configs WHERE id = ?",
                (config_id,),
            ).fetchone()
        return self._row_to_upstream_config(row) if row else None

    def create_upstream_config(
        self,
        config_id: str,
        server_id: str,
        name: str,
        endpoint: str | None = None,
        auth: dict | None = None,
        exposed_tools: list[str] | None = None,
    ) -> UpstreamMCPServerConfigRecord:
        now = self._now()
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO upstream_mcp_server_configs (id, server_id, name, endpoint, auth, exposed_tools, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    config_id,
                    server_id,
                    name,
                    endpoint,
                    json.dumps(auth or {}),
                    json.dumps(exposed_tools or []),
                    now,
                    now,
                ),
            )
        created = self.get_upstream_config(config_id)
        if created is None:
            raise RuntimeError(f"Failed to create upstream config: {config_id}")
        return created

    def update_upstream_config(
        self,
        config_id: str,
        name: str | None = None,
        endpoint: str | None | _Unset = _UNSET,
        auth: dict | None = None,
        exposed_tools: list[str] | None = None,
    ) -> UpstreamMCPServerConfigRecord | None:
        current = self.get_upstream_config(config_id)
        if current is None:
            return None
        next_name = name if name is not None else current.name
        next_endpoint = current.endpoint if endpoint is _UNSET else endpoint
        next_auth = auth if auth is not None else current.auth
        next_exposed_tools = exposed_tools if exposed_tools is not None else current.exposed_tools
        now = self._now()
        with self._connect() as conn:
            conn.execute(
                """
                UPDATE upstream_mcp_server_configs
                SET name = ?, endpoint = ?, auth = ?, exposed_tools = ?, updated_at = ?
                WHERE id = ?
                """,
                (
                    next_name,
                    next_endpoint,
                    json.dumps(next_auth),
                    json.dumps(next_exposed_tools),
                    now,
                    config_id,
                ),
            )
        updated = self.get_upstream_config(config_id)
        if updated is None:
            raise RuntimeError(f"Failed to update upstream config: {config_id}")
        return updated

    def delete_upstream_config(self, config_id: str) -> bool:
        with self._connect() as conn:
            result = conn.execute(
                "DELETE FROM upstream_mcp_server_configs WHERE id = ?",
                (config_id,),
            )
        return result.rowcount > 0

    # ------------------------------------------------------------------
    # Audit Logging
    # ------------------------------------------------------------------

    def log_action(
        self,
        action: str,
        details: str | None = None,
        actor: str = "System",
        status: str = "Success",
        latency_ms: int | None = None,
        timestamp: str | None = None,
    ) -> AuditLogEntry:
        now = timestamp or self._now()
        with self._connect() as conn:
            cursor = conn.execute(
                """
                INSERT INTO audit_log (timestamp, action, details, actor, status, latency_ms)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (now, action, details, actor, status, latency_ms),
            )
            log_id = int(cursor.lastrowid)
        return AuditLogEntry(
            id=log_id,
            timestamp=now,
            action=action,
            details=details,
            actor=actor,
            status=status,
            latency_ms=latency_ms,
        )

    def list_audit_logs(self, limit: int = 50) -> list[AuditLogEntry]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT id, timestamp, action, details, actor, status, latency_ms FROM audit_log ORDER BY timestamp DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [AuditLogEntry(**dict(row)) for row in rows]

    def get_usage_metrics(self, days: int = 7) -> dict:
        """Aggregate usage metrics from audit logs for the last N days."""
        today = datetime.now(timezone.utc).date()
        metrics = {
            "requests_trend_7d": [],
            "requests_last_24h": 0,
            "avg_latency_ms": 0,
            "success_rate_pct": 0,
        }

        with self._connect() as conn:
            # Trend data
            for offset in range(days - 1, -1, -1):
                day = today - timedelta(days=offset)
                day_str = day.isoformat()
                row = conn.execute(
                    "SELECT COUNT(*) FROM audit_log WHERE date(timestamp) = date(?)",
                    (day_str,),
                ).fetchone()
                metrics["requests_trend_7d"].append(
                    {"day": day.strftime("%a"), "requests": row[0] if row else 0}
                )

            # Last 24h stats
            since_24h = (datetime.now(timezone.utc) - timedelta(hours=24)).isoformat()
            row = conn.execute(
                "SELECT COUNT(*), AVG(latency_ms) FROM audit_log WHERE timestamp >= ?",
                (since_24h,),
            ).fetchone()
            if row and row[0] > 0:
                metrics["requests_last_24h"] = row[0]
                metrics["avg_latency_ms"] = int(row[1]) if row[1] is not None else 0

                success_row = conn.execute(
                    "SELECT COUNT(*) FROM audit_log WHERE timestamp >= ? AND status = 'Success'",
                    (since_24h,),
                ).fetchone()
                metrics["success_rate_pct"] = round((success_row[0] / row[0]) * 100, 1)

        return metrics
