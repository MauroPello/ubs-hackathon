# ubs-hackathon

## Goal

Design a conversational **AI assistant** that helps employees answer business questions by intelligently selecting the most relevant tables and columns from a complex underlying database schema.

## Implemented solution

This repository now includes a working Python MCP server prototype with:

- **Multi-DBMS support via SQLAlchemy** — connects to any SQLAlchemy-supported database (SQLite, PostgreSQL, MySQL/MariaDB, SQL Server, Oracle, Snowflake, BigQuery, DuckDB, and more) using standard connection URLs; no custom code required per DBMS
- **Schema catalog builder** that introspects source databases and merges **existing company schema docs**
- **Semantic schema search** using free online embeddings (Hugging Face) with safe local fallback
- **Read-only SQL execution** safeguards for conversational analytics
- **MCP tool surface** for `list_data_sources`, `search_schema`, `describe_table`, and `execute_query`
- **SSE/HTTP-first hosting** for multi-user deployments, plus stdio support for local clients
- **REST backend for metadata management** (data-source and documentation CRUD)

## Project structure

- `/src/ubs_hackathon/server.py` — MCP server and tool definitions
- `/src/ubs_hackathon/builder.py` — schema catalog indexing pipeline
- `/src/ubs_hackathon/datasource.py` — data source abstraction and read-only query execution
- `/src/ubs_hackathon/catalog.py` — catalog persistence and semantic search
- `/src/ubs_hackathon/demo_seed.py` — demo database generator
- `/environment.yml` — Conda environment for local development and CLI usage
- `/config/config.yaml` — sample configuration

## Supported data sources

