from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any

from mcp.server.fastmcp import FastMCP

from .catalog import SchemaCatalog
from .config import load_config
from .datasource import build_data_source, UpstreamMCPDataSource
from .meta_store import MetaStore
from .models import DataSourceConfig


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


def _make_upstream_proxy(
    tool_name: str,
    routes_by_data_source: dict[str, UpstreamMCPDataSource],
    description: str | None = None,
):
    """Return a callable that proxies a tool to the correct upstream by data source."""

    def proxy_tool(data_source: str, arguments: dict[str, Any] | None = None) -> dict:
        """Proxy tool forwarding requests to an upstream MCP server."""
        source = routes_by_data_source.get(data_source)
        if source is None:
            raise ValueError(
                f"Tool '{tool_name}' is not available for data_source '{data_source}'. "
                f"Supported data sources: {sorted(routes_by_data_source.keys())}"
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
    sources, catalog_path, _ = load_config(config_path)
    source_map = {cfg.name: build_data_source(cfg) for cfg in sources}
    catalog = SchemaCatalog(Path(catalog_path))

    # Load upstream MCP data sources from metadata store and build
    # tool routing by data source name.
    upstream_sources: dict[str, UpstreamMCPDataSource] = {}
    upstream_tool_routes: dict[str, dict[str, UpstreamMCPDataSource]] = {}
    upstream_tool_descriptions: dict[str, str] = {}
    if meta_db_path is not None:
        store = MetaStore(Path(meta_db_path))
        upstream_tool_specs_by_config: dict[str, list[tuple[str, str | None]]] = {}
        for upstream_cfg in store.list_upstream_configs():
            if not upstream_cfg.exposed_tools:
                continue
            tool_specs = _extract_exposed_tool_specs(upstream_cfg.exposed_tools)
            if not tool_specs:
                continue
            endpoint = upstream_cfg.endpoint or ""
            ds_config = DataSourceConfig(
                name=f"upstream__{upstream_cfg.id}",
                type="graph",
                connection=f"upstream://{upstream_cfg.id}",
                upstream_mcp_server_config_id=upstream_cfg.id,
            )
            upstream_source = UpstreamMCPDataSource(
                ds_config,
                endpoint,
                [tool_name for tool_name, _ in tool_specs],
            )
            upstream_sources[upstream_cfg.id] = upstream_source
            upstream_tool_specs_by_config[upstream_cfg.id] = tool_specs

        for registration in store.list_data_sources():
            config_id = registration.upstream_mcp_server_config_id
            if not config_id:
                continue
            upstream_source = upstream_sources.get(config_id)
            if upstream_source is None:
                continue
            for tool_name, tool_description in upstream_tool_specs_by_config.get(
                config_id, []
            ):
                per_tool_routes = upstream_tool_routes.setdefault(tool_name, {})
                per_tool_routes[registration.name] = upstream_source
                if tool_description:
                    upstream_tool_descriptions.setdefault(tool_name, tool_description)

    mcp = FastMCP("ubs-hackathon-assistant", host=host, port=port)

    @mcp.tool()
    def list_data_sources() -> list[dict]:
        """Enumerate configured data sources and supported type."""
        return [
            {
                "name": cfg.name,
                "type": cfg.type,
                "adapter": cfg.adapter or cfg.type,
                "sensitive_columns": list(cfg.sensitive_columns or []),
                "capabilities": source_map[cfg.name].capabilities(),
            }
            for cfg in sources
        ]

    @mcp.tool()
    def search_schema(query: str, top_k: int = 5) -> list[dict]:
        """Semantic search over indexed schema docs."""
        return catalog.search(query=query, top_k=top_k)

    @mcp.tool()
    def describe_table(data_source: str, table: str) -> dict:
        """Return complete table metadata from the schema catalog."""
        return catalog.describe_table(data_source=data_source, table=table)

    @mcp.tool()
    def execute_query(
        data_source: str,
        sql: str,
        limit: int = 200,
        session_id: str | None = None,
    ) -> dict:
        """Execute a read-only query against a configured source."""
        source = source_map.get(data_source)
        if source is None:
            raise ValueError(f"Unknown data source: {data_source}")
        return source.execute_read_only(sql=sql, limit=limit, session_id=session_id)

    @mcp.tool()
    def list_temporary_views(
        data_source: str, session_id: str | None = None
    ) -> list[dict]:
        """List temporary views created in the current server session."""
        source = source_map.get(data_source)
        if source is None:
            raise ValueError(f"Unknown data source: {data_source}")
        return source.list_temporary_views(session_id=session_id)

    @mcp.tool()
    def create_temporary_view(
        data_source: str,
        sql: str,
        view_name: str | None = None,
        ttl_seconds: int = 3600,
        session_id: str | None = None,
    ) -> dict:
        """Create a session-local temporary view for iterative analysis."""
        source = source_map.get(data_source)
        if source is None:
            raise ValueError(f"Unknown data source: {data_source}")
        return source.create_temporary_view(
            sql=sql, view_name=view_name, ttl_seconds=ttl_seconds, session_id=session_id
        )

    @mcp.tool()
    def drop_temporary_view(
        data_source: str, view_name: str, session_id: str | None = None
    ) -> dict:
        """Drop a temporary view created by this server session."""
        source = source_map.get(data_source)
        if source is None:
            raise ValueError(f"Unknown data source: {data_source}")
        return source.drop_temporary_view(view_name=view_name, session_id=session_id)

    @mcp.tool()
    def list_upstream_mcp_sources() -> list[dict]:
        """List upstream MCP server configurations with routed data sources and exposed tools."""
        tool_names_for_config: dict[str, list[str]] = {
            cfg_id: src.get_exposed_tools() for cfg_id, src in upstream_sources.items()
        }
        data_sources_by_config: dict[str, set[str]] = {
            cfg_id: set() for cfg_id in upstream_sources
        }
        for tool_name, routes in upstream_tool_routes.items():
            for data_source_name, src in routes.items():
                config_id = src.config.upstream_mcp_server_config_id
                if not config_id:
                    continue
                bucket = data_sources_by_config.setdefault(config_id, set())
                bucket.add(data_source_name)
        return [
            {
                "config_id": cfg_id,
                "exposed_tools": tool_names_for_config.get(cfg_id, []),
                "routed_data_sources": sorted(data_sources_by_config.get(cfg_id, set())),
                "capabilities": src.capabilities(),
            }
            for cfg_id, src in upstream_sources.items()
        ]

    # Register one proxy tool per upstream tool name.
    # If multiple upstream servers expose the same tool name, route by data_source.
    for _tool_name, _routes in upstream_tool_routes.items():
        _proxy = _make_upstream_proxy(
            _tool_name,
            _routes,
            description=upstream_tool_descriptions.get(_tool_name),
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
