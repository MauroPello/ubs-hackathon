from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from .embeddings import EmbeddingModel, cosine_similarity, create_embedding_model
from .models import TableDoc

CATALOG_SCHEMA = """
CREATE TABLE IF NOT EXISTS table_docs (
    data_source TEXT NOT NULL,
    table_name TEXT NOT NULL,
    doc_json TEXT NOT NULL,
    doc_text TEXT NOT NULL,
    embedding_json TEXT NOT NULL,
    PRIMARY KEY (data_source, table_name)
);
"""


class SchemaCatalog:
    def __init__(
        self, catalog_db_path: Path, embedding_model: EmbeddingModel | None = None
    ) -> None:
        self.catalog_db_path = catalog_db_path
        self.catalog_db_path.parent.mkdir(parents=True, exist_ok=True)
        self.embedding_model = embedding_model or create_embedding_model()
        self._ensure_schema()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.catalog_db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _ensure_schema(self) -> None:
        with self._connect() as conn:
            conn.executescript(CATALOG_SCHEMA)

    def _doc_text(self, doc: TableDoc) -> str:
        column_text = "\n".join(
            f"- {c.name} ({c.data_type}) nullable={c.nullable} samples={','.join(c.sample_values or [])}"
            for c in doc.columns
        )
        fk_text = "\n".join(
            f"- {fk.column} -> {fk.ref_table}.{fk.ref_column}"
            for fk in doc.foreign_keys
        )
        return (
            f"Data source: {doc.data_source}\n"
            f"Table: {doc.table}\n"
            f"Type: {doc.table_type}\n"
            f"Description: {doc.description or ''}\n"
            f"Row estimate: {doc.row_count_estimate}\n"
            f"Columns:\n{column_text}\n"
            f"Foreign keys:\n{fk_text}"
        )

    def upsert_table_doc(self, doc: TableDoc) -> None:
        text = self._doc_text(doc)
        embedding = self.embedding_model.embed(text)

        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO table_docs (data_source, table_name, doc_json, doc_text, embedding_json)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(data_source, table_name)
                DO UPDATE SET
                    doc_json = excluded.doc_json,
                    doc_text = excluded.doc_text,
                    embedding_json = excluded.embedding_json
                """,
                (
                    doc.data_source,
                    doc.table,
                    json.dumps(doc.to_dict()),
                    text,
                    json.dumps(embedding),
                ),
            )

    def describe_table(self, data_source: str, table: str) -> dict:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT doc_json FROM table_docs WHERE data_source = ? AND table_name = ?",
                (data_source, table),
            ).fetchone()
        if not row:
            raise ValueError(f"Table not found in catalog: {data_source}.{table}")
        return json.loads(row["doc_json"])

    def search(self, query: str, top_k: int = 5, data_source: str | None = None) -> list[dict]:
        q_vec = self.embedding_model.embed(query)
        with self._connect() as conn:
            if data_source:
                rows = conn.execute(
                    "SELECT data_source, table_name, doc_json, embedding_json FROM table_docs WHERE data_source = ?",
                    (data_source,),
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT data_source, table_name, doc_json, embedding_json FROM table_docs"
                ).fetchall()

        scored: list[tuple[float, dict]] = []
        for row in rows:
            emb = json.loads(row["embedding_json"])
            score = cosine_similarity(q_vec, emb)
            doc = json.loads(row["doc_json"])
            doc["score"] = round(score, 6)
            scored.append((score, doc))

        scored.sort(key=lambda s: s[0], reverse=True)
        return [item[1] for item in scored[: max(top_k, 0)]]
