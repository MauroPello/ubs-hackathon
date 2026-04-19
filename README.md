# ubs-hackathon

## Goal

Design a conversational **AI assistant** that helps employees answer business questions by intelligently selecting the most relevant tables and columns from a complex underlying database schema.

## Implemented solution

This repository now includes a working Python MCP server prototype with:

- **DB-agnostic architecture** via data source adapters (SQLite implemented, extensible to more DBMSes)
- **Schema catalog builder** that introspects source databases and stores table documentation
- **Semantic schema search** using local embeddings for table/column retrieval
- **Read-only SQL execution** safeguards for conversational analytics
- **MCP tool surface** for `list_data_sources`, `search_schema`, `describe_table`, and `execute_query`
- **Stdio + SSE transport options** for local and hosted integrations

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

### 4) Run MCP server (Claude Desktop / stdio)

```bash
ubs-mcp-server --config config/config.yaml --transport stdio
```

### 5) Run MCP server (hosted / SSE)

```bash
ubs-mcp-server --config config/config.yaml --transport sse --host 0.0.0.0 --port 8000
```

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

## Claude Desktop integration snippet

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
