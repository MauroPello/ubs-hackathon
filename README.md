# ubs-hackathon

## Goal

Design a conversational **AI assistant** that helps employees answer business questions by intelligently selecting the most relevant tables and columns from a complex underlying database schema.

## Implemented solution

This repository now includes a working Python MCP server prototype with:

- **DB-agnostic architecture** via data source adapters and MCP tool surface (SQLite implemented for demo, ready to extend to other DBMSes)
- **Schema catalog builder** that introspects source databases and merges **existing company schema docs**
- **Semantic schema search** using local embeddings for table/column retrieval
- **Read-only SQL execution** safeguards for conversational analytics
- **MCP tool surface** for `list_data_sources`, `search_schema`, `describe_table`, and `execute_query`
- **SSE/HTTP-first hosting** for multi-user deployments, plus stdio support for local clients

## Project structure

- `/src/ubs_hackathon/server.py` — MCP server and tool definitions
- `/src/ubs_hackathon/builder.py` — schema catalog indexing pipeline
- `/src/ubs_hackathon/datasource.py` — data source abstraction and read-only query execution
- `/src/ubs_hackathon/catalog.py` — catalog persistence and semantic search
- `/src/ubs_hackathon/demo_seed.py` — demo database generator
- `/config/config.yaml` — sample configuration

## Quickstart

### 1) Install dependencies

```bash
pip install -e .
```

### 2) Create demo database

```bash
ubs-seed-demo --db-path data/demo_business.db
```

### 3) Build schema catalog

```bash
ubs-build-catalog --config config/config.yaml
```

### 4) Run MCP server for multi-user HTTP hosting (SSE)

```bash
ubs-mcp-server --config config/config.yaml --transport sse --host 0.0.0.0 --port 8000
```

### 5) Optional: run MCP server for local client integrations (stdio)

```bash
ubs-mcp-server --config config/config.yaml --transport stdio
```

### 6) Provide existing schema docs

You can pass documentation either:

- inline in `config/config.yaml` under `schema_docs`, or
- via `schema_docs_path` pointing to a YAML/JSON file.

## Full free end-to-end test (220 tables + docs)

Use this flow to test the full setup with a realistic large schema (200+ tables) and included documentation.

### 1) Install dependencies

```bash
pip install -e .
```

### 2) Generate a synthetic SQLite dataset with 220 fact tables

```bash
python - <<'PY'
import json
import random
import sqlite3
from pathlib import Path

TABLE_COUNT = 220
ROWS_PER_TABLE = 500

data_dir = Path("data")
config_dir = Path("config")
data_dir.mkdir(parents=True, exist_ok=True)
config_dir.mkdir(parents=True, exist_ok=True)

db_path = data_dir / "big_demo.db"
docs_path = config_dir / "big_schema_docs.json"
cfg_path = config_dir / "big_config.yaml"

regions = ["EMEA", "AMER", "APAC", "LATAM"]
products = ["FX", "Rates", "Equities", "Credit", "Commodities"]

docs = {"big_demo_sqlite": {"tables": {}}}

with sqlite3.connect(db_path) as conn:
    cur = conn.cursor()
    cur.execute("PRAGMA foreign_keys = ON")

    cur.execute("DROP TABLE IF EXISTS dim_region")
    cur.execute("DROP TABLE IF EXISTS dim_product")
    cur.execute("CREATE TABLE dim_region (region_id INTEGER PRIMARY KEY, region_name TEXT NOT NULL)")
    cur.execute("CREATE TABLE dim_product (product_id INTEGER PRIMARY KEY, product_name TEXT NOT NULL)")
    cur.executemany(
        "INSERT INTO dim_region(region_id, region_name) VALUES (?, ?)",
        list(enumerate(regions, start=1)),
    )
    cur.executemany(
        "INSERT INTO dim_product(product_id, product_name) VALUES (?, ?)",
        list(enumerate(products, start=1)),
    )

    docs["big_demo_sqlite"]["tables"]["dim_region"] = {
        "description": "Reference table for reporting regions.",
        "columns": {
            "region_id": "Unique region identifier.",
            "region_name": "Region label used in reporting.",
        },
    }
    docs["big_demo_sqlite"]["tables"]["dim_product"] = {
        "description": "Reference table for product categories.",
        "columns": {
            "product_id": "Unique product identifier.",
            "product_name": "Product family label.",
        },
    }

    for i in range(1, TABLE_COUNT + 1):
        table = f"fact_business_{i:03d}"
        cur.execute(f"DROP TABLE IF EXISTS {table}")
        cur.execute(
            f"""
            CREATE TABLE {table} (
                event_id INTEGER PRIMARY KEY,
                event_date TEXT NOT NULL,
                region_id INTEGER NOT NULL,
                product_id INTEGER NOT NULL,
                customer_segment TEXT NOT NULL,
                revenue REAL NOT NULL,
                trade_count INTEGER NOT NULL,
                FOREIGN KEY(region_id) REFERENCES dim_region(region_id),
                FOREIGN KEY(product_id) REFERENCES dim_product(product_id)
            )
            """
        )
        rows = []
        for event_id in range(1, ROWS_PER_TABLE + 1):
            month = (event_id % 12) + 1
            day = (event_id % 28) + 1
            rows.append(
                (
                    event_id,
                    f"2026-{month:02d}-{day:02d}",
                    random.randint(1, len(regions)),
                    random.randint(1, len(products)),
                    random.choice(["Institutional", "Corporate", "Retail"]),
                    round(random.uniform(5_000, 500_000), 2),
                    random.randint(1, 200),
                )
            )
        cur.executemany(
            f"""
            INSERT INTO {table}
            (event_id, event_date, region_id, product_id, customer_segment, revenue, trade_count)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            rows,
        )
        docs["big_demo_sqlite"]["tables"][table] = {
            "description": f"Synthetic business fact table {i:03d} for analytics retrieval testing.",
            "columns": {
                "event_id": "Primary key for each business event.",
                "event_date": "Event booking date in YYYY-MM-DD format.",
                "region_id": "Foreign key to dim_region.",
                "product_id": "Foreign key to dim_product.",
                "customer_segment": "Segment bucket (Institutional, Corporate, Retail).",
                "revenue": "Revenue amount in base currency.",
                "trade_count": "Number of trades aggregated in the event record.",
            },
        }

with docs_path.open("w", encoding="utf-8") as f:
    json.dump(docs, f, indent=2)

cfg_path.write_text(
    "\n".join(
        [
            "catalog:",
            "  db_path: data/big_catalog.db",
            "data_sources:",
            "  - name: big_demo_sqlite",
            "    type: sqlite",
            "    connection: data/big_demo.db",
            "schema_docs_path: config/big_schema_docs.json",
            "",
        ]
    ),
    encoding="utf-8",
)

print(f"Created database: {db_path}")
print(f"Created schema docs: {docs_path}")
print(f"Created config: {cfg_path}")
print(f"Total documented tables: {len(docs['big_demo_sqlite']['tables'])}")
PY
```

