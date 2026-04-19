from __future__ import annotations

import argparse
from pathlib import Path

import uvicorn
from fastapi import FastAPI, HTTPException, status
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, ConfigDict

from .builder import _apply_schema_docs
from .catalog import SchemaCatalog
from .datasource import build_data_source
from .meta_store import MetaStore
from .models import DataSourceConfig

FRONTEND_HTML = """
<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>UBS Data Sources</title>
  <style>
    :root { --bg:#0f172a; --card:#111827; --muted:#94a3b8; --text:#e2e8f0; --accent:#6366f1; --danger:#ef4444; --ok:#22c55e; }
    * { box-sizing:border-box; font-family: Inter, system-ui, -apple-system, Segoe UI, Roboto, sans-serif; }
    body { margin:0; background:linear-gradient(120deg,#0f172a,#1e293b); color:var(--text); }
    .container { max-width:1100px; margin:24px auto; padding:0 16px; }
    h1 { margin:0 0 8px; font-size:1.6rem; }
    p { color:var(--muted); margin:0 0 16px; }
    .grid { display:grid; gap:16px; grid-template-columns:1fr 1fr; }
    .card { background:rgba(17,24,39,.92); border:1px solid #334155; border-radius:14px; padding:14px; box-shadow:0 10px 30px rgba(0,0,0,.25); }
    .row { display:flex; gap:8px; align-items:center; flex-wrap:wrap; margin-bottom:8px; }
    input, select, textarea { width:100%; background:#0b1220; border:1px solid #334155; color:var(--text); padding:8px 10px; border-radius:8px; }
    textarea { min-height:80px; resize:vertical; }
    button { border:0; border-radius:8px; padding:8px 10px; color:white; background:var(--accent); cursor:pointer; font-weight:600; }
    button.secondary { background:#334155; }
    button.danger { background:var(--danger); }
    button.ok { background:var(--ok); color:#052e16; }
    ul { list-style:none; padding:0; margin:0; display:flex; flex-direction:column; gap:8px; }
    li { border:1px solid #334155; border-radius:10px; padding:10px; background:#0b1220; }
    .small { font-size:.85rem; color:var(--muted); }
    .pill { display:inline-block; font-size:.75rem; padding:2px 6px; border-radius:999px; background:#1f2937; border:1px solid #374151; }
    #message { margin:10px 0; min-height:20px; color:#cbd5e1; }
    @media (max-width: 900px) { .grid { grid-template-columns: 1fr; } }
  </style>
</head>
<body>
  <div class="container">
    <h1>Data Source Manager</h1>
    <p>Small hackathon UI for managing sources, docs, and catalog sync.</p>
    <div id="message"></div>
    <div class="grid">
      <section class="card">
        <h3>Data Sources</h3>
        <div class="row">
          <input id="src-name" placeholder="name (e.g. demo_sqlite)" />
          <input id="src-type" placeholder="type (e.g. sqlite)" />
          <input id="src-conn" placeholder="connection (db path or URI)" />
          <button onclick="addSource()">Add source</button>
        </div>
        <ul id="sources"></ul>
      </section>
      <section class="card">
        <h3>Documentation <span id="selected" class="pill">none selected</span></h3>
        <div class="row">
          <select id="doc-type">
            <option value="general">general</option>
            <option value="table">table</option>
            <option value="column">column</option>
          </select>
          <input id="doc-target" placeholder="target (table or table.column)" />
          <textarea id="doc-content" placeholder="content"></textarea>
          <button onclick="addDoc()">Add doc</button>
        </div>
        <ul id="docs"></ul>
      </section>
    </div>
  </div>
  <script>
    let selectedSource = null;
    const msg = (text, isErr=false) => {
      const el = document.getElementById("message");
      el.textContent = text;
      el.style.color = isErr ? "#fca5a5" : "#cbd5e1";
    };
    const req = async (url, opts={}) => {
      const r = await fetch(url, {headers: {"Content-Type":"application/json"}, ...opts});
      if (r.status === 204) return null;
      let data = null;
      try { data = await r.json(); } catch {}
      if (!r.ok) throw new Error(data?.detail || "Request failed");
      return data;
    };
    const refreshSources = async () => {
      const list = await req("/data-sources");
      const container = document.getElementById("sources");
      container.innerHTML = "";
      for (const s of list) {
        const li = document.createElement("li");
        li.innerHTML = `
          <div><strong>${s.name}</strong> <span class="pill">${s.type}</span></div>
          <div class="small">${s.connection}</div>
          <div class="row">
            <button class="secondary" data-action="select">Select</button>
            <button class="ok" data-action="sync">Sync</button>
            <button class="danger" data-action="delete">Delete</button>
          </div>
        `;
        li.querySelector('[data-action="select"]').onclick = () => selectSource(s.name);
        li.querySelector('[data-action="sync"]').onclick = async () => {
          try {
            const out = await req(`/data-sources/${encodeURIComponent(s.name)}/sync`, {method:"POST"});
            msg(`Synced ${out.indexed_tables} tables for ${s.name}`);
          } catch (e) { msg(e.message, true); }
        };
        li.querySelector('[data-action="delete"]').onclick = async () => {
          try {
            await req(`/data-sources/${encodeURIComponent(s.name)}`, {method:"DELETE"});
            if (selectedSource === s.name) selectSource(null);
            await refreshSources();
            msg(`Deleted ${s.name}`);
          } catch (e) { msg(e.message, true); }
        };
        container.appendChild(li);
      }
    };
    const selectSource = async (name) => {
      selectedSource = name;
      document.getElementById("selected").textContent = name || "none selected";
      await refreshDocs();
    };
    const addSource = async () => {
      const name = document.getElementById("src-name").value.trim();
      const type = document.getElementById("src-type").value.trim();
      const connection = document.getElementById("src-conn").value.trim();
      if (!name || !type || !connection) return msg("Please fill all source fields", true);
      try {
        await req("/data-sources", {method:"POST", body: JSON.stringify({name, type, connection})});
        document.getElementById("src-name").value = "";
        document.getElementById("src-type").value = "";
        document.getElementById("src-conn").value = "";
        await refreshSources();
        msg(`Added ${name}`);
      } catch (e) { msg(e.message, true); }
    };
    const refreshDocs = async () => {
      const container = document.getElementById("docs");
      container.innerHTML = "";
      if (!selectedSource) return;
      const docs = await req(`/data-sources/${encodeURIComponent(selectedSource)}/docs`);
      for (const d of docs) {
        const li = document.createElement("li");
        li.innerHTML = `
          <div><strong>#${d.id}</strong> <span class="pill">${d.doc_type}</span> <span class="small">${d.target || "-"}</span></div>
          <div>${d.content}</div>
          <div class="row">
            <button class="danger" data-action="delete">Delete</button>
          </div>
        `;
        li.querySelector('[data-action="delete"]').onclick = async () => {
          try {
            await req(`/data-sources/${encodeURIComponent(selectedSource)}/docs/${d.id}`, {method:"DELETE"});
            await refreshDocs();
            msg(`Deleted doc #${d.id}`);
          } catch (e) { msg(e.message, true); }
        };
        container.appendChild(li);
      }
    };
    const addDoc = async () => {
      if (!selectedSource) return msg("Select a source first", true);
      const doc_type = document.getElementById("doc-type").value;
      const targetValue = document.getElementById("doc-target").value.trim();
      const content = document.getElementById("doc-content").value.trim();
      if (!content) return msg("Doc content is required", true);
      try {
        await req(`/data-sources/${encodeURIComponent(selectedSource)}/docs`, {
          method:"POST",
          body: JSON.stringify({doc_type, target: targetValue || null, content}),
        });
        document.getElementById("doc-target").value = "";
        document.getElementById("doc-content").value = "";
        await refreshDocs();
        msg("Doc added");
      } catch (e) { msg(e.message, true); }
    };
    refreshSources().catch((e) => msg(e.message, true));
  </script>
</body>
</html>
"""


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


