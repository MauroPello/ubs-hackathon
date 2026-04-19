from __future__ import annotations

import argparse

from .catalog import SchemaCatalog
from .config import load_config
from .datasource import build_data_source


def build_catalog(config_path: str | None = None) -> int:
    sources, catalog_path = load_config(config_path)
    catalog = SchemaCatalog(catalog_path)

    total_tables = 0
    for source_cfg in sources:
        source = build_data_source(source_cfg)
        tables = source.list_tables()
        for table in tables:
            doc = source.table_doc(table)
            catalog.upsert_table_doc(doc)
            total_tables += 1

    print(f"Indexed {total_tables} tables into {catalog_path}")
    return total_tables


def main() -> None:
    parser = argparse.ArgumentParser(description="Build schema catalog from configured data sources")
    parser.add_argument("--config", default=None, help="Path to YAML config")
    args = parser.parse_args()
    build_catalog(args.config)


if __name__ == "__main__":
    main()
