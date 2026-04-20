from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import Any


@dataclass(slots=True)
class DataSourceConfig:
    name: str
    type: str
    connection: str
    description: str | None = None
    adapter: str | None = None
    options: dict[str, Any] | None = None
    databases: list[str] | None = None
    sensitive_columns: list[str] | None = None
    upstream_mcp_server_config_id: str | None = None


@dataclass(slots=True)
class ColumnDoc:
    name: str
    data_type: str
    nullable: bool
    description: str | None = None
    sample_values: list[str] | None = None


@dataclass(slots=True)
class ForeignKeyDoc:
    column: str
    ref_table: str
    ref_column: str


@dataclass(slots=True)
class TableDoc:
    data_source: str
    table: str
    table_type: str
    description: str | None
    row_count_estimate: int | None
    columns: list[ColumnDoc]
    foreign_keys: list[ForeignKeyDoc]

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        return payload


@dataclass(slots=True)
class DataSourceRegistration:
    name: str
    databases: list[str]
    sensitive_columns: list[str]
    created_at: str
    updated_at: str
    description: str | None = None
    upstream_mcp_server_config_id: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class UpstreamMCPServerConfigRecord:
    """A user-configured instance of an upstream MCP server."""

    id: str
    server_id: str
    name: str
    endpoint: str | None
    auth: dict[str, Any]
    exposed_tools: list[str]
    created_at: str
    updated_at: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class DocEntry:
    id: int
    data_source: str
    doc_type: str
    target: str | None
    content: str
    created_at: str
    updated_at: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class AuditLogEntry:
    id: int | None
    timestamp: str
    action: str
    details: str | None
    actor: str
    status: str
    latency_ms: int | None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
