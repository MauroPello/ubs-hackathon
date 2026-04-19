from ubs_hackathon.builder import _apply_schema_docs
from ubs_hackathon.models import ColumnDoc, TableDoc


def test_apply_schema_docs_enriches_table_and_columns() -> None:
    doc = TableDoc(
        data_source="demo",
        table="orders",
        table_type="table",
        description=None,
        row_count_estimate=10,
        columns=[
            ColumnDoc(name="order_id", data_type="INTEGER", nullable=False),
            ColumnDoc(name="revenue", data_type="REAL", nullable=False),
        ],
        foreign_keys=[],
    )
    docs_map = {
        "demo": {
            "tables": {
                "orders": {
                    "description": "Order fact table.",
                    "columns": {"revenue": "Booked revenue amount."},
                }
            }
        }
    }

    _apply_schema_docs(doc, docs_map)

    assert doc.description == "Order fact table."
    assert doc.columns[0].description is None
    assert doc.columns[1].description == "Booked revenue amount."
