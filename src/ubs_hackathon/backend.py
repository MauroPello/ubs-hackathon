from __future__ import annotations

import argparse
from pathlib import Path

import uvicorn
from fastapi import FastAPI, HTTPException, status
from pydantic import BaseModel, ConfigDict

from .builder import _apply_schema_docs
from .catalog import SchemaCatalog
from .datasource import build_data_source
from .meta_store import MetaStore, _UNSET
from .models import DataSourceConfig


class DataSourceCreate(BaseModel):
    name: str
    type: str
    connection: str


class DataSourceUpdate(BaseModel):
    type: str | None = None
    connection: str | None = None

    model_config = ConfigDict(extra="forbid")


class DocCreate(BaseModel):
    doc_type: str
    target: str | None = None
    content: str


class DocUpdate(BaseModel):
    doc_type: str | None = None
    target: str | None = None
    content: str | None = None

    model_config = ConfigDict(extra="forbid")


def _docs_to_schema_map(data_source: str, docs: list[dict]) -> dict:
    source_payload: dict = {"tables": {}}
    for doc in docs:
        doc_type = doc.get("doc_type", "").lower()
        target = doc.get("target")
        content = doc.get("content")
        if not content:
            continue
        if doc_type == "table" and target:
            table_meta = source_payload["tables"].setdefault(target, {})
            table_meta["description"] = content
            continue
        if doc_type == "column" and target and "." in target:
            if target.count(".") != 1:
                continue
            table_name, column_name = target.split(".", 1)
            table_meta = source_payload["tables"].setdefault(table_name, {})
            column_meta = table_meta.setdefault("columns", {})
            column_meta[column_name] = content
    return {data_source: source_payload}


def create_app(meta_db_path: str | Path = "data/meta.db", catalog_path: str | Path = "data/catalog.db") -> FastAPI:
    app = FastAPI(title="UBS Hackathon Data Source Backend")
    store = MetaStore(Path(meta_db_path))
    catalog = SchemaCatalog(Path(catalog_path))

    @app.get("/data-sources")
    def list_data_sources() -> list[dict]:
        return [row.to_dict() for row in store.list_data_sources()]

    @app.post("/data-sources", status_code=status.HTTP_201_CREATED)
    def create_data_source(payload: DataSourceCreate) -> dict:
        if store.get_data_source(payload.name):
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Data source already exists")
        created = store.create_data_source(payload.name, payload.type, payload.connection)
        return created.to_dict()

    @app.get("/data-sources/{name}")
    def get_data_source(name: str) -> dict:
        found = store.get_data_source(name)
        if not found:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Data source not found")
        return found.to_dict()

    @app.put("/data-sources/{name}")
    def update_data_source(name: str, payload: DataSourceUpdate) -> dict:
        updated = store.update_data_source(name, type_=payload.type, connection=payload.connection)
        if not updated:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Data source not found")
        return updated.to_dict()

    @app.delete("/data-sources/{name}", status_code=status.HTTP_204_NO_CONTENT)
    def delete_data_source(name: str) -> None:
        deleted = store.delete_data_source(name)
        if not deleted:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Data source not found")

    @app.get("/data-sources/{name}/docs")
    def list_docs(name: str) -> list[dict]:
        if not store.get_data_source(name):
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Data source not found")
        return [row.to_dict() for row in store.list_docs(name)]

    @app.post("/data-sources/{name}/docs", status_code=status.HTTP_201_CREATED)
    def create_doc(name: str, payload: DocCreate) -> dict:
        if not store.get_data_source(name):
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Data source not found")
        created = store.create_doc(name, payload.doc_type, payload.target, payload.content)
        return created.to_dict()

    @app.get("/data-sources/{name}/docs/{doc_id}")
    def get_doc(name: str, doc_id: int) -> dict:
        found = store.get_doc(name, doc_id)
        if not found:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Doc not found")
        return found.to_dict()

    @app.put("/data-sources/{name}/docs/{doc_id}")
    def update_doc(name: str, doc_id: int, payload: DocUpdate) -> dict:
        if not store.get_data_source(name):
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Data source not found")
        updates = payload.model_dump(exclude_unset=True)
        updated = store.update_doc(
            name,
            doc_id,
            doc_type=updates.get("doc_type", _UNSET),
            target=updates.get("target", _UNSET),
            content=updates.get("content", _UNSET),
        )
        if not updated:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Doc not found")
        return updated.to_dict()

    @app.delete("/data-sources/{name}/docs/{doc_id}", status_code=status.HTTP_204_NO_CONTENT)
    def delete_doc(name: str, doc_id: int) -> None:
        deleted = store.delete_doc(name, doc_id)
        if not deleted:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Doc not found")

    @app.post("/data-sources/{name}/sync")
    def sync_data_source(name: str) -> dict:
        registration = store.get_data_source(name)
        if not registration:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Data source not found")
        source = build_data_source(
            DataSourceConfig(name=registration.name, type=registration.type, connection=registration.connection)
        )
        docs_map = _docs_to_schema_map(name, [row.to_dict() for row in store.list_docs(name)])
        total_tables = 0
        for table in source.list_tables():
            doc = source.table_doc(table)
            _apply_schema_docs(doc, docs_map)
            catalog.upsert_table_doc(doc)
            total_tables += 1
        return {"data_source": name, "indexed_tables": total_tables}

    return app


def main() -> None:
    parser = argparse.ArgumentParser(description="Run UBS hackathon metadata backend")
    parser.add_argument("--meta-db", default="data/meta.db", help="Path to metadata SQLite DB")
    parser.add_argument("--catalog", default="data/catalog.db", help="Path to schema catalog DB")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8080)
    args = parser.parse_args()

    app = create_app(meta_db_path=args.meta_db, catalog_path=args.catalog)
    uvicorn.run(app, host=args.host, port=args.port)


if __name__ == "__main__":
    main()
