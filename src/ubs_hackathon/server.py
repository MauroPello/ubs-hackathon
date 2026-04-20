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


def _make_upstream_proxy(
    source: UpstreamMCPDataSource, tool_name: str
):
    """Return a callable that proxies calls to the upstream MCP server tool."""

    def proxy_tool(arguments: dict[str, Any] | None = None) -> dict:
        """Proxy tool forwarding requests to an upstream MCP server."""
        return source.call_upstream_tool(tool_name, arguments or {})

    proxy_tool.__name__ = f"{source.config.name}__{tool_name}"
    proxy_tool.__doc__ = (
        f"Proxy tool for data source '{source.config.name}', "
        f"forwarding to upstream tool '{tool_name}'."
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

    # Load upstream MCP data sources from the metadata store so that
    # proxy tools are registered for each configured+exposed tool.
    upstream_sources: dict[str, UpstreamMCPDataSource] = {}
    if meta_db_path is not None:
        store = MetaStore(Path(meta_db_path))
        for upstream_cfg in store.list_upstream_configs():
            if not upstream_cfg.exposed_tools:
                continue
            endpoint = upstream_cfg.endpoint or ""
            ds_config = DataSourceConfig(
                name=f"upstream__{upstream_cfg.id}",
                type="graph",
                connection=f"upstream://{upstream_cfg.id}",
                upstream_mcp_server_config_id=upstream_cfg.id,
            )
            upstream_source = UpstreamMCPDataSource(
                ds_config, endpoint, upstream_cfg.exposed_tools
            )
            upstream_sources[upstream_cfg.id] = upstream_source

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
    def list_graph_entities(data_source: str) -> list[str]:
        """List graph entities (nodes/relationships) for graph-capable sources."""
        source = source_map.get(data_source)
        if source is None:
            raise ValueError(f"Unknown data source: {data_source}")
        return source.list_graph_entities()

    @mcp.tool()
    def describe_graph_entity(data_source: str, entity: str) -> dict:
        """Describe graph entity metadata in normalized catalog shape."""
        source = source_map.get(data_source)
        if source is None:
            raise ValueError(f"Unknown data source: {data_source}")
        return source.describe_graph_entity(entity).to_dict()

    @mcp.tool()
    def execute_graph_query(
        data_source: str,
        query: str,
        limit: int = 200,
        session_id: str | None = None,
    ) -> dict:
        """Execute a read-only graph query for graph-capable sources."""
        source = source_map.get(data_source)
        if source is None:
            raise ValueError(f"Unknown data source: {data_source}")
        return source.execute_graph_read_only(
            query=query, limit=limit, session_id=session_id
        )

    @mcp.tool()
    def list_upstream_mcp_sources() -> list[dict]:
        """List upstream MCP server data sources with their exposed tools."""
        return [
            {
                "config_id": cfg_id,
                "exposed_tools": src.get_exposed_tools(),
                "capabilities": src.capabilities(),
            }
            for cfg_id, src in upstream_sources.items()
        ]

    @mcp.tool()
    def call_upstream_tool(
        config_id: str,
        tool_name: str,
        arguments: dict[str, Any] | None = None,
    ) -> dict:
        """Call an exposed tool on a configured upstream MCP server.

        Use list_upstream_mcp_sources to discover available config IDs and tools.
        """
        source = upstream_sources.get(config_id)
        if source is None:
            raise ValueError(
                f"Unknown upstream MCP config: {config_id}. "
                f"Available: {list(upstream_sources.keys())}"
            )
        return source.call_upstream_tool(tool_name, arguments or {})

    # Register individual named proxy tools for each exposed upstream tool
    # so that MCP clients can discover them by name.
    for _cfg_id, _upstream_src in upstream_sources.items():
        for _tool_name in _upstream_src.get_exposed_tools():
            _proxy = _make_upstream_proxy(_upstream_src, _tool_name)
            _full_name = f"{_cfg_id}__{_tool_name}"
            mcp.tool(name=_full_name)(_proxy)

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
