from __future__ import annotations

import json
from pathlib import Path
from neo4j import GraphDatabase

from .embeddings import EmbeddingModel, cosine_similarity, create_embedding_model
from .models import TableDoc

class SchemaCatalog:
    def __init__(
        self, catalog_db_path: Path | None = None, embedding_model: EmbeddingModel | None = None
    ) -> None:
        # Provide hardcoded connection parameters as per hackathon docs
        self.driver = GraphDatabase.driver("bolt://localhost:7687", auth=("neo4j", "ChangeMe123!"))
        self.embedding_model = embedding_model or create_embedding_model()
        self._ensure_schema()

    def _ensure_schema(self) -> None:
        with self.driver.session() as session:
            session.run("CREATE INDEX table_data_source IF NOT EXISTS FOR (t:Table) ON (t.data_source)")
            session.run("CREATE INDEX table_name IF NOT EXISTS FOR (t:Table) ON (t.table_name)")

    def _doc_text(self, doc: TableDoc) -> str:
        column_text = "\n".join(
            f"- {c.name} ({c.data_type}) {c.description or ''} nullable={c.nullable} samples={','.join(c.sample_values or [])}"
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

        with self.driver.session() as session:
            # Upsert Table node
            session.execute_write(self._merge_table, doc, text, embedding)
            # Upsert relationships
            session.execute_write(self._merge_foreign_keys, doc)

    @staticmethod
    def _merge_table(tx, doc: TableDoc, text: str, embedding: list[float]):
        tx.run("""
            MERGE (t:Table {data_source: $data_source, table_name: $table_name})
            SET t.doc_json = $doc_json,
                t.doc_text = $doc_text,
                t.embedding = $embedding
        """, data_source=doc.data_source, table_name=doc.table, doc_json=json.dumps(doc.to_dict()), doc_text=text, embedding=embedding)

    @staticmethod
    def _merge_foreign_keys(tx, doc: TableDoc):
        for fk in doc.foreign_keys:
            tx.run("""
                MATCH (t1:Table {data_source: $data_source, table_name: $table_name})
                MERGE (t2:Table {data_source: $data_source, table_name: $ref_table})
                MERGE (t1)-[:HAS_FOREIGN_KEY {column: $column, ref_column: $ref_column}]->(t2)
            """, data_source=doc.data_source, table_name=doc.table, ref_table=fk.ref_table, column=fk.column, ref_column=fk.ref_column)

    def delete_data_source(self, data_source: str) -> bool:
        with self.driver.session() as session:
            session.run("MATCH (t:Table {data_source: $data_source}) DETACH DELETE t", data_source=data_source)
        return True

    def describe_table(self, data_source: str, table: str) -> dict:
        with self.driver.session() as session:
            record = session.run("MATCH (t:Table {data_source: $ds, table_name: $t}) RETURN t.doc_json AS doc_json", ds=data_source, t=table).single()
            if not record:
                raise ValueError(f"Table not found in catalog: {data_source}.{table}")

            doc = json.loads(record["doc_json"])

            res = session.run("""
                MATCH (t1:Table {data_source: $ds, table_name: $tname})-[:HAS_FOREIGN_KEY]-(t2:Table)
                RETURN DISTINCT t2.table_name AS ref_table, t2.doc_json AS doc_json
            """, ds=data_source, tname=table)

            related_tables = []
            for rec in res:
                rel_doc = json.loads(rec["doc_json"]) if rec["doc_json"] else {}
                related_tables.append({
                    "table": rec["ref_table"],
                    "description": rel_doc.get("description", "")
                })

            doc["related_entities"] = related_tables
            return doc

    def search(
        self, query: str, top_k: int = 5, data_source: str | None = None
    ) -> list[dict]:
        q_vec = self.embedding_model.embed(query)
        with self.driver.session() as session:
            if data_source:
                result = session.run("MATCH (t:Table {data_source: $ds}) RETURN t.doc_json AS doc_json, t.embedding AS embedding", ds=data_source)
            else:
                result = session.run("MATCH (t:Table) RETURN t.doc_json AS doc_json, t.embedding AS embedding")

            rows = []
            for record in result:
                rows.append((record["doc_json"], record["embedding"]))

        scored: list[tuple[float, dict]] = []
        for doc_json_str, emb in rows:
            if not emb: continue
            score = cosine_similarity(q_vec, emb)
            doc = json.loads(doc_json_str)
            doc["score"] = round(score, 6)
            scored.append((score, doc))

        scored.sort(key=lambda s: s[0], reverse=True)
        top_tables = [item[1] for item in scored[: max(top_k, 0)]]

        # Graph RAG Enrichment: fetch 1st degree connections for context
        with self.driver.session() as session:
            for table_info in top_tables:
                ds = table_info["data_source"]
                tname = table_info["table"]

                res = session.run("""
                    MATCH (t1:Table {data_source: $ds, table_name: $tname})-[:HAS_FOREIGN_KEY]-(t2:Table)
                    RETURN DISTINCT t2.table_name AS ref_table, t2.doc_json AS doc_json
                """, ds=ds, tname=tname)

                related_tables = []
                for rec in res:
                    rel_doc = json.loads(rec["doc_json"]) if rec["doc_json"] else {}
                    related_tables.append({
                        "table": rec["ref_table"],
                        "description": rel_doc.get("description", "")
                    })

                table_info["related_tables"] = related_tables

        return top_tables
