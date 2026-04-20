from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from ubs_hackathon.datasource import SQLiteDataSource, TemporaryViewError
from ubs_hackathon.models import DataSourceConfig


def _seed_sqlite_source(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(path) as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS orders (
                order_id INTEGER PRIMARY KEY,
                region TEXT NOT NULL,
                revenue REAL NOT NULL
            )
            """
        )
        conn.executemany(
            "INSERT INTO orders (order_id, region, revenue) VALUES (?, ?, ?)",
            [(1, "CH", 100.0), (2, "CH", 150.0), (3, "US", 200.0)],
        )


def test_temporary_views_create_list_query_and_drop(tmp_path: Path) -> None:
    source_db = tmp_path / "source.db"
    _seed_sqlite_source(source_db)

    source = SQLiteDataSource(
        DataSourceConfig(name="demo_sqlite", type="sqlite", connection=str(source_db))
    )

    created = source.create_temporary_view(
        "SELECT region, SUM(revenue) AS total_revenue FROM orders GROUP BY region",
        view_name="regional_summary",
        ttl_seconds=60,
        session_id="session-a",
    )
    assert created["name"].startswith("mcp_view_session-a_")
    assert "regional_summary" in created["name"]

    listed = source.list_temporary_views(session_id="session-a")
    assert len(listed) == 1
    assert listed[0]["name"] == created["name"]
    assert source.list_temporary_views(session_id="session-b") == []

    tables = source.list_tables()
    assert created["name"] in tables

    result = source.execute_read_only(
        f'SELECT * FROM "{created["name"]}" ORDER BY region'
    )
    assert result["rows"] == [
        {"region": "CH", "total_revenue": 250.0},
        {"region": "US", "total_revenue": 200.0},
    ]

    deleted = source.drop_temporary_view(created["name"], session_id="session-a")
    assert deleted == {"name": created["name"], "deleted": True}
    assert source.list_temporary_views(session_id="session-a") == []

    with pytest.raises(TemporaryViewError):
        source.drop_temporary_view(created["name"], session_id="session-a")


def test_temporary_views_are_partitioned_by_session(tmp_path: Path) -> None:
    source_db = tmp_path / "source.db"
    _seed_sqlite_source(source_db)

    source = SQLiteDataSource(
        DataSourceConfig(name="demo_sqlite", type="sqlite", connection=str(source_db))
    )

    alpha = source.create_temporary_view(
        "SELECT region, COUNT(*) AS c FROM orders GROUP BY region",
        view_name="summary",
        ttl_seconds=60,
        session_id="alpha",
    )["name"]
    beta = source.create_temporary_view(
        "SELECT region, SUM(revenue) AS revenue FROM orders GROUP BY region",
        view_name="summary",
        ttl_seconds=60,
        session_id="beta",
    )["name"]

    assert alpha != beta
    assert len(source.list_temporary_views(session_id="alpha")) == 1
    assert len(source.list_temporary_views(session_id="beta")) == 1
    assert source.list_temporary_views(session_id="gamma") == []


def test_table_doc_handles_identifiers_requiring_quoting(tmp_path: Path) -> None:
    source_db = tmp_path / "quoted_source.db"
    source_db.parent.mkdir(parents=True, exist_ok=True)

    with sqlite3.connect(source_db) as conn:
        conn.execute(
            'CREATE TABLE "order details" ("select" TEXT NOT NULL, "total amount" REAL)'
        )
        conn.executemany(
            'INSERT INTO "order details" ("select", "total amount") VALUES (?, ?)',
            [("a", 10.5), ("b", 20.25)],
        )

    source = SQLiteDataSource(
        DataSourceConfig(name="demo_sqlite", type="sqlite", connection=str(source_db))
    )

    doc = source.table_doc("order details")
    assert doc.table == "order details"
    assert doc.row_count_estimate == 2

    result = source.execute_read_only(
        'SELECT "select", "total amount" FROM "order details" ORDER BY "select"'
    )
    assert result["rows"] == [
        {"select": "a", "total amount": 10.5},
        {"select": "b", "total amount": 20.25},
    ]
