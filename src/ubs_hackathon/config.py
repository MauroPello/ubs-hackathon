from __future__ import annotations

import os
from pathlib import Path

import yaml

from .models import DataSourceConfig


DEFAULT_CONFIG_PATH = Path("config/config.yaml")


def _resolve_env(value: str) -> str:
    if not isinstance(value, str):
        return value
    if value.startswith("${") and value.endswith("}"):
        env_name = value[2:-1]
        return os.getenv(env_name, "")
    return value


def load_config(path: str | Path | None = None) -> tuple[list[DataSourceConfig], Path]:
    config_path = Path(path) if path else DEFAULT_CONFIG_PATH
    raw = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
    catalog_path = Path(raw.get("catalog", {}).get("db_path", "data/catalog.db"))

    sources: list[DataSourceConfig] = []
    for source in raw.get("data_sources", []):
        ds = DataSourceConfig(
            name=source["name"],
            type=source.get("type", "sqlite").lower(),
            connection=_resolve_env(source["connection"]),
        )
        sources.append(ds)

    return sources, catalog_path
