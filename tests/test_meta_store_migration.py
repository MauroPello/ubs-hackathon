from __future__ import annotations

import sqlite3
from pathlib import Path

from ubs_hackathon.meta_store import MetaStore


def _create_legacy_meta_db(path: Path) -> None:
    with sqlite3.connect(path) as conn:
        conn.executescript(
            """
            CREATE TABLE data_sources (
                name TEXT PRIMARY KEY,
                type TEXT NOT NULL,
                connection TEXT NOT NULL,
                databases TEXT NOT NULL DEFAULT '[]',
                sensitive_columns TEXT NOT NULL DEFAULT '[]',
                description TEXT,
                upstream_mcp_server_config_id TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );

            CREATE TABLE source_docs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                data_source TEXT NOT NULL,
                doc_type TEXT NOT NULL,
                target TEXT,
                content TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                FOREIGN KEY (data_source) REFERENCES data_sources(name) ON DELETE CASCADE
            );

            CREATE TABLE upstream_mcp_server_configs (
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
        )
        conn.execute(
            """
            INSERT INTO data_sources (
                name,
                type,
                connection,
                databases,
                sensitive_columns,
                description,
                upstream_mcp_server_config_id,
                created_at,
                updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "legacy_source",
                "sqlite",
                "sqlite:///tmp/demo.db",
                "[\"main\"]",
                "[\"users.email\"]",
                "Legacy",
                "connector_1",
                "2026-01-01T00:00:00+00:00",
                "2026-01-01T00:00:00+00:00",
            ),
        )


def test_meta_store_drops_legacy_data_source_columns(tmp_path: Path) -> None:
    db_path = tmp_path / "meta.db"
    _create_legacy_meta_db(db_path)

    store = MetaStore(db_path)

    with sqlite3.connect(db_path) as conn:
        columns = [row[1] for row in conn.execute("PRAGMA table_info(data_sources)").fetchall()]

    assert "type" not in columns
    assert "connection" not in columns

    row = store.get_data_source("legacy_source")
    assert row is not None
    assert row.name == "legacy_source"
    assert row.databases == ["main"]
    assert row.sensitive_columns == ["users.email"]
    assert row.upstream_mcp_server_config_id == "connector_1"
