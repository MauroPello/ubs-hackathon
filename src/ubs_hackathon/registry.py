"""Hardcoded registry of available upstream MCP servers.

Each entry describes a supported upstream MCP server: its data type,
available tools, authentication requirements and current availability.
Only one working implementation is available at this stage (Neo4j).
Notion is shown in the registry but is marked as unavailable.
"""

from __future__ import annotations

from typing import Any

UPSTREAM_MCP_REGISTRY: list[dict[str, Any]] = [
    {
        "id": "neo4j",
        "name": "Neo4j",
        "data_type": "graph",
        "description": (
            "Neo4j graph database MCP server for executing Cypher queries "
            "and exploring graph schema."
        ),
        "tools": [
            {
                "name": "execute_cypher",
                "description": "Execute a read-only Cypher query against the Neo4j database.",
            },
            {
                "name": "list_labels",
                "description": "List all node labels present in the graph database.",
            },
            {
                "name": "describe_node_type",
                "description": "Describe the properties and relationships of a node label.",
            },
        ],
        "requires_auth": True,
        "auth_schema": {
            "url": {
                "type": "string",
                "description": "Bolt URL, e.g. bolt://localhost:7687",
                "secret": False,
            },
            "username": {
                "type": "string",
                "description": "Neo4j database username",
                "secret": False,
            },
            "password": {
                "type": "string",
                "description": "Neo4j database password",
                "secret": True,
            },
        },
        "is_local": True,
        "status": "available",
    },
    {
        "id": "notion",
        "name": "Notion",
        "data_type": "documents",
        "description": (
            "Notion workspace MCP server for reading pages, databases, "
            "and block content."
        ),
        "tools": [
            {
                "name": "search_pages",
                "description": "Search pages and content in the Notion workspace.",
            },
            {
                "name": "get_page_content",
                "description": "Retrieve the full content of a specific Notion page.",
            },
            {
                "name": "list_databases",
                "description": "List all Notion databases accessible to the integration.",
            },
        ],
        "requires_auth": True,
        "auth_schema": {
            "api_key": {
                "type": "string",
                "description": "Notion integration token (starts with secret_...)",
                "secret": True,
            },
        },
        "is_local": False,
        "status": "unavailable",
    },
    {
        "id": "sql-like",
        "name": "SQL-like",
        "data_type": "sql",
        "description": (
            "Internal SQL connector for relational databases (SQLite, PostgreSQL, etc.). "
            "Allows enabling/disabling SQL analysis tools."
        ),
        "tools": [
            {
                "name": "search_schema",
                "description": "Semantic search over indexed schema docs.",
            },
            {
                "name": "describe_table",
                "description": "Return complete table metadata from the schema catalog.",
            },
            {
                "name": "execute_query",
                "description": "Execute a read-only query against a configured source.",
            },
            {
                "name": "list_temporary_views",
                "description": "List temporary views created in the current server session.",
            },
            {
                "name": "create_temporary_view",
                "description": "Create a session-local temporary view for iterative analysis.",
            },
            {
                "name": "drop_temporary_view",
                "description": "Drop a temporary view created by this server session.",
            },
        ],
        "requires_auth": True,
        "auth_schema": {
            "dialect": {
                "type": "string",
                "description": "SQL dialect (sqlite, postgresql, mysql, etc.)",
                "secret": False,
            },
            "connection": {
                "type": "string",
                "description": "SQLAlchemy connection string",
                "secret": False,
            },
        },
        "is_local": True,
        "status": "available",
    },
]

# Fast lookup by id.
UPSTREAM_MCP_REGISTRY_BY_ID: dict[str, dict[str, Any]] = {
    entry["id"]: entry for entry in UPSTREAM_MCP_REGISTRY
}


def get_registry_entry(server_id: str) -> dict[str, Any] | None:
    """Return the registry entry for *server_id*, or ``None`` if not found."""
    return UPSTREAM_MCP_REGISTRY_BY_ID.get(server_id)


def list_registry_entries(data_type: str | None = None) -> list[dict[str, Any]]:
    """Return registry entries, optionally filtered by *data_type*."""
    if data_type is None:
        return list(UPSTREAM_MCP_REGISTRY)
    return [e for e in UPSTREAM_MCP_REGISTRY if e["data_type"] == data_type]