### 3) Build the catalog

```bash
ubs-build-catalog --config config/big_config.yaml
```

Expected output includes `Indexed ... tables into data/big_catalog.db` (should be `222` tables: 220 fact + 2 dimension tables).

### 4) Run the MCP server

```bash
ubs-mcp-server --config config/big_config.yaml --transport stdio
```

### 5) Validate the end-to-end flow with MCP Inspector (free)

In a second terminal:

```bash
npx @modelcontextprotocol/inspector \
  --cli "ubs-mcp-server --config /absolute/path/to/config/big_config.yaml --transport stdio"
```

Then run these tool calls in the inspector:

1. `list_data_sources()`
   - Expect one source: `big_demo_sqlite`.
2. `search_schema("revenue by region and product", 5)`
   - Expect top matches among `fact_business_*` and dimension tables.
3. `describe_table("big_demo_sqlite", "fact_business_001")`
   - Expect full column metadata and foreign keys.
4. `execute_query("big_demo_sqlite", "SELECT r.region_name, p.product_name, ROUND(SUM(f.revenue),2) AS total_revenue FROM fact_business_001 f JOIN dim_region r ON f.region_id = r.region_id JOIN dim_product p ON f.product_id = p.product_id GROUP BY r.region_name, p.product_name ORDER BY total_revenue DESC", 50)`
   - Expect aggregated results.

If all four succeed, the setup is validated end-to-end: schema ingestion, documentation merge, semantic retrieval, table introspection, and read-only SQL execution.

## Available MCP tools

1. `list_data_sources()`
   - Lists configured data sources and types.
2. `search_schema(query, top_k=5)`
   - Returns the most relevant tables for a natural-language question.
3. `describe_table(data_source, table)`
   - Returns complete table metadata (columns, foreign keys, row estimates).
4. `execute_query(data_source, sql, limit=200)`
   - Executes read-only SQL with row limits and mutation blocking.
5. `rebuild_catalog()`
   - Re-indexes schemas from configured sources.

## Example prompt flow

- User asks: **"What was total revenue by region in Q1?"**
- Assistant calls `search_schema("revenue region q1")`
- Assistant receives `orders`, `customers`, `regions`
- Assistant generates SQL and calls `execute_query(...)`
- Assistant formats results as a business answer

## Claude Desktop integration snippet (optional local use)

Add a server entry to your Claude Desktop MCP configuration:

```json
{
  "mcpServers": {
    "ubs-hackathon": {
      "command": "ubs-mcp-server",
      "args": ["--config", "/absolute/path/to/config/config.yaml", "--transport", "stdio"]
    }
  }
}
```

## Next steps

- Add production adapters (Snowflake, BigQuery, Postgres, Oracle)
- Replace local embedding model with managed embeddings and vector DB
- Add enterprise security features (RBAC, row-level controls, masking)
- Extend retrieval to non-SQL sources (Notion, Slack, Google Workspace)
