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
- `/environment.yml` — Conda environment for local development and CLI usage
- `/config/config.yaml` — sample configuration

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

Useful checks:

- Run `MCP: List Servers` from the Command Palette to confirm the server is registered.
- Use the Chat tools picker to verify that `list_data_sources`, `search_schema`, `describe_table`, and `execute_query` are available.
- If the server fails to start, open the MCP output log from the Chat error indicator or the server list.

### Test prompts for Copilot

Use these prompts in Copilot Chat to verify that the MCP server is wired up correctly:

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

## Full free end-to-end test (220 tables + docs)

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

### 2) Generate a synthetic SQLite dataset with 220 fact tables

```bash
python scripts/generate_data.py
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
-- ubs-mcp-server --config config/big_config.yaml --transport stdio
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
