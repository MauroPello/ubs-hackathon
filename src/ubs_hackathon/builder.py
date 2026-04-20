from __future__ import annotations

import argparse
import logging

from .catalog import SchemaCatalog
from .config import load_config
from .datasource import build_data_source
from .models import TableDoc


def _apply_schema_docs(doc: TableDoc, docs_map: dict) -> None:
    source_docs = docs_map.get(doc.data_source, {})
    table_docs = source_docs.get("tables", {})
    graph_docs = source_docs.get("graph_entities", {})
    default_table_description = source_docs.get("default_table_description")
    is_graph_entity = doc.table_type in {"graph_node", "graph_relationship"}
    table_meta = table_docs.get(doc.table, {})
    if is_graph_entity:
        table_meta = graph_docs.get(doc.table, table_meta)

    if table_meta.get("description"):
        doc.description = table_meta["description"]
    elif (not is_graph_entity) and default_table_description:
        doc.description = default_table_description

    column_docs = table_meta.get("columns", {})
    for column in doc.columns:
        description = column_docs.get(column.name)
        if description:
            column.description = description


def sync_meta_from_config(
    sources: list[DataSourceConfig], docs_map: dict, meta_db_path: Path
) -> None:
    from .meta_store import MetaStore

    store = MetaStore(meta_db_path)

    # 1. Sync data sources
    for src in sources:
        store.upsert_data_source(
            name=src.name,
            type_=src.type,
            connection=src.connection,
            sensitive_columns=src.sensitive_columns,
            description=src.description,
            upstream_mcp_server_config_id=src.upstream_mcp_server_config_id,
        )

    # 2. Sync docs
    for ds_name, ds_docs in docs_map.items():
        # Check if this data source exists in meta store
        if not store.get_data_source(ds_name):
            continue

        # Default table description
        if ds_docs.get("default_table_description"):
            store.upsert_doc(ds_name, "table", None, ds_docs["default_table_description"])

        # Tables docs
        for table_name, table_meta in ds_docs.get("tables", {}).items():
            if table_meta.get("description"):
                store.upsert_doc(ds_name, "table", table_name, table_meta["description"])
            for col_name, col_desc in table_meta.get("columns", {}).items():
                store.upsert_doc(ds_name, "column", f"{table_name}.{col_name}", col_desc)

        # Graph entities
        for entity_name, entity_meta in ds_docs.get("graph_entities", {}).items():
            if entity_meta.get("description"):
                store.upsert_doc(
                    ds_name, "graph_entity", entity_name, entity_meta["description"]
                )
            for prop_name, prop_desc in entity_meta.get("columns", {}).items():
                store.upsert_doc(
                    ds_name, "graph_property", f"{entity_name}.{prop_name}", prop_desc
                )


def build_catalog(config_path: str | None = None) -> int:
    sources, catalog_path, meta_db_path, docs_map = load_config(config_path)
    
    print(f"🔄 Syncing configuration to meta-db at {meta_db_path}...")
    sync_meta_from_config(sources, docs_map, meta_db_path)
    
    catalog = SchemaCatalog(catalog_path)

    total_tables = 0
    for source_cfg in sources:
        source = build_data_source(source_cfg)
        for doc in source.catalog_docs():
            _apply_schema_docs(doc, docs_map)
            catalog.upsert_table_doc(doc)
            total_tables += 1

    print(f"✅ Indexed {total_tables} tables into {catalog_path}")
    return total_tables


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    parser = argparse.ArgumentParser(
        description="Sync config and build schema catalog from YAML"
    )
    parser.add_argument("--config", default=None, help="Path to YAML config")
    args = parser.parse_args()
    build_catalog(args.config)


if __name__ == "__main__":
    main()
