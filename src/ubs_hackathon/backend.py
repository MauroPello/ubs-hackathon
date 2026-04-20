from __future__ import annotations

import argparse
import re
import sqlite3
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

import uvicorn
from fastapi import FastAPI, HTTPException, status
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, ConfigDict, Field

from .builder import _apply_schema_docs
from .catalog import SchemaCatalog
from .datasource import build_data_source
from .meta_store import MetaStore, _UNSET
from .models import DataSourceConfig
from .registry import UPSTREAM_MCP_REGISTRY, get_registry_entry, list_registry_entries

_UNSET_SENTINEL = _UNSET

FRONTEND_COMMON_STYLE = """
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
    .grid-cards { display:grid; gap:16px; grid-template-columns:1fr 1fr; }
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
    ul { list-style:none; padding:0; margin:0; display:flex; flex-direction:column; gap:8px; max-height:420px; overflow:auto; }
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
    .topbar { display:flex; justify-content:space-between; align-items:center; gap:12px; margin-bottom:16px; }
    .nav { display:flex; gap:8px; flex-wrap:wrap; }
    .nav a { text-decoration:none; color:#171717; border:1px solid var(--line); border-radius:999px; padding:6px 11px; font-weight:600; background:#fff; }
    .nav a.active { background:#171717; color:#fff; border-color:#171717; }
    #message { margin:10px 0 16px; min-height:20px; color:#1f2937; font-weight:600; }
    @media (max-width: 980px) {
      .grid-main, .grid-cards, .integrations, .stats { grid-template-columns:1fr; }
      .row { grid-template-columns:1fr; }
    }
  </style>
"""


def _frontend_page(title: str, active_tab: str, body: str, script: str = "") -> str:
    nav_items = {
        "home": ("/", "Overview"),
        "sources": ("/sources", "Sources & Docs"),
        "dashboard": ("/dashboard", "Usage Dashboard"),
        "mcp-servers": ("/mcp-servers", "MCP Servers"),
    }
    nav_html = "".join(
        f'<a href="{href}" class="{"active" if key == active_tab else ""}">{label}</a>'
        for key, (href, label) in nav_items.items()
    )

    return f"""
<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>{title}</title>
{FRONTEND_COMMON_STYLE}
</head>
<body>
  <div class="container">
    <div class="topbar">
      <h1>Data Source Manager</h1>
      <nav class="nav">{nav_html}</nav>
    </div>
    {body}
  </div>
  <script>
{script}
  </script>
</body>
</html>
"""


def _frontend_home_html() -> str:
    body = """
    <div class="hero card">
      <p>
        Multi-page control center for data source onboarding, business documentation,
        runtime monitoring, and simulated connector demos.
      </p>
      <div class="grid-cards">
        <a class="card" href="/sources" style="text-decoration:none;color:inherit;display:block;">
          <h3>Sources & Docs</h3>
          <p>Register data sources, set sensitive columns, and manage table/column documentation.</p>
        </a>
        <a class="card" href="/dashboard" style="text-decoration:none;color:inherit;display:block;">
          <h3>MCP Usage Dashboard</h3>
          <p>Track requests, latency, success rate, and trend data from backend telemetry.</p>
        </a>
        <a class="card" href="/mcp-servers" style="text-decoration:none;color:inherit;display:block;">
          <h3>MCP Servers</h3>
          <p>Register and configure upstream MCP servers (Neo4j, Notion, …) and expose their tools as proxy tools.</p>
        </a>
      </div>
    </div>
    """
    return _frontend_page("UBS Data Sources", "home", body)


