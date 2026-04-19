from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import Any


@dataclass(slots=True)
class DataSourceConfig:
    name: str
    type: str
    connection: str


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
