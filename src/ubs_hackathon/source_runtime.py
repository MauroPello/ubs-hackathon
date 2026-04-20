from __future__ import annotations

from .models import DataSourceConfig, DataSourceRegistration, UpstreamMCPServerConfigRecord
from .registry import get_registry_entry


class RuntimeResolutionError(ValueError):
    pass


def _resolve_sql_like_runtime(
    connector: UpstreamMCPServerConfigRecord,
) -> tuple[str, str]:
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


def resolve_runtime_type_and_connection(
    connector: UpstreamMCPServerConfigRecord,
) -> tuple[str, str]:
    if connector.server_id == "sql-like":
        return _resolve_sql_like_runtime(connector)

    entry = get_registry_entry(connector.server_id)
    data_type = str((entry or {}).get("data_type") or connector.server_id).strip().lower()
    if not data_type:
        raise RuntimeResolutionError(
            f"Connector '{connector.id}' has invalid server_id '{connector.server_id}'"
        )
    return data_type, f"upstream://{connector.id}"


def build_runtime_source_config(
    registration: DataSourceRegistration,
    connector: UpstreamMCPServerConfigRecord,
) -> DataSourceConfig:
    source_type, connection = resolve_runtime_type_and_connection(connector)
    return DataSourceConfig(
        name=registration.name,
        type=source_type,
        connection=connection,
        description=registration.description,
        databases=registration.databases,
        sensitive_columns=registration.sensitive_columns,
        upstream_mcp_server_config_id=registration.upstream_mcp_server_config_id,
    )
