from __future__ import annotations

import argparse
import re
import os
import signal
import sqlite3
import uuid
import time
import random
from datetime import datetime, timedelta, timezone
from pathlib import Path

import uvicorn
from fastapi import FastAPI, HTTPException, status, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field

from .builder import _apply_schema_docs
from .catalog import SchemaCatalog
from .datasource import build_data_source
from .meta_store import MetaStore, _UNSET
from .models import DataSourceConfig
from .registry import UPSTREAM_MCP_REGISTRY, get_registry_entry, list_registry_entries
from .source_runtime import RuntimeResolutionError, build_runtime_source_config

_UNSET_SENTINEL = _UNSET


def _trigger_mcp_restart():
    """Signal the MCP server to restart by sending SIGHUP to the recorded PID."""
    pid_file = Path("data/mcp.pid")
    if not pid_file.exists():
        return
    try:
        pid = int(pid_file.read_text().strip())
        os.kill(pid, signal.SIGHUP)
    except (ValueError, ProcessLookupError, PermissionError):
        pass


def _seed_audit_logs(store: MetaStore):
    """Seed the audit log with mock historical data if empty."""
    logs = store.list_audit_logs(limit=1)
    if logs:
        return

    now = datetime.now(timezone.utc)
    actions = ["search_schema", "describe_table", "execute_query", "list_data_sources", "sync_data_source"]
    actors = ["User-123", "User-456", "System", "Admin"]

    # Generate 100 logs over the last 7 days
    for i in range(100):
        offset_seconds = random.randint(0, 7 * 24 * 3600)
        timestamp = (now - timedelta(seconds=offset_seconds)).isoformat()
        action = random.choice(actions)
        actor = random.choice(actors)
        status_val = "Success" if random.random() > 0.05 else "Error"
        latency = random.randint(20, 500)
        details = f"Mocked {action} for demonstration"

        store.log_action(
            action=action,
            details=details,
            actor=actor,
            status=status_val,
            latency_ms=latency,
            timestamp=timestamp
        )


def _collect_mcp_usage_snapshot(store: MetaStore, catalog_path: Path) -> dict:
    sources = store.list_data_sources()
    source_count = len(sources)
    docs_count = sum(len(store.list_docs(source.name)) for source in sources)

    with sqlite3.connect(catalog_path) as conn:
        row = conn.execute("SELECT COUNT(*) FROM table_docs").fetchone()
    catalog_tables = int(row[0]) if row else 0

    # Get real metrics from audit log
    metrics = store.get_usage_metrics()

    # Merge with static/calculated info
    snapshot = {
        "registered_sources": source_count,
        "stored_docs": docs_count,
        "catalog_tables": catalog_tables,
        "requests_last_24h": metrics["requests_last_24h"],
        "avg_latency_ms": metrics["avg_latency_ms"],
        "success_rate_pct": metrics["success_rate_pct"],
        "requests_trend_7d": metrics["requests_trend_7d"],
        "simulated_connectors": ["notion", "google_workspace"],
    }

    return snapshot


class DataSourceCreate(BaseModel):
    name: str
    databases: list[str] = Field(default_factory=list)
    sensitive_columns: list[str] = Field(default_factory=list)
    description: str | None = None
    upstream_mcp_server_config_id: str

    model_config = ConfigDict(extra="forbid")


