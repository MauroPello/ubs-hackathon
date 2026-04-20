from __future__ import annotations

import argparse
import os
import signal
import sys
import time
from pathlib import Path
from typing import Any

from mcp.server.fastmcp import FastMCP

from .catalog import SchemaCatalog
from .config import load_config, get_registry_entry
from .datasource import DataSource, build_data_source, UpstreamMCPDataSource
from .meta_store import MetaStore
from .models import DataSourceConfig
from .source_runtime import RuntimeResolutionError, build_runtime_source_config


def _extract_exposed_tool_specs(
    exposed_tools: list[Any] | None,
) -> list[tuple[str, str | None]]:
    """Normalize exposed tools to (name, description) tuples."""
    specs: list[tuple[str, str | None]] = []
    for item in exposed_tools or []:
        if isinstance(item, dict):
            name = str(item.get("name") or "").strip()
            if not name:
                continue
            raw_description = item.get("description")
            description_text = str(raw_description or "").strip()
            description = description_text or None
            specs.append((name, description))
            continue
        name = str(item or "").strip()
        if not name:
            continue
        specs.append((name, None))
    return specs


def _restart_handler(signum, frame):
    """Signal handler to trigger a self-restart of the process."""
    print("🔄 Upstream configuration changed. Restarting MCP server...")
    # Give a tiny bit of time for logs to flush and the OS to breathe
    time.sleep(0.2)
    os.execv(sys.executable, [sys.executable, "-m", "ubs_hackathon.server"] + sys.argv[1:])


signal.signal(signal.SIGHUP, _restart_handler)


class SourceRegistry:
    """Manages data source configurations and connection instances with caching."""

    def __init__(
        self,
        meta_db_path: str | Path | None,
        catalog_path: Path,
        yaml_sources: list[DataSourceConfig],
        registry: list[dict],
    ) -> None:
        self.meta_db_path = meta_db_path
        self.catalog_path = catalog_path
        self.yaml_sources = yaml_sources
        self.registry = registry
        self._ds_cache: dict[str, DataSource] = {}
        self._configs: dict[str, DataSourceConfig] = {}
        self._connector_configs: dict[str, Any] = {}
        self._upstream_sources: dict[str, UpstreamMCPDataSource] = {}
        self._upstream_tool_specs: dict[str, list[tuple[str, str | None]]] = {}
        self._last_refresh = 0.0
        self._ttl = 24 * 3600.0

    def _refresh_if_needed(self) -> None:
        now = time.time()
        if not self._configs or (now - self._last_refresh) > self._ttl:
            self.refresh()

    def refresh(self) -> None:
        if self.meta_db_path:
            store = MetaStore(Path(self.meta_db_path))

            # Load upstreams for proxy tools
            self._upstream_sources = {}
            self._upstream_tool_specs = {}
            self._connector_configs = {}
            for upstream_cfg in store.list_upstream_configs():
                self._connector_configs[upstream_cfg.id] = upstream_cfg
                if not upstream_cfg.exposed_tools:
                    continue
                tool_specs = _extract_exposed_tool_specs(upstream_cfg.exposed_tools)
                if not tool_specs:
                    continue

                self._upstream_tool_specs[upstream_cfg.id] = tool_specs

                entry = get_registry_entry(store.list_registry_entries() if hasattr(store, 'list_registry_entries') else self.registry, upstream_cfg.server_id)
                data_type = str((entry or {}).get("data_type") or upstream_cfg.server_id).strip().lower()
                if data_type == "sql":
                    # Internal SQL-like connector doesn't need an UpstreamMCPDataSource proxy
                    continue

                endpoint = upstream_cfg.endpoint or ""
                upstream_source = UpstreamMCPDataSource(
                    DataSourceConfig(
                        name=f"upstream__{upstream_cfg.id}",
                        type="graph",
                        connection=f"upstream://{upstream_cfg.id}",
                        upstream_mcp_server_config_id=upstream_cfg.id,
                    ),
                    endpoint,
                    [name for name, _ in tool_specs],
                )
                self._upstream_sources[upstream_cfg.id] = upstream_source

            # Load sources
            new_configs = {}
            for reg in store.list_data_sources():
                config_id = reg.upstream_mcp_server_config_id
                if not config_id:
                    continue
                connector = store.get_upstream_config(config_id)
                if not connector:
                    continue
                try:
                    cfg = build_runtime_source_config(reg, connector, self.registry)
                except RuntimeResolutionError:
                    continue
                new_configs[reg.name] = cfg
            self._configs = new_configs
        else:
            self._configs = {c.name: c for c in self.yaml_sources}

        self._last_refresh = time.time()

    def get_all_configs(self) -> list[DataSourceConfig]:
        self._refresh_if_needed()
        return list(self._configs.values())

    def get_source(self, name: str) -> DataSource | None:
        if name in self._ds_cache:
            return self._ds_cache[name]

        self._refresh_if_needed()
        cfg = self._configs.get(name)

        # Cache miss - look in DB if possible
        if not cfg and self.meta_db_path:
            store = MetaStore(Path(self.meta_db_path))
            reg = store.get_data_source(name)
            if reg:
                config_id = reg.upstream_mcp_server_config_id
                if config_id:
                    connector = store.get_upstream_config(config_id)
                    if connector:
                        try:
                            cfg = build_runtime_source_config(reg, connector, self.registry)
                        except RuntimeResolutionError:
                            cfg = None
                        if cfg:
                            self._configs[name] = cfg

        if cfg:
            config_id = cfg.upstream_mcp_server_config_id
            if config_id and config_id in self._upstream_sources:
                ds: DataSource = self._upstream_sources[config_id]
            else:
                ds = build_data_source(cfg)
            self._ds_cache[name] = ds
            return ds
        return None

    def get_allowed_tools(self, source_name: str) -> list[str]:
        """Return the list of allowed tool names for a given data source."""
        self._refresh_if_needed()
        cfg = self._configs.get(source_name)
        if not cfg:
            return []

        config_id = cfg.upstream_mcp_server_config_id
        if not config_id:
            return []

        # If it's a connector with explicit tool specs, return the whitelist
        if config_id in self._upstream_tool_specs:
            return [name for name, _ in self._upstream_tool_specs[config_id]]

        return []

    def is_tool_allowed(self, source_name: str, tool_name: str) -> bool:
        """Check if a tool is allowed for a given data source based on its connector config."""
        return tool_name in self.get_allowed_tools(source_name)

    def get_upstream_tool_descriptions(self) -> dict[str, str]:
        self._refresh_if_needed()
        descriptions: dict[str, str] = {}
        for config_id, specs in self._upstream_tool_specs.items():
            for tool_name, desc in specs:
                if desc:
                    descriptions.setdefault(tool_name, desc)
        return descriptions

    def get_upstream_tool_names(self) -> set[str]:
        self._refresh_if_needed()
        names: set[str] = set()
        for specs in self._upstream_tool_specs.values():
            for name, _ in specs:
                names.add(name)
        return names


