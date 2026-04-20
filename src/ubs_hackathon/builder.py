from __future__ import annotations

import argparse

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


def build_catalog(config_path: str | None = None) -> int:
    sources, catalog_path, docs_map = load_config(config_path)
    catalog = SchemaCatalog(catalog_path)

    total_tables = 0
    for source_cfg in sources:
        source = build_data_source(source_cfg)
        for doc in source.catalog_docs():
            _apply_schema_docs(doc, docs_map)
            catalog.upsert_table_doc(doc)
            total_tables += 1

    print(f"Indexed {total_tables} tables into {catalog_path}")
    return total_tables


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Build schema catalog from configured data sources"
    )
    parser.add_argument("--config", default=None, help="Path to YAML config")
    args = parser.parse_args()
    build_catalog(args.config)


if __name__ == "__main__":
    main()
