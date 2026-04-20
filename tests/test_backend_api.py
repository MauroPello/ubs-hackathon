from __future__ import annotations

import sqlite3
from pathlib import Path

from fastapi.testclient import TestClient

from ubs_hackathon.catalog import SchemaCatalog
from ubs_hackathon.backend import create_app


def _seed_sqlite_source(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(path) as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS orders (
                order_id INTEGER PRIMARY KEY,
                revenue REAL NOT NULL
            )
            """)
        conn.execute("INSERT INTO orders (order_id, revenue) VALUES (1, 100.0)")


def _create_sql_like_connector(
    client: TestClient, source_db: Path, name: str = "sql_connector"
) -> str:
    resp = client.post(
        "/upstream-mcp-server-configs",
        json={
            "server_id": "sql-like",
            "name": name,
            "auth": {"dialect": "sqlite", "connection": str(source_db)},
            "exposed_tools": [
                "search_schema",
                "describe_table",
                "execute_query",
                "list_temporary_views",
                "create_temporary_view",
                "drop_temporary_view",
            ],
        },
    )
    assert resp.status_code == 201
    return resp.json()["id"]


def test_frontend_homepage(tmp_path: Path) -> None:
    app = create_app(
        meta_db_path=tmp_path / "meta.db", catalog_path=tmp_path / "catalog.db"
    )
    client = TestClient(app)

    response = client.get("/")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/html")
    assert "Data Source Manager" in response.text
    assert 'href="/sources"' in response.text
    assert 'href="/dashboard"' in response.text
    assert 'href="/mcp-servers"' in response.text

    sources = client.get("/sources")
    assert sources.status_code == 200
    assert "Documentation description" in sources.text
    assert "Sensitive columns" in sources.text

    dashboard = client.get("/dashboard")
    assert dashboard.status_code == 200
    assert "MCP Usage Dashboard" in dashboard.text

    mcp_servers = client.get("/mcp-servers")
    assert mcp_servers.status_code == 200
    assert (
        "upstream MCP" in mcp_servers.text.lower()
        or "mcp server" in mcp_servers.text.lower()
    )

    # The registry API should return Neo4j and Notion entries.
    registry = client.get("/upstream-mcp-servers")
    assert registry.status_code == 200
    ids = [e["id"] for e in registry.json()]
    assert "neo4j" in ids
    assert "notion" in ids

    # Legacy /connectors URL still works (redirects to MCP Servers page).
    connectors = client.get("/connectors")
    assert connectors.status_code == 200
    assert (
        "mcp server" in connectors.text.lower() or "upstream" in connectors.text.lower()
    )


def test_data_sources_crud(tmp_path: Path) -> None:
    source_db = tmp_path / "source.db"
    _seed_sqlite_source(source_db)
    app = create_app(
        meta_db_path=tmp_path / "meta.db", catalog_path=tmp_path / "catalog.db"
    )
    client = TestClient(app)

    assert client.get("/data-sources").json() == []

    connector_id = _create_sql_like_connector(client, source_db)

    payload = {
        "name": "demo_sqlite",
        "databases": ["main"],
        "sensitive_columns": ["orders.revenue"],
        "description": "Primary demo sales source",
        "upstream_mcp_server_config_id": connector_id,
    }
    created = client.post("/data-sources", json=payload)
    assert created.status_code == 201
    assert created.json()["name"] == "demo_sqlite"
    assert created.json()["sensitive_columns"] == ["orders.revenue"]
    assert created.json()["description"] == "Primary demo sales source"

    listed = client.get("/data-sources")
    assert listed.status_code == 200
    assert len(listed.json()) == 1

    fetched = client.get("/data-sources/demo_sqlite")
    assert fetched.status_code == 200
    assert fetched.json()["upstream_mcp_server_config_id"] == connector_id
    assert fetched.json()["databases"] == ["main"]
    assert fetched.json()["sensitive_columns"] == ["orders.revenue"]
    assert fetched.json()["description"] == "Primary demo sales source"

    updated = client.put(
        "/data-sources/demo_sqlite",
        json={
            "databases": ["main", "analytics"],
            "sensitive_columns": ["orders.order_id"],
            "description": "Updated source summary",
        },
    )
    assert updated.status_code == 200
    assert updated.json()["databases"] == ["main", "analytics"]
    assert updated.json()["sensitive_columns"] == ["orders.order_id"]
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

    connector_id = _create_sql_like_connector(client, source_db)

    payload = {
        "name": "demo_sqlite",
        "upstream_mcp_server_config_id": connector_id,
    }
    assert client.post("/data-sources", json=payload).status_code == 201

    first_doc = client.post(
        "/data-sources/demo_sqlite/docs",
        json={"doc_type": "table", "target": "orders", "content": "Orders table doc"},
    )
    assert first_doc.status_code == 201
    first_doc_id = first_doc.json()["id"]
    assert (
        catalog.describe_table("demo_sqlite", "orders")["description"]
        == "Orders table doc"
    )

    second_doc = client.post(
        "/data-sources/demo_sqlite/docs",
        json={
            "doc_type": "column",
            "target": "orders.revenue",
            "content": "Revenue in USD",
        },
    )
    assert second_doc.status_code == 201
    second_doc_id = second_doc.json()["id"]
    assert (
        catalog.describe_table("demo_sqlite", "orders")["columns"][1]["description"]
        == "Revenue in USD"
    )

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
    assert (
        catalog.describe_table("demo_sqlite", "orders")["description"]
        == "Orders table documentation"
    )

    deleted_doc = client.delete(f"/data-sources/demo_sqlite/docs/{second_doc_id}")
    assert deleted_doc.status_code == 204
    assert len(client.get("/data-sources/demo_sqlite/docs").json()) == 1
    assert (
        catalog.describe_table("demo_sqlite", "orders")["columns"][1]["description"]
        is None
    )

    third_doc = client.post(
        "/data-sources/demo_sqlite/docs",
        json={
            "doc_type": "column",
            "target": "orders.revenue",
            "content": "Revenue amount",
        },
    )
    assert third_doc.status_code == 201
    third_doc_id = third_doc.json()["id"]

    partial_update = client.put(
        f"/data-sources/demo_sqlite/docs/{third_doc_id}",
        json={"content": "Revenue amount in USD"},
    )
    assert partial_update.status_code == 200
    assert partial_update.json()["target"] == "orders.revenue"
    assert (
        catalog.describe_table("demo_sqlite", "orders")["columns"][1]["description"]
        == "Revenue amount in USD"
    )

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
    app = create_app(
        meta_db_path=tmp_path / "meta.db", catalog_path=tmp_path / "catalog.db"
    )
    client = TestClient(app)

    connector_id = _create_sql_like_connector(client, source_db)

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
        json={
            "name": "demo_sqlite",
            "upstream_mcp_server_config_id": connector_id,
        },
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


def test_upstream_mcp_registry(tmp_path: Path) -> None:
    app = create_app(
        meta_db_path=tmp_path / "meta.db", catalog_path=tmp_path / "catalog.db"
    )
    client = TestClient(app)

    # Full registry.
    resp = client.get("/upstream-mcp-servers")
    assert resp.status_code == 200
    entries = resp.json()
    ids = {e["id"] for e in entries}
    assert "neo4j" in ids
    assert "notion" in ids

    # neo4j is available, notion is not.
    neo4j = next(e for e in entries if e["id"] == "neo4j")
    notion = next(e for e in entries if e["id"] == "notion")
    assert neo4j["status"] == "available"
    assert notion["status"] == "unavailable"
    assert neo4j["data_type"] == "graph"
    assert notion["data_type"] == "documents"
    assert neo4j["requires_auth"] is True
    assert len(neo4j["tools"]) > 0

    # Filter by data type.
    graph_entries = client.get("/upstream-mcp-servers?data_type=graph").json()
    assert all(e["data_type"] == "graph" for e in graph_entries)

    doc_entries = client.get("/upstream-mcp-servers?data_type=documents").json()
    assert all(e["data_type"] == "documents" for e in doc_entries)

    # Single entry lookup.
    resp_single = client.get("/upstream-mcp-servers/neo4j")
    assert resp_single.status_code == 200
    assert resp_single.json()["id"] == "neo4j"

    not_found = client.get("/upstream-mcp-servers/does_not_exist")
    assert not_found.status_code == 404


def test_upstream_mcp_server_config_crud(tmp_path: Path) -> None:
    app = create_app(
        meta_db_path=tmp_path / "meta.db", catalog_path=tmp_path / "catalog.db"
    )
    client = TestClient(app)

    # Initially empty.
    assert client.get("/upstream-mcp-server-configs").json() == []

    # Create a config for neo4j.
    payload = {
        "server_id": "neo4j",
        "name": "my_neo4j",
        "endpoint": "http://localhost:9000/mcp",
        "auth": {
            "url": "bolt://localhost:7687",
            "username": "neo4j",
            "password": "s3cr3t",
        },
        "exposed_tools": ["execute_cypher", "list_labels"],
    }
    created = client.post("/upstream-mcp-server-configs", json=payload)
    assert created.status_code == 201
    cfg = created.json()
    assert cfg["server_id"] == "neo4j"
    assert cfg["name"] == "my_neo4j"
    assert cfg["endpoint"] == "http://localhost:9000/mcp"
    assert cfg["auth"]["username"] == "neo4j"
    assert set(cfg["exposed_tools"]) == {"execute_cypher", "list_labels"}
    config_id = cfg["id"]

    # List.
    listed = client.get("/upstream-mcp-server-configs")
    assert listed.status_code == 200
    assert len(listed.json()) == 1

    # Get single.
    fetched = client.get(f"/upstream-mcp-server-configs/{config_id}")
    assert fetched.status_code == 200
    assert fetched.json()["name"] == "my_neo4j"

    # Update.
    updated = client.put(
        f"/upstream-mcp-server-configs/{config_id}",
        json={"name": "neo4j_prod", "exposed_tools": ["execute_cypher"]},
    )
    assert updated.status_code == 200
    assert updated.json()["name"] == "neo4j_prod"
    assert updated.json()["exposed_tools"] == ["execute_cypher"]

    # Delete.
    deleted = client.delete(f"/upstream-mcp-server-configs/{config_id}")
    assert deleted.status_code == 204
    assert client.get("/upstream-mcp-server-configs").json() == []

    # Creating with an unknown server_id should fail.
    bad = client.post(
        "/upstream-mcp-server-configs",
        json={"server_id": "nonexistent", "name": "test"},
    )
    assert bad.status_code == 422


def test_data_source_with_upstream_mcp_config(tmp_path: Path) -> None:
    app = create_app(
        meta_db_path=tmp_path / "meta.db", catalog_path=tmp_path / "catalog.db"
    )
    client = TestClient(app)

    # Create an upstream config first.
    cfg_resp = client.post(
        "/upstream-mcp-server-configs",
        json={
            "server_id": "neo4j",
            "name": "test_neo4j",
            "endpoint": "http://localhost:9000/mcp",
            "auth": {
                "url": "bolt://localhost:7687",
                "username": "neo4j",
                "password": "pw",
            },
            "exposed_tools": ["execute_cypher"],
        },
    )
    assert cfg_resp.status_code == 201
    config_id = cfg_resp.json()["id"]

    # Create a data source referencing this config.
    ds_resp = client.post(
        "/data-sources",
        json={
            "name": "graph_source",
            "upstream_mcp_server_config_id": config_id,
        },
    )
    assert ds_resp.status_code == 201
    ds = ds_resp.json()
    assert ds["upstream_mcp_server_config_id"] == config_id

    # Sync should return 0 tables (upstream MCP sources have no SQL schema).
    sync_resp = client.post("/data-sources/graph_source/sync")
    assert sync_resp.status_code == 200
    assert sync_resp.json()["indexed_tables"] == 0

    # Creating a data source with an invalid upstream config should fail.
    bad_ds = client.post(
        "/data-sources",
        json={
            "name": "bad_graph",
            "upstream_mcp_server_config_id": "nonexistent",
        },
    )
    assert bad_ds.status_code == 422