All data sources are powered by **[SQLAlchemy](https://www.sqlalchemy.org/)**, which means any database that has a SQLAlchemy dialect works out of the box — no custom adapter code required.

| Database | URL scheme | Extra install |
|---|---|---|
| SQLite (default) | `sqlite:///path/to/file.db` | *(stdlib, nothing to install)* |
| PostgreSQL | `postgresql+psycopg2://user:pw@host/db` | `pip install "ubs-hackathon[postgres]"` |
| MySQL / MariaDB | `mysql+pymysql://user:pw@host/db` | `pip install "ubs-hackathon[mysql]"` |
| SQL Server | `mssql+pyodbc://user:pw@host/db?driver=…` | `pip install "ubs-hackathon[mssql]"` |
| Oracle | `oracle+oracledb://user:pw@host/?service_name=s` | `pip install "ubs-hackathon[oracle]"` |
| Snowflake | `snowflake://user:pw@account/db/schema` | `pip install "ubs-hackathon[snowflake]"` |
| BigQuery | `bigquery://project/dataset` | `pip install "ubs-hackathon[bigquery]"` |
| DuckDB | `duckdb:///path/to/file.duckdb` | `pip install "ubs-hackathon[duckdb]"` |

Simply set the `connection` field in `config/config.yaml` to the appropriate URL.  Legacy entries that use `type: sqlite` with a bare file path continue to work unchanged.

For **non-SQL sources** (graph databases, vector stores, document stores) we recommend delegating to a purpose-built MCP server alongside this one:

- **Neo4j / Cypher** — [`mcp-neo4j-cypher`](https://github.com/neo4j-contrib/mcp-neo4j)
- **Vector stores** (Chroma, Weaviate, Pinecone) — their respective MCP servers or the SQLAlchemy `pgvector` dialect for PostgreSQL+pgvector

## Quickstart

### 1) Create the Conda environment

```bash
conda env create -f environment.yml
conda activate ubs-hackathon
```

### 2) Alternative: install with pip

If you prefer not to use Conda, install the package directly instead:

```bash
pip install -e .
```

### 3) Create demo database

```bash
ubs-seed-demo --db-path data/demo_business.db
```

### 4) Build schema catalog

```bash
ubs-build-catalog --config config/config.yaml
```

### 5) Run MCP server for multi-user HTTP hosting (SSE)

```bash
ubs-mcp-server --config config/config.yaml --transport sse --host 0.0.0.0 --port 8000
```

### 6) Optional: run MCP server for local client integrations (stdio)

```bash
ubs-mcp-server --config config/config.yaml --transport stdio
```

### 6b) Run metadata backend (REST API)

```bash
ubs-backend --meta-db data/meta.db --catalog data/catalog.db --host 127.0.0.1 --port 8080
```

Then open `http://127.0.0.1:8080/` for a small built-in UI to manage data sources, docs, and sync.

Available endpoints include:

- `GET/POST /data-sources`
- `GET/PUT/DELETE /data-sources/{name}`
- `GET/POST /data-sources/{name}/docs`
- `GET/PUT/DELETE /data-sources/{name}/docs/{id}`
- `POST /data-sources/{name}/sync`

### 7) Provide existing schema docs

You can pass documentation either:

- inline in `config/config.yaml` under `schema_docs`, or
- via `schema_docs_path` pointing to a YAML/JSON file.

## VS Code / Copilot Chat setup

To connect the local MCP server to GitHub Copilot Chat in VS Code, this repository includes a workspace MCP configuration at `.vscode/mcp.json`.

1. Open the workspace in VS Code.
2. Open Chat and make sure Copilot Chat is available in your account.
3. VS Code will discover the `ubs-hackathon` MCP server from `.vscode/mcp.json` and prompt you to trust it the first time.
4. The default config points at the Conda environment created from `environment.yml`: `/home/mpello/.conda/envs/ubs-hackathon/bin/python`.
5. If you recreate the environment elsewhere, update the `command` in `.vscode/mcp.json` to the new Python executable.

The server runs in stdio mode and uses the installed package from the Conda environment, so VS Code does not need a separate `PYTHONPATH` override.

### Embeddings configuration

By default, the catalog runs in `auto` mode:

- uses OpenAI embeddings if `OPENAI_API_KEY` is present,
- otherwise uses free online Hugging Face inference embeddings (no key required),
- and falls back to the local model automatically if the online call fails.

Optional environment variables:

- `UBS_EMBEDDINGS_PROVIDER` — `auto` (default), `openai`, `huggingface`, or `local`
- `OPENAI_API_KEY` — required only for `openai`
- `UBS_EMBEDDINGS_MODEL` — OpenAI model, defaults to `text-embedding-3-small`
- `UBS_EMBEDDINGS_BASE_URL` — OpenAI base URL, defaults to `https://api.openai.com/v1`
- `UBS_HF_EMBEDDINGS_MODEL` — defaults to `sentence-transformers/all-MiniLM-L6-v2`
- `UBS_HF_EMBEDDINGS_BASE_URL` — defaults to `https://api-inference.huggingface.co`
- `HF_API_TOKEN` — optional Hugging Face token (not required for basic free usage)

Useful checks:

- Run `MCP: List Servers` from the Command Palette to confirm the server is registered.
- Use the Chat tools picker to verify that `list_data_sources`, `search_schema`, `describe_table`, and `execute_query` are available.
- If the server fails to start, open the MCP output log from the Chat error indicator or the server list.

## Dataset choice for large-scale testing

The MCP server supports any SQLAlchemy-connected database, so you can point it at existing data warehouses (Snowflake, BigQuery, Redshift, etc.) or load a local dataset into SQLite, PostgreSQL, DuckDB, or any other supported engine.

For a real-world option with public documentation, the best fit is:

- **NYC TLC Trip Record Data** (official open dataset, strong data dictionary/docs, rich joins across trip/vendor/location dimensions)
- Documentation: https://www.nyc.gov/site/tlc/about/tlc-trip-record-data.page

For this hackathon repo, the practical default is to use the upgraded synthetic generator (`scripts/generate_data.py`) because it gives:

- large local data volume without external download dependencies,
- deterministic generation with configurable size,
- many interconnected dimensions and fact tables,
- complete schema documentation shipped as JSON for MCP retrieval.

### Base test prompts for Copilot

Use these prompts in Copilot Chat to verify that the MCP server is wired correctly:

1. `List the data sources available through this MCP server.`
   - Expected tool: `list_data_sources`
   - What to check: Copilot should name the configured source(s) and not invent extra ones.
2. `Search the schema for revenue by region and product, and show me the top 5 matching tables.`
   - Expected tool: `search_schema`
   - What to check: Copilot should surface the most relevant tables and explain why they match.
3. `Describe the table fact_business_001 in big_demo_sqlite.`
   - Expected tool: `describe_table`
   - What to check: Copilot should return columns, relationships, and any other table metadata.
4. `Write a read-only SQL query that totals revenue by region and product for fact_business_001, then run it.`
   - Expected tool: `execute_query`
   - What to check: Copilot should generate a SELECT-only query and return aggregated results.
5. `Before answering, search the schema for the best tables to answer: what was revenue in Q1 by region? Then explain the result.`
   - Expected tools: `search_schema` followed by `execute_query`
   - What to check: Copilot should use retrieval first, then query only the relevant tables.

If you want a quick smoke test, start with prompts 1 and 2. If those work, the server connection is good and the remaining prompts test table inspection and SQL execution.

## Full free end-to-end test (interconnected large schema + docs)

Use this flow to test the full setup with a realistic large schema (200+ tables) and included documentation.

### 1) Install dependencies

```bash
conda env create -f environment.yml
conda activate ubs-hackathon
```

If you are using a plain virtual environment instead of Conda, the existing pip flow still works:

```bash
pip install -e .
```

### 2) Generate the large synthetic SQLite dataset

```bash
python scripts/generate_data.py
```

### 3) Build the catalog

```bash
ubs-build-catalog --config config/big_config.yaml
```

You can increase scale if needed:

```bash
python scripts/generate_data.py --table-count 320 --rows-per-table 3000 --day-span 1095 --seed 42
```

Expected output includes `Indexed ... tables into data/big_catalog.db` with:

- many dimension/bridge/signal tables, and
- `fact_business_*` tables (default: `260` fact tables).

### 4) Run the MCP server

```bash
ubs-mcp-server --config config/big_config.yaml --transport stdio
```

### 5) Validate the end-to-end flow with MCP Inspector (free)

In a second terminal:

```bash
npx @modelcontextprotocol/inspector \
-- ubs-mcp-server --config config/big_config.yaml --transport stdio
```

Then run these tool calls in the inspector:

1. `list_data_sources()`
   - Expect one source: `big_demo_sqlite`.
2. `search_schema("pnl by region, product, desk and scenario", 5)`
   - Expect top matches among `fact_business_*`, `dim_product`, `dim_country`, `dim_region`, and `dim_desk`.
3. `describe_table("big_demo_sqlite", "fact_business_001")`
   - Expect full column metadata and foreign keys.
4. ```text
   execute_query(
     "big_demo_sqlite",
     "SELECT r.region_name,
             p.product_name,
             ROUND(SUM(f.revenue_usd),2) AS total_revenue_usd,
             ROUND(SUM(f.pnl_usd),2) AS total_pnl_usd
      FROM fact_business_001 f
      JOIN dim_country c ON f.country_id = c.country_id
      JOIN dim_region r ON c.region_id = r.region_id
      JOIN dim_product p ON f.product_id = p.product_id
      GROUP BY r.region_name, p.product_name
      ORDER BY total_revenue_usd DESC",
     50
   )
   ```
   - Expect aggregated results.

If all four succeed, the setup is validated end-to-end: schema ingestion, documentation merge, semantic retrieval, table introspection, and read-only SQL execution.

## Prompt pack to stress-test MCP data retrieval effectiveness

To make sure your Copilot agent doesn't cheat while trying to answer remove his possibility to read files.

Use these prompts in Copilot Chat (or any conversational AI connected to this MCP server):

1. `Find the best tables to analyze execution quality deterioration in stressed scenarios, then explain your table choices before querying.`
2. `Show top 10 country + product pairs by pnl_usd in Q1 2026 and include total trade_count and fail rate.`
3. `Identify desks with the largest gap between revenue_usd and cost_usd, grouped by scenario and quarter.`
4. `Correlate market_daily_signal volatility_index and spread_bps with fail_flag in fact_business_001; summarize high-risk regimes.`
5. `For counterparties marked systemic_flag = 1, show their customer segments, total notional_usd, and average slippage_bps.`
6. `Return only the SQL first for: monthly pnl trend by region and product family, then run it and summarize anomalies.`
7. `Do a two-step workflow: first find the most relevant table for customer-counterparty network concentration, then run a read-only query and explain concentration risk.`

What good behavior looks like:

- the assistant calls `search_schema` before writing SQL on non-trivial questions,
- joins follow FK paths across dimensions/bridge tables,
- results reference real columns (for example `revenue_usd`, `pnl_usd`, `fail_flag`, `volatility_index`),
- SQL remains read-only.

## Available MCP tools

1. `list_data_sources()`
   - Lists configured data sources and types.
2. `search_schema(query, top_k=5)`
   - Returns the most relevant tables for a natural-language question.
3. `describe_table(data_source, table)`
   - Returns complete table metadata (columns, foreign keys, row estimates).
4. `execute_query(data_source, sql, limit=200)`
   - Executes read-only SQL with row limits and mutation blocking.

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

- Add support for non-SQL sources (graph databases such as Neo4j via `mcp-neo4j-cypher`, vector stores such as Chroma or Weaviate via their MCP servers, or document stores via dedicated adapters)
- Replace local embedding model with managed embeddings and vector DB, or show that we could
- Add enterprise security features, or show that we could (RBAC, row-level controls, masking)
- Extend retrieval to non-SQL sources, or show that we could (Notion, Slack, Google Workspace)
