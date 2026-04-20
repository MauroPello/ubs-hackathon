from .models import (
    DataSourceConfig,
    DataSourceRegistration,
    UpstreamMCPServerConfigRecord,
)
from .config import get_registry_entry

# The three canonical source types recognised by the system.
SQL_SOURCE_TYPE = "sql"
GRAPH_SOURCE_TYPE = "graph"
DOCUMENTS_SOURCE_TYPE = "documents"
UPSTREAM_SOURCE_TYPES: frozenset[str] = frozenset(
    {GRAPH_SOURCE_TYPE, DOCUMENTS_SOURCE_TYPE}
)
ALL_SOURCE_TYPES: frozenset[str] = frozenset(
    {SQL_SOURCE_TYPE, GRAPH_SOURCE_TYPE, DOCUMENTS_SOURCE_TYPE}
)


class RuntimeResolutionError(ValueError):
    pass


def resolve_data_type(
    connector: UpstreamMCPServerConfigRecord,
    registry: list[dict],
) -> str:
    """Return the canonical data type for *connector* (``sql``, ``graph``, or ``documents``)."""
    entry = get_registry_entry(registry, connector.server_id)
    data_type = (
        str((entry or {}).get("data_type") or connector.server_id).strip().lower()
    )
    if data_type not in ALL_SOURCE_TYPES:
        raise RuntimeResolutionError(
            f"Connector '{connector.id}' has unsupported data_type '{data_type}' "
            f"(server_id='{connector.server_id}'). "
            f"Supported types: {', '.join(sorted(ALL_SOURCE_TYPES))}"
        )
    return data_type


def _resolve_sql_runtime(
    connector: UpstreamMCPServerConfigRecord,
) -> tuple[str, str]:
    """Extract (dialect, connection) from a SQL-like connector's auth."""
    dialect = str(connector.auth.get("dialect") or "").strip().lower()
    connection = str(connector.auth.get("connection") or "").strip()
    if not dialect:
        raise RuntimeResolutionError(
            f"Connector '{connector.id}' is missing required auth.dialect"
        )
    if not connection:
        raise RuntimeResolutionError(
            f"Connector '{connector.id}' is missing required auth.connection"
        )
    return dialect, connection


def build_runtime_source_config(
    registration: DataSourceRegistration,
    connector: UpstreamMCPServerConfigRecord,
    registry: list[dict],
) -> DataSourceConfig:
    """Build a fully-resolved :class:`DataSourceConfig` for any source type.

    * **SQL** sources: resolves ``type`` and ``connection`` from the
      connector's ``auth.dialect`` and ``auth.connection``.
    * **Graph / Documents** (upstream) sources: sets the canonical type and
      packs ``endpoint`` and ``exposed_tools`` into ``options`` so that the
      factory can create an :class:`UpstreamMCPDataSource`.
    """
    data_type = resolve_data_type(connector, registry)

    if data_type == SQL_SOURCE_TYPE:
        source_type, connection = _resolve_sql_runtime(connector)
        return DataSourceConfig(
            name=registration.name,
            type=source_type,
            connection=connection,
            description=registration.description,
            databases=registration.databases,
            sensitive_columns=registration.sensitive_columns,
            upstream_mcp_server_config_id=registration.upstream_mcp_server_config_id,
        )

    # Upstream (graph / documents)
    exposed_tools: list[str] = list(connector.exposed_tools or [])
    return DataSourceConfig(
        name=registration.name,
        type=data_type,
        description=registration.description,
        databases=registration.databases,
        sensitive_columns=registration.sensitive_columns,
        upstream_mcp_server_config_id=registration.upstream_mcp_server_config_id,
        options={
            "endpoint": connector.endpoint or "",
            "exposed_tools": exposed_tools,
        },
    )