def _frontend_sources_html() -> str:
    body = """
    <p>
      Register and maintain data sources, then attach documentation that enriches the schema catalog.
    </p>
    <div id="message"></div>
    <div class="grid-main">
      <section class="card">
        <div class="split">
          <h3>Data Sources</h3>
          <span id="form-mode" class="pill">create mode</span>
        </div>
        <div class="stack">
          <div class="field">
            <label>Data Category</label>
            <div class="actions">
              <button id="cat-sql" class="ok" onclick="setCategory('sql')">SQL-like</button>
              <button id="cat-graph" class="ghost" onclick="setCategory('graph')">Graph</button>
              <button id="cat-documents" class="ghost" onclick="setCategory('documents')">Documents</button>
            </div>
            <div class="hint">SQL-like sources are handled in-house. Graph and Document sources require an upstream MCP server.</div>
          </div>
          <div class="row">
            <div class="field">
              <label for="src-name">Name</label>
              <input id="src-name" placeholder="e.g. sales_sqlite_prod" />
              <div class="hint">Unique key used by MCP tools and endpoints.</div>
            </div>
            <div class="field" id="field-src-type">
              <label for="src-type">SQL Dialect</label>
              <select id="src-type">
                <option value="sqlite">sqlite</option>
                <option value="postgresql">postgresql</option>
                <option value="mysql">mysql</option>
                <option value="mssql">mssql</option>
                <option value="oracle">oracle</option>
                <option value="snowflake">snowflake</option>
                <option value="bigquery">bigquery</option>
                <option value="duckdb">duckdb</option>
              </select>
            </div>
          </div>
          <div class="field" id="field-src-conn">
            <label for="src-conn">Connection string / path</label>
            <input id="src-conn" placeholder="sqlite:///data/demo.db or postgresql+psycopg2://..." />
          </div>
          <div class="field" id="field-src-upstream" style="display:none">
            <label for="src-upstream">Upstream MCP Server</label>
            <select id="src-upstream">
              <option value="">-- select a configured upstream MCP server --</option>
            </select>
            <div class="hint">Select a configured upstream MCP server. Configure servers on the <a href="/mcp-servers">MCP Servers</a> page.</div>
          </div>
          <div class="field">
            <label for="src-sensitive-cols">Sensitive columns</label>
            <input id="src-sensitive-cols" placeholder="e.g. users.email, users.ssn, credit_card_number" />
            <div class="hint">Comma-separated column names (column or table.column).</div>
          </div>
          <div class="field">
            <label for="src-desc">Documentation description</label>
            <textarea id="src-desc" placeholder="Describe source ownership and intended usage."></textarea>
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
            <textarea id="doc-content" placeholder="Explain KPI logic, caveats, ownership..."></textarea>
          </div>
          <div class="actions">
            <button onclick="addDoc()">Add doc</button>
            <button class="ghost" onclick="clearDocForm()">Clear</button>
          </div>
        </div>
        <ul id="docs"></ul>
      </section>
    </div>
    """

    script = """
    let selectedSource = null;
    let currentCategory = "sql";
    const upstreamTypeMap = {};  // config_id -> data_type

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

    const setCategory = (cat) => {
      currentCategory = cat;
      ["sql","graph","documents"].forEach(c => {
        const btn = document.getElementById("cat-"+c);
        btn.className = c === cat ? "ok" : "ghost";
      });
      const isSql = cat === "sql";
      document.getElementById("field-src-type").style.display = isSql ? "" : "none";
      document.getElementById("field-src-conn").style.display = isSql ? "" : "none";
      document.getElementById("field-src-upstream").style.display = isSql ? "none" : "";
      if (!isSql) refreshUpstreamOptions(cat);
    };

    const refreshUpstreamOptions = async (cat) => {
      const configs = await req("/upstream-mcp-server-configs");
      const sel = document.getElementById("src-upstream");
      sel.innerHTML = '<option value="">-- select a configured upstream MCP server --</option>';
      const filtered = configs.filter(c => upstreamTypeMap[c.id] === cat || !upstreamTypeMap[c.id]);
      for (const c of filtered) {
        const opt = document.createElement("option");
        opt.value = c.id;
        opt.textContent = `${c.name} (${c.server_id})`;
        sel.appendChild(opt);
      }
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
      document.getElementById("src-desc").value = "";
      document.getElementById("form-mode").textContent = "create mode";
      setCategory("sql");
    };

    const clearDocForm = () => {
      document.getElementById("doc-type").value = "general";
      document.getElementById("doc-target").value = "";
      document.getElementById("doc-content").value = "";
      updateDocTargetHint();
    };

    const prefillSqlite = () => {
      setCategory("sql");
      document.getElementById("src-name").value = "demo_sqlite";
      document.getElementById("src-type").value = "sqlite";
      document.getElementById("src-conn").value = "data/demo_business.db";
      msg("Pre-filled a sqlite source template.");
    };

    const _detectCategory = (source) => {
      if (source.upstream_mcp_server_config_id) {
        return upstreamTypeMap[source.upstream_mcp_server_config_id] || "graph";
      }
      const t = (source.type || "").toLowerCase();
      if (["graph","documents"].includes(t)) return t;
      return "sql";
    };

    const loadSourceIntoForm = (source) => {
      document.getElementById("src-name").value = source.name;
      document.getElementById("src-sensitive-cols").value = (source.sensitive_columns || []).join(", ");
      document.getElementById("src-desc").value = source.description || "";
      document.getElementById("form-mode").textContent = `editing ${source.name}`;
      const cat = _detectCategory(source);
      setCategory(cat);
      if (cat === "sql") {
        document.getElementById("src-type").value = source.type || "sqlite";
        document.getElementById("src-conn").value = source.connection || "";
      } else {
        document.getElementById("src-upstream").value = source.upstream_mcp_server_config_id || "";
      }
    };

    const refreshSources = async () => {
      const list = await req("/data-sources");
      const container = document.getElementById("sources");
      container.innerHTML = "";
      for (const s of list) {
        const isUpstream = !!s.upstream_mcp_server_config_id;
        const li = document.createElement("li");
        const catBadge = isUpstream
          ? `<span class="pill">${upstreamTypeMap[s.upstream_mcp_server_config_id] || s.type}</span>`
          : `<span class="pill">${s.type}</span>`;
        const canSync = !isUpstream;
        li.innerHTML = `
          <div class="split">
            <div><strong>${s.name}</strong> ${catBadge} ${isUpstream ? '<span class="pill fake">upstream MCP</span>' : ""}</div>
            <span class="small">${new Date(s.updated_at).toLocaleString()}</span>
          </div>
          <div class="small">${s.description || "No description yet."}</div>
          <div class="small">${isUpstream ? "Upstream config: "+s.upstream_mcp_server_config_id : s.connection}</div>
          <div class="small">Sensitive columns: ${(s.sensitive_columns || []).length}</div>
          <div class="actions" style="margin-top:8px">
            <button class="secondary" data-action="select">Select</button>
            <button class="ok" data-action="sync" ${!canSync ? "disabled" : ""}>${!canSync ? "Sync N/A" : "Sync catalog"}</button>
            <button class="danger" data-action="delete">Delete</button>
          </div>
        `;

        li.querySelector('[data-action="select"]').onclick = () => {
          selectSource(s.name);
          loadSourceIntoForm(s);
        };

        li.querySelector('[data-action="sync"]').onclick = async () => {
          if (!canSync) return msg(`'${s.name}' uses an upstream MCP server and does not sync catalog tables.`);
          try {
            const out = await req(`/data-sources/${encodeURIComponent(s.name)}/sync`, {method:"POST"});
            msg(`Synced ${out.indexed_tables} tables for ${s.name}`);
          } catch (e) {
            msg(e.message, true);
          }
        };

        li.querySelector('[data-action="delete"]').onclick = async () => {
          try {
            await req(`/data-sources/${encodeURIComponent(s.name)}`, {method:"DELETE"});
            if (selectedSource === s.name) {
              selectedSource = null;
              document.getElementById("selected").textContent = "none selected";
              clearSourceForm();
              await refreshDocs();
            }
            await refreshSources();
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
      const sensitive_columns = parseSensitiveColumns();
      const description = document.getElementById("src-desc").value.trim();
      if (!name) return msg("Please fill in the source name.", true);
      let payload = {name, sensitive_columns, description: description || null};
      if (currentCategory === "sql") {
        const type = document.getElementById("src-type").value.trim();
        const connection = document.getElementById("src-conn").value.trim();
        if (!connection) return msg("Please fill in the connection string.", true);
        payload = {...payload, type, connection};
      } else {
        const upstreamId = document.getElementById("src-upstream").value;
        if (!upstreamId) return msg("Please select an upstream MCP server configuration.", true);
        payload = {...payload, type: currentCategory, connection: "upstream://"+upstreamId, upstream_mcp_server_config_id: upstreamId};
      }
      try {
        await req("/data-sources", {method:"POST", body: JSON.stringify(payload)});
        await refreshSources();
        msg(`Created source '${name}'`);
      } catch (e) {
        msg(e.message, true);
      }
    };

    const updateSource = async () => {
      const name = document.getElementById("src-name").value.trim();
      const sensitive_columns = parseSensitiveColumns();
      const description = document.getElementById("src-desc").value.trim();
      if (!name) return msg("Please fill in the source name.", true);
      let payload = {sensitive_columns, description: description || null};
      if (currentCategory === "sql") {
        const type = document.getElementById("src-type").value.trim();
        const connection = document.getElementById("src-conn").value.trim();
        if (!connection) return msg("Please fill in the connection string.", true);
        payload = {...payload, type, connection};
      } else {
        const upstreamId = document.getElementById("src-upstream").value;
        if (!upstreamId) return msg("Please select an upstream MCP server configuration.", true);
        payload = {...payload, type: currentCategory, connection: "upstream://"+upstreamId, upstream_mcp_server_config_id: upstreamId};
      }
      try {
        await req(`/data-sources/${encodeURIComponent(name)}`, {method:"PUT", body: JSON.stringify(payload)});
        await refreshSources();
        msg(`Updated source '${name}'`);
      } catch (e) {
        msg(e.message, true);
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
        msg("Doc added.");
      } catch (e) {
        msg(e.message, true);
      }
    };

    // Pre-load upstream configs to build the type map
    const initUpstreamTypeMap = async () => {
      try {
        const registry = await req("/upstream-mcp-servers");
        const byId = {};
        for (const e of registry) byId[e.id] = e.data_type;
        const configs = await req("/upstream-mcp-server-configs");
        for (const c of configs) {
          upstreamTypeMap[c.id] = byId[c.server_id] || "graph";
        }
      } catch {}
    };

    updateDocTargetHint();
    setCategory("sql");
    initUpstreamTypeMap().then(() => refreshSources().catch((e) => msg(e.message, true)));
    """
    return _frontend_page("UBS Data Sources | Sources", "sources", body, script)


