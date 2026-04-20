from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import Any


@dataclass(slots=True)
class DataSourceConfig:
    name: str
    type: str
    connection: str
    adapter: str | None = None
    options: dict[str, Any] | None = None


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
    type: str
    connection: str
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