def _make_upstream_proxy(
    tool_name: str,
    registry: SourceRegistry,
    description: str | None = None,
):
    """Return a callable that proxies a tool to the correct upstream by data source."""

    def proxy_tool(data_source: str, arguments: dict[str, Any] | None = None) -> dict:
        """Proxy tool forwarding requests to an upstream MCP server."""
        source = registry.get_source(data_source)
        if not isinstance(source, UpstreamMCPDataSource):
            raise ValueError(
                f"Tool '{tool_name}' is not available for data_source '{data_source}'. "
                f"Source is not an upstream MCP server."
            )
        return source.call_upstream_tool(tool_name, arguments or {})

    proxy_tool.__name__ = tool_name
    proxy_tool.__doc__ = (
        description
        or (
            f"Proxy tool for upstream MCP tool '{tool_name}'. "
            f"Select the target with data_source."
        )
    )
    return proxy_tool


def create_server(
    config_path: str | None = None,
    host: str = "127.0.0.1",
    port: int = 8000,
    meta_db_path: str | Path | None = None,
) -> FastMCP:
    yaml_sources, catalog_path, meta_db_path_from_config, _, _, connectors_registry = load_config(config_path)
    registry = SourceRegistry(
        meta_db_path=meta_db_path or meta_db_path_from_config,
        catalog_path=Path(catalog_path),
        yaml_sources=yaml_sources,
        registry=connectors_registry,
    )
    catalog = SchemaCatalog(Path(catalog_path))

    mcp = FastMCP("ubs-hackathon-assistant", host=host, port=port)

    @mcp.tool()
    def list_data_sources() -> list[dict]:
        """Enumerate configured data sources and supported type."""
        configs = registry.get_all_configs()
        results = []
        for cfg in configs:
            results.append(
                {
                    "name": cfg.name,
                    "type": cfg.type,
                    "adapter": cfg.adapter or cfg.type,
                    "sensitive_columns": list(cfg.sensitive_columns or []),
                    "capabilities": registry.get_allowed_tools(cfg.name),
                }
            )
        return results

    def search_schema(query: str, top_k: int = 5, data_source: str | None = None) -> list[dict]:
        """Semantic search over indexed schema docs. Optionally filter by data_source."""
        if data_source:
            if not registry.is_tool_allowed(data_source, "search_schema"):
                raise ValueError(f"Tool 'search_schema' is disabled for source '{data_source}'")
        return catalog.search(query=query, top_k=top_k, data_source=data_source)

    def describe_table(data_source: str, table: str) -> dict:
        """Return complete table metadata from the schema catalog."""
        if not registry.is_tool_allowed(data_source, "describe_table"):
            raise ValueError(f"Tool 'describe_table' is disabled for source '{data_source}'")
        return catalog.describe_table(data_source=data_source, table=table)

    def execute_query(
        data_source: str,
        sql: str,
        limit: int = 200,
        session_id: str | None = None,
    ) -> dict:
        """Execute a read-only query against a configured source."""
        if not registry.is_tool_allowed(data_source, "execute_query"):
            raise ValueError(f"Tool 'execute_query' is disabled for source '{data_source}'")
        source = registry.get_source(data_source)
        if source is None:
            raise ValueError(f"Unknown data source: {data_source}")
        return source.execute_read_only(sql=sql, limit=limit, session_id=session_id)

    def list_temporary_views(
        data_source: str, session_id: str | None = None
    ) -> list[dict]:
        """List temporary views created in the current server session."""
        if not registry.is_tool_allowed(data_source, "list_temporary_views"):
            raise ValueError(f"Tool 'list_temporary_views' is disabled for source '{data_source}'")
        source = registry.get_source(data_source)
        if source is None:
            raise ValueError(f"Unknown data source: {data_source}")
        return source.list_temporary_views(session_id=session_id)

    def create_temporary_view(
        data_source: str,
        sql: str,
        view_name: str | None = None,
        ttl_seconds: int = 3600,
        session_id: str | None = None,
    ) -> dict:
        """Create a session-local temporary view for iterative analysis."""
        if not registry.is_tool_allowed(data_source, "create_temporary_view"):
            raise ValueError(f"Tool 'create_temporary_view' is disabled for source '{data_source}'")
        source = registry.get_source(data_source)
        if source is None:
            raise ValueError(f"Unknown data source: {data_source}")
        return source.create_temporary_view(
            sql=sql, view_name=view_name, ttl_seconds=ttl_seconds, session_id=session_id
        )

    def drop_temporary_view(
        data_source: str, view_name: str, session_id: str | None = None
    ) -> dict:
        """Drop a temporary view created by this server session."""
        if not registry.is_tool_allowed(data_source, "drop_temporary_view"):
            raise ValueError(f"Tool 'drop_temporary_view' is disabled for source '{data_source}'")
        source = registry.get_source(data_source)
        if source is None:
            raise ValueError(f"Unknown data source: {data_source}")
        return source.drop_temporary_view(view_name=view_name, session_id=session_id)

    @mcp.tool()
    def list_upstream_mcp_sources() -> list[dict]:
        """List upstream MCP server configurations with routed data sources and exposed tools."""
        registry.refresh()  # Ensure we have latest for this specific introspection tool
        specs_by_config = registry._upstream_tool_specs
        upstreams = registry._upstream_sources
        configs = registry.get_all_configs()

        data_sources_by_config: dict[str, set[str]] = {}
        for cfg in configs:
            if cfg.upstream_mcp_server_config_id:
                bucket = data_sources_by_config.setdefault(
                    cfg.upstream_mcp_server_config_id, set()
                )
                bucket.add(cfg.name)

        return [
            {
                "config_id": cfg_id,
                "exposed_tools": [name for name, _ in specs_by_config.get(cfg_id, [])],
                "routed_data_sources": sorted(data_sources_by_config.get(cfg_id, set())),
                "capabilities": [name for name, _ in specs_by_config.get(cfg_id, [])],
            }
            for cfg_id, src in upstreams.items()
        ]

    internal_sql_tools = {
        "search_schema": search_schema,
        "describe_table": describe_table,
        "execute_query": execute_query,
        "list_temporary_views": list_temporary_views,
        "create_temporary_view": create_temporary_view,
        "drop_temporary_view": drop_temporary_view,
    }

    # Register one proxy tool per upstream tool name.
    # If multiple upstream servers expose the same tool name, route by data_source.
    for _tool_name in registry.get_upstream_tool_names():
        if _tool_name in internal_sql_tools:
            mcp.tool(name=_tool_name)(internal_sql_tools[_tool_name])
            continue

        _proxy = _make_upstream_proxy(
            _tool_name,
            registry,
            description=registry.get_upstream_tool_descriptions().get(_tool_name),
        )
        mcp.tool(name=_tool_name)(_proxy)

    return mcp


def main() -> None:
    parser = argparse.ArgumentParser(description="Run UBS hackathon MCP server")
    parser.add_argument("--config", default=None, help="Path to config YAML")
    parser.add_argument(
        "--transport",
        choices=["stdio", "sse"],
        default="sse",
        help="MCP transport",
    )
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument(
        "--meta-db",
        default=None,
        help="Path to metadata DB (enables dynamic upstream MCP proxy tools)",
    )
    args = parser.parse_args()

    # Write PID to file so backend can trigger restarts on config changes
    pid_file = Path("data/mcp.pid")
    pid_file.parent.mkdir(parents=True, exist_ok=True)
    pid_file.write_text(str(os.getpid()))

    mcp = create_server(
        args.config,
        host=args.host,
        port=args.port,
        meta_db_path=args.meta_db,
    )
    if args.transport == "stdio":
        mcp.run(transport="stdio")
    else:
        mcp.run(transport="sse")


if __name__ == "__main__":
    main()