class DataSourceUpdate(BaseModel):
    databases: list[str] | None = None
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

    config_id = registration.upstream_mcp_server_config_id
    if not config_id:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=f"Data source '{name}' must reference an upstream connector",
        )
    u_cfg = store.get_upstream_config(config_id)
    if not u_cfg:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=f"Connector '{config_id}' not found",
        )
    if u_cfg.server_id != "sql-like":
        return 0
    try:
        runtime_cfg = build_runtime_source_config(registration, u_cfg)
    except RuntimeResolutionError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=str(exc),
        ) from exc

    source = build_data_source(
        DataSourceConfig(
            name=runtime_cfg.name,
            type=runtime_cfg.type,
            connection=runtime_cfg.connection,
            sensitive_columns=runtime_cfg.sensitive_columns,
            description=runtime_cfg.description,
            databases=runtime_cfg.databases,
            upstream_mcp_server_config_id=runtime_cfg.upstream_mcp_server_config_id,
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

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    store = MetaStore(Path(meta_db_path))
    catalog = SchemaCatalog(Path(catalog_path))

    # Seed mock data
    _seed_audit_logs(store)

    @app.middleware("http")
    async def audit_middleware(request: Request, call_next):
        start_time = time.perf_counter()

        path = request.url.path
        if path.startswith("/api"):
            path = path[4:] or "/"

        # Skip auditing for the usage dashboard endpoints themselves to avoid loops/noise
        skip_audit = path in ["/mcp-usage", "/recent-activity"]

        response = None
        try:
            response = await call_next(request)
            return response
        finally:
            if not skip_audit:
                duration_ms = int((time.perf_counter() - start_time) * 1000)
                status_str = "Success" if response and response.status_code < 400 else "Error"

                # Log the action
                action = f"{request.method} {path}"
                # Simplify action name for common ones
                if path == "/data-sources" and request.method == "GET":
                    action = "list_data_sources"
                elif path.startswith("/data-sources/") and request.method == "GET":
                    action = "get_data_source"
                elif path.endswith("/sync") and request.method == "POST":
                    action = "sync_data_source"

                store.log_action(
                    action=action,
                    actor="System", # Could be extracted from auth if present
                    status=status_str,
                    latency_ms=duration_ms,
                    details=f"API Request: {request.method} {request.url.path}"
                )



    from fastapi import APIRouter

    api_router = APIRouter()

    @api_router.get("/mcp-usage")
    def mcp_usage() -> dict:
        return _collect_mcp_usage_snapshot(store, Path(catalog_path))

    @api_router.get("/recent-activity")
    def recent_activity(limit: int = 10) -> list[dict]:
        return [log.to_dict() for log in store.list_audit_logs(limit=limit)]

    # ------------------------------------------------------------------
    # Upstream MCP server registry (read-only, hardcoded)
    # ------------------------------------------------------------------

    @api_router.get("/upstream-mcp-servers")
    def list_upstream_mcp_servers(data_type: str | None = None) -> list[dict]:
        """List available upstream MCP servers from the hardcoded registry."""
        return list_registry_entries(data_type=data_type)

    @api_router.get("/upstream-mcp-servers/{server_id}")
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

    @api_router.get("/upstream-mcp-server-configs")
    def list_upstream_configs() -> list[dict]:
        """List all user-configured upstream MCP server instances."""
        return [c.to_dict() for c in store.list_upstream_configs()]

    @api_router.post("/upstream-mcp-server-configs", status_code=status.HTTP_201_CREATED)
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
        _trigger_mcp_restart()
        return created.to_dict()

    @api_router.get("/upstream-mcp-server-configs/{config_id}")
    def get_upstream_config(config_id: str) -> dict:
        """Get a single upstream MCP server configuration."""
        found = store.get_upstream_config(config_id)
        if not found:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Upstream MCP server configuration not found",
            )
        return found.to_dict()

    @api_router.put("/upstream-mcp-server-configs/{config_id}")
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
        _trigger_mcp_restart()
        return updated.to_dict()

    @api_router.delete(
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
        _trigger_mcp_restart()

    # ------------------------------------------------------------------
    # Data sources CRUD
    # ------------------------------------------------------------------

    @api_router.get("/data-sources")
    def list_data_sources() -> list[dict]:
        return [row.to_dict() for row in store.list_data_sources()]

    @api_router.post("/data-sources", status_code=status.HTTP_201_CREATED)
    def create_data_source(payload: DataSourceCreate) -> dict:
        if store.get_data_source(payload.name):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Data source '{payload.name}' already exists",
            )
        if not store.get_upstream_config(payload.upstream_mcp_server_config_id):
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail=f"Upstream MCP server config '{payload.upstream_mcp_server_config_id}' not found",
            )

        created = store.create_data_source(
            payload.name,
            databases=payload.databases,
            sensitive_columns=payload.sensitive_columns,
            description=payload.description,
            upstream_mcp_server_config_id=payload.upstream_mcp_server_config_id,
        )
        return created.to_dict()

    @api_router.get("/data-sources/{name}")
    def get_data_source(name: str) -> dict:
        found = store.get_data_source(name)
        if not found:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Data source not found"
            )
        return found.to_dict()

    @api_router.put("/data-sources/{name}")
    def update_data_source(name: str, payload: DataSourceUpdate) -> dict:
        found = store.get_data_source(name)
        if not found:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Data source not found"
            )

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
        if upstream_id is None and "upstream_mcp_server_config_id" in updates:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail="upstream_mcp_server_config_id cannot be null",
            )

        desc_sentinel = (
            updates["description"] if "description" in updates else _UNSET_SENTINEL
        )
        updated = store.update_data_source(
            name,
            databases=updates.get("databases"),
            sensitive_columns=updates.get("sensitive_columns"),
            description=desc_sentinel,
            upstream_mcp_server_config_id=upstream_id_sentinel,
        )
        if not updated:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Data source not found"
            )
        return updated.to_dict()

    @api_router.delete("/data-sources/{name}", status_code=status.HTTP_204_NO_CONTENT)
    def delete_data_source(name: str) -> None:
        deleted = store.delete_data_source(name)
        if not deleted:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Data source not found"
            )

    @api_router.get("/data-sources/{name}/docs")
    def list_docs(name: str) -> list[dict]:
        if not store.get_data_source(name):
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Data source not found"
            )
        return [row.to_dict() for row in store.list_docs(name)]

    @api_router.post("/data-sources/{name}/docs", status_code=status.HTTP_201_CREATED)
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

    @api_router.get("/data-sources/{name}/docs/{doc_id}")
    def get_doc(name: str, doc_id: int) -> dict:
        found = store.get_doc(name, doc_id)
        if not found:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Doc not found"
            )
        return found.to_dict()

    @api_router.put("/data-sources/{name}/docs/{doc_id}")
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

    @api_router.delete(
        "/data-sources/{name}/docs/{doc_id}", status_code=status.HTTP_204_NO_CONTENT
    )
    def delete_doc(name: str, doc_id: int) -> None:
        deleted = store.delete_doc(name, doc_id)
        if not deleted:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Doc not found"
            )
        _rebuild_catalog_for_data_source(store, catalog, name)

    @api_router.post("/data-sources/{name}/sync")
    def sync_data_source(name: str) -> dict:
        total_tables = _rebuild_catalog_for_data_source(store, catalog, name)
        return {"data_source": name, "indexed_tables": total_tables}

    # Include the router twice: once with /api prefix and once without.
    # This ensures both /api/recent-activity and /recent-activity work correctly.
    app.include_router(api_router, prefix="/api")
    app.include_router(api_router)

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
    parser.add_argument("--reload", action="store_true", help="Enable uvicorn reload")
    args = parser.parse_args()

    app = "ubs_hackathon.backend:create_app" if args.reload else create_app(meta_db_path=args.meta_db, catalog_path=args.catalog)

    if args.reload:
        uvicorn.run(app, host=args.host, port=args.port, reload=True, factory=True)
    else:
        uvicorn.run(app, host=args.host, port=args.port)


if __name__ == "__main__":
    main()