def _frontend_dashboard_html() -> str:
    body = """
    <p>
      Lightweight operational snapshot combining real metadata counts and simulated runtime telemetry.
    </p>
    <div id="message"></div>
    <section class="card">
      <h3>MCP Usage Dashboard</h3>
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
    """

    script = """
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

    refreshUsageDashboard().catch((e) => msg(e.message, true));
    setInterval(() => refreshUsageDashboard().catch((e) => msg(e.message, true)), 15000);
    """
    return _frontend_page("UBS Data Sources | Dashboard", "dashboard", body, script)


def _frontend_mcp_servers_html() -> str:
    body = """
    <p>
      Browse the upstream MCP server registry and configure server instances with authentication and tool selection.
      Configured servers can be referenced when creating data sources.
    </p>
    <div id="message"></div>
    <div class="grid-main">
      <section class="card">
        <h3>Available Upstream MCP Servers</h3>
        <ul id="registry-list"></ul>
        <div style="margin-top:16px">
          <h3>Configure an Upstream MCP Server</h3>
          <div class="stack" id="config-form">
            <div class="row">
              <div class="field">
                <label for="cfg-server">Server</label>
                <select id="cfg-server" onchange="onServerSelect()">
                  <option value="">-- select from registry --</option>
                </select>
              </div>
              <div class="field">
                <label for="cfg-name">Config name</label>
                <input id="cfg-name" placeholder="e.g. my_neo4j" />
                <div class="hint">A unique name for this configuration.</div>
              </div>
            </div>
            <div class="field">
              <label for="cfg-endpoint">Endpoint URL</label>
              <input id="cfg-endpoint" placeholder="e.g. http://localhost:9000/mcp-proxy" />
              <div class="hint">HTTP endpoint where this MCP server accepts tool calls.</div>
            </div>
            <div id="cfg-auth-fields" class="stack"></div>
            <div class="field">
              <label>Exposed Tools</label>
              <div id="cfg-tools-checkboxes" class="stack"></div>
              <div class="hint">Select which tools to expose as proxy tools on this MCP server.</div>
            </div>
            <div class="actions">
              <button onclick="saveConfig()">Save configuration</button>
              <button class="ghost" onclick="clearConfigForm()">Clear</button>
            </div>
          </div>
        </div>
      </section>
      <section class="card">
        <h3>Configured Instances</h3>
        <ul id="configs-list"></ul>
      </section>
    </div>
    """

    script = """
    let registryData = [];
    let editingConfigId = null;

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

    const onServerSelect = () => {
      const serverId = document.getElementById("cfg-server").value;
      const entry = registryData.find(e => e.id === serverId);
      const authDiv = document.getElementById("cfg-auth-fields");
      const toolsDiv = document.getElementById("cfg-tools-checkboxes");
      authDiv.innerHTML = "";
      toolsDiv.innerHTML = "";
      if (!entry) return;
      // Auth fields
      for (const [key, spec] of Object.entries(entry.auth_schema || {})) {
        const field = document.createElement("div");
        field.className = "field";
        const label = document.createElement("label");
        label.textContent = key + (spec.secret ? " (secret)" : "");
        const input = document.createElement("input");
        input.id = "cfg-auth-" + key;
        input.type = spec.secret ? "password" : "text";
        input.placeholder = spec.description || "";
        const hint = document.createElement("div");
        hint.className = "hint";
        hint.textContent = spec.description || "";
        field.appendChild(label);
        field.appendChild(input);
        field.appendChild(hint);
        authDiv.appendChild(field);
      }
      // Tool checkboxes
      const toolLabel = document.createElement("label");
      toolLabel.textContent = "Select tools to expose:";
      toolsDiv.appendChild(toolLabel);
      for (const tool of (entry.tools || [])) {
        const row = document.createElement("div");
        row.style.display = "flex";
        row.style.gap = "8px";
        row.style.alignItems = "center";
        const cb = document.createElement("input");
        cb.type = "checkbox";
        cb.id = "cfg-tool-" + tool.name;
        cb.value = tool.name;
        cb.checked = true;
        const lbl = document.createElement("label");
        lbl.htmlFor = "cfg-tool-" + tool.name;
        lbl.textContent = tool.name + " — " + (tool.description || "");
        row.appendChild(cb);
        row.appendChild(lbl);
        toolsDiv.appendChild(row);
      }
    };

    const clearConfigForm = () => {
      editingConfigId = null;
      document.getElementById("cfg-server").value = "";
      document.getElementById("cfg-name").value = "";
      document.getElementById("cfg-endpoint").value = "";
      document.getElementById("cfg-auth-fields").innerHTML = "";
      document.getElementById("cfg-tools-checkboxes").innerHTML = "";
    };

    const saveConfig = async () => {
      const serverId = document.getElementById("cfg-server").value;
      const name = document.getElementById("cfg-name").value.trim();
      const endpoint = document.getElementById("cfg-endpoint").value.trim();
      if (!serverId) return msg("Please select a server from the registry.", true);
      if (!name) return msg("Please provide a configuration name.", true);
      const entry = registryData.find(e => e.id === serverId);
      const auth = {};
      for (const key of Object.keys(entry?.auth_schema || {})) {
        const el = document.getElementById("cfg-auth-" + key);
        if (el) auth[key] = el.value;
      }
      const exposed_tools = [];
      for (const tool of (entry?.tools || [])) {
        const cb = document.getElementById("cfg-tool-" + tool.name);
        if (cb && cb.checked) exposed_tools.push(tool.name);
      }
      try {
        if (editingConfigId) {
          await req(`/upstream-mcp-server-configs/${encodeURIComponent(editingConfigId)}`, {
            method: "PUT",
            body: JSON.stringify({name, endpoint: endpoint || null, auth, exposed_tools}),
          });
          msg(`Updated configuration '${name}'`);
        } else {
          await req("/upstream-mcp-server-configs", {
            method: "POST",
            body: JSON.stringify({server_id: serverId, name, endpoint: endpoint || null, auth, exposed_tools}),
          });
          msg(`Saved configuration '${name}'`);
        }
        clearConfigForm();
        await refreshConfigs();
      } catch (e) {
        msg(e.message, true);
      }
    };

    const refreshRegistry = async () => {
      registryData = await req("/upstream-mcp-servers");
      const container = document.getElementById("registry-list");
      container.innerHTML = "";
      const sel = document.getElementById("cfg-server");
      sel.innerHTML = '<option value="">-- select from registry --</option>';
      for (const entry of registryData) {
        const isAvailable = entry.status === "available";
        const li = document.createElement("li");
        li.innerHTML = `
          <div class="split">
            <div><strong>${entry.name}</strong> <span class="pill">${entry.data_type}</span>
              <span class="pill" style="${isAvailable ? "background:#d1fae5;border-color:#6ee7b7;color:#065f46" : "background:#fff1f1;border-color:#efb0b0;color:#7f1d1d"}">
                ${isAvailable ? "available" : "unavailable"}
              </span>
            </div>
          </div>
          <div class="small">${entry.description || ""}</div>
          <div class="small" style="margin-top:4px">Tools: ${(entry.tools || []).map(t => t.name).join(", ")}</div>
          ${entry.requires_auth ? '<div class="small">Requires auth: ' + Object.keys(entry.auth_schema || {}).join(", ") + '</div>' : ""}
          <div class="small">${entry.is_local ? "Local server" : "External (cloud)"}</div>
          <div class="actions" style="margin-top:8px">
            <button class="ok" onclick="startConfigure('${entry.id}')" ${!isAvailable ? "disabled" : ""}>
              ${isAvailable ? "Configure" : "Not available"}
            </button>
          </div>
        `;
        container.appendChild(li);
        if (isAvailable) {
          const opt = document.createElement("option");
          opt.value = entry.id;
          opt.textContent = entry.name + " (" + entry.data_type + ")";
          sel.appendChild(opt);
        }
      }
    };

    const startConfigure = (serverId) => {
      document.getElementById("cfg-server").value = serverId;
      onServerSelect();
      document.getElementById("cfg-name").focus();
    };

    const refreshConfigs = async () => {
      const configs = await req("/upstream-mcp-server-configs");
      const container = document.getElementById("configs-list");
      container.innerHTML = "";
      if (!configs.length) {
        const li = document.createElement("li");
        li.innerHTML = '<div class="small">No upstream MCP server configurations yet. Use the form on the left to create one.</div>';
        container.appendChild(li);
        return;
      }
      for (const c of configs) {
        const li = document.createElement("li");
        const reg = registryData.find(e => e.id === c.server_id) || {};
        li.innerHTML = `
          <div class="split">
            <div><strong>${c.name}</strong> <span class="pill">${reg.name || c.server_id}</span> <span class="pill">${reg.data_type || ""}</span></div>
            <span class="small">${new Date(c.updated_at).toLocaleString()}</span>
          </div>
          <div class="small">Endpoint: ${c.endpoint || "(none)"}</div>
          <div class="small">Exposed tools: ${(c.exposed_tools || []).join(", ") || "(none)"}</div>
          <div class="actions" style="margin-top:8px">
            <button class="secondary" onclick="editConfig('${c.id}')">Edit</button>
            <button class="danger" onclick="deleteConfig('${c.id}', '${c.name}')">Delete</button>
          </div>
        `;
        container.appendChild(li);
      }
    };

    const editConfig = async (configId) => {
      const configs = await req("/upstream-mcp-server-configs");
      const c = configs.find(x => x.id === configId);
      if (!c) return;
      editingConfigId = configId;
      document.getElementById("cfg-server").value = c.server_id;
      onServerSelect();
      document.getElementById("cfg-name").value = c.name;
      document.getElementById("cfg-endpoint").value = c.endpoint || "";
      // Fill auth fields after a tick so DOM updates
      setTimeout(() => {
        for (const [key, val] of Object.entries(c.auth || {})) {
          const el = document.getElementById("cfg-auth-" + key);
          if (el) el.value = val;
        }
        for (const toolName of (c.exposed_tools || [])) {
          const cb = document.getElementById("cfg-tool-" + toolName);
          if (cb) cb.checked = true;
        }
        // Uncheck tools not in exposed list
        const reg = registryData.find(e => e.id === c.server_id) || {};
        for (const tool of (reg.tools || [])) {
          const cb = document.getElementById("cfg-tool-" + tool.name);
          if (cb && !(c.exposed_tools || []).includes(tool.name)) cb.checked = false;
        }
        msg(`Editing '${c.name}' — make changes and click Save.`);
      }, 50);
    };

    const deleteConfig = async (configId, name) => {
      try {
        await req(`/upstream-mcp-server-configs/${encodeURIComponent(configId)}`, {method:"DELETE"});
        await refreshConfigs();
        msg(`Deleted configuration '${name}'`);
      } catch (e) {
        msg(e.message, true);
      }
    };

    refreshRegistry().then(() => refreshConfigs()).catch((e) => msg(e.message, true));
    """
    return _frontend_page("UBS Data Sources | MCP Servers", "mcp-servers", body, script)


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
    success_rate_pct = round(
        max(95.0, 99.9 - ((docs_count + source_count) % 20) * 0.15), 1
    )

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
    description: str | None = None
    upstream_mcp_server_config_id: str | None = None

    model_config = ConfigDict(extra="forbid")


