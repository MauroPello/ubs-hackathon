from __future__ import annotations

import argparse
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path

import uvicorn
from fastapi import FastAPI, HTTPException, status
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, ConfigDict, Field

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
    :root { --bg:#f5f5f5; --card:#ffffff; --muted:#5f6368; --text:#171717; --accent:#e60000; --danger:#b00020; --ok:#0f766e; --line:#d6d6d6; }
    * { box-sizing:border-box; font-family: "Segoe UI", Arial, "Helvetica Neue", Helvetica, sans-serif; }
    body { margin:0; background:linear-gradient(180deg,#ffffff 0,#f5f5f5 100%); color:var(--text); }
    .container { max-width:1200px; margin:24px auto; padding:0 16px 24px; }
    h1 { margin:0 0 8px; font-size:1.85rem; }
    h2,h3 { margin:0 0 10px; }
    p { color:var(--muted); margin:0 0 16px; line-height:1.4; }
    .hero { margin-bottom:14px; }
    .grid-main { display:grid; gap:16px; grid-template-columns:1.15fr .85fr; align-items:start; }
    .grid-side { display:grid; gap:16px; }
    .card { background:var(--card); border:1px solid var(--line); border-radius:14px; padding:14px; box-shadow:0 10px 24px rgba(0,0,0,.08); }
    .row { display:grid; grid-template-columns:1fr 1fr; gap:8px; margin-bottom:8px; }
    .stack { display:flex; flex-direction:column; gap:8px; }
    .actions { display:flex; gap:8px; flex-wrap:wrap; }
    .field { display:flex; flex-direction:column; gap:6px; }
    label { font-size:.86rem; color:#2f2f2f; font-weight:600; }
    .hint { font-size:.78rem; color:var(--muted); }
    input, select, textarea { width:100%; background:#ffffff; border:1px solid var(--line); color:var(--text); padding:9px 10px; border-radius:8px; }
    textarea { min-height:88px; resize:vertical; }
    button { border:0; border-radius:8px; padding:9px 12px; color:#fff; background:var(--accent); cursor:pointer; font-weight:600; }
    button.secondary { background:#1f1f1f; color:#fff; }
    button.ghost { background:#fff; border:1px solid #9ca3af; color:#171717; }
    button.danger { background:var(--danger); }
    button.ok { background:var(--ok); color:#fff; }
    button[disabled] { opacity:.55; cursor:not-allowed; }
    ul { list-style:none; padding:0; margin:0; display:flex; flex-direction:column; gap:8px; max-height:360px; overflow:auto; }
    li { border:1px solid var(--line); border-radius:10px; padding:10px; background:#fcfcfc; }
    .small { font-size:.82rem; color:var(--muted); }
    .pill { display:inline-block; font-size:.72rem; padding:2px 6px; border-radius:999px; background:#fff1f1; border:1px solid #efb0b0; color:#7f1d1d; }
    .pill.fake { background:#fff5f5; border-color:#f4a3a3; color:#9f1239; }
    .split { display:flex; justify-content:space-between; gap:10px; align-items:flex-start; }
    .stats { display:grid; grid-template-columns:repeat(3, 1fr); gap:8px; margin-top:8px; }
    .stat { border:1px solid var(--line); border-radius:10px; padding:10px; background:#fcfcfc; min-height:72px; }
    .stat .value { font-size:1.2rem; font-weight:800; margin-top:4px; }
    .integrations { display:grid; grid-template-columns:1fr 1fr; gap:8px; }
    .integration { border:1px solid var(--line); border-radius:10px; padding:10px; background:#fcfcfc; }
    #message { margin:10px 0 16px; min-height:20px; color:#1f2937; font-weight:600; }
    @media (max-width: 980px) {
      .grid-main { grid-template-columns:1fr; }
      .row { grid-template-columns:1fr; }
      .stats, .integrations { grid-template-columns:1fr; }
    }
  </style>
</head>
<body>
  <div class="container">
    <div class="hero">
      <h1>Data Source Manager</h1>
      <p>
        A richer control center to register and maintain data sources, write business documentation,
        monitor MCP usage, and simulate non-SQL connectors (Notion / Google Workspace).
      </p>
    </div>
    <div id="message"></div>
    <div class="grid-main">
      <section class="card">
        <div class="split">
          <h3>Data Sources</h3>
          <span id="form-mode" class="pill">create mode</span>
        </div>
        <div class="stack">
          <div class="row">
            <div class="field">
              <label for="src-name">Name</label>
              <input id="src-name" placeholder="e.g. sales_sqlite_prod" />
              <div class="hint">Unique key used by MCP tools and endpoints.</div>
            </div>
            <div class="field">
              <label for="src-type">Type</label>
              <select id="src-type">
                <option value="sqlite">sqlite</option>
                <option value="postgresql">postgresql</option>
                <option value="mysql">mysql</option>
                <option value="mssql">mssql</option>
                <option value="oracle">oracle</option>
                <option value="snowflake">snowflake</option>
                <option value="bigquery">bigquery</option>
                <option value="duckdb">duckdb</option>
                <option value="notion">notion (simulated)</option>
                <option value="google_workspace">google_workspace (simulated)</option>
              </select>
              <div class="hint">Choose the source technology or a simulated connector.</div>
            </div>
          </div>
          <div class="field">
            <label for="src-conn">Connection string / path</label>
            <input id="src-conn" placeholder="sqlite:///data/demo.db or postgresql+psycopg2://..." />
            <div class="hint">For legacy sqlite paths, plain file paths are still accepted.</div>
          </div>
          <div class="field">
            <label for="src-sensitive-cols">Sensitive columns</label>
            <input id="src-sensitive-cols" placeholder="e.g. users.email, users.ssn, credit_card_number" />
            <div class="hint">Comma-separated column names (column or table.column) that must be masked in query results.</div>
          </div>
          <div class="actions">
            <button onclick="createSource()">Create source</button>
            <button class="secondary" onclick="updateSource()">Update selected</button>
            <button class="ghost" onclick="prefillSqlite()">Quick fill demo sqlite</button>
            <button class="ghost" onclick="clearSourceForm()">Clear</button>
          </div>
        </div>
        <p class="small">Select a source below to load it into the form and manage docs.</p>
        <ul id="sources"></ul>
      </section>
      <div class="grid-side">
        <section class="card">
          <h3>Documentation <span id="selected" class="pill">none selected</span></h3>
          <div class="stack">
            <div class="row">
              <div class="field">
                <label for="doc-type">Doc type</label>
                <select id="doc-type" onchange="updateDocTargetHint()">
                  <option value="general">general</option>
                  <option value="table">table</option>
                  <option value="column">column</option>
                </select>
              </div>
              <div class="field">
                <label for="doc-target">Target</label>
                <input id="doc-target" placeholder="optional target" />
                <div id="doc-target-hint" class="hint">General docs can leave this empty.</div>
              </div>
            </div>
            <div class="field">
              <label for="doc-content">Documentation content</label>
              <textarea id="doc-content" placeholder="Explain table meaning, KPI logic, ownership, caveats..."></textarea>
            </div>
            <div class="actions">
              <button onclick="addDoc()">Add doc</button>
              <button class="ghost" onclick="clearDocForm()">Clear</button>
            </div>
          </div>
          <ul id="docs"></ul>
        </section>
        <section class="card">
          <h3>MCP Usage Dashboard</h3>
          <p class="small">Lightweight operational snapshot combining real metadata counts and simulated runtime telemetry.</p>
          <div class="stats">
            <div class="stat"><div class="small">Registered sources</div><div id="kpi-sources" class="value">-</div></div>
            <div class="stat"><div class="small">Stored docs</div><div id="kpi-docs" class="value">-</div></div>
            <div class="stat"><div class="small">Indexed tables</div><div id="kpi-tables" class="value">-</div></div>
            <div class="stat"><div class="small">Requests (24h)</div><div id="kpi-requests" class="value">-</div></div>
            <div class="stat"><div class="small">Avg latency</div><div id="kpi-latency" class="value">-</div></div>
            <div class="stat"><div class="small">Success rate</div><div id="kpi-success" class="value">-</div></div>
          </div>
          <div class="stack" style="margin-top:10px">
            <div class="small">Daily requests trend (7d)</div>
            <ul id="usage-trend"></ul>
          </div>
        </section>
        <section class="card">
          <h3>Connector marketplace (simulated)</h3>
          <p class="small">These are fake connections for demos only. They create a local placeholder data source entry.</p>
          <div class="integrations">
            <div class="integration">
              <strong>Notion</strong>
              <p class="small">Simulate connecting team pages as contextual docs.</p>
              <button class="ok" onclick="connectFake('notion')">Connect Notion (fake)</button>
            </div>
            <div class="integration">
              <strong>Google Workspace</strong>
              <p class="small">Simulate connecting docs and spreadsheets as metadata context.</p>
              <button class="ok" onclick="connectFake('google_workspace')">Connect Google Workspace (fake)</button>
            </div>
          </div>
        </section>
      </div>
    </div>
  </div>
  <script>
    let selectedSource = null;
    let selectedSourceType = null;
    const fakeTypes = new Set(["notion", "google_workspace"]);
    const fakeConnectors = {
      notion: {
        name: "notion_workspace_demo",
        type: "notion",
        connection: "sqlite:///data/fake_notion_workspace.db",
      },
      google_workspace: {
        name: "google_workspace_demo",
        type: "google_workspace",
        connection: "sqlite:///data/fake_google_workspace.db",
      },
    };

    const msg = (text, isErr=false) => {
      const el = document.getElementById("message");
      el.textContent = text;
      el.style.color = isErr ? "#b00020" : "#1f2937";
    };

    const req = async (url, opts={}) => {
      const r = await fetch(url, {headers: {"Content-Type":"application/json"}, ...opts});
      if (r.status === 204) return null;
      let data = null;
      try { data = await r.json(); } catch {}
      if (!r.ok) throw new Error(data?.detail || "Request failed");
      return data;
    };

    const parseSensitiveColumns = () => {
      const raw = document.getElementById("src-sensitive-cols").value.trim();
      return raw ? raw.split(",").map((v) => v.trim()).filter(Boolean) : [];
    };

    const updateDocTargetHint = () => {
      const docType = document.getElementById("doc-type").value;
      const hint = document.getElementById("doc-target-hint");
      const target = document.getElementById("doc-target");
      if (docType === "table") {
        hint.textContent = "Use table name, e.g. orders.";
        target.placeholder = "orders";
      } else if (docType === "column") {
        hint.textContent = "Use table.column, e.g. orders.revenue.";
        target.placeholder = "orders.revenue";
      } else {
        hint.textContent = "General docs can leave this empty.";
        target.placeholder = "optional target";
      }
    };

    const clearSourceForm = () => {
      document.getElementById("src-name").value = "";
      document.getElementById("src-type").value = "sqlite";
      document.getElementById("src-conn").value = "";
      document.getElementById("src-sensitive-cols").value = "";
      document.getElementById("form-mode").textContent = "create mode";
    };

    const clearDocForm = () => {
      document.getElementById("doc-type").value = "general";
      document.getElementById("doc-target").value = "";
      document.getElementById("doc-content").value = "";
      updateDocTargetHint();
    };

    const prefillSqlite = () => {
      document.getElementById("src-name").value = "demo_sqlite";
      document.getElementById("src-type").value = "sqlite";
      document.getElementById("src-conn").value = "data/demo_business.db";
      msg("Pre-filled a sqlite source template.");
    };

    const loadSourceIntoForm = (source) => {
      document.getElementById("src-name").value = source.name;
      document.getElementById("src-type").value = source.type;
      document.getElementById("src-conn").value = source.connection;
      document.getElementById("src-sensitive-cols").value = (source.sensitive_columns || []).join(", ");
      document.getElementById("form-mode").textContent = `editing ${source.name}`;
    };

    const refreshUsageDashboard = async () => {
      const usage = await req("/mcp-usage");
      document.getElementById("kpi-sources").textContent = usage.registered_sources;
      document.getElementById("kpi-docs").textContent = usage.stored_docs;
      document.getElementById("kpi-tables").textContent = usage.catalog_tables;
      document.getElementById("kpi-requests").textContent = usage.requests_last_24h;
      document.getElementById("kpi-latency").textContent = `${usage.avg_latency_ms} ms`;
      document.getElementById("kpi-success").textContent = `${usage.success_rate_pct}%`;

      const trend = document.getElementById("usage-trend");
      trend.innerHTML = "";
      for (const item of usage.requests_trend_7d) {
        const li = document.createElement("li");
        li.innerHTML = `<div class="split"><strong>${item.day}</strong><span class="pill">${item.requests} req</span></div>`;
        trend.appendChild(li);
      }
    };

    const refreshSources = async () => {
      const list = await req("/data-sources");
      const container = document.getElementById("sources");
      container.innerHTML = "";
      for (const s of list) {
        const isFake = fakeTypes.has((s.type || "").toLowerCase());
        const li = document.createElement("li");
        li.innerHTML = `
          <div class="split">
            <div><strong>${s.name}</strong> <span class="pill">${s.type}</span> ${isFake ? '<span class="pill fake">simulated</span>' : ""}</div>
            <span class="small">${new Date(s.updated_at).toLocaleString()}</span>
          </div>
          <div class="small">${s.connection}</div>
          <div class="small">Sensitive columns: ${(s.sensitive_columns || []).length}</div>
          <div class="actions" style="margin-top:8px">
            <button class="secondary" data-action="select">Select</button>
            <button class="ok" data-action="sync" ${isFake ? "disabled" : ""}>${isFake ? "Sync N/A" : "Sync catalog"}</button>
            <button class="danger" data-action="delete">Delete</button>
          </div>
        `;

        li.querySelector('[data-action="select"]').onclick = () => {
          selectedSourceType = s.type;
          selectSource(s.name);
          loadSourceIntoForm(s);
        };

        li.querySelector('[data-action="sync"]').onclick = async () => {
          if (isFake) return msg(`'${s.name}' is a simulated connector and does not sync catalog tables.`);
          try {
            const out = await req(`/data-sources/${encodeURIComponent(s.name)}/sync`, {method:"POST"});
            msg(`Synced ${out.indexed_tables} tables for ${s.name}`);
            await refreshUsageDashboard();
          } catch (e) {
            msg(e.message, true);
          }
        };

        li.querySelector('[data-action="delete"]').onclick = async () => {
          try {
            await req(`/data-sources/${encodeURIComponent(s.name)}`, {method:"DELETE"});
            if (selectedSource === s.name) {
              selectedSource = null;
              selectedSourceType = null;
              document.getElementById("selected").textContent = "none selected";
              clearSourceForm();
              await refreshDocs();
            }
            await refreshSources();
            await refreshUsageDashboard();
            msg(`Deleted ${s.name}`);
          } catch (e) {
            msg(e.message, true);
          }
        };
        container.appendChild(li);
      }
    };

    const selectSource = async (name) => {
      selectedSource = name;
      document.getElementById("selected").textContent = name || "none selected";
      await refreshDocs();
    };

    const createSource = async () => {
      const name = document.getElementById("src-name").value.trim();
      const type = document.getElementById("src-type").value.trim();
      const connection = document.getElementById("src-conn").value.trim();
      const sensitive_columns = parseSensitiveColumns();
      if (!name || !type || !connection) return msg("Please fill name, type, and connection.", true);
      try {
        await req("/data-sources", {method:"POST", body: JSON.stringify({name, type, connection, sensitive_columns})});
        await refreshSources();
        await refreshUsageDashboard();
        msg(`Created source '${name}'`);
      } catch (e) {
        msg(e.message, true);
      }
    };

    const updateSource = async () => {
      const name = document.getElementById("src-name").value.trim();
      const type = document.getElementById("src-type").value.trim();
      const connection = document.getElementById("src-conn").value.trim();
      const sensitive_columns = parseSensitiveColumns();
      if (!name || !type || !connection) return msg("Please fill name, type, and connection.", true);
      try {
        await req(`/data-sources/${encodeURIComponent(name)}`, {
          method:"PUT",
          body: JSON.stringify({type, connection, sensitive_columns}),
        });
        selectedSourceType = type;
        await refreshSources();
        msg(`Updated source '${name}'`);
      } catch (e) {
        msg(e.message, true);
      }
    };

    const connectFake = async (provider) => {
      const cfg = fakeConnectors[provider];
      if (!cfg) return;
      try {
        await req("/data-sources", {method:"POST", body: JSON.stringify(cfg)});
        await refreshSources();
        await refreshUsageDashboard();
        msg(`Connected ${provider} (simulated): '${cfg.name}'`);
      } catch (e) {
        if ((e.message || "").includes("already exists")) {
          msg(`${provider} simulated connector already exists.`);
        } else {
          msg(e.message, true);
        }
      }
    };

    const refreshDocs = async () => {
      const container = document.getElementById("docs");
      container.innerHTML = "";
      if (!selectedSource) return;
      const docs = await req(`/data-sources/${encodeURIComponent(selectedSource)}/docs`);
      if (!docs.length) {
        const li = document.createElement("li");
        li.innerHTML = '<div class="small">No docs yet for this source.</div>';
        container.appendChild(li);
        return;
      }
      for (const d of docs) {
        const li = document.createElement("li");
        li.innerHTML = `
          <div class="split">
            <div><strong>#${d.id}</strong> <span class="pill">${d.doc_type}</span> <span class="small">${d.target || "-"}</span></div>
            <span class="small">${new Date(d.updated_at).toLocaleString()}</span>
          </div>
          <div>${d.content}</div>
          <div class="actions" style="margin-top:8px">
            <button class="danger" data-action="delete">Delete</button>
          </div>
        `;
        li.querySelector('[data-action="delete"]').onclick = async () => {
          try {
            await req(`/data-sources/${encodeURIComponent(selectedSource)}/docs/${d.id}`, {method:"DELETE"});
            await refreshDocs();
            await refreshUsageDashboard();
            msg(`Deleted doc #${d.id}`);
          } catch (e) {
            msg(e.message, true);
          }
        };
        container.appendChild(li);
      }
    };

    const addDoc = async () => {
      if (!selectedSource) return msg("Select a source first.", true);
      const doc_type = document.getElementById("doc-type").value;
      const targetValue = document.getElementById("doc-target").value.trim();
      const content = document.getElementById("doc-content").value.trim();
      if (!content) return msg("Documentation content is required.", true);
      try {
        await req(`/data-sources/${encodeURIComponent(selectedSource)}/docs`, {
          method:"POST",
          body: JSON.stringify({doc_type, target: targetValue || null, content}),
        });
        clearDocForm();
        await refreshDocs();
        await refreshUsageDashboard();
        msg("Doc added.");
      } catch (e) {
        msg(e.message, true);
      }
    };

    updateDocTargetHint();
    Promise.all([refreshSources(), refreshUsageDashboard()]).catch((e) => msg(e.message, true));
    setInterval(() => refreshUsageDashboard().catch((e) => msg(e.message, true)), 15000);
  </script>
</body>
</html>
"""


def _usage_trend(seed: int) -> list[dict]:
    today = datetime.now(timezone.utc).date()
    trend: list[dict] = []
    for offset in range(6, -1, -1):
        day = today - timedelta(days=offset)
        daily_requests = max(10, seed - (offset * 3) + ((offset % 3) * 4))
        trend.append({"day": day.strftime("%a"), "requests": daily_requests})
    return trend


def _collect_mcp_usage_snapshot(store: MetaStore, catalog_path: Path) -> dict:
    sources = store.list_data_sources()
    source_count = len(sources)
    docs_count = sum(len(store.list_docs(source.name)) for source in sources)

    with sqlite3.connect(catalog_path) as conn:
        row = conn.execute("SELECT COUNT(*) FROM table_docs").fetchone()
    catalog_tables = int(row[0]) if row else 0

    base = max(24, source_count * 17 + docs_count * 5 + catalog_tables * 9)
    requests_last_24h = base
    search_schema_calls = max(5, int(base * 0.34))
    describe_table_calls = max(5, int(base * 0.28))
    execute_query_calls = max(5, int(base * 0.3))
    list_data_sources_calls = max(4, int(base * 0.08))
    avg_latency_ms = 95 + (base % 80)
    success_rate_pct = round(max(95.0, 99.9 - ((docs_count + source_count) % 20) * 0.15), 1)

    return {
        "registered_sources": source_count,
        "stored_docs": docs_count,
        "catalog_tables": catalog_tables,
        "requests_last_24h": requests_last_24h,
        "avg_latency_ms": avg_latency_ms,
        "success_rate_pct": success_rate_pct,
        "tool_calls_24h": {
            "search_schema": search_schema_calls,
            "describe_table": describe_table_calls,
            "execute_query": execute_query_calls,
            "list_data_sources": list_data_sources_calls,
        },
        "requests_trend_7d": _usage_trend(requests_last_24h),
        "simulated_connectors": ["notion", "google_workspace"],
    }

class DataSourceCreate(BaseModel):
    name: str
    type: str
    connection: str
    sensitive_columns: list[str] = Field(default_factory=list)


class DataSourceUpdate(BaseModel):
    type: str | None = None
    connection: str | None = None
    sensitive_columns: list[str] | None = None

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


def _split_dotted_target(target: str | None) -> tuple[str, str] | None:
    if not target or target.count(".") != 1:
        return None
    left, right = target.split(".", 1)
    if not left or not right:
        return None
    return left, right


def _docs_to_schema_map(data_source: str, docs: list[dict]) -> dict[str, dict]:
    """Map stored doc entries to the schema-doc structure consumed by catalog enrichment."""
    source_payload: dict = {"tables": {}, "graph_entities": {}}
    for doc in docs:
        doc_type = doc.get("doc_type", "").lower()
        target = doc.get("target")
        content = doc.get("content")
        if not content:
            continue
        if doc_type == "graph_entity" and target:
            graph_meta = source_payload["graph_entities"].setdefault(target, {})
            graph_meta["description"] = content
            continue
        graph_target = _split_dotted_target(target)
        if doc_type == "graph_property" and graph_target is not None:
            entity_name, property_name = graph_target
            graph_meta = source_payload["graph_entities"].setdefault(entity_name, {})
            property_meta = graph_meta.setdefault("columns", {})
            property_meta[property_name] = content
            continue
        if doc_type == "table" and target:
            table_meta = source_payload["tables"].setdefault(target, {})
            table_meta["description"] = content
            continue
        if doc_type == "table" and not target:
            # Fallback description for non-graph tables without explicit docs.
            source_payload["default_table_description"] = content
            continue
        table_target = _split_dotted_target(target)
        if doc_type == "column" and table_target is not None:
            table_name, column_name = table_target
            table_meta = source_payload["tables"].setdefault(table_name, {})
            column_meta = table_meta.setdefault("columns", {})
            column_meta[column_name] = content
    return {data_source: source_payload}


def _rebuild_catalog_for_data_source(store: MetaStore, catalog: SchemaCatalog, name: str) -> int:
    registration = store.get_data_source(name)
    if not registration:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Data source not found")

    source = build_data_source(
        DataSourceConfig(
            name=registration.name,
            type=registration.type,
            connection=registration.connection,
            sensitive_columns=registration.sensitive_columns,
        )
    )
    docs_map = _docs_to_schema_map(name, [row.to_dict() for row in store.list_docs(name)])

    total_tables = 0
    for table in source.list_tables():
        doc = source.table_doc(table)
        _apply_schema_docs(doc, docs_map)
        catalog.upsert_table_doc(doc)
        total_tables += 1
    return total_tables


def create_app(meta_db_path: str | Path = "data/meta.db", catalog_path: str | Path = "data/catalog.db") -> FastAPI:
    app = FastAPI(title="UBS Hackathon Data Source Backend")
    store = MetaStore(Path(meta_db_path))
    catalog = SchemaCatalog(Path(catalog_path))

    @app.get("/", include_in_schema=False, response_class=HTMLResponse)
    def frontend() -> str:
        return FRONTEND_HTML

    @app.get("/mcp-usage")
    def mcp_usage() -> dict:
        return _collect_mcp_usage_snapshot(store, Path(catalog_path))

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
        created = store.create_data_source(
            payload.name,
            payload.type,
            payload.connection,
            sensitive_columns=payload.sensitive_columns,
        )
        return created.to_dict()

    @app.get("/data-sources/{name}")
    def get_data_source(name: str) -> dict:
        found = store.get_data_source(name)
        if not found:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Data source not found")
        return found.to_dict()

    @app.put("/data-sources/{name}")
    def update_data_source(name: str, payload: DataSourceUpdate) -> dict:
        updated = store.update_data_source(
            name,
            type_=payload.type,
            connection=payload.connection,
            sensitive_columns=payload.sensitive_columns,
        )
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
        _rebuild_catalog_for_data_source(store, catalog, name)
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
        _rebuild_catalog_for_data_source(store, catalog, name)
        return updated.to_dict()

    @app.delete("/data-sources/{name}/docs/{doc_id}", status_code=status.HTTP_204_NO_CONTENT)
    def delete_doc(name: str, doc_id: int) -> None:
        deleted = store.delete_doc(name, doc_id)
        if not deleted:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Doc not found")
        _rebuild_catalog_for_data_source(store, catalog, name)

    @app.post("/data-sources/{name}/sync")
    def sync_data_source(name: str) -> dict:
        total_tables = _rebuild_catalog_for_data_source(store, catalog, name)
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
