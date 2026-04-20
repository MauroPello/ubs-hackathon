# Usage Guide

This guide explains how to run and interact with the UBS Hackathon system.

## Running the System

You can run all components (Backend, Frontend, and MCP Server) using the provided script:

```bash
bash scripts/run-all.sh
```

### Manual Commands

#### 1) Run Metadata Backend (REST API)
```bash
ubs-backend --meta-db data/meta.db --catalog data/catalog.db --host 127.0.0.1 --port 8080
```
Open `http://127.0.0.1:8080/` to manage data sources and documentation.

#### 2) Run MCP Server (SSE)
```bash
ubs-mcp-server --config config/config.yaml --transport sse --host 0.0.0.0 --port 8000
```

#### 3) Run Frontend
```bash
cd frontend
pnpm run dev
```

#### 4) Validate with MCP Inspector
```bash
npx @modelcontextprotocol/inspector -- ubs-mcp-server --config config/config.yaml --transport stdio
```

## Available MCP Tools

1. `list_data_sources()`: Lists configured data sources and capabilities.
2. `search_schema(query, top_k=5)`: Returns relevant tables for a natural-language question.
3. `describe_table(data_source, table)`: Returns complete table metadata.
4. `execute_query(data_source, sql, limit=200)`: Executes read-only SQL queries.
5. `list_upstream_mcp_sources()`: Lists configured upstream MCP servers.

## Testing with Copilot Chat

Use these prompts to verify the integration:

1. `List the data sources available through this MCP server.`
2. `Search the schema for revenue by region and product, and show me the top 5 matching tables.`
3. `Describe the table fact_business_001 in big_demo_sqlite.`
4. `Write a read-only SQL query that totals revenue by region and product for fact_business_001, then run it.`

## Stress-Test Prompts

1. `Find the best tables to analyze execution quality deterioration in stressed scenarios, then explain your table choices before querying.`
2. `Show top 10 country + product pairs by pnl_usd in Q1 2026 and include total trade_count and fail rate.`
3. `Identify desks with the largest gap between revenue_usd and cost_usd, grouped by scenario and quarter.`
4. `Correlate market_daily_signal volatility_index and spread_bps with fail_flag in fact_business_001; summarize high-risk regimes.`