class DataSourceUpdate(BaseModel):
    type: str | None = None
    connection: str | None = None
    sensitive_columns: list[str] | None = None
    description: str | None = None
    upstream_mcp_server_config_id: str | None = None

    model_config = ConfigDict(extra="forbid")


class UpstreamMCPServerConfigCreate(BaseModel):
    server_id: str
    name: str
    endpoint: str | None = None
    auth: dict = Field(default_factory=dict)
    exposed_tools: list[str] = Field(default_factory=list)

    model_config = ConfigDict(extra="forbid")


class UpstreamMCPServerConfigUpdate(BaseModel):
    name: str | None = None
    endpoint: str | None = None
    auth: dict | None = None
    exposed_tools: list[str] | None = None

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


_SLUG_INVALID = re.compile(r"[^A-Za-z0-9_\-]")


def _make_config_id(name: str) -> str:
    """Generate a URL-safe config ID from a name, appended with a short UUID fragment."""
    slug = _SLUG_INVALID.sub("_", name.strip().lower())[:32].strip("_") or "cfg"
    return f"{slug}_{uuid.uuid4().hex[:8]}"


def _rebuild_catalog_for_data_source(
    store: MetaStore, catalog: SchemaCatalog, name: str
) -> int:
    registration = store.get_data_source(name)
    if not registration:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Data source not found"
        )

    # Upstream MCP data sources do not have catalogueable SQL tables.
    if registration.upstream_mcp_server_config_id:
        return 0

    source = build_data_source(
        DataSourceConfig(
            name=registration.name,
            type=registration.type,
            connection=registration.connection,
            sensitive_columns=registration.sensitive_columns,
            description=registration.description,
        )
    )
    docs_map = _docs_to_schema_map(
        name, [row.to_dict() for row in store.list_docs(name)]
    )

    total_tables = 0
    for table in source.list_tables():
        doc = source.table_doc(table)
        _apply_schema_docs(doc, docs_map)
        catalog.upsert_table_doc(doc)
        total_tables += 1
    return total_tables


