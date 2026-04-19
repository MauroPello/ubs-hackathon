from __future__ import annotations

import json
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


def _load_docs(path: Path) -> dict:
    if not path.exists():
        return {}
    if path.suffix.lower() == ".json":
        return json.loads(path.read_text(encoding="utf-8"))
    return yaml.safe_load(path.read_text(encoding="utf-8")) or {}


def load_config(path: str | Path | None = None) -> tuple[list[DataSourceConfig], Path, dict]:
    config_path = Path(path) if path else DEFAULT_CONFIG_PATH
    raw = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
    catalog_path = Path(raw.get("catalog", {}).get("db_path", "data/catalog.db"))
    docs_path = raw.get("schema_docs_path")

    sources: list[DataSourceConfig] = []
    for source in raw.get("data_sources", []):
        ds = DataSourceConfig(
            name=source["name"],
            type=source.get("type", "sqlite").lower(),
            connection=_resolve_env(source["connection"]),
        )
        sources.append(ds)

    docs_map = raw.get("schema_docs", {}) or {}
    if docs_path:
        docs_map = _load_docs(Path(docs_path))

    return sources, catalog_path, docs_map
