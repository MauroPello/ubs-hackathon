from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from ubs_hackathon.builder import build_catalog
from ubs_hackathon.catalog import SchemaCatalog
from ubs_hackathon.config import load_config
from ubs_hackathon.datasource import build_data_source


def _write_graph_config(path: Path) -> Path:
    catalog_path = path.parent / "graph_catalog.db"
    payload = {
        "catalog": {"db_path": str(catalog_path)},
        "data_sources": [
            {
                "name": "demo_graph",
                "type": "graph",
                "connection": "delegated://graph",
                "adapter": "delegated_graph",
                "options": {
                    "graph_entities": [
                        {
                            "name": "Person",
                            "entity_type": "graph_node",
                            "description": "Person node",
                            "columns": [
                                {"name": "person_id", "data_type": "string"},
                                {"name": "segment", "data_type": "string"},
                            ],
                        },
                        {
                            "name": "BOUGHT",
                            "entity_type": "graph_relationship",
                            "description": "Purchase edge",
                            "columns": [{"name": "amount", "data_type": "float"}],
                        },
                    ]
                },
            }
        ],
        "schema_docs": {
            "demo_graph": {
                "graph_entities": {
                    "Person": {
                        "description": "Customer node",
                        "columns": {"segment": "Customer segment"},
                    }
                }
            }
        },
    }
    path.write_text(yaml.safe_dump(payload), encoding="utf-8")
    return catalog_path


def test_delegated_graph_source_capabilities_and_query_validation(tmp_path: Path) -> None:
    config_path = tmp_path / "graph_config.yaml"
    _write_graph_config(config_path)
    sources, _, _ = load_config(config_path)
    source = build_data_source(sources[0])

    capabilities = source.capabilities()
    assert capabilities["graph_schema_discovery"] is True
    assert capabilities["graph_read_only_query"] is True
    assert capabilities["sql_read_only_query"] is False

    assert source.list_graph_entities() == ["BOUGHT", "Person"]
    person = source.describe_graph_entity("Person")
    assert person.table_type == "graph_node"
    assert person.table == "Person"

    out = source.execute_graph_read_only("MATCH (p:Person) RETURN p LIMIT 5", limit=5)
    assert out["query"].startswith("MATCH")
    assert out["limit"] == 5
    assert out["delegated"]["delegated"] is False
    assert out["rows"] == []
    assert out["row_count"] == 0
    assert out["truncated"] is False

    with pytest.raises(ValueError, match="mutating"):
        source.execute_graph_read_only("MATCH (p:Person) DELETE p")


def test_build_catalog_indexes_graph_entities_and_docs(tmp_path: Path) -> None:
    config_path = tmp_path / "graph_config.yaml"
    catalog_path = _write_graph_config(config_path)

    indexed = build_catalog(str(config_path))
    assert indexed == 2

    catalog = SchemaCatalog(catalog_path)
    person = catalog.describe_table("demo_graph", "Person")
    assert person["table_type"] == "graph_node"
    assert person["description"] == "Customer node"
    assert person["columns"][1]["description"] == "Customer segment"

    matches = catalog.search("customer segment graph", top_k=2)
    assert any(m["table"] == "Person" for m in matches)
