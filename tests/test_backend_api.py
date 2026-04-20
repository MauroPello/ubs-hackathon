from __future__ import annotations

import sqlite3
from pathlib import Path

from fastapi.testclient import TestClient

from ubs_hackathon.catalog import SchemaCatalog
from ubs_hackathon.backend import create_app


def _seed_sqlite_source(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(path) as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS orders (
                order_id INTEGER PRIMARY KEY,
                revenue REAL NOT NULL
            )
            """
        )
        conn.execute("INSERT INTO orders (order_id, revenue) VALUES (1, 100.0)")


def test_frontend_homepage(tmp_path: Path) -> None:
    app = create_app(meta_db_path=tmp_path / "meta.db", catalog_path=tmp_path / "catalog.db")
    client = TestClient(app)

    response = client.get("/")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/html")
    assert "Data Source Manager" in response.text
    assert "Documentation description" in response.text
    assert "MCP Usage Dashboard" in response.text
    assert "Connect Notion (fake)" in response.text


def test_data_sources_crud(tmp_path: Path) -> None:
    source_db = tmp_path / "source.db"
    _seed_sqlite_source(source_db)
    app = create_app(meta_db_path=tmp_path / "meta.db", catalog_path=tmp_path / "catalog.db")
    client = TestClient(app)

    assert client.get("/data-sources").json() == []

    payload = {
        "name": "demo_sqlite",
        "type": "sqlite",
        "connection": str(source_db),
        "description": "Primary demo sales source",
    }
    created = client.post("/data-sources", json=payload)
    assert created.status_code == 201
    assert created.json()["name"] == "demo_sqlite"
    assert created.json()["description"] == "Primary demo sales source"

    listed = client.get("/data-sources")
    assert listed.status_code == 200
    assert len(listed.json()) == 1

    fetched = client.get("/data-sources/demo_sqlite")
    assert fetched.status_code == 200
    assert fetched.json()["connection"] == str(source_db)
    assert fetched.json()["description"] == "Primary demo sales source"

    updated = client.put(
        "/data-sources/demo_sqlite",
        json={"connection": str(source_db), "type": "sqlite", "description": "Updated source summary"},
    )
    assert updated.status_code == 200
    assert updated.json()["type"] == "sqlite"
    assert updated.json()["description"] == "Updated source summary"

    deleted = client.delete("/data-sources/demo_sqlite")
    assert deleted.status_code == 204
    assert client.get("/data-sources").json() == []


def test_docs_crud_and_cascade_delete(tmp_path: Path) -> None:
    source_db = tmp_path / "source.db"
    meta_db = tmp_path / "meta.db"
    catalog_db = tmp_path / "catalog.db"
    _seed_sqlite_source(source_db)
    app = create_app(meta_db_path=meta_db, catalog_path=catalog_db)
    client = TestClient(app)
    catalog = SchemaCatalog(catalog_db)

    payload = {"name": "demo_sqlite", "type": "sqlite", "connection": str(source_db)}
    assert client.post("/data-sources", json=payload).status_code == 201

    first_doc = client.post(
        "/data-sources/demo_sqlite/docs",
        json={"doc_type": "table", "target": "orders", "content": "Orders table doc"},
    )
    assert first_doc.status_code == 201
    first_doc_id = first_doc.json()["id"]
    assert catalog.describe_table("demo_sqlite", "orders")["description"] == "Orders table doc"

    second_doc = client.post(
        "/data-sources/demo_sqlite/docs",
        json={"doc_type": "column", "target": "orders.revenue", "content": "Revenue in USD"},
    )
    assert second_doc.status_code == 201
    second_doc_id = second_doc.json()["id"]
    assert catalog.describe_table("demo_sqlite", "orders")["columns"][1]["description"] == "Revenue in USD"

    listed = client.get("/data-sources/demo_sqlite/docs")
    assert listed.status_code == 200
    assert len(listed.json()) == 2

    fetched = client.get(f"/data-sources/demo_sqlite/docs/{first_doc_id}")
    assert fetched.status_code == 200
    assert fetched.json()["content"] == "Orders table doc"

    updated = client.put(
        f"/data-sources/demo_sqlite/docs/{first_doc_id}",
        json={"content": "Orders table documentation", "target": None},
    )
    assert updated.status_code == 200
    assert updated.json()["content"] == "Orders table documentation"
    assert updated.json()["target"] is None
    assert catalog.describe_table("demo_sqlite", "orders")["description"] == "Orders table documentation"

    deleted_doc = client.delete(f"/data-sources/demo_sqlite/docs/{second_doc_id}")
    assert deleted_doc.status_code == 204
    assert len(client.get("/data-sources/demo_sqlite/docs").json()) == 1
    assert catalog.describe_table("demo_sqlite", "orders")["columns"][1]["description"] is None

    third_doc = client.post(
        "/data-sources/demo_sqlite/docs",
        json={"doc_type": "column", "target": "orders.revenue", "content": "Revenue amount"},
    )
    assert third_doc.status_code == 201
    third_doc_id = third_doc.json()["id"]

    partial_update = client.put(
        f"/data-sources/demo_sqlite/docs/{third_doc_id}",
        json={"content": "Revenue amount in USD"},
    )
    assert partial_update.status_code == 200
    assert partial_update.json()["target"] == "orders.revenue"
    assert catalog.describe_table("demo_sqlite", "orders")["columns"][1]["description"] == "Revenue amount in USD"

    invalid_update = client.put(
        f"/data-sources/demo_sqlite/docs/{third_doc_id}",
        json={"content": None},
    )
    assert invalid_update.status_code == 422
    assert "content cannot be null" in invalid_update.json()["detail"]

    deleted_source = client.delete("/data-sources/demo_sqlite")
    assert deleted_source.status_code == 204

    with sqlite3.connect(meta_db) as conn:
        row = conn.execute("SELECT COUNT(*) FROM source_docs").fetchone()
    assert row is not None and int(row[0]) == 0


def test_mcp_usage_endpoint(tmp_path: Path) -> None:
    source_db = tmp_path / "source.db"
    _seed_sqlite_source(source_db)
    app = create_app(meta_db_path=tmp_path / "meta.db", catalog_path=tmp_path / "catalog.db")
    client = TestClient(app)

    initial = client.get("/mcp-usage")
    assert initial.status_code == 200
    payload = initial.json()
    assert payload["registered_sources"] == 0
    assert payload["stored_docs"] == 0
    assert payload["catalog_tables"] == 0
    assert len(payload["requests_trend_7d"]) == 7
    assert set(payload["simulated_connectors"]) == {"notion", "google_workspace"}

    create_source = client.post(
        "/data-sources",
        json={"name": "demo_sqlite", "type": "sqlite", "connection": str(source_db)},
    )
    assert create_source.status_code == 201

    create_doc = client.post(
        "/data-sources/demo_sqlite/docs",
        json={"doc_type": "table", "target": "orders", "content": "Orders description"},
    )
    assert create_doc.status_code == 201

    usage_after = client.get("/mcp-usage")
    assert usage_after.status_code == 200
    usage_payload = usage_after.json()
    assert usage_payload["registered_sources"] == 1
    assert usage_payload["stored_docs"] == 1
    assert usage_payload["catalog_tables"] >= 1
    assert usage_payload["requests_last_24h"] >= 24
    assert usage_payload["avg_latency_ms"] >= 95
    assert 95.0 <= usage_payload["success_rate_pct"] <= 99.9
    assert set(usage_payload["tool_calls_24h"]) == {
        "search_schema",
        "describe_table",
        "execute_query",
        "list_data_sources",
    }