def _docs_to_schema_map(data_source: str, docs: list[dict]) -> dict[str, dict]:
    """Map stored doc entries to the schema-doc structure consumed by catalog enrichment."""
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
        if doc_type == "column" and target and target.count(".") == 1:
            table_name, column_name = target.split(".", 1)
            table_meta = source_payload["tables"].setdefault(table_name, {})
            column_meta = table_meta.setdefault("columns", {})
            column_meta[column_name] = content
    return {data_source: source_payload}


def create_app(meta_db_path: str | Path = "data/meta.db", catalog_path: str | Path = "data/catalog.db") -> FastAPI:
    app = FastAPI(title="UBS Hackathon Data Source Backend")
    store = MetaStore(Path(meta_db_path))
    catalog = SchemaCatalog(Path(catalog_path))

    @app.get("/", include_in_schema=False, response_class=HTMLResponse)
    def frontend() -> str:
        return FRONTEND_HTML

    @app.get("/data-sources")
    def list_data_sources() -> list[dict]:
        return [row.to_dict() for row in store.list_data_sources()]

    @app.post("/data-sources", status_code=status.HTTP_201_CREATED)
    def create_data_source(payload: DataSourceCreate) -> dict:
        if store.get_data_source(payload.name):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Data source '{payload.name}' already exists",
            )
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
        try:
            updated = store.update_doc(name, doc_id, **updates)
        except ValueError as exc:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(exc)) from exc
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
