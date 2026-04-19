from __future__ import annotations

import sqlite3
from pathlib import Path

from fastapi.testclient import TestClient

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


def test_data_sources_crud(tmp_path: Path) -> None:
    source_db = tmp_path / "source.db"
    _seed_sqlite_source(source_db)
    app = create_app(meta_db_path=tmp_path / "meta.db", catalog_path=tmp_path / "catalog.db")
    client = TestClient(app)

    assert client.get("/data-sources").json() == []

    payload = {"name": "demo_sqlite", "type": "sqlite", "connection": str(source_db)}
    created = client.post("/data-sources", json=payload)
    assert created.status_code == 201
    assert created.json()["name"] == "demo_sqlite"

    listed = client.get("/data-sources")
    assert listed.status_code == 200
    assert len(listed.json()) == 1

    fetched = client.get("/data-sources/demo_sqlite")
    assert fetched.status_code == 200
    assert fetched.json()["connection"] == str(source_db)

    updated = client.put("/data-sources/demo_sqlite", json={"connection": str(source_db), "type": "sqlite"})
    assert updated.status_code == 200
    assert updated.json()["type"] == "sqlite"

    deleted = client.delete("/data-sources/demo_sqlite")
    assert deleted.status_code == 204
    assert client.get("/data-sources").json() == []


def test_docs_crud_and_cascade_delete(tmp_path: Path) -> None:
    source_db = tmp_path / "source.db"
    meta_db = tmp_path / "meta.db"
    _seed_sqlite_source(source_db)
    app = create_app(meta_db_path=meta_db, catalog_path=tmp_path / "catalog.db")
    client = TestClient(app)

    payload = {"name": "demo_sqlite", "type": "sqlite", "connection": str(source_db)}
    assert client.post("/data-sources", json=payload).status_code == 201

    first_doc = client.post(
        "/data-sources/demo_sqlite/docs",
        json={"doc_type": "table", "target": "orders", "content": "Orders table doc"},
    )
    assert first_doc.status_code == 201
    first_doc_id = first_doc.json()["id"]

    second_doc = client.post(
        "/data-sources/demo_sqlite/docs",
        json={"doc_type": "column", "target": "orders.revenue", "content": "Revenue in USD"},
    )
    assert second_doc.status_code == 201
    second_doc_id = second_doc.json()["id"]

    listed = client.get("/data-sources/demo_sqlite/docs")
    assert listed.status_code == 200
    assert len(listed.json()) == 2

    fetched = client.get(f"/data-sources/demo_sqlite/docs/{first_doc_id}")
    assert fetched.status_code == 200
    assert fetched.json()["content"] == "Orders table doc"

    updated = client.put(
        f"/data-sources/demo_sqlite/docs/{first_doc_id}",
        json={"content": "Orders table documentation"},
    )
    assert updated.status_code == 200
    assert updated.json()["content"] == "Orders table documentation"

    deleted_doc = client.delete(f"/data-sources/demo_sqlite/docs/{second_doc_id}")
    assert deleted_doc.status_code == 204
    assert len(client.get("/data-sources/demo_sqlite/docs").json()) == 1

    deleted_source = client.delete("/data-sources/demo_sqlite")
    assert deleted_source.status_code == 204

    with sqlite3.connect(meta_db) as conn:
        row = conn.execute("SELECT COUNT(*) FROM source_docs").fetchone()
    assert row is not None and int(row[0]) == 0
