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


def load_config(
    path: str | Path | None = None,
) -> tuple[list[DataSourceConfig], Path, Path, dict, list[dict], list[dict]]:
    config_path = Path(path) if path else DEFAULT_CONFIG_PATH
    raw = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
    catalog_path = Path(raw.get("catalog", {}).get("db_path", "data/catalog.db"))
    meta_db_path = Path(raw.get("catalog", {}).get("meta_db_path", "data/meta.db"))
    docs_path = raw.get("schema_docs_path")

    sources: list[DataSourceConfig] = []
    for source in raw.get("data_sources", []):
        upstream_id = (source.get("upstream_mcp_server_config_id") or "").strip()
        if not upstream_id:
            raise ValueError(
                f"Data source '{source.get('name', '<unnamed>')}' must set upstream_mcp_server_config_id"
            )
        ds = DataSourceConfig(
            name=source["name"],
            type=(source.get("type") or "managed").lower(),
            connection=_resolve_env(
                source.get("connection", f"managed://{upstream_id}")
            ),
            description=source.get("description"),
            adapter=(source.get("adapter") or "").strip().lower() or None,
            options=source.get("options"),
            databases=list(source.get("databases", []) or []),
            sensitive_columns=list(source.get("sensitive_columns", []) or []),
            upstream_mcp_server_config_id=upstream_id,
        )
        sources.append(ds)

    docs_map = raw.get("schema_docs", {}) or {}
    if docs_path:
        docs_map = _load_docs(Path(docs_path))

    return (
        sources,
        catalog_path,
        meta_db_path,
        docs_map,
        list(raw.get("upstream_mcp_server_configs", []) or []),
        list(raw.get("connectors_registry", []) or []),
    )


def get_registry_entry(
    registry: list[dict], server_id: str
) -> dict | None:
    """Return the registry entry for *server_id*, or ``None`` if not found."""
    for entry in registry:
        if entry.get("id") == server_id:
            return entry
    return None


def list_registry_entries(
    registry: list[dict], data_type: str | None = None
) -> list[dict]:
    """Return registry entries, optionally filtered by *data_type*."""
    if data_type is None:
        return list(registry)
    return [e for e in registry if e.get("data_type") == data_type]
