from __future__ import annotations

import argparse
from pathlib import Path

from mcp.server.fastmcp import FastMCP

from .builder import build_catalog
from .catalog import SchemaCatalog
from .config import load_config
from .datasource import build_data_source


def create_server(config_path: str | None = None) -> FastMCP:
    sources, catalog_path, _ = load_config(config_path)
    source_map = {cfg.name: build_data_source(cfg) for cfg in sources}
    catalog = SchemaCatalog(Path(catalog_path))

    mcp = FastMCP("ubs-hackathon-assistant")

    @mcp.tool()
    def list_data_sources() -> list[dict]:
        """Enumerate configured data sources and supported type."""
        return [{"name": cfg.name, "type": cfg.type} for cfg in sources]

    @mcp.tool()
    def search_schema(query: str, top_k: int = 5) -> list[dict]:
        """Semantic search over indexed schema docs."""
        return catalog.search(query=query, top_k=top_k)

    @mcp.tool()
    def describe_table(data_source: str, table: str) -> dict:
        """Return complete table metadata from the schema catalog."""
        return catalog.describe_table(data_source=data_source, table=table)

    @mcp.tool()
    def execute_query(data_source: str, sql: str, limit: int = 200) -> dict:
        """Execute a read-only query against a configured source."""
        source = source_map.get(data_source)
        if source is None:
            raise ValueError(f"Unknown data source: {data_source}")
        return source.execute_read_only(sql=sql, limit=limit)

    @mcp.tool()
    def rebuild_catalog() -> dict:
        """Re-index schema docs from source systems."""
        count = build_catalog(config_path)
        return {"indexed_tables": count}

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
    args = parser.parse_args()

    mcp = create_server(args.config)
    if args.transport == "stdio":
        mcp.run(transport="stdio")
    else:
        mcp.run(transport="sse", host=args.host, port=args.port)


if __name__ == "__main__":
    main()
