# UBS Hackathon: Conversational AI Assistant

Design a conversational **AI assistant** that helps employees answer business questions by intelligently selecting the most relevant tables and columns from a complex underlying database schema.

## Key Features

- **Multi-DBMS support via SQLAlchemy** — connects to SQLite, PostgreSQL, MySQL, Snowflake, DuckDB, and more.
- **Semantic schema search** — finds relevant tables using natural language.
- **Enterprise Data Masking** — protects sensitive columns in results.
- **Model Context Protocol (MCP)** — native integration with Copilot Chat, Claude Desktop, and more.
- **Modern UI** — Built with Nuxt 4 and Nuxt UI for managing data sources and documentation.

## Quickstart

Get the system up and running in minutes:

1. **Initialize Environment**:
   ```bash
   bash scripts/init-env.sh
   ```
2. **Initialize Data**:
   ```bash
   bash scripts/init-data.sh
   ```
3. **Build the schema catalog**:
   ```bash
   bash scripts/build-catalog.sh
   ```
4. **Run the System**:
   ```bash
   bash scripts/run-all.sh
   ```

5. **Wipe Data (Optional)**:
   ```bash
   bash scripts/wipe-data.sh
   ```

## Documentation

For more detailed information, please refer to the following guides:

- 🛠️ **[Setup Guide](docs/setup.md)**: Installation and environment configuration.
- 🚀 **[Usage Guide](docs/usage.md)**: How to run the system and interact with MCP tools.
- 🧠 **[Technical Documentation](docs/technical.md)**: Architecture, embeddings, and datasets.
- 🌳 **[Neo4j Setup](docs/neo4j.md)**: Integration with graph databases.

## Project Structure

- `/src/ubs_hackathon` — Core MCP server and backend logic.
- `/frontend` — Nuxt 4 management dashboard.
- `/scripts` — Automation scripts for initialization and execution.
- `/config` — Configuration files for data sources.
- `/docs` — Detailed documentation and guides.

## License

Apache-2.0