def create_app(
    meta_db_path: str | Path = "data/meta.db",
    catalog_path: str | Path = "data/catalog.db",
) -> FastAPI:
    app = FastAPI(title="UBS Hackathon Data Source Backend")
    store = MetaStore(Path(meta_db_path))
    catalog = SchemaCatalog(Path(catalog_path))

    @app.get("/", include_in_schema=False, response_class=HTMLResponse)
    def frontend_home() -> str:
        return _frontend_home_html()

    @app.get("/sources", include_in_schema=False, response_class=HTMLResponse)
    def frontend_sources() -> str:
        return _frontend_sources_html()

    @app.get("/dashboard", include_in_schema=False, response_class=HTMLResponse)
    def frontend_dashboard() -> str:
        return _frontend_dashboard_html()

    @app.get("/mcp-servers", include_in_schema=False, response_class=HTMLResponse)
    def frontend_mcp_servers() -> str:
        return _frontend_mcp_servers_html()

    # Keep legacy /connectors URL as a redirect alias so existing bookmarks work.
    @app.get("/connectors", include_in_schema=False, response_class=HTMLResponse)
    def frontend_connectors_alias() -> str:
        return _frontend_mcp_servers_html()

    @app.get("/mcp-usage")
    def mcp_usage() -> dict:
        return _collect_mcp_usage_snapshot(store, Path(catalog_path))

    # ------------------------------------------------------------------
    # Upstream MCP server registry (read-only, hardcoded)
    # ------------------------------------------------------------------

    @app.get("/upstream-mcp-servers")
    def list_upstream_mcp_servers(data_type: str | None = None) -> list[dict]:
        """List available upstream MCP servers from the hardcoded registry."""
        return list_registry_entries(data_type=data_type)

    @app.get("/upstream-mcp-servers/{server_id}")
    def get_upstream_mcp_server(server_id: str) -> dict:
        """Get a single upstream MCP server entry from the registry."""
        entry = get_registry_entry(server_id)
        if entry is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Upstream MCP server '{server_id}' not found in registry",
            )
        return entry

    # ------------------------------------------------------------------
    # Upstream MCP server configs (user-configured instances)
    # ------------------------------------------------------------------

    @app.get("/upstream-mcp-server-configs")
    def list_upstream_configs() -> list[dict]:
        """List all user-configured upstream MCP server instances."""
        return [c.to_dict() for c in store.list_upstream_configs()]

    @app.post("/upstream-mcp-server-configs", status_code=status.HTTP_201_CREATED)
    def create_upstream_config(payload: UpstreamMCPServerConfigCreate) -> dict:
        """Create a new upstream MCP server configuration."""
        if get_registry_entry(payload.server_id) is None:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail=f"Server '{payload.server_id}' not found in upstream MCP registry",
            )
        config_id = _make_config_id(payload.name)
        created = store.create_upstream_config(
            config_id=config_id,
            server_id=payload.server_id,
            name=payload.name,
            endpoint=payload.endpoint,
            auth=payload.auth,
            exposed_tools=payload.exposed_tools,
        )
        return created.to_dict()

    @app.get("/upstream-mcp-server-configs/{config_id}")
    def get_upstream_config(config_id: str) -> dict:
        """Get a single upstream MCP server configuration."""
        found = store.get_upstream_config(config_id)
        if not found:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Upstream MCP server configuration not found",
            )
        return found.to_dict()

    @app.put("/upstream-mcp-server-configs/{config_id}")
    def update_upstream_config(
        config_id: str, payload: UpstreamMCPServerConfigUpdate
    ) -> dict:
        """Update an existing upstream MCP server configuration."""
        updates = payload.model_dump(exclude_unset=True)
        endpoint_value = updates["endpoint"] if "endpoint" in updates else _UNSET_SENTINEL
        updated = store.update_upstream_config(
            config_id,
            name=updates.get("name"),
            endpoint=endpoint_value,
            auth=updates.get("auth"),
            exposed_tools=updates.get("exposed_tools"),
        )
        if not updated:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Upstream MCP server configuration not found",
            )
        return updated.to_dict()

    @app.delete(
        "/upstream-mcp-server-configs/{config_id}",
        status_code=status.HTTP_204_NO_CONTENT,
    )
    def delete_upstream_config(config_id: str) -> None:
        """Delete an upstream MCP server configuration."""
        deleted = store.delete_upstream_config(config_id)
        if not deleted:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Upstream MCP server configuration not found",
            )

    # ------------------------------------------------------------------
    # Data sources CRUD
    # ------------------------------------------------------------------

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
        # Validate upstream config reference if provided.
        if payload.upstream_mcp_server_config_id:
            if not store.get_upstream_config(payload.upstream_mcp_server_config_id):
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                    detail=f"Upstream MCP server config '{payload.upstream_mcp_server_config_id}' not found",
                )
        created = store.create_data_source(
            payload.name,
            payload.type,
            payload.connection,
            sensitive_columns=payload.sensitive_columns,
            description=payload.description,
            upstream_mcp_server_config_id=payload.upstream_mcp_server_config_id,
        )
        return created.to_dict()

    @app.get("/data-sources/{name}")
    def get_data_source(name: str) -> dict:
        found = store.get_data_source(name)
        if not found:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Data source not found"
            )
        return found.to_dict()

    @app.put("/data-sources/{name}")
    def update_data_source(name: str, payload: DataSourceUpdate) -> dict:
        updates = payload.model_dump(exclude_unset=True)
        # Validate upstream config reference if explicitly provided.
        upstream_id = updates.get("upstream_mcp_server_config_id")
        if upstream_id is not None and upstream_id != "":
            if not store.get_upstream_config(upstream_id):
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                    detail=f"Upstream MCP server config '{upstream_id}' not found",
                )
        upstream_id_sentinel = (
            updates["upstream_mcp_server_config_id"]
            if "upstream_mcp_server_config_id" in updates
            else _UNSET_SENTINEL
        )
        desc_sentinel = (
            updates["description"] if "description" in updates else _UNSET_SENTINEL
        )
        updated = store.update_data_source(
            name,
            type_=updates.get("type"),
            connection=updates.get("connection"),
            sensitive_columns=updates.get("sensitive_columns"),
            description=desc_sentinel,
            upstream_mcp_server_config_id=upstream_id_sentinel,
        )
        if not updated:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Data source not found"
            )
        return updated.to_dict()

    @app.delete("/data-sources/{name}", status_code=status.HTTP_204_NO_CONTENT)
    def delete_data_source(name: str) -> None:
        deleted = store.delete_data_source(name)
        if not deleted:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Data source not found"
            )

    @app.get("/data-sources/{name}/docs")
    def list_docs(name: str) -> list[dict]:
        if not store.get_data_source(name):
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Data source not found"
            )
        return [row.to_dict() for row in store.list_docs(name)]

    @app.post("/data-sources/{name}/docs", status_code=status.HTTP_201_CREATED)
    def create_doc(name: str, payload: DocCreate) -> dict:
        if not store.get_data_source(name):
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Data source not found"
            )
        created = store.create_doc(
            name, payload.doc_type, payload.target, payload.content
        )
        _rebuild_catalog_for_data_source(store, catalog, name)
        return created.to_dict()

    @app.get("/data-sources/{name}/docs/{doc_id}")
    def get_doc(name: str, doc_id: int) -> dict:
        found = store.get_doc(name, doc_id)
        if not found:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Doc not found"
            )
        return found.to_dict()

    @app.put("/data-sources/{name}/docs/{doc_id}")
    def update_doc(name: str, doc_id: int, payload: DocUpdate) -> dict:
        if not store.get_data_source(name):
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Data source not found"
            )
        updates = payload.model_dump(exclude_unset=True)
        try:
            updated = store.update_doc(name, doc_id, **updates)
        except ValueError as exc:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(exc)
            ) from exc
        if not updated:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Doc not found"
            )
        _rebuild_catalog_for_data_source(store, catalog, name)
        return updated.to_dict()

    @app.delete(
        "/data-sources/{name}/docs/{doc_id}", status_code=status.HTTP_204_NO_CONTENT
    )
    def delete_doc(name: str, doc_id: int) -> None:
        deleted = store.delete_doc(name, doc_id)
        if not deleted:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Doc not found"
            )
        _rebuild_catalog_for_data_source(store, catalog, name)

    @app.post("/data-sources/{name}/sync")
    def sync_data_source(name: str) -> dict:
        total_tables = _rebuild_catalog_for_data_source(store, catalog, name)
        return {"data_source": name, "indexed_tables": total_tables}

    return app


def main() -> None:
    parser = argparse.ArgumentParser(description="Run UBS hackathon metadata backend")
    parser.add_argument(
        "--meta-db", default="data/meta.db", help="Path to metadata SQLite DB"
    )
    parser.add_argument(
        "--catalog", default="data/catalog.db", help="Path to schema catalog DB"
    )
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8080)
    args = parser.parse_args()

    app = create_app(meta_db_path=args.meta_db, catalog_path=args.catalog)
    uvicorn.run(app, host=args.host, port=args.port)


if __name__ == "__main__":
    main()
